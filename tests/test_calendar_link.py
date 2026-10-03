from datetime import date
from urllib.parse import parse_qs, urlparse

from scout.calendar_link import format_calendar_message, google_calendar_link
from scout.trip import DateWindow

SPRING_BREAK = DateWindow(date(2027, 3, 14), date(2027, 3, 19))


def link_fields(link):
    return {key: values[0] for key, values in parse_qs(urlparse(link).query).items()}


def test_all_day_trip_ends_the_day_after_its_last_day():
    fields = link_fields(google_calendar_link("San Juan, Puerto Rico", SPRING_BREAK))

    assert fields["dates"] == "20270314/20270320"


def test_event_is_named_and_located_after_the_destination():
    fields = link_fields(google_calendar_link("San Juan, Puerto Rico", SPRING_BREAK))

    assert fields["action"] == "TEMPLATE"
    assert fields["text"] == "Trip to San Juan, Puerto Rico"
    assert fields["location"] == "San Juan, Puerto Rico"


def test_trip_ending_on_the_last_day_of_a_month_rolls_into_the_next():
    month_end = DateWindow(date(2027, 3, 28), date(2027, 3, 31))

    fields = link_fields(google_calendar_link("Tulum, Mexico", month_end))

    assert fields["dates"] == "20270328/20270401"


def test_message_says_what_was_locked_in_before_the_link():
    message = format_calendar_message("San Juan, Puerto Rico", SPRING_BREAK)

    first_line, link = message.split("\n")
    assert first_line == (
        "📅 Locked in: San Juan, Puerto Rico, Mar 14–19. Add it to your calendar:"
    )
    assert link.startswith("https://calendar.google.com/calendar/render?")
