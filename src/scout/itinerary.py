"""How a trip's day-by-day plan reads in the chat (IT-1, IT-2)."""

from datetime import date
from itertools import groupby

from scout.trip import ItineraryAddOn, ItineraryDay


def format_itinerary(days: list[ItineraryDay], add_ons: list[ItineraryAddOn]) -> str:
    lines = ["the plan:"]
    for day, events in events_by_day(days):
        lines.append("")
        lines.append(format_date(day))
        lines.extend(_timed_plan(event) for event in events)
    if add_ons:
        lines.append("")
        lines.append("optional add-ons:")
        lines.extend(
            f"{add_on.activity} · {add_on.wanted_by}'s pick" for add_on in add_ons
        )
    return "\n".join(lines)


def events_by_day(days: list[ItineraryDay]) -> list[tuple[date, list[ItineraryDay]]]:
    """The plan's events grouped under their day, in the order given."""
    return [
        (day, list(events))
        for day, events in groupby(days, key=lambda event: event.day)
    ]


def format_date(day: date) -> str:
    """ "Monday, October 5"."""
    return f"{day:%A, %B} {day.day}"


def format_start(event: ItineraryDay) -> str | None:
    """ "9:30 PM", or None for something loose."""
    return f"{event.starts_at:%-I:%M %p}" if event.starts_at else None


def _timed_plan(event: ItineraryDay) -> str:
    start = format_start(event)
    return f"{start} · {event.plan}" if start else event.plan
