from dataclasses import replace
from datetime import date, datetime, time

import pytest

from scout.best_flights import HomeAirport
from scout.brochures import ActivityPitch, DestinationPitch
from scout.cards import (
    EXPENSES_THUMBNAIL_URL,
    FLIGHTS_THUMBNAIL_URL,
    fits_in_one_message,
)
from scout.flights import Flight, FlightsError, Layover, OneWay
from scout.hotels import Hotel, HotelsError, NearbyPlace
from scout.outgoing import Card, Link, React, Say, Tapback
from scout.outside_services import OutsideServices
from scout.places import Coordinates, PhotographedPlace, Place, PlacesError
from scout.trip import (
    Chronotype,
    DateWindow,
    DeckActivity,
    DestinationOption,
    ItineraryAddOn,
    ItineraryDay,
    MediaKind,
    MessagePhoto,
    NewExpense,
    PendingReceipt,
    PreferenceUpdate,
    Rating,
    Settlement,
    SharedMedia,
)
from scout.trip_actions import (
    ExpenseDraft,
    ItemDraft,
    TripActionError,
    TripActions,
)

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


def plan_day(day_of_march, plan, starts_at=None):
    return ItineraryDay(date(2027, 3, day_of_march), plan, starts_at)


def test_saving_preferences_reports_what_is_still_missing(maya_actions):
    status = maya_actions.save_member_preferences(
        "…0001", PreferenceUpdate(display_name="Maya", budget_usd=800)
    )

    assert "Maya is still missing: dates, home city" in status
    assert "waiting on: Maya, …0002" in status


def test_saving_the_senders_own_details_confirms_with_a_thumbs_up(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    actions = TripActions(store, SPACE, MAYA, message_id="msg-1")

    status = actions.save_member_preferences("…0001", MAYA_PREFERENCES)

    assert actions.outbox == [
        React(
            "msg-1",
            Tapback.LIKE,
            fallback_text="got it maya: mar 13–20 · ~$800 · boston",
        )
    ]
    assert "A 👍 is going on their newest message" in status


def test_the_thumbs_up_fallback_text_never_names_someone_by_their_number(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])
    actions = TripActions(store, SPACE, MAYA, message_id="msg-1")

    actions.save_member_preferences("…0001", PreferenceUpdate(budget_usd=800))

    assert actions.outbox[0].fallback_text == "got it: ~$800"


def test_saving_a_friends_details_is_confirmed_in_text_not_a_thumbs_up(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    actions = TripActions(store, SPACE, MAYA, message_id="msg-1")

    status = actions.save_member_preferences("…0002", LEO_PREFERENCES)

    assert actions.outbox == []
    assert "👍" not in status


def test_without_a_message_to_react_on_nothing_is_sent(maya_actions):
    status = maya_actions.save_member_preferences("…0001", MAYA_PREFERENCES)

    assert maya_actions.outbox == []
    assert "👍" not in status


def test_saving_twice_from_one_message_gives_only_one_thumbs_up(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])
    actions = TripActions(store, SPACE, MAYA, message_id="msg-1")

    actions.save_member_preferences("…0001", PreferenceUpdate(budget_usd=800))
    actions.save_member_preferences("…0001", PreferenceUpdate(home_city="Boston"))

    assert len(actions.outbox) == 1


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


def test_choosing_for_the_group_announces_the_lock_in_once(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, LEO_PREFERENCES)
    actions = TripActions(store, SPACE, MAYA)

    actions.lock_in_group_choice("san juan")

    texts = [item.text for item in actions.outbox if isinstance(item, Say)]
    assert texts == ["locked in: san juan, Mar 14–19 🎉"]


def test_locking_in_a_destination_tells_the_agent_to_send_the_activity_deck(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, LEO_PREFERENCES)

    result = TripActions(store, SPACE, MAYA).lock_in_group_choice("san juan")

    assert "call send_activity_deck" in result


def test_the_group_can_choose_a_destination_without_a_poll(maya_actions, store):
    maya_actions.lock_in_group_choice("Lisbon, Portugal")

    assert store.get_trip(SPACE).destination == "Lisbon, Portugal"


def test_itinerary_is_posted_in_date_order(locked_in_actions):
    locked_in_actions.post_itinerary(
        [plan_day(15, "Beach day in Condado"), plan_day(14, "Land and check in")],
        add_ons=[],
    )

    assert said(locked_in_actions.outbox)[1:] == [
        "the plan:\n\n"
        "Sunday, March 14\nLand and check in\n\n"
        "Monday, March 15\nBeach day in Condado"
    ]


