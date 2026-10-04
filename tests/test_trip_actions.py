from datetime import date, datetime

import pytest

from scout.best_flights import HomeAirport
from scout.brochures import ActivityPitch, DestinationPitch
from scout.flights import Flight, FlightsError
from scout.outgoing import Card, Say
from scout.outside_services import OutsideServices
from scout.places import Coordinates, PhotographedPlace, Place, PlacesError
from scout.trip import (
    DateWindow,
    DestinationOption,
    ItineraryDay,
    MediaKind,
    MessagePhoto,
    PendingReceipt,
    PreferenceUpdate,
    Settlement,
    SharedMedia,
)
from scout.trip_actions import TripActionError, TripActions

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
PRIYA = "+15550000003"
OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport"),
    DestinationOption("Miami, Florida", 800, "Easy flights"),
]


MAYA_PREFERENCES = PreferenceUpdate(
    display_name="Maya",
    available_from=date(2027, 3, 13),
    available_to=date(2027, 3, 20),
    budget_usd=800,
    home_city="Boston",
)


def said(outgoing):
    """The texts scout sent, failing on anything that isn't a plain text."""
    assert all(isinstance(item, Say) for item in outgoing), outgoing
    return [item.text for item in outgoing]


LEO_PREFERENCES = PreferenceUpdate(
    display_name="Leo",
    available_from=date(2027, 3, 14),
    available_to=date(2027, 3, 19),
    budget_usd=600,
    home_city="New York",
)


@pytest.fixture
def maya_actions(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    return TripActions(store, SPACE, MAYA)


def everyone_votes_for_san_juan(store, leo_preferences=LEO_PREFERENCES):
    """Runs a trip up to the moment the poll closes. Returns the closing actions."""
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, leo_preferences)
    TripActions(store, SPACE, MAYA).start_destination_poll(OPTIONS)
    TripActions(store, SPACE, MAYA).record_sender_vote(1)
    leo_actions = TripActions(store, SPACE, LEO)
    leo_actions.record_sender_vote(1)
    return leo_actions


@pytest.fixture
def locked_in_actions(store):
    everyone_votes_for_san_juan(store)
    return TripActions(store, SPACE, MAYA)


def plan_day(day_of_march, plan):
    return ItineraryDay(date(2027, 3, day_of_march), plan)


def test_saving_preferences_reports_what_is_still_missing(maya_actions):
    status = maya_actions.save_member_preferences(
        "…0001", PreferenceUpdate(display_name="Maya", budget_usd=800)
    )

    assert "Maya is still missing: dates, home city" in status
    assert "waiting on: Maya, …0002" in status


def test_rejects_dates_that_end_before_they_start(maya_actions):
    with pytest.raises(TripActionError):
        maya_actions.save_member_preferences(
            "…0001",
            PreferenceUpdate(
                available_from=date(2027, 3, 20), available_to=date(2027, 3, 13)
            ),
        )


def test_finds_a_member_by_the_name_they_shared(maya_actions, store):
    store.save_preferences(SPACE, LEO, PreferenceUpdate(display_name="Leo"))

    maya_actions.save_member_preferences("leo", PreferenceUpdate(home_city="NYC"))

    assert store.get_trip(SPACE).find_member(LEO).home_city == "NYC"


def test_rejects_preferences_for_someone_not_in_the_chat(maya_actions):
    with pytest.raises(TripActionError, match="members are: …0001, …0002"):
        maya_actions.save_member_preferences("Sam", PreferenceUpdate(budget_usd=500))


def test_records_a_vote_a_friend_reported_for_another_member(maya_actions, store):
    maya_actions.start_destination_poll(OPTIONS)

    maya_actions.record_member_vote("…0002", 1)

    assert store.get_trip(SPACE).open_poll.votes == {LEO: 1}
    assert said(maya_actions.outbox)[-1] == (
        "got it, …0002 → San Juan, Puerto Rico (1 of 2 voted)"
    )


def test_cannot_start_a_second_poll_while_one_is_open(maya_actions):
    maya_actions.start_destination_poll(OPTIONS)

    with pytest.raises(TripActionError):
        maya_actions.start_destination_poll(OPTIONS)


def test_a_poll_needs_exactly_three_options(maya_actions):
    with pytest.raises(TripActionError):
        maya_actions.start_destination_poll(OPTIONS[:2])


def test_closing_a_poll_nobody_voted_in_is_refused(maya_actions):
    maya_actions.start_destination_poll(OPTIONS)

    with pytest.raises(TripActionError):
        maya_actions.close_poll()


