"""GoogleHotels against the stand-in SerpApi server from conftest."""

from datetime import date

import pytest

from scout.hotels import GoogleHotels, Hotel, HotelsError, NearbyPlace
from scout.places import Coordinates
from scout.trip import DateWindow

SPRING_BREAK = DateWindow(date(2027, 3, 14), date(2027, 3, 19))
SEARCH_URL = "https://www.google.com/travel/hotels/San%20Juan?q=abc"
HOTEL_PHOTO = "https://lh5.googleusercontent.com/hotel-front"

SOLD_OUT = {"name": "Hotel Sin Cuartos", "overall_rating": 4.8}
CONDADO_VISTA = {
    "type": "hotel",
    "name": "Condado Vista",
    "hotel_class": "4-star hotel",
    "gps_coordinates": {"latitude": 18.4583, "longitude": -66.0745},
    "check_in_time": "3:00\u202fPM",
    "check_out_time": "11:00\u202fAM",
    "overall_rating": 4.5,
    "reviews": 1203,
    "location_rating": 4.8,
    "deal": "21% less than usual",
    "deal_description": "Great Deal",
    "rate_per_night": {"lowest": "$189", "extracted_lowest": 189},
    "total_rate": {"lowest": "$945", "extracted_lowest": 945},
    "amenities": ["Free Wi-Fi", "Outdoor pool"],
    "nearby_places": [
        {
            "name": "Condado Beach",
            "transportations": [{"type": "Walking", "duration": "2 min"}],
        },
        {
            "name": "Luis Muñoz Marín International Airport",
            "transportations": [
                {"type": "Taxi", "duration": "15 min"},
                {"type": "Public transport", "duration": "40 min"},
            ],
        },
    ],
    "images": [{"thumbnail": "https://x/thumb", "original_image": HOTEL_PHOTO}],
}
RENTAL_LISTING = "https://evolve.com/vacation-rentals/483846"
BEACH_RENTAL = {
    "type": "vacation rental",
    "name": "Beachfront Condo",
    "link": RENTAL_LISTING,
    "essential_info": ["Entire apartment", "Sleeps 6", "1 bedroom"],
    "rate_per_night": {"lowest": "$230", "extracted_lowest": 230},
}
BUDGET_INN = {
    "type": "hotel",
    "name": "Budget Inn",
    "hotel_class": "2-star hotel",
    "rate_per_night": {"lowest": "$95", "extracted_lowest": 95},
}
SEARCH_RESULTS = {
    "search_metadata": {"status": "Success", "google_hotels_url": SEARCH_URL},
    "properties": [SOLD_OUT, CONDADO_VISTA, BEACH_RENTAL, BUDGET_INN],
}


@pytest.fixture
def hotels(serpapi):
    serpapi.reply = (200, SEARCH_RESULTS)
    return GoogleHotels("test-key", api_url=serpapi.url)


def test_the_best_hotel_is_googles_top_pick_that_has_a_rate(hotels):
    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel == Hotel(
        name="Condado Vista",
        kind="4-star hotel",
        room_details=[],
        guest_rating=4.5,
        review_count=1203,
        location_rating=4.8,
        nights=5,
        nightly_rate_usd=189,
        stay_total_usd=945,
        typical_nightly_rate_usd=189,
        deal="21% less than usual",
        amenities=["Free Wi-Fi", "Outdoor pool"],
        nearby_places=[
            NearbyPlace("Condado Beach", "2 min walk"),
            NearbyPlace("Luis Muñoz Marín International Airport", "15 min by taxi"),
        ],
        check_in_time="3:00 PM",
        check_out_time="11:00 AM",
        coordinates=Coordinates(18.4583, -66.0745),
        photo_url=HOTEL_PHOTO,
        booking_url=(
            "https://www.google.com/travel/hotels?q=Condado%20Vista%20San%20Juan"
            "%2C%20Puerto%20Rico%20March%2014%202027%20to%20March%2019%202027"
        ),
    )


def test_the_typical_rate_is_the_middle_of_every_priced_place(hotels, serpapi):
    pricier = {**BUDGET_INN, "rate_per_night": {"extracted_lowest": 300}}
    serpapi.reply = (
        200,
        {"properties": [CONDADO_VISTA, BEACH_RENTAL, BUDGET_INN, pricier]},
    )

    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel.typical_nightly_rate_usd == 210


def test_too_few_priced_places_give_no_typical_rate(hotels, serpapi):
    serpapi.reply = (200, {"properties": [CONDADO_VISTA, BUDGET_INN]})

    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel.typical_nightly_rate_usd is None


def test_a_rental_says_what_kind_of_place_it_is(hotels, serpapi):
    serpapi.reply = (200, {"properties": [BEACH_RENTAL]})

    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel.kind == "Vacation rental"
    assert hotel.room_details == ["Entire apartment", "Sleeps 6", "1 bedroom"]


def test_a_rental_books_on_its_own_listing(hotels, serpapi):
    """Google Hotels can't find a rental by name, so its search link would
    open a list of other places."""
    serpapi.reply = (200, {"properties": [BEACH_RENTAL]})

    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel.booking_url == RENTAL_LISTING


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


def test_the_booking_link_opens_this_hotel_not_googles_general_search(hotels):
    """Google's own link is "hotels in <city>" with no dates, so a tap on Book
    landed on a list instead of the hotel."""
    hotel = hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)

    assert hotel.booking_url != SEARCH_URL
    assert "Condado%20Vista" in hotel.booking_url
    assert "March%2014%202027%20to%20March%2019%202027" in hotel.booking_url


def test_no_hotel_when_none_has_a_rate(hotels, serpapi):
    serpapi.reply = (200, {"properties": [SOLD_OUT]})

    assert hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK) is None


def test_a_refused_search_says_why(hotels, serpapi):
    serpapi.reply = (401, {"error": "Invalid API key."})

    with pytest.raises(HotelsError, match="search failed with 401: Invalid API key"):
        hotels.find_best_hotel("San Juan, Puerto Rico", SPRING_BREAK)