def test_itinerary_days_must_fall_within_the_trip(locked_in_actions):
    with pytest.raises(TripActionError, match="outside the trip dates"):
        locked_in_actions.post_itinerary(
            [plan_day(20, "One more beach day")], add_ons=[]
        )


def test_itinerary_shows_when_each_day_starts_and_who_wants_each_add_on(
    locked_in_actions,
):
    locked_in_actions.post_itinerary(
        [
            plan_day(14, "Land and check in"),
            plan_day(15, "Night kayak on the bio bay", starts_at=time(21, 30)),
        ],
        add_ons=[ItineraryAddOn("Scuba at Escambrón", wanted_by="leo")],
    )

    assert said(locked_in_actions.outbox)[1:] == [
        "the plan:\n\n"
        "Sunday, March 14\nLand and check in\n\n"
        "Monday, March 15\n9:30 PM · Night kayak on the bio bay\n\n"
        "optional add-ons:\n"
        "Scuba at Escambrón · Leo's pick"
    ]


def test_a_day_can_list_several_events_in_the_order_they_happen(
    locked_in_actions, store
):
    locked_in_actions.post_itinerary(
        [
            plan_day(14, "Dinner in Old San Juan", starts_at=time(19, 0)),
            plan_day(14, "Beach morning", starts_at=time(10, 0)),
            plan_day(15, "Bio bay kayak", starts_at=time(21, 0)),
        ],
        add_ons=[],
    )

    plan = [(event.day.day, event.plan) for event in store.get_trip(SPACE).itinerary]
    assert plan == [
        (14, "Beach morning"),
        (14, "Dinner in Old San Juan"),
        (15, "Bio bay kayak"),
    ]
    assert said(locked_in_actions.outbox)[1] == (
        "the plan:\n\n"
        "Sunday, March 14\n10:00 AM · Beach morning\n"
        "7:00 PM · Dinner in Old San Juan\n\n"
        "Monday, March 15\n9:00 PM · Bio bay kayak"
    )


def test_an_add_on_must_be_for_someone_in_the_chat(locked_in_actions):
    with pytest.raises(TripActionError, match="no single member is called 'Sam'"):
        locked_in_actions.post_itinerary(
            [plan_day(14, "Land and check in")],
            add_ons=[ItineraryAddOn("Scuba", wanted_by="Sam")],
        )


def test_a_new_plan_replaces_the_old_days_and_add_ons(locked_in_actions, store):
    locked_in_actions.post_itinerary(
        [plan_day(14, "Land"), plan_day(15, "Old Town walk")],
        add_ons=[ItineraryAddOn("Scuba", wanted_by="Leo")],
    )

    locked_in_actions.post_itinerary(
        [plan_day(14, "Land", starts_at=time(16, 0))], add_ons=[]
    )

    trip = store.get_trip(SPACE)
    assert trip.itinerary == [plan_day(14, "Land", starts_at=time(16, 0))]
    assert trip.itinerary_add_ons == []


def test_booking_links_cover_each_home_city_and_a_stay(locked_in_actions):
    locked_in_actions.send_booking_links()

    lines = said(locked_in_actions.outbox)[0].split("\n")
    assert lines[0] == "flights for Mar 14–19:"
    assert lines[1].startswith("Boston: https://www.google.com/travel/flights?")
    assert lines[2].startswith("New York: https://www.google.com/travel/flights?")
    assert lines[3].startswith("stays for 2: https://www.airbnb.com/s/")


def test_payers_can_remove_their_own_expense(maya_actions, store):
    maya_actions.log_sender_expense(ExpenseDraft(19_600, "Bio bay kayaks"))
    [expense] = store.get_trip(SPACE).expenses

    maya_actions.remove_expense(expense.id)

    assert store.get_trip(SPACE).expenses == []
    assert said(maya_actions.outbox)[-1] == "removed: Bio bay kayaks, $196."


def test_nobody_else_can_remove_someones_expense(maya_actions, store):
    expense_id = store.add_expense(
        SPACE, even_expense(LEO, 124_000, "Airbnb", MAYA, LEO)
    )

    with pytest.raises(TripActionError, match="only they can remove it"):
        maya_actions.remove_expense(expense_id)
    assert len(store.get_trip(SPACE).expenses) == 1


