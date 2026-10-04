"""Finds real flights on Google Flights, through SerpApi (IT-5).

scout never invents a fare: every flight it posts comes from here. Google
Flights has no public API, so SerpApi runs the search and returns the results
as JSON.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime

from scout.booking_links import flight_search_link
from scout.serpapi import SERPAPI_URL, SerpApiError, search_serpapi
from scout.trip import DateWindow

logger = logging.getLogger(__name__)

ROUND_TRIP = "1"
# One adult, so the fare is per person whatever the group's size.
ADULTS = "1"
SERPAPI_TIME_FORMAT = "%Y-%m-%d %H:%M"


class FlightsError(Exception):
    """SerpApi couldn't be reached, refused a search or sent an unusable reply."""


@dataclass(frozen=True)
class Layover:
    # Where a passenger changes planes, as an IATA code, e.g. "FLL".
    airport: str
    duration_minutes: int


@dataclass(frozen=True)
class OneWay:
    """One direction of a round trip, from the first takeoff to the last landing."""

    # IATA codes, e.g. "BOS" and "SJU".
    departure_airport: str
    arrival_airport: str
    departs_at: datetime
    arrives_at: datetime
    # One per leg, e.g. ["B6 1234"] for a nonstop.
    flight_numbers: list[str]
    airlines: list[str]
    # Empty for a nonstop.
    layovers: list[Layover]
    duration_minutes: int


@dataclass(frozen=True)
class Flight:
    """A round trip, the way out and the way back, as Google Flights prices it."""

    outbound: OneWay
    homebound: OneWay
    # The whole round trip, for one person.
    price_usd: int
    # Opens this search on Google Flights, where the group books.
    booking_url: str


class GoogleFlights:
    def __init__(self, api_key: str, api_url: str = SERPAPI_URL):
        self._api_key = api_key
        self._api_url = api_url

    def find_best_flight(
        self, departure_airport: str, arrival_airport: str, dates: DateWindow
    ) -> Flight | None:
        """Google's top pick for a round trip, balancing price, time and stops.
        None when Google finds no flights either way.

        Google lists only the ways out at first; the way back takes a second
        search for the picked way out, and that search's top pick has the
        round trip's price.
        """
        round_trip = {
            "departure_id": departure_airport,
            "arrival_id": arrival_airport,
            "outbound_date": dates.start.isoformat(),
            "return_date": dates.end.isoformat(),
            "type": ROUND_TRIP,
            "adults": ADULTS,
            "currency": "USD",
            "hl": "en",
        }
        outbound_reply = self._search(round_trip)
        outbound = _top_pick(outbound_reply)
        if outbound is None:
            return None
        homebound_reply = self._search(
            {**round_trip, "departure_token": _departure_token(outbound)}
        )
        homebound = _top_pick(homebound_reply)
        if homebound is None:
            return None
        booking_url = (
            _google_flights_url(homebound_reply)
            or _google_flights_url(outbound_reply)
            or flight_search_link(departure_airport, arrival_airport, dates)
        )
        return Flight(
            outbound=_to_one_way(outbound),
            homebound=_to_one_way(homebound),
            price_usd=homebound["price"],
            booking_url=booking_url,
        )

    def _search(self, params: dict[str, str]) -> dict:
        try:
            return search_serpapi(
                self._api_url, self._api_key, "google_flights", params
            )
        except SerpApiError as error:
            raise FlightsError(str(error)) from None


def connect_flights() -> GoogleFlights | None:
    """The flight search to use, or None if no API key is set."""
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        logger.warning("SERPAPI_API_KEY isn't set, so scout can't look up flights")
        return None
    return GoogleFlights(api_key)


def _top_pick(reply: dict) -> dict | None:
    results = reply.get("best_flights") or reply.get("other_flights") or []
    return results[0] if results else None


def _departure_token(outbound: dict) -> str:
    try:
        return outbound["departure_token"]
    except KeyError:
        raise FlightsError(
            "Google Flights listed a way out with no departure_token, "
            "so the way back can't be looked up"
        ) from None


def _google_flights_url(reply: dict) -> str | None:
    return reply.get("search_metadata", {}).get("google_flights_url")


def _to_one_way(result: dict) -> OneWay:
    legs = result["flights"]
    return OneWay(
        departure_airport=legs[0]["departure_airport"]["id"],
        arrival_airport=legs[-1]["arrival_airport"]["id"],
        departs_at=_parse_time(legs[0]["departure_airport"]["time"]),
        arrives_at=_parse_time(legs[-1]["arrival_airport"]["time"]),
        flight_numbers=[leg["flight_number"] for leg in legs],
        airlines=list(dict.fromkeys(leg["airline"] for leg in legs)),
        layovers=[
            Layover(layover["id"], layover["duration"])
            for layover in result.get("layovers", [])
        ],
        duration_minutes=result["total_duration"],
    )


def _parse_time(text: str) -> datetime:
    return datetime.strptime(text, SERPAPI_TIME_FORMAT)
