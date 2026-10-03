"""NessieBank against a stand-in Nessie server on localhost.

Nessie is the external boundary here, so a small local HTTP server plays it.
That runs scout's real request code without touching the shared sandbox.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from scout.nessie import STARTING_BALANCE_USD, NessieBank, NessieError

API_KEY = "test-key"


class FakeNessie:
    """Answers each POST with a new ID, or with a canned reply."""

    def __init__(self):
        self.requests = []
        self.canned_reply = None  # (status, body) to answer with instead of a new ID
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self):
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def _serve(self):
        # A short poll interval makes shutdown, and so each test, quick.
        self._server.serve_forever(poll_interval=0.01)

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    def _handler(self):
        nessie = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                url = urlparse(self.path)
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                nessie.requests.append(
                    {"path": url.path, "query": parse_qs(url.query), "body": body}
                )
                status, reply = nessie.canned_reply or (
                    201,
                    {"objectCreated": {"_id": f"id-{len(nessie.requests)}"}},
                )
                encoded = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args):
                pass  # Keep test output quiet.

        return Handler


@pytest.fixture
def nessie():
    fake = FakeNessie()
    yield fake
    fake.stop()


@pytest.fixture
def bank(nessie):
    return NessieBank(API_KEY, base_url=nessie.url)


def test_opening_an_account_creates_a_customer_then_a_funded_checking_account(
    bank, nessie
):
    account_id = bank.open_account()

    customer, account = nessie.requests
    assert customer["path"] == "/customers"
    assert account["path"] == "/customers/id-1/accounts"
    assert account["body"]["type"] == "Checking"
    assert account["body"]["balance"] == STARTING_BALANCE_USD
    assert account_id == "id-2"


def test_every_request_carries_the_api_key(bank, nessie):
    bank.open_account()

    assert all(r["query"] == {"key": [API_KEY]} for r in nessie.requests)


def test_moving_money_withdraws_from_the_payer_and_deposits_to_the_payee(bank, nessie):
    payment = bank.move_money("jordan-account", "leo-account", 40_000)

    withdrawal, deposit = nessie.requests
    assert withdrawal["path"] == "/accounts/jordan-account/withdrawals"
    assert deposit["path"] == "/accounts/leo-account/deposits"
    assert withdrawal["body"]["amount"] == deposit["body"]["amount"] == 400
    assert payment == ("id-1", "id-2")


@pytest.mark.parametrize(
    ("amount_cents", "whole_dollars"), [(23_650, 237), (23_649, 236), (40, 1)]
)
def test_nessie_gets_whole_dollars_rounded_half_up_and_never_zero(
    bank, nessie, amount_cents, whole_dollars
):
    bank.move_money("maya-account", "leo-account", amount_cents)

    assert nessie.requests[0]["body"]["amount"] == whole_dollars


def test_a_refused_request_says_what_failed_without_the_api_key(bank, nessie):
    nessie.canned_reply = (401, "Invalid API key.")

    with pytest.raises(NessieError, match="POST /customers failed with 401") as error:
        bank.open_account()
    assert API_KEY not in str(error.value)


def test_an_unreachable_nessie_raises_a_nessie_error(nessie):
    nessie.stop()
    bank = NessieBank(API_KEY, base_url=nessie.url)

    with pytest.raises(NessieError, match="didn't connect"):
        bank.open_account()


def test_ids_named_id_instead_of_underscore_id_still_work(bank, nessie):
    nessie.canned_reply = (201, {"objectCreated": {"id": "uuid-7"}})

    assert bank.move_money("a", "b", 100) == ("uuid-7", "uuid-7")
