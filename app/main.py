from typing import List, Tuple, Dict, Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TailorTalk API", version="1.0.0")

# ── Calendar utilities ────────────────────────────────────────────────────────
try:
    from app.calendarUtils import (
        book_event_from_text, get_upcoming_events,
        get_calendar_info, parse_meeting_details
    )
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


# ── Schemas ───────────────────────────────────────────────────────────────────
class ChatInput(BaseModel):
    user_input: str
    chat_history: List[Tuple[str, str]] = []
    # Per-user booking session state passed from frontend
    pending_booking: Optional[Dict[str, Any]] = None
    attempt_count: int = 0


class ChatResponse(BaseModel):
    response: str
    pending_booking: Optional[Dict[str, Any]] = None
    attempt_count: int = 0


MAX_ATTEMPTS = 3


# ── Intent detection ──────────────────────────────────────────────────────────
def detect_intent(text: str) -> str:
    t = text.lower().strip()

    # Book checked first — prevents substrings like 'hi' inside booking msgs
    if any(w in t for w in ['book', 'schedule', 'arrange', 'set up', 'create', 'add']) and \
       any(w in t for w in ['meeting', 'appointment', 'call', 'session', 'event']):
        return "book"

    greet_words = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
    if len(t.split()) <= 5 and any(t == w or t.startswith(w + ' ') for w in greet_words):
        return "greet"

    if any(w in t for w in ['help', 'what can you do', 'capabilities', 'commands']):
        return "help"
    if any(w in t for w in ['cancel', 'delete', 'remove']):
        return "cancel"
    if any(w in t for w in ['show', 'list', 'upcoming', 'what meetings', 'my schedule', 'my calendar', 'my meetings', 'do i have']):
        return "view"

    return "agent"