def even_expense(payer, cents, description, *members):
    shares = {member: cents // len(members) for member in members}
    return NewExpense(payer, cents, description, shares)


def maya_owes_leo_50(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, LEO_PREFERENCES)
    store.add_expense(SPACE, even_expense(LEO, 10_000, "Groceries", MAYA, LEO))


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
        "split it 3 ways, or tell me who had what?"
    ]
    assert store.get_trip(SPACE).expenses == []
    assert store.get_trip(SPACE).pending_receipt == PendingReceipt(
        PRIYA, "Casa Brisa", 16_400
    )


def test_logging_the_confirmed_receipt_clears_it(store):
    priya_actions = priya_texts_a_receipt(store)

    priya_actions.log_sender_expense(ExpenseDraft(16_400, "Casa Brisa"))

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

    *cards, _closing_line = maya_actions_with_photos.outbox
    assert all(isinstance(card, Card) for card in cards)
    assert [card.caption for card in cards] == ["Tulum", "Punta Cana", "San Juan"]
    assert cards[0].thumbnail_url == "https://lh3.googleusercontent.com/Tulum,-Mexico"


@pytest.fixture
def maya_actions_with_photos(store, maya_actions):
    return actions_with(store, FakeBrochurePhotos())


def test_the_plan_is_a_timeline_card_with_the_text_for_phones_without_it(
    locked_in_actions, store
):
    store.save_preferences(
        SPACE, MAYA, PreferenceUpdate(chronotype=Chronotype.NIGHT_OWL)
    )
    actions = actions_with(store, FakeBrochurePhotos())

    actions.post_itinerary(
        [
            plan_day(15, "Night kayak on the bio bay", starts_at=time(21, 30)),
            plan_day(14, "Land and check in"),
        ],
        add_ons=[ItineraryAddOn("Scuba at Escambrón", wanted_by="Leo")],
    )

    _announcement, card = actions.outbox
    assert isinstance(card, Card)
    assert card.thumbnail_url == (
        "https://lh3.googleusercontent.com/San-Juan,-Puerto-Rico"
    )
    assert card.layout["subtitle"] == "Mar 14–19 · paced for night owls"
    tables = [
        node["child"]["children"]
        for node in card.layout["root"]["children"]
        if node.get("child", {}).get("children", [{}])[0].get("type") == "text"
        and node["child"]["children"][1:2] == [{"type": "divider"}]
    ]
    assert [(table[0]["text"], table[2:]) for table in tables] == [
        (
            "Sunday, March 14",
            [{"type": "keyValueRow", "key": "Land and check in", "value": "Anytime"}],
        ),
        (
            "Monday, March 15",
            [
                {
                    "type": "keyValueRow",
                    "key": "Night kayak on the bio bay",
                    "value": "9:30 PM",
                }
            ],
        ),
    ]
    assert "Scuba at Escambrón · Leo's pick" in card.fallback_text


def test_locking_in_the_destination_sends_no_calendar_link(store):
    everyone_votes_for_san_juan(store)
    actions = TripActions(
        store, SPACE, MAYA, OutsideServices(public_url="https://scout.example.com")
    )

    actions.lock_in_group_choice("Tulum, Mexico")

    assert not [item for item in actions.outbox if isinstance(item, Link)]


def test_the_first_plan_is_announced_then_posted_then_offered_as_a_calendar(
    locked_in_actions, store
):
    actions = TripActions(
        store,
        SPACE,
        MAYA,
        OutsideServices(
            places=FakeBrochurePhotos(), public_url="https://scout.example.com"
        ),
    )

    actions.post_itinerary([plan_day(14, "Land and check in")], add_ons=[])

    announcement, itinerary_card, calendar_offer, calendar_link = actions.outbox
    assert announcement.text.endswith("is set")
    assert isinstance(itinerary_card, Card)
    assert calendar_offer.text == "to put this on your calendar, you can subscribe to:"
    assert calendar_link == Link(f"webcal://scout.example.com/calendars/{SPACE}.ics")


def test_a_revised_plan_does_not_send_the_calendar_link_again(locked_in_actions, store):
    services = OutsideServices(public_url="https://scout.example.com")
    first = TripActions(store, SPACE, MAYA, services)
    first.post_itinerary([plan_day(14, "Land")], add_ons=[])
    revision = TripActions(store, SPACE, MAYA, services)

    revision.post_itinerary([plan_day(14, "Land and swim")], add_ons=[])

    assert not [item for item in revision.outbox if isinstance(item, Link)]


