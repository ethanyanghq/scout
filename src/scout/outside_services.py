"""The outside APIs scout acts through, beyond Claude."""

from dataclasses import dataclass

from scout.places import GooglePlaces, connect_places


@dataclass(frozen=True)
class OutsideServices:
    # None means that service isn't set up, and scout works without it: it
    # says it can't recommend places.
    places: GooglePlaces | None = None


# For tests and anywhere else that runs without outside APIs.
NO_OUTSIDE_SERVICES = OutsideServices()


def connect_outside_services() -> OutsideServices:
    """Connects every service whose API key is set in the environment."""
    return OutsideServices(places=connect_places())
