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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

# Initialize Google Calendar service
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
    Check calendar availability between two datetime ranges
    Returns list of busy time slots
    """
    if not service:
        logger.error("Calendar service not available")
        return []
    
    try:
        logger.info(f"📅 Checking availability from {start_time} to {end_time}")
        
        body = {
            "timeMin": start_time.isoformat() + "Z",
            "timeMax": end_time.isoformat() + "Z",
            "items": [{"id": CALENDAR_ID}]
        }
        
        result = service.freebusy().query(body=body).execute()
        busy_slots = result['calendars'][CALENDAR_ID]['busy']
        
        logger.info(f"Found {len(busy_slots)} busy time slots")
        return busy_slots
        
    except HttpError as e:
        logger.error(f"HTTP error checking availability: {e}")
        return []
    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        return []

def book_event(summary: str, start_time: datetime, end_time: datetime, description: str = None, attendees: List[str] = None) -> Dict[str, Any]:
    """
    Book an event on Google Calendar with enhanced error handling
    """
    if not service:
        return {"error": "Calendar service not available", "success": False}
    
    try:
        logger.info(f"📝 Booking event: {summary} from {start_time} to {end_time}")
        
        # Prepare event details
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time.isoformat(), 
                'timeZone': APP_TIMEZONE
            },
            'end': {
                'dateTime': end_time.isoformat(), 
                'timeZone': APP_TIMEZONE
            }
        }
        
        # Add description if provided
        if description:
            event['description'] = description
        
        # Add attendees if provided
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]
        
        # Insert the event
        created_event = service.events().insert(
            calendarId=CALENDAR_ID, 
            body=event,
            sendUpdates='all'  # Send email notifications to attendees
        ).execute()
        
        logger.info(f"✅ Event created successfully: {created_event.get('htmlLink')}")
        
        return {
            "success": True,
            "event_id": created_event.get('id'),
            "html_link": created_event.get('htmlLink'),
            "summary": created_event.get('summary'),
            "start_time": created_event.get('start'),
            "end_time": created_event.get('end')
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
    """
    Cancel an existing event
    """
    if not service:
        return {"error": "Calendar service not available", "success": False}
    
    try:
        logger.info(f"🗑️ Cancelling event: {event_id}")
        
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
        
        logger.info("✅ Event cancelled successfully")
        return {"success": True, "message": "Event cancelled successfully"}
        
    except HttpError as e:
        error_msg = f"HTTP error cancelling event: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}
    except Exception as e:
        error_msg = f"Error cancelling event: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}

def get_upcoming_events(max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Get upcoming events from the calendar
    """
    if not service:
        return []
    
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        logger.info(f"Found {len(events)} upcoming events")
        
        return events
        
    except HttpError as e:
        logger.error(f"HTTP error getting events: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting events: {e}")
        return []

def book_event_from_text(user_input: str) -> str:
    """
    Enhanced function to parse user input and book events with better error handling
    """
    logger.info(f"🔧 [Tool Called] book_event_from_text() with input: {user_input}")
    
    try:
        # Parse date and time from user input
        parsed_info = parse_meeting_details(user_input)
        if not parsed_info:
            return "❌ Couldn't parse the meeting details. Please provide date, time, and duration."
        
        summary = parsed_info.get('summary', 'Meeting')
        start_time = parsed_info['start_time']
        end_time = parsed_info['end_time']
        attendees = parsed_info.get('attendees', [])
        description = parsed_info.get('description')
        
        # Check availability before booking
        busy_slots = check_availability(start_time, end_time)
        if busy_slots:
            return "⛔ That time slot is already busy. Please try a different time."
        
        # Book the event
        result = book_event(summary, start_time, end_time, description, attendees)
        
        if result.get('success'):
            # Format response with local time
            local_tz = pytz.timezone(APP_TIMEZONE)
            local_start = start_time.astimezone(local_tz).strftime('%A, %B %d at %I:%M %p')
            local_end = end_time.astimezone(local_tz).strftime('%I:%M %p')
            
            response = f"✅ Meeting booked successfully!\n\n📅 **Date & Time**: {local_start} - {local_end}\n📋 **Title**: {summary}"
            
            if attendees:
                response += f"\n👥 **Attendees**: {', '.join(attendees)}"
            
            if description:
                response += f"\n📝 **Description**: {description}"
            
            response += f"\n🔗 **View Event**: [Click here]({result['html_link']})"
            
            return response
        else:
            return f"❌ Failed to book meeting: {result.get('error', 'Unknown error')}"
            
    except Exception as e:
        logger.error(f"Error in book_event_from_text: {e}")
        return f"❌ An error occurred while booking the meeting: {str(e)}"

