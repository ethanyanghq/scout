from datetime import date

import pytest

from scout.brochures import ActivityPitch, DestinationPitch
from scout.outgoing import Card, Link, Say
from scout.outside_services import OutsideServices
from scout.places import Coordinates, PhotographedPlace, Place, PlacesError
from scout.trip import (
    DateWindow,
    DestinationOption,
    ItineraryDay,
    PendingReceipt,
    PreferenceUpdate,
    Settlement,
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


def test_saves_details_another_member_shared_earlier_in_the_chat(maya_actions, store):
    maya_actions.save_member_preferences("…0002", PreferenceUpdate(budget_usd=600))

    assert store.get_trip(SPACE).find_member(LEO).budget_usd == 600


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
        "Got it, …0002 → San Juan, Puerto Rico (1 of 2 voted)"
    )


def test_starting_a_poll_posts_it_to_the_chat(maya_actions):
    maya_actions.start_destination_poll(OPTIONS)

    assert said(maya_actions.outbox)[0].startswith("🗳️ Where should we go?")


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


def test_closing_the_poll_sends_a_calendar_link_after_the_winner(store):
    closing = everyone_votes_for_san_juan(store)

    winner, lead_in, link = closing.outbox
    assert winner.text.startswith("🎉 Poll closed! San Juan, Puerto Rico wins")
    assert lead_in.text.startswith("📅 Locked in: San Juan, Puerto Rico, Mar 14–19.")
    assert link == Link(link.url)
    assert link.url.startswith("https://calendar.google.com/calendar/render?")


def test_no_calendar_link_when_no_dates_work_for_everyone(store):
    leo_in_april = PreferenceUpdate(
        display_name="Leo",
        available_from=date(2027, 4, 1),
        available_to=date(2027, 4, 5),
        budget_usd=600,
        home_city="New York",
    )

    closing = everyone_votes_for_san_juan(store, leo_preferences=leo_in_april)

    assert store.get_trip(SPACE).dates is None
    assert len(said(closing.outbox)) == 1


def test_itinerary_is_posted_in_date_order(locked_in_actions):
    locked_in_actions.post_itinerary(
        [plan_day(15, "Beach day in Condado"), plan_day(14, "Land and check in")]
    )

    assert said(locked_in_actions.outbox) == [
        "🗓️ The plan:\nSun 3/14 · Land and check in\nMon 3/15 · Beach day in Condado"
    ]


def test_a_new_itinerary_replaces_the_old_one(locked_in_actions, store):
    locked_in_actions.post_itinerary([plan_day(14, "Land"), plan_day(15, "Beach")])

    locked_in_actions.post_itinerary([plan_day(16, "Rainforest hike")])

    assert store.get_trip(SPACE).itinerary == [plan_day(16, "Rainforest hike")]


def test_itinerary_days_must_fall_within_the_trip(locked_in_actions):
    with pytest.raises(TripActionError, match="outside the trip dates"):
        locked_in_actions.post_itinerary([plan_day(20, "One more beach day")])


def test_itinerary_cannot_plan_the_same_day_twice(locked_in_actions):
    with pytest.raises(TripActionError, match="only once"):
        locked_in_actions.post_itinerary([plan_day(14, "Beach"), plan_day(14, "Hike")])


def test_no_itinerary_before_a_destination_is_chosen(maya_actions):
    with pytest.raises(TripActionError, match="destination"):
        maya_actions.post_itinerary([plan_day(14, "Beach")])


def test_booking_links_cover_each_home_city_and_a_stay(locked_in_actions):
    locked_in_actions.send_booking_links()

    lines = said(locked_in_actions.outbox)[0].split("\n")
    assert lines[0] == "✈️ Flights for Mar 14–19:"
    assert lines[1].startswith("Boston: https://www.google.com/travel/flights?")
    assert lines[2].startswith("New York: https://www.google.com/travel/flights?")
    assert lines[3].startswith("🏠 Stays for 2: https://www.airbnb.com/s/")


def test_no_booking_links_before_a_destination_is_chosen(maya_actions):
    with pytest.raises(TripActionError, match="destination"):
        maya_actions.send_booking_links()


def test_logging_an_expense_confirms_it_in_the_chat(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, LEO, LEO_PREFERENCES)
    leo_actions = TripActions(store, SPACE, LEO)

    leo_actions.log_sender_expense(124_000, "Airbnb")

    assert said(leo_actions.outbox) == [
        "Got it: Airbnb, $1,240, paid by Leo. Split 2 ways."
    ]
    [expense] = store.get_trip(SPACE).expenses
    assert (expense.payer_phone, expense.amount_cents) == (LEO, 124_000)


def test_an_expense_must_cost_something(maya_actions):
    with pytest.raises(TripActionError):
        maya_actions.log_sender_expense(0, "Airbnb")


def test_payers_can_remove_their_own_expense(maya_actions, store):
    maya_actions.log_sender_expense(19_600, "Bio bay kayaks")
    [expense] = store.get_trip(SPACE).expenses

    maya_actions.remove_expense(expense.id)

    assert store.get_trip(SPACE).expenses == []
    assert said(maya_actions.outbox)[-1] == "Removed: Bio bay kayaks, $196."


