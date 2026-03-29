"""
Customer Success AI Agent
==========================
Pure Python stdlib — zero external dependencies.

Run standalone : python simple_agent.py
Import as module: from agent.simple_agent import run_agent

Decision flow per message
--------------------------
 1. Detect channel   (email | whatsapp | web)
 2. Load customer memory
 3. Is it an acknowledgment?  → friendly closing, no search
 4. Detect intent    (pricing | refund | legal | angry | product)
 5. Hard escalation? → static message, escalated=True
 6. Angry?           → empathetic response, escalated=True
 7. Search docs      Phase 1: phrase match
                     Phase 2: token scoring  (≥2 tokens)
                     Phase 3: retry with prior topic if follow-up
 8. Doc found?       → return doc answer, escalated=False
 9. No match?        → AI fallback with prior-topic hint, escalated=True
10. Format for channel
11. Save turn to memory
12. Log to terminal
13. Return 4-field JSON
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────
# METRICS — shared counters for /api/metrics
# ─────────────────────────────────────────────
METRICS: dict[str, int] = {
    "total":      0,
    "cache_hits": 0,
    "escalation": 0,
    "docs":       0,
    "claude":     0,
    "fallback":   0,
}


def get_metrics() -> dict[str, int]:
    """Return a snapshot of live counters."""
    return dict(METRICS)


# ─────────────────────────────────────────────
# PRODUCT DOCS
# ─────────────────────────────────────────────
# Loaded from context/product-docs.md at startup.
# Falls back to _BUILTIN_DOCS when the file is missing
# so the agent works in isolation during testing.

_CONTEXT_DIR = Path(__file__).resolve().parents[2] / "context"


def _read_file(name: str) -> str:
    p = _CONTEXT_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


_BUILTIN_DOCS: dict[str, str] = {
    "reset password": (
        "To reset your password: go to app.flowdesk.io/login, click "
        "'Forgot your password?', enter your email, and check your inbox "
        "for a reset link — it expires in 60 minutes. "
        "Already logged in? Go to Settings > Security > Change Password."
    ),
    "invite team": (
        "To invite a team member: Settings > Team > Invite Member. "
        "Enter their email and choose a role — Admin (full access), "
        "Agent (respond to conversations), or Viewer (read-only). "
        "The invite is valid for 48 hours."
    ),
    "gmail not syncing": (
        "To fix Gmail sync: Settings > Channels > Gmail > Reconnect. "
        "Also check that IMAP is enabled in Gmail and that Flowdesk "
        "still has access under your Google account's third-party apps."
    ),
    "chat widget": (
        "If your chat widget isn't showing: paste the embed script just "
        "before the closing </body> tag. Add your domain under "
        "Settings > Channels > Web Chat > Allowed Domains, and check "
        "the browser console for JavaScript errors."
    ),
    "whatsapp supported": (
        "Yes! Flowdesk integrates with WhatsApp Business API. "
        "You will need a Meta Business Account to connect it. "
        "Go to Settings > Channels > WhatsApp > Connect via Meta to get started."
    ),
    "whatsapp setup": (
        "To connect WhatsApp: Settings > Channels > WhatsApp > Connect via Meta. "
        "You need a Meta Business Account and a WhatsApp Business API number. "
        "Meta approval typically takes 1-5 business days."
    ),
    "2fa": (
        "To enable 2FA: Settings > Security > Two-Factor Authentication > Enable 2FA. "
        "Scan the QR code with Google Authenticator or Authy, enter the 6-digit code, "
        "and save your backup codes somewhere safe."
    ),
    "canned responses": (
        "To set up canned responses: Settings > Canned Responses > New Response. "
        "Give it a shortcut like /greet and write your message. "
        "In any conversation, type the shortcut and press Tab to insert it."
    ),
    "analytics": (
        "Go to Reports > Analytics Dashboard to see total conversations, "
        "average response time, resolution time, and CSAT score. "
        "Export reports as CSV or PDF, or schedule weekly email summaries."
    ),
    "ticket management": (
        "Tickets can be created manually or automatically from conversations. "
        "Fields: Title, Priority (Low/Medium/High/Critical), Status, Assignee, Due Date. "
        "Duplicate tickets from the same customer can be merged."
    ),
    "knowledge base": (
        "Articles are organised into Collections and Categories. "
        "Mark articles as Public (customer-facing) or Internal (agents only). "
        "Your help centre URL is yoursubdomain.help.flowdesk.io."
    ),
    "stripe": (
        "To connect Stripe: Settings > Integrations > Stripe > Connect Stripe. "
        "Once connected, a customer's billing info appears in the conversation "
        "sidebar when their email matches a Stripe record."
    ),
    "ai agent": (
        "The AI Agent answers messages automatically using your knowledge base. "
        "Adjust the confidence threshold at Settings > AI > Confidence Level (default 75%). "
        "Fix wrong answers under Settings > AI > Training Data, then click Retrain."
    ),
    "login": (
        "Can't log in? Try resetting your password at app.flowdesk.io/login. "
        "Check for email typos and try a different browser or incognito mode. "
        "If 2FA is blocking you, use a backup code or email support@flowdesk.io."
    ),
    "trial": (
        "Flowdesk offers a 14-day free trial with no credit card required. "
        "All core features are available during the trial period."
    ),
}


def _parse_markdown_docs(md: str) -> dict[str, str]:
    """
    Split product-docs.md on ## / ### headings into {title_lower: body}.
    Drops [RESTRICTED] sections — those are handled by escalation rules.
    """
    docs: dict[str, str] = {}
    title = ""
    lines: list[str] = []

    for line in md.splitlines():
        if line.startswith("##"):
            if title and lines:
                docs[title] = "\n".join(lines).strip()
            title = line.lstrip("#").strip().lower()
            lines = []
        else:
            lines.append(line)

    if title and lines:
        docs[title] = "\n".join(lines).strip()

    return {k: v for k, v in docs.items() if "[restricted]" not in k}


_raw_md = _read_file("product-docs.md")
DOCS: dict[str, str] = _parse_markdown_docs(_raw_md) if _raw_md else _BUILTIN_DOCS


# ─────────────────────────────────────────────
# TOPIC KEYWORD MAP
# ─────────────────────────────────────────────
# Each entry: ([trigger phrases], "lookup key in DOCS or _BUILTIN_DOCS")
# Rules:
#   - More specific / multi-word phrases come before shorter ones
#   - Include "my X" variants where "my" is commonly inserted by users

_TOPIC_MAP: list[tuple[list[str], str]] = [

    # ── Password & account access ────────────────────────────
    (["reset my password", "forgot my password",        # ← "my" variants first
      "reset password",    "forgot password",
      "reset link",        "new password",
      "change password",   "password reset"],
     "how to reset your password"),

    (["change my email", "update my email",
      "change email",    "update email"],
     "how to change your email address"),

    (["2fa", "two factor", "two-factor",
      "authenticator", "mfa", "backup code"],
     "two-factor authentication (2fa)"),

    (["can't log in",       "cannot log in",
      "login not working",  "login issue",
      "locked out",         "won't let me in"],
     "i can't log in to my account"),

    # ── Team & onboarding ────────────────────────────────────
    (["invite member", "add member", "add agent",
      "add user",      "team member", "new member",
      "invite someone", "invite my team"],
     "inviting team members"),

    (["create account",  "sign up",
      "getting started", "how do i start"],
     "creating your account"),

    # ── Features ─────────────────────────────────────────────
    (["unified inbox", "shared inbox"],
     "unified inbox"),

    (["ai agent",           "confidence threshold",
      "confidence score",   "wrong answers",
      "retrain",            "training data",
      "ai is wrong"],
     "ai agent"),

    (["ticket",       "tickets",
      "sla",          "merge ticket",
      "ticket priority"],
     "ticket management"),

    (["knowledge base", "help center", "help article"],
     "knowledge base"),

    (["analytics",        "csat",
      "agent performance", "export report",
      "dashboard",         "response time stats"],
     "analytics dashboard"),

    (["canned response", "quick reply",
      "shortcut message", "/greet"],
     "canned responses"),

    # ── Integrations ─────────────────────────────────────────
    (["connect gmail", "gmail setup", "gmail integration"],
     "gmail / google workspace"),

    (["gmail not syncing",    "emails not showing",
      "not receiving emails", "email sync",
      "emails stopped"],
     "i'm not receiving customer emails"),

    # "Does Flowdesk support WhatsApp?" — answered before the setup entry
    (["does flowdesk work with whatsapp", "support whatsapp",
      "integrate whatsapp",               "whatsapp supported",
      "work with whatsapp"],
     "whatsapp supported"),

    (["whatsapp setup",     "connect whatsapp",
      "whatsapp business",  "set up whatsapp"],
     "whatsapp business"),

    (["whatsapp not delivering", "customers not receiving whatsapp"],
     "whatsapp messages are sending but customers aren't receiving them"),

    (["stripe", "connect stripe", "billing info sidebar"],
     "stripe"),

    (["slack", "connect slack", "slack notification"],
     "slack"),

    # ── Troubleshooting ──────────────────────────────────────
    (["chat widget",       "widget not showing",
      "widget disappeared", "embed script",
      "widget missing"],
     "chat widget is not appearing on my website"),

    (["wrong agent",      "wrong assignment",
      "routing rule",     "assignment rule"],
     "conversations are being assigned to the wrong agent"),

    (["trial", "free trial"],
     "trial"),

    # "login" is intentionally last — broad keyword, low specificity
    (["login", "sign in"],
     "login"),
]


# ─────────────────────────────────────────────
# DOC SEARCH
# ─────────────────────────────────────────────

_STOPWORDS: frozenset[str] = frozenset({
    "i", "my", "me", "we", "you", "your", "it", "its",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "have", "has", "had",
    "how", "what", "why", "when", "where", "which", "who",
    "can", "could", "would", "should", "will", "may", "might",
    "to", "for", "in", "on", "at", "of", "from", "with", "by",
    "not", "no", "please", "help", "need", "want", "get", "use",
    "just", "also", "about", "up", "any", "all",
    "and", "or", "but", "so", "if", "than", "then",
    "try", "trying", "our", "their", "this", "that", "there",
})


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens; stopwords and single-char tokens removed."""
    return {
        t for t in re.findall(r"\b\w+\b", text.lower())
        if t not in _STOPWORDS and len(t) > 1
    }


