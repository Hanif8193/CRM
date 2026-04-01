"""
Async Kafka Producer — Flowdesk CRM
====================================
Publishes events to four topics:

    fte.tickets.incoming    Raw inbound customer messages (existing)
    fte.responses.outgoing  AI-generated replies           (existing)
    crm.leads.created       New lead created event         (new)
    crm.leads.dlq           Dead-letter queue for retries  (new)

Design principles
-----------------
* Graceful degradation — if Kafka is unavailable the app keeps running;
  failed payloads are logged to the ``kafka_errors`` DB table instead.
* Exactly-once semantics — idempotent producer + acks="all".
* Retry with exponential back-off before giving up and writing to DLQ.
* All public helpers are async and safe to call from any coroutine.

Lifecycle (call from FastAPI lifespan or consumer __main__):
    await init_producer()
    ...
    await close_producer()
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from config import KAFKA_BOOTSTRAP_SERVERS

log = logging.getLogger(__name__)

# ── Topic names ───────────────────────────────────────────────────────────────
TOPIC_INCOMING     = "fte.tickets.incoming"
TOPIC_OUTGOING     = "fte.responses.outgoing"
TOPIC_LEADS        = "crm.leads.created"
TOPIC_LEADS_DLQ    = "crm.leads.dlq"

# ── Retry configuration ───────────────────────────────────────────────────────
MAX_RETRIES        = 3          # attempts before DLQ
RETRY_BASE_DELAY   = 1.0        # seconds (doubles each attempt)

# ── Module-level producer (None when Kafka is unavailable) ───────────────────
_producer = None   # AIOKafkaProducer | None


# ═════════════════════════════════════════════════════════════════════════════
# Lifecycle
# ═════════════════════════════════════════════════════════════════════════════

async def init_producer() -> None:
    """
    Start the global AIOKafkaProducer.

    Safe to call multiple times — reinitialises only when not already running.
    If aiokafka is missing or Kafka is unreachable the function logs a warning
    and leaves ``_producer`` as None so every publish call degrades gracefully.
    """
    global _producer
    if _producer is not None:
        return  # already running

    try:
        from aiokafka import AIOKafkaProducer

        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",               # wait for all in-sync replicas
            enable_idempotence=True,  # exactly-once per partition
            compression_type="gzip",
            request_timeout_ms=15_000,
            retry_backoff_ms=500,
        )
        await _producer.start()
        log.info("[Kafka] Producer started — bootstrap=%s", KAFKA_BOOTSTRAP_SERVERS)

    except ImportError:
        log.warning("[Kafka] aiokafka not installed — publishing disabled")
        _producer = None
    except Exception as exc:
        log.warning("[Kafka] Producer unavailable: %s — continuing without Kafka", exc)
        _producer = None


async def close_producer() -> None:
    """
    Flush pending messages and stop the producer.
    Call once during application shutdown.
    """
    global _producer
    if _producer is not None:
        try:
            await _producer.stop()
            log.info("[Kafka] Producer stopped")
        except Exception as exc:
            log.error("[Kafka] Error stopping producer: %s", exc)
        finally:
            _producer = None


# ═════════════════════════════════════════════════════════════════════════════
# Core publish helper
# ═════════════════════════════════════════════════════════════════════════════

async def _publish(topic: str, key: str, payload: dict[str, Any]) -> bool:
    """
    Send one message to a Kafka topic.

    Retries up to MAX_RETRIES times with exponential back-off.
    On final failure writes the payload to the ``kafka_errors`` DB table
    and attempts to push to the dead-letter topic.

    Args:
        topic:   Target Kafka topic name.
        key:     Partition key (e.g. lead_id or customer_id as string).
        payload: Dict that will be JSON-serialised as the message value.

    Returns:
        True on success, False if all retries failed.
    """
    if _producer is None:
        log.warning("[Kafka] Producer not available — skipping publish to %s", topic)
        await _log_error_to_db(topic, payload, "Producer not initialised")
        return False

    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await _producer.send_and_wait(topic=topic, key=key, value=payload)
            log.debug("[Kafka] → %s  key=%s  attempt=%d", topic, key, attempt)
            return True

        except Exception as exc:
            last_exc = exc
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            log.warning(
                "[Kafka] Publish failed (attempt %d/%d) topic=%s: %s — retry in %.1fs",
                attempt, MAX_RETRIES, topic, exc, delay,
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)

    # All retries exhausted
    log.error("[Kafka] Giving up on topic=%s key=%s after %d attempts", topic, key, MAX_RETRIES)
    await _log_error_to_db(topic, payload, str(last_exc))
    await _send_to_dlq(topic, key, payload)
    return False


async def _send_to_dlq(original_topic: str, key: str, payload: dict) -> None:
    """
    Push a failed message to the dead-letter topic (best-effort).

    The DLQ payload wraps the original so it can be replayed later.
    """
    if _producer is None:
        return
    dlq_payload = {
        "original_topic": original_topic,
        "payload":        payload,
        "failed_at":      datetime.now(timezone.utc).isoformat(),
    }
    try:
        await _producer.send_and_wait(
            topic=TOPIC_LEADS_DLQ, key=key, value=dlq_payload
        )
        log.info("[Kafka] DLQ → %s  key=%s", TOPIC_LEADS_DLQ, key)
    except Exception as exc:
        log.error("[Kafka] DLQ publish also failed: %s", exc)


async def _log_error_to_db(topic: str, payload: dict, error: str) -> None:
    """
    Write a failed Kafka payload to the ``kafka_errors`` table.

    Silently skips if the database is unavailable.
    """
    try:
        from database.connection import get_conn, is_db_available
        if not is_db_available():
            return
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kafka_errors (topic, payload, error_message)
                    VALUES (%s, %s::jsonb, %s)
                    """,
                    (topic, json.dumps(payload, default=str), error),
                )
        log.debug("[Kafka] Error logged to kafka_errors table")
    except Exception as exc:
        log.error("[Kafka] Could not log error to DB: %s", exc)


