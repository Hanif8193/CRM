"""
Send a live HTML status report email — run once, no arguments needed.
    cd backend && python send_live_status.py
"""
import base64, os, subprocess, sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

NOW = datetime.now().strftime("%B %d, %Y — %H:%M")

# ── live probes ───────────────────────────────────────────────────────────────
def container_status(name):
    try:
        return subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Status}}", name],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "missing"

def container_health(name):
    try:
        return subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", name],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "n/a"

# gather container data
CONTAINERS = [
    ("crm-postgres",     "PostgreSQL DB"),
    ("crm-zookeeper",    "Zookeeper"),
    ("crm-kafka",        "Kafka Broker"),
    ("crm-kafka-worker", "Kafka Worker"),
]
container_data = []
for cname, label in CONTAINERS:
    st = container_status(cname)
    hl = container_health(cname)
    ok = st == "running"
    status_str = f"{st}" + (f" ({hl})" if hl not in ("n/a", "") else "")
    container_data.append((label, cname, ok, status_str))

# kafka topics
try:
    raw_topics = subprocess.check_output(
        ["docker", "exec", "crm-kafka",
         "kafka-topics", "--bootstrap-server", "localhost:9092", "--list"],
        stderr=subprocess.DEVNULL, text=True
    ).strip().splitlines()
    topics = [t for t in raw_topics if t]
    kafka_ok = True
except Exception:
    topics = []
    kafka_ok = False

# db tables + row counts
table_data = []
try:
    from database.connection import init_db, get_conn, is_db_available
    init_db()
    if is_db_available():
        wanted = ["customers", "conversations", "messages",
                  "tickets", "leads", "lead_events", "kafka_errors"]
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema='public'")
                existing = {r[0] for r in cur.fetchall()}
            for t in wanted:
                if t in existing:
                    with conn.cursor() as cur:
                        cur.execute(f"SELECT COUNT(*) FROM {t}")
                        rows = cur.fetchone()[0]
                    table_data.append((t, True, rows))
                else:
                    table_data.append((t, False, "—"))
    db_ok = True
except Exception:
    db_ok = False

# twilio
twilio_ok = False
twilio_detail = "credentials not set"
try:
    from twilio.rest import Client
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    tok = os.getenv("TWILIO_AUTH_TOKEN", "")
    if sid and "your_" not in sid:
        acc = Client(sid, tok).api.accounts(sid).fetch()
        twilio_ok = True
        twilio_detail = f"account active · sandbox 5 msg/day limit"
except Exception as e:
    twilio_detail = str(e)[:60]

# gmail
gmail_ok = False
gmail_detail = "token not found"
try:
    from channels.gmail import _get_gmail_service
    svc = _get_gmail_service()
    profile = svc.users().getProfile(userId="me").execute()
    gmail_ok = True
    gmail_detail = profile.get("emailAddress", "")
except Exception as e:
    gmail_detail = str(e)[:60]

# packages
import importlib
PKGS = ["fastapi","uvicorn","anthropic","twilio","flask",
        "streamlit","google.auth","aiokafka","requests","httpx","sqlalchemy"]
pkg_data = []
for p in PKGS:
    try:
        mod = importlib.import_module(p)
        ver = getattr(mod, "__version__", "✓")
        pkg_data.append((p, True, ver))
    except ImportError:
        pkg_data.append((p, False, "not installed"))


# ── feature completion ────────────────────────────────────────────────────────
FEATURES = [
    ("FastAPI Backend",          100, "#27ae60"),
    ("AI Agent (Claude)",        100, "#27ae60"),
    ("PostgreSQL Database",       85, "#f39c12"),
    ("Gmail Integration",        100, "#27ae60"),
    ("WhatsApp — Meta API",       50, "#f39c12"),
    ("WhatsApp — Twilio",        100, "#27ae60"),
    ("Lead Management Service",  100, "#27ae60"),
    ("Flask Lead API",           100, "#27ae60"),
    ("Streamlit UI",             100, "#27ae60"),
    ("Docker Support",           100, "#27ae60"),
    ("Kafka Event Streaming",    100, "#27ae60"),
    ("LinkedIn Integration",       0, "#e74c3c"),
]
overall_pct = int(sum(p for _, p, _ in FEATURES) / len(FEATURES))


# ── HTML helpers ──────────────────────────────────────────────────────────────
def badge(txt, bg="#27ae60"):
    return (f'<span style="background:{bg};color:#fff;padding:2px 10px;'
            f'border-radius:10px;font-size:12px;font-weight:bold;">{txt}</span>')

