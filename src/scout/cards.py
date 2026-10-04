"""The interactive cards scout sends into the chat.

A card is a HermesShare layout: declarative JSON that an Apple-signed iMessage
extension draws as native SwiftUI. iMessage runs no HTML or JavaScript, so the
payload is parameters for a fixed vocabulary of views, never code.

Only sending is built. What someone taps on a card can't reach scout: Linq's
ingest flattens an inbound `imessage_app` part to a single replacement
character before any webhook sees it, so the group still votes in text.
"""

from dataclasses import dataclass

from scout.best_flights import (
    HomeCityFlight,
    describe_stops,
    format_clock,
    format_duration,
)
from scout.group_summary import format_window
from scout.trip import Trip

# Destination articles are white text on near-black, with one muted sea-glass
# accent and soft gray for the small print, so nothing fights the photos.
SEA_GLASS_HEX = "#8FC1B5"
SOFT_GRAY_HEX = "#A1A1AA"
# Tints the atmosphere background's glow; this dark it reads as plain black.
NIGHT_GLOW_HEX = "#1B2422"
# A departure-board blue, matching HermesShare's own flight cards.
FLIGHT_ACCENT_HEX = "#0A84FF"
NONSTOP_HEX = "#30D158"
CONNECTING_HEX = "#FF9F0A"


@dataclass(frozen=True)
class Activity:
    """Something to do at a destination, shown with its photo in the article."""

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
    """One destination, as the group sees it in its card."""

    # As the agent named it, e.g. "Cancún, Mexico".
    destination: str
    # Where it is, e.g. "Quintana Roo, Mexico".
    region: str
    # A sentence on why it fits the group.
    detail: str
    hotel: str
    costs: list[CostEstimate]
    activities: list[Activity]
    hero_photo_url: str | None = None

    @property
    def estimated_cost_per_person_usd(self) -> int:
        return sum(cost.estimated_usd for cost in self.costs)

    @property
    def place_name(self) -> str:
        """The name a card leads with: "Cancún" rather than "Cancún, Mexico"."""
        return self.destination.split(",")[0].strip()


def destination_article(brochure: Brochure, nights: int) -> dict:
    """One destination as a short travel article: a hero photo, why it fits,
    where to stay, things to do with photos, and what it all costs."""
    return {
        "version": 1,
        "title": brochure.place_name,
        "subtitle": brochure.region,
        "accentColorHex": SEA_GLASS_HEX,
        # `atmosphere` draws a near-black card and switches its text to white.
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 18,
            "alignment": "leading",
            "children": [
                *_photo_strip(brochure),
                {
                    "type": "statusBadge",
                    "label": f"~${brochure.estimated_cost_per_person_usd:,} "
                    "per person, all in",
                    "colorHex": SEA_GLASS_HEX,
                },
                _text(brochure.detail, role="body"),
                _section_heading("Where you'll stay"),
                _text(brochure.hotel, role="headline"),
                _section_heading("Things to do"),
                *[_activity(activity) for activity in brochure.activities],
                _section_heading("What it costs"),
                _cost_breakdown(brochure),
                _text(
                    f"Estimates for {nights} nights. Nothing is booked.",
                    role="footnote",
                    color_hex=SOFT_GRAY_HEX,
                ),
            ],
        },
    }


def _photo_strip(brochure: Brochure) -> list[dict]:
    """The hero photo, then each activity's, to swipe through.

    A `gallery` sizes and clips every photo itself. HermesShare's `image`
    node doesn't, so one large photo stretches the whole card off screen.
    """
    activity_photos = [a.photo_url for a in brochure.activities if a.photo_url]
    photos = (
        [brochure.hero_photo_url, *activity_photos]
        if brochure.hero_photo_url
        else activity_photos
    )
    if not photos:
        return []
    return [{"type": "gallery", "urls": photos, "heightPt": 230, "cornerRadius": 18}]


def _activity(activity: Activity) -> dict:
    return {
        "type": "vstack",
        "spacing": 2,
        "alignment": "leading",
        "children": [
            _text(activity.name, role="headline"),
            _text(
                f"~${activity.estimated_cost_usd:,} per person",
                role="footnote",
                color_hex=SOFT_GRAY_HEX,
            ),
        ],
    }


