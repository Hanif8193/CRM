"""
Customer Success AI Agent — FastAPI کا مرکزی entry point

v3.0.0 میں تبدیلیاں:
  - CORS صرف مخصوص origins تک محدود (ALLOWED_ORIGINS env var)
  - فی IP sliding-window rate limiting (.env سے قابل ترتیب)
  - Structured JSON logging + اختیاری Sentry error tracking
  - Kafka producer lifespan میں شروع/بند
  - Global exception handler — unhandled errors پر صاف JSON
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    """JSONResponse that explicitly declares charset=utf-8 in Content-Type.
    Ensures non-ASCII characters (em-dash, Urdu text, etc.) render correctly
    in all HTTP clients, not just browsers that assume UTF-8.
    """
    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

# ─── Logging سب سے پہلے setup کریں ─────────────────────────────────────────
# کوئی بھی module اپنا پہلا log لکھنے سے پہلے logging تیار ہونا چاہیے
from logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

# ─── باقی imports ────────────────────────────────────────────────────────────
from api.admin_routes import router as admin_router
from api.message_routes import router as message_router
from api.routes import router as legacy_router
from config import ALLOWED_ORIGINS, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW
from database.connection import close_db, init_db
from kafka.producer import close_producer, init_producer
from middleware.rate_limit import RateLimitMiddleware


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan — ایپ شروع اور بند ہونے کے کام
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager۔

    شروع (yield سے پہلے):
      - PostgreSQL connection pool کھولیں
      - Kafka producer شروع کریں

    بند (yield کے بعد):
      - Kafka producer بند کریں (باقی پیغامات flush ہوں)
      - PostgreSQL pool بند کریں
    """
    log.info("CRM AI Agent v3.0.0 شروع ہو رہا ہے")

    # PostgreSQL pool کھولیں
    init_db()

    # Kafka producer شروع کریں (اگر Kafka نہیں تو خاموش رہے گا)
    await init_producer()

    log.info("Startup مکمل — درخواستیں قبول کرنے کے لیے تیار")

    yield  # ← یہاں ایپ چلتی رہتی ہے

    # Shutdown — صاف بند کریں
    log.info("Shutdown شروع ہو رہا ہے")
    await close_producer()  # پہلے Kafka flush کریں
    close_db()              # پھر DB بند کریں
    log.info("Shutdown مکمل")


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI Application
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Customer Success AI Agent",
    version="3.0.0",
    default_response_class=UTF8JSONResponse,
    description=(
        "Digital FTE — email، WhatsApp، اور web پر گاہکوں کے پیغامات سنبھالتا ہے۔ "
        "Conversation memory، doc search، escalation rules، Kafka، "
        "rate limiting، اور structured logging شامل ہیں۔"
    ),
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Middleware — آخر میں add کریں = سب سے باہر = سب سے پہلے چلے
# ═══════════════════════════════════════════════════════════════════════════════

# 1️⃣ CORS — صرف مخصوص origins کو اجازت دیں
#    Production میں کبھی wildcard * استعمال نہ کریں
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,      # .env سے آتا ہے: https://mycrm.com
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

# 2️⃣ Rate Limiting — فی IP مخصوص درخواستیں فی منٹ
#    Default: 5 درخواستیں / 60 سیکنڈ (قابل ترتیب .env سے)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=RATE_LIMIT_REQUESTS,   # RATE_LIMIT_REQUESTS=5
    window_seconds=RATE_LIMIT_WINDOW,   # RATE_LIMIT_WINDOW=60
)


# ═══════════════════════════════════════════════════════════════════════════════
# Routers — endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# نئے routes: POST /api/message، GET/DELETE /api/memory/*، GET /api/tickets/*
app.include_router(message_router, prefix="/api", tags=["Agent"])

# Admin routes: GET/PATCH /api/admin/*
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

# پرانے routes: POST /api/chat، POST /api/webhook/*، GET /api/health، GET /api/metrics
app.include_router(legacy_router, prefix="/api", tags=["Legacy / Webhooks"])


# ═══════════════════════════════════════════════════════════════════════════════
# Root Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Root"])
def root() -> dict:
    """ایپ کا status چیک کریں۔"""
    return {
        "status":  "ok",
        "message": "Customer Success AI Agent چل رہا ہے",
        "docs":    "/docs",     # Swagger UI
        "version": "3.0.0",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Global Error Handler — غیر متوقع خرابیاں
# ═══════════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    کوئی بھی unhandled exception پکڑیں، log کریں، اور صاف JSON واپس کریں۔
    Sentry کی طرف بھی بھیجا جائے گا اگر SENTRY_DSN سیٹ ہو۔
    """
    log.error(
        "غیر متوقع خرابی method=%s path=%s error=%s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,  # stack trace بھی log کریں
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "اندرونی خرابی ہوئی۔ ہماری ٹیم کو اطلاع دے دی گئی ہے۔"},
    )
