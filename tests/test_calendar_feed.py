from datetime import date, datetime, time

from scout.calendar_feed import build_calendar_feed, calendar_subscription_url
from scout.trip import DateWindow, ItineraryDay, Trip, TripStage

GENERATED_AT = datetime(2027, 3, 1, 12, 0)


def trip_with(itinerary):
    return Trip(
        space_id="chat-1",
        stage=TripStage.DESTINATION_CHOSEN,
        destination="San Juan, Puerto Rico",
        dates=DateWindow(date(2027, 3, 14), date(2027, 3, 19)),
        members=[],
        open_poll=None,
        itinerary=itinerary,
        itinerary_add_ons=[],
        activity_deck=None,
        expenses=[],
        settlements=[],
        pending_receipt=None,
        place_suggestions=[],
    )


def feed_lines(itinerary):
    feed = build_calendar_feed(trip_with(itinerary), GENERATED_AT)
    return feed.replace("\r\n ", "").split("\r\n")


def test_each_planned_day_is_an_event_starting_when_its_anchor_does():
    lines = feed_lines(
        [ItineraryDay(date(2027, 3, 15), "Night kayak", time(21, 30))],
    )

    assert "SUMMARY:Night kayak" in lines
    assert "DTSTART:20270315T213000" in lines
    assert "DTEND:20270315T233000" in lines


def test_a_loose_day_is_an_all_day_event_ending_the_day_after():
    lines = feed_lines([ItineraryDay(date(2027, 3, 31), "Fly home")])

    assert "DTSTART;VALUE=DATE:20270331" in lines
    assert "DTEND;VALUE=DATE:20270401" in lines


def test_event_text_escapes_what_calendars_treat_as_syntax():
    lines = feed_lines([ItineraryDay(date(2027, 3, 14), "Tapas; wine, views")])

    assert "SUMMARY:Tapas\\; wine\\, views" in lines


def test_long_lines_are_folded_without_losing_text():
    plan = "Old San Juan walking tour with a long lunch " * 4
    feed = build_calendar_feed(
        trip_with([ItineraryDay(date(2027, 3, 14), plan)]), GENERATED_AT
    )

    assert all(len(line.encode()) <= 75 for line in feed.split("\r\n"))
    assert f"SUMMARY:{plan.replace(',', '\\,')}" in feed.replace("\r\n ", "")


def test_subscription_url_uses_the_webcal_scheme_so_phones_offer_to_subscribe():
    url = calendar_subscription_url("https://scout.example.com/", "chat 1")

    assert url == "webcal://scout.example.com/calendars/chat%201.ics"