def _lookup(key: str) -> str | None:
    """
    Find section content by key.
    Checks DOCS (parsed from product-docs.md) first,
    then _BUILTIN_DOCS as a substring fallback.
    """
    if key in DOCS:
        return DOCS[key]
    # Builtin fallback: check if any builtin key is a substring of the TOPIC_MAP key
    for bk, bv in _BUILTIN_DOCS.items():
        if bk in key:
            return bv
    return None


def search_docs(message: str, prior_topic: str = "") -> tuple[str, str] | None:
    """
    Three-phase doc search.

    Phase 1 — Phrase match
        Checks every trigger phrase list for a verbatim substring in the
        lowercased message. Returns on the first hit (highest confidence).

    Phase 2 — Token scoring
        Strips stopwords from both the message and each phrase list, then
        counts token overlap. Returns the best scorer if overlap >= 2.

    Phase 3 — Prior-topic retry (follow-up handling)
        If phases 1–2 both fail and prior_topic is set, retries phases 1–2
        with the prior topic appended to the message. This lets follow-up
        questions like "what if my backup codes are lost?" resolve to the
        2FA section even though the message alone has no 2FA keywords.

    Returns (section_title, answer_text) or None.
    """

    def _run_phases(query: str) -> tuple[str, str] | None:
        lower = query.lower()

        # Phase 1: verbatim phrase match
        for phrases, key in _TOPIC_MAP:
            if any(phrase in lower for phrase in phrases):
                answer = _lookup(key)
                if answer:
                    return key, answer

        # Phase 2: token overlap scoring
        tokens = _tokenize(query)
        if not tokens:
            return None

        best_score: int = 0
        best: tuple[str, str] | None = None

        for phrases, key in _TOPIC_MAP:
            score = sum(len(tokens & _tokenize(p)) for p in phrases)
            if score > best_score:
                answer = _lookup(key)
                if answer:
                    best_score = score
                    best = (key, answer)

        return best if best_score >= 2 else None

    result = _run_phases(message)
    if result:
        return result

    # Phase 3: retry with prior topic context
    if prior_topic:
        return _run_phases(f"{message} {prior_topic}")

    return None


