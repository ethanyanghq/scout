from urllib.parse import parse_qs, urlparse

from scout.nearby import describe_travel_time, directions_link
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


def test_directions_go_to_the_exact_place_from_wherever_you_are():
    link = directions_link(place("Lote 23", LOTE_23))

    query = parse_qs(urlparse(link).query)
    assert link.startswith("https://www.google.com/maps/dir/?")
    assert query == {
        "api": ["1"],
        "destination": ["Lote 23"],
        "destination_place_id": ["id-Lote 23"],
    }
