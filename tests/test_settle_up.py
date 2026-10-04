from scout.expense_split import split_evenly
from scout.settle_up import plan_payments
from scout.trip import Expense, Member, Settlement, Trip, TripStage

MAYA = Member("+15550000001", "Maya")
LEO = Member("+15550000002", "Leo")
JORDAN = Member("+15550000003", "Jordan")
PRIYA = Member("+15550000004", "Priya")


def trip_with(members, *expenses):
    return Trip(
        space_id="group-chat-1",
        stage=TripStage.DESTINATION_CHOSEN,
        destination="San Juan, Puerto Rico",
        dates=None,
        members=list(members),
        open_poll=None,
        itinerary=[],
        itinerary_add_ons=[],
        activity_deck=None,
        expenses=[
            Expense(
                payer.phone,
                cents,
                description,
                shares=split_evenly(cents, [m.phone for m in members]),
                id=number,
            )
            for number, (payer, cents, description) in enumerate(expenses, start=1)
        ],
        settlements=[],
        pending_receipt=None,
        place_suggestions=[],
    )


def spring_break_trip():
    """The PRD's sample journey: $1,600 of shared costs split four ways."""
    return trip_with(
        [MAYA, LEO, JORDAN, PRIYA],
        (LEO, 124_000, "Airbnb"),
        (PRIYA, 16_400, "Casa Brisa dinner"),
        (MAYA, 19_600, "Bio bay kayaks"),
    )


def summarize(payments):
    return [(p.payer.label, p.payee.label, p.amount_cents) for p in payments]


def test_whoever_owes_most_pays_whoever_is_owed_most_first():
    payments = plan_payments(spring_break_trip())

    assert summarize(payments) == [
        ("Jordan", "Leo", 40_000),
        ("Priya", "Leo", 23_600),
        ("Maya", "Leo", 20_400),
    ]


def test_settling_up_takes_at_most_one_payment_fewer_than_the_group_size():
    trip = trip_with(
        [MAYA, LEO, JORDAN, PRIYA],
        (MAYA, 30_000, "Car"),
        (LEO, 10_000, "Gas"),
        (JORDAN, 5_000, "Snacks"),
    )

    payments = plan_payments(trip)

    assert len(payments) <= 3
    assert sum(p.amount_cents for p in payments if p.payee == MAYA) == 18_750


def test_leftover_cents_are_shared_so_nothing_is_lost():
    trip = trip_with([MAYA, LEO, JORDAN], (MAYA, 10_000, "Groceries"))

    payments = plan_payments(trip)

    # $100 splits into $33.34 + $33.33 + $33.33. Maya covers the extra cent.
    assert summarize(payments) == [("Leo", "Maya", 3_333), ("Jordan", "Maya", 3_333)]


def test_nobody_pays_when_everyone_spent_the_same():
    trip = trip_with([MAYA, LEO], (MAYA, 5_000, "Lunch"), (LEO, 5_000, "Dinner"))

    assert plan_payments(trip) == []


def paid(trip, payer, payee, cents):
    trip.settlements.append(Settlement(payer.phone, payee.phone, cents))
    return trip


def test_payments_already_made_drop_out_of_the_plan():
    trip = paid(spring_break_trip(), MAYA, LEO, 20_400)

    assert summarize(plan_payments(trip)) == [
        ("Jordan", "Leo", 40_000),
        ("Priya", "Leo", 23_600),
    ]


def test_a_cost_only_some_people_shared_is_owed_only_by_them():
    trip = trip_with([MAYA, LEO, JORDAN, PRIYA])
    kayaks = split_evenly(19_600, [MAYA.phone, LEO.phone])
    trip.expenses.append(
        Expense(MAYA.phone, 19_600, "Kayaks", shares=kayaks_by_phone(kayaks), id=1)
    )

    # Jordan and Priya weren't on the kayaks, so they owe nothing.
    assert summarize(plan_payments(trip)) == [("Leo", "Maya", 9_800)]


def kayaks_by_phone(shares):
    return {MAYA.phone: shares[MAYA.phone], LEO.phone: shares[LEO.phone]}
