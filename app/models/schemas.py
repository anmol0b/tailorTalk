from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel


class BookingState(BaseModel):
    """Partial booking details accumulated across conversation turns."""
    date_hint:     Optional[str] = None
    time_hint:     Optional[str] = None
    duration_hint: Optional[str] = None
    topic_hint:    Optional[str] = None
    emails:        Optional[List[str]] = None


class ChatInput(BaseModel):
    user_input:      str
    chat_history:    List[Tuple[str, str]] = []
    pending_booking: Optional[BookingState] = None
    attempt_count:   int = 0


class ChatResponse(BaseModel):
    response:        str
    pending_booking: Optional[BookingState] = None
    attempt_count:   int = 0


class EventOut(BaseModel):
    """Simplified calendar event for API responses."""
    id:       Optional[str] = None
    title:    str
    start:    str
    end:      str
    link:     Optional[str] = None
    attendees: List[str] = []