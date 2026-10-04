from datetime import date
from urllib.parse import parse_qs, urlparse

from scout.booking_links import (
    flight_search_link,
    format_booking_links,
)
from scout.trip import DateWindow, Member, Trip, TripStage

SPRING_BREAK = DateWindow(date(2027, 3, 14), date(2027, 3, 19))


def member(phone, home_city):
    return Member(
        phone=phone,
        available_from=date(2027, 3, 13),
        available_to=date(2027, 3, 20),
        budget_usd=800,
        home_city=home_city,
    )


def san_juan_trip(*members):
    return Trip(
        space_id="group-chat-1",
        stage=TripStage.DESTINATION_CHOSEN,
        destination="San Juan, Puerto Rico",
        dates=SPRING_BREAK,
        members=list(members),
        open_poll=None,
        itinerary=[],
        expenses=[],
        settlements=[],
        pending_receipt=None,
        place_suggestions=[],
    )


def test_flight_search_goes_from_home_city_to_destination_on_trip_dates():
    link = flight_search_link("Boston", "San Juan, Puerto Rico", SPRING_BREAK)

    search = parse_qs(urlparse(link).query)["q"][0]
    assert search == (
        "Flights to San Juan, Puerto Rico from Boston on 2027-03-14 through 2027-03-19"
    )


def test_members_from_the_same_city_share_one_flight_link():
    trip = san_juan_trip(
        member("+15550000001", "Boston"),
        member("+15550000002", "boston"),
        member("+15550000003", "Chicago"),
    )

    lines = format_booking_links(trip).split("\n")

    flight_cities = [line.split(":")[0] for line in lines[1:-2]]
    assert flight_cities == ["Boston", "Chicago"]
    assert lines[-2].startswith("stays for 3: https://www.airbnb.com/s/")
