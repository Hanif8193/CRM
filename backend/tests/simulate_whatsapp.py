"""
WhatsApp messaging simulator.

Simulates a customer sending short WhatsApp-style messages to
POST /api/message (channel="whatsapp") and prints the conversation
in a chat-like format.

Usage:
    python tests/simulate_whatsapp.py
    python tests/simulate_whatsapp.py --url http://localhost:8000
"""

import json
import time
import argparse
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_URL  = "http://localhost:8000/api/message"
MSG_DELAY    = 0.4   # seconds between messages in a thread (feels realistic)

# ── Core function ─────────────────────────────────────────────────────────────

def simulate_whatsapp(customer_id: str, message: str, api_url: str = DEFAULT_URL) -> dict:
    """
    Send a single WhatsApp-style message to the agent and return the response dict.
    Raises urllib.error.URLError when the server is unreachable.
    """
    payload = json.dumps({
        "customer_id": customer_id,
        "channel":     "whatsapp",
        "message":     message,
    }).encode()

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


# ── Pretty printer ────────────────────────────────────────────────────────────

_GREEN  = "\033[32m"
_BLUE   = "\033[34m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"

def _print_header(label: str, customer_id: str, api_url: str) -> None:
    print(f"\n{'─' * 56}")
    print(f"  {_BOLD}{label}{_RESET}")
    print(f"  +{customer_id}")
    print(f"{'─' * 56}")


def _print_user(message: str) -> None:
    print(f"\n  {_GREEN}You :{_RESET} {message}")


def _print_ai(response: str, escalated: bool, source: str) -> None:
    # WhatsApp responses should already be short — print as-is
    lines = response.strip().splitlines()
    prefix = f"  {_BLUE}AI  :{_RESET} "
    indent = "        "
    for i, line in enumerate(lines):
        print(f"{prefix if i == 0 else indent}{line}")

    tag = ""
    if escalated:
        tag = f"  {_YELLOW}[escalated → human agent]{_RESET}"
    elif source == "docs":
        tag = f"  {_BLUE}[answered from docs]{_RESET}"
    if tag:
        print(tag)


def _print_error(msg: str) -> None:
    print(f"\n  {_RED}[ERROR]{_RESET} {msg}")


# ── Thread runner ─────────────────────────────────────────────────────────────

def run_thread(label: str, customer_id: str, messages: list[str], api_url: str) -> bool:
    """
    Send a sequence of messages as one customer and print the conversation.
    Returns True if all messages succeeded.
    """
    _print_header(label, customer_id, api_url)
    ok = True

    for msg in messages:
        _print_user(msg)
        try:
            result = simulate_whatsapp(customer_id, msg, api_url)
            _print_ai(
                response  = result.get("response", ""),
                escalated = result.get("escalated", False),
                source    = result.get("source", ""),
            )
        except urllib.error.URLError as exc:
            _print_error(f"Cannot reach API: {exc.reason}")
            _print_error("Is the backend running?  uvicorn main:app --reload")
            ok = False
            break
        except Exception as exc:
            _print_error(str(exc))
            ok = False

        time.sleep(MSG_DELAY)

    return ok


# ── Scenarios ─────────────────────────────────────────────────────────────────

def run_simulation(api_url: str = DEFAULT_URL) -> None:
    print(f"\n{'=' * 56}")
    print(f"  {_BOLD}FLOWDESK — WhatsApp Simulator{_RESET}")
    print(f"  API: {api_url}")
    print(f"{'=' * 56}")

    threads = [
        {
            "label":       "THREAD 1 — Short question + follow-up (memory test)",
            "customer_id": "+447911123456",
            "messages": [
                "hi, how do i reset my password?",
                "ok done, but now it's asking for a 2FA code",
                "i don't have the app anymore",
            ],
        },
        {
            "label":       "THREAD 2 — Angry complaint → escalation",
            "customer_id": "+1-312-555-0184",
            "messages": [
                "your app is broken again, data is missing",
                "this is the third time this week, completely unacceptable",
            ],
        },
        {
            "label":       "THREAD 3 — Pricing question",
            "customer_id": "+34 612 345 678",
            "messages": [
                "what's the price for 20 users?",
            ],
        },
        {
            "label":       "THREAD 4 — Acknowledgment detection",
            "customer_id": "+447911123456",   # same user as thread 1 — memory persists
            "messages": [
                "thanks!",
                "actually one more thing — can I use flowdesk on mobile?",
            ],
        },
    ]

    passed = 0
    failed = 0

    for thread in threads:
        success = run_thread(
            label       = thread["label"],
            customer_id = thread["customer_id"],
            messages    = thread["messages"],
            api_url     = api_url,
        )
        if success:
            passed += 1
        else:
            failed += 1

    print(f"\n{'─' * 56}")
    print(f"  Done — {passed} threads passed, {failed} failed")
    print(f"{'─' * 56}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flowdesk WhatsApp simulator")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Base API URL (default: {DEFAULT_URL})",
    )
    args = parser.parse_args()
    run_simulation(api_url=args.url)