def test_the_plan_is_posted_as_text_when_place_search_is_down(locked_in_actions, store):
    actions = actions_with(store, FakeBrochurePhotos(is_down=True))

    status = actions.post_itinerary([plan_day(14, "Land and check in")], add_ons=[])

    assert said(actions.outbox)[1:] == [
        "the plan:\n\nSunday, March 14\nLand and check in"
    ]
    assert "place search isn't working" in status


def deck_activity(name):
    return DeckActivity(name, "A local favorite.", 60)


DECK = [
    deck_activity("Night kayak in the bio bay"),
    deck_activity("Old San Juan food tour"),
    deck_activity("El Yunque hike"),
]


def test_the_deck_is_one_card_with_a_nah_meh_yeah_choice_per_activity(
    locked_in_actions, store
):
    actions = actions_with(store, FakeBrochurePhotos())

    actions.send_activity_deck(DECK)

    [card] = actions.outbox
    assert card.thumbnail_url == (
        "https://lh3.googleusercontent.com/San-Juan,-Puerto-Rico"
    )
    choices = card.layout["root"]["children"]
    assert len(choices) == len(DECK)
    first = choices[0]["child"]["children"]
    assert first[0]["urls"] == [
        "https://lh3.googleusercontent.com/"
        "Night-kayak-in-the-bio-bay-in-San-Juan,-Puerto-Rico"
    ]
    assert first[1]["text"] == "Night kayak in the bio bay"
    assert first[2]["text"] == "~$60 per person · A local favorite."
    picker = first[3]
    assert [o["label"] for o in picker["options"]] == ["Nah", "Meh", "Yeah"]
    # Starting on nah means every activity has a rating when Send is tapped.
    assert picker["selectedId"] == "nah"
    [send] = card.layout["actions"]
    assert send["deepLinkURL"] == "hermesshare://text?lead=%40scout%20my%20picks%3A"


def test_the_deck_uses_only_nodes_the_hermesshare_build_on_phones_can_open(
    locked_in_actions, store
):
    actions = actions_with(store, FakeBrochurePhotos())

    actions.send_activity_deck(DECK)

    [card] = actions.outbox
    assert "swipeDeck" not in node_types(card.layout["root"])


class FakeLongPhotoLinks(FakeBrochurePhotos):
    """Google Places, when its photo links run to thousands of characters."""

    def find_photographed(self, text_query, photo_count):
        place = super().find_photographed(text_query, photo_count)
        return replace(place, photo_urls=[url + "x" * 6000 for url in place.photo_urls])


def test_a_deck_too_big_for_one_message_drops_the_activity_photos(
    locked_in_actions, store
):
    actions = actions_with(store, FakeLongPhotoLinks())

    actions.send_activity_deck(DECK)

    [card] = actions.outbox
    assert fits_in_one_message(card.layout)
    assert card.thumbnail_url is not None
    assert "gallery" not in node_types(card.layout["root"])


def test_without_place_search_the_deck_goes_out_as_numbered_text(
    locked_in_actions, store
):
    status = locked_in_actions.send_activity_deck(DECK)

    [card] = locked_in_actions.outbox
    assert card.thumbnail_url is None
    assert "2. Old San Juan food tour · ~$60" in card.fallback_text
    assert '"@scout my picks: 1 yeah, 2 meh, 3 nah"' in card.fallback_text
    assert "posted as text: place search isn't set up" in status


def test_a_deck_activity_name_cant_hold_the_pick_separators(locked_in_actions):
    with pytest.raises(TripActionError, match="can't contain"):
        locked_in_actions.send_activity_deck(
            [*DECK[:2], deck_activity("Snorkel, then lunch")]
        )


def test_a_deck_activity_name_cant_end_in_a_rating(locked_in_actions):
    with pytest.raises(TripActionError, match="can't end in"):
        locked_in_actions.send_activity_deck([*DECK[:2], deck_activity("Hell Yeah")])


def test_picks_are_confirmed_until_the_last_one_asks_for_the_itinerary(store):
    everyone_votes_for_san_juan(store)
    TripActions(store, SPACE, MAYA).send_activity_deck(DECK)

    maya_actions = TripActions(store, SPACE, MAYA)
    maya_actions.record_sender_picks({0: Rating.YEAH, 1: Rating.MEH})
    leo_actions = TripActions(store, SPACE, LEO)
    result = leo_actions.record_sender_picks({0: Rating.YEAH})

    assert said(maya_actions.outbox) == ["got Maya's picks (1 of 2 sent)"]
    assert said(leo_actions.outbox) == []
    assert "call post_itinerary" in result


