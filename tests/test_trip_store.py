from datetime import date

from scout.trip import (
    DestinationOption,
    PreferenceUpdate,
)

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
