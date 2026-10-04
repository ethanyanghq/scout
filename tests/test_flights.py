"""GoogleFlights against a stand-in SerpApi server on localhost.

SerpApi is the external boundary here, so a small local HTTP server plays it.
That runs scout's real request code without an API key or a bill.
"""

import json
import threading
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


class FakeSerpApi:
    """Answers every search with `reply`, and keeps each query it got."""

    def __init__(self):
        self.queries = []
        self.reply = (200, SEARCH_RESULTS)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self):
        host, port = self._server.server_address
        return f"http://{host}:{port}/search.json"

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    def _serve(self):
        # A short poll interval makes shutdown, and so each test, quick.
        self._server.serve_forever(poll_interval=0.01)

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.urlparse(self.path).query
                fake.queries.append(dict(urllib.parse.parse_qsl(query)))
                status, reply = fake.reply
                encoded = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args):
                pass  # Keep test output quiet.

        return Handler


@pytest.fixture
def serpapi():
    fake = FakeSerpApi()
    yield fake
    fake.stop()


@pytest.fixture
def flights(serpapi):
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


def test_searches_a_round_trip_for_one_adult_so_fares_are_per_person(flights, serpapi):
    flights.find_best_flight("BOS", "SJU", SPRING_BREAK)

    [query] = serpapi.queries
    assert query["engine"] == "google_flights"
    assert query["api_key"] == API_KEY
    assert query["departure_id"] == "BOS"
    assert query["arrival_id"] == "SJU"
    assert query["outbound_date"] == "2027-03-14"
    assert query["return_date"] == "2027-03-19"
    assert query["type"] == "1"
    assert query["adults"] == "1"
    assert query["currency"] == "USD"


def test_falls_back_to_other_flights_when_google_has_no_best_ones(flights, serpapi):
    serpapi.reply = (
        200,
        {**SEARCH_RESULTS, "best_flights": [], "other_flights": [NONSTOP]},
    )

    flight = flights.find_best_flight("EWR", "SJU", SPRING_BREAK)

    assert flight.flight_numbers == ["UA 1513"]
    assert flight.layover_airports == []


def test_no_flights_is_none(flights, serpapi):
    serpapi.reply = (
        200,
        {"error": "Google Flights hasn't returned any results for this query."},
    )

    assert flights.find_best_flight("BOS", "XXX", SPRING_BREAK) is None


def test_without_googles_search_link_the_booking_link_is_a_plain_search(
    flights, serpapi
):
    serpapi.reply = (200, {**SEARCH_RESULTS, "search_metadata": {}})

    flight = flights.find_best_flight("BOS", "SJU", SPRING_BREAK)

    assert flight.booking_url.startswith("https://www.google.com/travel/flights?q=")
    assert "BOS" in flight.booking_url


def test_a_refused_search_says_why(flights, serpapi):
    serpapi.reply = (401, {"error": "Invalid API key."})

    with pytest.raises(FlightsError, match="search failed with 401: Invalid API key"):
        flights.find_best_flight("BOS", "SJU", SPRING_BREAK)


def test_an_unreachable_serpapi_raises_a_flights_error(serpapi):
    serpapi.stop()
    flights = GoogleFlights(API_KEY, api_url=serpapi.url)

    with pytest.raises(FlightsError, match="didn't connect"):
        flights.find_best_flight("BOS", "SJU", SPRING_BREAK)
