"""GooglePlaces against a stand-in Places server on localhost.

Google is the external boundary here, so a small local HTTP server plays it.
That runs scout's real request code without an API key or a bill.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scout.places import Coordinates, GooglePlaces, Place, PlacesError

API_KEY = "test-key"
CONDADO = Coordinates(18.4574, -66.0745)
TACO_SPOT = {
    "id": "place-1",
    "displayName": {"text": "Lote 23", "languageCode": "en"},
    "location": {"latitude": 18.4518, "longitude": -66.0702},
    "priceLevel": "PRICE_LEVEL_MODERATE",
    "editorialSummary": {"text": "Open-air food park with local vendors."},
    "primaryTypeDisplayName": {"text": "Food court"},
}


class FakePlaces:
    """Answers every search with `reply`, and keeps each request it got."""

    def __init__(self):
        self.requests = []
        self.reply = (200, {"places": [TACO_SPOT]})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self):
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1/places:searchText"

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    def _serve(self):
        # A short poll interval makes shutdown, and so each test, quick.
        self._server.serve_forever(poll_interval=0.01)

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                # Header names are case-insensitive, so keep the lookup that knows it.
                fake.requests.append({"headers": self.headers, "body": body})
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
def google():
    fake = FakePlaces()
    yield fake
    fake.stop()


@pytest.fixture
def places(google):
    return GooglePlaces(API_KEY, search_url=google.url)


def test_search_results_become_places_with_a_price_and_summary(places):
    [place] = places.search("tacos with outdoor seating", limit=3)

    assert place == Place(
        place_id="place-1",
        name="Lote 23",
        location=Coordinates(18.4518, -66.0702),
        price="$$",
        summary="Open-air food park with local vendors.",
    )


def test_search_sends_the_query_key_and_field_mask(places, google):
    places.search("tacos with outdoor seating", limit=3)

    [request] = google.requests
    assert request["body"] == {"textQuery": "tacos with outdoor seating", "pageSize": 3}
    assert request["headers"]["X-Goog-Api-Key"] == API_KEY
    assert "places.priceLevel" in request["headers"]["X-Goog-FieldMask"]


def test_search_near_a_spot_looks_around_it_first(places, google):
    places.search("tacos", limit=3, near=CONDADO)

    circle = google.requests[0]["body"]["locationBias"]["circle"]
    assert circle["center"] == {"latitude": 18.4574, "longitude": -66.0745}


def test_places_without_a_summary_are_described_by_their_kind(places, google):
    google.reply = (
        200,
        {"places": [{**TACO_SPOT, "editorialSummary": None}]},
    )

    [place] = places.search("tacos", limit=3)

    assert place.summary == "Food court"


def test_unknown_price_levels_are_left_out(places, google):
    google.reply = (
        200,
        {"places": [{**TACO_SPOT, "priceLevel": "PRICE_LEVEL_UNSPECIFIED"}]},
    )

    [place] = places.search("tacos", limit=3)

    assert place.price is None


def test_no_matches_is_an_empty_list(places, google):
    google.reply = (200, {})

    assert places.search("igloo bar", limit=3) == []


def test_search_never_returns_more_than_asked(places, google):
    google.reply = (200, {"places": [TACO_SPOT] * 5})

    assert len(places.search("tacos", limit=3)) == 3


def test_a_refused_search_says_why(places, google):
    google.reply = (403, {"error": {"message": "API key not valid"}})

    with pytest.raises(PlacesError, match="search failed with 403.*API key not valid"):
        places.search("tacos", limit=3)


def test_an_unreachable_places_api_raises_a_places_error(google):
    google.stop()
    places = GooglePlaces(API_KEY, search_url=google.url)

    with pytest.raises(PlacesError, match="didn't connect"):
        places.search("tacos", limit=3)