def test_sending_a_new_deck_forgets_the_old_picks(locked_in_actions, store):
    locked_in_actions.send_activity_deck(DECK)
    locked_in_actions.record_sender_picks({0: Rating.YEAH})

    locked_in_actions.send_activity_deck(DECK)

    assert store.get_trip(SPACE).activity_deck.picks == {}


def test_picks_must_be_on_the_deck(locked_in_actions):
    locked_in_actions.send_activity_deck(DECK)

    with pytest.raises(TripActionError, match="activity 4 isn't on the deck"):
        locked_in_actions.record_member_picks("Leo", {3: Rating.YEAH})


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
        outbound=OneWay(
            departure_airport=airport,
            arrival_airport="SJU",
            departs_at=datetime(2027, 3, 14, 6, 15),
            arrives_at=datetime(2027, 3, 14, 14, 20),
            flight_numbers=["B6 101", "B6 955"] if layovers else ["B6 101"],
            airlines=["JetBlue"],
            layovers=list(layovers),
            duration_minutes=485,
        ),
        homebound=OneWay(
            departure_airport="SJU",
            arrival_airport=airport,
            departs_at=datetime(2027, 3, 19, 22, 30),
            arrives_at=datetime(2027, 3, 20, 2, 45),
            flight_numbers=["B6 902"],
            airlines=["JetBlue"],
            layovers=[],
            duration_minutes=255,
        ),
        price_usd=price_usd,
        booking_url=f"https://www.google.com/travel/flights?from={airport}",
    )


ROUTES = {
    "BOS": flight_from("BOS", 312, layovers=[Layover("FLL", 85)]),
    "NYC": flight_from("NYC", 1240),
}
HOME_AIRPORTS = [HomeAirport("Boston", "BOS"), HomeAirport("new york", "NYC")]


def flights_actions(store, flights):
    return TripActions(store, SPACE, MAYA, OutsideServices(flights=flights))


def test_flights_are_one_card_with_both_ways_from_each_home_city(
    locked_in_actions, store
):
    actions = flights_actions(store, FakeFlights(ROUTES))

    actions.send_best_flights(HOME_AIRPORTS, "SJU")

    intro, card, offer = actions.outbox
    assert intro == Say("these flights seem like the best deals")
    assert offer == Say("want me to find a hotel too?")
    assert isinstance(card, Card)
    assert card.layout["title"] == "Flights to San Juan, Puerto Rico"
    assert card.layout["subtitle"] == "Mar 14–19 · round trip"
    words = card_words(card.layout)
    assert {"FROM BOSTON", "FROM NEW YORK"} <= words
    assert {"Out · Sun, Mar 14", "Back · Fri, Mar 19"} <= words
    assert {"Leave BOS · Boston", "Land SJU · San Juan, Puerto Rico"} <= words
    assert {"Leave SJU · San Juan, Puerto Rico", "Land BOS · Boston"} <= words
    assert {"6:15 AM", "2:20 PM", "10:30 PM", "2:45 AM +1"} <= words
    assert {"$312 per person", "$1,240 per person"} <= words


def test_the_flight_card_shows_where_each_layover_is_and_how_long(
    locked_in_actions, store
):
    actions = flights_actions(store, FakeFlights(ROUTES))

    actions.send_best_flights(HOME_AIRPORTS, "SJU")

    _, card, _ = actions.outbox
    words = card_words(card.layout)
    assert {"1 stop · FLL", "Nonstop"} <= words
    assert {"Change planes in FLL", "1h 25m wait"} <= words


def test_the_flight_card_bubble_shows_a_plane_not_the_destination(
    locked_in_actions, store
):
    actions = flights_actions(store, FakeFlights(ROUTES))

    actions.send_best_flights(HOME_AIRPORTS, "SJU")

    _, card, _ = actions.outbox
    assert card.thumbnail_url == FLIGHTS_THUMBNAIL_URL


def test_the_flights_text_has_the_way_out_and_the_way_back(locked_in_actions, store):
    actions = flights_actions(store, FakeFlights(ROUTES))

    actions.send_best_flights(HOME_AIRPORTS, "SJU")

    _, card, _ = actions.outbox
    assert (
        "   out Sun, Mar 14, BOS 6:15 AM → SJU 2:20 PM · JetBlue B6 101 · "
        "1 stop · FLL · 8h 5m" in card.fallback_text.splitlines()
    )
    assert (
        "   back Fri, Mar 19, SJU 10:30 PM → BOS 2:45 AM +1 · JetBlue B6 902 · "
        "Nonstop · 4h 15m" in card.fallback_text.splitlines()
    )