def test_closing_the_poll_locks_in_the_dates_everyone_shares(store):
    everyone_votes_for_san_juan(store)

    trip = store.get_trip(SPACE)
    assert trip.destination == "San Juan, Puerto Rico"
    assert trip.dates == DateWindow(date(2027, 3, 14), date(2027, 3, 19))


def test_one_member_choosing_for_the_group_closes_the_poll_without_votes(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, LEO_PREFERENCES)
    store.open_poll(SPACE, OPTIONS)

    TripActions(store, SPACE, MAYA).lock_in_group_choice("san juan")

    trip = store.get_trip(SPACE)
    assert trip.open_poll is None
    assert trip.destination == "San Juan, Puerto Rico"
    assert trip.dates == DateWindow(date(2027, 3, 14), date(2027, 3, 19))


def test_the_group_can_choose_a_destination_without_a_poll(maya_actions, store):
    maya_actions.lock_in_group_choice("Lisbon, Portugal")

    assert store.get_trip(SPACE).destination == "Lisbon, Portugal"


def test_itinerary_is_posted_in_date_order(locked_in_actions):
    locked_in_actions.post_itinerary(
        [plan_day(15, "Beach day in Condado"), plan_day(14, "Land and check in")]
    )

    assert said(locked_in_actions.outbox) == [
        "the plan:\nSun 3/14 · Land and check in\nMon 3/15 · Beach day in Condado"
    ]


def test_itinerary_days_must_fall_within_the_trip(locked_in_actions):
    with pytest.raises(TripActionError, match="outside the trip dates"):
        locked_in_actions.post_itinerary([plan_day(20, "One more beach day")])


def test_booking_links_cover_each_home_city_and_a_stay(locked_in_actions):
    locked_in_actions.send_booking_links()

    lines = said(locked_in_actions.outbox)[0].split("\n")
    assert lines[0] == "flights for Mar 14–19:"
    assert lines[1].startswith("Boston: https://www.google.com/travel/flights?")
    assert lines[2].startswith("New York: https://www.google.com/travel/flights?")
    assert lines[3].startswith("stays for 2: https://www.airbnb.com/s/")


def test_payers_can_remove_their_own_expense(maya_actions, store):
    maya_actions.log_sender_expense(19_600, "Bio bay kayaks")
    [expense] = store.get_trip(SPACE).expenses

    maya_actions.remove_expense(expense.id)

    assert store.get_trip(SPACE).expenses == []
    assert said(maya_actions.outbox)[-1] == "removed: Bio bay kayaks, $196."


def test_nobody_else_can_remove_someones_expense(maya_actions, store):
    expense_id = store.add_expense(SPACE, LEO, 124_000, "Airbnb")

    with pytest.raises(TripActionError, match="only they can remove it"):
        maya_actions.remove_expense(expense_id)
    assert len(store.get_trip(SPACE).expenses) == 1


def maya_owes_leo_50(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, LEO_PREFERENCES)
    store.add_expense(SPACE, LEO, 10_000, "Groceries")


def test_a_payment_is_recorded_and_confirmed_in_the_chat(store):
    maya_owes_leo_50(store)
    maya_actions = TripActions(store, SPACE, MAYA)

    maya_actions.record_sender_payment("Leo")

    assert said(maya_actions.outbox) == [
        "paid ✓ Maya → Leo $50\neveryone's settled up 🎉"
    ]
    assert store.get_trip(SPACE).settlements == [Settlement(MAYA, LEO, 5_000)]


def test_nobody_can_record_paying_someone_they_do_not_owe(store):
    maya_owes_leo_50(store)
    leo_actions = TripActions(store, SPACE, LEO)

    with pytest.raises(TripActionError, match="Leo doesn't owe Maya anything"):
        leo_actions.record_sender_payment("Maya")
    assert store.get_trip(SPACE).settlements == []


def priya_texts_a_receipt(store):
    """Returns Priya's actions after scout asked her to confirm her receipt."""
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO, PRIYA])
    store.save_preferences(SPACE, PRIYA, PreferenceUpdate(display_name="Priya"))
    priya_actions = TripActions(store, SPACE, PRIYA)
    priya_actions.ask_to_confirm_receipt("Casa Brisa", date(2027, 3, 16), 16_400)
    return priya_actions


def test_a_receipt_is_read_back_for_its_payer_to_confirm(store):
    priya_actions = priya_texts_a_receipt(store)

    assert said(priya_actions.outbox) == [
        "from the receipt: Casa Brisa, Mar 16, $164 total, paid by Priya. "
        "split it 3 ways?"
    ]
    assert store.get_trip(SPACE).expenses == []
    assert store.get_trip(SPACE).pending_receipt == PendingReceipt(
        PRIYA, "Casa Brisa", 16_400
    )


