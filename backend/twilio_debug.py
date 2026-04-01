"""
Twilio Sandbox diagnostic — run this first to find the exact error.
Usage: python twilio_debug.py
"""

import os
import sys
from dotenv import load_dotenv

# Load .env from the same directory as this script
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")

print("=== Twilio Sandbox Diagnostic ===\n")

# 1. Check credentials loaded
print(f"[1] TWILIO_ACCOUNT_SID : {'✓ loaded (' + ACCOUNT_SID[:6] + '...)' if ACCOUNT_SID else '✗ NOT FOUND in .env'}")
print(f"[2] TWILIO_AUTH_TOKEN  : {'✓ loaded' if AUTH_TOKEN else '✗ NOT FOUND in .env'}\n")

if not ACCOUNT_SID or not AUTH_TOKEN:
    print("STOP: Fix missing credentials in backend/.env first.")
    sys.exit(1)

# 2. Try importing twilio
try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException
    print("[3] twilio library     : ✓ installed\n")
except ImportError:
    print("[3] twilio library     : ✗ NOT installed — run: pip install twilio")
    sys.exit(1)

# 3. Verify credentials against Twilio API
try:
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    account = client.api.accounts(ACCOUNT_SID).fetch()
    print(f"[4] Credentials valid  : ✓ Account status = {account.status}\n")
except TwilioRestException as e:
    print(f"[4] Credentials check  : ✗ FAILED — {e.msg} (HTTP {e.status})")
    print("    → Double-check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
    sys.exit(1)

# 4. Send a test message
TO_NUMBER = input("Enter YOUR WhatsApp number to test (e.g. +923001234567): ").strip()
if not TO_NUMBER:
    print("No number entered — skipping send test.")
    sys.exit(0)

print(f"\nSending test message to whatsapp:{TO_NUMBER} ...")

try:
    msg = client.messages.create(
        from_="whatsapp:+14155238886",
        to=f"whatsapp:{TO_NUMBER}",
        body="Flowdesk CRM — Twilio Sandbox test message ✓",
    )
    print(f"\n✓ SUCCESS — Message SID: {msg.sid}")
    print(f"  Status : {msg.status}")

except TwilioRestException as e:
    print(f"\n✗ FAILED — Error {e.code}: {e.msg}")

    if e.code == 63007:
        print("\n  FIX: The recipient has not joined the Twilio Sandbox.")
        print("  → Ask them to send this WhatsApp message to +14155238886:")
        print("    join <your-sandbox-keyword>")
        print("  → Find your keyword at: Twilio Console → Messaging → Try it out → WhatsApp")

    elif e.code == 21211:
        print("\n  FIX: Invalid 'To' phone number format.")
        print("  → Use E.164 format: +[country code][number], e.g. +923001234567")

    elif e.code == 20003:
        print("\n  FIX: Authentication failed.")
        print("  → Regenerate your Auth Token in the Twilio Console.")

    else:
        print(f"\n  See: https://www.twilio.com/docs/errors/{e.code}")
