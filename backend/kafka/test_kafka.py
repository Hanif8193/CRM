"""
Kafka Integration Test — Flowdesk CRM
=======================================
Tests the full Kafka pipeline for lead events:

    1. Connects to Kafka and verifies the broker is reachable.
    2. Publishes a sample ``crm.leads.created`` event.
    3. Consumes the event back from the topic.
    4. Verifies the payload round-trips correctly.
    5. Calls ``add_lead()`` end-to-end and checks the LeadResult.

Run:
    cd backend
    python kafka/test_kafka.py

Requirements:
    - Kafka must be running on KAFKA_BOOTSTRAP_SERVERS (default localhost:9092)
    - .env must be loaded (Twilio + Gmail credentials for delivery tests)
    - pip install aiokafka
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime, timezone

# Allow imports from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# ── ANSI colours ─────────────────────────────────────────────────────────────
GR = "\033[92m"; RD = "\033[91m"; YL = "\033[93m"; CY = "\033[96m"; R = "\033[0m"; B = "\033[1m"
def ok(msg):   print(f"  {GR}{B}✓{R} {msg}")
def fail(msg): print(f"  {RD}{B}✗{R} {msg}")
def info(msg): print(f"  {CY}→{R} {msg}")
def warn(msg): print(f"  {YL}!{R} {msg}")


KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TEST_TOPIC    = "crm.leads.created"
TEST_LEAD     = {
    "id":         9999,
    "name":       "Test Lead",
    "phone":      "+923001234567",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "event":      "lead.created",
}

results: dict[str, bool] = {}


# ═════════════════════════════════════════════════════════════════════════════
# Test helpers
# ═════════════════════════════════════════════════════════════════════════════

async def test_broker_connection() -> bool:
    """Verify Kafka broker is reachable."""
    print(f"\n{B}[1] Broker connection{R}")
    try:
        from aiokafka.admin import AIOKafkaAdminClient
        client = AIOKafkaAdminClient(bootstrap_servers=KAFKA_SERVERS)
        await client.start()
        await client.close()
        ok(f"Kafka broker reachable at {KAFKA_SERVERS}")
        return True
    except Exception as exc:
        fail(f"Cannot reach Kafka at {KAFKA_SERVERS}: {exc}")
        info("Start Kafka:  docker-compose up kafka -d")
        return False


async def test_publish_lead_event() -> bool:
    """Publish a test lead event and verify it's acknowledged."""
    print(f"\n{B}[2] Publish lead event{R}")
    try:
        from kafka.producer import init_producer, publish_lead_event, close_producer
        await init_producer()
        result = await publish_lead_event(TEST_LEAD)
        await close_producer()

        if result:
            ok(f"Event published to {TEST_TOPIC}  lead_id={TEST_LEAD['id']}")
        else:
            fail("publish_lead_event returned False (check producer logs)")
        return result
    except Exception as exc:
        fail(f"Publish failed: {exc}")
        return False


async def test_consume_lead_event() -> bool:
    """Consume one message from the test topic and validate the payload."""
    print(f"\n{B}[3] Consume lead event{R}")
    try:
        from aiokafka import AIOKafkaConsumer

        consumer = AIOKafkaConsumer(
            TEST_TOPIC,
            bootstrap_servers=KAFKA_SERVERS,
            group_id="crm-test-validator",
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
            consumer_timeout_ms=8_000,   # wait up to 8 s
        )
        await asyncio.wait_for(consumer.start(), timeout=10)
        info("Waiting up to 8s for a message on the topic...")

        received = None
        try:
            async for msg in consumer:
                received = msg.value
                break   # take the first message
        except Exception:
            pass        # consumer_timeout_ms elapsed — no message
        finally:
            await consumer.stop()

        if received is None:
            warn("No message received within timeout — did test [2] succeed?")
            return False

        # Validate key fields
        ok(f"Message received  event={received.get('event')}  id={received.get('id')}")
        checks = [
            ("event",      "lead.created"),
            ("id",         TEST_LEAD["id"]),
            ("name",       TEST_LEAD["name"]),
            ("phone",      TEST_LEAD["phone"]),
        ]
        passed = True
        for field, expected in checks:
            if received.get(field) == expected:
                ok(f"  {field} = {expected}")
            else:
                fail(f"  {field}: expected={expected!r}  got={received.get(field)!r}")
                passed = False
        return passed

    except Exception as exc:
        fail(f"Consume failed: {exc}")
        return False


async def test_add_lead_integration() -> bool:
    """
    End-to-end test: call add_lead() and check the LeadResult.
    This also tests DB persistence and the Kafka bridge in lead_service.
    """
    print(f"\n{B}[4] add_lead() end-to-end{R}")
    try:
        from database.connection import init_db
        init_db()

        from services.lead_service import add_lead
        result = add_lead("Integration Test", "+923009999999")

        ok(f"Lead saved  lead_id={result.lead_id}")
        if result.kafka_queued:
            ok("Kafka event queued")
        elif result.message_sid:
            warn(f"Kafka unavailable — direct WhatsApp SID={result.message_sid}")
        else:
            warn(f"Neither Kafka nor WhatsApp succeeded: {result.error}")

        return result.success

    except Exception as exc:
        fail(f"add_lead() raised: {exc}")
        return False


async def test_error_logging() -> bool:
    """Verify that failed publishes are written to kafka_errors (DB test)."""
    print(f"\n{B}[5] kafka_errors DB logging{R}")
    try:
        from database.connection import init_db, get_conn, is_db_available
        init_db()
        if not is_db_available():
            warn("DB not available — skipping error-log test")
            return True   # not a failure

        from kafka.producer import _log_error_to_db
        await _log_error_to_db("test.topic", {"test": True}, "unit-test error")

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM kafka_errors WHERE topic = %s",
                    ("test.topic",),
                )
                count = cur.fetchone()[0]

        if count > 0:
            ok(f"Error row written to kafka_errors (total rows for test.topic: {count})")
            return True
        else:
            fail("Row was not found in kafka_errors after insert")
            return False

    except Exception as exc:
        fail(f"Error logging test failed: {exc}")
        return False


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

async def main():
    print(f"\n{B}{CY}{'═'*60}{R}")
    print(f"{B}{CY}  Flowdesk CRM — Kafka Integration Tests{R}")
    print(f"{B}{CY}  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{R}")
    print(f"{B}{CY}{'═'*60}{R}")

    # Run tests sequentially (each may depend on the previous)
    tests = [
        ("Broker connection",     test_broker_connection),
        ("Publish lead event",    test_publish_lead_event),
        ("Consume lead event",    test_consume_lead_event),
        ("add_lead() end-to-end", test_add_lead_integration),
        ("kafka_errors logging",  test_error_logging),
    ]

    passed = 0
    for name, fn in tests:
        try:
            result = await fn()
        except Exception as exc:
            result = False
            fail(f"Unexpected exception in '{name}': {exc}")
        results[name] = result
        if result:
            passed += 1

    # Summary
    total = len(tests)
    print(f"\n{B}{'─'*60}{R}")
    print(f"{B}Results: {GR if passed == total else YL}{passed}/{total} passed{R}\n")
    for name, result in results.items():
        icon = f"{GR}✓{R}" if result else f"{RD}✗{R}"
        print(f"  {icon}  {name}")

    print()
    if passed == total:
        print(f"{GR}{B}All tests passed — Kafka pipeline is working!{R}")
    else:
        print(f"{YL}{B}Some tests failed. Check Kafka is running and .env is configured.{R}")
        print(f"\nStart Kafka:  {CY}docker-compose up kafka zookeeper -d{R}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
