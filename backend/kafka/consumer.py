"""
Kafka Consumer Worker — Flowdesk CRM
======================================
Runs two concurrent consumer loops in a single process:

    Loop 1 — ``fte.tickets.incoming``
        Reads raw customer messages → AI agent → publishes reply to
        ``fte.responses.outgoing``.

    Loop 2 — ``crm.leads.created``
        Reads new-lead events → sends WhatsApp welcome (Twilio) →
        sends Gmail notification → writes audit row to ``lead_events``.

Error strategy
--------------
* Failed processing does NOT commit the offset — Kafka will redeliver.
* After MAX_PROCESSING_RETRIES consecutive failures the message is
  skipped (offset committed) and the error written to ``kafka_errors``.
* WhatsApp / Gmail failures are non-fatal: the audit row records what
  succeeded and what failed.

Run as a standalone worker (separate from the FastAPI server):
    cd backend
    python -m kafka.consumer

Scale horizontally:
    docker-compose up --scale kafka-worker=3
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running as __main__ from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import KAFKA_BOOTSTRAP_SERVERS
from kafka.producer import (
    init_producer,
    close_producer,
    publish_outgoing,
    _log_error_to_db,
)
from logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

# ── Topics ────────────────────────────────────────────────────────────────────
TOPIC_INCOMING  = "fte.tickets.incoming"
TOPIC_LEADS     = "crm.leads.created"

# ── Consumer groups ───────────────────────────────────────────────────────────
GROUP_AGENT = os.getenv("KAFKA_CONSUMER_GROUP",       "crm-agent-workers")
GROUP_LEADS = os.getenv("KAFKA_LEADS_CONSUMER_GROUP", "crm-lead-processors")

# ── Retry / back-off ──────────────────────────────────────────────────────────
MAX_PROCESSING_RETRIES = 3
RETRY_BASE_DELAY       = 2.0   # seconds

# ── Graceful shutdown ─────────────────────────────────────────────────────────
_running = True


def _handle_signal(sig, _frame):
    """Handle SIGINT / SIGTERM — let the current message finish then exit."""
    global _running
    log.info("[Consumer] Signal %s received — shutting down gracefully", sig)
    _running = False


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _make_consumer(topic: str, group_id: str):
    """
    Build and return an AIOKafkaConsumer for a single topic.

    Args:
        topic:    Kafka topic name to subscribe to.
        group_id: Consumer-group ID for coordinated partition assignment.

    Returns:
        Configured AIOKafkaConsumer instance (not yet started).

    Raises:
        ImportError: if aiokafka is not installed.
    """
    from aiokafka import AIOKafkaConsumer
    return AIOKafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,       # manual commit after successful processing
        session_timeout_ms=30_000,
        heartbeat_interval_ms=10_000,
        max_poll_interval_ms=300_000,   # 5 min — allow slow AI/WhatsApp calls
    )


async def _commit_with_retry(consumer, retries: int = 3) -> None:
    """Commit offset with up to ``retries`` attempts."""
    for attempt in range(1, retries + 1):
        try:
            await consumer.commit()
            return
        except Exception as exc:
            log.warning("[Consumer] Commit failed (attempt %d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                await asyncio.sleep(1)


# ═════════════════════════════════════════════════════════════════════════════
# Loop 1: incoming customer messages → AI agent
# ═════════════════════════════════════════════════════════════════════════════

async def _process_incoming(data: dict[str, Any]) -> None:
    """
    Run the AI agent on one inbound customer message and publish the reply.

    This is the core CRM pipeline:
        raw message → agent → response topic

    Args:
        data: Deserialized Kafka message value with keys
              ``customer_id``, ``channel``, ``message``.
    """
    from agent.simple_agent import run_agent

    customer_id = data.get("customer_id", "unknown")
    channel     = data.get("channel", "web")
    message     = data.get("message", "")

    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_agent(
            customer_message=message,
            customer_id=customer_id,
            channel=channel,
        ),
    )

    await publish_outgoing(
        customer_id=customer_id,
        response=result["response"],
        intent=result["intent"],
        escalated=result["escalated"],
        source=result.get("source", ""),
    )

    log.info(
        "[Consumer/Agent] customer=%s intent=%s escalated=%s",
        customer_id, result["intent"], result["escalated"],
    )


async def consume_incoming() -> None:
    """
    Consumer loop for ``fte.tickets.incoming``.

    Continuously reads messages, runs the AI agent, and publishes replies.
    Commits offset only on success so failed messages are redelivered.
    After MAX_PROCESSING_RETRIES failures the message is dead-lettered.
    """
    try:
        consumer = _make_consumer(TOPIC_INCOMING, GROUP_AGENT)
    except ImportError:
        log.error("[Consumer] aiokafka not installed — run: pip install aiokafka")
        return

    await consumer.start()
    log.info("[Consumer/Agent] Started — topic=%s group=%s", TOPIC_INCOMING, GROUP_AGENT)

    fail_count = 0
    try:
        async for msg in consumer:
            if not _running:
                break

            data = msg.value
            try:
                await _process_incoming(data)
                await _commit_with_retry(consumer)
                fail_count = 0  # reset on success

            except Exception as exc:
                fail_count += 1
                log.error(
                    "[Consumer/Agent] Processing failed (consecutive=%d) offset=%d: %s",
                    fail_count, msg.offset, exc, exc_info=True,
                )
                if fail_count >= MAX_PROCESSING_RETRIES:
                    log.error("[Consumer/Agent] Dead-lettering message at offset=%d", msg.offset)
                    await _log_error_to_db(TOPIC_INCOMING, data, str(exc))
                    await _commit_with_retry(consumer)
                    fail_count = 0
                else:
                    await asyncio.sleep(RETRY_BASE_DELAY * fail_count)

    finally:
        await consumer.stop()
        log.info("[Consumer/Agent] Stopped")


# ═════════════════════════════════════════════════════════════════════════════
# Loop 2: lead created events → WhatsApp + Gmail + DB audit
# ═════════════════════════════════════════════════════════════════════════════

async def _send_whatsapp_for_lead(name: str, phone: str) -> str | None:
    """
    Send a WhatsApp welcome message to a new lead via Twilio.

    Falls back to Meta Cloud API if WHATSAPP_API_TOKEN is set and Twilio is not.

    Args:
        name:  Lead's full name.
        phone: E.164 phone number, e.g. '+923001234567'.

    Returns:
        Twilio message SID on success, None on failure.
    """
    welcome = (
        f"Hello {name}, welcome to Flowdesk! 🎉\n"
        "Our team will reach out to you shortly. "
        "Reply anytime if you have questions."
    )

    # Try Twilio first
    try:
        from channels.whatsapp_twilio import send_whatsapp_message
        sid = send_whatsapp_message(phone, welcome)
        log.info("[Consumer/Lead] WhatsApp sent via Twilio → %s SID=%s", phone, sid)
        return sid
    except Exception as twilio_exc:
        log.warning("[Consumer/Lead] Twilio failed: %s — trying Meta API", twilio_exc)

    # Fallback: Meta Cloud API
    try:
        from channels.whatsapp import send_whatsapp_reply
        send_whatsapp_reply(phone, welcome)
        log.info("[Consumer/Lead] WhatsApp sent via Meta API → %s", phone)
        return "meta-api"
    except Exception as meta_exc:
        log.error("[Consumer/Lead] Both WhatsApp methods failed: %s", meta_exc)
        return None


async def _send_email_for_lead(name: str, phone: str, lead_id: int) -> bool:
    """
    Send a Gmail notification to the CRM team about a new lead.

    Reads NOTIFY_EMAIL from .env; skips silently if not set.

    Args:
        name:    Lead's full name.
        phone:   Lead's phone number.
        lead_id: Database ID of the lead row.

    Returns:
        True if email was sent, False otherwise.
    """
    notify_email = os.getenv("NOTIFY_EMAIL", "")
    if not notify_email:
        log.debug("[Consumer/Lead] NOTIFY_EMAIL not set — skipping email")
        return False

    subject = f"New Lead #{lead_id}: {name}"
    body = (
        f"A new lead has been registered in Flowdesk CRM.\n\n"
        f"  Name   : {name}\n"
        f"  Phone  : {phone}\n"
        f"  Lead ID: {lead_id}\n"
        f"  Time   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "A WhatsApp welcome message has been sent automatically."
    )

    try:
        from channels.gmail import send_gmail_reply
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: send_gmail_reply(
                to_email=notify_email,
                subject=subject,
                body=body,
            ),
        )
        log.info("[Consumer/Lead] Email notification sent → %s", notify_email)
        return True
    except Exception as exc:
        log.error("[Consumer/Lead] Email notification failed: %s", exc)
        return False


def _audit_lead_event(
    lead_id:      int,
    name:         str,
    phone:        str,
    whatsapp_sid: str | None,
    email_sent:   bool,
    error:        str | None = None,
) -> None:
    """
    Write an audit row to ``lead_events`` for observability.

    Args:
        lead_id:      Database ID of the lead.
        name:         Lead's full name.
        phone:        Lead's phone number.
        whatsapp_sid: Twilio SID or 'meta-api' on success, None on failure.
        email_sent:   True if the Gmail notification was delivered.
        error:        Error description if processing partially failed.
    """
    try:
        from database.connection import get_conn, is_db_available
        if not is_db_available():
            log.debug("[Consumer/Lead] DB unavailable — skipping audit log")
            return
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lead_events
                        (lead_id, name, phone, whatsapp_sid, email_sent, error)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (lead_id, name, phone, whatsapp_sid, email_sent, error),
                )
        log.debug("[Consumer/Lead] Audit row written for lead_id=%d", lead_id)
    except Exception as exc:
        log.error("[Consumer/Lead] Audit log failed: %s", exc)


async def _process_lead_event(data: dict[str, Any]) -> None:
    """
    Process one ``crm.leads.created`` event end-to-end.

    Steps:
        1. Extract lead fields from the Kafka payload.
        2. Send WhatsApp welcome message (Twilio → Meta API fallback).
        3. Send Gmail notification to the CRM team.
        4. Write audit row to ``lead_events``.

    Args:
        data: Deserialized event payload from ``crm.leads.created``.
    """
    lead_id = int(data.get("id", 0))
    name    = data.get("name", "")
    phone   = data.get("phone", "")

    log.info("[Consumer/Lead] Processing lead_id=%d name=%s phone=%s", lead_id, name, phone)

    # Run WhatsApp and Email concurrently
    whatsapp_task = asyncio.create_task(_send_whatsapp_for_lead(name, phone))
    email_task    = asyncio.create_task(_send_email_for_lead(name, phone, lead_id))

    whatsapp_sid, email_sent = await asyncio.gather(
        whatsapp_task, email_task, return_exceptions=False
    )

    errors = []
    if whatsapp_sid is None:
        errors.append("WhatsApp delivery failed")
    if not email_sent:
        errors.append("Email notification skipped or failed")

    _audit_lead_event(
        lead_id=lead_id,
        name=name,
        phone=phone,
        whatsapp_sid=whatsapp_sid,
        email_sent=email_sent,
        error="; ".join(errors) if errors else None,
    )

    log.info(
        "[Consumer/Lead] Done lead_id=%d whatsapp=%s email=%s",
        lead_id, whatsapp_sid or "FAILED", email_sent,
    )


async def consume_leads() -> None:
    """
    Consumer loop for ``crm.leads.created``.

    For each event: send WhatsApp + Gmail concurrently, then audit to DB.
    Commits offset only after all three steps finish (or are confirmed
    non-fatal). Dead-letters after MAX_PROCESSING_RETRIES failures.
    """
    try:
        consumer = _make_consumer(TOPIC_LEADS, GROUP_LEADS)
    except ImportError:
        log.error("[Consumer] aiokafka not installed — run: pip install aiokafka")
        return

    await consumer.start()
    log.info("[Consumer/Lead] Started — topic=%s group=%s", TOPIC_LEADS, GROUP_LEADS)

    fail_count = 0
    try:
        async for msg in consumer:
            if not _running:
                break

            data = msg.value
            try:
                await _process_lead_event(data)
                await _commit_with_retry(consumer)
                fail_count = 0

            except Exception as exc:
                fail_count += 1
                log.error(
                    "[Consumer/Lead] Failed (consecutive=%d) offset=%d: %s",
                    fail_count, msg.offset, exc, exc_info=True,
                )
                if fail_count >= MAX_PROCESSING_RETRIES:
                    log.error("[Consumer/Lead] Dead-lettering lead event at offset=%d", msg.offset)
                    await _log_error_to_db(TOPIC_LEADS, data, str(exc))
                    await _commit_with_retry(consumer)
                    fail_count = 0
                else:
                    await asyncio.sleep(RETRY_BASE_DELAY * fail_count)

    finally:
        await consumer.stop()
        log.info("[Consumer/Lead] Stopped")


# ═════════════════════════════════════════════════════════════════════════════
# Entry point — run both consumer loops concurrently
# ═════════════════════════════════════════════════════════════════════════════

async def run_all_consumers() -> None:
    """
    Start the Kafka producer then run both consumer loops concurrently.

    Both loops share one producer instance for outgoing publishes.
    Either loop can be disabled by removing it from the gather call.
    """
    await init_producer()
    log.info("[Consumer] Starting all consumer loops")

    try:
        await asyncio.gather(
            consume_incoming(),   # fte.tickets.incoming → AI agent
            consume_leads(),      # crm.leads.created  → WhatsApp + Gmail + audit
        )
    finally:
        await close_producer()
        log.info("[Consumer] All consumers stopped")


if __name__ == "__main__":
    asyncio.run(run_all_consumers())