def test_logging_the_confirmed_receipt_clears_it(store):
    priya_actions = priya_texts_a_receipt(store)

    priya_actions.log_sender_expense(16_400, "Casa Brisa")

    trip = store.get_trip(SPACE)
    assert trip.pending_receipt is None
    assert [e.amount_cents for e in trip.expenses] == [16_400]


def test_a_dropped_receipt_is_never_logged(store):
    priya_actions = priya_texts_a_receipt(store)

    priya_actions.drop_pending_receipt()

    trip = store.get_trip(SPACE)
    assert trip.pending_receipt is None
    assert trip.expenses == []


CONDADO = Coordinates(18.4574, -66.0745)
TACO_SPOTS = [
    Place("place-1", "Lote 23", Coordinates(18.4518, -66.0730), "$$", "Food park."),
    Place("place-2", "Taco Bar", Coordinates(18.4580, -66.0750), "$", None),
    Place("place-3", "Cocina", Coordinates(18.4560, -66.0700), None, "Patio."),
]


class FakePlaces:
    """Stands in for Google Places.

    Finding a spot ("Condado, San Juan") only knows Condado. Searching for a
    vibe ("tacos in San Juan") returns `results`.
    """

    def __init__(self, results=TACO_SPOTS, is_down=False):
        self.results = results
        self.is_down = is_down
        self.searches = []

    def search(self, text_query, limit, near=None):
        if self.is_down:
            raise PlacesError("search didn't connect: timed out")
        self.searches.append((text_query, near))
        if " in " in text_query:
            return self.results[:limit]
        if text_query.startswith("Condado"):
            return [Place("condado", "Condado", CONDADO, None, None)]
        return []


def actions_with(store, places):
    return TripActions(store, SPACE, MAYA, OutsideServices(places=places))


def test_nearby_places_are_posted_with_rough_walking_times(locked_in_actions, store):
    maya_actions = actions_with(store, FakePlaces())

    maya_actions.suggest_nearby_places("cozy tacos with outdoor seating", "Condado")

    assert said(maya_actions.outbox) == [
        "near Condado:\n"
        "1. Lote 23 · $$ · ~10 min walk\n"
        "   Food park.\n"
        "2. Taco Bar · $ · ~1 min walk\n"
        "3. Cocina · ~8 min walk\n"
        "   Patio.\n"
        "reply with a number and i'll send directions."
    ]


def test_suggested_places_are_remembered_for_picking_one(locked_in_actions, store):
    actions_with(store, FakePlaces()).suggest_nearby_places("tacos", "Condado")

    assert store.get_trip(SPACE).place_suggestions == TACO_SPOTS


def test_a_places_outage_is_reported_instead_of_inventing_places(
    locked_in_actions, store
):
    with pytest.raises(TripActionError, match="place search isn't working"):
        actions_with(store, FakePlaces(is_down=True)).suggest_nearby_places(
            "tacos", None
        )
    assert store.get_trip(SPACE).place_suggestions == []


def test_picking_a_place_sends_directions_to_it(maya_actions, store):
    store.replace_place_suggestions(SPACE, TACO_SPOTS)

    maya_actions.send_directions(1)

    lead_in, link = maya_actions.outbox
    assert lead_in == Say("directions to Taco Bar:")
    assert link.url.startswith("https://www.google.com/maps/dir/")
    assert "destination_place_id=place-2" in link.url


class FakeBrochurePhotos:
    """Stands in for Google Places' photo lookups.

    Every search finds a place with one photo named after the search, and a
    hotel search finds a 4.7-star resort, unless `has_hotels` is off.
    """

    def __init__(self, has_hotels=True, is_down=False):
        self.has_hotels = has_hotels
        self.is_down = is_down

    def find_photographed(self, text_query, photo_count):
        if self.is_down:
            raise PlacesError("search didn't connect: timed out")
        if text_query.startswith("top rated hotel"):
            if not self.has_hotels:
                return None
            return PhotographedPlace("Playa Resort", 4.7, [])
        photo = f"https://lh3.googleusercontent.com/{text_query.replace(' ', '-')}"
        return PhotographedPlace(text_query, None, [photo][:photo_count])


def tropical_pitch(name):
    return DestinationPitch(
        name=name,
        region="Caribbean",
        description="White sand and warm water.",
        flights_usd=400,
        hotel_usd=500,
        food_and_activities_usd=200,
        activities=[ActivityPitch("Snorkel the reef", 60)],
    )