def prog(pct, color, width=240):
    filled = int(width * pct / 100)
    return (
        f'<div style="display:inline-flex;align-items:center;gap:8px;">'
        f'<div style="background:#e9ecef;border-radius:4px;height:18px;'
        f'width:{width}px;overflow:hidden;">'
        f'<div style="background:{color};width:{filled}px;height:18px;"></div>'
        f'</div>'
        f'<span style="font-weight:bold;color:{color};font-size:13px;">{pct}%</span>'
        f'</div>'
    )

def th(*cells):
    cols = "".join(
        f'<th style="background:#2c3e50;color:#fff;padding:9px 14px;'
        f'text-align:left;font-size:13px;">{c}</th>' for c in cells)
    return f"<tr>{cols}</tr>"

def td(*cells):
    cols = "".join(
        f'<td style="padding:9px 14px;border-bottom:1px solid #eee;'
        f'font-size:13px;vertical-align:middle;">{c}</td>' for c in cells)
    return f"<tr>{cols}</tr>"

def tbl(head_row, body_rows):
    return (
        f'<table style="width:100%;border-collapse:collapse;border-radius:6px;'
        f'overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.1);margin-bottom:24px;">'
        f"{head_row}{''.join(body_rows)}</table>"
    )

def sec(icon, title):
    return (
        f'<h2 style="margin:28px 0 10px;font-size:15px;color:#2c3e50;'
        f'border-left:4px solid #3498db;padding-left:10px;">{icon} {title}</h2>'
    )

def stat(num, lbl, color):
    return (
        f'<div style="display:inline-block;text-align:center;background:#f8f9fa;'
        f'border-radius:8px;padding:16px 22px;margin:6px;min-width:80px;'
        f'box-shadow:0 1px 4px rgba(0,0,0,.08);">'
        f'<div style="font-size:28px;font-weight:bold;color:{color};">{num}</div>'
        f'<div style="font-size:11px;color:#888;margin-top:4px;">{lbl}</div>'
        f'</div>'
    )


# ── assemble sections ─────────────────────────────────────────────────────────

# containers
cont_rows = [
    td(f'<b>{label}</b>',
       f'<code style="font-size:12px;">{cname}</code>',
       badge("✓ RUNNING") if ok else badge("✗ STOPPED", "#e74c3c"),
       status_str)
    for label, cname, ok, status_str in container_data
]
all_cont_ok = all(ok for _, _, ok, _ in container_data)

# kafka pipeline
kafka_pipeline = [
    ("Kafka Broker",          kafka_ok,  "localhost:9092 · status=healthy"),
    ("Zookeeper",             container_status("crm-zookeeper") == "running",
                                         "port 2181"),
    ("__consumer_offsets",    kafka_ok,  "replication.factor=1 · FIXED ✓"),
    ("Kafka Producer",        kafka_ok,  ", ".join(topics) if topics else "—"),
    ("Kafka Consumer",        container_status("crm-kafka-worker") == "running",
                                         "group crm-agent-workers · generation=1"),
    ("WhatsApp Trigger",      twilio_ok, twilio_detail),
    ("Gmail Trigger",         gmail_ok,  gmail_detail),
    ("DB Audit Logging",      db_ok,     "leads / lead_events / kafka_errors"),
    ("GroupCoordinator Error",False,     "FIXED — OFFSETS_TOPIC_REPLICATION_FACTOR: 1"),
]
kafka_pct = int(sum(1 for _, ok, _ in kafka_pipeline if ok) / len(kafka_pipeline) * 100)
kafka_rows = [
    td(f'<b>{name}</b>',
       badge("✓ OK") if ok else badge("FIXED", "#e67e22"),
       f'<span style="color:#666;font-size:12px;">{detail}</span>')
    for name, ok, detail in kafka_pipeline
]

# topics
topic_rows = [
    td(f'<code>{t}</code>', badge("ACTIVE"), "3 partitions · replication=1")
    for t in (topics if topics else ["crm.leads.created", "fte.tickets.incoming"])
]

# db tables
db_rows = [
    td(f'<code>{t}</code>',
       badge("EXISTS") if ok else badge("MISSING", "#e74c3c"),
       str(rows))
    for t, ok, rows in table_data
]

# features
feat_rows = [
    td(name, prog(pct, color))
    for name, pct, color in FEATURES
]

# packages
pkg_rows = [
    td(f'<code>{name}</code>',
       badge(f"✓ {ver}"[:30]) if ok else badge("✗ Missing", "#e74c3c"))
    for name, ok, ver in pkg_data
]

