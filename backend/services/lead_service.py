"""
Lead Management Service — Flowdesk CRM
========================================
Responsibilities
----------------
1. Validate and persist a new lead (PostgreSQL when available, in-memory fallback).
2. Publish a ``crm.leads.created`` Kafka event so the consumer can trigger
   WhatsApp + Gmail asynchronously — decoupling the API from delivery latency.
3. Provide a sync-friendly wrapper (``add_lead``) that works from Flask,
   Streamlit, or any synchronous context by bridging into the async Kafka call.

Event flow
----------
  caller → add_lead(name, phone)
         → _persist_lead()         — DB or in-memory
         → _fire_kafka_event()     — crm.leads.created (async, best-effort)
         → LeadResult              — returned to caller immediately

The WhatsApp message and email are handled entirely by the Kafka consumer
(``kafka/consumer.py``). If Kafka is unavailable the lead is still saved and
a direct WhatsApp send is attempted as a synchronous fallback.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from twilio.base.exceptions import TwilioRestException

log = logging.getLogger(__name__)

# ── In-memory fallback (used when DB is unavailable) ─────────────────────────
_LEADS: list[dict] = []


@dataclass
class LeadResult:
    """
    Outcome of an ``add_lead`` call.

    Attributes:
        success:      True if the lead was saved (regardless of Kafka/WhatsApp).
        lead_id:      Database or in-memory ID assigned to the lead.
        kafka_queued: True if the Kafka event was acknowledged.
        message_sid:  Twilio SID if a direct (fallback) WhatsApp was sent.
        error:        Description of any non-fatal failure.
    """
    success:      bool
    lead_id:      Optional[int]  = None
    kafka_queued: bool           = False
    message_sid:  Optional[str]  = None
    error:        Optional[str]  = None


# ═════════════════════════════════════════════════════════════════════════════
# Persistence
# ═════════════════════════════════════════════════════════════════════════════

def _persist_lead(name: str, phone: str) -> dict:
    """
    Save the lead to PostgreSQL. Falls back to the in-memory list when the
    database is unavailable so the API never returns a 500 on a DB outage.

    Args:
        name:  Lead's full name (already stripped).
        phone: E.164 phone number (already stripped).

    Returns:
        Lead dict with keys: ``id``, ``name``, ``phone``, ``created_at``.
    """
    created_at = datetime.now(timezone.utc).isoformat()

    # Try database first
    try:
        from database.connection import get_conn, is_db_available
        if is_db_available():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO leads (name, phone)
                        VALUES (%s, %s)
                        RETURNING id, created_at
                        """,
                        (name, phone),
                    )
                    row = cur.fetchone()
                    lead = {
                        "id":         row[0],
                        "name":       name,
                        "phone":      phone,
                        "created_at": row[1].isoformat(),
                    }
                    log.info("[LeadService] Persisted to DB: lead_id=%d", lead["id"])
                    return lead
    except Exception as exc:
        log.warning("[LeadService] DB insert failed — using in-memory store: %s", exc)

    # In-memory fallback
    lead = {
        "id":         len(_LEADS) + 1,
        "name":       name,
        "phone":      phone,
        "created_at": created_at,
    }
    _LEADS.append(lead)
    log.info("[LeadService] Saved in-memory: lead_id=%d", lead["id"])
    return lead


# ═════════════════════════════════════════════════════════════════════════════
# Kafka event publishing
# ═════════════════════════════════════════════════════════════════════════════

