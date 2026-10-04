"""Turns the agent's destination picks into brochures with real places and photos.

The agent picks the destinations, the activities and the cost estimates. Google
Places supplies the hotel, its rating and every photo, because scout never
invents a place.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from scout.cards import Activity, Brochure, CostEstimate
from scout.places import GooglePlaces, PhotographedPlace


class NoHotelFound(Exception):
    """Google Places has no hotel for a destination, so it can't be pitched."""


@dataclass(frozen=True)
class ActivityPitch:
    name: str
    estimated_cost_usd: int


@dataclass(frozen=True)
class DestinationPitch:
    """One destination as the agent pitches it, before Places fills in the rest."""

    name: str
    # Where it is, e.g. "Quintana Roo, Mexico".
    region: str
    description: str
    flights_usd: int
    hotel_usd: int
    food_and_activities_usd: int
    activities: list[ActivityPitch]


def build_brochures(
    places: GooglePlaces, pitches: list[DestinationPitch]
) -> list[Brochure]:
    """Looks up each destination's photos and hotel, all destinations at once.

    Raises PlacesError if Google can't be reached, and NoHotelFound if a
    destination has no hotel.
    """
    with ThreadPoolExecutor(max_workers=len(pitches)) as pool:
        return list(pool.map(lambda pitch: _build_brochure(places, pitch), pitches))


def format_brochure(brochure: Brochure, nights: int) -> str:
    """A brochure as text, for phones that can't open its card."""
    costs = " · ".join(f"{c.label} ~${c.estimated_usd:,}" for c in brochure.costs)
    activities = ", ".join(
        f"{a.name} (~${a.estimated_cost_usd:,})" for a in brochure.activities
    )
    return "\n".join(
        [
            f"{brochure.destination} · ~${brochure.estimated_cost_per_person_usd:,}",
            costs,
            brochure.detail,
            f"Stay: {brochure.hotel}",
            f"Do: {activities}",
            f"Estimates per person for {nights} nights.",
        ]
    )


def _build_brochure(places: GooglePlaces, pitch: DestinationPitch) -> Brochure:
    destination = places.find_photographed(pitch.name, photo_count=1)
    hotel = places.find_photographed(f"top rated hotel in {pitch.name}", 0)
    if hotel is None:
        raise NoHotelFound(f"no hotel found in {pitch.name}")
    return Brochure(
        destination=pitch.name,
        region=pitch.region,
        detail=pitch.description,
        hotel=_hotel_label(hotel),
        costs=[
            CostEstimate("Flights", pitch.flights_usd, "airplane"),
            CostEstimate("Hotel", pitch.hotel_usd, "bed.double.fill"),
            CostEstimate("Food & fun", pitch.food_and_activities_usd, "fork.knife"),
        ],
        activities=[_find_activity(places, pitch, a) for a in pitch.activities],
        hero_photo_url=_first_photo(destination),
    )


def _find_activity(
    places: GooglePlaces, pitch: DestinationPitch, activity: ActivityPitch
) -> Activity:
    spot = places.find_photographed(f"{activity.name} in {pitch.name}", 1)
    return Activity(activity.name, activity.estimated_cost_usd, _first_photo(spot))


def _first_photo(place: PhotographedPlace | None) -> str | None:
    if place is None or not place.photo_urls:
        return None
    return place.photo_urls[0]


def _hotel_label(hotel: PhotographedPlace) -> str:
    if hotel.rating is None:
        return hotel.name
    return f"{hotel.name} (★ {hotel.rating})"
