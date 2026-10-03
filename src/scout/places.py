"""Finds real places with Google Places API (New) Text Search (OT-1, OT-2).

scout never invents a place: every suggestion it makes comes from here.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TIMEOUT_SECONDS = 10
# Google bills by the fields requested, so ask only for what scout shows.
FIELD_MASK = ",".join(
    f"places.{field}"
    for field in (
        "id",
        "displayName",
        "location",
        "priceLevel",
        "editorialSummary",
        "primaryTypeDisplayName",
    )
)
# Results can still come from farther out; this only says where to look first.
NEARBY_RADIUS_METERS = 2_000
PRICE_LABELS = {
    "PRICE_LEVEL_FREE": "free",
    "PRICE_LEVEL_INEXPENSIVE": "$",
    "PRICE_LEVEL_MODERATE": "$$",
    "PRICE_LEVEL_EXPENSIVE": "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
}


class PlacesError(Exception):
    """Google Places couldn't be reached or refused a search."""


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    location: Coordinates
    # "$" to "$$$$", or "free". None when Google doesn't know.
    price: str | None
    # Google's one-line summary, or else the kind of place ("Mexican restaurant").
    summary: str | None


class GooglePlaces:
    def __init__(self, api_key: str, search_url: str = PLACES_SEARCH_URL):
        self._api_key = api_key
        self._search_url = search_url

    def search(
        self, text_query: str, limit: int, near: Coordinates | None = None
    ) -> list[Place]:
        """The best matches for a free-text search, looking near `near` first."""
        body: dict = {"textQuery": text_query, "pageSize": limit}
        if near is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": near.latitude, "longitude": near.longitude},
                    "radius": NEARBY_RADIUS_METERS,
                }
            }
        results = self._post(body).get("places", [])
        return [_to_place(result) for result in results[:limit]]

    def _post(self, body: dict) -> dict:
        request = urllib.request.Request(
            self._search_url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": FIELD_MASK,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
                return json.load(reply)
        except urllib.error.HTTPError as error:
            reason = error.read().decode(errors="replace")[:200]
            raise PlacesError(f"search failed with {error.code}: {reason}") from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise PlacesError(f"search didn't connect: {error}") from None
        except json.JSONDecodeError as error:
            raise PlacesError(f"search sent an unexpected reply: {error}") from None


def connect_places() -> GooglePlaces | None:
    """The places search to use, or None if no API key is set."""
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        logger.warning(
            "GOOGLE_PLACES_API_KEY isn't set, so scout can't recommend places"
        )
        return None
    return GooglePlaces(api_key)


def _to_place(result: dict) -> Place:
    summary = result.get("editorialSummary") or result.get("primaryTypeDisplayName")
    return Place(
        place_id=result["id"],
        name=result["displayName"]["text"],
        location=Coordinates(
            result["location"]["latitude"], result["location"]["longitude"]
        ),
        price=PRICE_LABELS.get(result.get("priceLevel", "")),
        summary=summary["text"] if summary else None,
    )
