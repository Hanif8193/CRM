"""
Flask micro-app — Lead Management API.

Runs independently from the existing FastAPI backend on port 5050.

Endpoints:
    POST /add-lead   { "name": "...", "phone": "+923xxxxxxxxx" }
    GET  /leads      list all leads (debug)

Run:
    cd backend
    python api/lead_app.py
"""

import sys
import os

# Allow imports from backend/ root when running this file directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from services.lead_service import add_lead, get_all_leads

app = Flask(__name__)


@app.post("/add-lead")
def api_add_lead():
    """
    Add a new lead and trigger a WhatsApp welcome message.

    Request body (JSON):
        { "name": "Ali Khan", "phone": "+923001234567" }

    Response (success):
        { "status": "ok", "lead_id": 1, "message_sid": "SMxxx..." }

    Response (error):
        { "status": "error", "message": "..." }  — HTTP 400 or 502
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    name  = (data.get("name")  or "").strip()
    phone = (data.get("phone") or "").strip()

    if not name:
        return jsonify({"status": "error", "message": "'name' is required."}), 400
    if not phone:
        return jsonify({"status": "error", "message": "'phone' is required."}), 400

    result = add_lead(name, phone)

    if result.success:
        return jsonify({
            "status":      "ok",
            "lead_id":     result.lead_id,
            "message_sid": result.message_sid,
        }), 200
    else:
        # Lead saved but WhatsApp delivery failed
        return jsonify({
            "status":    "partial",
            "lead_id":   result.lead_id,
            "message":   f"Lead saved, but WhatsApp failed: {result.error}",
        }), 502


@app.get("/leads")
def api_get_leads():
    """Return all leads (for debugging)."""
    return jsonify(get_all_leads()), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
