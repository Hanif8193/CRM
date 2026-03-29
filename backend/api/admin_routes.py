"""
Admin API routes — internal dashboard endpoints.

GET  /api/admin/tickets                        — all tickets (newest first)
GET  /api/admin/conversations                  — all conversations (newest first)
GET  /api/admin/conversations/{sid}/messages   — messages for one session
PATCH /api/admin/tickets/{ticket_id}/close     — mark a ticket as closed
"""

from fastapi import APIRouter, HTTPException

from database.connection import get_conn, is_db_available
import database.operations as db

router = APIRouter()


def _require_db():
    if not is_db_available():
        raise HTTPException(status_code=503, detail="Database is not available")


@router.get("/tickets", summary="List all tickets")
def list_all_tickets(limit: int = 100) -> dict:
    _require_db()
    try:
        with get_conn() as conn:
            tickets = db.get_all_tickets(conn, limit)
        return {"tickets": tickets, "count": len(tickets)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/conversations", summary="List all conversations")
def list_all_conversations(limit: int = 50) -> dict:
    _require_db()
    try:
        with get_conn() as conn:
            conversations = db.get_all_conversations(conn, limit)
        return {"conversations": conversations, "count": len(conversations)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/conversations/{session_id}/messages",
    summary="Get messages for a conversation session",
)
def get_conversation_messages(session_id: str) -> dict:
    _require_db()
    try:
        with get_conn() as conn:
            messages = db.get_conversation_history(conn, session_id)
        return {"session_id": session_id, "messages": messages}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/tickets/{ticket_id}/close", summary="Close a ticket")
def close_ticket(ticket_id: int) -> dict:
    _require_db()
    try:
        with get_conn() as conn:
            updated = db.update_ticket_status(conn, ticket_id, "closed")
        if not updated:
            raise HTTPException(
                status_code=404,
                detail=f"Ticket #{ticket_id} not found",
            )
        return {"ticket_id": ticket_id, "status": "closed"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
