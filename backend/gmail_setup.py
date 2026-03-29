"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          Gmail OAuth Setup & Test Script — CRM AI Agent                    ║
║          Gmail OAuth سیٹ اپ اور ٹیسٹ اسکرپٹ                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

یہ فائل تین کام کرتی ہے:
  1. Gmail OAuth token بناتی ہے (پہلی بار)
  2. Token کو gmail_token.json میں محفوظ کرتی ہے
  3. ٹیسٹ ای میل بھیجتی ہے تاکہ سب کچھ کام کر رہا ہو

چلانے کا طریقہ (backend/ فولڈر سے):
    python gmail_setup.py

ضروریات:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv
"""

# ──────────────────────────────────────────────────────────────────────────────
# Standard library imports — Python کی built-in libraries
# ──────────────────────────────────────────────────────────────────────────────
import base64           # Gmail API کے لیے base64url encoding
import json             # Token JSON پڑھنا/لکھنا
import os               # Environment variables پڑھنا
import sys              # Exit codes کے لیے
from datetime import datetime           # وقت timestamp کے لیے
from email.mime.multipart import MIMEMultipart  # MIME email structure
from email.mime.text import MIMEText            # Email body text
from pathlib import Path                        # فائل پاتھ handle کرنا
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# .env فائل لوڈ کریں — environment variables
# ──────────────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    # backend/ فولڈر میں .env ڈھونڈیں، نہ ملے تو parent (CRM/) میں
    _env_path = Path(__file__).parent / ".env"
    if not _env_path.exists():
        _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(_env_path)
    print(f"✅ .env لوڈ ہو گئی: {_env_path}")
except ImportError:
    print("⚠️  python-dotenv install نہیں — os.environ سے پڑھ رہے ہیں")

# ──────────────────────────────────────────────────────────────────────────────
# Configuration — .env سے settings پڑھیں
# ──────────────────────────────────────────────────────────────────────────────

# gmail_credentials.json کی جگہ (.env میں GMAIL_CREDENTIALS_PATH)
CREDENTIALS_PATH = Path(
    os.getenv("GMAIL_CREDENTIALS_PATH", "gmail_credentials.json")
)

# gmail_token.json کی جگہ (.env میں GMAIL_TOKEN_PATH)
TOKEN_PATH = Path(
    os.getenv("GMAIL_TOKEN_PATH", "gmail_token.json")
)

# Gmail API scopes — کیا کام کر سکتے ہیں
# gmail.send = ای میل بھیجنا
# gmail.readonly = ای میل پڑھنا (webhooks کے لیے)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Gmail Service بنانا — _get_gmail_service()
# Build authenticated Gmail API service
# ══════════════════════════════════════════════════════════════════════════════

def _get_gmail_service():
    """
    Authenticated Gmail API service object واپس کریں۔

    یہ فنکشن تین حالتیں handle کرتا ہے:
      A. نیا token نہیں → browser flow چلائے (پہلی بار)
      B. Token expired → خودبخود refresh کرے
      C. Token valid → سیدھا service واپس کرے

    Returns:
        googleapiclient.discovery.Resource — Gmail API service

    Raises:
        FileNotFoundError — جب gmail_credentials.json نہ ہو
        SystemExit       — جب Google API packages install نہ ہوں
    """
    # ── Google packages import کریں ──────────────────────────────────────────
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("\n❌ Google API packages نہیں ملے۔ یہ command چلائیں:")
        print("   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    creds: Optional[Credentials] = None

    # ── A: موجودہ token لوڈ کریں ─────────────────────────────────────────────
    # اگر پہلے OAuth ہو چکی ہے تو محفوظ token فائل سے پڑھیں
    if TOKEN_PATH.exists():
        print(f"📂 موجودہ token پڑھ رہے ہیں: {TOKEN_PATH}")
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # ── B یا C: Token چیک کریں ───────────────────────────────────────────────
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            # ── B: Token expired ہے — خودبخود نئی لیں ──────────────────────
            # Browser کھولنے کی ضرورت نہیں، Google خودبخود refresh کرے گا
            print("🔄 Token کی میعاد ختم ہو گئی — refresh ہو رہا ہے...")
            try:
                creds.refresh(Request())
                print("✅ Token refresh ہو گیا")
            except Exception as e:
                # Refresh ناکام ہو تو دوبارہ full OAuth flow چلائیں
                print(f"⚠️  Refresh ناکام: {e}")
                print("🌐 دوبارہ browser OAuth flow چل رہا ہے...")
                creds = None  # نیچے browser flow چلائے گا

        if not creds:
            # ── C: پہلی بار — credentials فائل سے browser flow ──────────────
            if not CREDENTIALS_PATH.exists():
                print(f"\n❌ Credentials فائل نہیں ملی: {CREDENTIALS_PATH}")
                print("\n📋 یہ مراحل follow کریں:")
                print("   1. console.cloud.google.com کھولیں")
                print("   2. APIs & Services → Credentials → Create Credentials")
                print("   3. OAuth 2.0 Client ID → Desktop application")
                print("   4. JSON ڈاؤنلوڈ کریں")
                print(f"   5. فائل کا نام رکھیں: {CREDENTIALS_PATH}")
                raise FileNotFoundError(
                    f"Gmail credentials نہیں ملی: {CREDENTIALS_PATH}"
                )

            print(f"\n🌐 Gmail OAuth browser flow شروع ہو رہا ہے...")
            print("   براؤزر کھلے گا — اپنا Gmail account چنیں اور Allow کریں")
            print("   اگر 'Google hasn't verified this app' آئے:")
            print("   → 'Advanced' پر کلک کریں")
            print("   → 'Go to CRM Gmail OAuth (unsafe)' پر کلک کریں")
            print("   → 'Allow' پر کلک کریں\n")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SCOPES,
            )
            # port=0 → کوئی بھی خالی port استعمال کرے
            creds = flow.run_local_server(port=0)

        # ── Token محفوظ کریں ─────────────────────────────────────────────────
        # اگلی بار browser کھولنے کی ضرورت نہیں
        TOKEN_PATH.write_text(creds.to_json())
        print(f"💾 Token محفوظ ہو گیا: {TOKEN_PATH}")

    # ── Gmail API service بنائیں اور واپس کریں ───────────────────────────────
    service = build("gmail", "v1", credentials=creds)
    print("✅ Gmail service تیار ہے")
    return service


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: ای میل بھیجنا — send_gmail_reply()
# Send email via Gmail API
# ══════════════════════════════════════════════════════════════════════════════

def send_gmail_reply(
    to_email: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> dict:
    """
    Gmail API کے ذریعے ای میل بھیجیں۔

    یہ فنکشن:
      1. Authenticated Gmail service حاصل کرتا ہے
      2. MIME message بناتا ہے (plain text)
      3. Threading headers لگاتا ہے (اگر reply ہو)
      4. base64url encode کرتا ہے (Gmail API requirement)
      5. API call کرتا ہے

    Args:
        to_email    : وصول کنندہ کی ای میل address
        subject     : ای میل کا عنوان
        body        : ای میل کا مکمل متن (plain text)
        thread_id   : Gmail thread ID (reply کو اسی thread میں رکھتا ہے)
        in_reply_to : اصل message کا RFC 2822 Message-ID
                      mail clients کے لیے thread grouping

    Returns:
        dict with keys:
            id        — نئے message کا Gmail ID
            threadId  — Thread ID
            labelIds  — Labels (عموماً ["SENT"])

    Raises:
        googleapiclient.errors.HttpError — Gmail API error
    """
    from googleapiclient.errors import HttpError

    try:
        # Gmail service حاصل کریں (auto-refresh included)
        service = _get_gmail_service()

        # ── MIME message بنائیں ───────────────────────────────────────────────
        # MIMEMultipart = multiple parts والی email (plain + html وغیرہ)
        mime_msg = MIMEMultipart("alternative")
        mime_msg["To"]      = to_email
        mime_msg["Subject"] = subject
        # From: Gmail خودبخود لگاتا ہے ("me" = authenticated account)

        # ── Threading headers — replies کو thread میں رکھنا ──────────────────
        # یہ headers email clients کو بتاتے ہیں کہ یہ کس message کا جواب ہے
        if in_reply_to:
            mime_msg["In-Reply-To"] = in_reply_to  # کس message کا جواب
            mime_msg["References"]  = in_reply_to  # thread chain reference

        # ── Email body لگائیں ────────────────────────────────────────────────
        # plain text — اگر HTML بھی چاہیے تو MIMEText(html_body, "html") add کریں
        mime_msg.attach(MIMEText(body, "plain", "utf-8"))

        # ── base64url encoding ────────────────────────────────────────────────
        # Gmail API raw MIME bytes نہیں لیتا — base64url string لیتا ہے
        # as_bytes() → MIME → bytes
        # urlsafe_b64encode() → URL-safe base64
        # decode("ascii") → Python string
        raw_encoded = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")

        # ── API payload بنائیں ────────────────────────────────────────────────
        api_body: dict = {"raw": raw_encoded}

        # thread_id دیں تاکہ reply اسی thread میں جائے (inbox میں grouped)
        if thread_id:
            api_body["threadId"] = thread_id

        # ── Gmail API call — ای میل بھیجیں ───────────────────────────────────
        result = (
            service
            .users()
            .messages()
            .send(userId="me", body=api_body)  # "me" = authenticated user
            .execute()
        )

        print(f"✅ ای میل بھیجی گئی!")
        print(f"   To:        {to_email}")
        print(f"   Subject:   {subject}")
        print(f"   Message ID: {result.get('id')}")
        print(f"   Thread ID:  {result.get('threadId')}")
        return result

    except HttpError as exc:
        # Gmail API نے error دی — status code اور وجہ دکھائیں
        status = getattr(exc.resp, "status", "?")
        print(f"❌ Gmail API خرابی (HTTP {status}): {exc}")

        # عام errors کی وجہ بتائیں
        if status == 403:
            print("   وجہ: Gmail API enable نہیں یا scopes کافی نہیں")
        elif status == 401:
            print("   وجہ: Token invalid ہے — gmail_token.json حذف کریں اور دوبارہ OAuth چلائیں")
        elif status == 400:
            print("   وجہ: Request میں کوئی غلطی — to_email چیک کریں")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Test Email — ٹیسٹ ای میل بھیجیں
# ══════════════════════════════════════════════════════════════════════════════

def send_test_email(to_email: str) -> dict:
    """
    ٹیسٹ ای میل بھیجیں تاکہ Gmail setup کام کر رہا ہو۔

    یہ فنکشن send_gmail_reply() کو call کرتا ہے مگر:
      - Subject اور body پہلے سے لکھی ہوئی ہے
      - thread_id اور in_reply_to نہیں (نئی email)
      - کامیابی/ناکامی کا واضح message دیتا ہے

    Args:
        to_email: جہاں ٹیسٹ ای میل بھیجنی ہے

    Returns:
        Gmail API response dict

    Usage:
        send_test_email("yourname@gmail.com")
        # اپنا ہی address دیں — اپنے inbox میں ملے گی
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    subject = f"✅ CRM Gmail Setup Test — {now}"

    body = f"""
سلام! یہ CRM AI Agent کی طرف سے ٹیسٹ ای میل ہے۔
Hello! This is a test email from CRM AI Agent.

اگر آپ یہ ای میل وصول کر رہے ہیں تو Gmail OAuth مکمل طور پر کام کر رہا ہے۔
If you received this email, Gmail OAuth is working correctly.

────────────────────────────────
وقت / Time: {now}
ارسال: CRM AI Agent (gmail_setup.py)
────────────────────────────────

اگلے مراحل / Next steps:
  1. FastAPI سرور شروع کریں: uvicorn main:app --reload
  2. Tests چلائیں: pytest tests/test_agent.py -v
  3. Docker سے چلائیں: docker-compose up --build

نوٹ: یہ ای میل gmail_setup.py سے بھیجی گئی ہے۔
Note: This email was sent from gmail_setup.py.
""".strip()

    print(f"\n📧 ٹیسٹ ای میل بھیج رہے ہیں → {to_email}")
    return send_gmail_reply(to_email=to_email, subject=subject, body=body)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Token Inspector — موجودہ token کی معلومات دکھائیں
