from datetime import date

import pytest

from scout.nessie import NessieError, SandboxPayment
from scout.trip import DateWindow, DestinationOption, ItineraryDay, PreferenceUpdate
from scout.trip_actions import TripActionError, TripActions

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
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
    status = maya_actions.save_sender_preferences(
        PreferenceUpdate(display_name="Maya", budget_usd=800)
    )

    assert "Maya is still missing: dates, home city" in status
    assert "waiting on: Maya, …0002" in status


def test_rejects_dates_that_end_before_they_start(maya_actions):
    with pytest.raises(TripActionError):
        maya_actions.save_sender_preferences(
            PreferenceUpdate(
                available_from=date(2027, 3, 20), available_to=date(2027, 3, 13)
            )
        )


def test_starting_a_poll_posts_it_to_the_chat(maya_actions):
    maya_actions.start_destination_poll(OPTIONS)

    assert maya_actions.outbox[0].startswith("🗳️ Where should we go?")


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

    winner, calendar = closing.outbox
    assert winner.startswith("🎉 Poll closed! San Juan, Puerto Rico wins")
    assert calendar.startswith("📅 Locked in: San Juan, Puerto Rico, Mar 14–19.")
    assert "calendar.google.com" in calendar


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
    assert len(closing.outbox) == 1


def test_itinerary_is_posted_in_date_order(locked_in_actions):
    locked_in_actions.post_itinerary(
        [plan_day(15, "Beach day in Condado"), plan_day(14, "Land and check in")]
    )

    assert locked_in_actions.outbox == [
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

    lines = locked_in_actions.outbox[0].split("\n")
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

    assert leo_actions.outbox == ["Got it: Airbnb, $1,240, paid by Leo. Split 2 ways."]
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
    assert maya_actions.outbox[-1] == "Removed: Bio bay kayaks, $196."


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

    assert maya_actions.outbox[-1] == (
        "💸 Shared costs: $100, so $50 each. Fewest payments to settle up:\n"
        "…0002 → …0001 $50\n"
        'To pay, text "@scout pay …0001".'
    )


def test_no_settle_up_before_anyone_logs_an_expense(maya_actions):
    with pytest.raises(TripActionError, match="nobody has logged an expense"):
        maya_actions.post_settle_up()


class FakeBank:
    """Stands in for Nessie: opens numbered accounts and records each payment."""

    def __init__(self, is_down=False):
        self.is_down = is_down
        self.accounts_opened = 0
        self.payments = []

    def open_account(self):
        self._fail_if_down()
        self.accounts_opened += 1
        return f"account-{self.accounts_opened}"

    def move_money(self, from_account_id, to_account_id, amount_cents):
        self._fail_if_down()
        self.payments.append((from_account_id, to_account_id, amount_cents))
        return SandboxPayment("withdrawal-1", "deposit-1")

    def _fail_if_down(self):
        if self.is_down:
            raise NessieError("POST /customers didn't connect: timed out")


def maya_owes_leo_50(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, LEO_PREFERENCES)
    store.add_expense(SPACE, LEO, 10_000, "Groceries")


def test_paying_moves_sandbox_money_and_confirms_in_the_chat(store):
    maya_owes_leo_50(store)
    bank = FakeBank()
    maya_actions = TripActions(store, SPACE, MAYA, bank)

    maya_actions.pay_from_sender("Leo")

    assert bank.payments == [("account-1", "account-2", 5_000)]
    assert maya_actions.outbox == [
        "Paid ✓ Maya → Leo $50 through Capital One's Nessie sandbox "
        "(not real money)\nEveryone's settled up 🎉"
    ]
    [settlement] = store.get_trip(SPACE).settlements
    assert settlement.went_through_nessie


def test_each_member_gets_one_nessie_account_that_is_reused(store):
    maya_owes_leo_50(store)
    store.add_expense(SPACE, LEO, 2_000, "Ice")
    bank = FakeBank()
    TripActions(store, SPACE, MAYA, bank).pay_from_sender("Leo")
    store.add_expense(SPACE, LEO, 2_000, "Ice")

    TripActions(store, SPACE, MAYA, bank).pay_from_sender("Leo")

    assert bank.accounts_opened == 2
    assert [payment[:2] for payment in bank.payments] == [
        ("account-1", "account-2"),
        ("account-1", "account-2"),
    ]
    maya = store.get_trip(SPACE).find_member(MAYA)
    assert maya.nessie_account_id == "account-1"


def test_payments_are_simulated_when_no_sandbox_bank_is_set_up(store):
    maya_owes_leo_50(store)
    maya_actions = TripActions(store, SPACE, MAYA)

    maya_actions.pay_from_sender("Leo")

    assert maya_actions.outbox[0].startswith(
        "Paid ✓ Maya → Leo $50 (simulated: no money moved in the Capital One sandbox)"
    )
    [settlement] = store.get_trip(SPACE).settlements
    assert not settlement.went_through_nessie


def test_the_group_can_still_settle_up_when_nessie_is_down(store):
    maya_owes_leo_50(store)
    maya_actions = TripActions(store, SPACE, MAYA, FakeBank(is_down=True))

    maya_actions.pay_from_sender("Leo")

    assert "(simulated" in maya_actions.outbox[0]
    assert len(store.get_trip(SPACE).settlements) == 1


def test_payee_names_match_however_they_are_capitalized(store):
    maya_owes_leo_50(store)

    TripActions(store, SPACE, MAYA, FakeBank()).pay_from_sender(" leo ")

    assert len(store.get_trip(SPACE).settlements) == 1


def test_nobody_can_pay_someone_they_do_not_owe(store):
    maya_owes_leo_50(store)
    leo_actions = TripActions(store, SPACE, LEO, FakeBank())

    with pytest.raises(TripActionError, match="Leo doesn't owe Maya anything"):
        leo_actions.pay_from_sender("Maya")
    assert store.get_trip(SPACE).settlements == []


def test_a_refused_payment_says_who_the_sender_does_owe(store):
    maya_owes_leo_50(store)

    with pytest.raises(TripActionError, match="They owe: Leo"):
        TripActions(store, SPACE, MAYA, FakeBank()).pay_from_sender("Jordan")
