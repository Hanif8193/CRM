"""
Customer Success AI Agent
Decision flow per message:
  1. Cache hit?           → return cached answer     (no Claude, instant)
  2. Escalation keyword?  → return static message    (no Claude)
  3. Doc section match?   → return doc answer        (no Claude)
  4. Anything else        → call Claude
"""

import re
import time
from pathlib import Path
import anthropic
from config import ANTHROPIC_API_KEY

# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------

CONTEXT_DIR = Path(__file__).resolve().parents[2] / "context"


def _load(filename: str) -> str:
    path = CONTEXT_DIR / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""


COMPANY_PROFILE  = _load("company-profile.md")
PRODUCT_DOCS     = _load("product-docs.md")
ESCALATION_RULES = _load("escalation-rules.md")
BRAND_VOICE      = _load("brand-voice.md")


# ---------------------------------------------------------------------------
# Doc section parser
# Splits product-docs.md into {section_title: section_content} at load time.
# ---------------------------------------------------------------------------

def _parse_sections(markdown: str) -> dict[str, str]:
    """Split markdown on ## / ### headings → {title: body}. Drops [RESTRICTED] sections."""
    sections: dict[str, str] = {}
    current_title = ""
    current_lines: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            if current_title and current_lines:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title and current_lines:
        sections[current_title] = "\n".join(current_lines).strip()

    return {k: v for k, v in sections.items() if "[RESTRICTED]" not in k}


DOCS_SECTIONS = _parse_sections(PRODUCT_DOCS)


# ---------------------------------------------------------------------------
# Topic → section mapping
# Each entry: ([trigger phrases], "Exact Section Title in DOCS_SECTIONS")
# More specific / multi-word phrases are listed first to win over shorter ones.
# ---------------------------------------------------------------------------

TOPIC_KEYWORD_MAP: list[tuple[list[str], str]] = [
    # Account & password
    (["reset password", "forgot password", "reset my password", "password reset",
      "reset link", "password link", "new password", "change password"],
     "How to Reset Your Password"),
    (["change email", "update email", "new email", "update my email"],
     "How to Change Your Email Address"),
    (["2fa", "two factor", "two-factor", "authenticator", "mfa", "backup code"],
     "Two-Factor Authentication (2FA)"),
    (["can't log in", "cannot log in", "login issue", "sign in problem",
      "won't let me in", "locked out", "login not working"],
     "I can't log in to my account"),

    # Getting started
    (["invite", "add member", "add agent", "add user", "team member", "new member"],
     "Inviting Team Members"),
    (["create account", "sign up", "getting started", "how do i start", "new account"],
     "Creating Your Account"),

    # Features
    (["unified inbox", "shared inbox"],                        "Unified Inbox"),
    (["ai agent", "confidence threshold", "confidence score",
      "ai wrong", "wrong answers", "retrain", "training data"], "AI Agent"),
    (["ticket", "tickets", "sla", "merge ticket", "ticket priority"],
     "Ticket Management"),
    (["knowledge base", "help center", "help article"],        "Knowledge Base"),
    (["analytics", "report", "dashboard", "csat",
      "agent performance", "export report"],                   "Analytics Dashboard"),
    (["canned response", "canned replies", "/greet",
      "shortcut message", "quick reply"],                      "Canned Responses"),

    # Integrations
    (["connect gmail", "gmail setup", "gmail integration"],    "Gmail / Google Workspace"),
    (["gmail not syncing", "emails not showing",
      "not receiving emails", "email sync", "emails stopped"], "I'm not receiving customer emails"),
    (["whatsapp setup", "connect whatsapp",
      "whatsapp business api", "whatsapp integration"],        "WhatsApp Business"),
    (["whatsapp not delivering", "whatsapp not received",
      "customers not receiving whatsapp"],
     "WhatsApp messages are sending but customers aren't receiving them"),
    (["stripe", "billing info sidebar", "connect stripe"],     "Stripe"),
    (["slack", "slack notification", "connect slack"],         "Slack"),

    # Troubleshooting
    (["chat widget", "widget not showing", "widget disappeared",
      "embed script", "widget missing"],
     "Chat widget is not appearing on my website"),
    (["wrong agent", "wrong assignment", "assignment rule",
      "routing rule", "misrouted"],
     "Conversations are being assigned to the wrong agent"),
]

# Flat set of every meaningful word used across all keywords — used for token scoring
_ALL_KEYWORD_TOKENS: set[str] = {
    token
    for phrases, _ in TOPIC_KEYWORD_MAP
    for phrase in phrases
    for token in phrase.split()
}

