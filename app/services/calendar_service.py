import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytz
from dateutil import parser as date_parser
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import APP_TIMEZONE, GOOGLE_CALENDAR_ID, GOOGLE_SERVICE_ACCOUNT_FILE

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ── Service init ──────────────────────────────────────────────────────────────
_service = None
_calendar_id = GOOGLE_CALENDAR_ID

try:
    _creds = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    if not _calendar_id:
        _calendar_id = _creds.service_account_email
    _service = build("calendar", "v3", credentials=_creds)
    logger.info("✅ Google Calendar service initialized")
except Exception as e:
    logger.error(f"❌ Calendar service init failed: {e}")


def is_available() -> bool:
    return _service is not None


# ── Availability ──────────────────────────────────────────────────────────────
def check_availability(start_time: datetime, end_time: datetime) -> List[Dict]:
    """Return list of conflicting events. Empty = slot is free."""
    if not _service:
        return []
    try:
        utc = pytz.utc
        start_utc = start_time.astimezone(utc)
        end_utc   = end_time.astimezone(utc)

        body = {
            "timeMin": start_utc.isoformat(),
            "timeMax": end_utc.isoformat(),
            "items":   [{"id": _calendar_id}],
        }
        result     = _service.freebusy().query(body=body).execute()
        busy_slots = result["calendars"][_calendar_id]["busy"]
        logger.info(f"freebusy: {len(busy_slots)} busy slots")
        return busy_slots

    except HttpError as e:
        logger.warning(f"freebusy failed ({e}), using events fallback")
        return _overlap_check(start_time, end_time)
    except Exception as e:
        logger.error(f"check_availability error: {e}")
        return _overlap_check(start_time, end_time)


