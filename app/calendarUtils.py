import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import pytz
import re
import logging
from typing import Optional, Dict, Any, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

try:
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    if not CALENDAR_ID:
        CALENDAR_ID = credentials.service_account_email
    service = build('calendar', 'v3', credentials=credentials)
    logger.info("✅ Google Calendar service initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize Google Calendar service: {e}")
    service = None


def check_availability(start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """
    Check calendar availability. Returns list of conflicting busy slots.
    Uses freebusy API with correct UTC conversion, falls back to events list.
    """
    if not service:
        return []

    try:
        logger.info(f"📅 Checking availability from {start_time} to {end_time}")

        # Convert to UTC — this was the bug: tz-aware datetimes must be
        # converted to UTC before calling .isoformat(), not appending 'Z'
        utc = pytz.utc
        start_utc = start_time.astimezone(utc)
        end_utc = end_time.astimezone(utc)

        body = {
            "timeMin": start_utc.isoformat(),   # already has +00:00, no 'Z' needed
            "timeMax": end_utc.isoformat(),
            "items": [{"id": CALENDAR_ID}]
        }

        result = service.freebusy().query(body=body).execute()
        busy_slots = result['calendars'][CALENDAR_ID]['busy']
        logger.info(f"Found {len(busy_slots)} busy slots via freebusy")
        return busy_slots

    except HttpError as e:
        logger.warning(f"freebusy failed ({e}), falling back to events list check")
        # Fallback: scan upcoming events for overlap manually
        return _check_overlap_via_events(start_time, end_time)
    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        return _check_overlap_via_events(start_time, end_time)


def _check_overlap_via_events(start_time: datetime, end_time: datetime) -> List[Dict]:
    """
    Fallback availability check: fetch events in the time window and
    return any that overlap with the requested slot.
    """
    if not service:
        return []
    try:
        utc = pytz.utc
        start_utc = start_time.astimezone(utc)
        end_utc = end_time.astimezone(utc)

        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_utc.isoformat(),
            timeMax=end_utc.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        conflicts = []
        for ev in events:
            ev_start_str = ev.get('start', {}).get('dateTime') or ev.get('start', {}).get('date')
            ev_end_str   = ev.get('end',   {}).get('dateTime') or ev.get('end',   {}).get('date')
            if ev_start_str and ev_end_str:
                try:
                    ev_start = datetime.fromisoformat(ev_start_str.replace('Z', '+00:00')).astimezone(utc)
                    ev_end   = datetime.fromisoformat(ev_end_str.replace('Z', '+00:00')).astimezone(utc)
                    # Overlap condition: not (ev ends before slot starts OR ev starts after slot ends)
                    if not (ev_end <= start_utc or ev_start >= end_utc):
                        conflicts.append({
                            "start": ev_start_str,
                            "end":   ev_end_str,
                            "title": ev.get('summary', 'Untitled'),
                        })
                except Exception:
                    pass

        logger.info(f"Fallback check found {len(conflicts)} conflicting events")
        return conflicts

    except Exception as e:
        logger.error(f"Fallback availability check failed: {e}")
        return []


def book_event(summary: str, start_time: datetime, end_time: datetime,
               description: str = None, attendees: List[str] = None) -> Dict[str, Any]:
    if not service:
        return {"error": "Calendar service not available", "success": False}

    try:
        logger.info(f"📝 Booking event: {summary} from {start_time} to {end_time}")

        event = {
            'summary': summary,
            'start': {'dateTime': start_time.isoformat(), 'timeZone': APP_TIMEZONE},
            'end':   {'dateTime': end_time.isoformat(),   'timeZone': APP_TIMEZONE},
        }

        if description:
            event['description'] = description

        # Store attendees in description — service accounts can't send invites
        if attendees:
            attendee_str = ', '.join(attendees)
            existing_desc = event.get('description', '')
            event['description'] = (existing_desc + f'\n\nInvitees: {attendee_str}').strip()

        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event,
        ).execute()

        logger.info(f"✅ Event created successfully: {created_event.get('htmlLink')}")
        return {
            "success": True,
            "event_id":  created_event.get('id'),
            "html_link": created_event.get('htmlLink'),
            "summary":   created_event.get('summary'),
            "start_time": created_event.get('start'),
            "end_time":   created_event.get('end'),
        }

    except HttpError as e:
        error_msg = f"HTTP error booking event: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}
    except Exception as e:
        error_msg = f"Error booking event: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}


