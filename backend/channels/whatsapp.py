"""WhatsApp channel handler (Meta Cloud API)."""
import httpx
from config import WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID
from agent.agent import get_agent_response

WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"


def handle_whatsapp_message(from_number: str, message: str) -> dict:
    """Process an incoming WhatsApp message and send a reply. Returns the agent result dict."""
    result = get_agent_response(message, channel="whatsapp")
    send_whatsapp_reply(from_number, result["response"])
    return result


def send_whatsapp_reply(to_number: str, message: str):
    """Send a WhatsApp message via Meta Cloud API."""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message},
    }
    response = httpx.post(WHATSAPP_API_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()
