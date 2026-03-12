# TailorTalk

AI calendar booking assistant with:
- `FastAPI` backend (`app/main.py`)
- `Streamlit` chat frontend (`streamlitApp/app.py`)
- Google Calendar integration (`app/calendarUtils.py`)
- Optional LangChain + Groq assistant (`app/agent.py`)

## Restart This Old Project

### 1. Create a clean Python environment
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure environment
Copy and edit the env file:
```bash
cp .env.example .env
```

Required in `.env`:
- `GROQ_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_FILE` (path to your service-account JSON)
- `GOOGLE_CALENDAR_ID` (calendar to write events to)

Optional in `.env`:
- `APP_TIMEZONE` (default: `Asia/Kolkata`)
- `BACKEND_PORT` (default: `8000`)
- `FRONTEND_PORT` (default: `8501`)

### 3. Google Calendar setup
1. Enable Google Calendar API in your Google Cloud project.
2. Create a service account and download JSON credentials.
3. Put the JSON in the project root (or update `GOOGLE_SERVICE_ACCOUNT_FILE`).
4. Share your target Google Calendar with the service-account email.
5. Set `GOOGLE_CALENDAR_ID` to that shared calendar ID.

## Run

### Option A: Single command (recommended)
```bash
python start.py
```

### Option B: Two terminals
Terminal 1:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:
```bash
streamlit run streamlitApp/app.py --server.port 8501 --server.address 0.0.0.0
```

## Verify

Backend health:
```bash
curl http://localhost:8000/health
```

Chat endpoint:
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"user_input":"Book a meeting tomorrow at 3 PM with john@example.com","chat_history":[]}'
```

Frontend:
- Open `http://localhost:8501`

## Notes From Revival Pass

- Startup script now uses env-configurable ports and service-account file paths.
- Calendar integration no longer hardcodes timezone/calendar defaults; it reads `.env`.
- `.env.example` reflects actual config keys used by the app.
- `.gitignore` now excludes common local Python artifacts.

## Common Issues

- `ModuleNotFoundError`: your virtualenv is not active, or dependencies were not installed.
- `Failed to initialize Google Calendar service`: service-account JSON path is wrong or invalid.
- Calendar writes fail: calendar not shared with service account, or `GOOGLE_CALENDAR_ID` is incorrect.
- Frontend shows backend offline: backend not running on expected port.

## Next Build Steps (Recommended)

1. Add automated tests for `extract_meeting_details` and `parse_meeting_details`.
2. Add a proper `Makefile`/task runner (`make setup`, `make run`, `make test`).
3. Add request/response schemas and stricter validation for `/chat` and `/book_meeting`.
4. Add structured logging and centralized error responses.