def test_nobody_else_can_remove_someones_expense(maya_actions, store):
    expense_id = store.add_expense(SPACE, LEO, 124_000, "Airbnb")

    with pytest.raises(TripActionError, match="only they can remove it"):
        maya_actions.remove_expense(expense_id)
    assert len(store.get_trip(SPACE).expenses) == 1


def test_removing_an_expense_that_does_not_exist_is_refused(maya_actions):
    with pytest.raises(TripActionError, match="no expense #7"):
        maya_actions.remove_expense(7)


def test_settle_up_is_posted_to_the_chat(maya_actions):
    maya_actions.log_sender_expense(10_000, "Groceries")

    maya_actions.post_settle_up()

    assert said(maya_actions.outbox)[-1] == (
        "💸 Shared costs: $100, so $50 each. Fewest payments to settle up:\n"
        "…0002 → …0001 $50\n"
        'Once you\'ve paid, text "@scout I paid …0001".'
    )


def test_no_settle_up_before_anyone_logs_an_expense(maya_actions):
    with pytest.raises(TripActionError, match="nobody has logged an expense"):
        maya_actions.post_settle_up()


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
        "Paid ✓ Maya → Leo $50\nEveryone's settled up 🎉"
    ]
    assert store.get_trip(SPACE).settlements == [Settlement(MAYA, LEO, 5_000)]


def test_payee_names_match_however_they_are_capitalized(store):
    maya_owes_leo_50(store)

    TripActions(store, SPACE, MAYA).record_sender_payment(" leo ")

    assert len(store.get_trip(SPACE).settlements) == 1


def test_nobody_can_record_paying_someone_they_do_not_owe(store):
    maya_owes_leo_50(store)
    leo_actions = TripActions(store, SPACE, LEO)

    with pytest.raises(TripActionError, match="Leo doesn't owe Maya anything"):
        leo_actions.record_sender_payment("Maya")
    assert store.get_trip(SPACE).settlements == []


def test_a_refused_payment_says_who_the_sender_does_owe(store):
    maya_owes_leo_50(store)

    with pytest.raises(TripActionError, match="They owe: Leo"):
        TripActions(store, SPACE, MAYA).record_sender_payment("Jordan")


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
        "From the receipt: Casa Brisa, Mar 16, $164 total, paid by Priya. "
        "Split it 3 ways?"
    ]
    assert store.get_trip(SPACE).expenses == []
    assert store.get_trip(SPACE).pending_receipt == PendingReceipt(
        PRIYA, "Casa Brisa", 16_400
    )


def test_a_receipt_without_a_date_is_read_back_without_one(maya_actions):
    maya_actions.ask_to_confirm_receipt("Bodega", None, 1_250)

    assert said(maya_actions.outbox)[0].startswith(
        "From the receipt: Bodega, $12.50 total"
    )


def test_logging_the_confirmed_receipt_clears_it(store):
    priya_actions = priya_texts_a_receipt(store)

    priya_actions.log_sender_expense(16_400, "Casa Brisa")

    trip = store.get_trip(SPACE)
    assert trip.pending_receipt is None
    assert [e.amount_cents for e in trip.expenses] == [16_400]


def test_someone_elses_expense_leaves_the_receipt_waiting(store):
    priya_texts_a_receipt(store)

    TripActions(store, SPACE, LEO).log_sender_expense(2_000, "Ice")

    assert store.get_trip(SPACE).pending_receipt is not None


def test_a_dropped_receipt_is_never_logged(store):
    priya_actions = priya_texts_a_receipt(store)

    priya_actions.drop_pending_receipt()

    trip = store.get_trip(SPACE)
    assert trip.pending_receipt is None
    assert trip.expenses == []


def test_a_receipt_total_must_be_more_than_zero(maya_actions):
    with pytest.raises(TripActionError):
        maya_actions.ask_to_confirm_receipt("Casa Brisa", None, 0)


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
        "📍 Near Condado:\n"
        "1. Lote 23 · $$ · ~10 min walk\n"
        "   Food park.\n"
        "2. Taco Bar · $ · ~1 min walk\n"
        "3. Cocina · ~8 min walk\n"
        "   Patio.\n"
        "Reply with a number and I'll send directions."
    ]


def test_places_are_searched_near_the_spot_the_group_named(locked_in_actions, store):
    places = FakePlaces()

    actions_with(store, places).suggest_nearby_places("tacos", "Condado")

    assert places.searches == [
        ("Condado, San Juan, Puerto Rico", None),
        ("tacos in San Juan, Puerto Rico", CONDADO),
    ]


def test_without_a_named_spot_places_come_from_the_whole_destination(
    locked_in_actions, store
):
    maya_actions = actions_with(store, FakePlaces())

    maya_actions.suggest_nearby_places("tacos", None)

    assert said(maya_actions.outbox)[0].startswith(
        "📍 Near San Juan, Puerto Rico:\n1. Lote 23 · $$\n"
    )