def test_without_flight_search_scout_sends_booking_links_instead(locked_in_actions):
    with pytest.raises(TripActionError, match="send booking links instead"):
        locked_in_actions.send_best_flights(HOME_AIRPORTS, "SJU")


class FakeHotels:
    """Stands in for Google Hotels: finds `hotel` wherever's asked, or nothing."""

    def __init__(self, hotel, is_down=False):
        self.hotel = hotel
        self.is_down = is_down

    def find_best_hotel(self, destination, dates):
        if self.is_down:
            raise HotelsError("search didn't connect: timed out")
        return self.hotel


CONDADO_VISTA = Hotel(
    name="Condado Vista",
    kind="4-star hotel",
    room_details=[],
    guest_rating=4.5,
    review_count=1203,
    location_rating=4.8,
    nights=5,
    nightly_rate_usd=189,
    stay_total_usd=945,
    typical_nightly_rate_usd=230,
    deal="21% less than usual",
    amenities=["Spa", "Free Wi-Fi", "Outdoor pool", "Beach access"],
    nearby_places=[NearbyPlace("Condado Beach", "2 min walk")],
    check_in_time="3:00 PM",
    check_out_time="11:00 AM",
    coordinates=Coordinates(18.4583, -66.0745),
    photo_url="https://lh5.googleusercontent.com/hotel-front",
    booking_url="https://www.google.com/travel/hotels?q=Condado%20Vista",
)


def card_words(layout):
    """Every string anywhere in a card, so a test can ask what it says."""
    if isinstance(layout, str):
        return {layout}
    children = layout.values() if isinstance(layout, dict) else layout
    if not isinstance(layout, dict | list):
        return set()
    return set().union(*(card_words(child) for child in children), set())


def node_types(node):
    """The type of every node anywhere in a card's tree."""
    if isinstance(node, list):
        return set().union(*(node_types(child) for child in node), set())
    if not isinstance(node, dict):
        return set()
    own = {node["type"]} if isinstance(node.get("type"), str) else set()
    return own.union(*(node_types(child) for child in node.values()))


def hotels_actions(store, hotels):
    return TripActions(store, SPACE, MAYA, OutsideServices(hotels=hotels))


def test_the_hotel_is_one_card_with_its_photo_rate_and_rating(locked_in_actions, store):
    actions = hotels_actions(store, FakeHotels(CONDADO_VISTA))

    actions.send_best_hotel()

    intro, card = actions.outbox
    assert intro == Say("this seems like the best place to stay")
    assert isinstance(card, Card)
    assert card.layout["title"] == "Where to stay in San Juan, Puerto Rico"
    assert card.layout["subtitle"] == "Mar 14–19 · 5 nights"
    words = card_words(card.layout)
    assert {"Condado Vista", "4-star hotel", "4.5 ★ · 1,203 reviews"} <= words
    assert {"$189", "$945", "All 5 nights"} <= words
    assert [a["deepLinkURL"] for a in card.layout["actions"]] == [
        CONDADO_VISTA.booking_url
    ]
    assert card.thumbnail_url == CONDADO_VISTA.photo_url
    assert "Condado Vista · 4.5 ★" in card.fallback_text


def test_the_hotel_card_compares_the_rate_with_whats_typical(locked_in_actions, store):
    actions = hotels_actions(store, FakeHotels(CONDADO_VISTA))

    actions.send_best_hotel()

    _, card = actions.outbox
    words = card_words(card.layout)
    assert {"Typical here", "$230 a night", "Deal · 21% less than usual"} <= words
    assert (
        "   21% less than usual · typical here is $230 a night"
        in card.fallback_text.splitlines()
    )


def test_the_hotel_card_shows_where_it_is_and_whats_there(locked_in_actions, store):
    actions = hotels_actions(store, FakeHotels(CONDADO_VISTA))

    actions.send_best_hotel()

    _, card = actions.outbox
    words = card_words(card.layout)
    assert {"Location", "4.8 out of 5", "Condado Beach", "2 min walk"} <= words
    assert {"3:00 PM", "11:00 AM"} <= words
    [tags] = [n for n in card.layout["root"]["children"] if n["type"] == "tagRow"]
    assert tags["labels"] == ["Beach access", "Outdoor pool", "Free Wi-Fi", "Spa"]
    [hotel_map] = [
        n for n in card.layout["root"]["children"] if n["type"] == "mapPreview"
    ]
    assert (hotel_map["latitude"], hotel_map["longitude"]) == (18.4583, -66.0745)