# ─────────────────────────────────────────────
# INTENT DETECTION
# ─────────────────────────────────────────────

_INTENTS: dict[str, list[str]] = {
    "pricing": [
        "price", "pricing", "how much", "cost", "plan cost",
        "subscription cost", "upgrade cost", "downgrade",
        "discount", "promo", "coupon", "monthly fee", "annual fee",
    ],
    "refund": [
        "refund", "money back", "reimburse", "overcharged",
        "duplicate charge", "chargeback", "billing dispute",
        "wrong charge",
    ],
    "legal": [
        "gdpr", "legal notice", "cease and desist", "lawsuit",
        "attorney", "legal action", "sue", "dpa",
        "data protection", "unauthorized use", "intellectual property",
        "ico", "ftc", "regulatory", "data processing agreement",
    ],
    "security": [
        "account suspended", "account locked", "unauthorized login",
        "security breach", "account hacked", "account is hacked",
        "been hacked", "got hacked", "hacked my account", "hacked",
        "someone logged in", "data breach", "audit trail",
        "account activity", "suspicious activity", "compromised",
        "access logs", "locked out unexpectedly", "account disabled",
    ],
    "enterprise": [
        "enterprise", "sso", "saml", "50 agents", "100 seats",
        "white label", "custom contract", "dedicated infrastructure",
        "custom sla", "dedicated manager", "white-label",
        "custom branding", "large company",
    ],
    "cancellation": [
        "cancel account", "cancel subscription", "want to cancel",
        "cancel my plan", "how do i cancel", "how to cancel",
        "delete my account", "close my account", "i want to leave",
        "switching to another", "leaving flowdesk",
    ],
    "angry": [
        "furious", "unacceptable", "terrible", "worst", "useless",
        "scam", "fraud", "demand", "fed up", "outrageous",
        "disgusting", "horrible", "i'm done",
    ],
}


