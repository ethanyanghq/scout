from datetime import date, datetime

from scout.nessie import SandboxPayment
from scout.places import Coordinates, Place
from scout.trip import (
    DateWindow,
    DestinationOption,
    Expense,
    PendingReceipt,
    PreferenceUpdate,
    Settlement,
    TripStage,
)

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


def test_closing_a_poll_sets_the_destination_and_dates(store):
    store.create_trip(SPACE)
    store.open_poll(SPACE, OPTIONS)
    poll_id = store.get_trip(SPACE).open_poll.id
    dates = DateWindow(date(2027, 3, 14), date(2027, 3, 19))

    store.close_poll(poll_id, "Tulum, Mexico", dates)

    trip = store.get_trip(SPACE)
    assert trip.stage == TripStage.DESTINATION_CHOSEN
    assert trip.destination == "Tulum, Mexico"
    assert trip.dates == dates
    assert trip.open_poll is None


def test_a_trip_closed_without_shared_dates_has_no_dates(store):
    store.create_trip(SPACE)
    store.open_poll(SPACE, OPTIONS)
    poll_id = store.get_trip(SPACE).open_poll.id

    store.close_poll(poll_id, "Tulum, Mexico", None)

    assert store.get_trip(SPACE).dates is None


def test_recent_messages_come_back_oldest_first_and_limited(store):
    store.create_trip(SPACE)
    for minute in range(5):
        store.log_message(
            SPACE, MAYA, f"message {minute}", datetime(2026, 10, 2, 9, minute)
        )

    recent = store.recent_messages(SPACE, limit=2)

    assert [m.text for m in recent] == ["message 3", "message 4"]


def test_expenses_come_back_in_the_order_they_were_logged(store):
    store.create_trip(SPACE)

    airbnb = store.add_expense(SPACE, LEO, 124_000, "Airbnb")
    kayaks = store.add_expense(SPACE, MAYA, 19_600, "Bio bay kayaks")

    assert store.get_trip(SPACE).expenses == [
        Expense(airbnb, LEO, 124_000, "Airbnb"),
        Expense(kayaks, MAYA, 19_600, "Bio bay kayaks"),
    ]


def test_removing_an_expense_keeps_the_others(store):
    store.create_trip(SPACE)
    airbnb = store.add_expense(SPACE, LEO, 124_000, "Airbnb")
    kayaks = store.add_expense(SPACE, MAYA, 19_600, "Bio bay kayaks")

    store.remove_expense(SPACE, airbnb)

    assert [e.id for e in store.get_trip(SPACE).expenses] == [kayaks]


def test_settlements_remember_whether_sandbox_money_moved(store):
    store.create_trip(SPACE)
    through_nessie = Settlement(MAYA, LEO, 5_000, went_through_nessie=True)
    simulated = Settlement(MAYA, LEO, 1_000, went_through_nessie=False)

    store.add_settlement(SPACE, through_nessie, SandboxPayment("w-1", "d-1"))
    store.add_settlement(SPACE, simulated, None)

    assert store.get_trip(SPACE).settlements == [through_nessie, simulated]


def test_a_members_nessie_account_is_saved(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])

    store.save_nessie_account(SPACE, MAYA, "account-1")

    assert store.get_trip(SPACE).find_member(MAYA).nessie_account_id == "account-1"


def test_a_newer_receipt_replaces_the_one_waiting(store):
    store.create_trip(SPACE)
    store.save_pending_receipt(SPACE, PendingReceipt(MAYA, "Casa Brisa", 16_400))

    store.save_pending_receipt(SPACE, PendingReceipt(LEO, "Bodega", 1_250))

    assert store.get_trip(SPACE).pending_receipt == PendingReceipt(LEO, "Bodega", 1_250)


def test_a_cleared_receipt_is_gone(store):
    store.create_trip(SPACE)
    store.save_pending_receipt(SPACE, PendingReceipt(MAYA, "Casa Brisa", 16_400))

    store.clear_pending_receipt(SPACE)

    assert store.get_trip(SPACE).pending_receipt is None


def test_new_place_suggestions_replace_the_old_ones_in_order(store):
    store.create_trip(SPACE)
    tacos = Place("place-1", "Lote 23", Coordinates(18.45, -66.07), "$$", "Food park.")
    bar = Place("place-2", "La Factoría", Coordinates(18.46, -66.11), None, None)
    beach = Place("place-3", "Playa", Coordinates(18.46, -66.08), "free", None)
    store.replace_place_suggestions(SPACE, [tacos])

    store.replace_place_suggestions(SPACE, [bar, beach])

    assert store.get_trip(SPACE).place_suggestions == [bar, beach]
