"""How a trip's day-by-day plan reads in the chat (IT-1, IT-2)."""

from scout.trip import ItineraryAddOn, ItineraryDay


def format_itinerary(days: list[ItineraryDay], add_ons: list[ItineraryAddOn]) -> str:
    lines = ["the plan:"]
    lines.extend(f"{format_day(day)} · {_timed_plan(day)}" for day in days)
    if add_ons:
        lines.append("optional add-ons:")
        lines.extend(
            f"{add_on.activity} · {add_on.wanted_by}'s pick" for add_on in add_ons
        )
    return "\n".join(lines)


def format_day(day: ItineraryDay) -> str:
    """ "Sun 3/14"."""
    return f"{day.day:%a} {day.day.month}/{day.day.day}"


def format_start(day: ItineraryDay) -> str | None:
    """ "9:30 PM", or None on a loose day."""
    return f"{day.starts_at:%-I:%M %p}" if day.starts_at else None


def _timed_plan(day: ItineraryDay) -> str:
    start = format_start(day)
    return f"{start} · {day.plan}" if start else day.plan
