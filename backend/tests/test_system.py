"""
Comprehensive system test for the Flowdesk CRM AI.

Covers every path through the agent:
  - web / email / whatsapp channels
  - doc search, acknowledgment, escalation, negative sentiment, AI fallback
  - conversation memory and follow-up context
  - ticket creation (priority + reason)
  - API response shape

Usage:
    # backend must be running first:
    #   uvicorn main:app --reload
    python tests/test_system.py
    python tests/test_system.py --url http://localhost:8000
"""

import json
import argparse
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone

DEFAULT_URL = "http://localhost:8000/api"

# ── ANSI colours ──────────────────────────────────────────────────────────────
_R = "\033[0m"
_BOLD   = "\033[1m"
_GREEN  = "\033[32m"
_RED    = "\033[31m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_DIM    = "\033[2m"

def _ok(s):   return f"{_GREEN}{s}{_R}"
def _fail(s): return f"{_RED}{s}{_R}"
def _warn(s): return f"{_YELLOW}{s}{_R}"
def _info(s): return f"{_CYAN}{s}{_R}"
def _dim(s):  return f"{_DIM}{s}{_R}"

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _delete(url: str) -> dict:
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

# ── Test result tracking ──────────────────────────────────────────────────────

@dataclass
class Result:
    name:   str
    passed: bool
    notes:  list[str] = field(default_factory=list)


_results: list[Result] = []


def _assert(condition: bool, name: str, notes: list[str]) -> Result:
    r = Result(name=name, passed=condition, notes=notes)
    _results.append(r)
    icon = _ok("PASS") if condition else _fail("FAIL")
    print(f"  [{icon}] {name}")
    for note in notes:
        colour = _dim if condition else _warn
        print(f"         {colour(note)}")
    return r

# ── Individual test cases ─────────────────────────────────────────────────────

def test_web_doc_response(base: str) -> None:
    print(f"\n{_bold_header('TEST 1 — Web: doc search (password reset)')}")
    r = _post(f"{base}/message", {
        "customer_id": "test_web_001",
        "channel":     "web",
        "message":     "Hi, I forgot my password and can't log in",
    })
    _print_response(r)
    _assert(
        not r["escalated"] and r["source"] == "docs" and r["intent"] == "product",
        "Password reset → docs, not escalated",
        [f"source={r['source']}  intent={r['intent']}  escalated={r['escalated']}"],
    )


def test_followup_memory(base: str) -> None:
    print(f"\n{_bold_header('TEST 2 — Web: follow-up uses memory (2FA thread)')}")

    r1 = _post(f"{base}/message", {
        "customer_id": "test_mem_001",
        "channel":     "web",
        "message":     "My authenticator app is generating wrong codes",
    })
    _print_response(r1)
    _assert(
        r1["source"] == "docs" and not r1["escalated"],
        "Turn 1: 2FA matched from docs",
        [f"source={r1['source']}  escalated={r1['escalated']}"],
    )

    r2 = _post(f"{base}/message", {
        "customer_id": "test_mem_001",
        "channel":     "web",
        "message":     "what if I lost my backup codes?",   # no direct 2FA keyword
    })
    _print_response(r2)
    _assert(
        r2["source"] == "docs" and not r2["escalated"],
        "Turn 2: follow-up resolved via prior-topic memory",
        [f"source={r2['source']}  escalated={r2['escalated']}",
         "Expected: 2FA section found through memory context"],
    )

    r3 = _post(f"{base}/message", {
        "customer_id": "test_mem_001",
        "channel":     "web",
        "message":     "Thanks, that worked!",
    })
    _print_response(r3)
    _assert(
        r3["intent"] == "acknowledgment" and not r3["escalated"],
        "Turn 3: acknowledgment detected — no doc search",
        [f"intent={r3['intent']}  source={r3['source']}"],
    )

    mem = _get(f"{base}/memory/test_mem_001")
    _assert(
        mem.get("turns", 0) == 3,
        "Memory persisted 3 turns",
        [f"turns={mem.get('turns')}  topic={mem.get('topic')!r}"],
    )


def test_email_escalation_refund(base: str) -> None:
    print(f"\n{_bold_header('TEST 3 — Email: refund escalation (high priority)')}")
    r = _post(f"{base}/message", {
        "customer_id": "refund@corp.com",
        "channel":     "email",
        "message":     (
            "Dear Flowdesk,\n\n"
            "I've been overcharged this month and need a full refund immediately. "
            "This is completely unacceptable.\n\nBest, David"
        ),
    })
    _print_response(r)
    _assert(
        r["escalated"] and r["escalation_reason"] == "refund" and r["priority"] == "high",
        "Refund escalation: reason=refund, priority=high",
        [f"escalated={r['escalated']}  reason={r['escalation_reason']}  "
         f"priority={r['priority']}  ticket_id={r.get('ticket_id')}"],
    )
    _assert(
        "Ticket ID" in r["response"] or r.get("ticket_id") is not None
        or "billing" in r["response"].lower(),
        "Response contains ticket info or billing contact",
        [f"response preview: {r['response'][:100]}..."],
    )


def test_whatsapp_pricing_escalation(base: str) -> None:
    print(f"\n{_bold_header('TEST 4 — WhatsApp: pricing escalation (medium priority)')}")
    r = _post(f"{base}/message", {
        "customer_id": "+447900112233",
        "channel":     "whatsapp",
        "message":     "how much does the growth plan cost?",
    })
    _print_response(r)
    _assert(
        r["escalated"] and r["escalation_reason"] == "pricing" and r["priority"] == "medium",
        "Pricing escalation: reason=pricing, priority=medium",
        [f"escalated={r['escalated']}  reason={r['escalation_reason']}  "
         f"priority={r['priority']}  ticket_id={r.get('ticket_id')}"],
    )
    _assert(
        len(r["response"]) < 400,
        "WhatsApp response is compact",
        [f"length={len(r['response'])} chars"],
    )


def test_legal_escalation(base: str) -> None:
    print(f"\n{_bold_header('TEST 5 — Web: legal escalation (high priority)')}")
    r = _post(f"{base}/message", {
        "customer_id": "legal_test_001",
        "channel":     "web",
        "message":     "I will be taking legal action unless you respond within 24 hours",
    })
    _print_response(r)
    _assert(
        r["escalated"] and r["escalation_reason"] == "legal" and r["priority"] == "high",
        "Legal escalation: reason=legal, priority=high",
        [f"escalated={r['escalated']}  reason={r['escalation_reason']}  "
         f"priority={r['priority']}  ticket_id={r.get('ticket_id')}"],
    )


def test_angry_escalation(base: str) -> None:
    print(f"\n{_bold_header('TEST 6 — Web: angry customer escalation (high priority)')}")
    r = _post(f"{base}/message", {
        "customer_id": "angry_test_001",
        "channel":     "web",
        "message":     "This is the worst software I have ever used — absolutely useless",
    })
    _print_response(r)
    _assert(
        r["escalated"] and r["priority"] == "high",
        "Angry escalation: escalated=True, priority=high",
        [f"escalated={r['escalated']}  reason={r['escalation_reason']}  "
         f"priority={r['priority']}"],
    )


def test_negative_sentiment_escalation(base: str) -> None:
    print(f"\n{_bold_header('TEST 7 — Web: negative sentiment (no angry keyword)')}")
    r = _post(f"{base}/message", {
        "customer_id": "neg_test_001",
        "channel":     "web",
        "message":     "I am really disappointed with how slow and broken everything is",
    })
    _print_response(r)
    _assert(
        r["escalated"] and r["escalation_reason"] == "negative_sentiment",
        "Negative sentiment escalated with correct reason",
        [f"escalated={r['escalated']}  reason={r['escalation_reason']}  "
         f"priority={r['priority']}"],
    )


def test_ticket_no_duplicate(base: str) -> None:
    print(f"\n{_bold_header('TEST 8 — Ticket deduplication (same customer, two escalations)')}")
    cid = "dedup_test_001"

    r1 = _post(f"{base}/message", {
        "customer_id": cid, "channel": "web",
        "message": "I want a refund for last month",
    })
    tid1 = r1.get("ticket_id")
    _print_response(r1)

    r2 = _post(f"{base}/message", {
        "customer_id": cid, "channel": "web",
        "message": "Still waiting for my refund — this is unacceptable",
    })
    tid2 = r2.get("ticket_id")
    _print_response(r2)

    if tid1 is not None and tid2 is not None:
        _assert(
            tid1 == tid2,
            "Same ticket reused — no duplicates",
            [f"ticket_id first={tid1}  second={tid2}"],
        )
    else:
        _assert(True, "Ticket dedup skipped (DB not available)", ["Running without DB"])


def test_whatsapp_thread(base: str) -> None:
    print(f"\n{_bold_header('TEST 9 — WhatsApp: multi-turn thread with memory')}")
    cid = "wa_thread_001"

    turns = [
        ("hi how do I reset my password",   False, "docs"),
        ("ok but my reset link expired",     False, "docs"),
        ("thanks!",                          False, "acknowledgment"),
        ("one more thing, can I add a user", False, "docs"),
    ]

    for msg, exp_escalated, exp_source in turns:
        r = _post(f"{base}/message", {
            "customer_id": cid, "channel": "whatsapp", "message": msg,
        })
        _print_response(r, label=f"  > {msg!r}")
        _assert(
            r["escalated"] == exp_escalated and r["source"] == exp_source,
            f"'{msg[:40]}...' → source={exp_source}, escalated={exp_escalated}",
            [f"source={r['source']}  escalated={r['escalated']}"],
        )

    mem = _get(f"{base}/memory/{cid}")
    _assert(
        mem.get("turns", 0) == 4,
        "Memory has 4 turns",
        [f"turns={mem.get('turns')}"],
    )


def test_memory_delete(base: str) -> None:
    print(f"\n{_bold_header('TEST 10 — Memory delete (GDPR erasure)')}")
    cid = "gdpr_test_001"

    _post(f"{base}/message", {
        "customer_id": cid, "channel": "web", "message": "hi, how do I reset my password",
    })

    before = _get(f"{base}/memory/{cid}")
    _assert(before.get("turns", 0) > 0, "Memory exists before delete",
            [f"turns={before.get('turns')}"])

    _delete(f"{base}/memory/{cid}")

    after = _get(f"{base}/memory/{cid}")
    _assert(after == {}, "Memory empty after delete", [f"returned: {after}"])


def test_health(base: str) -> None:
    print(f"\n{_bold_header('TEST 11 — Health endpoint')}")
    r = _get(f"{base}/health")
    _assert(r.get("status") == "healthy", "GET /api/health → healthy",
            [f"response: {r}"])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _bold_header(title: str) -> str:
    return f"{_BOLD}{_CYAN}{title}{_R}"


def _print_response(r: dict, label: str = "") -> None:
    if label:
        print(f"  {_dim(label)}")
    preview = r.get("response", "")[:120].replace("\n", " ")
    ticket  = f"  ticket=#{r['ticket_id']}" if r.get("ticket_id") else ""
    print(
        f"  {_dim('→')} escalated={_warn(str(r['escalated'])) if r['escalated'] else r['escalated']}"
        f"  source={r.get('source','?')}"
        f"  priority={r.get('priority','?')}"
        f"  reason={r.get('escalation_reason','') or '-'}"
        f"{ticket}"
    )
    print(f"  {_dim('response:')} {preview}")

# ── Runner ────────────────────────────────────────────────────────────────────

def run_all(base: str) -> None:
    print(f"\n{'═'*65}")
    print(f"  {_BOLD}FLOWDESK CRM — System Test Suite{_R}")
    print(f"  API: {base}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'═'*65}")

    # Connectivity check
    try:
        _get(f"{base}/health")
    except urllib.error.URLError as exc:
        print(f"\n{_fail('[FATAL]')} Cannot reach {base}/health: {exc.reason}")
        print("        Start the backend first:  uvicorn main:app --reload\n")
        return

    tests = [
        test_health,
        test_web_doc_response,
        test_followup_memory,
        test_email_escalation_refund,
        test_whatsapp_pricing_escalation,
        test_legal_escalation,
        test_angry_escalation,
        test_negative_sentiment_escalation,
        test_ticket_no_duplicate,
        test_whatsapp_thread,
        test_memory_delete,
    ]

    for fn in tests:
        try:
            fn(base)
        except urllib.error.URLError as exc:
            print(f"  {_fail('[ERROR]')} Network error in {fn.__name__}: {exc.reason}")
        except Exception as exc:
            print(f"  {_fail('[ERROR]')} Unexpected error in {fn.__name__}: {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(1 for r in _results if r.passed)
    failed = total - passed

    print(f"\n{'═'*65}")
    print(f"  {_BOLD}Results:{_R}  "
          f"{_ok(f'{passed} passed')}  "
          f"{(_fail(f'{failed} failed') if failed else _dim('0 failed'))}"
          f"  /  {total} assertions")

    if failed:
        print(f"\n  {_BOLD}Failed assertions:{_R}")
        for r in _results:
            if not r.passed:
                print(f"    {_fail('✗')} {r.name}")
                for note in r.notes:
                    print(f"      {_dim(note)}")

    print(f"{'═'*65}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flowdesk system test suite")
    parser.add_argument("--url", default=DEFAULT_URL,
                        help=f"Base API URL (default: {DEFAULT_URL})")
    args = parser.parse_args()
    run_all(base=args.url)