def test_a_hotel_rating_is_rounded_to_one_decimal(locked_in_actions, store):
    rental = replace(CONDADO_VISTA, guest_rating=4.427273, review_count=33)
    actions = hotels_actions(store, FakeHotels(rental))

    actions.send_best_hotel()

    _, card = actions.outbox
    assert "4.4 ★ · 33 reviews" in card_words(card.layout)


def test_a_rental_card_says_what_the_place_is(locked_in_actions, store):
    rental = replace(
        CONDADO_VISTA,
        kind="Vacation rental",
        room_details=["Entire apartment", "Sleeps 6", "1 bedroom"],
    )
    actions = hotels_actions(store, FakeHotels(rental))

    actions.send_best_hotel()

    _, card = actions.outbox
    assert "Vacation rental · Entire apartment · Sleeps 6 · 1 bedroom" in card_words(
        card.layout
    )


def test_an_unrated_hotel_card_leaves_out_the_rating(locked_in_actions, store):
    unrated = replace(CONDADO_VISTA, guest_rating=None, review_count=None)
    actions = hotels_actions(store, FakeHotels(unrated))

    actions.send_best_hotel()

    _, card = actions.outbox
    assert "Guests say" not in card_words(card.layout)
    assert "★" not in card.fallback_text


def test_without_hotel_search_scout_sends_booking_links_instead(locked_in_actions):
    with pytest.raises(TripActionError, match="send booking links instead"):
        locked_in_actions.send_best_hotel()


def test_a_hotel_search_that_fails_is_reported(locked_in_actions, store):
    actions = hotels_actions(store, FakeHotels(None, is_down=True))

    with pytest.raises(TripActionError, match="hotel search isn't working"):
        actions.send_best_hotel()


def test_no_hotel_with_a_rate_points_to_booking_links(locked_in_actions, store):
    actions = hotels_actions(store, FakeHotels(None))

    with pytest.raises(TripActionError, match="no hotels with a rate.*booking links"):
        actions.send_best_hotel()


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


def test_after_the_brochures_scout_asks_for_the_groups_final_decision(
    maya_actions_with_photos,
):
    maya_actions_with_photos.send_destination_brochures(TROPICAL_PITCHES, nights=5)

    assert maya_actions_with_photos.outbox[-1] == Say(
        "once you're ready, let me know your final decision with @scout"
    )


@pytest.fixture
def trio_actions(store):
    """Maya, Leo and Priya, with Priya's actions."""
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO, PRIYA])
    for phone, name in [(MAYA, "Maya"), (LEO, "Leo"), (PRIYA, "Priya")]:
        store.save_preferences(SPACE, phone, PreferenceUpdate(display_name=name))
    return lambda phone: TripActions(store, SPACE, phone)


def test_a_cost_only_two_people_shared_is_split_between_just_them(trio_actions, store):
    maya_actions = trio_actions(MAYA)

    maya_actions.log_sender_expense(
        ExpenseDraft(19_600, "Kayaks", split_among=("Maya", "Leo"))
    )

    [expense] = store.get_trip(SPACE).expenses
    assert expense.shares == {MAYA: 9_800, LEO: 9_800}
    assert said(maya_actions.outbox) == [
        "got it: Kayaks, $196, paid by Maya. split between Maya and Leo, $98 each."
    ]


def test_each_person_pays_for_their_own_items_plus_their_part_of_tax_and_tip(
    trio_actions, store
):
    priya_actions = trio_actions(PRIYA)
    priya_actions.log_sender_expense(
        ExpenseDraft(
            6_000,
            "Casa Brisa",
            items=(
                ItemDraft("Steak", 4_000, ("Maya",)),
                ItemDraft("Salad", 1_000, ("Leo",)),
            ),
        )
    )

    [expense] = store.get_trip(SPACE).expenses
    assert expense.shares == {MAYA: 4_800, LEO: 1_200}
    assert "Steak $40 (Maya)" in said(priya_actions.outbox)[0]


def test_an_item_with_no_names_is_split_among_the_expenses_group(trio_actions, store):
    maya_actions = trio_actions(MAYA)

    maya_actions.log_sender_expense(
        ExpenseDraft(
            3_000,
            "Pizza",
            split_among=("Maya", "Leo"),
            items=(ItemDraft("Pizza", 3_000),),
        )
    )

    assert store.get_trip(SPACE).expenses[0].shares == {MAYA: 1_500, LEO: 1_500}


