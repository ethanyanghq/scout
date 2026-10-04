"""GooglePlaces against a stand-in Places server on localhost.

Google is the external boundary here, so a small local HTTP server plays it.
That runs scout's real request code without an API key or a bill.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scout.places import (
    Coordinates,
    GooglePlaces,
    PhotographedPlace,
    Place,
    PlacesError,
)

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
BEACH_RESORT = {
    "displayName": {"text": "Hotel Xcaret Arte"},
    "rating": 4.7,
    "photos": [
        {"name": "places/resort-1/photos/pool"},
        {"name": "places/resort-1/photos/beach"},
        {"name": "places/resort-1/photos/lobby"},
    ],
}


class FakePlaces:
    """Answers every search with `reply`, and each photo with a public link
    named after it. Keeps each request it got."""

    def __init__(self):
        self.requests = []
        self.reply = (200, {"places": [TACO_SPOT]})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self):
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"

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

            def do_GET(self):
                fake.requests.append({"headers": self.headers, "path": self.path})
                photo = self.path.split("/photos/")[1].split("/media")[0]
                reply = {"photoUri": f"https://lh3.googleusercontent.com/{photo}"}
                encoded = json.dumps(reply).encode()
                self.send_response(200)
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
    return GooglePlaces(API_KEY, api_url=google.url)


def test_search_results_become_places_with_a_price_and_summary(places):
    [place] = places.search("tacos with outdoor seating", limit=3)

    assert place == Place(
        place_id="place-1",
        name="Lote 23",
        location=Coordinates(18.4518, -66.0702),
        price="$$",
        summary="Open-air food park with local vendors.",
    )


def test_search_near_a_spot_looks_around_it_first(places, google):
    places.search("tacos", limit=3, near=CONDADO)

    circle = google.requests[0]["body"]["locationBias"]["circle"]
    assert circle["center"] == {"latitude": 18.4574, "longitude": -66.0745}


def test_a_refused_search_says_why(places, google):
    google.reply = (403, {"error": {"message": "API key not valid"}})

    with pytest.raises(PlacesError, match="search failed with 403.*API key not valid"):
        places.search("tacos", limit=3)


def test_a_photographed_place_has_its_rating_and_public_photo_links(places, google):
    google.reply = (200, {"places": [BEACH_RESORT]})

    resort = places.find_photographed("best resort in Cancun", photo_count=2)

    assert resort == PhotographedPlace(
        name="Hotel Xcaret Arte",
        rating=4.7,
        photo_urls=[
            "https://lh3.googleusercontent.com/pool",
            "https://lh3.googleusercontent.com/beach",
        ],
    )
