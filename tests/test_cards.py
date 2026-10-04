"""The trip interview card's layout: what it asks and how its answers come back."""

import urllib.parse
from datetime import date

from scout.cards import trip_interview


def test_the_interview_picks_real_dates_from_today_on():
    card = trip_interview(date(2026, 11, 15))

    calendar = _input(card, "dates")
    assert calendar["type"] == "dateRangePicker"
    assert calendar["earliestDate"] == "2026-11-15"


def test_the_budget_is_a_slider_from_0_to_3000_labeled_every_500():
    card = trip_interview(date(2026, 10, 3))

    slider = _input(card, "budget")
    assert slider["type"] == "slider"
    assert (slider["minValue"], slider["maxValue"]) == (0, 3000)
    assert (slider["tickStep"], slider["value"]) == (500, 1000)


def test_the_interview_asks_for_the_kind_of_trip():
    card = trip_interview(date(2026, 10, 3))

    vibes = [option["label"] for option in _input(card, "vibe")["options"]]
    assert {"Early riser", "Late nights"} <= set(vibes)


def test_sending_answers_fills_in_a_text_that_tags_scout():
    card = trip_interview(date(2026, 10, 3))

    [send] = card["actions"]
    link = urllib.parse.urlsplit(send["deepLinkURL"])
    assert (link.scheme, link.netloc) == ("hermesshare", "text")
    assert urllib.parse.parse_qs(link.query)["lead"] == ["@scout my trip:"]


def _input(card, field_id):
    return next(
        node for node in card["root"]["children"] if node.get("fieldId") == field_id
    )
