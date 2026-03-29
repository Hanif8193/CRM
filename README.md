# Customer Success AI Agent

A Digital FTE (Full-Time Employee) powered by Claude AI that handles customer support across Web, Gmail, and WhatsApp.

## Project Structure

```
CRM/
├── backend/               # FastAPI backend
│   ├── main.py            # App entry point
│   ├── config.py          # Environment config
│   ├── requirements.txt   # Python dependencies
│   ├── agent/
│   │   └── agent.py       # Claude AI agent logic
│   ├── channels/
│   │   ├── web.py         # Web chat handler
│   │   ├── gmail.py       # Gmail handler
│   │   └── whatsapp.py    # WhatsApp handler
│   ├── api/
│   │   └── routes.py      # API endpoints
│   └── models/
│       └── schemas.py     # Pydantic models
├── frontend/              # Next.js frontend
│   ├── pages/
│   │   └── index.js       # Main page
│   └── components/
│       └── ChatWidget.js  # Chat UI component
├── database/
│   └── schema.sql         # PostgreSQL schema
└── README.md
```

## Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # Fill in your API keys
uvicorn main:app --reload
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

### 3. Database

```bash
psql -U postgres -d crm_db -f database/schema.sql
```

## Channels

| Channel    | How it works |
|------------|-------------|
| Web        | Chat widget on the frontend, calls `/api/chat` |
| WhatsApp   | Meta Cloud API webhook at `/api/webhook/whatsapp` |
| Gmail      | Google push notifications at `/api/webhook/gmail` |

## API Endpoints

- `POST /api/chat` — Web chat
- `POST /api/webhook/whatsapp` — WhatsApp webhook
- `POST /api/webhook/gmail` — Gmail webhook
- `GET  /api/health` — Health check
