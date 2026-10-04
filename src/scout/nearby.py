"""How nearby place suggestions and directions read in the chat (OT-1, OT-3).

Travel times are estimates from straight-line distance, so scout doesn't need
a second, routing API. They're labeled with "~" so nobody takes them as exact.
"""

import math
from urllib.parse import urlencode

from scout.places import Coordinates, Place

GOOGLE_MAPS_DIRECTIONS_URL = "https://www.google.com/maps/dir/"

EARTH_RADIUS_METERS = 6_371_000
# Streets aren't straight lines, so stretch the straight-line distance.
DETOUR_FACTOR = 1.3
WALKING_METERS_PER_MINUTE = 80  # about 5 km/h
DRIVING_METERS_PER_MINUTE = 400  # about 24 km/h in city traffic
# Past this, suggest driving instead of walking.
LONGEST_WALK_MINUTES = 30


def format_nearby_places(
    places: list[Place], start: Coordinates | None, area: str
) -> str:
    """Lists places by number. `area` names where the group is, e.g. "Condado"."""
    lines = [f"near {area}:"]
    for number, place in enumerate(places, start=1):
        details = [place.name]
        if place.price:
            details.append(place.price)
        if start is not None:
            details.append(describe_travel_time(start, place.location))
        lines.append(f"{number}. {' · '.join(details)}")
        if place.summary:
            lines.append(f"   {place.summary}")
    lines.append("reply with a number and i'll send directions.")
    return "\n".join(lines)


def format_directions(place: Place) -> str:
    """The line before the directions link, which goes in a message of its own
    so iMessage shows it as a map card."""
    return f"directions to {place.name}:"


def directions_link(place: Place) -> str:
    # With no origin, Google Maps starts from wherever each member opens the
    # link, so one link works for the whole group.
    query = urlencode(
        {
            "api": 1,
            "destination": place.name,
            "destination_place_id": place.place_id,
        }
    )
    return f"{GOOGLE_MAPS_DIRECTIONS_URL}?{query}"


def describe_travel_time(start: Coordinates, end: Coordinates) -> str:
    """A rough walk, or a drive if the walk is too long: "~8 min walk"."""
    meters = _straight_line_meters(start, end) * DETOUR_FACTOR
    walking_minutes = max(1, round(meters / WALKING_METERS_PER_MINUTE))
    if walking_minutes <= LONGEST_WALK_MINUTES:
        return f"~{walking_minutes} min walk"
    driving_minutes = max(1, round(meters / DRIVING_METERS_PER_MINUTE))
    return f"~{driving_minutes} min drive"


def _straight_line_meters(start: Coordinates, end: Coordinates) -> float:
    # The haversine formula: distance along the Earth's surface.
    start_lat, end_lat = math.radians(start.latitude), math.radians(end.latitude)
    lat_change = end_lat - start_lat
    lng_change = math.radians(end.longitude - start.longitude)
    a = (
        math.sin(lat_change / 2) ** 2
        + math.cos(start_lat) * math.cos(end_lat) * math.sin(lng_change / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))