# ═════════════════════════════════════════════════════════════════════════════
# Public publish helpers
# ═════════════════════════════════════════════════════════════════════════════

async def publish_lead_event(lead: dict[str, Any]) -> bool:
    """
    Publish a ``crm.leads.created`` event for a newly created lead.

    The consumer will react by sending a WhatsApp message, an email
    notification, and writing an audit row to ``lead_events``.

    Args:
        lead: Dict with at minimum ``id``, ``name``, ``phone``,
              and ``created_at`` fields.

    Returns:
        True if the event was acknowledged by Kafka, False otherwise.

    Example::

        await publish_lead_event({
            "id":         1,
            "name":       "Ali Khan",
            "phone":      "+923001234567",
            "created_at": "2026-03-31T10:00:00",
        })
    """
    payload = {
        **lead,
        "event":      "lead.created",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    return await _publish(TOPIC_LEADS, str(lead.get("id", "0")), payload)


async def publish_incoming(customer_id: str, channel: str, message: str) -> bool:
    """
    Publish a raw inbound customer message to ``fte.tickets.incoming``.

    Args:
        customer_id: Customer identifier string.
        channel:     Source channel — ``email``, ``whatsapp``, or ``web``.
        message:     Raw message text from the customer.

    Returns:
        True on success, False if all retries failed.
    """
    payload = {
        "customer_id": customer_id,
        "channel":     channel,
        "message":     message,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    return await _publish(TOPIC_INCOMING, customer_id, payload)


async def publish_outgoing(
    customer_id: str,
    response:    str,
    intent:      str,
    escalated:   bool,
    source:      str = "",
    ticket_id:   Optional[int] = None,
) -> bool:
    """
    Publish an AI-generated reply to ``fte.responses.outgoing``.

    Args:
        customer_id: Customer identifier string.
        response:    Text of the AI reply.
        intent:      Detected intent label.
        escalated:   Whether the ticket was escalated to a human.
        source:      Which subsystem produced the reply (docs/ai/cache…).
        ticket_id:   Database ticket ID if one was created.

    Returns:
        True on success, False if all retries failed.
    """
    payload = {
        "customer_id":  customer_id,
        "response":     response,
        "intent":       intent,
        "escalated":    escalated,
        "source":       source,
        "ticket_id":    ticket_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    return await _publish(TOPIC_OUTGOING, customer_id, payload)
