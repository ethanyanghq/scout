"""The trip interview card's layout: what it asks and how its answers come back."""

import urllib.parse
from datetime import date

from scout.cards import trip_interview


def test_the_interview_offers_the_next_six_months_starting_next_month():
    card = trip_interview(date(2026, 11, 15))

    months = _picker(card, "month")["options"]
    assert [(m["label"], m["sublabel"]) for m in months] == [
        ("December", "2026"),
        ("January", "2027"),
        ("February", "2027"),
        ("March", "2027"),
        ("April", "2027"),
        ("May", "2027"),
    ]


def test_the_interview_asks_how_long_the_budget_and_the_vibe():
    card = trip_interview(date(2026, 10, 3))

    assert "About a week" in _labels(card, "length")
    assert "$500–$800" in _labels(card, "budget")
    assert {"Early riser", "Late nights"} <= set(_labels(card, "vibe"))


def test_sending_answers_fills_in_a_text_that_tags_scout():
    card = trip_interview(date(2026, 10, 3))

    [send] = card["actions"]
    link = urllib.parse.urlsplit(send["deepLinkURL"])
    assert (link.scheme, link.netloc) == ("hermesshare", "text")
    assert urllib.parse.parse_qs(link.query)["lead"] == ["@scout my trip:"]


def _picker(card, field_id):
    return next(
        node for node in card["root"]["children"] if node.get("fieldId") == field_id
    )


def _labels(card, field_id):
    return [option["label"] for option in _picker(card, field_id)["options"]]