def parse_meeting_details(user_input: str) -> Optional[Dict[str, Any]]:
    """
    Parse meeting details from user input with enhanced parsing
    """
    try:
        now = datetime.now()
        user_lower = user_input.lower()
        
        # Extract summary/title
        summary_patterns = [
            r'meeting\s+(?:about|regarding|titled?)\s+[\'"](.*?)[\'"]',
            r'meeting\s+(?:about|regarding)\s+(.*?)(?=\s+(?:with|for|on|at)|$)',
            r'book\s+(?:a\s+)?(?:meeting|call|appointment)\s+(?:about|regarding)\s+(.*?)(?=\s+(?:with|for|on|at)|$)'
        ]
        
        summary = "Meeting"  # Default
        for pattern in summary_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                summary = match.group(1).strip()
                break
        
        # Extract date
        date_patterns = [
            r'\b(\d{4}-\d{2}-\d{2})\b',  # YYYY-MM-DD
            r'\b(tomorrow)\b',
            r'\b(next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',
            r'\b(in\s+(\d+)\s+days?)\b'
        ]
        
        event_date = now
        for pattern in date_patterns:
            match = re.search(pattern, user_lower)
            if match:
                if match.group(1) == 'tomorrow':
                    event_date = now + timedelta(days=1)
                elif match.group(1).startswith('next '):
                    day_name = match.group(1).split()[1]
                    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    target_day = days.index(day_name)
                    current_day = now.weekday()
                    days_ahead = (target_day - current_day + 7) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    event_date = now + timedelta(days=days_ahead)
                elif match.group(1).startswith('in '):
                    days = int(match.group(2))
                    event_date = now + timedelta(days=days)
                else:
                    # YYYY-MM-DD format
                    event_date = datetime.strptime(match.group(1), '%Y-%m-%d')
                break
        
        # Extract time
        time_patterns = [
            r'\b(\d{1,2}:\d{2})\b',  # HH:MM
            r'\b(\d{1,2})\s*(am|pm)\b',  # 3 PM
            r'\b(\d{1,2}:\d{2})\s*(am|pm)\b'  # 3:30 PM
        ]
        
        event_time = None
        for pattern in time_patterns:
            match = re.search(pattern, user_lower)
            if match:
                time_str = match.group(1)
                if len(match.groups()) > 1 and match.group(2):
                    # Handle AM/PM
                    hour = int(time_str.split(':')[0])
                    minute = int(time_str.split(':')[1]) if ':' in time_str else 0
                    if match.group(2).lower() == 'pm' and hour < 12:
                        hour += 12
                    elif match.group(2).lower() == 'am' and hour == 12:
                        hour = 0
                    event_time = f"{hour:02d}:{minute:02d}"
                else:
                    event_time = time_str
                break
        
        if not event_time:
            return None
        
        # Extract duration
        duration_patterns = [
            r'\b(\d+)\s*(minute|min|hour|hr)s?\b',
            r'\bfor\s+(\d+)\s*(minute|min|hour|hr)s?\b',
            r'\b(\d+)\s*(minute|min|hour|hr)\s+meeting\b'
        ]
        
        duration = timedelta(minutes=30)  # Default 30 minutes
        for pattern in duration_patterns:
            match = re.search(pattern, user_lower)
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                if 'hour' in unit or 'hr' in unit:
                    duration = timedelta(hours=value)
                else:
                    duration = timedelta(minutes=value)
                break
        
        # Extract attendees (email addresses)
        attendees = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', user_input)
        
        # Extract description/agenda
        description_patterns = [
            r'agenda[:\-]?\s*(.*?)(?=\s+(?:with|for|on|at)|$)',
            r'about\s+(.*?)(?=\s+(?:with|for|on|at)|$)',
            r'description[:\-]?\s*(.*?)(?=\s+(?:with|for|on|at)|$)'
        ]
        
        description = None
        for pattern in description_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                description = match.group(1).strip()
                break
        
        # Create datetime objects
        local_tz = pytz.timezone(APP_TIMEZONE)
        start_time = local_tz.localize(datetime.combine(event_date.date(), datetime.strptime(event_time, '%H:%M').time()))
        end_time = start_time + duration
        
        return {
            'summary': summary,
            'start_time': start_time,
            'end_time': end_time,
            'attendees': attendees,
            'description': description
        }
        
    except Exception as e:
        logger.error(f"Error parsing meeting details: {e}")
        return None

def get_calendar_info() -> Dict[str, Any]:
    """
    Get basic calendar information
    """
    if not service:
        return {"error": "Calendar service not available"}
    
    try:
        calendar = service.calendars().get(calendarId=CALENDAR_ID).execute()
        return {
            "id": calendar.get('id'),
            "summary": calendar.get('summary'),
            "description": calendar.get('description'),
            "timeZone": calendar.get('timeZone')
        }
    except Exception as e:
        logger.error(f"Error getting calendar info: {e}")
        return {"error": str(e)}
