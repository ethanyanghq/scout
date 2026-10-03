"""How a trip's day-by-day plan reads in the chat (IT-1)."""

from scout.trip import ItineraryDay


def format_itinerary(days: list[ItineraryDay]) -> str:
    lines = ["🗓️ The plan:"]
    lines.extend(
        f"{day.day:%a} {day.day.month}/{day.day.day} · {day.plan}" for day in days
    )
    return "\n".join(lines)
