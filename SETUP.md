# CRM AI Agent — مکمل Setup گائیڈ
## Complete Setup Guide (Windows & Linux)

---

## فہرست / Table of Contents

1. [پروجیکٹ کی ساخت](#structure)
2. [ضروریات](#prerequisites)
3. [.env ترتیب](#env-setup)
4. [Gmail OAuth (ایک بار)](#gmail-oauth)
5. [Docker سے چلائیں](#docker)
6. [بغیر Docker (Local Dev)](#local-dev)
7. [Tests چلائیں](#tests)
8. [Kafka Workers Scale کریں](#kafka-scale)
9. [`send_gmail_reply` استعمال کی مثال](#gmail-example)
10. [عام مسائل](#troubleshooting)

---

## 1. پروجیکٹ کی ساخت {#structure}

```
CRM/
├── .env.example                   ← تمام environment variables (یہاں سے .env بنائیں)
├── Dockerfile                     ← Multi-stage Python 3.11 build
├── docker-compose.yml             ← مکمل stack: backend + postgres + kafka + frontend
│
├── database/
│   └── schema.sql                 ← PostgreSQL schema (idempotent)
│
└── backend/
    ├── main.py                    ← FastAPI entry point
    ├── config.py                  ← تمام env vars یہاں لوڈ ہوتے ہیں
    ├── logging_config.py          ← Structured JSON logging + Sentry
    ├── requirements.txt           ← Python dependencies
    │
    ├── channels/
    │   ├── gmail.py               ← Gmail OAuth2 + send_gmail_reply()
    │   ├── whatsapp.py            ← WhatsApp Meta API
    │   └── web.py                 ← Web chat channel
    │
    ├── kafka/
    │   ├── producer.py            ← Async producer (fte.tickets.incoming)
    │   └── consumer.py            ← Worker (fte.tickets.incoming → AI → fte.responses.outgoing)
    │
    ├── middleware/
    │   └── rate_limit.py          ← Sliding-window IP rate limiter
    │
    ├── database/
    │   ├── connection.py          ← PostgreSQL connection pool
    │   └── operations.py          ← CRUD: conversations, messages, tickets
    │
    ├── agent/
    │   ├── agent.py               ← Main AI agent (cached, doc-search, Claude)
    │   └── simple_agent.py        ← Extended agent with memory
    │
    └── tests/
        ├── conftest.py            ← Fixtures: DB + Kafka mocked
        └── test_agent.py          ← 20+ pytest tests
```

---

## 2. ضروریات {#prerequisites}

### Windows پر:
```powershell
# Docker Desktop install کریں
# https://www.docker.com/products/docker-desktop/
# پھر PowerShell میں چیک کریں:
docker --version
docker-compose --version

# Python (بغیر Docker tests کے لیے)
python --version   # 3.11+ چاہیے
```

### Linux پر:
```bash
# Docker اور Docker Compose install کریں
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER   # logout/login کے بعد sudo کے بغیر چلے

# چیک کریں
docker --version
docker compose version

# Python
python3 --version   # 3.11+
```

---

## 3. Environment Variables سیٹ کریں {#env-setup}

### Windows:
```powershell
# CRM فولڈر میں جائیں
cd "C:\Users\pc\Desktop\My Projects\CRM"

# .env.example کاپی کریں
copy .env.example .env

# نوٹ پیڈ میں کھولیں
notepad .env
```

### Linux/Mac:
```bash
cd ~/projects/CRM
cp .env.example .env
nano .env
# یا: code .env
```

### `.env` میں کیا بھرنا ہے:

```env
# ─── ضروری (بغیر ان کے ایپ نہیں چلے گی) ──────────────────────────────────

# Anthropic AI key
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Gmail credentials فائل کی جگہ
GMAIL_CREDENTIALS_PATH=gmail_credentials.json
GMAIL_TOKEN_PATH=gmail_token.json

# CORS — اپنا frontend domain ڈالیں
ALLOWED_ORIGINS=http://localhost:3000

# ─── اختیاری (ان کے بغیر بھی چلے گا) ────────────────────────────────────

# WhatsApp (Meta Cloud API سے لیں)
WHATSAPP_API_TOKEN=your_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_id_here

# Sentry error tracking (خالی چھوڑیں اگر نہیں چاہیے)
SENTRY_DSN=

# Rate limiting (default: 5 requests per 60 seconds)
RATE_LIMIT_REQUESTS=5
RATE_LIMIT_WINDOW=60

# Production CORS
# ALLOWED_ORIGINS=https://mycrm.com,https://app.mycrm.com
```

---

## 4. Gmail OAuth — ایک بار کا کام {#gmail-oauth}

> ⚠️ یہ صرف ایک بار کرنا ہے۔ بعد میں ٹوکن خودبخود refresh ہوتا رہے گا۔

### مرحلہ 1: Google Cloud Console سے credentials بنائیں

1. [console.cloud.google.com](https://console.cloud.google.com) کھولیں
2. نیا project بنائیں یا موجودہ چنیں
3. **APIs & Services → Enable APIs** → **Gmail API** enable کریں
4. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop application**
6. JSON ڈاؤنلوڈ کریں
7. فائل کا نام `gmail_credentials.json` رکھیں اور `backend/` فولڈر میں رکھیں

### مرحلہ 2: Interactive OAuth Flow چلائیں

#### Windows:
```powershell
cd "C:\Users\pc\Desktop\My Projects\CRM\backend"

# Virtual environment بنائیں
python -m venv venv
venv\Scripts\activate

# Dependencies install کریں
pip install -r requirements.txt

# OAuth flow چلائیں (براؤزر کھلے گا)
python -c "from channels.gmail import _get_gmail_service; _get_gmail_service()"
```

#### Linux:
```bash
cd ~/projects/CRM/backend

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python3 -c "from channels.gmail import _get_gmail_service; _get_gmail_service()"
```

### مرحلہ 3: براؤزر میں اجازت دیں

1. براؤزر خودبخود کھلے گا
2. اپنا Google account چنیں
3. **"Allow"** کلک کریں
4. Terminal میں `gmail_token.json محفوظ ہو گیا` نظر آئے گا ✅

---

## 5. Docker سے مکمل stack چلائیں {#docker}

```bash
# CRM فولڈر میں جائیں
cd "C:\Users\pc\Desktop\My Projects\CRM"   # Windows
# یا
cd ~/projects/CRM                           # Linux

# پہلی بار یا code تبدیل ہونے پر
docker-compose up --build

# Background میں چلائیں
docker-compose up --build -d

# Logs دیکھیں
docker-compose logs -f backend
docker-compose logs -f kafka-worker

# بند کریں
docker-compose down

# بند کریں اور تمام data حذف کریں (fresh start)
docker-compose down -v
```

### Services جو چلیں گے:

| Service      | Port  | مقصد                              |
|--------------|-------|-----------------------------------|
| backend      | 8000  | FastAPI — http://localhost:8000   |
| frontend     | 3000  | Next.js — http://localhost:3000   |
| postgres     | 5432  | PostgreSQL database               |
| kafka        | 9092  | Kafka broker                      |
| zookeeper    | 2181  | Kafka کا coordinator               |
| kafka-worker | —     | AI agent worker                   |

### چیک کریں سب ٹھیک ہے:
```bash
# Health check
curl http://localhost:8000/api/health
# جواب: {"status": "healthy"}

# Swagger UI
# http://localhost:8000/docs کھولیں
```

---

## 6. بغیر Docker — Local Development {#local-dev}

### PostgreSQL چلائیں:
```bash
# Windows — PostgreSQL install ہو تو:
# pgAdmin کھولیں اور crm_db database بنائیں

# Linux:
sudo -u postgres psql
CREATE DATABASE crm_db;
\q

# Schema apply کریں:
psql -U postgres -d crm_db -f database/schema.sql
```

### Backend چلائیں:
```bash
cd backend

# Windows:
venv\Scripts\activate
uvicorn main:app --reload --port 8000

# Linux:
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

### Kafka Consumer چلائیں (الگ terminal):
```bash
cd backend

# Windows:
venv\Scripts\activate
python -m kafka.consumer

# Linux:
source venv/bin/activate
python3 -m kafka.consumer
```

### Frontend چلائیں:
```bash
cd frontend
npm install
npm run dev
# http://localhost:3000 کھولیں
```

---

## 7. Tests چلائیں (Docker کی ضرورت نہیں) {#tests}

Tests میں DB اور Kafka مکمل طور پر mock ہیں — کوئی external service نہیں چاہیے۔

```bash
cd backend

# Windows:
venv\Scripts\activate
pytest tests/test_agent.py -v

# Linux:
source venv/bin/activate
pytest tests/test_agent.py -v

# مخصوص test چلائیں
pytest tests/test_agent.py::TestAngryCustomer -v
pytest tests/test_agent.py::TestPricingEscalation -v
pytest tests/test_agent.py::TestWhatsAppFormatting -v
pytest tests/test_agent.py::TestGmailReply -v

# Coverage کے ساتھ
pip install pytest-cov
pytest tests/test_agent.py --cov=. --cov-report=html
# htmlcov/index.html کھولیں
```

### متوقع output:
```
tests/test_agent.py::TestInputValidation::test_empty_message_returns_422 PASSED
tests/test_agent.py::TestInputValidation::test_whitespace_only_message_returns_422 PASSED
tests/test_agent.py::TestAngryCustomer::test_angry_message_escalates[...] PASSED
tests/test_agent.py::TestPricingEscalation::test_pricing_message_escalates[...] PASSED
tests/test_agent.py::TestWhatsAppFormatting::test_whatsapp_response_is_short[...] PASSED
tests/test_agent.py::TestGmailReply::test_send_gmail_reply_calls_api PASSED
tests/test_agent.py::TestRateLimiting::test_rate_limit_triggers_on_excess_requests PASSED
...
20 passed in 8.3s
```

---

## 8. Kafka Workers Scale کریں {#kafka-scale}

```bash
# 3 parallel workers چلائیں (3 partitions کے لیے)
docker-compose up --scale kafka-worker=3

# چیک کریں workers چل رہے ہیں
docker-compose ps

# ہر worker کے logs الگ دیکھیں
docker-compose logs kafka-worker
```

> **نوٹ:** kafka_workers کی تعداد Kafka partitions سے زیادہ نہیں ہونی چاہیے۔
> `docker-compose.yml` میں `KAFKA_NUM_PARTITIONS: 3` ہے، یعنی زیادہ سے زیادہ 3 workers۔

---

## 9. `send_gmail_reply` استعمال کی مثال {#gmail-example}

### سادہ جواب بھیجنا:
```python
from channels.gmail import send_gmail_reply

# نئی ای میل بھیجیں (کسی thread کے بغیر)
result = send_gmail_reply(
    to_email="customer@example.com",
    subject="آپ کی مدد کے لیے",
    body="آپ کا مسئلہ ہماری ٹیم کو بھیج دیا گیا ہے۔ 24 گھنٹے میں جواب ملے گا۔",
)
print(result["id"])        # Gmail message ID
print(result["threadId"])  # Gmail thread ID
```

### موجودہ thread میں جواب:
```python
from channels.gmail import send_gmail_reply

# webhook سے ملنے والا thread_id اور message_id استعمال کریں
result = send_gmail_reply(
    to_email    = "customer@example.com",
    subject     = "Re: پاس ورڈ reset نہیں ہو رہا",
    body        = (
        "آپ کی ای میل ملی۔\n\n"
        "پاس ورڈ reset کرنے کے لیے:\n"
        "1. app.flowdesk.io/login کھولیں\n"
        "2. 'Forgot Password' پر کلک کریں\n"
        "3. اپنی ای میل ڈالیں\n"
        "4. inbox چیک کریں (60 منٹ میں link expire ہو جاتا ہے)\n\n"
        "مزید مدد چاہیے تو بتائیں۔"
    ),
    thread_id   = "17abc123def456",         # اصل thread ID
    in_reply_to = "<xyz@mail.gmail.com>",   # اصل ای میل کا Message-ID
)
print(f"✅ جواب بھیجا گیا: {result['id']}")
```

### Webhook endpoint میں استعمال:
```python
# backend/api/routes.py میں
@router.post("/webhook/gmail")
def gmail_webhook(payload: dict):
    from channels.gmail import handle_gmail_message

    result = handle_gmail_message(
        sender_email = payload.get("from", ""),
        subject      = payload.get("subject", ""),
        body         = payload.get("body", ""),
        thread_id    = payload.get("threadId"),
        message_id   = payload.get("messageId"),
    )
    # handle_gmail_message خودبخود send_gmail_reply کال کرتا ہے
    return {"status": "ok", "escalated": result["escalated"]}
```

---

## 10. عام مسائل {#troubleshooting}

### مسئلہ: `gmail_credentials.json نہیں ملی`
```bash
# فائل یہاں ہونی چاہیے:
backend/gmail_credentials.json
# یا .env میں path دیں:
GMAIL_CREDENTIALS_PATH=/full/path/to/gmail_credentials.json
```

### مسئلہ: PostgreSQL connect نہیں ہو رہا
```bash
# چیک کریں Docker postgres چل رہا ہے:
docker-compose ps postgres
# Local dev میں .env چیک کریں:
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/crm_db
```

### مسئلہ: Kafka timeout
```bash
# Kafka کا health چیک کریں:
docker-compose ps kafka
docker-compose logs kafka

# Kafka کے بغیر بھی ایپ چلتی ہے — صرف warning آئے گا
# اگر Kafka نہیں چاہیے تو kafka-worker service کو comment کریں
```

### مسئلہ: `ModuleNotFoundError`
```bash
# Windows:
venv\Scripts\activate
pip install -r requirements.txt

# Linux:
source venv/bin/activate
pip3 install -r requirements.txt
```

### مسئلہ: CORS error frontend میں
```env
# .env میں اپنا frontend URL ڈالیں:
ALLOWED_ORIGINS=http://localhost:3000

# Production:
ALLOWED_ORIGINS=https://mycrm.com,https://app.mycrm.com
```

### مسئلہ: Rate limit (429 error)
```env
# .env میں limit بڑھائیں:
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW=60
```

---

## Quick Reference — فوری حوالہ

```bash
# ─── Docker Commands ────────────────────────────────────────────
docker-compose up --build          # build اور چلائیں
docker-compose up -d               # background میں
docker-compose down                # بند کریں
docker-compose down -v             # بند کریں + data حذف
docker-compose logs -f backend     # backend logs
docker-compose up --scale kafka-worker=3  # 3 workers

# ─── Tests ──────────────────────────────────────────────────────
pytest tests/test_agent.py -v                        # سب tests
pytest tests/test_agent.py::TestAngryCustomer -v     # ایک class
pytest tests/test_agent.py -k "angry" -v             # keyword سے

# ─── Gmail OAuth ────────────────────────────────────────────────
python -c "from channels.gmail import _get_gmail_service; _get_gmail_service()"

# ─── API Test ───────────────────────────────────────────────────
curl -X POST http://localhost:8000/api/message \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"test1","channel":"web","message":"پاس ورڈ reset کیسے کروں؟"}'
```
