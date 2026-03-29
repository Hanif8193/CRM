"""
Async Kafka Producer — پیغامات Kafka میں بھیجنا

دو topics پر publish کرتا ہے:
  - fte.tickets.incoming   — گاہک کے آنے والے خام پیغامات
  - fte.responses.outgoing — AI کے تیار کردہ جوابات

یہ producer اختیاری ہے: اگر Kafka شروع میں نہ ملے تو app نارمل چلتی رہتی ہے
اور تمام publish calls خاموشی سے نظرانداز ہو جاتی ہیں۔

Lifecycle (FastAPI lifespan میں):
    await init_producer()   # ایپ شروع ہوتے وقت ایک بار
    await close_producer()  # ایپ بند ہوتے وقت ایک بار
"""

import json       # پیغامات JSON فارمیٹ میں encode کرنا
import logging
from typing import Optional

from config import KAFKA_BOOTSTRAP_SERVERS

log = logging.getLogger(__name__)

# Topic ناموں کی تعریف — docker-compose کی config سے match ہونا چاہیے
TOPIC_INCOMING = "fte.tickets.incoming"    # آنے والے پیغامات
TOPIC_OUTGOING = "fte.responses.outgoing"  # جانے والے جوابات

# Global producer instance — None جب Kafka دستیاب نہ ہو
_producer = None  # AIOKafkaProducer یا None


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle Functions
# ═══════════════════════════════════════════════════════════════════════════════

async def init_producer() -> None:
    """
    Kafka producer شروع کریں۔

    اگر aiokafka install نہیں یا Kafka نہیں ملتا تو خاموشی سے چھوڑ دیتا ہے
    — app crash نہیں ہوتی۔
    """
    global _producer
    try:
        # lazy import — تاکہ aiokafka کے بغیر بھی app شروع ہو سکے
        from aiokafka import AIOKafkaProducer

        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,

            # پیغام کی value — UTF-8 JSON میں تبدیل کریں
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),

            # key — customer_id کو UTF-8 bytes میں تبدیل کریں
            # ایک ہی customer کے تمام پیغام ایک ہی partition میں جائیں گے
            key_serializer=lambda k: k.encode("utf-8") if k else None,

            # قابل اعتماد ترسیل کی سیٹنگ
            acks="all",              # تمام in-sync replicas کا انتظار کریں
            enable_idempotence=True, # duplicate سے بچیں (exactly-once per partition)
            compression_type="gzip", # نیٹ ورک پر کم ڈیٹا بھیجیں
        )
        await _producer.start()
        log.info("Kafka producer متصل ہو گیا bootstrap_servers=%s", KAFKA_BOOTSTRAP_SERVERS)

    except ImportError:
        # aiokafka install نہیں — Kafka کے بغیر چلیں
        log.warning("aiokafka install نہیں — Kafka publishing بند ہے")
        _producer = None

    except Exception as exc:
        # Kafka server نہیں ملا — app پھر بھی چلتی رہے
        log.warning("Kafka producer دستیاب نہیں: %s — Kafka کے بغیر جاری ہے", exc)
        _producer = None


async def close_producer() -> None:
    """
    باقی پیغامات flush کریں اور producer بند کریں۔
    FastAPI lifespan shutdown میں call ہوتا ہے۔
    """
    global _producer
    if _producer is not None:
        try:
            await _producer.stop()  # تمام pending پیغامات بھیج کر بند کریں
            log.info("Kafka producer بند ہو گیا")
        except Exception as exc:
            log.error("Kafka producer بند کرنے میں خرابی: %s", exc)
        _producer = None


# ═══════════════════════════════════════════════════════════════════════════════
# Publish Helpers — پیغامات بھیجنا
# ═══════════════════════════════════════════════════════════════════════════════

async def publish_incoming(
    customer_id: str,
    channel: str,
    message: str,
) -> None:
    """
    آنے والا خام پیغام ``fte.tickets.incoming`` topic پر بھیجیں۔

    پیغام customer_id سے key کیا جاتا ہے تاکہ ایک گاہک کے تمام پیغام
    ایک ہی partition میں جائیں اور ترتیب برقرار رہے۔

    Args:
        customer_id: گاہک کی شناخت
        channel:     چینل (email / whatsapp / web)
        message:     گاہک کا خام پیغام
    """
    if _producer is None:
        return  # Kafka نہیں — خاموشی سے نظرانداز کریں

    # Kafka کو بھیجنے والا payload
    payload = {
        "customer_id": customer_id,
        "channel":     channel,
        "message":     message,
    }
    try:
        await _producer.send_and_wait(
            topic=TOPIC_INCOMING,
            key=customer_id,   # partition key
            value=payload,
        )
        log.debug("Kafka → %s  customer=%s", TOPIC_INCOMING, customer_id)
    except Exception as exc:
        log.error("Kafka publish_incoming ناکام customer=%s: %s", customer_id, exc)


async def publish_outgoing(
    customer_id: str,
    response: str,
    intent: str,
    escalated: bool,
    source: str = "",
    ticket_id: Optional[int] = None,
) -> None:
    """
    AI کا تیار کردہ جواب ``fte.responses.outgoing`` topic پر بھیجیں۔

    Args:
        customer_id: گاہک کی شناخت
        response:    AI کا جواب
        intent:      شناخت شدہ intent (product / pricing / refund / ...)
        escalated:   True اگر human agent کو بھیجا گیا
        source:      جواب کا ذریعہ (docs / escalation / ai / ...)
        ticket_id:   ticket ID اگر بنا ہو
    """
    if _producer is None:
        return  # Kafka نہیں — خاموشی سے نظرانداز کریں

    payload = {
        "customer_id": customer_id,
        "response":    response,
        "intent":      intent,
        "escalated":   escalated,
        "source":      source,
        "ticket_id":   ticket_id,
    }
    try:
        await _producer.send_and_wait(
            topic=TOPIC_OUTGOING,
            key=customer_id,
            value=payload,
        )
        log.debug(
            "Kafka → %s  customer=%s escalated=%s",
            TOPIC_OUTGOING, customer_id, escalated,
        )
    except Exception as exc:
        log.error("Kafka publish_outgoing ناکام customer=%s: %s", customer_id, exc)
