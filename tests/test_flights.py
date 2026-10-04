"""GoogleFlights against a stand-in SerpApi server on localhost.

SerpApi is the external boundary here, so a small local HTTP server plays it.
That runs scout's real request code without an API key or a bill.
"""

from datetime import date, datetime

import pytest

from scout.flights import Flight, FlightsError, GoogleFlights
from scout.trip import DateWindow

API_KEY = "test-key"
SPRING_BREAK = DateWindow(date(2027, 3, 14), date(2027, 3, 19))
SAN_JUAN_PHOTO = "https://lh5.googleusercontent.com/san-juan"
SEARCH_URL = "https://www.google.com/travel/flights?hl=en&tfs=abc"


def leg(flight_number, airline, departs, arrives):
    """One plane in a flight, as SerpApi lists it."""
    (from_code, departs_at), (to_code, arrives_at) = departs, arrives
    return {
        "departure_airport": {"name": from_code, "id": from_code, "time": departs_at},
        "arrival_airport": {"name": to_code, "id": to_code, "time": arrives_at},
        "duration": 150,
        "airline": airline,
        "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/B6.png",
        "flight_number": flight_number,
        "travel_class": "Economy",
    }


VIA_FORT_LAUDERDALE = {
    "flights": [
        leg(
            "B6 101",
            "JetBlue",
            ("BOS", "2027-03-14 06:15"),
            ("FLL", "2027-03-14 09:40"),
        ),
        leg(
            "B6 955",
            "JetBlue",
            ("FLL", "2027-03-14 11:05"),
            ("SJU", "2027-03-14 14:20"),
        ),
    ],
    "layovers": [{"duration": 85, "name": "Fort Lauderdale", "id": "FLL"}],
    "total_duration": 485,
    "price": 312,
    "type": "Round trip",
}
NONSTOP = {
    "flights": [
        leg(
            "UA 1513",
            "United",
            ("EWR", "2027-03-14 08:00"),
            ("SJU", "2027-03-14 12:05"),
        ),
    ],
    "total_duration": 245,
    "price": 389,
    "type": "Round trip",
}
SEARCH_RESULTS = {
    "search_metadata": {"status": "Success", "google_flights_url": SEARCH_URL},
    "best_flights": [VIA_FORT_LAUDERDALE, NONSTOP],
    "other_flights": [],
    "airports": [
        {
            "departure": [{"airport": {"id": "BOS"}, "city": "Boston"}],
            "arrival": [
                {"airport": {"id": "SJU"}, "city": "San Juan", "image": SAN_JUAN_PHOTO}
            ],
        }
    ],
}


@pytest.fixture
def flights(serpapi):
    serpapi.reply = (200, SEARCH_RESULTS)
    return GoogleFlights(API_KEY, api_url=serpapi.url)


def test_the_best_flight_is_googles_top_pick_with_every_leg(flights):
    flight = flights.find_best_flight("BOS", "SJU", SPRING_BREAK)

    assert flight == Flight(
        departure_airport="BOS",
        arrival_airport="SJU",
        departs_at=datetime(2027, 3, 14, 6, 15),
        arrives_at=datetime(2027, 3, 14, 14, 20),
        flight_numbers=["B6 101", "B6 955"],
        airlines=["JetBlue"],
        layover_airports=["FLL"],
        duration_minutes=485,
        price_usd=312,
        booking_url=SEARCH_URL,
        destination_photo_url=SAN_JUAN_PHOTO,
    )


def test_falls_back_to_other_flights_when_google_has_no_best_ones(flights, serpapi):
    serpapi.reply = (
        200,
        {**SEARCH_RESULTS, "best_flights": [], "other_flights": [NONSTOP]},
    )

    flight = flights.find_best_flight("EWR", "SJU", SPRING_BREAK)

    assert flight.flight_numbers == ["UA 1513"]
    assert flight.layover_airports == []


def test_a_refused_search_says_why(flights, serpapi):
    serpapi.reply = (401, {"error": "Invalid API key."})

    with pytest.raises(FlightsError, match="search failed with 401: Invalid API key"):
        flights.find_best_flight("BOS", "SJU", SPRING_BREAK)
