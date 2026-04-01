"""
Flowdesk CRM — Terminal Status Dashboard
Run: python status.py
"""

import os
import sys
import io
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows so box-drawing chars render correctly
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── ANSI colours ──────────────────────────────────────────────────────────────
R  = "\033[0m"       # reset
B  = "\033[1m"       # bold
CY = "\033[96m"      # cyan
GR = "\033[92m"      # green
YL = "\033[93m"      # yellow
RD = "\033[91m"      # red
BL = "\033[94m"      # blue
MG = "\033[95m"      # magenta
DM = "\033[2m"       # dim
W  = "\033[97m"      # white

BAR_WIDTH = 30       # characters wide for progress bars

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Helpers ───────────────────────────────────────────────────────────────────

def bar(pct: int) -> str:
    filled = int(BAR_WIDTH * pct / 100)
    empty  = BAR_WIDTH - filled
    if pct == 100:
        color = GR
    elif pct >= 50:
        color = YL
    else:
        color = RD
    return f"{color}{'█' * filled}{DM}{'░' * empty}{R}"


def badge(text: str, color: str) -> str:
    return f"{color}{B}[{text}]{R}"


def ok()      : return f"{GR}{B} ✓ {R}"
def warn()    : return f"{YL}{B} ~ {R}"
def fail()    : return f"{RD}{B} ✗ {R}"
def pending() : return f"{YL}{B} ? {R}"


def divider(char="─", width=72):
    print(f"{DM}{char * width}{R}")


def header(title: str):
    divider("═")
    pad = (70 - len(title)) // 2
    print(f"{BL}{B}{'═' * pad}  {W}{title}{BL}  {'═' * pad}{R}")
    divider("═")


def section(title: str):
    print()
    print(f"  {CY}{B}▶  {title}{R}")
    divider()


# ── Probe functions ───────────────────────────────────────────────────────────

def check_env(key: str) -> bool:
    """Return True if env var is set and non-empty."""
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")
    val = os.getenv(key, "")
    return bool(val and val not in ("your_anthropic_api_key", "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                                     "your_twilio_auth_token", "your_whatsapp_token",
                                     "your_gmail_client_id"))


def check_file(rel: str) -> bool:
    return Path(__file__).parent.joinpath(rel).exists()


def check_import(module: str) -> bool:
    import importlib
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def check_db() -> bool:
    try:
        from database.connection import is_db_available
        return is_db_available()
    except Exception:
        return False


# ── Sections ──────────────────────────────────────────────────────────────────

def show_features():
    section("FEATURE COMPLETION")

    features = [
        ("FastAPI Backend",          100),
        ("AI Agent  (Claude)",       100),
        ("PostgreSQL Database",       check_db() and 100 or 60),
        ("Gmail Integration",        100 if check_file("gmail_token.json") else 70),
        ("WhatsApp — Meta API",      100 if check_env("WHATSAPP_API_TOKEN") else 50),
        ("WhatsApp — Twilio",        100 if check_env("TWILIO_ACCOUNT_SID") else 50),
        ("Lead Management Service",  100),
        ("Flask Lead API",           100),
        ("Streamlit UI",             100),
        ("Docker Support",           100 if check_file("../Dockerfile") else 80),
        ("Kafka Streaming",           80),
        ("LinkedIn Integration",       0),
    ]

    total   = len(features)
    done    = sum(1 for _, p in features if p == 100)
    partial = sum(1 for _, p in features if 0 < p < 100)
    pending_count = sum(1 for _, p in features if p == 0)

    for name, pct in features:
        icon = ok() if pct == 100 else (warn() if pct > 0 else fail())
        label = f"{name:<30}"
        print(f"  {icon} {W}{label}{R}  {bar(pct)}  {B}{pct:>3}%{R}")

    print()
    overall = int(sum(p for _, p in features) / total)
    print(f"  {'Overall':>33}   {bar(overall)}  {B}{CY}{overall:>3}%{R}")
    print()
    print(f"  {GR}{B}{done} complete{R}  {YL}{B}{partial} in-progress{R}  {RD}{B}{pending_count} pending{R}")


def show_channels():
    section("CHANNEL STATUS")

    channels = [
        ("Web Chat",           True,  "FastAPI REST + WebSocket"),
        ("Gmail",              check_file("gmail_token.json"), "Google OAuth2 + Gmail API"),
        ("WhatsApp (Meta)",    check_env("WHATSAPP_API_TOKEN"), "Meta Cloud API v19"),
        ("WhatsApp (Twilio)",  check_env("TWILIO_ACCOUNT_SID"), "Twilio Sandbox REST API"),
        ("LinkedIn",           False, "Not connected yet"),
    ]

    for name, active, provider in channels:
        icon   = ok() if active else fail()
        status = badge("ACTIVE",  GR) if active else badge("OFFLINE", RD)
        print(f"  {icon} {W}{name:<22}{R}  {status}  {DM}{provider}{R}")


