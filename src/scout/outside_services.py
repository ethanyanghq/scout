"""The outside APIs scout acts through, beyond Claude."""

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


# For tests and anywhere else that runs without outside APIs.
NO_OUTSIDE_SERVICES = OutsideServices()


def connect_outside_services() -> OutsideServices:
    """Connects every service whose API key is set in the environment."""
    return OutsideServices(
        places=connect_places(),
        flights=connect_flights(),
        hotels=connect_hotels(),
    )