def detect_intent(message: str) -> str:
    """Returns: pricing | refund | legal | security | enterprise | cancellation | angry | product"""
    lower = message.lower()
    for intent, keywords in _INTENTS.items():
        if any(kw in lower for kw in keywords):
            return intent
    return "product"


_ESCALATION_RESPONSES: dict[str, str] = {
    "pricing": (
        "For pricing details, our sales team can walk you through the best plan "
        "for your needs. Reach them at sales@flowdesk.io or book a call at "
        "flowdesk.io/demo. Someone will be in touch within 1 business day."
    ),
    "refund": (
        "I'm sorry about this billing issue — I completely understand how "
        "frustrating that must be. Refund and billing requests are handled "
        "directly by our billing team. I'm flagging this as urgent right now. "
        "You can also reach them at billing@flowdesk.io."
    ),
    "legal": (
        "Thank you for bringing this to our attention. This matter requires "
        "review by our legal and compliance team. I'm flagging it as urgent — "
        "please expect a response within 1-2 business days. "
        "For time-sensitive matters, email legal@flowdesk.io directly."
    ),
    "security": (
        "I take security and account issues very seriously. I'm escalating this "
        "to our security team right now so they can investigate personally. "
        "Please do not share any sensitive credentials here. Our team will "
        "contact you at the email on file within 1 business day."
    ),
    "enterprise": (
        "This sounds like a great fit for our Enterprise program! Our enterprise "
        "team offers tailored solutions including custom SLAs, dedicated onboarding, "
        "and more. I'm connecting you with an Enterprise Account Executive — "
        "they'll reach out within 1 business day. You can also email "
        "enterprise@flowdesk.io to fast-track."
    ),
    "cancellation": (
        "I'm sorry to hear you're thinking of leaving — we'd love the chance to "
        "make things right. I'm connecting you with our customer success team "
        "who can assist with your account. They'll reach out shortly. You can "
        "also email success@flowdesk.io if you prefer."
    ),
    # Triggered when _detect_sentiment returns "negative" without an explicit
    # angry/refund/legal keyword — catches frustrated, disappointed, broken, etc.
    "negative_sentiment": (
        "I can hear this hasn't been a smooth experience — I'm really sorry about that. "
        "I'm connecting you with a human support agent who can give this the personal "
        "attention it deserves. You should hear from someone very shortly."
    ),
}

# Priority and reason assigned per escalation intent.
# Used by the route layer to populate the tickets table.
_ESCALATION_PRIORITY: dict[str, str] = {
    "pricing":            "medium",
    "refund":             "high",
    "legal":              "high",
    "security":           "critical",
    "enterprise":         "medium",
    "cancellation":       "high",
    "angry":              "high",
    "negative_sentiment": "high",
}

# The reason stored in the DB ticket row.
_ESCALATION_REASON: dict[str, str] = {
    "pricing":            "pricing",
    "refund":             "refund",
    "legal":              "legal",
    "security":           "security",
    "enterprise":         "enterprise",
    "cancellation":       "cancellation",
    "angry":              "angry",
    "negative_sentiment": "negative_sentiment",
}


# ─────────────────────────────────────────────
# CHANNEL DETECTION
# ─────────────────────────────────────────────

_EMAIL_SIGNALS: frozenset[str] = frozenset([
    "dear ", "regards", "sincerely", "subject:", "to whom",
    "hi flowdesk", "hello flowdesk", "hi team",
])
_WHATSAPP_SIGNALS: frozenset[str] = frozenset([
    "hey!", "hiya", "quick q", "btw", "lol",
    "asap", "omg", "pls", "thx",
])


