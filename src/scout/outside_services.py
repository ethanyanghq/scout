"""The outside APIs scout acts through, beyond Claude."""

from dataclasses import dataclass

from scout.nessie import NessieBank, connect_bank
from scout.places import GooglePlaces, connect_places


@dataclass(frozen=True)
class OutsideServices:
    # None means that service isn't set up, and scout works without it:
    # payments are simulated, and scout says it can't recommend places.
    bank: NessieBank | None = None
    places: GooglePlaces | None = None


# For tests and anywhere else that runs without outside APIs.
NO_OUTSIDE_SERVICES = OutsideServices()


def connect_outside_services() -> OutsideServices:
    """Connects every service whose API key is set in the environment."""
    return OutsideServices(bank=connect_bank(), places=connect_places())
