"""
Gmail integration simulator.

Simulates inbound customer emails by formatting messages as email text
and posting them to POST /api/message (channel="email").

Usage:
    python tests/simulate_gmail.py
    python tests/simulate_gmail.py --url http://localhost:8000
"""

import io
import sys
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_URL = "http://localhost:8000/api/message"

# ── Core function ─────────────────────────────────────────────────────────────

def simulate_email(customer_id: str, subject: str, body: str, api_url: str = DEFAULT_URL) -> dict:
    """
    Format a plain text body as an email and POST it to /api/message.

    Returns the parsed response dict from the agent.
    Raises urllib.error.URLError when the server is unreachable.
    """
    timestamp = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    # Compose a realistic email-style message string
    email_text = (
        f"From: {customer_id}\n"
        f"Subject: {subject}\n"
        f"Date: {timestamp}\n"
        f"\n"
        f"{body.strip()}"
    )

    payload = json.dumps({
        "customer_id": customer_id,
        "channel":     "email",
        "message":     email_text,
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

_DIVIDER = "─" * 60

def _print_email(label: str, customer_id: str, subject: str, body: str) -> None:
    print(f"\n{_DIVIDER}")
    print(f"  {label}")
    print(_DIVIDER)
    print(f"  From   : {customer_id}")
    print(f"  Subject: {subject}")
    print(f"  Body   : {body.strip()[:120]}{'...' if len(body) > 120 else ''}")


def _print_response(result: dict) -> None:
    escalated = result.get("escalated", False)
    source    = result.get("source", "?")
    intent    = result.get("intent", "?")
    response  = result.get("response", "")

    status_icon = "[ESCALATED]" if escalated else "[RESOLVED] "
    print(f"\n  {status_icon}  intent={intent}  source={source}")
    print()
    # Wrap long response lines for readability
    for line in response.splitlines():
        print(f"    {line}")


def run_simulation(api_url: str = DEFAULT_URL) -> None:
    """Run all test email scenarios."""

    # ── Test cases ────────────────────────────────────────────────────────────
    emails = [
        {
            "label":       "TEST 1 — Password reset request",
            "customer_id": "alice@techcorp.com",
            "subject":     "Can't log in — password reset not working",
            "body": (
                "Hi Flowdesk support,\n\n"
                "I've been trying to reset my password for the past hour and the "
                "reset email never arrives. I've checked my spam folder and there's "
                "nothing there either.\n\n"
                "Could you please help me get back into my account?\n\n"
                "Thanks,\nAlice"
            ),
        },
        {
            "label":       "TEST 2 — Angry complaint",
            "customer_id": "marcus.b@retailco.io",
            "subject":     "Completely unacceptable — data missing after update",
            "body": (
                "This is absolutely ridiculous. After your latest update yesterday, "
                "three months of our customer contact data has disappeared from the "
                "dashboard. We run a business with this software and I cannot believe "
                "how irresponsible this is.\n\n"
                "I demand an explanation and a fix immediately. If this isn't resolved "
                "today I will be disputing our subscription charge with my bank.\n\n"
                "— Marcus"
            ),
        },
        {
            "label":       "TEST 3 — Pricing question",
            "customer_id": "priya.k@startupxyz.com",
            "subject":     "Pricing for our growing team",
            "body": (
                "Hello,\n\n"
                "We're currently on the Starter plan with 8 users and we're about to "
                "hire 5 more people. I'd like to understand what the cost difference "
                "would be if we move up to the Growth plan, and whether there are any "
                "annual billing discounts available.\n\n"
                "Happy to schedule a call if that's easier.\n\n"
                "Best,\nPriya"
            ),
        },
    ]

    print("\n" + "=" * 60)
    print("  FLOWDESK — Gmail Integration Simulator")
    print(f"  API: {api_url}")
    print("=" * 60)

    passed = 0
    failed = 0

    for email in emails:
        _print_email(
            label       = email["label"],
            customer_id = email["customer_id"],
            subject     = email["subject"],
            body        = email["body"],
        )

        try:
            result = simulate_email(
                customer_id = email["customer_id"],
                subject     = email["subject"],
                body        = email["body"],
                api_url     = api_url,
            )
            _print_response(result)
            passed += 1
        except urllib.error.URLError as exc:
            print(f"\n  [ERROR] Could not reach API: {exc.reason}")
            print("          Is the backend running?  uvicorn main:app --reload")
            failed += 1
        except Exception as exc:
            print(f"\n  [ERROR] Unexpected error: {exc}")
            failed += 1

    print(f"\n{_DIVIDER}")
    print(f"  Done — {passed} passed, {failed} failed")
    print(_DIVIDER + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flowdesk Gmail simulator")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"API endpoint (default: {DEFAULT_URL})",
    )
    args = parser.parse_args()
    run_simulation(api_url=args.url)
