from datetime import date, datetime

from scout.trip import DestinationOption, PreferenceUpdate, TripStage

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport"),
    DestinationOption("Miami, Florida", 800, "Easy flights"),
]


def test_new_trip_starts_by_collecting_preferences(store):
    store.create_trip(SPACE)

    trip = store.get_trip(SPACE)

    assert trip.stage == TripStage.COLLECTING_PREFERENCES
    assert trip.members == []
    assert trip.open_poll is None


def test_unknown_chat_has_no_trip(store):
    assert store.get_trip("never-seen") is None


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


def test_closing_a_poll_sets_the_destination(store):
    store.create_trip(SPACE)
    store.open_poll(SPACE, OPTIONS)
    poll_id = store.get_trip(SPACE).open_poll.id

    store.close_poll(poll_id, "Tulum, Mexico")

    trip = store.get_trip(SPACE)
    assert trip.stage == TripStage.DESTINATION_CHOSEN
    assert trip.destination == "Tulum, Mexico"
    assert trip.open_poll is None


def test_recent_messages_come_back_oldest_first_and_limited(store):
    store.create_trip(SPACE)
    for minute in range(5):
        store.log_message(
            SPACE, MAYA, f"message {minute}", datetime(2026, 10, 2, 9, minute)
        )

    recent = store.recent_messages(SPACE, limit=2)

    assert [m.text for m in recent] == ["message 3", "message 4"]
