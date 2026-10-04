import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scout.trip_store import TripStore


@pytest.fixture
def store(tmp_path):
    return TripStore(tmp_path / "scout.db")


class FakeSerpApi:
    """Stands in for SerpApi: answers every search with `reply`, a (status, JSON)
    pair a test sets, and keeps each query it got."""

    def __init__(self):
        self.queries = []
        self.reply = (200, {})
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