def _overlap_check(start_time: datetime, end_time: datetime) -> List[Dict]:
    """Fallback: scan events list for overlaps."""
    if not _service:
        return []
    try:
        utc       = pytz.utc
        start_utc = start_time.astimezone(utc)
        end_utc   = end_time.astimezone(utc)

        result = _service.events().list(
            calendarId=_calendar_id,
            timeMin=start_utc.isoformat(),
            timeMax=end_utc.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        conflicts = []
        for ev in result.get("items", []):
            es = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            ee = ev.get("end",   {}).get("dateTime") or ev.get("end",   {}).get("date")
            if es and ee:
                try:
                    ev_s = datetime.fromisoformat(es.replace("Z", "+00:00")).astimezone(utc)
                    ev_e = datetime.fromisoformat(ee.replace("Z", "+00:00")).astimezone(utc)
                    if not (ev_e <= start_utc or ev_s >= end_utc):
                        conflicts.append({"start": es, "end": ee, "title": ev.get("summary", "Untitled")})
                except Exception:
                    pass
        logger.info(f"overlap_check: {len(conflicts)} conflicts")
        return conflicts
    except Exception as e:
        logger.error(f"_overlap_check failed: {e}")
        return []


# ── Book ──────────────────────────────────────────────────────────────────────
def book_event(
    summary:    str,
    start_time: datetime,
    end_time:   datetime,
    description: Optional[str] = None,
    attendees:   Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not _service:
        return {"success": False, "error": "Calendar service unavailable"}
    try:
        event: Dict[str, Any] = {
            "summary": summary,
            "start":   {"dateTime": start_time.isoformat(), "timeZone": APP_TIMEZONE},
            "end":     {"dateTime": end_time.isoformat(),   "timeZone": APP_TIMEZONE},
        }
        # Build description — service accounts can't send invites, store emails here
        desc_parts = []
        if description:
            desc_parts.append(description)
        if attendees:
            desc_parts.append(f"Invitees: {', '.join(attendees)}")
        if desc_parts:
            event["description"] = "\n\n".join(desc_parts)

        created = _service.events().insert(calendarId=_calendar_id, body=event).execute()
        logger.info(f"✅ Event created: {created.get('htmlLink')}")
        return {
            "success":   True,
            "event_id":  created.get("id"),
            "html_link": created.get("htmlLink"),
            "summary":   created.get("summary"),
            "start":     created.get("start"),
            "end":       created.get("end"),
        }
    except HttpError as e:
        logger.error(f"book_event HttpError: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"book_event error: {e}")
        return {"success": False, "error": str(e)}


# ── Cancel ────────────────────────────────────────────────────────────────────
def cancel_event(event_id: str) -> Dict[str, Any]:
    if not _service:
        return {"success": False, "error": "Calendar service unavailable"}
    try:
        _service.events().delete(calendarId=_calendar_id, eventId=event_id).execute()
        logger.info(f"✅ Event {event_id} cancelled")
        return {"success": True}
    except HttpError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── List upcoming ─────────────────────────────────────────────────────────────
def get_upcoming_events(max_results: int = 10) -> List[Dict[str, Any]]:
    if not _service:
        return []
    try:
        now    = datetime.utcnow().isoformat() + "Z"
        result = _service.events().list(
            calendarId=_calendar_id,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = result.get("items", [])
        logger.info(f"Found {len(events)} upcoming events")
        return events
    except Exception as e:
        logger.error(f"get_upcoming_events error: {e}")
        return []


# ── Calendar info ─────────────────────────────────────────────────────────────
def get_calendar_info() -> Dict[str, Any]:
    if not _service:
        return {"error": "Calendar service unavailable"}
    try:
        cal = _service.calendars().get(calendarId=_calendar_id).execute()
        return {
            "id":       cal.get("id"),
            "summary":  cal.get("summary"),
            "timeZone": cal.get("timeZone"),
        }
    except Exception as e:
        logger.error(f"get_calendar_info error: {e}")
        return {"error": str(e)}


# ── Parse + book from natural language text ───────────────────────────────────
def parse_meeting_details(user_input: str) -> Optional[Dict[str, Any]]:
    try:
        now       = datetime.now()
        user_lower = user_input.lower()

        # Summary
        summary = "Meeting"
        for pattern in [
            r'meeting\s+(?:about|regarding)\s+(.*?)(?=\s+(?:with|for|on|at)|$)',
            r'(?:call|session|appointment)\s+(?:about|regarding)\s+(.*?)(?=\s+(?:with|for|on|at)|$)',
        ]:
            m = re.search(pattern, user_input, re.IGNORECASE)
            if m:
                summary = m.group(1).strip()
                break

        # Date
        event_date = now
        next_day = re.search(
            r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', user_lower
        )
        if next_day:
            days_map = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
            target   = days_map.index(next_day.group(1))
            ahead    = (target - now.weekday() + 7) % 7 or 7
            event_date = now + timedelta(days=ahead)
        elif re.search(r'\btomorrow\b', user_lower):
            event_date = now + timedelta(days=1)
        elif re.search(r'\btoday\b', user_lower):
            event_date = now
        elif re.search(r'\b\d{4}-\d{2}-\d{2}\b', user_lower):
            event_date = datetime.strptime(
                re.search(r'\b\d{4}-\d{2}-\d{2}\b', user_lower).group(), '%Y-%m-%d'
            )
        elif re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', user_lower):
            day_name = re.search(
                r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', user_lower
            ).group(1)
            days_map = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
            target   = days_map.index(day_name)
            ahead    = (target - now.weekday() + 7) % 7 or 7
            event_date = now + timedelta(days=ahead)

        # Time
        event_time = None
        for pattern in [
            r'\b(\d{1,2}:\d{2})\s*(am|pm)\b',
            r'\b(\d{1,2})\s*(am|pm)\b',
            r'\b(\d{1,2}:\d{2})\b',
        ]:
            m = re.search(pattern, user_lower)
            if m:
                time_str = m.group(1)
                ampm     = m.group(2) if len(m.groups()) > 1 else None
                hour     = int(time_str.split(':')[0])
                minute   = int(time_str.split(':')[1]) if ':' in time_str else 0
                if ampm:
                    if ampm == 'pm' and hour != 12: hour += 12
                    elif ampm == 'am' and hour == 12: hour = 0
                event_time = f"{hour:02d}:{minute:02d}"
                break

        if not event_time:
            return None

        # Duration
        duration = timedelta(minutes=30)
        dur = re.search(r'\b(\d+)\s*(minute|min|hour|hr)s?\b', user_lower)
        if dur:
            v, u = int(dur.group(1)), dur.group(2)
            duration = timedelta(hours=v) if 'hour' in u or 'hr' in u else timedelta(minutes=v)

        # Attendees
        attendees = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', user_input)

        # Description
        description = None
        m = re.search(r'\babout\s+(.*?)(?=\s+(?:with|for|at\s+\d)|$)', user_input, re.IGNORECASE)
        if m:
            description = m.group(1).strip()

        local_tz   = pytz.timezone(APP_TIMEZONE)
        start_time = local_tz.localize(
            datetime.combine(event_date.date(), datetime.strptime(event_time, '%H:%M').time())
        )
        end_time = start_time + duration

        return {
            "summary":     summary,
            "start_time":  start_time,
            "end_time":    end_time,
            "attendees":   attendees,
            "description": description,
        }
    except Exception as e:
        logger.error(f"parse_meeting_details error: {e}")
        return None


def book_event_from_text(user_input: str) -> str:
    """Parse natural language and book a real calendar event. Returns formatted response string."""
    logger.info(f"🔧 book_event_from_text: {user_input}")
    try:
        parsed = parse_meeting_details(user_input)
        if not parsed:
            return "❌ Couldn't parse the meeting details. Please provide date, time, and attendee email."

        start_time  = parsed["start_time"]
        end_time    = parsed["end_time"]
        summary     = parsed["summary"]
        attendees   = parsed["attendees"]
        description = parsed["description"]

        # Conflict check
        conflicts = check_availability(start_time, end_time)
        if conflicts:
            local_tz = pytz.timezone(APP_TIMEZONE)
            lines    = []
            for c in conflicts[:3]:
                title = c.get("title", "Untitled")
                try:
                    cs = datetime.fromisoformat(c["start"].replace("Z", "+00:00")).astimezone(local_tz).strftime("%I:%M %p")
                    ce = datetime.fromisoformat(c["end"].replace("Z", "+00:00")).astimezone(local_tz).strftime("%I:%M %p")
                    lines.append(f"• **{title}** ({cs} – {ce})")
                except Exception:
                    lines.append(f"• **{title}**")
            slot_start = start_time.astimezone(local_tz).strftime("%I:%M %p")
            slot_end   = end_time.astimezone(local_tz).strftime("%I:%M %p")
            return (
                f"⚠️ **Time conflict at {slot_start} – {slot_end}:**\n"
                + "\n".join(lines)
                + "\n\nWould you like to pick a different time?"
            )

        result = book_event(summary, start_time, end_time, description, attendees)
        if result.get("success"):
            local_tz    = pytz.timezone(APP_TIMEZONE)
            local_start = start_time.astimezone(local_tz).strftime("%A, %B %d at %I:%M %p")
            local_end   = end_time.astimezone(local_tz).strftime("%I:%M %p")
            response    = (
                f"✅ **Meeting booked!**\n\n"
                f"📅 **When**: {local_start} – {local_end}\n"
                f"📋 **Title**: {summary}"
            )
            if attendees:
                response += f"\n👥 **Invitees**: {', '.join(attendees)}"
            if description:
                response += f"\n📝 **About**: {description}"
            response += f"\n🔗 [View in Google Calendar]({result['html_link']})"
            return response
        else:
            return f"❌ Failed to book: {result.get('error', 'Unknown error')}"

    except Exception as e:
        logger.error(f"book_event_from_text error: {e}")
        return f"❌ An error occurred: {e}"