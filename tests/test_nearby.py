from urllib.parse import parse_qs, urlparse

from scout.nearby import describe_travel_time, directions_link, format_nearby_places
from scout.places import Coordinates, Place

CONDADO = Coordinates(18.4574, -66.0745)
# About 640 m from Condado as the crow flies.
LOTE_23 = Coordinates(18.4518, -66.0730)
# About 3.4 km away, across the bay.
OLD_SAN_JUAN = Coordinates(18.4655, -66.1057)


def place(name, location, price="$$", summary="Open-air food park."):
    return Place(f"id-{name}", name, location, price, summary)


def test_nearby_spots_get_a_rough_walking_time():
    assert describe_travel_time(CONDADO, LOTE_23) == "~10 min walk"


def test_far_spots_get_a_driving_time_instead():
    assert describe_travel_time(CONDADO, OLD_SAN_JUAN) == "~11 min drive"


def test_a_spot_right_here_is_still_a_minute_away():
    assert describe_travel_time(CONDADO, CONDADO) == "~1 min walk"


def test_suggestions_are_numbered_with_price_time_and_summary():
    message = format_nearby_places(
        [place("Lote 23", LOTE_23), place("La Placita", OLD_SAN_JUAN, price="$")],
        start=CONDADO,
        area="Condado",
    )

    assert message == (
        "📍 Near Condado:\n"
        "1. Lote 23 · $$ · ~10 min walk\n"
        "   Open-air food park.\n"
        "2. La Placita · $ · ~11 min drive\n"
        "   Open-air food park.\n"
        "Reply with a number and I'll send directions."
    )


def test_without_a_starting_spot_there_is_no_travel_time():
    message = format_nearby_places(
        [place("Lote 23", LOTE_23)], start=None, area="San Juan, Puerto Rico"
    )

    assert message.splitlines()[:2] == [
        "📍 Near San Juan, Puerto Rico:",
        "1. Lote 23 · $$",
    ]


def test_unknown_price_and_summary_are_left_out():
    message = format_nearby_places(
        [place("Lote 23", LOTE_23, price=None, summary=None)],
        start=None,
        area="Condado",
    )

    assert message.splitlines()[:2] == ["📍 Near Condado:", "1. Lote 23"]
    assert message.splitlines()[2].startswith("Reply with a number")


def test_directions_go_to_the_exact_place_from_wherever_you_are():
    link = directions_link(place("Lote 23", LOTE_23))

    query = parse_qs(urlparse(link).query)
    assert link.startswith("https://www.google.com/maps/dir/?")
    assert query == {
        "api": ["1"],
        "destination": ["Lote 23"],
        "destination_place_id": ["id-Lote 23"],
    }