# Words that carry no search signal
_STOPWORDS = {
    "i", "my", "me", "we", "you", "your", "our", "its", "it",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "have", "has", "had",
    "how", "what", "why", "when", "where", "which", "who",
    "can", "could", "would", "should", "will", "may", "might",
    "to", "for", "in", "on", "at", "of", "from", "with", "by",
    "not", "no", "please", "help", "need", "want", "trying",
    "try", "get", "use", "just", "also", "about", "up",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens, stripped of stopwords and very short tokens."""
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def _find_doc_answer(message: str) -> tuple[str, str] | None:
    """
    Two-phase search for a matching doc section.

    Phase 1 — Phrase match (exact substring):
      Fast and high-confidence. Checks whether any multi-word trigger phrase
      appears verbatim in the message.

    Phase 2 — Token scoring (partial match):
      Tokenizes the message and scores each map entry by how many of its
      keyword tokens overlap with the message tokens. Returns the best
      scoring section if it meets the minimum threshold (2 matching tokens).
      This catches paraphrased or partial questions like:
        "my password is broken" → matches "password" → How to Reset Your Password

    Returns (section_title, section_content) or None.
    """
    lower = message.lower()

    # Phase 1: exact phrase match
    for keywords, section_title in TOPIC_KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            content = DOCS_SECTIONS.get(section_title)
            if content:
                return section_title, content

    # Phase 2: token scoring
    message_tokens = _tokenize(message)
    if not message_tokens:
        return None

    best_score = 0
    best_entry: tuple[str, str] | None = None

    for keywords, section_title in TOPIC_KEYWORD_MAP:
        # Score = number of keyword tokens that appear in the message
        score = sum(
            len(message_tokens & _tokenize(kw))
            for kw in keywords
        )
        if score > best_score:
            content = DOCS_SECTIONS.get(section_title)
            if content:
                best_score = score
                best_entry = (section_title, content)

    # Require at least 2 overlapping tokens to avoid false positives
    if best_score >= 2:
        return best_entry

    return None


# ---------------------------------------------------------------------------
# Escalation detection
# ---------------------------------------------------------------------------

PRICING_KEYWORDS = [
    "price", "pricing", "how much", "cost", "plan cost", "subscription cost",
    "upgrade cost", "downgrade", "discount", "promo", "coupon", "cheaper",
    "monthly fee", "annual fee", "what does it cost",
]

REFUND_KEYWORDS = [
    "refund", "money back", "reimburse", "overcharged", "duplicate charge",
    "chargeback", "billing dispute", "wrong charge",
]

ANGRY_KEYWORDS = [
    "furious", "angry", "unacceptable", "ridiculous", "terrible", "awful",
    "worst", "useless", "scam", "fraud", "demand", "threatening",
    "i'm done", "fed up", "horrible", "disgusting", "outrageous",
]

LEGAL_KEYWORDS = [
    "gdpr", "data protection", "legal notice", "cease and desist",
    "attorney", "regulatory", "ico", "ftc", "dpa", "data processing agreement",
    "unauthorized use", "intellectual property", "lawsuit", "legal action", "sue",
]

SECURITY_KEYWORDS = [
    "account suspended", "account locked", "unauthorized login", "security breach",
    "account hacked", "someone logged in", "data breach", "audit trail",
    "account activity", "suspicious activity", "compromised", "access logs",
    "locked out unexpectedly", "account disabled",
]

ENTERPRISE_KEYWORDS = [
    "enterprise", "sso", "saml", "50 agents", "100 seats", "white label",
    "custom contract", "dedicated infrastructure", "custom sla", "dedicated manager",
    "white-label", "custom branding", "large team",
]

CANCELLATION_KEYWORDS = [
    "cancel account", "cancel subscription", "want to cancel", "cancel my plan",
    "how do i cancel", "how to cancel", "delete my account", "close my account",
    "i want to leave", "switching to another", "leaving flowdesk",
]


def _matches(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def detect_intent(message: str) -> str:
    """Returns: legal | security | cancellation | enterprise | refund | pricing | angry | product"""
    if _matches(message, LEGAL_KEYWORDS):        return "legal"
    if _matches(message, SECURITY_KEYWORDS):     return "security"
    if _matches(message, CANCELLATION_KEYWORDS): return "cancellation"
    if _matches(message, ENTERPRISE_KEYWORDS):   return "enterprise"
    if _matches(message, REFUND_KEYWORDS):       return "refund"
    if _matches(message, PRICING_KEYWORDS):      return "pricing"
    if _matches(message, ANGRY_KEYWORDS):        return "angry"
    return "product"


ESCALATION_MESSAGES = {
    "pricing": (
        "For pricing details, I'd love to connect you with our sales team "
        "who can find the best plan for your needs. Reach them at "
        "sales@flowdesk.io or book a call at flowdesk.io/demo — "
        "someone will be in touch within 1 business day."
    ),
    "refund": (
        "I'm sorry about this billing issue — I completely understand how "
        "frustrating that must be. Refund and billing requests are handled "
        "directly by our billing team. I'm flagging this as urgent for them "
        "now. You can also reach them at billing@flowdesk.io. They typically "
        "respond within 1 business day."
    ),
    "legal": (
        "Thank you for bringing this to our attention. This matter requires "
        "review by our legal and compliance team. I'm flagging this for them "
        "immediately and marking it as urgent. Please expect a response within "
        "1–2 business days. For time-sensitive matters, email legal@flowdesk.io."
    ),
    "security": (
        "I take security and account issues very seriously. I'm escalating this "
        "to our security and account team right now so they can investigate "
        "personally. Please do not share any sensitive credentials here. Our team "
        "will contact you at the email on file within 1 business day."
    ),
    "enterprise": (
        "This sounds like a great fit for our Enterprise program! Our enterprise "
        "team offers tailored solutions including custom SLAs, dedicated onboarding, "
        "and more. I'm connecting you with an Enterprise Account Executive — they'll "
        "reach out within 1 business day. You can also fast-track by emailing "
        "enterprise@flowdesk.io."
    ),
    "cancellation": (
        "I'm sorry to hear you're thinking of leaving — we'd love the chance to "
        "make things right. I'm connecting you with a member of our customer success "
        "team who can assist with your account. They'll reach out shortly. You can "
        "also email success@flowdesk.io if you prefer."
    ),
}

FALLBACK_MESSAGE = (
    "I'm having trouble responding right now — connecting you to support. "
    "A human agent will be with you shortly."
)


# ---------------------------------------------------------------------------
# Channel formatting
# ---------------------------------------------------------------------------

CHANNEL_INSTRUCTIONS = {
    "whatsapp": (
        "CHANNEL: WhatsApp. Keep your reply SHORT — 2 to 4 sentences maximum. "
        "Plain text only, no markdown, no bullet points. Mobile-friendly language."
    ),
    "email": (
        "CHANNEL: Email. Use a formal greeting ('Hi [Name],') and sign-off "
        "('Best regards, Flowdesk Support Team'). Short paragraphs. "
        "Be thorough — the customer may not reply quickly."
    ),
    "web": (
        "CHANNEL: Web Chat. Medium-length reply. Use numbered steps or bullet points. "
        "End with: 'Let me know if that helps!'"
    ),
}


def _build_system_prompt(channel: str) -> str:
    channel_instruction = CHANNEL_INSTRUCTIONS.get(channel, CHANNEL_INSTRUCTIONS["web"])
    return f"""You are the Flowdesk Customer Success AI Agent.
Your job is to help customers resolve issues accurately, warmly, and efficiently.

CHANNEL FORMATTING
{channel_instruction}

BRAND VOICE
{BRAND_VOICE}

COMPANY PROFILE
{COMPANY_PROFILE}

PRODUCT DOCUMENTATION
Answer questions using ONLY the information below. Do not invent facts.
{PRODUCT_DOCS}

ESCALATION RULES
{ESCALATION_RULES}

BEHAVIOR
- Pricing, refunds, legal → use exact escalation message from the rules above.
- Angry customers → validate feelings first, then solve or escalate.
- If answer not in docs → admit it and offer to connect with a human.
- Never fabricate prices, deadlines, or guarantees.
"""


# ---------------------------------------------------------------------------
# Cache  (in-memory, per process)
# Key: (normalized_message, channel)  — same question on different channels
# gets different formatting so they are stored separately.
# ---------------------------------------------------------------------------

_cache: dict[tuple[str, str], dict] = {}


def _cache_key(message: str, channel: str) -> tuple[str, str]:
    """Normalize message to improve hit rate for minor variations."""
    normalized = " ".join(message.lower().split())   # collapse whitespace
    normalized = re.sub(r"[^\w\s]", "", normalized)  # strip punctuation
    return (normalized, channel)


# ---------------------------------------------------------------------------
# Metrics  (in-memory counters, reset on process restart)
# ---------------------------------------------------------------------------

METRICS: dict[str, int] = {
    "total":      0,
    "cache_hits": 0,
    "escalation": 0,
    "docs":       0,
    "claude":     0,
    "fallback":   0,
}


def get_metrics() -> dict[str, int]:
    """Return a copy of the current metrics counters."""
    return dict(METRICS)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(intent: str, channel: str, source: str,
         elapsed_ms: float, detail: str = "") -> None:
    detail_str = f" | {detail}" if detail else ""
    print(
        f"[AGENT] intent={intent:<10} channel={channel:<10} "
        f"source={source:<11} elapsed={elapsed_ms:>6.0f}ms{detail_str}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def get_agent_response(
    customer_message: str,
    channel: str = "web",
    conversation_history: list | None = None,
) -> dict:
    """
    Process a customer message and return:
        {
            "response":  str,   # reply to send to the customer
            "intent":    str,   # detected intent
            "escalated": bool,  # True when routed to a human queue
            "source":    str,   # "cache" | "escalation" | "docs" | "claude" | "fallback"
        }
    """
    t_start = time.time()

    if conversation_history is None:
        conversation_history = []

    METRICS["total"] += 1
    intent = detect_intent(customer_message)

    # ------------------------------------------------------------------
    # Step 1 — Cache
    #   Only cache single-turn messages. Multi-turn conversations are
    #   contextual so the same text may need a different reply.
    # ------------------------------------------------------------------
    if not conversation_history:
        key = _cache_key(customer_message, channel)
        if key in _cache:
            METRICS["cache_hits"] += 1
            elapsed = (time.time() - t_start) * 1000
            _log(intent, channel, "CACHE", elapsed, "hit")
            return _cache[key]

    # ------------------------------------------------------------------
    # Step 2 — Hard escalations  (pricing / refund / legal)
    # ------------------------------------------------------------------
    if intent in ESCALATION_MESSAGES:
        METRICS["escalation"] += 1
        result = {
            "response":  ESCALATION_MESSAGES[intent],
            "intent":    intent,
            "escalated": True,
            "source":    "escalation",
        }
        elapsed = (time.time() - t_start) * 1000
        _log(intent, channel, "ESCALATION", elapsed)
        return result

    # ------------------------------------------------------------------
    # Step 3 — Doc lookup
    #   Skip on multi-turn: contextual replies need Claude.
    # ------------------------------------------------------------------
    if not conversation_history:
        doc_match = _find_doc_answer(customer_message)
        if doc_match:
            section_title, section_content = doc_match
            METRICS["docs"] += 1
            result = {
                "response":  section_content,
                "intent":    intent,
                "escalated": False,
                "source":    "docs",
            }
            # Store in cache so the next identical question is instant
            key = _cache_key(customer_message, channel)
            _cache[key] = result
            elapsed = (time.time() - t_start) * 1000
            _log(intent, channel, "DOCS", elapsed, f"section={section_title}")
            return result

    # ------------------------------------------------------------------
    # Step 4 — Claude
    # ------------------------------------------------------------------
    system_prompt = _build_system_prompt(channel)
    messages = conversation_history + [{"role": "user", "content": customer_message}]

    try:
        api_result = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        reply = api_result.content[0].text
        escalated = _response_is_escalation(reply)
        METRICS["claude"] += 1
        result = {
            "response":  reply,
            "intent":    intent,
            "escalated": escalated,
            "source":    "claude",
        }
        # Cache single-turn Claude answers too
        if not conversation_history:
            key = _cache_key(customer_message, channel)
            _cache[key] = result
        elapsed = (time.time() - t_start) * 1000
        _log(intent, channel, "CLAUDE", elapsed)
        return result

    except Exception as e:
        METRICS["fallback"] += 1
        elapsed = (time.time() - t_start) * 1000
        _log(intent, channel, "FALLBACK", elapsed, f"error={e}")
        return {
            "response":  FALLBACK_MESSAGE,
            "intent":    intent,
            "escalated": True,
            "source":    "fallback",
        }


def _response_is_escalation(reply: str) -> bool:
    """Detect whether Claude's reply handed the conversation to a human."""
    phrases = [
        "connect you with", "human agent", "billing team", "sales team",
        "legal team", "flag this", "escalat", "someone will reach out",
    ]
    lower = reply.lower()
    return any(p in lower for p in phrases)