def cancel_event(event_id: str) -> Dict[str, Any]:
    if not service:
        return {"error": "Calendar service not available", "success": False}
    try:
        logger.info(f"🗑️ Cancelling event: {event_id}")
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
        logger.info("✅ Event cancelled successfully")
        return {"success": True, "message": "Event cancelled successfully"}
    except HttpError as e:
        return {"error": f"HTTP error cancelling event: {e}", "success": False}
    except Exception as e:
        return {"error": f"Error cancelling event: {e}", "success": False}


def get_upcoming_events(max_results: int = 10) -> List[Dict[str, Any]]:
    if not service:
        return []
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = result.get('items', [])
        logger.info(f"Found {len(events)} upcoming events")
        return events
    except Exception as e:
        logger.error(f"Error getting events: {e}")
        return []


def book_event_from_text(user_input: str) -> str:
    logger.info(f"🔧 [Tool Called] book_event_from_text() with input: {user_input}")

    try:
        parsed_info = parse_meeting_details(user_input)
        if not parsed_info:
            return "❌ Couldn't parse the meeting details. Please provide date, time, and duration."

        summary    = parsed_info.get('summary', 'Meeting')
        start_time = parsed_info['start_time']
        end_time   = parsed_info['end_time']
        attendees  = parsed_info.get('attendees', [])
        description = parsed_info.get('description')

        # ── Conflict check ────────────────────────────────────────────────────
        conflicts = check_availability(start_time, end_time)
        if conflicts:
            local_tz = pytz.timezone(APP_TIMEZONE)

            # Build a readable list of conflicting events
            conflict_lines = []
            for c in conflicts[:3]:  # show max 3 conflicts
                title = c.get('title', 'Untitled')
                try:
                    c_start = datetime.fromisoformat(
                        c['start'].replace('Z', '+00:00')
                    ).astimezone(local_tz).strftime('%I:%M %p')
                    c_end = datetime.fromisoformat(
                        c['end'].replace('Z', '+00:00')
                    ).astimezone(local_tz).strftime('%I:%M %p')
                    conflict_lines.append(f"• **{title}** ({c_start} – {c_end})")
                except Exception:
                    conflict_lines.append(f"• **{title}**")

            conflicts_str = '\n'.join(conflict_lines)
            local_start = start_time.astimezone(local_tz).strftime('%I:%M %p')
            local_end   = end_time.astimezone(local_tz).strftime('%I:%M %p')

            return (
                f"⚠️ **Time conflict detected!**\n\n"
                f"You already have something scheduled at **{local_start} – {local_end}**:\n"
                f"{conflicts_str}\n\n"
                f"Would you like to pick a different time?"
            )

        # ── Book ──────────────────────────────────────────────────────────────
        result = book_event(summary, start_time, end_time, description, attendees)

        if result.get('success'):
            local_tz    = pytz.timezone(APP_TIMEZONE)
            local_start = start_time.astimezone(local_tz).strftime('%A, %B %d at %I:%M %p')
            local_end   = end_time.astimezone(local_tz).strftime('%I:%M %p')

            response = (
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
            return f"❌ Failed to book meeting: {result.get('error', 'Unknown error')}"

    except Exception as e:
        logger.error(f"Error in book_event_from_text: {e}")
        return f"❌ An error occurred: {str(e)}"


def parse_meeting_details(user_input: str) -> Optional[Dict[str, Any]]:
    try:
        now = datetime.now()
        user_lower = user_input.lower()

        summary_patterns = [
            r'meeting\s+(?:about|regarding|titled?)\s+[\'"](.*?)[\'"]',
            r'meeting\s+(?:about|regarding)\s+(.*?)(?=\s+(?:with|for|on|at)|$)',
            r'book\s+(?:a\s+)?(?:meeting|call|appointment)\s+(?:about|regarding)\s+(.*?)(?=\s+(?:with|for|on|at)|$)',
            r'(?:call|session|appointment)\s+(?:about|regarding)\s+(.*?)(?=\s+(?:with|for|on|at)|$)',
        ]
        summary = "Meeting"
        for pattern in summary_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                summary = match.group(1).strip()
                break

        date_patterns = [
            r'\b(\d{4}-\d{2}-\d{2})\b',
            r'\b(tomorrow)\b',
            r'\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',
            r'\b(in\s+(\d+)\s+days?)\b',
        ]
        event_date = now
        for pattern in date_patterns:
            match = re.search(pattern, user_lower)
            if match:
                val = match.group(1)
                if val == 'tomorrow':
                    event_date = now + timedelta(days=1)
                elif val.startswith('next '):
                    day_name = val.split()[1]
                    days_map = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
                    target = days_map.index(day_name)
                    ahead = (target - now.weekday() + 7) % 7 or 7
                    event_date = now + timedelta(days=ahead)
                elif val.startswith('in '):
                    event_date = now + timedelta(days=int(match.group(2)))
                else:
                    event_date = datetime.strptime(val, '%Y-%m-%d')
                break

        time_patterns = [
            r'\b(\d{1,2}:\d{2})\s*(am|pm)\b',
            r'\b(\d{1,2})\s*(am|pm)\b',
            r'\b(\d{1,2}:\d{2})\b',
        ]
        event_time = None
        for pattern in time_patterns:
            match = re.search(pattern, user_lower)
            if match:
                time_str = match.group(1)
                ampm = match.group(2) if len(match.groups()) > 1 else None
                if ':' in time_str:
                    hour, minute = int(time_str.split(':')[0]), int(time_str.split(':')[1])
                else:
                    hour, minute = int(time_str), 0
                if ampm:
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                event_time = f"{hour:02d}:{minute:02d}"
                break

        if not event_time:
            return None

        duration_patterns = [
            r'\bfor\s+(\d+)\s*(minute|min|hour|hr)s?\b',
            r'\b(\d+)\s*[-]?\s*(minute|min|hour|hr)\s+(?:meeting|call|session)\b',
            r'\b(\d+)\s*(minute|min|hour|hr)s?\b',
        ]
        duration = timedelta(minutes=30)
        for pattern in duration_patterns:
            match = re.search(pattern, user_lower)
            if match:
                value = int(match.group(1))
                unit  = match.group(2)
                duration = timedelta(hours=value) if 'hour' in unit or 'hr' in unit else timedelta(minutes=value)
                break

        attendees = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', user_input)

        description_patterns = [
            r'\babout\s+(.*?)(?=\s+(?:with|for|on|at\s+\d)|$)',
            r'\bagenda[:\-]?\s*(.*?)(?=\s+(?:with|for|on|at)|$)',
        ]
        description = None
        for pattern in description_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                description = match.group(1).strip()
                break

        local_tz   = pytz.timezone(APP_TIMEZONE)
        start_time = local_tz.localize(
            datetime.combine(event_date.date(), datetime.strptime(event_time, '%H:%M').time())
        )
        end_time = start_time + duration

        return {
            'summary':     summary,
            'start_time':  start_time,
            'end_time':    end_time,
            'attendees':   attendees,
            'description': description,
        }

    except Exception as e:
        logger.error(f"Error parsing meeting details: {e}")
        return None


def get_calendar_info() -> Dict[str, Any]:
    if not service:
        return {"error": "Calendar service not available"}
    try:
        cal = service.calendars().get(calendarId=CALENDAR_ID).execute()
        return {
            "id":          cal.get('id'),
            "summary":     cal.get('summary'),
            "description": cal.get('description'),
            "timeZone":    cal.get('timeZone'),
        }
    except Exception as e:
        logger.error(f"Error getting calendar info: {e}")
        return {"error": str(e)}