"""The "Add to Google Calendar" link scout texts once a trip is locked in (CAL-1).

A prefilled link needs no sign-in, API key, or Google review, so it keeps
scout's zero-onboarding promise. Tapping it opens Google Calendar with the
event filled in, and scout stores nothing.
"""

from datetime import timedelta
from urllib.parse import quote, urlencode

from scout.group_summary import format_window
from scout.trip import DateWindow

GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/render"
EVENT_DETAILS = "Planned in your group chat with scout."


def format_calendar_message(destination: str, dates: DateWindow) -> str:
    return (
        f"📅 Locked in: {destination}, {format_window(dates)}. "
        f"Add it to your calendar:\n{google_calendar_link(destination, dates)}"
    )


def google_calendar_link(destination: str, dates: DateWindow) -> str:
    """An all-day event covering every day of the trip."""
    # Google treats an all-day event's end date as exclusive, so a trip whose
    # last day is the 19th has to end on the 20th.
    end_exclusive = dates.end + timedelta(days=1)
    query = urlencode(
        {
            "action": "TEMPLATE",
            "text": f"Trip to {destination}",
            "dates": f"{dates.start:%Y%m%d}/{end_exclusive:%Y%m%d}",
            "location": destination,
            "details": EVENT_DETAILS,
        },
        quote_via=quote,
        safe="/",
    )
    return f"{GOOGLE_CALENDAR_URL}?{query}"
