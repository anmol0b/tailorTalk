import logging
from fastapi import APIRouter

from app.models.schemas import BookingState, ChatInput, ChatResponse
from app.services import booking, calendar_service, agent_service

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_ATTEMPTS = booking.MAX_ATTEMPTS

ABANDON_WORDS = {'cancel', 'stop', 'forget it', 'never mind', 'skip', 'abort', 'quit'}


# ── Intent detection ──────────────────────────────────────────────────────────
def _intent(text: str) -> str:
    t = text.lower().strip()
    if any(w in t for w in ['book', 'schedule', 'arrange', 'set up', 'create', 'add']) and \
       any(w in t for w in ['meeting', 'appointment', 'call', 'session', 'event']):
        return "book"
    greet = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
    if len(t.split()) <= 5 and any(t == w or t.startswith(w + ' ') for w in greet):
        return "greet"
    if any(w in t for w in ['help', 'what can you do', 'capabilities']):
        return "help"
    if any(w in t for w in ['cancel', 'delete', 'remove']):
        return "cancel"
    if any(w in t for w in ['show', 'list', 'upcoming', 'my schedule', 'my calendar', 'my meetings', 'do i have']):
        return "view"
    return "agent"


# ── Format events ─────────────────────────────────────────────────────────────
def _fmt_events(events: list) -> str:
    from datetime import datetime
    if not events:
        return "📭 No upcoming events on your calendar."
    lines = ["📅 **Your upcoming events:**\n"]
    for ev in events:
        dt_str = ev.get('start', {}).get('dateTime') or ev.get('start', {}).get('date', '')
        try:
            dt        = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            formatted = dt.strftime('%A, %b %d at %I:%M %p')
        except Exception:
            formatted = dt_str
        title     = ev.get('summary', 'Untitled')
        attendees = ev.get('attendees', [])
        link      = ev.get('htmlLink', '')
        lines.append(f"**{title}**  🕐 {formatted}")
        if attendees:
            lines.append(f"  👥 {', '.join(a['email'] for a in attendees)}")
        if link:
            lines.append(f"  🔗 [Open in Calendar]({link})")
        lines.append("")
    return '\n'.join(lines)


# ── POST /chat ────────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatInput):
    text     = payload.user_input.strip()
    pending  = payload.pending_booking
    attempts = payload.attempt_count

    # ── Mid-booking flow ──────────────────────────────────────────────────────
    if pending is not None:
        if any(w in text.lower() for w in ABANDON_WORDS):
            return ChatResponse(
                response="No problem, I've dropped that booking. What else can I help with?",
                pending_booking=None, attempt_count=0,
            )

        updated = booking.merge(pending, text)
        missing = booking.missing_fields(updated)

        if not missing:
            result = calendar_service.book_event_from_text(booking.build_booking_text(updated))
            return ChatResponse(response=result, pending_booking=None, attempt_count=0)

        attempts += 1
        if attempts >= MAX_ATTEMPTS:
            return ChatResponse(
                response=(
                    "I wasn't able to get all the details — no booking was made.\n\n"
                    "Feel free to try again:\n"
                    "*\"Book a 30-min call tomorrow at 3 PM with john@example.com about design review\"*"
                ),
                pending_booking=None, attempt_count=0,
            )

        remaining = MAX_ATTEMPTS - attempts
        question  = booking.ask_for(missing)
        return ChatResponse(
            response=f"{question}\n\n*({remaining} attempt{'s' if remaining > 1 else ''} remaining)*",
            pending_booking=updated,
            attempt_count=attempts,
        )

    # ── Fresh message ─────────────────────────────────────────────────────────
    intent = _intent(text)
    logger.info(f"Intent={intent} | '{text}'")

    if intent == "greet":
        return ChatResponse(response=(
            "👋 Hey! I'm TailorTalk — your AI calendar assistant.\n\n"
            "Try: *\"Book a 30-min call tomorrow at 3 PM with john@example.com about onboarding\"*\n\n"
            "I'll ask for anything missing."
        ))

    if intent == "help":
        return ChatResponse(response=(
            "🤖 **What I can do:**\n\n"
            "📅 **Book** — *\"Book a 1-hour call next Monday at 2 PM about sprint planning\"*\n"
            "📋 **View** — *\"Show my upcoming meetings\"*\n"
            "❌ **Cancel** *(coming soon)*\n\n"
            "Missing details? I'll ask one question at a time — max 3 follow-ups."
        ))

    if intent == "view":
        if not calendar_service.is_available():
            return ChatResponse(response="⚠️ Calendar unavailable — check your `.env` settings")
        return ChatResponse(response=_fmt_events(calendar_service.get_upcoming_events()))

    if intent == "book":
        if not calendar_service.is_available():
            return ChatResponse(response="⚠️ Calendar unavailable — check your `.env` settings")

        partial = booking.extract_partial(text)
        missing = booking.missing_fields(partial)

        if not missing:
            result = calendar_service.book_event_from_text(text)
            return ChatResponse(response=result)

        question = booking.ask_for(missing)
        return ChatResponse(
            response=f"{question}\n\n*({MAX_ATTEMPTS} attempts remaining)*",
            pending_booking=partial,
            attempt_count=0,
        )

    if intent == "cancel":
        return ChatResponse(response="To cancel, tell me the **meeting title + date**. *(coming soon)*")

    # ── Agent fallback ────────────────────────────────────────────────────────
    reply = agent_service.invoke(text, payload.chat_history)
    return ChatResponse(response=reply)