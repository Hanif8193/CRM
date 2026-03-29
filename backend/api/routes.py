import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from agent.simple_agent import get_metrics
from channels.gmail import handle_gmail_message
from channels.web import handle_web_message
from channels.whatsapp import handle_whatsapp_message
from config import WHATSAPP_APP_SECRET, WHATSAPP_WEBHOOK_VERIFY_TOKEN
from models.schemas import AgentResponse, CustomerMessage

router = APIRouter()


def _verify_whatsapp_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256 HMAC-SHA256 signature.

    Computes the expected HMAC-SHA256 digest of the raw request body using
    WHATSAPP_APP_SECRET and compares it to the value in the header using a
    constant-time comparison to prevent timing attacks.

    Args:
        raw_body: Raw request body bytes before JSON parsing.
        signature_header: Value of the X-Hub-Signature-256 header.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    if not WHATSAPP_APP_SECRET:
        return False

    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)


@router.post("/chat", response_model=AgentResponse)
def web_chat(message: CustomerMessage):
    """Handle messages from the web chat widget."""
    result = handle_web_message(message.customer_id, message.message)
    return AgentResponse(
        customer_id=message.customer_id,
        channel="web",
        response=result["response"],
        intent=result["intent"],
        escalated=result["escalated"],
        source=result["source"],
    )


@router.get("/webhook/whatsapp", response_class=PlainTextResponse)
def whatsapp_webhook_verify(
    mode:         str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge:    str = Query(alias="hub.challenge"),
) -> str:
    """Webhook verification handshake required by Meta before it delivers events.

    Meta sends GET ?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=<nonce>.
    Respond with the challenge value to confirm ownership of the endpoint.
    """
    if mode != "subscribe" or verify_token != WHATSAPP_WEBHOOK_VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Webhook verification failed.")
    return challenge


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Receive and process WhatsApp messages from Meta webhook.

    Verifies the X-Hub-Signature-256 HMAC-SHA256 signature before parsing
    the payload to ensure the request originates from Meta.
    """
    raw_body  = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not _verify_whatsapp_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")

    try:
        payload     = json.loads(raw_body)
        entry       = payload["entry"][0]
        change      = entry["changes"][0]["value"]
        msg         = change["messages"][0]
        from_number = msg["from"]
        text        = msg["text"]["body"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    result = handle_whatsapp_message(from_number, text)
    return {"status": "ok", "intent": result["intent"], "escalated": result["escalated"]}


@router.post("/webhook/gmail")
def gmail_webhook(payload: dict):
    """Receive Gmail push notifications."""
    sender  = payload.get("from", "")
    subject = payload.get("subject", "")
    body    = payload.get("body", "")

    result = handle_gmail_message(sender, subject, body)
    return {"status": "ok", "intent": result["intent"], "escalated": result["escalated"]}


@router.get("/health")
def health():
    return {"status": "healthy"}


@router.get("/metrics")
def metrics():
    """Live counters: total requests, cache hits, docs used, Claude calls, escalations."""
    data  = get_metrics()
    total = data["total"] or 1  # avoid division by zero
    return {
        **data,
        "cache_hit_rate":  f"{data['cache_hits']  / total * 100:.1f}%",
        "docs_rate":       f"{data['docs']         / total * 100:.1f}%",
        "claude_rate":     f"{data['claude']       / total * 100:.1f}%",
        "escalation_rate": f"{data['escalation']   / total * 100:.1f}%",
        "fallback_rate":   f"{data['fallback']      / total * 100:.1f}%",
    }