TROPICAL_PITCHES = [
    tropical_pitch("Tulum, Mexico"),
    tropical_pitch("Punta Cana, Dominican Republic"),
    tropical_pitch("San Juan, Puerto Rico"),
]


def test_each_destination_gets_its_own_card_named_for_the_place(
    maya_actions_with_photos,
):
    maya_actions_with_photos.send_destination_brochures(TROPICAL_PITCHES, nights=5)

    cards = maya_actions_with_photos.outbox
    assert all(isinstance(card, Card) for card in cards)
    assert [card.caption for card in cards] == ["Tulum", "Punta Cana", "San Juan"]
    assert {card.subcaption for card in cards} == {"3 locations for you to consider"}
    assert cards[0].thumbnail_url == "https://lh3.googleusercontent.com/Tulum,-Mexico"


@pytest.fixture
def maya_actions_with_photos(store, maya_actions):
    return actions_with(store, FakeBrochurePhotos())


class FakeFlights:
    """Stands in for Google Flights. Each airport in `routes` has one flight
    to wherever's asked; any other airport has none."""

    def __init__(self, routes, is_down=False):
        self.routes = routes
        self.is_down = is_down

    def find_best_flight(self, departure_airport, arrival_airport, dates):
        if self.is_down:
            raise FlightsError("search didn't connect: timed out")
        return self.routes.get(departure_airport)


def flight_from(airport, price_usd, layovers=()):
    return Flight(
        departure_airport=airport,
        arrival_airport="SJU",
        departs_at=datetime(2027, 3, 14, 6, 15),
        arrives_at=datetime(2027, 3, 14, 14, 20),
        flight_numbers=["B6 101"],
        airlines=["JetBlue"],
        layover_airports=list(layovers),
        duration_minutes=485,
        price_usd=price_usd,
        booking_url=f"https://www.google.com/travel/flights?from={airport}",
        destination_photo_url="https://lh5.googleusercontent.com/san-juan",
    )


ROUTES = {
    "BOS": flight_from("BOS", 312, layovers=["FLL"]),
    "NYC": flight_from("NYC", 1240),
}
HOME_AIRPORTS = [HomeAirport("Boston", "BOS"), HomeAirport("new york", "NYC")]


def flights_actions(store, flights):
    return TripActions(store, SPACE, MAYA, OutsideServices(flights=flights))


def test_flights_are_one_card_with_a_departure_board_per_home_city(
    locked_in_actions, store
):
    actions = flights_actions(store, FakeFlights(ROUTES))

    actions.send_best_flights(HOME_AIRPORTS, "SJU")

    [card] = actions.outbox
    assert isinstance(card, Card)
    assert card.layout["title"] == "Flights to San Juan, Puerto Rico"
    assert card.layout["subtitle"] == "Mar 14–19 · round trip"
    boards = [
        node["board"]
        for node in card.layout["root"]["children"]
        if node["type"] == "flightBoard"
    ]
    assert [(b["origin"], b["destination"]) for b in boards] == [
        ("BOS", "SJU"),
        ("NYC", "SJU"),
    ]
    assert boards[0]["departTime"] == "6:15 AM"
    assert boards[0]["status"] == "1 stop · FLL"
    assert boards[1]["status"] == "Nonstop"
    assert card.thumbnail_url == "https://lh5.googleusercontent.com/san-juan"


def test_without_flight_search_scout_sends_booking_links_instead(locked_in_actions):
    with pytest.raises(TripActionError, match="send booking links instead"):
        locked_in_actions.send_best_flights(HOME_AIRPORTS, "SJU")


def keep_media(store, tmp_path, kind, media_id="a1b2c3d4", space_id=SPACE):
    """A photo or voice note kept for a chat, with a readable copy on disk."""
    readable = tmp_path / f"{media_id}.readable.jpg"
    readable.write_bytes(b"jpeg bytes")
    store.save_media(
        space_id,
        SharedMedia(media_id, kind, tmp_path / f"{media_id}.heic", readable, None),
    )


def test_viewing_a_photo_shows_its_readable_copy(store, tmp_path, maya_actions):
    keep_media(store, tmp_path, MediaKind.PHOTO)

    photo = maya_actions.view_photo("a1b2c3d4")

    assert photo == MessagePhoto("image/jpeg", "anBlZyBieXRlcw==")


def test_another_chats_photos_stay_out_of_view(store, tmp_path, maya_actions):
    store.create_trip("another-chat")
    keep_media(store, tmp_path, MediaKind.PHOTO, space_id="another-chat")

    with pytest.raises(TripActionError, match="no photo a1b2c3d4"):
        maya_actions.view_photo("a1b2c3d4")
