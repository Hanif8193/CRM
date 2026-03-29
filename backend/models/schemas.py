from pydantic import BaseModel, field_validator
from typing import Optional, Literal
from datetime import datetime


class CustomerMessage(BaseModel):
    customer_id: str
    channel: str                      # "web" | "gmail" | "whatsapp"
    message: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None


class AgentResponse(BaseModel):
    customer_id: str
    channel: str
    response: str
    intent: str                       # detected intent (product, pricing, refund, …)
    escalated: bool = False           # True when routed to a human queue
    source: str = "claude"            # "escalation" | "docs" | "claude" | "fallback"
    timestamp: datetime = None

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data)


# ── /message endpoint ────────────────────────────────────────────────────────

class MessageRequest(BaseModel):
    """Input for POST /api/message."""
    customer_id: str
    channel:     Literal["email", "whatsapp", "web"]
    message:     str

    @field_validator("customer_id")
    @classmethod
    def customer_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("customer_id must not be empty")
        return v.strip()

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty")
        return v.strip()


class MessageResponse(BaseModel):
    """Output for POST /api/message — matches simple_agent.run_agent() return dict."""
    response:          str
    intent:            str
    escalated:         bool
    source:            str            # docs | escalation | ai | acknowledgment
    priority:          str = "low"    # low | medium | high
    escalation_reason: str = ""       # pricing | refund | legal | angry | negative_sentiment | ""
    ticket_id:         Optional[int] = None  # set when escalated and DB is available


# ── Existing / webhook models ─────────────────────────────────────────────────

class Customer(BaseModel):
    id: Optional[int] = None
    name: str
    email: str
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
