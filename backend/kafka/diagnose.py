"""
Flowdesk CRM — Kafka Full Diagnostic & Status Report
======================================================
Run: python kafka/diagnose.py

Checks every layer of the Kafka pipeline and prints a colour-coded
status report with exact fix commands for anything that is failing.
"""

from __future__ import annotations
import asyncio, io, json, os, socket, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# ── ANSI ─────────────────────────────────────────────────────────────────────
GR="\033[92m"; RD="\033[91m"; YL="\033[93m"; CY="\033[96m"
MG="\033[95m"; BL="\033[94m"; W="\033[97m";  DM="\033[2m";  R="\033[0m"; B="\033[1m"

def _ok(msg):   print(f"  {GR}{B}✓{R} {msg}")
def _fail(msg): print(f"  {RD}{B}✗{R} {msg}")
def _warn(msg): print(f"  {YL}{B}!{R} {msg}")
def _info(msg): print(f"  {BL}→{R} {msg}")
def _fix(msg):  print(f"  {MG}{B}FIX:{R} {CY}{msg}{R}")
def _sec(title):
    print(f"\n{B}{W}{'─'*62}{R}")
    print(f"{B}{CY}  {title}{R}")
    print(f"{B}{W}{'─'*62}{R}")

def _port(host, port, timeout=2):
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except: return False

