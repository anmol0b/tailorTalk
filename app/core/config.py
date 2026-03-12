import os
from dotenv import load_dotenv

load_dotenv()

# Google Calendar
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json")
GOOGLE_CALENDAR_ID          = os.getenv("GOOGLE_CALENDAR_ID")
APP_TIMEZONE                = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

# Groq / LLM
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
GROQ_MODEL     = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# Server
BACKEND_PORT  = int(os.getenv("BACKEND_PORT", 8000))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", 8501))
BACKEND_URL   = os.getenv("TAILORTALK_BACKEND_URL", f"http://127.0.0.1:{BACKEND_PORT}")