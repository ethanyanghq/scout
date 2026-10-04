"""GoogleFlights against a stand-in SerpApi server on localhost.

SerpApi is the external boundary here, so a small local HTTP server plays it.
That runs scout's real request code without an API key or a bill.
"""

from datetime import date, datetime

import pytest

from scout.flights import Flight, FlightsError, GoogleFlights, Layover, OneWay
from scout.trip import DateWindow

API_KEY = "test-key"
SPRING_BREAK = DateWindow(date(2027, 3, 14), date(2027, 3, 19))
SEARCH_URL = "https://www.google.com/travel/flights?hl=en&tfs=abc"
RETURN_SEARCH_URL = "https://www.google.com/travel/flights?hl=en&tfs=abc-return"
DEPARTURE_TOKEN = "WyJDalJJ-way-out"


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
    "departure_token": DEPARTURE_TOKEN,
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
    "departure_token": "WyJDalJJ-nonstop",
}
HOME_NONSTOP = {
    "flights": [
        leg(
            "B6 902",
            "JetBlue",
            ("SJU", "2027-03-19 22:30"),
            ("BOS", "2027-03-20 02:45"),
        ),
    ],
    "total_duration": 255,
    # The way back's price is the whole round trip's.
    "price": 334,
    "type": "Round trip",
}
WAY_OUT_RESULTS = {
    "search_metadata": {"status": "Success", "google_flights_url": SEARCH_URL},
    "best_flights": [VIA_FORT_LAUDERDALE, NONSTOP],
    "other_flights": [],
}
WAY_BACK_RESULTS = {
    "search_metadata": {"status": "Success", "google_flights_url": RETURN_SEARCH_URL},
    "best_flights": [HOME_NONSTOP],
    "other_flights": [],
}


def answer_both_ways(way_out, way_back):
    """SerpApi lists the ways out, then the ways back for a departure_token."""
    return lambda query: (200, way_back if "departure_token" in query else way_out)


@pytest.fixture
def flights(serpapi):
    serpapi.reply = answer_both_ways(WAY_OUT_RESULTS, WAY_BACK_RESULTS)
    return GoogleFlights(API_KEY, api_url=serpapi.url)


def test_the_best_flight_is_googles_top_pick_both_ways_with_every_leg(flights):
    flight = flights.find_best_flight("BOS", "SJU", SPRING_BREAK)

    assert flight == Flight(
        outbound=OneWay(
            departure_airport="BOS",
            arrival_airport="SJU",
            departs_at=datetime(2027, 3, 14, 6, 15),
            arrives_at=datetime(2027, 3, 14, 14, 20),
            flight_numbers=["B6 101", "B6 955"],
            airlines=["JetBlue"],
            layovers=[Layover("FLL", 85)],
            duration_minutes=485,
        ),
        homebound=OneWay(
            departure_airport="SJU",
            arrival_airport="BOS",
            departs_at=datetime(2027, 3, 19, 22, 30),
            arrives_at=datetime(2027, 3, 20, 2, 45),
            flight_numbers=["B6 902"],
            airlines=["JetBlue"],
            layovers=[],
            duration_minutes=255,
        ),
        price_usd=334,
        booking_url=RETURN_SEARCH_URL,
    )


def test_the_way_back_is_searched_for_the_picked_way_out(flights, serpapi):
    flights.find_best_flight("BOS", "SJU", SPRING_BREAK)

    way_out_query, way_back_query = serpapi.queries
    assert "departure_token" not in way_out_query
    assert way_back_query["departure_token"] == DEPARTURE_TOKEN
    assert way_back_query["return_date"] == "2027-03-19"


def test_falls_back_to_other_flights_when_google_has_no_best_ones(flights, serpapi):
    serpapi.reply = answer_both_ways(
        {**WAY_OUT_RESULTS, "best_flights": [], "other_flights": [NONSTOP]},
        WAY_BACK_RESULTS,
    )

    flight = flights.find_best_flight("EWR", "SJU", SPRING_BREAK)

    assert flight.outbound.flight_numbers == ["UA 1513"]
    assert flight.outbound.layovers == []


def test_no_way_back_means_no_flight(flights, serpapi):
    serpapi.reply = answer_both_ways(
        WAY_OUT_RESULTS, {**WAY_BACK_RESULTS, "best_flights": []}
    )

    assert flights.find_best_flight("BOS", "SJU", SPRING_BREAK) is None


def test_a_refused_search_says_why(flights, serpapi):
    serpapi.reply = (401, {"error": "Invalid API key."})

    with pytest.raises(FlightsError, match="search failed with 401: Invalid API key"):
        flights.find_best_flight("BOS", "SJU", SPRING_BREAK)
