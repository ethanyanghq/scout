"""GoogleHotels against the stand-in SerpApi server from conftest."""

from datetime import date

import pytest

from scout.hotels import GoogleHotels, Hotel, HotelsError
from scout.trip import DateWindow

SPRING_BREAK = DateWindow(date(2027, 3, 14), date(2027, 3, 19))
SEARCH_URL = "https://www.google.com/travel/hotels/San%20Juan?q=abc"
HOTEL_PHOTO = "https://lh5.googleusercontent.com/hotel-front"

SOLD_OUT = {"name": "Hotel Sin Cuartos", "overall_rating": 4.8}
CONDADO_VISTA = {
    "name": "Condado Vista",
    "overall_rating": 4.5,
    "reviews": 1203,
    "rate_per_night": {"lowest": "$189", "extracted_lowest": 189},
    "total_rate": {"lowest": "$945", "extracted_lowest": 945},
    "images": [{"thumbnail": "https://x/thumb", "original_image": HOTEL_PHOTO}],
}
SEARCH_RESULTS = {
    "search_metadata": {"status": "Success", "google_hotels_url": SEARCH_URL},
    "properties": [SOLD_OUT, CONDADO_VISTA],
}


@pytest.fixture
def hotels(serpapi):
    serpapi.reply = (200, SEARCH_RESULTS)
    return GoogleHotels("test-key", api_url=serpapi.url)


def test_the_best_hotel_is_googles_top_pick_that_has_a_rate(hotels):
    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel == Hotel(
        name="Condado Vista",
        guest_rating=4.5,
        review_count=1203,
        nights=5,
        nightly_rate_usd=189,
        stay_total_usd=945,
        photo_url=HOTEL_PHOTO,
        booking_url=SEARCH_URL,
    )


def test_the_search_is_for_the_destination_and_trip_dates(hotels, serpapi):
    hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    [query] = serpapi.queries
    assert query["engine"] == "google_hotels"
    assert query["q"] == "hotels in San Juan, Puerto Rico"
    assert (query["check_in_date"], query["check_out_date"]) == (
        "2027-03-14",
        "2027-03-19",
    )


def test_a_listing_without_a_stay_total_is_priced_by_the_night(hotels, serpapi):
    no_total = {k: v for k, v in CONDADO_VISTA.items() if k != "total_rate"}
    serpapi.reply = (200, {"properties": [no_total]})

    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel.stay_total_usd == 945


def test_without_google_hotels_link_the_booking_link_is_a_hotel_search(hotels, serpapi):
    serpapi.reply = (200, {"properties": [CONDADO_VISTA]})

    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel.booking_url.startswith("https://www.google.com/travel/hotels?q=Hotels")


def test_no_hotel_when_none_has_a_rate(hotels, serpapi):
    serpapi.reply = (200, {"properties": [SOLD_OUT]})

    assert hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK) is None


def test_a_refused_search_says_why(hotels, serpapi):
    serpapi.reply = (401, {"error": "Invalid API key."})

    with pytest.raises(HotelsError, match="search failed with 401: Invalid API key"):
        hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)
