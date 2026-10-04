"""The interactive cards scout sends into the chat.

A card is a HermesShare layout: declarative JSON that an Apple-signed iMessage
extension draws as native SwiftUI. iMessage runs no HTML or JavaScript, so the
payload is parameters for a fixed vocabulary of views, never code.

Only sending is built. What someone taps on a card can't reach scout: Linq's
ingest flattens an inbound `imessage_app` part to a single replacement
character before any webhook sees it, so the group still votes in text.
"""

from dataclasses import dataclass

# Tints the card's icons and headers. A warm sand, for a resort brochure.
BROCHURE_ACCENT_HEX = "#E08A3C"
# Shown when a hero photo won't load.
BROCHURE_FALLBACK_SYMBOL = "beach.umbrella.fill"


@dataclass(frozen=True)
class Activity:
    """Something to do at a destination, shown in the brochure's photo strip."""

    name: str
    estimated_cost_usd: int
    photo_url: str | None = None


@dataclass(frozen=True)
class CostEstimate:
    """One part of a destination's per-person estimate, e.g. flights."""

    label: str
    estimated_usd: int
    sf_symbol: str


@dataclass(frozen=True)
class Brochure:
    """One destination, as the group sees it in the card."""

    destination: str
    # Where it is and how it rates, e.g. "Quintana Roo · ★ 4.7".
    subtitle: str
    # A sentence on why it fits the group.
    detail: str
    hotel: str
    costs: list[CostEstimate]
    activities: list[Activity]
    hero_photo_url: str | None = None

    @property
    def estimated_cost_per_person_usd(self) -> int:
        return sum(cost.estimated_usd for cost in self.costs)


def destination_brochures(brochures: list[Brochure]) -> dict:
    """A scrollable card of destinations, each tapping open to its own page.

    `photoCatalog` draws an accordion: a hero photo per destination, and the
    price breakdown and activities once it's opened.
    """
    return {
        "version": 1,
        "title": "Where should we go?",
        "subtitle": f"{len(brochures)} spots that fit · tap one to look around",
        "accentColorHex": BROCHURE_ACCENT_HEX,
        "background": {"kind": "plain"},
        "root": {
            "type": "photoCatalog",
            "catalogItems": [_catalog_item(brochure) for brochure in brochures],
        },
    }


def _catalog_item(brochure: Brochure) -> dict:
    item = {
        "id": _slug(brochure.destination),
        "title": brochure.destination,
        "subtitle": brochure.subtitle,
        "priceText": f"~${brochure.estimated_cost_per_person_usd:,}",
        "priceUnit": "person, all in",
        "detail": f"{brochure.detail} Staying at {brochure.hotel}.",
        # `amenities` is the catalog's icon-tile slot; scout fills it with
        # what the price is made of.
        "amenities": [
            {
                "label": f"{cost.label} ~${cost.estimated_usd:,}",
                "systemImage": cost.sf_symbol,
            }
            for cost in brochure.costs
        ],
        "rooms": [_activity_tile(brochure, a) for a in brochure.activities],
        "fallbackSystemImage": BROCHURE_FALLBACK_SYMBOL,
    }
    # The renderer hides the hero rather than showing a broken image, so only
    # send the key when there's a photo.
    if brochure.hero_photo_url:
        item["heroImageUrl"] = brochure.hero_photo_url
    return item


def _activity_tile(brochure: Brochure, activity: Activity) -> dict:
    """One photo in a destination's activity strip. `rooms` is the catalog's
    gallery slot; scout fills it with things to do rather than hotel rooms."""
    tile = {
        "id": f"{_slug(brochure.destination)}-{_slug(activity.name)}",
        "name": activity.name,
        "price": f"~${activity.estimated_cost_usd:,}",
    }
    if activity.photo_url:
        tile["imageUrl"] = activity.photo_url
    return tile


def brochure_thumbnail_url(brochures: list[Brochure]) -> str | None:
    """The photo iMessage shows on the unopened bubble: the first hero there is."""
    return next((b.hero_photo_url for b in brochures if b.hero_photo_url), None)


def _slug(text: str) -> str:
    kept = [c.lower() if c.isalnum() else "-" for c in text]
    return "".join(kept).strip("-").replace("--", "-")
