import sqlite3
from datetime import date, time

from scout.trip import (
    DeckActivity,
    DestinationOption,
    ItineraryDay,
    PreferenceUpdate,
    Rating,
)
from scout.trip_store import TripStore

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport"),
    DestinationOption("Miami, Florida", 800, "Easy flights"),
]


def test_adding_a_member_twice_keeps_one_copy(store):
    store.create_trip(SPACE)

    store.add_members(SPACE, [MAYA, LEO])
    store.add_members(SPACE, [MAYA])

    assert [m.phone for m in store.get_trip(SPACE).members] == [MAYA, LEO]


def test_later_updates_keep_earlier_preferences(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])

    store.save_preferences(
        SPACE,
        MAYA,
        PreferenceUpdate(
            display_name="Maya",
            available_from=date(2027, 3, 13),
            available_to=date(2027, 3, 20),
        ),
    )
    store.save_preferences(
        SPACE, MAYA, PreferenceUpdate(budget_usd=800, must_haves=["beach"])
    )

    maya = store.get_trip(SPACE).find_member(MAYA)
    assert maya.display_name == "Maya"
    assert maya.available_from == date(2027, 3, 13)
    assert maya.budget_usd == 800
    assert maya.must_haves == ["beach"]


def test_changing_a_vote_replaces_the_old_one(store):
    store.create_trip(SPACE)
    store.open_poll(SPACE, OPTIONS)
    poll_id = store.get_trip(SPACE).open_poll.id

    store.record_vote(poll_id, MAYA, 0)
    store.record_vote(poll_id, MAYA, 2)

    assert store.get_trip(SPACE).open_poll.votes == {MAYA: 2}


def test_deleting_a_trip_leaves_other_chats_alone(store):
    store.create_trip(SPACE)
    store.create_trip("other-chat")
    store.add_members("other-chat", [MAYA])

    store.delete_trip(SPACE)

    assert store.get_trip(SPACE) is None
    assert [member.phone for member in store.get_trip("other-chat").members] == [MAYA]


def test_a_database_from_before_chronotypes_and_start_times_still_opens(tmp_path):
    path = tmp_path / "scout.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE members (
                space_id TEXT NOT NULL, phone TEXT NOT NULL, display_name TEXT,
                available_from TEXT, available_to TEXT, budget_usd INTEGER,
                home_city TEXT, must_haves TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (space_id, phone)
            );
            CREATE TABLE itinerary_days (
                space_id TEXT NOT NULL, day TEXT NOT NULL, plan TEXT NOT NULL,
                PRIMARY KEY (space_id, day)
            );
            """
        )
    db.close()

    store = TripStore(path)
    store.create_trip("chat-1")
    store.add_members("chat-1", ["+15550000001"])
    store.replace_itinerary(
        "chat-1", [ItineraryDay(date(2027, 3, 14), "Snorkel", time(9, 0))], []
    )

    trip = store.get_trip("chat-1")
    assert trip.members[0].chronotype is None
    assert trip.itinerary[0].starts_at == time(9, 0)


def test_scout_never_counts_a_missing_name_as_something_to_ask_for(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])
    store.save_preferences(
        SPACE,
        MAYA,
        PreferenceUpdate(
            available_from=date(2027, 3, 13),
            available_to=date(2027, 3, 20),
            budget_usd=1200,
            home_city="Boston",
        ),
    )

    [maya] = store.get_trip(SPACE).members
    assert maya.display_name is None
    assert maya.missing_preferences == []


def test_an_expense_saved_before_shares_were_kept_is_split_evenly(store):
    store.create_trip("chat")
    store.add_members("chat", ["+15550000001", "+15550000002"])
    with store._transaction() as db:
        db.execute(
            "INSERT INTO expenses (space_id, payer_phone, amount_cents, description) "
            "VALUES ('chat', '+15550000001', 10_001, 'Groceries')"
        )

    [expense] = store.get_trip("chat").expenses

    assert expense.shares == {"+15550000001": 5_001, "+15550000002": 5_000}


def test_activity_ratings_survive_a_reload(store):
    store.create_trip(SPACE)
    store.replace_activity_deck(SPACE, [DeckActivity("Kayak", "", 60)] * 3)

    store.save_activity_picks(SPACE, MAYA, {0: Rating.YEAH, 2: Rating.MEH})

    assert store.get_trip(SPACE).activity_deck.picks == {
        MAYA: {0: Rating.YEAH, 2: Rating.MEH}
    }


def test_picks_saved_before_swiping_count_as_yeahs(store):
    store.create_trip(SPACE)
    store.replace_activity_deck(SPACE, [DeckActivity("Kayak", "", 60)] * 3)
    with store._transaction() as db:
        db.execute(
            "INSERT INTO activity_picks (space_id, phone, positions) VALUES (?, ?, ?)",
            (SPACE, MAYA, "[0, 2]"),
        )

    assert store.get_trip(SPACE).activity_deck.picks == {
        MAYA: {0: Rating.YEAH, 2: Rating.YEAH}
    }
