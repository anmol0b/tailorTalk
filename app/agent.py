import os
import logging
from dotenv import load_dotenv
from langchain.agents import Tool, initialize_agent, AgentType
from langchain_groq import ChatGroq

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Calendar imports ──────────────────────────────────────────────────────────
try:
    from app.calendarUtils import (
        book_event_from_text,
        get_upcoming_events,
        cancel_event,
        check_availability,
    )
    CALENDAR_OK = True
except Exception as e:
    CALENDAR_OK = False
    logger.error(f"❌ calendarUtils import failed: {e}")


# ── LLM ───────────────────────────────────────────────────────────────────────
llm = None
try:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in .env")
    llm = ChatGroq(
        groq_api_key=api_key,
        model_name="meta-llama/llama-4-scout-17b-16e-instruct"
    )
    logger.info("✅ LLM initialised")
except Exception as e:
    logger.error(f"❌ LLM init failed: {e}")


# ── Tools — every func now does real work ─────────────────────────────────────
def _book(user_input: str) -> str:
    """Parse natural language and book a real Google Calendar event."""
    if not CALENDAR_OK:
        return "❌ Calendar service unavailable."
    return book_event_from_text(user_input)


def _view_events(_: str) -> str:
    """Return upcoming calendar events as formatted text."""
    if not CALENDAR_OK:
        return "❌ Calendar service unavailable."
    events = get_upcoming_events(max_results=8)
    if not events:
        return "📭 No upcoming events found."
    lines = []
    for ev in events:
        start = ev.get('start', {}).get('dateTime') or ev.get('start', {}).get('date', '')
        lines.append(f"• {ev.get('summary','Untitled')} — {start}")
    return "📅 Upcoming events:\n" + "\n".join(lines)


def _cancel(event_id: str) -> str:
    """Cancel an event by its Google Calendar event ID."""
    if not CALENDAR_OK:
        return "❌ Calendar service unavailable."
    result = cancel_event(event_id.strip())
    if result.get("success"):
        return "✅ Event cancelled successfully."
    return f"❌ Could not cancel: {result.get('error', 'unknown error')}"


tools = [
    Tool(
        name="BookMeeting",
        func=_book,
        description=(
            "Book a Google Calendar meeting from natural language. "
            "Input must include date, time, and at least one attendee email. "
            "Example: 'Book a 30-minute meeting tomorrow at 3 PM with john@example.com about design review'"
        )
    ),
    Tool(
        name="GetUpcomingEvents",
        func=_view_events,
        description=(
            "Get a list of upcoming Google Calendar events. "
            "Call this when the user asks to see their schedule, meetings, or calendar. "
            "No specific input needed."
        )
    ),
    Tool(
        name="CancelEvent",
        func=_cancel,
        description=(
            "Cancel an existing Google Calendar event by its event ID. "
            "Input should be the event ID string."
        )
    ),
]

SYSTEM_PROMPT = """You are TailorTalk, a friendly AI assistant that manages Google Calendar bookings.

You have three tools:
- BookMeeting: books a real calendar event from natural language
- GetUpcomingEvents: lists upcoming events
- CancelEvent: cancels an event by ID

Rules:
- Always use tools for calendar actions — never fake a result
- If booking details are incomplete, ask for what's missing before calling BookMeeting
- Be concise and friendly
- Format responses with emojis for readability
- Always confirm what action you took"""

# ── Agent ─────────────────────────────────────────────────────────────────────
agent_executor = None
try:
    if llm:
        agent_executor = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,
            early_stopping_method="generate",
            agent_kwargs={"system_message": SYSTEM_PROMPT},
        )
        logger.info("✅ Agent initialised")
    else:
        logger.warning("⚠️ Agent skipped — LLM not available")
except Exception as e:
    logger.error(f"❌ Agent init failed: {e}")


def get_agent_status() -> dict:
    return {
        "llm_available": llm is not None,
        "agent_available": agent_executor is not None,
        "calendar_available": CALENDAR_OK,
        "tools": [t.name for t in tools],
        "model": "meta-llama/llama-4-scout-17b-16e-instruct" if llm else None,
    }