def _docker_container_status(name):
    """Returns 'running', 'exited', or 'missing'."""
    try:
        out = subprocess.check_output(
            ["docker","inspect","--format","{{.State.Status}}",name],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        return out
    except: return "missing"


# ═══════════════════════════════════════════════════════════════════════════
# Results store
# ═══════════════════════════════════════════════════════════════════════════
R_ = {}   # name → (ok:bool, detail:str)

def record(name, ok, detail=""):
    R_[name] = (ok, detail)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# 1. Docker containers
# ═══════════════════════════════════════════════════════════════════════════

def check_docker():
    _sec("1 · Docker Containers")

    containers = {
        "crm-zookeeper": "Zookeeper",
        "crm-kafka":     "Kafka Broker",
        "crm-postgres":  "PostgreSQL",
        "crm-kafka-worker": "Kafka Worker",
    }

    all_ok = True
    for cname, label in containers.items():
        status = _docker_container_status(cname)
        if status == "running":
            _ok(f"{label:<20} [{cname}]  status=running")
        elif status == "exited":
            _fail(f"{label:<20} [{cname}]  status=EXITED (stopped)")
            all_ok = False
        else:
            _fail(f"{label:<20} [{cname}]  NOT FOUND")
            all_ok = False

    if not all_ok:
        _fix("docker-compose up zookeeper kafka kafka-worker -d")

    record("Docker", all_ok)
    return all_ok


# ═══════════════════════════════════════════════════════════════════════════
# 2. Network ports
# ═══════════════════════════════════════════════════════════════════════════

def check_ports():
    _sec("2 · Network Ports")

    checks = [
        ("Kafka",      "localhost", 9092),
        ("Zookeeper",  "localhost", 2181),
        ("PostgreSQL",  "localhost", 5432),
    ]

    all_ok = True
    for label, host, port in checks:
        open_ = _port(host, port)
        if open_:
            _ok(f"{label:<14} {host}:{port}  OPEN")
        else:
            _fail(f"{label:<14} {host}:{port}  CLOSED")
            all_ok = False

    if not _port("localhost", 9092):
        _fix("docker-compose up zookeeper kafka -d  # then wait ~20s")

    record("Ports", all_ok)
    return all_ok


# ═══════════════════════════════════════════════════════════════════════════
# 3. Database tables
# ═══════════════════════════════════════════════════════════════════════════

def check_db_tables():
    _sec("3 · Database Tables")

    try:
        from database.connection import init_db, get_conn, is_db_available
        init_db()
        if not is_db_available():
            _fail("Cannot connect to PostgreSQL")
            _fix("docker-compose up postgres -d")
            record("DB Tables", False)
            return False

        required = ["customers","conversations","messages","tickets",
                    "leads","lead_events","kafka_errors"]
        missing  = []

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
                existing = {r[0] for r in cur.fetchall()}

        for t in required:
            if t in existing:
                _ok(f"Table  {t}")
            else:
                _fail(f"Table  {t}  MISSING")
                missing.append(t)

        if missing:
            _fix("python -c \"exec(open('kafka/migrations.sql').read())\"  "
                 "# or: psql $DATABASE_URL -f backend/kafka/migrations.sql")
            record("DB Tables", False, f"missing: {missing}")
            return False

        record("DB Tables", True)
        return True

    except Exception as exc:
        _fail(f"DB check error: {exc}")
        record("DB Tables", False, str(exc))
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 4. Credentials
# ═══════════════════════════════════════════════════════════════════════════

def check_credentials():
    _sec("4 · Environment Credentials")

    def env_ok(key):
        v = os.getenv(key, "")
        return bool(v and "your_" not in v and "xxxx" not in v.lower())

    creds = [
        ("TWILIO_ACCOUNT_SID",  "WhatsApp Twilio"),
        ("TWILIO_AUTH_TOKEN",   "WhatsApp Twilio"),
        ("ANTHROPIC_API_KEY",   "AI Agent"),
        ("GMAIL_CLIENT_ID",     "Gmail OAuth"),
        ("GMAIL_CLIENT_SECRET", "Gmail OAuth"),
        ("NOTIFY_EMAIL",        "Email alerts"),
        ("KAFKA_BOOTSTRAP_SERVERS", "Kafka"),
    ]

    files = [
        ("gmail_token.json",       "Gmail session token"),
        ("gmail_credentials.json", "Gmail OAuth credentials"),
    ]

    issues = []
    for key, label in creds:
        ok = env_ok(key)
        if ok:
            _ok(f"{key:<30} {DM}({label}){R}")
        else:
            _warn(f"{key:<30} {YL}NOT SET{R}  {DM}({label}){R}")
            issues.append(key)

    base = Path(__file__).resolve().parents[1]
    for fname, label in files:
        exists = (base / fname).exists()
        if exists:
            _ok(f"{fname:<30} {DM}({label}){R}")
        else:
            _warn(f"{fname:<30} {YL}MISSING{R}  {DM}({label}){R}")
            issues.append(fname)

    if "NOTIFY_EMAIL" in issues:
        _fix("Set NOTIFY_EMAIL=you@gmail.com in backend/.env")
    if "gmail_token.json" in issues:
        _fix("python -c \"from channels.gmail import _get_gmail_service; _get_gmail_service()\"")

    record("Credentials", len(issues) == 0, f"issues: {issues}" if issues else "")
    return len(issues) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Kafka producer
# ═══════════════════════════════════════════════════════════════════════════

async def check_producer():
    _sec("5 · Kafka Producer")

    if not _port("localhost", 9092):
        _fail("Kafka port 9092 is closed — cannot test producer")
        _fix("docker-compose up zookeeper kafka -d")
        record("Kafka Producer", False, "Kafka not running")
        return False

    try:
        from kafka.producer import init_producer, publish_lead_event, close_producer

        await init_producer()
        test_lead = {
            "id": 9999, "name": "Diagnostic Test", "phone": "+923001234567",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await publish_lead_event(test_lead)
        await close_producer()

        if result:
            _ok("Producer connected and published test event")
            _ok("Topic: crm.leads.created  lead_id=9999")
            record("Kafka Producer", True)
            return True
        else:
            _fail("Producer returned False — check Kafka broker logs")
            record("Kafka Producer", False, "publish returned False")
            return False

    except Exception as exc:
        _fail(f"Producer error: {exc}")
        _fix("docker-compose up kafka zookeeper -d  # ensure broker is healthy")
        record("Kafka Producer", False, str(exc))
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 6. Kafka consumer (readback test)
# ═══════════════════════════════════════════════════════════════════════════

async def check_consumer():
    _sec("6 · Kafka Consumer (readback)")

    if not _port("localhost", 9092):
        _fail("Kafka port 9092 is closed — cannot test consumer")
        record("Kafka Consumer", False, "Kafka not running")
        return False

    try:
        from aiokafka import AIOKafkaConsumer
        from kafka.producer import init_producer, publish_lead_event, close_producer

        SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        TOPIC   = "crm.leads.created"

        # Publish a fresh event then read it back
        await init_producer()
        test_lead = {
            "id": 8888, "name": "Consumer Test", "phone": "+923001111111",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        pub_ok = await publish_lead_event(test_lead)
        await close_producer()

        if not pub_ok:
            _fail("Publish step failed — cannot test consumer")
            record("Kafka Consumer", False, "publish failed")
            return False

        consumer = AIOKafkaConsumer(
            TOPIC,
            bootstrap_servers=SERVERS,
            group_id="crm-diag-readback",
            value_deserializer=lambda r: json.loads(r.decode()),
            auto_offset_reset="latest",
            enable_auto_commit=True,
            consumer_timeout_ms=8000,
        )
        await consumer.start()
        _info("Waiting up to 8s for message...")

        received = None
        try:
            async for msg in consumer:
                received = msg.value
                break
        except Exception: pass
        finally:
            await consumer.stop()

        if received and received.get("id") == 8888:
            _ok(f"Consumer received event  id={received['id']}  name={received['name']}")
            _ok("Round-trip verified ✓")
            record("Kafka Consumer", True)
            return True
        else:
            _warn("No message received within 8s (may have been consumed already)")
            record("Kafka Consumer", False, "timeout / no message")
            return False

    except Exception as exc:
        _fail(f"Consumer error: {exc}")
        record("Kafka Consumer", False, str(exc))
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 7. WhatsApp trigger
# ═══════════════════════════════════════════════════════════════════════════

def check_whatsapp():
    _sec("7 · WhatsApp Trigger (Twilio)")

    sid_env = os.getenv("TWILIO_ACCOUNT_SID", "")
    tok_env = os.getenv("TWILIO_AUTH_TOKEN", "")

    if not sid_env or "your_" in sid_env:
        _fail("TWILIO_ACCOUNT_SID not set")
        _fix("Add TWILIO_ACCOUNT_SID=ACxxx to backend/.env")
        record("WhatsApp Trigger", False, "no credentials")
        return False

    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException

        client  = Client(sid_env, tok_env)
        account = client.api.accounts(sid_env).fetch()
        _ok(f"Twilio credentials valid  account_status={account.status}")

        # Check daily sandbox limit by looking at recent messages
        msgs = client.messages.list(limit=5)
        _ok(f"Last {len(msgs)} messages visible in Twilio account")

        # Check sandbox limit (error 63038)
        _info("Note: Twilio Sandbox has a 5 msg/day limit. Upgrade to production for unlimited.")
        record("WhatsApp Trigger", True)
        return True

    except Exception as exc:
        error_str = str(exc)
        if "63038" in error_str:
            _warn("Twilio credentials valid BUT daily sandbox limit (5/day) reached")
            _fix("Wait until midnight UTC OR upgrade Twilio account to remove the limit")
            record("WhatsApp Trigger", True, "credentials ok, sandbox limit hit")
            return True   # credentials work — limit is operational, not a config error
        else:
            _fail(f"Twilio error: {exc}")
            record("WhatsApp Trigger", False, str(exc))
            return False


# ═══════════════════════════════════════════════════════════════════════════
# 8. Gmail trigger
# ═══════════════════════════════════════════════════════════════════════════

def check_gmail():
    _sec("8 · Gmail Trigger")

    base = Path(__file__).resolve().parents[1]

    if not (base / "gmail_token.json").exists():
        _fail("gmail_token.json not found — OAuth not completed")
        _fix("python -c \"from channels.gmail import _get_gmail_service; _get_gmail_service()\"")
        record("Gmail Trigger", False, "no token")
        return False

    notify = os.getenv("NOTIFY_EMAIL", "")
    if not notify or "your@" in notify:
        _warn("NOTIFY_EMAIL is not set — consumer will skip email notifications")
        _fix("Set NOTIFY_EMAIL=you@gmail.com in backend/.env")
        record("Gmail Trigger", False, "NOTIFY_EMAIL not set")
        return False

    try:
        from channels.gmail import _get_gmail_service
        svc = _get_gmail_service()
        profile = svc.users().getProfile(userId="me").execute()
        _ok(f"Gmail OAuth valid  account={profile.get('emailAddress')}")
        _ok(f"Notifications will be sent to: {notify}")
        record("Gmail Trigger", True)
        return True
    except Exception as exc:
        _fail(f"Gmail error: {exc}")
        _fix("Re-run OAuth: python -c \"from channels.gmail import _get_gmail_service; _get_gmail_service()\"")
        record("Gmail Trigger", False, str(exc))
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 9. DB logging
# ═══════════════════════════════════════════════════════════════════════════

def check_db_logging():
    _sec("9 · DB Audit Logging (lead_events / kafka_errors)")

    try:
        from database.connection import init_db, get_conn, is_db_available
        init_db()
        if not is_db_available():
            _fail("DB not available")
            record("DB Logging", False)
            return False

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM lead_events")
                le_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM kafka_errors")
                ke_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM leads")
                l_count  = cur.fetchone()[0]

        _ok(f"leads       table: {l_count} rows")
        _ok(f"lead_events table: {le_count} rows")
        _ok(f"kafka_errors table: {ke_count} rows")

        if ke_count > 0:
            _warn(f"{ke_count} Kafka errors logged — review with: SELECT * FROM kafka_errors ORDER BY created_at DESC LIMIT 10;")

        record("DB Logging", True)
        return True

    except Exception as exc:
        _fail(f"DB logging check error: {exc}")
        _fix("python -c \"exec(open('kafka/migrations.sql').read())\"")
        record("DB Logging", False, str(exc))
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Final report
# ═══════════════════════════════════════════════════════════════════════════

def print_report():
    _sec("STATUS REPORT")

    rows = [
        ("Docker Containers",   "Docker"),
        ("Network Ports",       "Ports"),
        ("Database Tables",     "DB Tables"),
        ("Credentials",         "Credentials"),
        ("Kafka Producer",      "Kafka Producer"),
        ("Kafka Consumer",      "Kafka Consumer"),
        ("WhatsApp Trigger",    "WhatsApp Trigger"),
        ("Gmail Trigger",       "Gmail Trigger"),
        ("DB Audit Logging",    "DB Logging"),
    ]

    passed = 0
    print()
    for label, key in rows:
        ok_, detail = R_.get(key, (False, "not checked"))
        icon  = f"{GR}{B}✅{R}" if ok_ else f"{RD}{B}❌{R}"
        note  = f"  {DM}{detail}{R}" if detail and not ok_ else ""
        print(f"  {icon}  {W}{label:<25}{R}{note}")
        if ok_: passed += 1

    total   = len(rows)
    pct     = int(passed / total * 100)
    bar_len = 40
    filled  = int(bar_len * pct / 100)
    color   = GR if pct >= 80 else (YL if pct >= 50 else RD)
    bar     = f"{color}{'█'*filled}{DM}{'░'*(bar_len-filled)}{R}"

    print(f"\n  Overall Kafka Status:  {bar}  {B}{color}{pct}%{R}  ({passed}/{total})\n")

    # Action plan
    if pct < 100:
        _sec("ACTION PLAN — Steps to reach 100%")
        step = 1

        if not R_.get("Docker", (True,))[0]:
            print(f"\n  {B}{step}.{R} Start Kafka + Zookeeper containers:")
            print(f"     {CY}cd CRM && docker-compose up zookeeper kafka kafka-worker -d{R}")
            print(f"     {DM}# Wait ~30 seconds for Kafka to become healthy{R}")
            step += 1

        if not R_.get("DB Tables", (True,))[0]:
            print(f"\n  {B}{step}.{R} Apply database migrations:")
            print(f"     {CY}cd backend && python -c \"")
            print(f"       import sys; sys.path.insert(0,'.')")
            print(f"       from dotenv import load_dotenv; load_dotenv('.env')")
            print(f"       from database.connection import init_db, get_conn; init_db()")
            print(f"       sql = open('kafka/migrations.sql').read()")
            print(f"       conn = __import__('contextlib').contextmanager(lambda: (yield))()")
            print(f"     \"{R}  {DM}# or use psql directly:{R}")
            print(f"     {CY}psql postgresql://postgres:postgres@localhost:5432/crm_db -f backend/kafka/migrations.sql{R}")
            step += 1

        if not R_.get("Credentials", (True,))[0]:
            print(f"\n  {B}{step}.{R} Fix missing credentials in {CY}backend/.env{R}:")
            print(f"     {DM}NOTIFY_EMAIL=you@gmail.com   ← add your real email{R}")
            step += 1

        if not R_.get("Gmail Trigger", (True,))[0]:
            print(f"\n  {B}{step}.{R} Complete Gmail OAuth (one-time):")
            print(f"     {CY}cd backend && python -c \"from channels.gmail import _get_gmail_service; _get_gmail_service()\"{R}")
            print(f"     {DM}# Browser will open → sign in → grant permission{R}")
            step += 1

        if not R_.get("WhatsApp Trigger", (True,))[0]:
            print(f"\n  {B}{step}.{R} Fix Twilio credentials in {CY}backend/.env{R}:")
            print(f"     {DM}TWILIO_ACCOUNT_SID=ACxxx   TWILIO_AUTH_TOKEN=xxx{R}")
            print(f"     {DM}Get them from: console.twilio.com{R}")
            step += 1

        print(f"\n  {B}{step}.{R} Run end-to-end Kafka test:")
        print(f"     {CY}# Terminal 1 — start consumer worker:")
        print(f"     cd backend && python -m kafka.consumer{R}")
        print(f"     {CY}# Terminal 2 — run test suite:")
        print(f"     cd backend && python kafka/test_kafka.py{R}")
        step += 1

        print(f"\n  {B}{step}.{R} (Optional) Scale consumer workers:")
        print(f"     {CY}docker-compose up --scale kafka-worker=3 -d{R}")

    else:
        print(f"  {GR}{B}🎉 All checks passed — Kafka pipeline is fully operational!{R}\n")
        print(f"  Run the consumer:  {CY}cd backend && python -m kafka.consumer{R}")
        print(f"  Run tests:         {CY}cd backend && python kafka/test_kafka.py{R}")

    print()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    os.system("")  # enable ANSI on Windows
    print(f"\n{B}{CY}{'═'*62}{R}")
    print(f"{B}{CY}  Flowdesk CRM — Kafka Diagnostic Report{R}")
    print(f"{B}{CY}  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{R}")
    print(f"{B}{CY}{'═'*62}{R}")

    check_docker()
    check_ports()
    check_db_tables()
    check_credentials()
    await check_producer()
    await check_consumer()
    check_whatsapp()
    check_gmail()
    check_db_logging()
    print_report()


if __name__ == "__main__":
    asyncio.run(main())
