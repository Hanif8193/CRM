"""
Kafka Consumer Worker — پیغامات Kafka سے پڑھنا اور AI سے پروسیس کرنا

``fte.tickets.incoming`` topic سے پیغامات پڑھتا ہے،
AI agent سے جواب بنواتا ہے،
اور ``fte.responses.outgoing`` پر publish کرتا ہے۔

الگ process کے طور پر چلائیں (FastAPI سرور سے الگ):
    python -m kafka.consumer

یا Docker Compose سے (docker-compose.yml میں kafka-worker service):
    docker-compose up kafka-worker

Horizontal scaling:
    docker-compose up --scale kafka-worker=3
    (ہر worker ایک partition سنبھالتا ہے)
"""

import asyncio   # async/await کے لیے
import json      # JSON deserialize کرنے کے لیے
import logging
import os
import signal    # SIGINT/SIGTERM handle کرنے کے لیے (graceful shutdown)
import sys
from pathlib import Path

# جب بطور __main__ چلیں تو backend/ کو Python path میں شامل کریں
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.simple_agent import run_agent          # AI agent
from config import KAFKA_BOOTSTRAP_SERVERS
from kafka.producer import init_producer, publish_outgoing, close_producer
from logging_config import setup_logging

# logging شروع کریں (consumer کے لیے الگ process ہے)
setup_logging()
log = logging.getLogger(__name__)

# وہ topic جہاں سے پیغامات پڑھیں گے
INCOMING_TOPIC = "fte.tickets.incoming"

# Consumer group ID — ایک ہی group کے workers مل کر topic partition کریں گے
GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP", "crm-agent-workers")

# Graceful shutdown flag — True جب تک چلتے رہیں
_running = True


# ═══════════════════════════════════════════════════════════════════════════════
# Signal Handling — بند ہونے کا اشارہ
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_signal(sig, frame):
    """
    SIGINT (Ctrl+C) یا SIGTERM ملنے پر consumer کو صاف بند کریں۔
    فوری بند نہیں ہوتا — موجودہ پیغام پروسیس ہوتا ہے پھر بند۔
    """
    global _running
    log.info("Signal %s ملا — consumer بند ہو رہا ہے", sig)
    _running = False


# SIGINT (Ctrl+C) اور SIGTERM دونوں handle کریں
signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Consume Loop — پیغامات پڑھنا
# ═══════════════════════════════════════════════════════════════════════════════

async def consume() -> None:
    """
    Kafka consumer کا مرکزی loop۔

    ہر پیغام کے لیے:
      1. JSON payload deserialize کریں
      2. AI agent سے جواب بنوائیں (executor میں — blocking کال)
      3. جواب fte.responses.outgoing پر publish کریں
      4. صرف کامیابی پر offset commit کریں
         (ناکام ہو تو پیغام دوبارہ آئے گا)
    """
    try:
        from aiokafka import AIOKafkaConsumer
    except ImportError:
        log.error("aiokafka install نہیں — چلائیں: pip install aiokafka")
        return

    # پہلے producer شروع کریں (جوابات بھیجنے کے لیے)
    await init_producer()

    # Kafka consumer بنائیں
    consumer = AIOKafkaConsumer(
        INCOMING_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,

        # JSON bytes کو Python dict میں تبدیل کریں
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),

        # اگر پہلے کوئی offset commit نہیں تو شروع سے پڑھیں
        auto_offset_reset="earliest",

        # Manual commit — AI کامیاب ہونے پر ہی commit کریں
        enable_auto_commit=False,

        # AI agent slow ہو سکتا ہے — timeout زیادہ رکھیں
        session_timeout_ms=30_000,      # 30 سیکنڈ
        heartbeat_interval_ms=10_000,   # 10 سیکنڈ
    )

    await consumer.start()
    log.info(
        "Kafka consumer شروع ہو گیا topic=%s group=%s bootstrap=%s",
        INCOMING_TOPIC, GROUP_ID, KAFKA_BOOTSTRAP_SERVERS,
    )

    try:
        # ہر پیغام کا انتظار کریں اور پروسیس کریں
        async for msg in consumer:

            # اگر shutdown signal آ گیا تو loop سے نکلیں
            if not _running:
                break

            # پیغام کی معلومات نکالیں
            data        = msg.value
            customer_id = data.get("customer_id", "unknown")
            channel     = data.get("channel", "web")
            message     = data.get("message", "")

            log.info(
                "پیغام پروسیس ہو رہا ہے customer=%s channel=%s partition=%d offset=%d",
                customer_id, channel, msg.partition, msg.offset,
            )

            try:
                # run_agent synchronous (blocking) ہے
                # asyncio event loop کو block نہ کریں — executor میں چلائیں
                loop   = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,  # default ThreadPoolExecutor
                    lambda: run_agent(
                        customer_message=message,
                        customer_id=customer_id,
                        channel=channel,
                    ),
                )

                # AI کا جواب outgoing topic پر بھیجیں
                await publish_outgoing(
                    customer_id=customer_id,
                    response=result["response"],
                    intent=result["intent"],
                    escalated=result["escalated"],
                    source=result.get("source", ""),
                )

                # ✅ کامیابی پر ہی offset commit کریں
                # اگر پہلے commit کریں اور publish ناکام ہو تو پیغام کھو جائے گا
                await consumer.commit()

                log.info(
                    "پروسیسنگ مکمل customer=%s intent=%s escalated=%s source=%s",
                    customer_id, result["intent"], result["escalated"], result["source"],
                )

            except Exception as exc:
                # ❌ ناکامی پر commit نہ کریں — پیغام دوبارہ آئے گا
                log.error(
                    "پروسیسنگ ناکام customer=%s offset=%d: %s",
                    customer_id, msg.offset, exc, exc_info=True,
                )

    finally:
        # صاف بند کریں — consumer اور producer دونوں
        await consumer.stop()
        await close_producer()
        log.info("Kafka consumer بند ہو گیا")


if __name__ == "__main__":
    # براہ راست چلانا: python -m kafka.consumer
    asyncio.run(consume())