def _cost_breakdown(brochure: Brochure) -> dict:
    total = f"~${brochure.estimated_cost_per_person_usd:,}"
    return {
        "type": "card",
        "child": {
            "type": "vstack",
            "spacing": 4,
            "children": [
                *[
                    _row(cost.label, f"~${cost.estimated_usd:,}", cost.sf_symbol)
                    for cost in brochure.costs
                ],
                {"type": "divider"},
                _row("Per person, all in", total, "sun.max.fill"),
            ],
        },
    }


def _section_heading(title: str) -> dict:
    heading = _text(title.upper(), role="subheadline", color_hex=SEA_GLASS_HEX)
    heading["style"]["weight"] = "bold"
    return heading


def _text(words: str, role: str, color_hex: str | None = None) -> dict:
    style = {"role": role}
    if color_hex:
        style["colorHex"] = color_hex
    return {"type": "text", "text": words, "style": style}


def best_flights(trip: Trip, home_city_flights: list[HomeCityFlight]) -> dict:
    """A departure board for each home city's flight, with its fare and a
    button that opens it on Google Flights.

    Expects a trip whose destination and dates are locked in.
    """
    return {
        "version": 1,
        "title": f"Flights to {trip.destination}",
        "subtitle": f"{format_window(trip.dates)} · round trip",
        "accentColorHex": FLIGHT_ACCENT_HEX,
        # The board is drawn dark, so the card around it goes dark too.
        "background": {"kind": "atmosphere"},
        "root": {
            "type": "vstack",
            "spacing": 16,
            "alignment": "leading",
            "children": [
                node
                for home_city_flight in home_city_flights
                for node in _flight_nodes(trip, home_city_flight)
            ],
        },
        "actions": [_booking_action(f) for f in home_city_flights],
    }


def flights_thumbnail_url(home_city_flights: list[HomeCityFlight]) -> str | None:
    """The photo iMessage shows on the unopened bubble: the destination city."""
    return next(
        (
            f.flight.destination_photo_url
            for f in home_city_flights
            if f.flight.destination_photo_url
        ),
        None,
    )


def _flight_nodes(trip: Trip, home_city_flight: HomeCityFlight) -> list[dict]:
    flight = home_city_flight.flight
    board = {
        "type": "flightBoard",
        "board": {
            "origin": flight.departure_airport,
            "destination": flight.arrival_airport,
            "originCity": home_city_flight.home_city,
            "destinationCity": trip.destination,
            "flightCode": flight.flight_numbers[0],
            "departTime": format_clock(flight.departs_at),
            "arriveTime": format_clock(flight.arrives_at),
            "status": describe_stops(flight),
            "statusColorHex": (
                CONNECTING_HEX if flight.layover_airports else NONSTOP_HEX
            ),
        },
    }
    fare = {
        "type": "card",
        "child": {
            "type": "vstack",
            "spacing": 4,
            "children": [
                _row("Fare", f"${flight.price_usd:,} per person", "dollarsign.circle"),
                _row("Airline", " / ".join(flight.airlines), "airplane"),
                _row("Flying time", format_duration(flight.duration_minutes), "clock"),
                _row("For", ", ".join(home_city_flight.travelers), "person.2.fill"),
            ],
        },
    }
    return [board, fare]


def _row(key: str, value: str, sf_symbol: str) -> dict:
    return {
        "type": "keyValueRow",
        "key": key,
        "value": value,
        "iconSystemName": sf_symbol,
    }


def _booking_action(home_city_flight: HomeCityFlight) -> dict:
    # An https link opens Google Flights rather than posting a reply in the chat.
    return {
        "id": f"book-{_slug(home_city_flight.home_city)}",
        "label": f"Book from {home_city_flight.home_city}",
        "systemImage": "airplane.departure",
        "deepLinkURL": home_city_flight.flight.booking_url,
    }


def _slug(text: str) -> str:
    kept = [c.lower() if c.isalnum() else "-" for c in text]
    return "".join(kept).strip("-").replace("--", "-")
