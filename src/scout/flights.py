"""Finds real flights on Google Flights, through SerpApi (IT-5).

scout never invents a fare: every flight it posts comes from here. Google
Flights has no public API, so SerpApi runs the search and returns the results
as JSON.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from scout.booking_links import flight_search_link
from scout.trip import DateWindow

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
# A Google Flights search often takes several seconds on SerpApi's side.
TIMEOUT_SECONDS = 30
ROUND_TRIP = "1"
# One adult, so the fare is per person whatever the group's size.
ADULTS = "1"
SERPAPI_TIME_FORMAT = "%Y-%m-%d %H:%M"


class FlightsError(Exception):
    """SerpApi couldn't be reached or refused a search."""


@dataclass(frozen=True)
class Flight:
    """One round trip's way out, as Google Flights lists it.

    Google prices the whole round trip but lists only the outbound legs until
    one is picked, so the return isn't shown.
    """

    # IATA codes, e.g. "BOS" and "SJU".
    departure_airport: str
    arrival_airport: str
    departs_at: datetime
    arrives_at: datetime
    # One per leg, e.g. ["B6 1234"] for a nonstop.
    flight_numbers: list[str]
    airlines: list[str]
    # Where a passenger changes planes, as IATA codes. Empty for a nonstop.
    layover_airports: list[str]
    duration_minutes: int
    # The whole round trip, for one person.
    price_usd: int
    # Opens this search on Google Flights, where the group books.
    booking_url: str
    # A photo of the destination city, when Google has one.
    destination_photo_url: str | None


class GoogleFlights:
    def __init__(self, api_key: str, api_url: str = SERPAPI_URL):
        self._api_key = api_key
        self._api_url = api_url

    def find_best_flight(
        self, departure_airport: str, arrival_airport: str, dates: DateWindow
    ) -> Flight | None:
        """Google's top pick for a round trip, balancing price, time and stops.
        None when Google finds no flights."""
        reply = self._search(
            {
                "departure_id": departure_airport,
                "arrival_id": arrival_airport,
                "outbound_date": dates.start.isoformat(),
                "return_date": dates.end.isoformat(),
                "type": ROUND_TRIP,
                "adults": ADULTS,
                "currency": "USD",
                "hl": "en",
            }
        )
        results = reply.get("best_flights") or reply.get("other_flights") or []
        if not results:
            return None
        booking_url = reply.get("search_metadata", {}).get(
            "google_flights_url"
        ) or flight_search_link(departure_airport, arrival_airport, dates)
        return _to_flight(results[0], booking_url, _destination_photo(reply))

    def _search(self, params: dict[str, str]) -> dict:
        query = urllib.parse.urlencode(
            {"engine": "google_flights", **params, "api_key": self._api_key}
        )
        try:
            with urllib.request.urlopen(
                f"{self._api_url}?{query}", timeout=TIMEOUT_SECONDS
            ) as reply:
                return json.load(reply)
        except urllib.error.HTTPError as error:
            raise FlightsError(
                f"search failed with {error.code}: {_error_reason(error)}"
            ) from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise FlightsError(f"search didn't connect: {error}") from None
        except json.JSONDecodeError as error:
            raise FlightsError(f"search sent an unexpected reply: {error}") from None


def connect_flights() -> GoogleFlights | None:
    """The flight search to use, or None if no API key is set."""
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        logger.warning("SERPAPI_API_KEY isn't set, so scout can't look up flights")
        return None
    return GoogleFlights(api_key)


def _to_flight(result: dict, booking_url: str, photo_url: str | None) -> Flight:
    legs = result["flights"]
    return Flight(
        departure_airport=legs[0]["departure_airport"]["id"],
        arrival_airport=legs[-1]["arrival_airport"]["id"],
        departs_at=_parse_time(legs[0]["departure_airport"]["time"]),
        arrives_at=_parse_time(legs[-1]["arrival_airport"]["time"]),
        flight_numbers=[leg["flight_number"] for leg in legs],
        airlines=list(dict.fromkeys(leg["airline"] for leg in legs)),
        layover_airports=[layover["id"] for layover in result.get("layovers", [])],
        duration_minutes=result["total_duration"],
        price_usd=result["price"],
        booking_url=booking_url,
        destination_photo_url=photo_url,
    )


def _destination_photo(reply: dict) -> str | None:
    for airports in reply.get("airports", []):
        for arrival in airports.get("arrival", []):
            if arrival.get("image"):
                return arrival["image"]
    return None


def _parse_time(text: str) -> datetime:
    return datetime.strptime(text, SERPAPI_TIME_FORMAT)


def _error_reason(error: urllib.error.HTTPError) -> str:
    """SerpApi's own explanation, e.g. "Invalid API key.", if it sent one."""
    body = error.read().decode(errors="replace")
    try:
        return json.loads(body)["error"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return body[:200]
