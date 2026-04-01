"""
Streamlit UI — Add Lead with WhatsApp Auto-Trigger.

Calls lead_service directly — no Flask server required.

Run:
    cd backend
    streamlit run ui/streamlit_app.py
"""

import sys
import os
import re

# Allow imports from backend/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from services.lead_service import add_lead, get_all_leads

E164_RE = re.compile(r"^\+\d{7,15}$")

st.set_page_config(page_title="Add Lead — Flowdesk CRM", page_icon="📋", layout="centered")

st.title("📋 Add New Lead")
st.caption("Flowdesk CRM · WhatsApp Auto-Trigger via Twilio Sandbox")

st.info(
    "A WhatsApp welcome message is sent automatically when a lead is added.\n\n"
    "**Pre-requisite:** The lead's number must have joined the Twilio Sandbox by "
    "sending `join <keyword>` to **+1 415 523 8886**.",
    icon="ℹ️",
)

# ── Form ──────────────────────────────────────────────────────────────────────
with st.form("add_lead_form", clear_on_submit=True):
    name  = st.text_input("Full Name", placeholder="Ali Khan")
    phone = st.text_input(
        "WhatsApp Number", placeholder="+923001234567",
        help="Include country code, e.g. +923001234567",
    )
    submitted = st.form_submit_button("Add Lead & Send WhatsApp", type="primary")

# ── Submit handler ─────────────────────────────────────────────────────────────
if submitted:
    errors = []
    if not name.strip():
        errors.append("Name is required.")
    if not phone.strip():
        errors.append("Phone number is required.")
    elif not E164_RE.match(phone.strip()):
        errors.append("Phone must be in E.164 format, e.g. +923001234567")

    if errors:
        for err in errors:
            st.error(err)
    else:
        with st.spinner("Saving lead and sending WhatsApp message..."):
            result = add_lead(name.strip(), phone.strip())

        if result.success:
            st.success(f"Lead added! WhatsApp message sent to **{phone.strip()}**")
            st.code(
                f"Lead ID    : {result.lead_id}\n"
                f"Message SID: {result.message_sid}",
                language="text",
            )
        else:
            st.warning(
                f"Lead saved (ID: {result.lead_id}), but WhatsApp failed:\n\n"
                f"{result.error}"
            )

# ── Lead list ─────────────────────────────────────────────────────────────────
with st.expander("View all leads"):
    leads = get_all_leads()
    if leads:
        st.table(leads)
    else:
        st.caption("No leads yet.")