# ══════════════════════════════════════════════════════════════════════════════

def inspect_token() -> None:
    """
    gmail_token.json کی موجودہ حالت چیک کریں۔
    Diagnose کریں کہ token valid ہے یا نہیں۔
    """
    print("\n🔍 Token معائنہ...")
    print(f"   Token فائل: {TOKEN_PATH}")

    if not TOKEN_PATH.exists():
        print("   ❌ Token فائل موجود نہیں — OAuth flow چلائیں")
        return

    try:
        data = json.loads(TOKEN_PATH.read_text())
        print(f"   ✅ Token فائل موجود ہے")
        print(f"   Client ID:  {data.get('client_id', 'نہیں ملا')[:30]}...")
        print(f"   Scopes:     {data.get('scopes', [])}")
        print(f"   Token Type: {data.get('token_uri', 'نامعلوم')}")

        # expiry چیک کریں
        expiry = data.get("expiry")
        if expiry:
            print(f"   Expiry:     {expiry}")
        else:
            print("   Expiry:     (refresh token موجود ہے — خودبخود renew ہوتا ہے)")

    except json.JSONDecodeError:
        print("   ❌ Token فائل corrupt ہے — حذف کریں اور دوبارہ OAuth چلائیں")


# ══════════════════════════════════════════════════════════════════════════════
# Main — براہ راست چلانے کا کوڈ
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Interactive setup wizard — مرحلہ وار Gmail setup کریں۔
    """
    print("=" * 65)
    print("  CRM Gmail OAuth Setup Wizard")
    print("  CRM Gmail OAuth سیٹ اپ وزرڈ")
    print("=" * 65)

    # موجودہ token کی حالت دکھائیں
    inspect_token()

    print("\n" + "─" * 65)
    print("مرحلہ 1: Gmail Service بنا رہے ہیں...")
    print("Step 1: Building Gmail service...")
    print("─" * 65)

    try:
        # Gmail service بنائیں (OAuth flow چلے گا اگر پہلی بار ہے)
        service = _get_gmail_service()
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Gmail service ناکام: {e}")
        sys.exit(1)

    print("\n" + "─" * 65)
    print("مرحلہ 2: ٹیسٹ ای میل بھیجیں")
    print("Step 2: Send a test email")
    print("─" * 65)

    # وصول کنندہ کا address پوچھیں
    print("\nکس ای میل پر ٹیسٹ بھیجنا ہے؟")
    print("Which email should receive the test? (اپنا Gmail address دیں)")
    to_email = input("Email address: ").strip()

    if not to_email or "@" not in to_email:
        print("❌ درست email address درج کریں")
        sys.exit(1)

    print()
    try:
        result = send_test_email(to_email)
        print("\n" + "=" * 65)
        print("🎉 کامیاب! Gmail OAuth مکمل طور پر کام کر رہا ہے")
        print("🎉 Success! Gmail OAuth is fully working")
        print("=" * 65)
        print(f"\n   ✅ Message ID : {result['id']}")
        print(f"   ✅ Thread ID  : {result['threadId']}")
        print(f"   ✅ Token فائل : {TOKEN_PATH}")
        print(f"\n   📬 {to_email} کا inbox چیک کریں")
        print("\nاگلے مراحل:")
        print("   uvicorn main:app --reload          ← FastAPI شروع کریں")
        print("   pytest tests/test_agent.py -v      ← Tests چلائیں")
        print("   docker-compose up --build          ← Docker سے چلائیں")

    except Exception as e:
        print(f"\n❌ ٹیسٹ ای میل ناکام: {e}")
        print("\nمسئلے کا حل:")
        print("  1. google.cloud.console.com → OAuth consent screen")
        print("  2. Test users میں اپنا email شامل کریں")
        print("  3. gmail_token.json حذف کریں")
        print("  4. یہ script دوبارہ چلائیں")
        sys.exit(1)


if __name__ == "__main__":
    main()