def test_suggested_places_are_remembered_for_picking_one(locked_in_actions, store):
    actions_with(store, FakePlaces()).suggest_nearby_places("tacos", "Condado")

    assert store.get_trip(SPACE).place_suggestions == TACO_SPOTS


def test_no_suggestions_before_a_destination_is_chosen(maya_actions, store):
    with pytest.raises(TripActionError, match="hasn't picked a destination"):
        actions_with(store, FakePlaces()).suggest_nearby_places("tacos", None)


def test_no_suggestions_without_a_places_api_key(locked_in_actions):
    with pytest.raises(TripActionError, match="place search isn't set up"):
        locked_in_actions.suggest_nearby_places("tacos", None)


def test_a_spot_that_cannot_be_found_is_reported(locked_in_actions, store):
    places = FakePlaces()

    with pytest.raises(TripActionError, match="couldn't find 'Narnia'"):
        actions_with(store, places).suggest_nearby_places("tacos", "Narnia")


def test_a_search_with_no_matches_is_reported(locked_in_actions, store):
    with pytest.raises(TripActionError, match="no places matched"):
        actions_with(store, FakePlaces(results=[])).suggest_nearby_places(
            "igloo bar", None
        )


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
    assert lead_in == Say("🧭 Directions to Taco Bar:")
    assert link.url.startswith("https://www.google.com/maps/dir/")
    assert "destination_place_id=place-2" in link.url


def test_once_a_place_is_picked_the_suggestions_are_done(maya_actions, store):
    store.replace_place_suggestions(SPACE, TACO_SPOTS)

    maya_actions.send_directions(0)

    assert store.get_trip(SPACE).place_suggestions == []


def test_picking_a_place_that_was_not_suggested_is_refused(maya_actions, store):
    store.replace_place_suggestions(SPACE, TACO_SPOTS)

    with pytest.raises(TripActionError, match="place 4 doesn't exist"):
        maya_actions.send_directions(3)


def test_no_directions_without_suggestions(maya_actions):
    with pytest.raises(TripActionError, match="no place suggestions"):
        maya_actions.send_directions(0)


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


def test_brochures_are_one_card_with_real_photos_and_an_all_in_price(
    maya_actions_with_photos,
):
    maya_actions_with_photos.send_destination_brochures(TROPICAL_PITCHES, nights=5)

    [card] = maya_actions_with_photos.outbox
    assert isinstance(card, Card)
    tulum = card.layout["root"]["catalogItems"][0]
    assert tulum["title"] == "Tulum, Mexico"
    assert tulum["priceText"] == "~$1,100"
    assert tulum["heroImageUrl"] == "https://lh3.googleusercontent.com/Tulum,-Mexico"
    assert "Playa Resort (★ 4.7)" in tulum["detail"]
    assert [tile["label"] for tile in tulum["amenities"]] == [
        "Flights ~$400",
        "Hotel ~$500",
        "Food & fun ~$200",
    ]
    [snorkel] = tulum["rooms"]
    assert snorkel["name"] == "Snorkel the reef"
    assert snorkel["imageUrl"].startswith("https://lh3.googleusercontent.com/Snorkel")
    assert card.thumbnail_url == tulum["heroImageUrl"]


def test_brochures_read_the_same_as_text_on_phones_without_the_card_app(
    maya_actions_with_photos,
):
    maya_actions_with_photos.send_destination_brochures(TROPICAL_PITCHES, nights=5)

    [card] = maya_actions_with_photos.outbox
    assert card.fallback_text.startswith("Estimates per person for 5 nights.")
    assert (
        "Tulum, Mexico · ~$1,100\n"
        "Flights ~$400 · Hotel ~$500 · Food & fun ~$200\n"
        "White sand and warm water.\n"
        "Stay: Playa Resort (★ 4.7)\n"
        "Do: Snorkel the reef (~$60)"
    ) in card.fallback_text


def test_brochures_need_exactly_three_destinations(maya_actions_with_photos):
    with pytest.raises(TripActionError, match="expected 3 destinations, got 2"):
        maya_actions_with_photos.send_destination_brochures(TROPICAL_PITCHES[:2], 5)


def test_a_destination_without_a_hotel_asks_for_another_pick(store, maya_actions):
    actions = actions_with(store, FakeBrochurePhotos(has_hotels=False))

    with pytest.raises(TripActionError, match="no hotel found in Tulum"):
        actions.send_destination_brochures(TROPICAL_PITCHES, nights=5)
    assert actions.outbox == []


def test_brochures_say_so_when_place_search_is_down(store, maya_actions):
    actions = actions_with(store, FakeBrochurePhotos(is_down=True))

    with pytest.raises(TripActionError, match="place search isn't working"):
        actions.send_destination_brochures(TROPICAL_PITCHES, nights=5)


def test_brochures_need_place_search_set_up(maya_actions):
    with pytest.raises(TripActionError, match="brochures aren't available"):
        maya_actions.send_destination_brochures(TROPICAL_PITCHES, nights=5)


@pytest.fixture
def maya_actions_with_photos(store, maya_actions):
    return actions_with(store, FakeBrochurePhotos())
