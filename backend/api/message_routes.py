"""
POST   /api/message                  — main AI agent endpoint
GET    /api/memory/{customer_id}     — in-memory conversation history
DELETE /api/memory/{customer_id}     — clear memory (testing / GDPR)
GET    /api/tickets/{customer_id}    — ticket history from PostgreSQL
"""

from fastapi import APIRouter, HTTPException
from models.schemas import MessageRequest, MessageResponse
from agent.simple_agent import run_agent, get_memory, _store
from database.connection import get_conn, is_db_available
import database.operations as db

router = APIRouter()

# ── Fallback used when run_agent itself raises an exception ──────────────────
_ERROR_RESPONSE = MessageResponse(
    response=(
        "I'm having trouble responding right now. "
        "A human support agent will be with you shortly."
    ),
    intent="error",
    escalated=True,
    source="fallback",
)


# ── POST /api/message ─────────────────────────────────────────────────────────

@router.post(
    "/message",
    response_model=MessageResponse,
    summary="Send a customer message to the AI agent",
    response_description="Agent reply with intent, escalation flag, and source",
)
def post_message(req: MessageRequest) -> MessageResponse:
    """
    Main endpoint. Accepts a customer message on any supported channel,
    runs the full agent decision tree (acknowledgment → escalation → docs → AI),
    and returns a formatted response.

    Persists each turn to PostgreSQL when the DB is available.
    Escalated responses automatically open/update a ticket.
    """
    try:
        result = run_agent(
            customer_message = req.message,
            customer_id      = req.customer_id,
            channel          = req.channel,
        )
    except Exception as exc:
        print(
            f"[AGENT] customer={req.customer_id:<16} "
            f"channel={req.channel:<10} "
            f"source=error        "
            f"error={exc}"
        )
        return _ERROR_RESPONSE

    ticket_id = None

    # ── Persist to DB (best-effort — never block the response) ────────────────
    if is_db_available():
        try:
            with get_conn() as conn:
                db.ensure_customer(conn, req.customer_id)
                db.save_message(
                    conn,
                    customer_id = req.customer_id,
                    channel     = req.channel,
                    message     = req.message,
                    response    = result["response"],
                    source      = result["source"],
                )
                if result.get("escalated") and result.get("escalation_reason"):
                    ticket_id = db.escalate_ticket(
                        conn,
                        customer_id = req.customer_id,
                        priority    = result.get("priority", "low"),
                        reason      = result.get("escalation_reason", ""),
                    )
        except Exception as db_exc:
            print(f"[DB] write failed for customer={req.customer_id}: {db_exc}")

    # ── Enrich escalation response with ticket info ───────────────────────────
    if result.get("escalated") and result.get("escalation_reason"):
        ticket_line = (
            f"\n\nTicket ID: #{ticket_id}"
            if ticket_id
            else ""
        )
        priority_label = result.get("priority", "low").capitalize()
        result["response"] = (
            f"{result['response']}"
            f"{ticket_line}"
            f"\nPriority: {priority_label}"
        )
        if ticket_id:
            print(
                f"[TICKET] customer={req.customer_id:<16} "
                f"ticket=#{ticket_id:<6} "
                f"priority={priority_label:<8} "
                f"reason={result.get('escalation_reason', '')}"
            )

    return MessageResponse(ticket_id=ticket_id, **result)


# ── GET /api/memory/{customer_id} ────────────────────────────────────────────

@router.get(
    "/memory/{customer_id}",
    summary="Retrieve conversation memory for a customer",
)
def get_customer_memory(customer_id: str) -> dict:
    """
    Returns the full in-memory record for the given customer_id:
    - messages  : [{role, text, ts}, …]
    - topic     : last matched doc section or intent
    - sentiment : positive | negative | neutral
    - channel   : last channel used
    - turns     : number of completed exchanges
    - last_seen : ISO-8601 UTC timestamp

    Returns an empty object {} when the customer has no history.
    """
    return get_memory(customer_id)


# ── DELETE /api/memory/{customer_id} ─────────────────────────────────────────

@router.delete(
    "/memory/{customer_id}",
    summary="Clear conversation memory for a customer",
)
def delete_customer_memory(customer_id: str) -> dict:
    """
    Removes all stored conversation history for a customer.
    Useful for testing and for GDPR right-to-erasure requests.
    Returns 404 when the customer_id is not found.
    """
    if customer_id not in _store:
        raise HTTPException(
            status_code=404,
            detail=f"No memory found for customer_id '{customer_id}'",
        )
    del _store[customer_id]
    return {"deleted": True, "customer_id": customer_id}


# ── GET /api/tickets/{customer_id} ───────────────────────────────────────────

@router.get(
    "/tickets/{customer_id}",
    summary="Get ticket history for a customer",
)
def get_customer_tickets(customer_id: str) -> dict:
    """
    Returns all tickets for a customer from PostgreSQL, newest first.
    Each ticket includes: id, customer_id, status, created_at.

    Returns 503 when the database is not available.
    Returns an empty list when the customer has no tickets.
    """
    if not is_db_available():
        raise HTTPException(
            status_code=503,
            detail="Database is not available",
        )
    try:
        with get_conn() as conn:
            tickets = db.get_tickets(conn, customer_id)
        return {"customer_id": customer_id, "tickets": tickets}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
