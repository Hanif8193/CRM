"""
Flowdesk CRM — Overall Status Chart (Terminal)
Run: python overview.py
"""

import os, sys, io
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

console = Console()


# ── Probes ────────────────────────────────────────────────────────────────────

def env(key):
    v = os.getenv(key, "")
    return bool(v and "your_" not in v and "xxxx" not in v)

def file(rel):
    return Path(__file__).parent.joinpath(rel).exists()

def pkg(name):
    import importlib
    try: importlib.import_module(name); return True
    except ImportError: return False

def db_ok():
    try:
        from database.connection import is_db_available
        return is_db_available()
    except Exception:
        return False


# ── Data ──────────────────────────────────────────────────────────────────────

FEATURES = [
    ("FastAPI Backend",         100),
    ("AI Agent (Claude)",       100),
    ("PostgreSQL DB",           100 if db_ok() else 60),
    ("Gmail Integration",       100 if file("gmail_token.json") else 70),
    ("WhatsApp Meta API",       100 if env("WHATSAPP_API_TOKEN") else 50),
    ("WhatsApp Twilio",         100 if env("TWILIO_ACCOUNT_SID") else 50),
    ("Lead Management",         100),
    ("Flask Lead API",          100),
    ("Streamlit UI",            100),
    ("Docker Support",          100 if file("../Dockerfile") else 80),
    ("Kafka Streaming",          80),
    ("LinkedIn Integration",      0),
]

CHANNELS = [
    ("Web Chat",         True,                        "FastAPI :8000"),
    ("Gmail",            file("gmail_token.json"),    "Google OAuth2"),
    ("WhatsApp Meta",    env("WHATSAPP_API_TOKEN"),   "Meta Cloud API"),
    ("WhatsApp Twilio",  env("TWILIO_ACCOUNT_SID"),   "Twilio Sandbox"),
    ("LinkedIn",         False,                       "Not connected"),
]

CREDS = [
    ("ANTHROPIC_API_KEY",        env("ANTHROPIC_API_KEY"),        "AI Agent"),
    ("TWILIO_ACCOUNT_SID",       env("TWILIO_ACCOUNT_SID"),       "Twilio"),
    ("TWILIO_AUTH_TOKEN",        env("TWILIO_AUTH_TOKEN"),         "Twilio"),
    ("WHATSAPP_API_TOKEN",       env("WHATSAPP_API_TOKEN"),        "Meta WA"),
    ("GMAIL_CLIENT_ID",          env("GMAIL_CLIENT_ID"),           "Gmail OAuth"),
    ("gmail_token.json",         file("gmail_token.json"),         "Gmail session"),
]

PACKAGES = [
    ("fastapi","FastAPI"), ("uvicorn","Server"), ("anthropic","Claude AI"),
    ("twilio","Twilio"),   ("flask","Flask"),    ("streamlit","UI"),
    ("google.auth","Gmail"),("dotenv","Env"),    ("httpx","HTTP"),
    ("aiokafka","Kafka"),  ("requests","HTTP2"), ("sqlalchemy","ORM"),
]


# ── Bar ───────────────────────────────────────────────────────────────────────

def pbar(pct: int, width: int = 20) -> Text:
    filled = int(width * pct / 100)
    empty  = width - filled
    color  = "green" if pct == 100 else ("yellow" if pct >= 50 else "red")
    t = Text()
    t.append("█" * filled, style=color)
    t.append("░" * empty,  style="bright_black")
    t.append(f" {pct:>3}%",style=f"bold {color}")
    return t


# ── Tables ────────────────────────────────────────────────────────────────────

def feature_table():
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
              title="[bold white]Feature Completion[/]", title_justify="left",
              border_style="bright_black")
    t.add_column("#",        style="dim",        width=3)
    t.add_column("Feature",  style="white",      width=26)
    t.add_column("Progress", width=28)

    for i, (name, pct) in enumerate(FEATURES, 1):
        t.add_row(str(i), name, pbar(pct))
    return t


def channel_table():
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
              title="[bold white]Channel Status[/]", title_justify="left",
              border_style="bright_black")
    t.add_column("Channel",  style="white",  width=20)
    t.add_column("Status",   width=12)
    t.add_column("Provider", style="dim",    width=18)

    for name, ok, provider in CHANNELS:
        status = Text("● ACTIVE",  style="bold green") if ok else Text("● OFFLINE", style="bold red")
        t.add_row(name, status, provider)
    return t


def creds_table():
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
              title="[bold white]Credentials[/]", title_justify="left",
              border_style="bright_black")
    t.add_column("Key / File",  style="white", width=28)
    t.add_column("State",       width=10)
    t.add_column("Used for",    style="dim",   width=14)

    for key, ok, label in CREDS:
        state = Text("✓ Set",    style="bold green") if ok else Text("✗ Missing", style="bold red")
        t.add_row(key, state, label)
    return t


def packages_table():
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
              title="[bold white]Dependencies[/]", title_justify="left",
              border_style="bright_black")
    t.add_column("Package",  style="white", width=14)
    t.add_column("",         width=6)
    t.add_column("Role",     style="dim",   width=12)

    for name, role in PACKAGES:
        ok    = pkg(name)
        state = Text("✓", style="bold green") if ok else Text("✗", style="bold red")
        t.add_row(name, state, role)
    return t


def summary_panel():
    total   = len(FEATURES)
    done    = sum(1 for _, p in FEATURES if p == 100)
    partial = sum(1 for _, p in FEATURES if 0 < p < 100)
    pend    = sum(1 for _, p in FEATURES if p == 0)
    overall = int(sum(p for _, p in FEATURES) / total)

    ch_active = sum(1 for _, ok, _ in CHANNELS if ok)

    creds_ok  = sum(1 for _, ok, _ in CREDS if ok)
    pkgs_ok   = sum(1 for n, _ in PACKAGES if pkg(n))

    t = Text(justify="center")
    t.append("\n")
    t.append(f"  {'Overall Progress':20}", style="dim")
    t.append_text(pbar(overall, 24))
    t.append("\n\n")
    t.append(f"  Features    ", style="dim")
    t.append(f"{done}✓ ", style="bold green")
    t.append(f"{partial}~ ", style="bold yellow")
    t.append(f"{pend}✗",   style="bold red")
    t.append(f"       Channels  ", style="dim")
    t.append(f"{ch_active}/{len(CHANNELS)} active", style="bold green")
    t.append("\n")
    t.append(f"  Credentials ", style="dim")
    t.append(f"{creds_ok}/{len(CREDS)} set", style="bold green" if creds_ok == len(CREDS) else "bold yellow")
    t.append(f"       Packages  ", style="dim")
    t.append(f"{pkgs_ok}/{len(PACKAGES)} installed", style="bold green" if pkgs_ok == len(PACKAGES) else "bold yellow")
    t.append("\n")

    return Panel(t,
                 title=f"[bold white]Flowdesk CRM · {datetime.now().strftime('%Y-%m-%d %H:%M')}[/]",
                 border_style="blue", padding=(0, 1))


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(summary_panel())
    console.print()
    console.print(Columns([feature_table(), channel_table()], equal=False, expand=False))
    console.print()
    console.print(Columns([creds_table(), packages_table()], equal=False, expand=False))
    console.print()
    console.print("[dim]  Run again: [white]python overview.py[/][/]")
    console.print()
