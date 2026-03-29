"""
Gmail channel handler — Gmail API + OAuth2 کے ذریعے ای میل وصول کریں اور جواب بھیجیں۔

پہلی بار چلانے کے لیے (ایک بار انٹرایکٹو OAuth):
    python -c "from channels.gmail import _get_gmail_service; _get_gmail_service()"

یہ براؤزر کھولے گا، Google سے اجازت لے گا، اور gmail_token.json محفوظ کر دے گا۔
اگلی بار ٹوکن خودبخود refresh ہوگا۔

Credentials بنانے کے مراحل:
  1. Google Cloud Console → APIs & Services → Credentials
  2. OAuth 2.0 Client ID بنائیں (Desktop application)
  3. JSON ڈاؤنلوڈ کریں اور gmail_credentials.json کے نام سے محفوظ کریں
     (یا .env میں GMAIL_CREDENTIALS_PATH سیٹ کریں)
"""

import base64  # Gmail API کے لیے base64url encoding
import logging
from email.mime.multipart import MIMEMultipart  # MIME ای میل بنانے کے لیے
from email.mime.text import MIMEText             # ای میل کا متن (plain text)
from pathlib import Path
from typing import Optional

from config import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH
from agent.agent import get_agent_response

# لاگنگ سیٹ اپ — ہر فنکشن اپنے نام سے لاگ کرے گا
log = logging.getLogger(__name__)

# OAuth2 اسکوپ — gmail.send: بھیجنا، gmail.readonly: پڑھنا
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# ٹوکن اور credentials کی فائل پاتھ (config سے آتی ہے)
_TOKEN_PATH = Path(GMAIL_TOKEN_PATH)
_CREDS_PATH = Path(GMAIL_CREDENTIALS_PATH)


# ═══════════════════════════════════════════════════════════════════════════════
# Auth — OAuth2 سروس بنانا
# ═══════════════════════════════════════════════════════════════════════════════