def test_a_cost_only_the_payer_shared_is_not_logged(trio_actions, store):
    maya_actions = trio_actions(MAYA)

    with pytest.raises(TripActionError, match="nothing to split"):
        maya_actions.log_sender_expense(
            ExpenseDraft(2_000, "Souvenir", split_among=("Maya",))
        )
    assert store.get_trip(SPACE).expenses == []


def test_an_unknown_name_stops_the_expense_from_being_logged(trio_actions, store):
    maya_actions = trio_actions(MAYA)

    with pytest.raises(TripActionError, match="no single member is called 'Sam'"):
        maya_actions.log_sender_expense(
            ExpenseDraft(2_000, "Taxi", split_among=("Leo", "Sam"))
        )
    assert store.get_trip(SPACE).expenses == []


def test_the_expense_report_needs_no_destination_photo(trio_actions):
    maya_actions = trio_actions(MAYA)
    maya_actions.log_sender_expense(
        ExpenseDraft(19_600, "Kayaks", split_among=("Maya", "Leo"))
    )
    maya_actions.outbox.clear()

    maya_actions.post_expense_report()

    summary, ledger = maya_actions.outbox
    assert "$196 across 1 expense" in summary.fallback_text
    assert "Maya: paid $196, owes $98 · is owed $98" in summary.fallback_text
    assert "Priya: paid $0, owes $0 · even" in summary.fallback_text
    assert "Leo → Maya $98" in summary.fallback_text
    assert "#1 Kayaks · $196 · paid by Maya" in ledger.fallback_text


def test_the_expense_report_bubble_shows_money_not_the_destination(trio_actions):
    maya_actions = trio_actions(MAYA)
    maya_actions.log_sender_expense(ExpenseDraft(19_600, "Kayaks"))
    maya_actions.outbox.clear()

    maya_actions.post_expense_report()

    assert all(
        card.thumbnail_url == EXPENSES_THUMBNAIL_URL for card in maya_actions.outbox
    )


def test_the_expense_summary_leads_with_the_total(trio_actions):
    maya_actions = trio_actions(MAYA)
    maya_actions.log_sender_expense(ExpenseDraft(19_600, "Kayaks"))
    maya_actions.outbox.clear()

    maya_actions.post_expense_report()

    summary, _ = maya_actions.outbox
    total, *_ = summary.layout["root"]["children"]
    assert [t["text"] for t in total["children"]] == [
        "$196",
        "spent across 1 expense",
    ]


def photo_actions(store, phone=MAYA):
    store.lock_in_destination(
        SPACE, "San Juan", DateWindow(date(2027, 3, 14), date(2027, 3, 19))
    )
    return TripActions(
        store, SPACE, phone, OutsideServices(places=FakeBrochurePhotos())
    )


def test_the_expense_report_is_a_summary_card_then_a_ledger_card(trio_actions, store):
    trio_actions(MAYA).log_sender_expense(
        ExpenseDraft(19_600, "Kayaks", split_among=("Maya", "Leo"))
    )
    actions = photo_actions(store)

    actions.post_expense_report()

    summary, ledger = actions.outbox
    assert [summary.caption, ledger.caption] == ["Trip expenses", "Every expense"]
    assert "Leo → Maya $98" in summary.fallback_text
    assert "#1 Kayaks · $196 · paid by Maya" in ledger.fallback_text


def test_a_long_trip_spreads_its_expenses_over_several_cards(trio_actions, store):
    maya_actions = trio_actions(MAYA)
    for number in range(60):
        maya_actions.log_sender_expense(
            ExpenseDraft(1_000 + number, f"Expense number {number}")
        )
    actions = photo_actions(store)

    actions.post_expense_report()

    summary, *ledgers = actions.outbox
    assert len(ledgers) > 1
    assert ledgers[0].caption == f"Every expense (1 of {len(ledgers)})"
    assert all(fits_in_one_message(card.layout) for card in actions.outbox)
    listed = "\n".join(card.fallback_text for card in ledgers)
    assert all(f"Expense number {n} " in listed for n in range(60))


def test_the_expense_report_needs_an_expense(trio_actions):
    with pytest.raises(TripActionError, match="nobody has logged"):
        trio_actions(MAYA).post_expense_report()
