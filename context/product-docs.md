# Flowdesk Product Documentation

> This document is used internally by the AI agent to answer customer questions accurately.
> Topics marked **[RESTRICTED]** must be escalated to a human agent — do not answer directly.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Account & Password](#account--password)
3. [Features Guide](#features-guide)
4. [Pricing & Plans](#pricing--plans-restricted)
5. [Integrations](#integrations)
6. [Troubleshooting](#troubleshooting)
7. [Billing & Refunds](#billing--refunds-restricted)

---

## Getting Started

### Creating Your Account

1. Go to **app.flowdesk.io/signup**
2. Enter your work email and create a password
3. Verify your email (check spam if not received within 2 minutes)
4. Complete the onboarding wizard — takes about 5 minutes
5. Connect your first channel (Gmail recommended for beginners)

### Inviting Team Members

1. Go to **Settings → Team**
2. Click **Invite Member**
3. Enter their email address and choose a role:
   - **Admin** — full access including billing
   - **Agent** — can view and respond to conversations
   - **Viewer** — read-only access
4. They will receive an invite email valid for 48 hours

---

## Account & Password

### How to Reset Your Password

**If you are logged out:**
1. Go to **app.flowdesk.io/login**
2. Click **"Forgot your password?"** below the login form
3. Enter the email address associated with your account
4. Click **Send Reset Link**
5. Check your inbox (and spam folder) for an email from **noreply@flowdesk.io**
6. Click the reset link — it expires in **60 minutes**
7. Enter your new password (minimum 8 characters, must include 1 number)
8. Click **Save Password**
9. You will be redirected to the login page — sign in with your new password

**If you are already logged in:**
1. Click your profile avatar (top-right corner)
2. Go to **Settings → Security**
3. Click **Change Password**
4. Enter your current password, then your new password twice
5. Click **Update Password**

**If you no longer have access to your email:**
Contact support at support@flowdesk.io with proof of account ownership (billing receipt or business email domain match).

---

### How to Change Your Email Address

1. Go to **Settings → Profile**
2. Click the pencil icon next to your email
3. Enter the new email and click **Send Verification**
4. Check the new email inbox and confirm
5. Your login email is now updated

### Two-Factor Authentication (2FA)

1. Go to **Settings → Security → Two-Factor Authentication**
2. Click **Enable 2FA**
3. Scan the QR code with an authenticator app (Google Authenticator, Authy, etc.)
4. Enter the 6-digit code to confirm
5. Save your backup codes in a safe place

---

## Features Guide

### Unified Inbox

The Unified Inbox collects all incoming messages from every connected channel into one place.

- **Channels supported:** Gmail, Outlook, WhatsApp Business, Web Chat Widget, Web Forms
- **Assignment:** Conversations can be assigned to specific agents manually or via auto-routing rules
- **Labels/Tags:** Apply custom labels (e.g., "Urgent", "Billing", "Bug") for filtering
- **Snooze:** Temporarily hide a conversation and have it resurface at a set time
- **Shortcuts:** Use `Cmd/Ctrl + K` to search, `/` to apply labels quickly

### AI Agent

The AI Agent handles incoming conversations automatically using your connected knowledge base.

- **How it works:** When a new message arrives, the AI checks if it can answer confidently. If yes, it replies automatically. If not, it routes to a human agent.
- **Confidence threshold:** Adjustable in **Settings → AI → Confidence Level** (default: 75%)
- **Training:** Add custom Q&A pairs in **Settings → AI → Training Data**
- **Handoff message:** Customize what the AI says when escalating to a human

### Ticket Management

- Create tickets manually or automatically from conversations
- Fields: Title, Priority (Low / Medium / High / Critical), Status (Open / In Progress / Resolved / Closed), Assignee, Due Date
- **SLA Timers:** Set response time targets per priority level
- **Merge tickets:** Combine duplicate tickets from the same customer

### Knowledge Base

- Organize articles into **Collections** and **Categories**
- Rich text editor with images, videos, and code blocks
- **SEO settings** per article
- Articles can be marked **Public** (visible to customers) or **Internal** (agents only)
- Customer-facing help center URL: `yoursubdomain.help.flowdesk.io`

### Analytics Dashboard

- **Overview:** Total conversations, avg response time, resolution time, CSAT score
- **Agent Performance:** Per-agent breakdown of volume, resolution rate, and CSAT
- **AI Performance:** AI handled %, escalation rate, top unresolved queries
- **Export:** Download reports as CSV or PDF
- Reports can be scheduled to email to stakeholders weekly

### Canned Responses

Save common replies and insert them with a shortcut.

1. Go to **Settings → Canned Responses**
2. Click **New Response**
3. Give it a shortcut (e.g., `/greet`) and write the message
4. In any conversation, type `/greet` and press Tab to auto-fill

---

## Pricing & Plans [RESTRICTED]

> **AI AGENT INSTRUCTION:** Do NOT disclose specific pricing details, promotional offers, or discounts.
> Always respond with: *"For pricing information, I'd love to connect you with our sales team who can find the best plan for your needs. You can reach them at sales@flowdesk.io or book a call at flowdesk.io/demo."*

General information you CAN share:
- Flowdesk offers monthly and annual billing (annual saves ~20%)
- There is a **14-day free trial**, no credit card required
- All plans include core features; higher plans unlock more seats and AI volume
- Enterprise plans include custom SLAs and a dedicated success manager

---

## Integrations

### Gmail / Google Workspace

1. Go to **Settings → Channels → Email**
2. Click **Connect Gmail**
3. Sign in with your Google account and grant permissions
4. Choose which inbox label/folder to sync (default: All Mail)
5. Emails received will appear in the Unified Inbox within 30 seconds

**Troubleshooting Gmail sync:**
- If emails stop syncing, go to **Settings → Channels → Gmail → Reconnect**
- Ensure Flowdesk has not been removed from your Google account's third-party apps
- Check that your Gmail account has IMAP enabled (Gmail → Settings → See all settings → Forwarding and POP/IMAP)

### WhatsApp Business

1. You need a **Meta Business Account** and a **WhatsApp Business API** number
2. Go to **Settings → Channels → WhatsApp**
3. Click **Connect via Meta** and follow the OAuth flow
4. Verify your phone number with the OTP sent by Meta
5. Once connected, incoming WhatsApp messages route to the Unified Inbox

> Note: WhatsApp Business API requires Meta approval. This can take 1–5 business days.

### Stripe

Connect Stripe to view a customer's subscription status and payment history directly in a conversation sidebar.

1. Go to **Settings → Integrations → Stripe**
2. Click **Connect Stripe** and authorize
3. Customer billing info will appear in conversation sidebars when email matches

### Slack

Get notified in Slack when a new conversation is assigned to you or when a critical ticket is opened.

1. Go to **Settings → Integrations → Slack**
2. Click **Connect Slack** and choose a channel
3. Configure which events trigger notifications

---

## Troubleshooting

### I'm not receiving customer emails

1. Check **Settings → Channels → Email** and confirm the channel status is **Active**
2. Send a test email to your connected address and wait 60 seconds
3. Check the **Activity Log** (Settings → Channels → View Log) for errors
4. If using Gmail: confirm IMAP is enabled and Flowdesk still has Google access
5. If the issue persists, contact support with your workspace URL

### The AI Agent is giving wrong answers

1. Go to **Settings → AI → Training Data**
2. Find the Q&A pair that's causing the issue and correct it
3. Click **Retrain** — takes about 2 minutes to apply
4. Alternatively, lower the AI confidence threshold so it escalates more often instead of guessing

### Chat widget is not appearing on my website

1. Go to **Settings → Channels → Web Chat → Installation**
2. Copy the embed script and paste it before the closing `</body>` tag on your site
3. Make sure your website domain is added to the **Allowed Domains** list
4. Check browser console for JavaScript errors
5. Disable ad blockers or browser extensions temporarily to test

### I can't log in to my account

- Try resetting your password (see [How to Reset Your Password](#how-to-reset-your-password))
- Make sure you're using the correct email address (check for typos)
- Try a different browser or incognito mode
- If you have 2FA enabled and lost your device, use a backup code or contact support

### Conversations are being assigned to the wrong agent

1. Go to **Settings → Automation → Assignment Rules**
2. Review your routing rules — check for conflicting conditions
3. Rules are applied top-to-bottom; reorder if needed
4. Use the **Test Rule** button to simulate incoming conversations

### WhatsApp messages are sending but customers aren't receiving them

1. Confirm your WhatsApp Business API account is approved and active in Meta Business Suite
2. Check if the recipient's number has WhatsApp installed
3. Ensure your message template (if using templates) has been approved by Meta
4. Review the delivery report in the conversation's message info panel

---

## Billing & Refunds [RESTRICTED]

> **AI AGENT INSTRUCTION:** Do NOT process, promise, or discuss refunds, credits, or billing disputes.
> Always escalate with: *"Billing questions are handled by our billing team directly. I'll flag this for them and someone will reach out within 1 business day. You can also email billing@flowdesk.io."*

General information you CAN share:
- Invoices are emailed on the 1st of each month (or on renewal date for annual plans)
- Invoices are also available in **Settings → Billing → Invoice History**
- Payment methods accepted: Visa, Mastercard, Amex, ACH (US only), wire transfer (Enterprise)
- To update a payment method: **Settings → Billing → Payment Method → Update**