def detect_channel(message: str, hint: str = "") -> str:
    """
    Returns 'email' | 'whatsapp' | 'web'.
    An explicit valid hint is always used as-is.
    Otherwise inferred from signal words and message length.
    """
    if hint in {"email", "whatsapp", "web"}:
        return hint

    lower = message.lower()

    if any(s in lower for s in _EMAIL_SIGNALS) or len(message) > 300:
        return "email"

    if any(s in lower for s in _WHATSAPP_SIGNALS) or len(message) < 80:
        return "whatsapp"

    return "web"


# ─────────────────────────────────────────────
# ACKNOWLEDGMENT DETECTION
# ─────────────────────────────────────────────
# "Thanks!", "Got it", "ok perfect" etc. should NOT trigger a doc search.
# They get a friendly closing reply and the conversation is marked positive.

_ACK_WORDS: frozenset[str] = frozenset([
    "thanks", "thank", "thx", "ty",
    "got it", "gotcha", "understood", "noted",
    "ok", "okay", "great", "perfect", "awesome",
    "cool", "nice", "brilliant", "cheers", "appreciate",
])

_ACK_RESPONSE = (
    "You're welcome! Feel free to reach out anytime — "
    "we're always happy to help."
)

# ─────────────────────────────────────────────
# GREETING / INTRODUCTION DETECTION
# ─────────────────────────────────────────────
# "Hi I'm John", "I am Hanif, my number is …" etc. — the customer is
# identifying themselves, not asking a question yet.
# Respond with a warm welcome and ask how we can help.

_GREETING_PHRASES: tuple[str, ...] = (
    "i am ", "i'm ", "my name is ", "this is ", "hello i am",
    "hi i am", "hi i'm", "hey i am", "hey i'm",
    "hi my name", "hello my name",
)

_GREETING_RESPONSE = (
    "Hi there! Thanks for reaching out to Flowdesk Support. "
    "How can I help you today?"
)


_GREETING_OVERRIDE_WORDS: frozenset[str] = frozenset([
    # Negative sentiment — inlined here because _NEG_WORDS is defined later
    "frustrated", "angry", "terrible", "awful", "useless", "worst",
    "broken", "bad", "disappointed", "slow", "horrible",
    # Support / escalation signals
    "refund", "cancel", "price", "pricing", "legal", "sue",
    "problem", "issue", "error", "help", "how", "why", "when",
    "cant", "cannot", "please",
])


def _is_greeting(message: str) -> bool:
    """
    True when the message looks like a self-introduction with no support question.
    Conditions:
      - No question mark (it's a statement, not a query)
      - Starts with or contains a greeting/introduction phrase
      - No negative/escalation/support keywords that would override this path
    """
    if "?" in message:
        return False
    lower = message.lower().strip()
    if not any(lower.startswith(p) or f" {p}" in lower for p in _GREETING_PHRASES):
        return False
    # Bail out if the message also contains a real support signal
    words = set(re.findall(r"\b\w+\b", lower))
    return not bool(words & _GREETING_OVERRIDE_WORDS)


def _is_acknowledgment(message: str) -> bool:
    """
    True when the message is short (<=8 words) and contains only
    positive/closing words with no new question or keyword signals.
    Punctuation is stripped from each word before matching so that
    "thanks!" and "ok." match correctly.
    """
    if "?" in message:
        return False
    words = message.lower().split()
    if len(words) > 8:
        return False
    tokens = {re.sub(r"[^\w]", "", w) for w in words}
    return bool(tokens & _ACK_WORDS)


# ─────────────────────────────────────────────
# CONVERSATION MEMORY
# ─────────────────────────────────────────────
# Per customer_id dictionary. Replace _store with a DB-backed
# implementation in production.
#
# Schema per customer:
# {
#   "messages": [{"role": "user"|"agent", "text": str, "ts": str}],
#   "topic":    str,     last matched section title or intent
#   "sentiment": str,    "positive" | "negative" | "neutral"
#   "channel":  str,
#   "turns":    int,
#   "last_seen": str     ISO-8601 UTC
# }

_store: dict[str, dict] = {}

_POS_WORDS: frozenset[str] = frozenset([
    "thanks", "thank", "great", "love", "awesome", "perfect",
    "excellent", "wonderful", "appreciate", "happy", "helpful",
])
_NEG_WORDS: frozenset[str] = frozenset([
    "frustrated", "angry", "terrible", "awful", "useless", "worst",
    "broken", "bad", "disappointed", "slow", "problem", "horrible",
])


