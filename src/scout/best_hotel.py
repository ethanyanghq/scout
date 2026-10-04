"""The hotel scout recommends for the trip, and how it reads in the chat.

Google Hotels picks the hotel; scout supplies the destination and dates.
"""

from scout.group_summary import format_window
from scout.hotels import GoogleHotels, Hotel
from scout.trip import Trip


class NoHotelAvailable(Exception):
    """Google Hotels has no hotel with a rate for the destination and dates."""


def find_best_hotel(hotels: GoogleHotels, trip: Trip) -> Hotel:
    """Expects a trip whose destination and dates are locked in. Raises
    HotelsError if SerpApi can't be reached, and NoHotelAvailable if Google
    lists nothing."""
    hotel = hotels.find_best_hotel(trip.destination, trip.dates)
    if hotel is None:
        raise NoHotelAvailable(
            f"no hotels with a rate in {trip.destination} "
            f"for {format_window(trip.dates)}"
        )
    return hotel


def format_best_hotel(trip: Trip, hotel: Hotel) -> str:
    """The hotel as text, for the chat log and phones that can't open the card."""
    rating = describe_rating(hotel)
    lines = [
        f"recommended hotel in {trip.destination}, {format_window(trip.dates)}",
        f"{hotel.name} · {rating}" if rating else hotel.name,
        f"   {describe_rates(hotel)}",
        f"   {hotel.booking_url}",
        "google hotels' top pick for your dates, so it may not be the cheapest. "
        "rates can change until you book. "
        "whoever books, tell me what you paid and i'll split it.",
    ]
    return "\n".join(lines)


def describe_rating(hotel: Hotel) -> str | None:
    """ "4.5 ★ · 1,203 reviews", or None for a hotel nobody has rated."""
    if hotel.guest_rating is None:
        return None
    if hotel.review_count is None:
        return f"{hotel.guest_rating} ★"
    return f"{hotel.guest_rating} ★ · {hotel.review_count:,} reviews"


def describe_rates(hotel: Hotel) -> str:
    """ "$189 a night · $945 for 5 nights, for one room of two"."""
    return (
        f"${hotel.nightly_rate_usd:,} a night · "
        f"${hotel.stay_total_usd:,} for {hotel.nights} nights, for one room of two"
    )