# ── Booking detail extraction helpers ────────────────────────────────────────
def extract_partial_details(text: str) -> Dict[str, Any]:
    """Extract whatever booking details are present, even if incomplete."""
    found = {}
    t = text.lower()

    # Date
    if re.search(r'\btomorrow\b', t):
        found['date_hint'] = 'tomorrow'
    elif re.search(r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', t):
        found['date_hint'] = re.search(r'\bnext\s+\w+\b', t).group()
    elif re.search(r'\b\d{4}-\d{2}-\d{2}\b', t):
        found['date_hint'] = re.search(r'\b\d{4}-\d{2}-\d{2}\b', t).group()
    elif re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', t):
        found['date_hint'] = re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', t).group()

    # Time
    time_match = re.search(r'\b(\d{1,2}(?::\d{2})?)\s*(am|pm)\b', t) or \
                 re.search(r'\b(\d{1,2}:\d{2})\b', t)
    if time_match:
        found['time_hint'] = time_match.group()

    # Duration
    dur_match = re.search(r'\b(\d+)\s*(minute|min|hour|hr)s?\b', t)
    if dur_match:
        found['duration_hint'] = dur_match.group()

    # Topic/agenda
    topic_match = re.search(r'\babout\s+(.*?)(?=\s+(?:with|for|at\s+\d)|$)', text, re.IGNORECASE)
    if topic_match:
        found['topic_hint'] = topic_match.group(1).strip()

    # Email
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    if emails:
        found['emails'] = emails

    return found


def what_is_missing(details: Dict[str, Any]) -> List[str]:
    """Return list of required fields still missing."""
    missing = []
    if 'date_hint' not in details:
        missing.append('date')
    if 'time_hint' not in details:
        missing.append('time')
    if not details.get('emails'):
        missing.append('email')
    return missing  # topic is optional


def ask_for_missing(missing: List[str], attempt: int) -> str:
    """Generate a focused question for the missing fields."""
    questions = {
        'date': "📅 What **date** should I book it for? *(e.g. tomorrow, next Monday, June 15)*",
        'time': "🕐 What **time** works? *(e.g. 3 PM, 14:30)*",
    }
    if len(missing) == 2:
        return (
            "I need just two things to book this:\n\n"
            f"{questions['date']}\n"
            f"{questions['time']}"
        )
    return questions[missing[0]]


def merge_details(existing: Dict, new_text: str) -> Dict:
    """Merge newly extracted details into the existing partial booking."""
    new = extract_partial_details(new_text)
    merged = {**existing, **new}
    # Also append any topic text from the original booking intent
    if 'topic_hint' not in merged:
        topic = re.search(r'\babout\s+(.*?)(?=\s+(?:with|for|at\s+\d)|$)', new_text, re.IGNORECASE)
        if topic:
            merged['topic_hint'] = topic.group(1).strip()
    return merged


def build_booking_text(details: Dict, original_input: str) -> str:
    """Reconstruct a full booking sentence from accumulated details."""
    parts = ["Book a meeting"]
    if details.get('duration_hint'):
        parts = [f"Book a {details['duration_hint']} meeting"]
    if details.get('date_hint'):
        parts.append(details['date_hint'])
    if details.get('time_hint'):
        parts.append(f"at {details['time_hint']}")
    if details.get('emails'):
        parts.append(f"with {' '.join(details['emails'])}")
    if details.get('topic_hint'):
        parts.append(f"about {details['topic_hint']}")
    return ' '.join(parts)


# ── Format upcoming events ────────────────────────────────────────────────────
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


# ── /chat ─────────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatInput):
    user_input = payload.user_input.strip()
    pending    = payload.pending_booking  # accumulated partial booking details
    attempts   = payload.attempt_count

    # ── If we're mid-booking conversation, treat this reply as booking info ──
    if pending is not None:
        # User might be abandoning
        if any(w in user_input.lower() for w in ['cancel', 'stop', 'forget it', 'never mind', 'skip']):
            return ChatResponse(
                response="No problem, I've cancelled that booking. What else can I help with?",
                pending_booking=None,
                attempt_count=0
            )

        # Merge new info into what we already have
        updated = merge_details(pending, user_input)
        missing = what_is_missing(updated)

        if not missing:
            # We have everything — try to book
            booking_text = build_booking_text(updated, user_input)
            logger.info(f"Completing booking with: {booking_text}")
            result = book_event_from_text(booking_text)
            return ChatResponse(response=result, pending_booking=None, attempt_count=0)

        # Still missing info
        attempts += 1
        if attempts >= MAX_ATTEMPTS:
            return ChatResponse(
                response=(
                    "I wasn't able to get all the details needed to book this. "
                    "Feel free to try again anytime with something like:\n\n"
                    "*\"Book a 30-min call tomorrow at 3 PM about design review\"*"
                ),
                pending_booking=None,
                attempt_count=0
            )

        # Ask again (attempts remaining)
        remaining = MAX_ATTEMPTS - attempts
        question = ask_for_missing(missing, attempts)
        return ChatResponse(
            response=f"{question}\n\n*({remaining} attempt{'s' if remaining > 1 else ''} remaining)*",
            pending_booking=updated,
            attempt_count=attempts
        )

    # ── Normal intent routing ─────────────────────────────────────────────────
    intent = detect_intent(user_input)
    logger.info(f"Intent={intent} | '{user_input}'")

    if intent == "greet":
        return ChatResponse(response=(
            "👋 Hey! I'm TailorTalk — your AI calendar assistant.\n\n"
            "Just describe what you need:\n"
            "*\"Book a 30-min call tomorrow at 3 PM about design review\"*\n\n"
            "I'll ask for anything I'm missing."
        ))

    if intent == "help":
        return ChatResponse(response=(
            "🤖 **What I can do:**\n\n"
            "📅 **Book a meeting** — describe it naturally\n"
            "> *\"Book a 1-hour call next Monday at 2 PM about sprint planning\"*\n\n"
            "📋 **View your schedule**\n"
            "> *\"Show my upcoming meetings\"*\n\n"
            "❌ **Cancel a meeting** *(coming soon)*\n\n"
            "If details are missing, I'll ask — max 3 follow-up questions."
        ))

    if intent == "view":
        if not CALENDAR_AVAILABLE:
            return ChatResponse(response="⚠️ Calendar unavailable — check your `.env` settings")
        return ChatResponse(response=format_events(get_upcoming_events(max_results=8)))

    if intent == "book":
        if not CALENDAR_AVAILABLE:
            return ChatResponse(response="⚠️ Calendar unavailable — check your `.env` settings")

        # Try to book immediately with what we have
        parsed = None
        try:
            parsed = parse_meeting_details(user_input)
        except Exception:
            pass

        if parsed:
            # All required fields present — book right away
            result = book_event_from_text(user_input)
            if "Couldn't parse" not in result:
                return ChatResponse(response=result, pending_booking=None, attempt_count=0)

        # Missing required fields — extract what we have and start asking
        partial = extract_partial_details(user_input)
        missing = what_is_missing(partial)

        if not missing:
            # parse_meeting_details failed for another reason, try direct booking
            result = book_event_from_text(user_input)
            return ChatResponse(response=result)

        question = ask_for_missing(missing, 0)
        remaining = MAX_ATTEMPTS
        return ChatResponse(
            response=f"{question}\n\n*({remaining} attempts remaining)*",
            pending_booking=partial,
            attempt_count=0
        )

    if intent == "cancel":
        return ChatResponse(response="To cancel, tell me the **meeting title + date**. *(Full cancel support coming soon)*")

    # ── Fallback: LangChain agent ─────────────────────────────────────────────
    if AGENT_AVAILABLE:
        try:
            history = [("human" if r == "user" else "assistant", c) for r, c in payload.chat_history]
            reply = agent_executor.invoke({"input": user_input, "chat_history": history})
            if isinstance(reply, dict):
                reply = reply.get("output") or reply.get("response") or str(reply)
            return ChatResponse(response=reply.strip())
        except Exception as e:
            logger.error(f"Agent error: {e}")

    return ChatResponse(response="Not sure how to help — try *\"book a meeting\"* or *\"show my schedule\"*")


# ── /health ───────────────────────────────────────────────────────────────────
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