def _get_gmail_service():
    """
    Gmail API سروس آبجیکٹ واپس کریں (authenticated)۔

    ٹوکن خودبخود refresh ہوتا ہے۔
    اگر کوئی ٹوکن موجود نہیں تو براؤزر OAuth flow چلایا جاتا ہے
    (صرف interactive terminal میں کام کرتا ہے)۔

    Raises:
        FileNotFoundError: جب gmail_credentials.json موجود نہ ہو۔
        google.auth.exceptions.RefreshError: جب ٹوکن revoke ہو چکا ہو۔
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds: Optional[Credentials] = None

    # اگر پرانا ٹوکن محفوظ ہے تو پہلے اسے لوڈ کریں
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

    # ٹوکن چیک کریں — expired ہو تو refresh کریں، نہ ہو تو browser flow چلائیں
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # ٹوکن میعاد ختم ہو گئی — خودبخود نئی لیں
            log.info("Gmail OAuth2 ٹوکن refresh ہو رہا ہے")
            creds.refresh(Request())
        else:
            # پہلی بار یا ٹوکن نہیں — براؤزر سے اجازت لیں
            if not _CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail credentials فائل نہیں ملی: {_CREDS_PATH}\n"
                    "Google Cloud Console سے OAuth2 credentials ڈاؤنلوڈ کریں "
                    "اور gmail_credentials.json کے نام سے محفوظ کریں، "
                    "یا .env میں GMAIL_CREDENTIALS_PATH سیٹ کریں۔"
                )
            log.info("Gmail OAuth2 browser flow چل رہا ہے")
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS_PATH), _SCOPES)
            creds = flow.run_local_server(port=0)  # براؤزر کھولتا ہے

        # نیا یا refresh شدہ ٹوکن محفوظ کریں تاکہ اگلی بار browser نہ کھلے
        _TOKEN_PATH.write_text(creds.to_json())
        log.info("Gmail ٹوکن محفوظ ہو گیا: %s", _TOKEN_PATH)

    # Gmail API سروس بنائیں اور واپس کریں
    return build("gmail", "v1", credentials=creds)


# ═══════════════════════════════════════════════════════════════════════════════
# Inbound — آنے والی ای میل پروسیس کریں
# ═══════════════════════════════════════════════════════════════════════════════

def handle_gmail_message(
    sender_email: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> dict:
    """
    آنے والی Gmail پیغام پروسیس کریں اور AI جواب خودبخود بھیجیں۔

    Args:
        sender_email: بھیجنے والے کی ای میل (From: ہیڈر)
        subject:      ای میل کا عنوان
        body:         ای میل کا متن (plain text)
        thread_id:    Gmail thread ID — جواب اسی تھریڈ میں رکھنے کے لیے
        message_id:   RFC 2822 Message-ID — In-Reply-To ہیڈر کے لیے

    Returns:
        Agent result dict: {response, intent, escalated, source}
    """
    # AI agent کے لیے prompt بنائیں
    prompt = f"Email from: {sender_email}\nSubject: {subject}\n\nMessage:\n{body}"
    result = get_agent_response(prompt, channel="email")

    # Subject میں "Re:" صرف ایک بار لگائیں
    reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"

    try:
        # AI کا جواب بھیجیں — اگر fail ہو تو صرف log کریں، crash نہ ہو
        send_gmail_reply(
            to_email=sender_email,
            subject=reply_subject,
            body=result["response"],
            thread_id=thread_id,
            in_reply_to=message_id,
        )
    except Exception as exc:
        log.error("Gmail جواب بھیجنے میں خرابی to=%s: %s", sender_email, exc)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Outbound — ای میل جواب بھیجیں
# ═══════════════════════════════════════════════════════════════════════════════

def send_gmail_reply(
    to_email: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> dict:
    """
    Gmail API کے ذریعے ای میل جواب بھیجیں۔

    Args:
        to_email:    وصول کنندہ کی ای میل
        subject:     ای میل عنوان (جوابات میں "Re: " لگائیں)
        body:        plain text پیغام
        thread_id:   Gmail thread ID — اسی تھریڈ میں رکھنے کے لیے
        in_reply_to: اصل ای میل کا RFC 2822 Message-ID
                     یہ In-Reply-To اور References ہیڈر سیٹ کرتا ہے
                     تاکہ mail clients تھریڈ صحیح دکھائیں

    Returns:
        Gmail API response dict (keys: id, threadId, labelIds)

    Raises:
        googleapiclient.errors.HttpError: Gmail API 4xx/5xx errors پر
        FileNotFoundError: جب gmail_credentials.json نہ ہو
    """
    from googleapiclient.errors import HttpError

    try:
        # Gmail service حاصل کریں (OAuth2 + auto-refresh)
        service = _get_gmail_service()

        # MIME ای میل پیغام بنائیں
        mime_msg = MIMEMultipart("alternative")
        mime_msg["To"]      = to_email
        mime_msg["Subject"] = subject

        # RFC 2822 threading ہیڈر — mail clients تھریڈ صحیح گروپ کریں
        if in_reply_to:
            mime_msg["In-Reply-To"] = in_reply_to  # کس کا جواب ہے
            mime_msg["References"]  = in_reply_to  # تھریڈ chain

        # پیغام کا متن (UTF-8 plain text)
        mime_msg.attach(MIMEText(body, "plain", "utf-8"))

        # Gmail API کے لیے base64url encoding — raw MIME bytes کو encode کریں
        raw_b64 = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
        send_body: dict = {"raw": raw_b64}

        # thread_id دیں تاکہ ای میل اسی تھریڈ میں جائے
        if thread_id:
            send_body["threadId"] = thread_id

        # Gmail API کال — ای میل بھیجیں
        result = (
            service.users()
            .messages()
            .send(userId="me", body=send_body)
            .execute()
        )

        log.info(
            "Gmail جواب بھیجا گیا to=%s threadId=%s messageId=%s",
            to_email,
            result.get("threadId"),
            result.get("id"),
        )
        return result

    except HttpError as exc:
        # Gmail API error — status code اور تفصیل log کریں
        log.error(
            "Gmail API خرابی status=%s to=%s: %s",
            getattr(exc.resp, "status", "?"),
            to_email,
            exc,
        )
        raise  # اوپر propagate کریں تاکہ caller سنبھال سکے


# ═══════════════════════════════════════════════════════════════════════════════
# Example Usage — مثال
# ═══════════════════════════════════════════════════════════════════════════════
#
# سادہ جواب بھیجنا:
#   from channels.gmail import send_gmail_reply
#   send_gmail_reply(
#       to_email    = "customer@example.com",
#       subject     = "Re: My Issue",
#       body        = "آپ کا مسئلہ حل ہو گیا ہے۔ شکریہ!",
#       thread_id   = "17abc123def456",       # Gmail thread ID
#       in_reply_to = "<abc@mail.gmail.com>", # اصل ای میل کا Message-ID
#   )
#
# تھریڈ میں رکھنے کے لیے thread_id لازمی دیں۔
# ═══════════════════════════════════════════════════════════════════════════════
