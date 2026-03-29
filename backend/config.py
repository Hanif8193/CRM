"""
Central configuration — all values read from environment variables.

Copy .env.example → .env and fill in your secrets before running.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/crm_db",
)

# ── Anthropic / Claude ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# ── Gmail OAuth2 ──────────────────────────────────────────────────────────────
# GMAIL_CLIENT_PATH اور GMAIL_CREDENTIALS_PATH دونوں کام کرتے ہیں (.env میں جو بھی ہو)
GMAIL_CREDENTIALS_PATH: str = (
    os.getenv("GMAIL_CLIENT_PATH")          # نیا نام (.env.example میں)
    or os.getenv("GMAIL_CREDENTIALS_PATH")  # پرانا نام (backwards compat)
    or "gmail_credentials.json"             # default
)
GMAIL_TOKEN_PATH: str = os.getenv("GMAIL_TOKEN_PATH", "gmail_token.json")

# ── WhatsApp (Meta Cloud API) ─────────────────────────────────────────────────
WHATSAPP_API_TOKEN:            str = os.getenv("WHATSAPP_API_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID:      str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET:           str = os.getenv("WHATSAPP_APP_SECRET", "")

# ── CORS ──────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins.
# Production example: ALLOWED_ORIGINS=https://mycrm.com,https://app.mycrm.com
_raw_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ── Rate limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "5"))
RATE_LIMIT_WINDOW:   int = int(os.getenv("RATE_LIMIT_WINDOW",   "60"))  # seconds

# ── Kafka ─────────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# ── Sentry ────────────────────────────────────────────────────────────────────
SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

# ── Application ───────────────────────────────────────────────────────────────
ENV:       str = os.getenv("ENV", "development")  # development | production
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