def _detect_sentiment(text: str) -> str:
    words = set(text.lower().split())
    if words & _NEG_WORDS:  return "negative"
    if words & _POS_WORDS:  return "positive"
    return "neutral"


def _is_followup(message: str, history: list[dict]) -> bool:
    """Short message with prior history = likely a follow-up question."""
    return bool(history) and len(message.split()) <= 10


def _get_record(customer_id: str) -> dict:
    return _store.setdefault(customer_id, {
        "messages":  [],
        "topic":     "",
        "sentiment": "neutral",
        "channel":   "web",
        "turns":     0,
        "last_seen": "",
    })


def _save_turn(customer_id: str, user_msg: str, agent_msg: str,
               topic: str, channel: str) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec = _get_record(customer_id)
    rec["messages"].append({"role": "user",  "text": user_msg,  "ts": now})
    rec["messages"].append({"role": "agent", "text": agent_msg, "ts": now})
    rec["topic"]     = topic
    rec["sentiment"] = _detect_sentiment(user_msg)
    rec["channel"]   = channel
    rec["turns"]    += 1
    rec["last_seen"] = now


def get_memory(customer_id: str) -> dict:
    """Return the full memory record for a customer (empty dict if none)."""
    return dict(_store.get(customer_id, {}))


# ─────────────────────────────────────────────
# AI FALLBACK
# ─────────────────────────────────────────────
# Used when no doc answer is found.
# Swap the body of this function for a real LLM call in production:
#
#   import anthropic
#   client = anthropic.Anthropic(api_key=YOUR_KEY)
#   result = client.messages.create(
#       model="claude-sonnet-4-6",
#       max_tokens=512,
#       messages=[{"role": "user", "content": message}],
#   )
#   return result.content[0].text

def _ai_fallback(intent: str, prior_topic: str = "") -> str:
    """
    Context-aware fallback without an LLM.
    Prior topic (from memory) personalises the message for follow-up threads.
    """
    if intent == "angry":
        return (
            "I completely understand your frustration and I'm truly sorry for "
            "the experience you've had. I'm escalating this to a senior support "
            "agent right now — someone will reach out to you very shortly."
        )

    if prior_topic:
        label = re.sub(r"^(how to |i'm not |i can't )", "", prior_topic).strip()
        return (
            f"I can see you've been asking about {label}. "
            "I want to make sure you get the right answer, so let me connect "
            "you with a support agent who can look into this further. "
            "You should hear from someone shortly."
        )

    return (
        "That's a great question. I want to make sure you get the right answer, "
        "so let me connect you with one of our support agents who can help directly. "
        "You should hear from someone shortly."
    )


# ─────────────────────────────────────────────
# RESPONSE FORMATTING
# ─────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """Remove markdown formatting for plain-text channels."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)        # **bold**
    text = re.sub(r"\*(.+?)\*",     r"\1", text)         # *italic*
    text = re.sub(r"`(.+?)`",       r"\1", text)         # `code`
    text = re.sub(r"^#{1,4}\s+",   "",    text, flags=re.MULTILINE)
    return text


def _format_email(text: str, name: str) -> str:
    greeting = f"Hi {name.split()[0]}," if name else "Hi there,"
    closing  = (
        "\n\nPlease don't hesitate to reach out if you need anything else.\n\n"
        "Best regards,\nFlowdesk Support Team"
    )
    return f"{greeting}\n\n{text.strip()}{closing}"


def _format_whatsapp(text: str) -> str:
    """
    Extract the single most useful line from potentially long doc content.

    Priority:
      1. First prose sentence that isn't a list item (reads like a direct answer)
      2. First numbered step (setup instructions)
      3. First non-empty line as a fallback

    Hard limit: 80 characters, trimmed at a word boundary.
    """
    plain = _strip_markdown(text)
    # Remove block formatting that's useless on mobile
    plain = re.sub(r"^[-*•>]\s+", "",   plain, flags=re.MULTILINE)
    plain = re.sub(r"-{3,}",      "",   plain)
    plain = re.sub(r"\n{2,}",     "\n", plain)

    lines = [l.strip() for l in plain.splitlines() if l.strip()]
    if not lines:
        return text[:80]

    steps = [l for l in lines if re.match(r"^\d+\.", l)]
    prose = [l for l in lines if not re.match(r"^\d+\.", l)]

    # Prefer a prose intro if present (e.g. "Yes! Flowdesk supports...")
    candidate = prose[0] if prose else steps[0]

    candidate = re.sub(r"\s+", " ", candidate).strip()
    if len(candidate) > 80:
        candidate = candidate[:77].rsplit(" ", 1)[0] + "..."

    return candidate


