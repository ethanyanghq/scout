"""The calendar feed scout shares once a trip's itinerary is posted (CAL-1).

Members subscribe to one URL, and every day of the plan shows up in their
calendar as its own event. scout serves the feed from its own web server
(app.py), so a changed plan reaches subscribers' calendars without a new link.
"""

from datetime import datetime, timedelta
from urllib.parse import quote

from scout.group_summary import format_window
from scout.trip import ItineraryDay, Trip

# The plan gives each event's start but not its end, so a timed event blocks
# out time for a typical activity.
ANCHOR_ACTIVITY_DURATION = timedelta(hours=2)
# How often calendar apps are asked to check for a revised plan.
REFRESH_INTERVAL = "PT1H"
# The RFC 5545 limit on a line's length, in bytes.
MAX_LINE_BYTES = 75


def format_plan_set_message(trip: Trip) -> str:
    """The line that comes before the itinerary."""
    return f"the plan for {trip.destination}, {format_window(trip.dates)}, is set"


def format_calendar_message() -> str:
    """The line before the link, which goes in a message of its own so the link
    stays tappable."""
    return "to put this on your calendar, you can subscribe to:"


def calendar_subscription_url(public_url: str, space_id: str) -> str:
    """Where the chat's calendar feed lives. The webcal scheme makes a phone
    offer to subscribe, where https would only download the file once."""
    https_url = f"{public_url.rstrip('/')}/calendars/{quote(space_id, safe='')}.ics"
    return https_url.replace("https://", "webcal://", 1).replace(
        "http://", "webcal://", 1
    )


def build_calendar_feed(trip: Trip, generated_at: datetime) -> str:
    """The trip's itinerary as an iCalendar file, one event per planned event."""
    stamp = f"{generated_at:%Y%m%dT%H%M%SZ}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//scout//trip plan//EN",
        f"X-WR-CALNAME:{_escape(f'Trip to {trip.destination}')}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH_INTERVAL}",
        f"X-PUBLISHED-TTL:{REFRESH_INTERVAL}",
    ]
    for position, event in enumerate(trip.itinerary):
        lines.extend(_event(trip, event, position, stamp))
    lines.append("END:VCALENDAR")
    return "".join(f"{_fold(line)}\r\n" for line in lines)


def _event(trip: Trip, day: ItineraryDay, position: int, stamp: str) -> list[str]:
    day_number = (day.day - trip.dates.start).days + 1
    details = (
        f"Day {day_number} of the trip to {trip.destination}. "
        "Planned in your group chat with scout."
    )
    return [
        "BEGIN:VEVENT",
        f"UID:{day.day:%Y%m%d}-{position}-{trip.space_id}@scout",
        f"DTSTAMP:{stamp}",
        *_event_times(day),
        f"SUMMARY:{_escape(day.plan)}",
        f"LOCATION:{_escape(trip.destination)}",
        f"DESCRIPTION:{_escape(details)}",
        "END:VEVENT",
    ]


def _event_times(day: ItineraryDay) -> list[str]:
    if day.starts_at is None:
        # An all-day event's end date is exclusive.
        return [
            f"DTSTART;VALUE=DATE:{day.day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{day.day + timedelta(days=1):%Y%m%d}",
        ]
    # No time zone, so each calendar shows it at that time wherever it is.
    start = datetime.combine(day.day, day.starts_at)
    return [
        f"DTSTART:{start:%Y%m%dT%H%M%S}",
        f"DTEND:{start + ANCHOR_ACTIVITY_DURATION:%Y%m%dT%H%M%S}",
    ]


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Wraps a long line the way iCalendar requires: each continuation starts
    with a space, and no character is split across lines."""
    folded: list[str] = []
    current = ""
    for character in line:
        limit = MAX_LINE_BYTES - (1 if folded else 0)
        if len((current + character).encode()) > limit:
            folded.append(current)
            current = ""
        current += character
    folded.append(current)
    return "\r\n ".join(folded)
