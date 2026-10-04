"""Finds real hotels on Google Hotels, through SerpApi.

scout never invents a rate: every hotel it posts comes from here. Google Hotels
has no public API, so SerpApi runs the search and returns the results as JSON.
"""

import logging
import os
from dataclasses import dataclass

from scout.booking_links import hotel_search_link
from scout.serpapi import SERPAPI_URL, SerpApiError, search_serpapi
from scout.trip import DateWindow

logger = logging.getLogger(__name__)

# Two guests, so the rate is for one double room, not for the whole group.
GUESTS_PER_ROOM = "2"


class HotelsError(Exception):
    """SerpApi couldn't be reached or refused a search."""


@dataclass(frozen=True)
class Hotel:
    name: str
    # Guests' average out of 5, and how many rated. None when nobody has.
    guest_rating: float | None
    review_count: int | None
    nights: int
    # For one room, before any taxes and fees Google adds at checkout.
    nightly_rate_usd: int
    stay_total_usd: int
    photo_url: str | None
    # Opens this search on Google Hotels, where the group books.
    booking_url: str


class GoogleHotels:
    def __init__(self, api_key: str, api_url: str = SERPAPI_URL):
        self._api_key = api_key
        self._api_url = api_url

    def find_best_hotel(self, destination: str, dates: DateWindow) -> Hotel | None:
        """Google's top-ranked hotel with a room free on the dates. None when
        Google lists no hotel with a rate."""
        reply = self._search(
            {
                "q": f"hotels in {destination}",
                "check_in_date": dates.start.isoformat(),
                "check_out_date": dates.end.isoformat(),
                "adults": GUESTS_PER_ROOM,
                "currency": "USD",
                "hl": "en",
            }
        )
        booking_url = reply.get("search_metadata", {}).get(
            "google_hotels_url"
        ) or hotel_search_link(destination, dates)
        priced = (p for p in reply.get("properties", []) if "rate_per_night" in p)
        top_pick = next(priced, None)
        if top_pick is None:
            return None
        return _to_hotel(top_pick, dates, booking_url)

    def _search(self, params: dict[str, str]) -> dict:
        try:
            return search_serpapi(self._api_url, self._api_key, "google_hotels", params)
        except SerpApiError as error:
            raise HotelsError(str(error)) from None


def connect_hotels() -> GoogleHotels | None:
    """The hotel search to use, or None if no API key is set."""
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        logger.warning("SERPAPI_API_KEY isn't set, so scout can't look up hotels")
        return None
    return GoogleHotels(api_key)


def _to_hotel(result: dict, dates: DateWindow, booking_url: str) -> Hotel:
    nights = (dates.end - dates.start).days
    nightly_rate = result["rate_per_night"]["extracted_lowest"]
    # Google omits the stay total on some listings, so fall back to the nights.
    stay_total = (
        result.get("total_rate", {}).get("extracted_lowest") or nightly_rate * nights
    )
    images = result.get("images", [])
    return Hotel(
        name=result["name"],
        guest_rating=result.get("overall_rating"),
        review_count=result.get("reviews"),
        nights=nights,
        nightly_rate_usd=nightly_rate,
        stay_total_usd=stay_total,
        photo_url=images[0].get("original_image") if images else None,
        booking_url=booking_url,
    )