def show_credentials():
    section("CREDENTIALS / ENV VARS")

    creds = [
        ("ANTHROPIC_API_KEY",           "AI Agent"),
        ("TWILIO_ACCOUNT_SID",          "Twilio WhatsApp"),
        ("TWILIO_AUTH_TOKEN",           "Twilio WhatsApp"),
        ("WHATSAPP_API_TOKEN",          "Meta WhatsApp"),
        ("WHATSAPP_PHONE_NUMBER_ID",    "Meta WhatsApp"),
        ("GMAIL_CLIENT_ID",             "Gmail OAuth2"),
    ]

    for key, label in creds:
        found = check_env(key)
        icon  = ok() if found else fail()
        status = f"{GR}Set{R}" if found else f"{RD}Missing{R}"
        print(f"  {icon} {W}{key:<35}{R}  {status}  {DM}({label}){R}")

    token_ok = check_file("gmail_token.json")
    icon = ok() if token_ok else warn()
    status = f"{GR}Found{R}" if token_ok else f"{YL}Run OAuth setup{R}"
    print(f"  {icon} {W}{'gmail_token.json':<35}{R}  {status}  {DM}(Gmail session){R}")


def show_endpoints():
    section("API ENDPOINTS")

    endpoints = [
        ("POST",  "/chat",                        "FastAPI :8000", GR),
        ("GET",   "/webhook/whatsapp",             "FastAPI :8000", BL),
        ("POST",  "/webhook/whatsapp",             "FastAPI :8000", GR),
        ("POST",  "/webhook/gmail",                "FastAPI :8000", GR),
        ("GET",   "/health",                       "FastAPI :8000", BL),
        ("GET",   "/metrics",                      "FastAPI :8000", BL),
        ("GET",   "/api/admin/tickets",            "FastAPI :8000", BL),
        ("PATCH", "/api/admin/tickets/{id}/close", "FastAPI :8000", YL),
        ("POST",  "/add-lead",                     "Flask   :5050", GR),
        ("GET",   "/leads",                        "Flask   :5050", BL),
    ]

    method_color = {"GET": BL, "POST": GR, "PATCH": YL, "DELETE": RD}
    for method, path, server, _ in endpoints:
        mc = method_color.get(method, W)
        print(f"  {DM}│{R}  {mc}{B}{method:<6}{R}  {W}{path:<42}{R}  {DM}{server}{R}")


def show_modules():
    section("MODULES & FILES")

    modules = [
        ("backend/main.py",                      check_file("main.py")),
        ("backend/config.py",                    check_file("config.py")),
        ("channels/gmail.py",                    check_file("channels/gmail.py")),
        ("channels/whatsapp.py",                 check_file("channels/whatsapp.py")),
        ("channels/whatsapp_twilio.py",          check_file("channels/whatsapp_twilio.py")),
        ("channels/web.py",                      check_file("channels/web.py")),
        ("services/lead_service.py",             check_file("services/lead_service.py")),
        ("api/routes.py",                        check_file("api/routes.py")),
        ("api/admin_routes.py",                  check_file("api/admin_routes.py")),
        ("api/lead_app.py",                      check_file("api/lead_app.py")),
        ("ui/streamlit_app.py",                  check_file("ui/streamlit_app.py")),
        ("send_status_report.py",                check_file("send_status_report.py")),
        ("docker-compose.yml",                   check_file("../docker-compose.yml")),
    ]

    col = 2
    rows = [modules[i:i+col] for i in range(0, len(modules), col)]
    for row in rows:
        line = ""
        for path, exists in row:
            icon = f"{GR}✓{R}" if exists else f"{RD}✗{R}"
            line += f"  {icon} {W}{path:<40}{R}"
        print(line)


def show_dependencies():
    section("PYTHON DEPENDENCIES")

    deps = [
        ("fastapi",        "FastAPI framework"),
        ("uvicorn",        "ASGI server"),
        ("sqlalchemy",     "ORM / database"),
        ("anthropic",      "Claude AI SDK"),
        ("twilio",         "Twilio WhatsApp"),
        ("flask",          "Lead API"),
        ("streamlit",      "CRM UI"),
        ("google.auth",    "Gmail OAuth2"),
        ("dotenv",         "Env var loader"),
        ("httpx",          "HTTP client"),
        ("aiokafka",       "Kafka async"),
        ("requests",       "HTTP (Streamlit)"),
    ]

    col = 2
    rows = [deps[i:i+col] for i in range(0, len(deps), col)]
    for row in rows:
        line = ""
        for pkg, label in row:
            found = check_import(pkg)
            icon  = f"{GR}✓{R}" if found else f"{RD}✗ pip install {pkg}{R}"
            line += f"  {icon} {W}{pkg:<16}{R}{DM}{label:<28}{R}"
        print(line)


def show_summary():
    section("QUICK START COMMANDS")
    cmds = [
        ("FastAPI backend",   "uvicorn main:app --reload --port 8000"),
        ("Flask Lead API",    "python api/lead_app.py"),
        ("Streamlit UI",      "streamlit run ui/streamlit_app.py"),
        ("Email status",      "python send_status_report.py you@email.com"),
        ("Twilio debug",      "python twilio_debug.py"),
    ]
    for label, cmd in cmds:
        print(f"  {BL}${R}  {DM}{label:<22}{R}  {W}{cmd}{R}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.system("")   # enable ANSI on Windows cmd/PowerShell

    header(f"FLOWDESK CRM  ·  STATUS DASHBOARD  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    show_features()
    show_channels()
    show_credentials()
    show_endpoints()
    show_modules()
    show_dependencies()
    show_summary()

    print()
    divider("═")
    print(f"  {DM}Run again anytime:  {W}python status.py{R}")
    divider("═")
    print()
