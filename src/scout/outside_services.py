"""The outside APIs scout acts through, beyond Claude."""

import os
from dataclasses import dataclass

from scout.flights import GoogleFlights, connect_flights
from scout.hotels import GoogleHotels, connect_hotels
from scout.places import GooglePlaces, connect_places


@dataclass(frozen=True)
class OutsideServices:
    # None means that service isn't set up, and scout works without it: it
    # says it can't recommend places, or sends search links instead of flights
    # and hotels.
    places: GooglePlaces | None = None
    flights: GoogleFlights | None = None
    hotels: GoogleHotels | None = None
    # Where the internet reaches scout's web server, like "https://scout.example.com".
    # Calendar feeds are served from it. None means no calendar link is sent.
    public_url: str | None = None


# For tests and anywhere else that runs without outside APIs.
NO_OUTSIDE_SERVICES = OutsideServices()


def connect_outside_services() -> OutsideServices:
    """Connects every service whose API key is set in the environment."""
    return OutsideServices(
        places=connect_places(),
        flights=connect_flights(),
        hotels=connect_hotels(),
        public_url=os.environ.get("SCOUT_PUBLIC_URL") or None,
    )
