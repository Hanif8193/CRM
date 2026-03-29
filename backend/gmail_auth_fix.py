"""
Gmail OAuth Quick Fix
اگر Test User add نہیں ہو رہا یا access_denied آ رہا ہے

چلانے کا طریقہ:
    cd backend
    python gmail_auth_fix.py
"""

import os
import sys
from pathlib import Path

# .env لوڈ کریں
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

CREDENTIALS_PATH = Path(os.getenv("GMAIL_CLIENT_PATH") or os.getenv("GMAIL_CREDENTIALS_PATH") or "gmail_credentials.json")
TOKEN_PATH       = Path(os.getenv("GMAIL_TOKEN_PATH", "gmail_token.json"))

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

def run():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("چلائیں: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    if not CREDENTIALS_PATH.exists():
        print(f"❌ فائل نہیں ملی: {CREDENTIALS_PATH}")
        print("Google Console سے credentials JSON ڈاؤنلوڈ کریں اور backend/ میں رکھیں")
        sys.exit(1)

    # پرانا token حذف کریں
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        print(f"🗑  پرانا token حذف کیا: {TOKEN_PATH}")

    print("\n🌐 Browser کھل رہا ہے...")
    print("─" * 50)
    print("Browser میں:")
    print("  1. اپنا Gmail account چنیں")
    print("  2. اگر warning آئے → 'Advanced' پر کلک کریں")
    print("  3. 'Go to ... (unsafe)' پر کلک کریں")
    print("  4. 'Allow' پر کلک کریں")
    print("─" * 50)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        SCOPES,
        # یہ parameter browser کو force کرتا ہے consent دکھانے کے لیے
        # even if previously authorized
    )

    # run_local_server — localhost پر redirect کرتا ہے
    # access_type='offline' → refresh_token ملتا ہے (لمبے عرصے کے لیے)
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",       # ← یہ لازمی ہے — ہمیشہ consent screen دکھائے
    )

    # token محفوظ کریں
    TOKEN_PATH.write_text(creds.to_json())
    print(f"\n✅ Token محفوظ ہو گیا: {TOKEN_PATH}")

    # فوری test
    print("\n📧 Gmail connection ٹیسٹ ہو رہا ہے...")
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    print(f"✅ Logged in as: {profile['emailAddress']}")
    print(f"   Total messages: {profile.get('messagesTotal', 'N/A')}")
    print("\n🎉 کامیاب! اب send_gmail_reply() کام کرے گا")


if __name__ == "__main__":
    run()
