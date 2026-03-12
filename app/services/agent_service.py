import logging
from typing import List, Tuple

from app.core.config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger(__name__)

_agent = None
_llm   = None

try:
    from langchain.agents import Tool, initialize_agent, AgentType
    from langchain_groq import ChatGroq
    from app.services.calendar_service import (
        book_event_from_text,
        get_upcoming_events,
        cancel_event,
    )

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")

    _llm = ChatGroq(groq_api_key=GROQ_API_KEY, model_name=GROQ_MODEL)

    def _view(_: str) -> str:
        events = get_upcoming_events(max_results=8)
        if not events:
            return "📭 No upcoming events."
        return "\n".join(
            f"• {ev.get('summary','Untitled')} — "
            f"{ev.get('start',{}).get('dateTime') or ev.get('start',{}).get('date','')}"
            for ev in events
        )

    def _cancel(event_id: str) -> str:
        result = cancel_event(event_id.strip())
        return "✅ Cancelled." if result.get("success") else f"❌ {result.get('error')}"

    _tools = [
        Tool(
            name="BookMeeting",
            func=book_event_from_text,
            description=(
                "Book a Google Calendar meeting from natural language. "
                "Input must include date, time, and at least one attendee email."
            ),
        ),
        Tool(
            name="GetUpcomingEvents",
            func=_view,
            description="List upcoming Google Calendar events. No input needed.",
        ),
        Tool(
            name="CancelEvent",
            func=_cancel,
            description="Cancel a Google Calendar event by its event ID.",
        ),
    ]

    _SYSTEM = """You are TailorTalk, a friendly AI assistant that manages Google Calendar.
Always use tools for calendar actions — never fake a result.
Be concise, friendly, and confirm what action you took."""

    _agent = initialize_agent(
        tools=_tools,
        llm=_llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5,
        early_stopping_method="generate",
        agent_kwargs={"system_message": _SYSTEM},
    )
    logger.info("✅ Agent initialized")

except Exception as e:
    logger.error(f"❌ Agent init failed: {e}")


def invoke(user_input: str, chat_history: List[Tuple[str, str]]) -> str:
    if not _agent:
        return "Agent unavailable — check GROQ_API_KEY."
    try:
        history = [("human" if r == "user" else "assistant", c) for r, c in chat_history]
        reply   = _agent.invoke({"input": user_input, "chat_history": history})
        if isinstance(reply, dict):
            reply = reply.get("output") or reply.get("response") or str(reply)
        return reply.strip()
    except Exception as e:
        logger.error(f"Agent invoke error: {e}")
        return "I ran into an issue. Please try rephrasing your request."


def get_status() -> dict:
    return {
        "llm_available":   _llm   is not None,
        "agent_available": _agent is not None,
        "model":           GROQ_MODEL if _llm else None,
    }