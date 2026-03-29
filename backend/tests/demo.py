"""
Flowdesk CRM AI — Live Demo Script

A narrated, step-by-step walkthrough designed for presentations.
Each step pauses so the presenter can talk before moving on.

Usage:
    # backend must be running:
    #   uvicorn main:app --reload

    python tests/demo.py              # interactive (press Enter to advance)
    python tests/demo.py --auto       # auto-advance (2-second delay)
    python tests/demo.py --url http://localhost:8000
"""

import json
import sys
import time
import argparse
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8000/api"

# ── ANSI ──────────────────────────────────────────────────────────────────────
_R      = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[32m"
_CYAN   = "\033[36m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_MAGENTA= "\033[35m"
_WHITE  = "\033[97m"

W = 68   # column width

# ── Helpers ───────────────────────────────────────────────────────────────────

def _http_post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _send(base: str, customer_id: str, channel: str, message: str) -> dict:
    return _http_post(f"{base}/message", {
        "customer_id": customer_id,
        "channel":     channel,
        "message":     message,
    })


def _memory(base: str, customer_id: str) -> dict:
    return _http_get(f"{base}/memory/{customer_id}")


def _tickets(base: str, customer_id: str) -> dict:
    try:
        return _http_get(f"{base}/tickets/{customer_id}")
    except urllib.error.HTTPError as e:
        return {"tickets": [], "note": str(e)}

# ── Presenter controls ────────────────────────────────────────────────────────

_AUTO   = False
_DELAY  = 2.0


def _pause(prompt: str = "") -> None:
    if _AUTO:
        time.sleep(_DELAY)
    else:
        try:
            input(f"\n  {_DIM}[{prompt or 'Enter to continue'}]{_R} ")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)


def _clear_line() -> None:
    print()

# ── Display blocks ────────────────────────────────────────────────────────────

def _banner() -> None:
    print(f"\n{'╔' + '═'*(W-2) + '╗'}")
    print(f"{'║'}{_BOLD}{_CYAN}{'  FLOWDESK — Customer Success AI':^{W-2}}{_R}{'║'}")
    print(f"{'║'}{_BOLD}{'  Live Demo':^{W-2}}{'║'}")
    print(f"{'╚' + '═'*(W-2) + '╝'}")


def _step(n: int, title: str) -> None:
    print(f"\n{'─'*W}")
    print(f"  {_BOLD}{_CYAN}STEP {n}{_R}  {_BOLD}{title}{_R}")
    print(f"{'─'*W}")


def _narrate(text: str) -> None:
    """Print a narrator line (grey, indented)."""
    print(f"\n  {_DIM}▶  {text}{_R}")


def _user_msg(channel: str, customer: str, message: str) -> None:
    icon = {"email": "✉", "whatsapp": "📱", "web": "🌐"}.get(channel, "?")
    print(f"\n  {_YELLOW}{icon}  CUSTOMER [{channel.upper()}]{_R}")
    print(f"  {_BOLD}{customer}{_R}")
    # Wrap long messages
    for line in message.splitlines():
        print(f"    {line}")


def _ai_reply(result: dict) -> None:
    escalated = result.get("escalated", False)
    source    = result.get("source", "?")
    intent    = result.get("intent", "?")
    priority  = result.get("priority", "low")
    reason    = result.get("escalation_reason", "")
    ticket_id = result.get("ticket_id")
    response  = result.get("response", "")

    status = (f"{_RED}ESCALATED{_R}" if escalated else f"{_GREEN}RESOLVED{_R}")

    print(f"\n  {_CYAN}🤖  AI AGENT{_R}  {status}")
    print(f"  {_DIM}source={source}  intent={intent}", end="")
    if escalated:
        print(f"  priority={priority}  reason={reason}", end="")
    if ticket_id:
        print(f"  ticket=#{ticket_id}", end="")
    print(f"{_R}")

    # Print response (wrapped)
    print()
    for line in response.splitlines():
        if line.strip():
            print(f"    {line}")


def _memory_snapshot(mem: dict) -> None:
    print(f"\n  {_MAGENTA}📋  MEMORY SNAPSHOT{_R}")
    print(f"  {_DIM}turns={mem.get('turns')}  "
          f"topic={mem.get('topic')!r}  "
          f"sentiment={mem.get('sentiment')}  "
          f"channel={mem.get('channel')}{_R}")


def _ticket_snapshot(data: dict) -> None:
    tickets = data.get("tickets", [])
    print(f"\n  {_MAGENTA}🎫  TICKETS{_R}")
    if not tickets:
        print(f"  {_DIM}(none — DB may not be running){_R}")
        return
    for t in tickets:
        print(
            f"  {_DIM}#{t['id']}  status={t['status']}  "
            f"priority={t['priority']}  reason={t['reason']}  "
            f"created={t['created_at'][:19]}{_R}"
        )

# ── Demo steps ────────────────────────────────────────────────────────────────

def run_demo(base: str) -> None:
    _banner()
    print(f"\n  API: {base}")
    _pause("Press Enter to start the demo")

    # ── STEP 1: Simple web query ──────────────────────────────────────────────
    _step(1, "Customer sends a support question via the web portal")
    _narrate("Sarah can't log in. She opens the support widget and asks for help.")

    _user_msg("web", "sarah.m@company.com", "Hi! I forgot my password and can't log in")
    result = _send(base, "sarah.m@company.com", "web",
                   "Hi! I forgot my password and can't log in")
    _ai_reply(result)
    _narrate("The AI matched the password reset docs instantly — no human needed.")
    _pause()

    # ── STEP 2: Follow-up uses memory ─────────────────────────────────────────
    _step(2, "Follow-up question — AI uses conversation memory")
    _narrate("Sarah has more questions. Notice she doesn't repeat context — "
             "the AI remembers her topic from the last message.")

    _user_msg("web", "sarah.m@company.com", "ok, but now it's asking for a 2FA code")
    result = _send(base, "sarah.m@company.com", "web",
                   "ok, but now it's asking for a 2FA code")
    _ai_reply(result)

    _user_msg("web", "sarah.m@company.com", "I don't have my backup codes anymore")
    result = _send(base, "sarah.m@company.com", "web",
                   "I don't have my backup codes anymore")
    _ai_reply(result)

    mem = _memory(base, "sarah.m@company.com")
    _memory_snapshot(mem)
    _narrate("3 turns stored. Topic carried forward between messages automatically.")
    _pause()

    # ── STEP 3: Acknowledgment detection ──────────────────────────────────────
    _step(3, "Acknowledgment — smart short-circuit")
    _narrate("'Thanks!' should NOT trigger a doc search. The AI detects it as a "
             "closing message and responds warmly without any processing overhead.")

    _user_msg("web", "sarah.m@company.com", "Thanks, that worked!")
    result = _send(base, "sarah.m@company.com", "web", "Thanks, that worked!")
    _ai_reply(result)
    _narrate(f"Intent = {result['intent']!r}. No doc search. No escalation. Clean.")
    _pause()

    # ── STEP 4: WhatsApp — short messages ─────────────────────────────────────
    _step(4, "WhatsApp channel — short messages, compact replies")
    _narrate("Marcus is on WhatsApp. The AI formats responses for mobile: "
             "one clear sentence, no long paragraphs.")

    msgs = [
        "hi, does flowdesk work with whatsapp?",
        "how do I connect it?",
    ]
    for msg in msgs:
        _user_msg("whatsapp", "+447911 555 001", msg)
        result = _send(base, "+447911555001", "whatsapp", msg)
        _ai_reply(result)

    _narrate("WhatsApp responses extract the most useful sentence from the docs.")
    _pause()

    # ── STEP 5: Email — formal formatting ─────────────────────────────────────
    _step(5, "Email channel — formal greeting and sign-off")
    _narrate("Priya emails from her work account. The AI detects the email channel "
             "and applies a formal greeting and sign-off automatically.")

    email_body = (
        "Dear Flowdesk Support,\n\n"
        "We are looking to invite three new team members to our workspace. "
        "Could you walk me through the process?\n\n"
        "Kind regards,\nPriya Kapoor"
    )
    _user_msg("email", "priya.k@startup.io", email_body)
    result = _send(base, "priya.k@startup.io", "email", email_body)
    _ai_reply(result)
    _narrate("Notice the 'Hi Priya,' greeting and 'Best regards, Flowdesk Support' closing.")
    _pause()

    # ── STEP 6: Refund escalation — high priority ticket ─────────────────────
    _step(6, "Escalation: refund request → high priority ticket")
    _narrate("David was overcharged. The AI recognises a billing dispute and "
             "escalates immediately — creating a high-priority ticket.")

    _user_msg("web", "david.r@enterprise.com",
              "I've been charged twice this month. I want a full refund now.")
    result = _send(base, "david.r@enterprise.com", "web",
                   "I've been charged twice this month. I want a full refund now.")
    _ai_reply(result)
    tickets = _ticket_snapshot(_tickets(base, "david.r@enterprise.com"))
    _narrate("Ticket created with reason=refund, priority=high. "
             "Billing team is notified.")
    _pause()

    # ── STEP 7: Ticket deduplication ──────────────────────────────────────────
    _step(7, "Ticket deduplication — same customer, no duplicate tickets")
    _narrate("David sends a follow-up. The AI finds his existing open ticket "
             "and updates it — no second ticket is created.")

    _user_msg("web", "david.r@enterprise.com",
              "Still no response! This is completely unacceptable.")
    result = _send(base, "david.r@enterprise.com", "web",
                   "Still no response! This is completely unacceptable.")
    _ai_reply(result)
    tickets = _ticket_snapshot(_tickets(base, "david.r@enterprise.com"))
    _narrate(f"Same ticket #{result.get('ticket_id')} reused. Status updated to 'escalated'.")
    _pause()

    # ── STEP 8: Pricing → medium priority ─────────────────────────────────────
    _step(8, "Escalation: pricing question → medium priority, sales team")
    _narrate("A prospect asks about pricing. This routes to the sales team "
             "with medium priority — lower urgency than billing disputes.")

    _user_msg("web", "lead@prospect.com",
              "What's the cost for 50 users on the Growth plan?")
    result = _send(base, "lead@prospect.com", "web",
                   "What's the cost for 50 users on the Growth plan?")
    _ai_reply(result)
    _ticket_snapshot(_tickets(base, "lead@prospect.com"))
    _narrate("Priority=medium. Sales team follows up within 1 business day.")
    _pause()

    # ── STEP 9: Negative sentiment ────────────────────────────────────────────
    _step(9, "Subtle escalation: negative sentiment detection")
    _narrate("No angry keywords — but 'disappointed' and 'broken' are enough "
             "for the AI to escalate with empathy, not a generic error.")

    _user_msg("web", "frustrated@user.com",
              "I am really disappointed, everything feels slow and broken today")
    result = _send(base, "frustrated@user.com", "web",
                   "I am really disappointed, everything feels slow and broken today")
    _ai_reply(result)
    _narrate(f"reason={result.get('escalation_reason')!r}  "
             f"priority={result.get('priority')} — caught without explicit angry words.")
    _pause()

    # ── STEP 10: Legal escalation ─────────────────────────────────────────────
    _step(10, "Escalation: legal threat → highest priority, legal team")
    _narrate("The AI recognises legal language and routes directly to the legal "
             "team with a calm, professional response.")

    _user_msg("web", "legal@partner.com",
              "We intend to pursue legal action if this data issue isn't resolved")
    result = _send(base, "legal@partner.com", "web",
                   "We intend to pursue legal action if this data issue isn't resolved")
    _ai_reply(result)
    _narrate("reason=legal, priority=high. No escalation phrasing — just calm professionalism.")
    _pause()

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'╔' + '═'*(W-2) + '╗'}")
    print(f"{'║'}{_BOLD}{_GREEN}{'  Demo Complete':^{W-2}}{_R}{'║'}")
    print(f"{'╚' + '═'*(W-2) + '╝'}")
    print(f"""
  {_BOLD}What you just saw:{_R}

  {_GREEN}✓{_R}  Doc search — instant answers from product docs
  {_GREEN}✓{_R}  Conversation memory — follow-ups work without re-explaining
  {_GREEN}✓{_R}  Acknowledgment detection — "Thanks!" never triggers a search
  {_GREEN}✓{_R}  Channel formatting — email formal, WhatsApp compact, web clean
  {_GREEN}✓{_R}  Escalation routing — pricing → sales, refund → billing, legal → legal
  {_GREEN}✓{_R}  Priority tiers — high (refund/legal/angry), medium (pricing)
  {_GREEN}✓{_R}  Negative sentiment — escalates on disappointment, not just anger
  {_GREEN}✓{_R}  Ticket deduplication — no duplicate tickets per customer
  {_GREEN}✓{_R}  Ticket ID in response — customer always knows their reference

  {_DIM}Run the full test suite:  python tests/test_system.py{_R}
""")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flowdesk live demo")
    parser.add_argument("--url",  default=DEFAULT_URL,
                        help=f"Base API URL (default: {DEFAULT_URL})")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-advance steps (no Enter required)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between steps in auto mode (default: 2)")
    args = parser.parse_args()

    _AUTO  = args.auto
    _DELAY = args.delay

    try:
        run_demo(base=args.url)
    except urllib.error.URLError as exc:
        print(f"\n  \033[31m[FATAL]\033[0m Cannot reach {args.url}/health: {exc.reason}")
        print("         Start the backend first:  uvicorn main:app --reload\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n  Demo interrupted.\n")
        sys.exit(0)
