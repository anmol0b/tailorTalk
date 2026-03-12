# TailorTalk 🗓️
> Book Google Calendar meetings in plain English — powered by LLaMA 4, LangChain, and FastAPI.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?style=flat-square)
![Streamlit](https://img.shields.io/badge/Streamlit-1.x-red?style=flat-square)
![LangChain](https://img.shields.io/badge/LangChain-0.1+-purple?style=flat-square)

---

## What it does

Type a natural language message like:

> *"Book a 30-minute call tomorrow at 3 PM with john@example.com about design review"*

TailorTalk parses the intent, checks availability, and creates a real event on your Google Calendar — no forms, no clicking.

---

## Architecture

```
Streamlit Chat UI
      │  HTTP
      ▼
FastAPI Backend  ──► Intent Detection
      │                    │
      │         ┌──────────┴──────────┐
      │       book       view       agent
      │         │          │          │
      └─────────┴──────────┘          │
                │                LangChain
         calendarUtils           + Groq LLM
                │
        Google Calendar API
```

**Stack:**
- **Frontend** — Streamlit (`streamlitApp/app.py`)
- **Backend** — FastAPI (`app/main.py`)
- **AI Agent** — LangChain + Groq LLaMA 4 Scout (`app/agent.py`)
- **Calendar** — Google Calendar API via service account (`app/calendarUtils.py`)

---

## Quickstart

### 1. Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure `.env`

```bash
cp .env.example .env
```

```env
GROQ_API_KEY=your_groq_api_key
GOOGLE_SERVICE_ACCOUNT_FILE=your-service-account.json
GOOGLE_CALENDAR_ID=your-email@gmail.com
APP_TIMEZONE=Asia/Kolkata        # optional, default: Asia/Kolkata
BACKEND_PORT=8000                # optional
FRONTEND_PORT=8501               # optional
```

### 3. Google Calendar setup

1. Go to [Google Cloud Console](https://console.cloud.google.com) → enable **Google Calendar API**
2. Create a **Service Account** → download the JSON credentials → place it in the project root
3. Open [Google Calendar](https://calendar.google.com) → Settings → your calendar → **Share with specific people**
4. Add your service account email (found in the JSON as `client_email`) with **"Make changes to events"** permission
5. Run the one-time setup to link the calendar:

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
creds = service_account.Credentials.from_service_account_file(
    os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE'),
    scopes=['https://www.googleapis.com/auth/calendar']
)
service = build('calendar', 'v3', credentials=creds)
result = service.calendarList().insert(body={'id': os.getenv('GOOGLE_CALENDAR_ID')}).execute()
print('Linked:', result.get('id'))
"
```

### 4. Run

```bash
python start.py
```

| Service  | URL |
|----------|-----|
| Frontend | http://localhost:8501 |
| Backend  | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

Or run manually in two terminals:

```bash
# Terminal 1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
streamlit run streamlitApp/app.py --server.port 8501
```

---

## Example prompts

| Intent | Example |
|--------|---------|
| Book a meeting | `Book a 30-min call tomorrow at 3 PM with john@example.com about onboarding` |
| Schedule for next week | `Schedule a 1-hour sprint planning next Monday at 10 AM with team@company.com` |
| View schedule | `Show my upcoming meetings` |
| General help | `What can you do?` |

---

## Verify it's working

```bash
# Health check
curl http://localhost:8000/health

# Test booking via API directly
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Book a meeting tomorrow at 3 PM with john@example.com", "chat_history": []}'
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Failed to initialize Google Calendar service` | Check `GOOGLE_SERVICE_ACCOUNT_FILE` path in `.env` |
| `Calendar service not available` (404) | Run the one-time calendar link script in step 3 above |
| `forbiddenForServiceAccounts` (403) | Ensure attendees are not passed as formal invites — stored in description instead |
| `ModuleNotFoundError` | Activate your virtualenv: `source .venv/bin/activate` |
| Frontend shows backend offline | Make sure `python start.py` is running and backend is on port 8000 |

---

## Project structure

```
tailorTalk/
├── app/
│   ├── main.py           # FastAPI routes + intent detection
│   ├── agent.py          # LangChain agent + Groq LLM
│   └── calendarUtils.py  # Google Calendar API wrapper
├── streamlitApp/
│   └── app.py            # Streamlit chat UI
├── start.py              # Launches both services
├── requirements.txt
└── .env.example
```

---

## Roadmap

- [ ] OAuth2 login — let any user connect their own Google Calendar
- [ ] Cancel meetings by title/date
- [ ] Telegram bot interface
- [ ] Deployed public demo

---

## License

MIT