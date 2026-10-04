"""Finds real hotels on Google Hotels, through SerpApi.

scout never invents a rate: every hotel it posts comes from here. Google Hotels
has no public API, so SerpApi runs the search and returns the results as JSON.
"""

import logging
import os
from dataclasses import dataclass, replace
from statistics import median

from scout.booking_links import hotel_link
from scout.places import Coordinates
from scout.serpapi import SERPAPI_URL, SerpApiError, search_serpapi
from scout.trip import DateWindow

logger = logging.getLogger(__name__)

# Two guests, so the rate is for one double room, not for the whole group.
GUESTS_PER_ROOM = "2"
# Google's `type` for a place that isn't a hotel.
VACATION_RENTAL = "vacation rental"
# A typical rate needs a few other places to compare against.
MIN_RATES_FOR_TYPICAL = 3
# How Google says someone gets to a nearby place, as scout writes it.
TRAVEL_MODES = {"Walking": "walk", "Taxi": "by taxi", "Public transport": "by transit"}


class HotelsError(Exception):
    """SerpApi couldn't be reached or refused a search."""


@dataclass(frozen=True)
class NearbyPlace:
    name: str
    # How long it takes and how, e.g. "5 min walk".
    trip: str


@dataclass(frozen=True)
class Hotel:
    name: str
    # "3-star hotel", or "Vacation rental" for a place with no star class.
    kind: str | None
    # What a rental is, e.g. ["Entire apartment", "Sleeps 6", "1 bedroom"].
    # Empty for a hotel.
    room_details: list[str]
    # Guests' average out of 5, and how many rated. None when nobody has.
    guest_rating: float | None
    review_count: int | None
    # Guests' score out of 5 for the neighborhood alone.
    location_rating: float | None
    nights: int
    # For one room, with the taxes and fees Google knows about.
    nightly_rate_usd: int
    stay_total_usd: int
    # The middle nightly rate of every place Google priced for the same stay,
    # so the group can tell a deal from a splurge. None with too few to say.
    typical_nightly_rate_usd: int | None
    # Google's own deal flag, e.g. "34% less than usual".
    deal: str | None
    amenities: list[str]
    nearby_places: list[NearbyPlace]
    # Local times, e.g. "4:00 PM".
    check_in_time: str | None
    check_out_time: str | None
    coordinates: Coordinates | None
    photo_url: str | None
    # Opens this hotel on Google Hotels for the stay, where the group books.
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
        priced = [p for p in reply.get("properties", []) if "rate_per_night" in p]
        if not priced:
            return None
        top_pick = priced[0]
        hotel = _to_hotel(top_pick, dates, _booking_url(top_pick, destination, dates))
        return replace(hotel, typical_nightly_rate_usd=_typical_nightly_rate(priced))

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
    coordinates = result.get("gps_coordinates")
    return Hotel(
        name=result["name"],
        kind=result.get("hotel_class") or _capitalize(result.get("type")),
        room_details=result.get("essential_info", []),
        guest_rating=result.get("overall_rating"),
        review_count=result.get("reviews"),
        location_rating=result.get("location_rating"),
        nights=nights,
        nightly_rate_usd=nightly_rate,
        stay_total_usd=stay_total,
        typical_nightly_rate_usd=None,
        deal=result.get("deal"),
        amenities=result.get("amenities", []),
        nearby_places=[
            place
            for place in map(_to_nearby_place, result.get("nearby_places", []))
            if place
        ],
        check_in_time=_clean_time(result.get("check_in_time")),
        check_out_time=_clean_time(result.get("check_out_time")),
        coordinates=(
            Coordinates(coordinates["latitude"], coordinates["longitude"])
            if coordinates
            else None
        ),
        photo_url=images[0].get("original_image") if images else None,
        booking_url=booking_url,
    )


def _booking_url(result: dict, destination: str, dates: DateWindow) -> str:
    """Where to book this place. A search by name finds a hotel on Google
    Hotels, but not a vacation rental, so a rental opens its own listing."""
    if result.get("type") == VACATION_RENTAL and result.get("link"):
        return result["link"]
    return hotel_link(result["name"], destination, dates)


def _typical_nightly_rate(priced: list[dict]) -> int | None:
    rates = [p["rate_per_night"]["extracted_lowest"] for p in priced]
    if len(rates) < MIN_RATES_FOR_TYPICAL:
        return None
    return round(median(rates))


def _to_nearby_place(result: dict) -> NearbyPlace | None:
    """The first way there Google lists that scout can name, or None."""
    for transportation in result.get("transportations", []):
        mode = TRAVEL_MODES.get(transportation.get("type"))
        if mode:
            return NearbyPlace(result["name"], f"{transportation['duration']} {mode}")
    return None


def _clean_time(text: str | None) -> str | None:
    # Google separates "4:00" and "PM" with a narrow no-break space.
    return text.replace("\u202f", " ") if text else None


def _capitalize(text: str | None) -> str | None:
    return text[:1].upper() + text[1:] if text else None