def _format_web(text: str) -> str:
    return _strip_markdown(text).strip()


def format_response(text: str, channel: str, customer_name: str = "") -> str:
    """Apply channel-specific formatting to a raw answer string."""
    if channel == "email":
        return _format_email(text, customer_name)
    if channel == "whatsapp":
        return _format_whatsapp(text)
    return _format_web(text)


# ─────────────────────────────────────────────
# TERMINAL LOGGING
# ─────────────────────────────────────────────

def _log(
    customer_id: str,
    channel:     str,
    source:      str,
    elapsed_ms:  float,
    reason:      str = "",
    priority:    str = "",
    ticket_id:   int | None = None,
) -> None:
    parts = (
        f"[AGENT] customer={customer_id:<16} "
        f"channel={channel:<10} "
        f"source={source:<13} "
        f"elapsed={elapsed_ms:>6.1f}ms"
    )
    if reason:
        parts += f"  reason={reason}"
    if priority:
        parts += f"  priority={priority}"
    if ticket_id is not None:
        parts += f"  ticket=#{ticket_id}"
    print(parts)


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def run_agent(
    customer_message: str,
    customer_id:      str = "anonymous",
    channel:          str = "",
    customer_name:    str = "",
) -> dict:
    """
    Process a single customer message end-to-end.

    Parameters
    ----------
    customer_message : raw text from the customer
    customer_id      : unique identifier used for memory
    channel          : 'email' | 'whatsapp' | 'web'
                       (auto-detected from the message when omitted)
    customer_name    : used in personalised email greetings

    Returns
    -------
    {
        "response":          str,
        "intent":            str,   pricing | refund | legal | angry | product | acknowledgment
        "escalated":         bool,
        "source":            str,   docs | escalation | ai | acknowledgment
        "escalation_reason": str,   set when escalated — matches intent or "negative_sentiment"
        "priority":          str,   "low" | "medium" | "high"  (always present)
    }
    The route layer is responsible for persisting ticket data to the DB and
    appending the ticket ID to the response text.
    """
    t_start = time.time()

    # Step 1 ─ resolve channel
    ch = detect_channel(customer_message, hint=channel)

    # Step 2 ─ load memory
    record      = _get_record(customer_id)
    history     = record["messages"]
    prior_topic = record["topic"]
    followup    = _is_followup(customer_message, history)

    # Step 3 ─ acknowledgment shortcut
    #   Must run BEFORE intent/doc detection so "Thanks!" never
    #   gets routed into the doc search via the prior-topic context.
    if _is_acknowledgment(customer_message):
        raw                = _ACK_RESPONSE
        intent             = "acknowledgment"
        source             = "acknowledgment"
        escalated          = False
        escalation_reason  = ""
        priority           = "low"

    # Step 3b ─ greeting / self-introduction shortcut
    #   "Hi I'm Hanif, my number is …" — customer is identifying themselves,
    #   not asking a support question yet. Reply warmly and prompt them.
    elif _is_greeting(customer_message):
        raw                = _GREETING_RESPONSE
        intent             = "greeting"
        source             = "acknowledgment"
        escalated          = False
        escalation_reason  = ""
        priority           = "low"

    # Step 4-9 ─ normal decision tree
    else:
        intent = detect_intent(customer_message)

        # Upgrade to "negative_sentiment" when the message carries clear negative
        # words (frustrated, disappointed, broken…) but no explicit escalation
        # keyword. Catches subtle dissatisfaction that keyword lists miss.
        if intent == "product" and _detect_sentiment(customer_message) == "negative":
            intent = "negative_sentiment"

        if intent in _ESCALATION_RESPONSES:
            # Hard escalation — never search docs
            raw               = _ESCALATION_RESPONSES[intent]
            source            = "escalation"
            escalated         = True
            escalation_reason = _ESCALATION_REASON.get(intent, intent)
            priority          = _ESCALATION_PRIORITY.get(intent, "low")

        elif intent == "angry":
            # Empathetic AI response + escalate
            raw               = _ai_fallback("angry")
            source            = "ai"
            escalated         = True
            escalation_reason = _ESCALATION_REASON.get("angry", "angry")
            priority          = _ESCALATION_PRIORITY.get("angry", "high")

        else:
            # Product question — search docs
            # Pass prior_topic only when this looks like a follow-up;
            # otherwise a fresh question might accidentally match old context.
            context = prior_topic if followup else ""
            match   = search_docs(customer_message, prior_topic=context)

            if match:
                section_title, raw = match
                prior_topic        = section_title   # update for next turn
                source             = "docs"
                escalated          = False
                escalation_reason  = ""
                priority           = "low"
            else:
                raw               = _ai_fallback("product", prior_topic=prior_topic)
                source            = "ai"
                escalated         = True
                escalation_reason = ""   # no specific reason — just no doc match
                priority          = "low"

    # Step 10 ─ channel formatting
    response = format_response(raw, ch, customer_name)

    # Step 11 ─ save to memory
    _save_turn(customer_id, customer_message, response,
               topic   = prior_topic or intent,
               channel = ch)

    # Step 12 ─ log (ticket_id logged later by the route layer)
    elapsed = (time.time() - t_start) * 1000
    _log(customer_id, ch, source, elapsed,
         reason=escalation_reason, priority=priority if escalated else "")

    # Step 12b ─ update metrics counters
    METRICS["total"] += 1
    if escalated:
        METRICS["escalation"] += 1
    if source == "docs":
        METRICS["docs"] += 1
    elif source == "ai":
        METRICS["claude"] += 1
        if not escalated:
            METRICS["fallback"] += 1

    # Step 13 ─ return
    return {
        "response":          response,
        "intent":            intent,
        "escalated":         escalated,
        "source":            source,
        "escalation_reason": escalation_reason,
        "priority":          priority,
    }


