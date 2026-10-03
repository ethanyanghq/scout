"""Search links for flights and stays (IT-2).

scout never books anything. These links open Google Flights and Airbnb with
the trip already filled in, and the group books there themselves.
"""

from urllib.parse import quote, urlencode

from scout.group_summary import format_window, summarize_group
from scout.trip import DateWindow, Trip

GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights"
AIRBNB_SEARCH_URL = "https://www.airbnb.com/s"


def format_booking_links(trip: Trip) -> str:
    """Expects a trip whose destination and dates are locked in."""
    lines = [f"✈️ Flights for {format_window(trip.dates)}:"]
    lines.extend(
        f"{city}: {flight_search_link(city, trip.destination, trip.dates)}"
        for city in summarize_group(trip.members).home_cities
    )
    guest_count = len(trip.members)
    lines.append(
        f"🏠 Stays for {guest_count}: "
        f"{stay_search_link(trip.destination, trip.dates, guest_count)}"
    )
    lines.append("You book these yourselves. Live prices there beat my estimates.")
    return "\n".join(lines)


def flight_search_link(home_city: str, destination: str, dates: DateWindow) -> str:
    # Google Flights understands a plain-English search, so scout doesn't need
    # to know airport codes for every home city.
    search = (
        f"Flights to {destination} from {home_city} "
        f"on {dates.start.isoformat()} through {dates.end.isoformat()}"
    )
    return f"{GOOGLE_FLIGHTS_URL}?{urlencode({'q': search}, quote_via=quote)}"


def stay_search_link(destination: str, dates: DateWindow, guest_count: int) -> str:
    # The stay runs from the first day to the last, when everyone flies home.
    query = urlencode(
        {
            "checkin": dates.start.isoformat(),
            "checkout": dates.end.isoformat(),
            "adults": guest_count,
        }
    )
    return f"{AIRBNB_SEARCH_URL}/{quote(destination)}/homes?{query}"