def _fire_kafka_event(lead: dict) -> bool:
    """
    Publish a ``crm.leads.created`` event to Kafka.

    Bridges from a synchronous call site into the async Kafka producer.
    Works in plain threads (Flask / Streamlit) by creating a new event loop
    when there is no running one, and by scheduling a task when there is.

    Args:
        lead: Lead dict (id, name, phone, created_at).

    Returns:
        True if the event was acknowledged by Kafka, False otherwise.
    """
    from kafka.producer import init_producer, publish_lead_event

    async def _async_publish():
        await init_producer()
        return await publish_lead_event(lead)

    # Case 1: no running event loop (Flask, Streamlit, CLI)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        if not loop.is_running():
            return loop.run_until_complete(_async_publish())
    except RuntimeError:
        # loop was closed or didn't exist — create a fresh one
        return asyncio.run(_async_publish())

    # Case 2: already inside an async context (FastAPI)
    # Schedule as a fire-and-forget background task
    asyncio.ensure_future(_async_publish())
    log.debug("[LeadService] Kafka event scheduled as background task")
    return True   # optimistic — will be True unless producer is None


# ═════════════════════════════════════════════════════════════════════════════
# Direct WhatsApp fallback (when Kafka is unavailable)
# ═════════════════════════════════════════════════════════════════════════════

def _direct_whatsapp(name: str, phone: str) -> Optional[str]:
    """
    Send a WhatsApp welcome message directly (bypassing Kafka).

    Used only when Kafka is unavailable so the customer still receives a
    message even if event-driven processing is down.

    Args:
        name:  Lead's name for the greeting.
        phone: E.164 phone number.

    Returns:
        Twilio SID on success, None on failure.
    """
    welcome = (
        f"Hello {name}, thanks for contacting us! 🎉\n"
        "Our team will reach you shortly."
    )
    try:
        from channels.whatsapp_twilio import send_whatsapp_message
        sid = send_whatsapp_message(phone, welcome)
        log.info("[LeadService] Direct WhatsApp sent SID=%s", sid)
        return sid
    except (ValueError, TwilioRestException) as exc:
        log.warning("[LeadService] Direct WhatsApp failed: %s", exc)
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════

def add_lead(name: str, phone: str) -> LeadResult:
    """
    Create a new lead and trigger all downstream actions.

    Workflow:
        1. Persist lead to DB (falls back to in-memory).
        2. Publish ``crm.leads.created`` Kafka event.
           → Consumer handles WhatsApp + Gmail + audit asynchronously.
        3. If Kafka is not available, send WhatsApp directly as a fallback.

    Args:
        name:  Full name of the lead.
        phone: WhatsApp number in E.164 format, e.g. '+923001234567'.

    Returns:
        LeadResult indicating what succeeded and what (if anything) failed.
    """
    name  = name.strip()
    phone = phone.strip()

    # Step 1 — Persist
    lead = _persist_lead(name, phone)

    # Step 2 — Kafka event (WhatsApp + Gmail handled by consumer)
    kafka_queued = False
    try:
        kafka_queued = _fire_kafka_event(lead)
        if kafka_queued:
            log.info(
                "[LeadService] lead_id=%d queued for Kafka processing",
                lead["id"],
            )
            return LeadResult(
                success=True,
                lead_id=lead["id"],
                kafka_queued=True,
            )
    except Exception as exc:
        log.warning("[LeadService] Kafka unavailable: %s — falling back to direct send", exc)

    # Step 3 — Fallback: direct WhatsApp when Kafka failed
    sid   = _direct_whatsapp(name, phone)
    error = None if sid else "WhatsApp delivery failed and Kafka unavailable"

    return LeadResult(
        success=True,
        lead_id=lead["id"],
        kafka_queued=False,
        message_sid=sid,
        error=error,
    )


def get_all_leads() -> list[dict]:
    """
    Return all leads.

    Queries PostgreSQL when available; falls back to the in-memory list.

    Returns:
        List of lead dicts ordered by creation time (newest first).
    """
    try:
        from database.connection import get_conn, is_db_available
        if is_db_available():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, name, phone, created_at FROM leads ORDER BY id DESC"
                    )
                    cols = ["id", "name", "phone", "created_at"]
                    rows = cur.fetchall()
            return [
                {**dict(zip(cols, r)), "created_at": r[3].isoformat()}
                for r in rows
            ]
    except Exception as exc:
        log.warning("[LeadService] DB read failed — returning in-memory list: %s", exc)

    return list(reversed(_LEADS))
