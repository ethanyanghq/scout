"""Moves sandbox money between members over Capital One's Nessie API (CS-3).

Nessie is a fake bank for hackathons: its customers, accounts, and balances
aren't real, so this is a demo payment rail, not a real one. scout's own
ledger stays the source of truth for who owes whom; Nessie mirrors each
payment so the money visibly moves.

The live API differs from its old docs (checked October 2026):
- It's HTTPS only, with the key as a `?key=` query parameter.
- Transfers have no payee field, so a payment is a withdrawal from the payer's
  account plus a deposit into the payee's.
- Amounts are whole dollars.
- Its enterprise endpoints show every team's data to anyone with a key, so
  scout sends placeholder names and addresses, never members' details.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import date
from typing import NamedTuple
from urllib.parse import urlencode

from scout.money import CENTS_PER_DOLLAR

logger = logging.getLogger(__name__)

NESSIE_URL = "https://api.nessieisreal.com"
# Nessie has been slow and flaky at past hackathons. A payment that hangs
# longer than this is recorded as simulated instead of stalling the chat.
TIMEOUT_SECONDS = 8
STARTING_BALANCE_USD = 2_000
PLACEHOLDER_CUSTOMER = {
    "first_name": "scout",
    "last_name": "traveler",
    "address": {
        "street_number": "1",
        "street_name": "Main St",
        "city": "Boston",
        "state": "MA",
        "zip": "02108",
    },
}


class NessieError(Exception):
    """Nessie couldn't be reached or refused a request."""


class SandboxPayment(NamedTuple):
    """Where one payment shows up in Nessie, for checking it there."""

    withdrawal_id: str
    deposit_id: str


class NessieBank:
    def __init__(self, api_key: str, base_url: str = NESSIE_URL):
        self._api_key = api_key
        self._base_url = base_url

    def open_account(self) -> str:
        """Opens a funded checking account for one member. Returns its ID."""
        customer_id = self._post("/customers", PLACEHOLDER_CUSTOMER)
        return self._post(
            f"/customers/{customer_id}/accounts",
            {
                "type": "Checking",
                "nickname": "scout trip",
                "rewards": 0,
                "balance": STARTING_BALANCE_USD,
            },
        )

    def move_money(
        self, from_account_id: str, to_account_id: str, amount_cents: int
    ) -> SandboxPayment:
        payment = {
            "medium": "balance",
            "amount": _whole_dollars(amount_cents),
            "transaction_date": date.today().isoformat(),
            "description": "scout settle-up",
        }
        return SandboxPayment(
            withdrawal_id=self._post(
                f"/accounts/{from_account_id}/withdrawals", payment
            ),
            deposit_id=self._post(f"/accounts/{to_account_id}/deposits", payment),
        )

    def _post(self, path: str, body: dict) -> str:
        """Creates something in Nessie and returns its ID."""
        request = urllib.request.Request(
            f"{self._base_url}{path}?{urlencode({'key': self._api_key})}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Error messages name the path only: the full URL carries the API key.
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
                created = json.load(reply)["objectCreated"]
            # Newer Nessie objects sometimes say "id" instead of "_id".
            return created.get("_id") or created["id"]
        except urllib.error.HTTPError as error:
            reason = error.read().decode(errors="replace")[:200]
            raise NessieError(
                f"POST {path} failed with {error.code}: {reason}"
            ) from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise NessieError(f"POST {path} didn't connect: {error}") from None
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise NessieError(
                f"POST {path} sent an unexpected reply: {error}"
            ) from None


def connect_bank() -> NessieBank | None:
    """The Nessie bank to pay through, or None if no API key is set."""
    api_key = os.environ.get("NESSIE_API_KEY")
    if not api_key:
        logger.warning("NESSIE_API_KEY isn't set, so payments will be simulated")
        return None
    return NessieBank(api_key)


def _whole_dollars(amount_cents: int) -> int:
    # Nessie only stores whole dollars. scout's ledger keeps the exact cents;
    # the sandbox mirror rounds half up, and never to $0.
    rounded = (amount_cents + CENTS_PER_DOLLAR // 2) // CENTS_PER_DOLLAR
    return max(1, rounded)
