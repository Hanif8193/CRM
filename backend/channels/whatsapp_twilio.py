"""
WhatsApp channel handler — Twilio Sandbox.

Env vars required (backend/.env):
    TWILIO_ACCOUNT_SID   ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN    your_auth_token
"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Load .env from backend/ regardless of cwd
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"   # Twilio Sandbox sender (fixed)

E164_RE = re.compile(r"^\+\d{7,15}$")           # basic E.164 validation


def send_whatsapp_message(to_number: str, message: str) -> str:
    """
    Send a WhatsApp message via Twilio Sandbox.

    Args:
        to_number: Recipient in E.164 format, e.g. '+923001234567'.
        message:   Text body to send.

    Returns:
        Twilio Message SID string.

    Raises:
        ValueError:          Missing credentials or invalid number format.
        TwilioRestException: Twilio API rejected the request.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError(
            "Twilio credentials not set. "
            "Add TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to backend/.env"
        )

    # Normalise number — strip leading spaces, ensure no duplicate prefix
    number = to_number.strip()
    if not E164_RE.match(number):
        raise ValueError(
            f"Invalid phone number '{number}'. "
            "Use E.164 format: +[country code][number], e.g. +923001234567"
        )

    formatted_to = f"whatsapp:{number}"

    client  = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    msg     = client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=formatted_to,
        body=message,
    )

    print(f"[Twilio] Sent → {formatted_to} | SID: {msg.sid}")
    return msg.sid
