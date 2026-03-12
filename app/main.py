from typing import List, Tuple, Dict, Any
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TailorTalk API", version="1.0.0")

# ── Calendar utilities ────────────────────────────────────────────────────────
try:
    from app.calendarUtils import book_event_from_text, get_upcoming_events, get_calendar_info
    CALENDAR_AVAILABLE = True
    logger.info("✅ calendarUtils loaded")
except Exception as e:
    CALENDAR_AVAILABLE = False
    logger.error(f"❌ calendarUtils failed: {e}")

# ── Agent (optional fallback) ─────────────────────────────────────────────────
try:
    from app.agent import agent_executor, get_agent_status
    AGENT_AVAILABLE = agent_executor is not None
    logger.info("✅ Agent loaded")
except Exception as e:
    AGENT_AVAILABLE = False
    logger.error(f"❌ Agent failed: {e}")


class ChatInput(BaseModel):
    user_input: str
    chat_history: List[Tuple[str, str]] = []


def detect_intent(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']):
        return "greet"
    if any(w in t for w in ['help', 'what can you do', 'capabilities', 'commands']):
        return "help"
    if any(w in t for w in ['cancel', 'delete', 'remove']):
        return "cancel"
    if any(w in t for w in ['show', 'list', 'upcoming', 'what meetings', 'my schedule', 'my calendar', 'my meetings', 'do i have']):
        return "view"
    if any(w in t for w in ['book', 'schedule', 'arrange', 'set up', 'create', 'add']) and \
       any(w in t for w in ['meeting', 'appointment', 'call', 'session', 'event']):
        return "book"
    return "agent"


def format_events(events: list) -> str:
    if not events:
        return "📭 No upcoming events found on your calendar."
    lines = ["📅 **Your upcoming events:**\n"]
    for ev in events:
        dt_str = ev.get('start', {}).get('dateTime') or ev.get('start', {}).get('date', '')
        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            formatted = dt.strftime('%A, %b %d at %I:%M %p')
        except Exception:
            formatted = dt_str
        title = ev.get('summary', 'Untitled')
        attendees = ev.get('attendees', [])
        link = ev.get('htmlLink', '')
        lines.append(f"**{title}**  🕐 {formatted}")
        if attendees:
            lines.append(f"  👥 {', '.join(a['email'] for a in attendees)}")
        if link:
            lines.append(f"  🔗 [Open in Calendar]({link})")
        lines.append("")
    return '\n'.join(lines)


@app.post("/chat")
async def chat(payload: ChatInput):
    user_input = payload.user_input.strip()
    intent = detect_intent(user_input)
    logger.info(f"Intent={intent} | '{user_input}'")

    if intent == "greet":
        return {"response": (
            "👋 Hey! I'm TailorTalk — your AI calendar assistant.\n\n"
            "Try: *\"Book a 30-min call tomorrow at 3 PM with john@example.com about onboarding\"*"
        )}

    if intent == "help":
        return {"response": (
            "🤖 **What I can do:**\n\n"
            "📅 **Book** → *\"Book a 1-hour call next Monday at 2 PM with team@company.com\"*\n"
            "📋 **View** → *\"Show my upcoming meetings\"*\n"
            "❌ **Cancel** → *\"Cancel my 3 PM meeting tomorrow\"* *(coming soon)*"
        )}

    if intent == "view":
        if not CALENDAR_AVAILABLE:
            return {"response": "⚠️ Calendar unavailable — check `GOOGLE_SERVICE_ACCOUNT_FILE` and `GOOGLE_CALENDAR_ID` in `.env`"}
        return {"response": format_events(get_upcoming_events(max_results=8))}

    if intent == "book":
        if not CALENDAR_AVAILABLE:
            return {"response": "⚠️ Calendar unavailable — check your `.env` settings"}
        # ✅ Real booking — hits Google Calendar API via calendarUtils
        result = book_event_from_text(user_input)
        if "Couldn't parse" in result:
            return {"response": (
                "I need a bit more info:\n\n"
                "• **Date** — *tomorrow / next Monday / 2025-06-15*\n"
                "• **Time** — *3 PM / 14:30*\n"
                "• **Email** — *john@example.com*\n"
                "• **Duration** *(optional)* — default 30 min\n"
                "• **Topic** *(optional)*\n\n"
                "Example: *\"Book a 30-min call tomorrow at 3 PM with john@example.com about design review\"*"
            )}
        return {"response": result}

    if intent == "cancel":
        return {"response": "To cancel, tell me the **meeting title + date**. *(Full cancel support coming soon)*"}

    # ── Fallback: LangChain agent ─────────────────────────────────────────────
    if AGENT_AVAILABLE:
        try:
            history = [("human" if r == "user" else "assistant", c) for r, c in payload.chat_history]
            reply = agent_executor.invoke({"input": user_input, "chat_history": history})
            if isinstance(reply, dict):
                reply = reply.get("output") or reply.get("response") or str(reply)
            return {"response": reply.strip()}
        except Exception as e:
            logger.error(f"Agent error: {e}")

    return {"response": "Not sure how to help — try *\"book a meeting\"* or *\"show my schedule\"*"}


@app.get("/health")
async def health_check():
    info: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "calendar_available": CALENDAR_AVAILABLE,
        "agent_available": AGENT_AVAILABLE,
    }
    if CALENDAR_AVAILABLE:
        try: info["calendar"] = get_calendar_info()
        except Exception: pass
    if AGENT_AVAILABLE:
        try: info["agent"] = get_agent_status()
        except Exception: pass
    return info

@app.get("/")
async def root():
    return {"message": "TailorTalk API v1.0", "docs": "/docs"}