"""A destination brochure card: what it tells the group, and scout's one accent."""

from datetime import date

from scout.cards import (
    Activity,
    Brochure,
    CostEstimate,
    destination_article,
    trip_interview,
)

SCOUT_BLUE = "#2B2EF3"

SAN_JUAN = Brochure(
    destination="San Juan, Puerto Rico",
    region="Puerto Rico",
    detail="Beaches, a colorful old town and no passport needed.",
    hotel="Condado Vanderbilt Hotel (★ 4.6)",
    costs=[
        CostEstimate("Flights", 350, "airplane"),
        CostEstimate("Hotel", 550, "bed.double.fill"),
    ],
    activities=[
        Activity("Hike El Yunque", 60, "https://example.com/yunque.jpg"),
        Activity("Kayak the bio bay", 85),
    ],
    hero_photo_url="https://example.com/san-juan.jpg",
)


def test_a_brochure_carries_the_place_price_hotel_activities_and_costs():
    card = destination_article(SAN_JUAN, nights=5)
    words = _all_words(card)

    assert (card["title"], card["subtitle"]) == ("San Juan", "Puerto Rico")
    assert "~$900 per person, all in" in words
    assert SAN_JUAN.detail in words
    assert "Condado Vanderbilt Hotel (★ 4.6)" in words
    assert {"Hike El Yunque", "~$60", "Kayak the bio bay", "~$85"} <= words
    assert {"Flights", "~$350", "Hotel", "~$550", "~$900"} <= words
    assert "Estimates for 5 nights. Nothing is booked." in words


def test_a_brochure_swipes_through_the_hero_then_each_activity_photo():
    card = destination_article(SAN_JUAN, nights=5)

    [gallery] = [n for n in card["root"]["children"] if n["type"] == "gallery"]
    assert gallery["urls"] == [
        "https://example.com/san-juan.jpg",
        "https://example.com/yunque.jpg",
    ]


def test_scout_cards_share_one_blue_accent():
    brochure = destination_article(SAN_JUAN, nights=5)
    interview = trip_interview(date(2026, 10, 3))

    assert brochure["accentColorHex"] == SCOUT_BLUE
    assert interview["accentColorHex"] == SCOUT_BLUE


def _all_words(card: dict) -> set[str]:
    """Every string anywhere in the card, so a test can ask what it says."""
    words = set()

    def collect(value):
        if isinstance(value, str):
            words.add(value)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(card)
    return words