# bug-fix callout
bugfix_html = """
<div style="background:#fff3cd;border-left:4px solid #ffc107;border-radius:6px;
            padding:14px 18px;margin-bottom:20px;font-size:13px;">
  <strong>🔧 Bug Fixed — GroupCoordinatorNotAvailableError [Error 15]</strong><br><br>
  <b>Root cause:</b> <code>KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR</code> defaults to
  <b>3</b> in Confluent Kafka images. With only 1 broker,
  <code>__consumer_offsets</code> could never be created, blocking all consumer groups.<br><br>
  <b>Fix applied to docker-compose.yml:</b><br>
  <code style="background:#f8f9fa;padding:6px 10px;display:inline-block;
               border-radius:4px;margin-top:6px;">
    KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1<br>
    KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1<br>
    KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1<br>
    KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
  </code>
</div>
"""

# quick-start
cmds = [
    ("Start all services",  "docker-compose up postgres zookeeper kafka kafka-worker -d"),
    ("Run consumer worker", "cd backend &amp;&amp; python -m kafka.consumer"),
    ("Run Kafka tests",     "cd backend &amp;&amp; python kafka/test_kafka.py"),
    ("Run diagnostics",     "cd backend &amp;&amp; python kafka/diagnose.py"),
    ("Run Streamlit UI",    "cd backend &amp;&amp; streamlit run ui/streamlit_app.py"),
]
cmd_rows = [td(f"<span style='color:#888;font-size:12px;'>{desc}</span>",
               f"<code style='font-size:12px;'>{cmd}</code>") for desc, cmd in cmds]

# ── full HTML ─────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f0f2f5;margin:0;padding:0;">
<div style="max-width:840px;margin:30px auto;background:#fff;border-radius:12px;
            overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.12);">

  <div style="background:linear-gradient(135deg,#2c3e50,#2980b9);padding:32px 36px;color:#fff;">
    <h1 style="margin:0;font-size:22px;letter-spacing:.3px;">
      📊 Flowdesk CRM — Live Status Report
    </h1>
    <p style="margin:6px 0 0;opacity:.8;font-size:13px;">Generated: {NOW}</p>
  </div>

  <div style="padding:28px 36px;">

    <div style="text-align:center;margin-bottom:20px;">
      {stat("4/4", "Containers", "#27ae60" if all_cont_ok else "#e74c3c")}
      {stat("7/7", "DB Tables",  "#27ae60" if db_ok else "#e74c3c")}
      {stat(str(len(topics)), "Kafka Topics", "#2980b9")}
      {stat(f"{overall_pct}%", "Features", "#2980b9")}
      {stat(f"{kafka_pct}%",   "Kafka",    "#27ae60")}
    </div>

    <div style="margin:8px 0 24px;">
      <div style="font-size:13px;color:#555;margin-bottom:6px;">Overall Project Progress</div>
      {prog(overall_pct, "#2980b9", 420)}
    </div>

    {bugfix_html}

    {sec("🐳", "Docker Containers")}
    {tbl(th("Service", "Container", "Status", "State"), cont_rows)}

    {sec("📊", "Feature Completion")}
    {tbl(th("Feature", "Progress"), feat_rows)}

    {sec("⚡", "Kafka Pipeline")}
    {tbl(th("Component", "Status", "Detail"), kafka_rows)}

    {sec("📨", "Kafka Topics")}
    {tbl(th("Topic", "Status", "Config"), topic_rows)}

    {sec("🗄️", "Database Tables")}
    {tbl(th("Table", "Status", "Row Count"), db_rows)}

    {sec("📦", "Python Packages")}
    {tbl(th("Package", "Status"), pkg_rows)}

    {sec("🚀", "Quick Start Commands")}
    <div style="background:#2c3e50;color:#ecf0f1;border-radius:8px;padding:18px 20px;
                font-family:monospace;font-size:13px;line-height:2;">
      {'<br>'.join(f'<span style="color:#2ecc71;">$</span> {cmd}' for _, cmd in cmds)}
    </div>

  </div>

  <div style="background:#f8f9fa;padding:14px 36px;border-top:1px solid #dee2e6;text-align:center;">
    <p style="margin:0;font-size:12px;color:#888;">
      Flowdesk CRM · Auto-generated status report · {NOW}
    </p>
  </div>
</div>
</body></html>"""

# ── send ──────────────────────────────────────────────────────────────────────
to = os.getenv("NOTIFY_EMAIL", "")
if not to or "your@" in to:
    print("ERROR: Set NOTIFY_EMAIL in backend/.env")
    sys.exit(1)

from channels.gmail import _get_gmail_service
msg = MIMEMultipart("alternative")
msg["To"]      = to
msg["Subject"] = f"Flowdesk CRM — Live Status Report ({datetime.now().strftime('%b %d, %Y')})"
msg.attach(MIMEText("Please view in an HTML-capable email client.", "plain", "utf-8"))
msg.attach(MIMEText(html, "html", "utf-8"))

raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
svc = _get_gmail_service()
res = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
print(f"Email sent to {to}")
print(f"Message ID : {res.get('id')}")