# ─────────────────────────────────────────────
# CLI DEMO — python simple_agent.py
# ─────────────────────────────────────────────

if __name__ == "__main__":

    _TESTS = [
        # (label, message, customer_id, channel, customer_name)

        # ── Phrase match ─────────────────────────────────────
        ("Password reset (phrase: 'forgot my password')",
         "Hey, I forgot my password and can't log in. How do I reset it?",
         "cust_001", "web", "Sarah Mitchell"),

        # ── Follow-up: uses prior topic ──────────────────────
        ("Follow-up: expired link (no direct keyword, uses memory)",
         "what if my reset link already expired?",
         "cust_001", "web", "Sarah Mitchell"),

        # ── Acknowledgment: must NOT trigger doc search ───────
        ("Acknowledgment: 'Thanks! That worked.'",
         "Thanks! That worked perfectly.",
         "cust_001", "web", "Sarah Mitchell"),

        # ── Email formatting ─────────────────────────────────
        ("Invite team (email — formal greeting + closing)",
         "Dear Flowdesk Support,\n\n"
         "I would like to invite three members of my team to our workspace. "
         "Could you walk me through the steps?\n\nKind regards, James",
         "cust_002", "email", "James Okafor"),

        # ── WhatsApp: prose intro extracted, not setup step ──
        ("WhatsApp support question (yes/no answer first)",
         "hi does flowdesk work with whatsapp?",
         "cust_003", "whatsapp", ""),

        # ── Hard escalation: pricing ──────────────────────────
        ("Pricing question (escalation)",
         "How much does the Growth plan cost per month?",
         "cust_004", "web", "Priya Nair"),

        # ── Hard escalation: refund ───────────────────────────
        ("Angry + refund (escalation, refund wins over angry)",
         "This is absolutely unacceptable! I demand a refund right now.",
         "cust_005", "web", "Derek Vance"),

        # ── AI fallback: no doc match ─────────────────────────
        ("Unknown question (AI fallback)",
         "Do you support integration with Microsoft Teams?",
         "cust_006", "web", ""),

        # ── Token scoring match ───────────────────────────────
        ("2FA: token scoring ('authenticator' alone scores 2+)",
         "My authenticator app is generating wrong codes",
         "cust_007", "web", "Elena Vasquez"),

        # ── Follow-up on 2FA using prior topic ───────────────
        ("Follow-up 2FA: 'lost backup codes' (no direct phrase, uses memory)",
         "what if I lost my backup codes?",
         "cust_007", "web", "Elena Vasquez"),
    ]

    W = 72
    for label, msg, cid, ch, name in _TESTS:
        print(f"\n{'=' * W}")
        print(f"  {label}")
        print("=" * W)

        result = run_agent(
            customer_message = msg,
            customer_id      = cid,
            channel          = ch,
            customer_name    = name,
        )

        print(json.dumps(result, indent=2, ensure_ascii=True))

        mem = get_memory(cid)
        print(
            f"\n  [MEMORY] "
            f"topic={mem.get('topic', '')!r:<46}"
            f"sentiment={mem.get('sentiment'):<10}"
            f"turns={mem.get('turns')}"
        )

    print(f"\n{'=' * W}")
    print("  All tests complete.")
    print("=" * W)
