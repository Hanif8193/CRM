"""
Database operations for the CRM agent.

All functions accept a psycopg2 connection and are intentionally thin wrappers
around SQL so business logic stays in the routes/agent layer.

Usage:
    from database.connection import get_conn
    from database import operations as db

    with get_conn() as conn:
        db.ensure_customer(conn, customer_id)
        session_id = db.get_or_create_conversation(conn, customer_id, "web")
        db.save_message(conn, customer_id, "web", message, response, "docs", session_id)
        ticket_id = db.escalate_ticket(conn, customer_id, priority="high", reason="refund")
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

# A conversation session expires after this many minutes of inactivity
_SESSION_TIMEOUT_MINUTES = 30


# ── customers ────────────────────────────────────────────────────────────────

def ensure_customer(conn, customer_id: str) -> None:
    """Insert the customer if it does not already exist (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO customers (customer_id)
            VALUES (%s)
            ON CONFLICT (customer_id) DO NOTHING
            """,
            (customer_id,),
        )


# ── conversations ─────────────────────────────────────────────────────────────

def get_or_create_conversation(conn, customer_id: str, channel: str) -> str:
    """
    Return the session_id for the customer's active conversation on the given
    channel, or create a new one if none exists or the last one has timed out.

    A conversation times out after _SESSION_TIMEOUT_MINUTES of inactivity.
    Returns the session_id string.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_SESSION_TIMEOUT_MINUTES)

    with conn.cursor() as cur:
        # Find an active session (last_active_at within timeout window)
        cur.execute(
            """
            SELECT session_id
            FROM   conversations
            WHERE  customer_id    = %s
              AND  channel        = %s
              AND  last_active_at > %s
            ORDER  BY last_active_at DESC
            LIMIT  1
            """,
            (customer_id, channel, cutoff),
        )
        row = cur.fetchone()

    if row:
        session_id = row[0]
        _touch_conversation(conn, session_id)
        return session_id

    # No active session — create a new one
    return _create_conversation(conn, customer_id, channel)


def _create_conversation(conn, customer_id: str, channel: str) -> str:
    """Create a new conversation row and return its session_id."""
    session_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (session_id, customer_id, channel)
            VALUES (%s, %s, %s)
            """,
            (session_id, customer_id, channel),
        )
    return session_id


def _touch_conversation(conn, session_id: str) -> None:
    """Update last_active_at and increment message_count for an existing session."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE conversations
            SET    last_active_at = NOW(),
                   message_count  = message_count + 1
            WHERE  session_id = %s
            """,
            (session_id,),
        )


def get_conversation_history(conn, session_id: str) -> list[dict]:
    """
    Return all messages in a conversation session, oldest first.
    Each dict has: role ('user'|'assistant'), text, created_at.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT message, response, created_at
            FROM   messages
            WHERE  session_id = %s
            ORDER  BY created_at ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()

    history = []
    for msg, resp, ts in rows:
        history.append({"role": "user",      "text": msg,  "created_at": ts.isoformat()})
        history.append({"role": "assistant",  "text": resp, "created_at": ts.isoformat()})
    return history


# ── messages ─────────────────────────────────────────────────────────────────

def save_message(
    conn,
    customer_id: str,
    channel: str,
    message: str,
    response: str,
    source: str,
    session_id: str | None = None,
) -> int:
    """
    Persist one conversation turn.
    Returns the new message row id.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (customer_id, session_id, channel, message, response, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (customer_id, session_id, channel, message, response, source),
        )
        row = cur.fetchone()
        return row[0]


def get_messages(conn, customer_id: str, limit: int = 50) -> list[dict]:
    """Return the most recent messages for a customer, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, customer_id, session_id, channel, message, response, source, created_at
            FROM   messages
            WHERE  customer_id = %s
            ORDER  BY created_at DESC
            LIMIT  %s
            """,
            (customer_id, limit),
        )
        cols = ["id", "customer_id", "session_id", "channel",
                "message", "response", "source", "created_at"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── tickets ──────────────────────────────────────────────────────────────────

def _row_to_ticket(row: tuple) -> dict:
    return {
        "id":          row[0],
        "customer_id": row[1],
        "status":      row[2],
        "priority":    row[3],
        "reason":      row[4],
        "created_at":  row[5].isoformat(),
    }


def get_open_ticket(conn, customer_id: str) -> dict | None:
    """Return the most recent open/escalated ticket for a customer, or None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, customer_id, status, priority, reason, created_at
            FROM   tickets
            WHERE  customer_id = %s
              AND  status IN ('open', 'escalated')
            ORDER  BY created_at DESC
            LIMIT  1
            """,
            (customer_id,),
        )
        row = cur.fetchone()
        return _row_to_ticket(row) if row else None


def create_ticket(
    conn,
    customer_id: str,
    priority: str = "low",
    reason:   str = "",
) -> int:
    """Open a new ticket. Returns the new ticket row id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tickets (customer_id, status, priority, reason)
            VALUES (%s, 'open', %s, %s)
            RETURNING id
            """,
            (customer_id, priority, reason),
        )
        row = cur.fetchone()
        return row[0]


def escalate_ticket(
    conn,
    customer_id: str,
    priority: str = "low",
    reason:   str = "",
) -> int:
    """
    Mark the most recent open ticket as 'escalated', or create a new one.
    Returns the ticket id.
    """
    existing = get_open_ticket(conn, customer_id)
    if existing:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tickets
                SET    status   = 'escalated',
                       priority = %s,
                       reason   = %s
                WHERE  id = %s
                """,
                (priority, reason, existing["id"]),
            )
        return existing["id"]

    return create_ticket(conn, customer_id, priority=priority, reason=reason)


def get_tickets(conn, customer_id: str) -> list[dict]:
    """Return all tickets for a customer, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, customer_id, status, priority, reason, created_at
            FROM   tickets
            WHERE  customer_id = %s
            ORDER  BY created_at DESC
            """,
            (customer_id,),
        )
        return [_row_to_ticket(r) for r in cur.fetchall()]


def get_all_tickets(conn, limit: int = 100) -> list[dict]:
    """Return all tickets across all customers, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, customer_id, status, priority, reason, created_at
            FROM   tickets
            ORDER  BY created_at DESC
            LIMIT  %s
            """,
            (limit,),
        )
        return [_row_to_ticket(r) for r in cur.fetchall()]


def get_all_conversations(conn, limit: int = 50) -> list[dict]:
    """Return all conversations with metadata, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, customer_id, channel,
                   started_at, last_active_at, message_count
            FROM   conversations
            ORDER  BY last_active_at DESC
            LIMIT  %s
            """,
            (limit,),
        )
        cols = ["session_id", "customer_id", "channel",
                "started_at", "last_active_at", "message_count"]
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(zip(cols, r))
        d["started_at"]     = d["started_at"].isoformat()
        d["last_active_at"] = d["last_active_at"].isoformat()
        result.append(d)
    return result


def update_ticket_status(conn, ticket_id: int, status: str) -> bool:
    """Update a ticket's status. Returns True if a row was updated."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tickets SET status = %s WHERE id = %s",
            (status, ticket_id),
        )
        return cur.rowcount > 0
