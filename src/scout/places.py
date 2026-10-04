"""Finds real places with Google Places API (New) Text Search (OT-1, OT-2).

scout never invents a place: every suggestion it makes comes from here.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PLACES_API_URL = "https://places.googleapis.com/v1"
TIMEOUT_SECONDS = 10


def _field_mask(*fields: str) -> str:
    return ",".join(f"places.{field}" for field in fields)


# Google bills by the fields requested, so ask only for what scout shows.
FIELD_MASK = _field_mask(
    "id",
    "displayName",
    "location",
    "priceLevel",
    "editorialSummary",
    "primaryTypeDisplayName",
)
# Photos and ratings are billed at a higher tier, so only brochures ask for them.
PHOTO_FIELD_MASK = _field_mask("displayName", "rating", "photos")
# Wide enough for a full-width photo on a phone.
PHOTO_MAX_WIDTH_PX = 1200
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


@dataclass(frozen=True)
class PhotographedPlace:
    """A place as a brochure shows it."""

    name: str
    # Google's star rating out of 5, or None when it has none.
    rating: float | None
    # Public HTTPS links with no API key in them, so they can go to phones.
    photo_urls: list[str]


class GooglePlaces:
    def __init__(self, api_key: str, api_url: str = PLACES_API_URL):
        self._api_key = api_key
        self._api_url = api_url

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
        results = self._search(body, FIELD_MASK).get("places", [])
        return [_to_place(result) for result in results[:limit]]

    def find_photographed(
        self, text_query: str, photo_count: int
    ) -> PhotographedPlace | None:
        """The best match for a search, with up to `photo_count` of its photos."""
        body = {"textQuery": text_query, "pageSize": 1}
        results = self._search(body, PHOTO_FIELD_MASK).get("places", [])
        if not results:
            return None
        best = results[0]
        photos = best.get("photos", [])[:photo_count]
        return PhotographedPlace(
            name=best["displayName"]["text"],
            rating=best.get("rating"),
            photo_urls=[self._public_photo_url(photo["name"]) for photo in photos],
        )

    def _public_photo_url(self, photo_name: str) -> str:
        """Google's own link to a photo. Asking for the link, rather than
        following the media URL's redirect, keeps the API key off phones."""
        query = urllib.parse.urlencode(
            {"maxWidthPx": PHOTO_MAX_WIDTH_PX, "skipHttpRedirect": "true"}
        )
        request = urllib.request.Request(
            f"{self._api_url}/{photo_name}/media?{query}",
            headers={"X-Goog-Api-Key": self._api_key},
        )
        return self._send(request)["photoUri"]

    def _search(self, body: dict, field_mask: str) -> dict:
        request = urllib.request.Request(
            f"{self._api_url}/places:searchText",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": field_mask,
            },
            method="POST",
        )
        return self._send(request)

    def _send(self, request: urllib.request.Request) -> dict:
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
