import re
import logging
from typing import Any, Dict, List, Optional

from app.models.schemas import BookingState

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


# ── Extract partial details from any user message ────────────────────────────
def extract_partial(text: str) -> BookingState:
    """Pull out whatever booking details exist — date, time, duration, topic, emails."""
    t = text.lower().strip()
    state = BookingState()

    # Date — 'next <day>' must be checked before bare day name
    next_day = re.search(
        r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', t
    )
    if next_day:
        state.date_hint = next_day.group()
    elif re.search(r'\btomorrow\b', t):
        state.date_hint = 'tomorrow'
    elif re.search(r'\btoday\b', t):
        state.date_hint = 'today'
    elif re.search(r'\b\d{4}-\d{2}-\d{2}\b', t):
        state.date_hint = re.search(r'\b\d{4}-\d{2}-\d{2}\b', t).group()
    elif re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', t):
        state.date_hint = re.search(
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', t
        ).group()

    # Time
    time_match = re.search(r'\b(\d{1,2}(?::\d{2})?)\s*(am|pm)\b', t) or \
                 re.search(r'\b(\d{1,2}:\d{2})\b', t)
    if time_match:
        state.time_hint = time_match.group()

    # Duration
    dur = re.search(r'\b(\d+)\s*(minute|min|hour|hr)s?\b', t)
    if dur:
        state.duration_hint = dur.group()

    # Topic
    topic = re.search(r'\babout\s+(.*?)(?=\s+(?:with|for|at\s+\d)|$)', text, re.IGNORECASE)
    if topic:
        state.topic_hint = topic.group(1).strip()

    # Emails
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    if emails:
        state.emails = emails

    return state


def merge(existing: BookingState, new_text: str) -> BookingState:
    """Merge newly extracted details into existing state — never overwrite with None."""
    new = extract_partial(new_text)
    return BookingState(
        date_hint     = new.date_hint     or existing.date_hint,
        time_hint     = new.time_hint     or existing.time_hint,
        duration_hint = new.duration_hint or existing.duration_hint,
        topic_hint    = new.topic_hint    or existing.topic_hint,
        emails        = new.emails        or existing.emails,
    )


def missing_fields(state: BookingState) -> List[str]:
    """Return required fields not yet collected, in priority order."""
    missing = []
    if not state.date_hint:
        missing.append('date')
    if not state.time_hint:
        missing.append('time')
    if not state.emails:
        missing.append('email')
    return missing  # topic/duration are optional


def ask_for(missing: List[str]) -> str:
    """Return a single focused question for the first missing field."""
    questions = {
        'date':  "📅 What **date** should I book it for? *(e.g. tomorrow, next Monday, June 15)*",
        'time':  "🕐 What **time** works? *(e.g. 3 PM, 14:30)*",
        'email': "👤 Who should I invite? *(share their email address)*",
    }
    for field in ['date', 'time', 'email']:
        if field in missing:
            return questions[field]
    return questions[missing[0]]


def build_booking_text(state: BookingState) -> str:
    """Reconstruct a full natural language booking sentence from accumulated state."""
    parts = [f"Book a {state.duration_hint} meeting"] if state.duration_hint else ["Book a meeting"]
    if state.date_hint:
        parts.append(state.date_hint)
    if state.time_hint:
        parts.append(f"at {state.time_hint}")
    if state.emails:
        parts.append(f"with {' '.join(state.emails)}")
    if state.topic_hint:
        parts.append(f"about {state.topic_hint}")
    return ' '.join(parts)