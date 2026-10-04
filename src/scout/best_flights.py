"""The best flight from each of the group's home cities, and how it reads in the chat.

The agent names each home city's airport, since a member's "nyc" or "boston"
isn't something Google Flights can search. Google Flights picks the flight.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from scout.flights import Flight, GoogleFlights, OneWay
from scout.group_summary import format_window
from scout.trip import Trip

MINUTES_PER_HOUR = 60


class NoFlightFound(Exception):
    """Google Flights has nothing between a home city's airport and the destination."""


@dataclass(frozen=True)
class HomeAirport:
    home_city: str
    # The IATA code to fly from, e.g. "BOS", or a city code such as "NYC".
    airport_code: str


@dataclass(frozen=True)
class HomeCityFlight:
    home_city: str
    # Who flies from there, as scout names them in the chat.
    travelers: list[str]
    flight: Flight


def find_best_flights(
    flights: GoogleFlights,
    trip: Trip,
    home_airports: list[HomeAirport],
    arrival_airport: str,
) -> list[HomeCityFlight]:
    """Searches every home city at once, since each search takes seconds.

    Expects a trip whose dates are locked in. Raises FlightsError if SerpApi
    can't be reached, and NoFlightFound if a home city has no flights.
    """
    with ThreadPoolExecutor(max_workers=len(home_airports)) as pool:
        return list(
            pool.map(
                lambda home: _find_home_city_flight(
                    flights, trip, home, arrival_airport
                ),
                home_airports,
            )
        )


def format_best_flights(trip: Trip, home_city_flights: list[HomeCityFlight]) -> str:
    """The flights as text, for the chat log and phones that can't open the card."""
    lines = [f"recommended flights to {trip.destination}, {format_window(trip.dates)}"]
    for home_city_flight in home_city_flights:
        lines.extend(_format_home_city_flight(home_city_flight))
    lines.append(
        "google flights' top pick from each city, so it may not be the shortest "
        "or the cheapest. live fares can change until you book. "
        "whoever books, tell me what you paid and i'll split it."
    )
    return "\n".join(lines)


def describe_stops(one_way: OneWay) -> str:
    """ "Nonstop", "1 stop · MIA" or "2 stops · MIA, ATL"."""
    airports = [layover.airport for layover in one_way.layovers]
    if not airports:
        return "Nonstop"
    plural = "" if len(airports) == 1 else "s"
    return f"{len(airports)} stop{plural} · {', '.join(airports)}"


def format_duration(minutes: int) -> str:
    """ "4h 5m", the way Google Flights writes it."""
    hours, minutes = divmod(minutes, MINUTES_PER_HOUR)
    return f"{hours}h {minutes}m"


def format_clock(moment: datetime) -> str:
    """ "6:15 AM"."""
    return f"{moment:%-I:%M %p}"


def format_day(moment: datetime) -> str:
    """ "Sun, Mar 14"."""
    return f"{moment:%a, %b %-d}"


def format_landing(one_way: OneWay) -> str:
    """When it lands: "2:20 PM", or "6:05 AM +1" when that's the next day."""
    days_later = (one_way.arrives_at.date() - one_way.departs_at.date()).days
    clock = format_clock(one_way.arrives_at)
    return f"{clock} +{days_later}" if days_later else clock


def _find_home_city_flight(
    flights: GoogleFlights, trip: Trip, home: HomeAirport, arrival_airport: str
) -> HomeCityFlight:
    flight = flights.find_best_flight(home.airport_code, arrival_airport, trip.dates)
    if flight is None:
        raise NoFlightFound(
            f"no flights from {home.airport_code} to {arrival_airport} "
            f"for {format_window(trip.dates)}"
        )
    travelers = [
        member.label
        for member in trip.members
        if (member.home_city or "").casefold() == home.home_city.casefold()
    ]
    return HomeCityFlight(home.home_city, travelers, flight)


def _format_home_city_flight(home_city_flight: HomeCityFlight) -> list[str]:
    flight = home_city_flight.flight
    return [
        f"{home_city_flight.home_city}: ${flight.price_usd:,} round trip per person, "
        f"for {', '.join(home_city_flight.travelers)}",
        f"   out {_format_one_way(flight.outbound)}",
        f"   back {_format_one_way(flight.homebound)}",
        f"   {flight.booking_url}",
    ]


def _format_one_way(one_way: OneWay) -> str:
    """ "Sun, Mar 14, BOS 6:15 AM → SJU 2:20 PM · JetBlue B6 101 · 1 stop · FLL
    · 8h 5m"."""
    return " · ".join(
        [
            f"{format_day(one_way.departs_at)}, "
            f"{one_way.departure_airport} {format_clock(one_way.departs_at)} → "
            f"{one_way.arrival_airport} {format_landing(one_way)}",
            f"{' / '.join(one_way.airlines)} {one_way.flight_numbers[0]}",
            describe_stops(one_way),
            format_duration(one_way.duration_minutes),
        ]
    )
