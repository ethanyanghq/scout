from scout.settle_up import format_settle_up, plan_payments
from scout.trip import Expense, Member, Trip, TripStage

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
        expenses=[
            Expense(number, payer.phone, cents, description)
            for number, (payer, cents, description) in enumerate(expenses, start=1)
        ],
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


def test_settle_up_message_shows_the_total_share_and_payments():
    message = format_settle_up(spring_break_trip())

    assert message == (
        "💸 Shared costs: $1,600, so $400 each. Fewest payments to settle up:\n"
        "Jordan → Leo $400\n"
        "Priya → Leo $236\n"
        "Maya → Leo $204"
    )


def test_uneven_shares_are_described_as_about():
    trip = trip_with([MAYA, LEO, JORDAN], (MAYA, 10_000, "Groceries"))

    assert format_settle_up(trip).startswith(
        "💸 Shared costs: $100, so about $33.33 each."
    )


def test_settle_up_message_says_when_everyone_is_even():
    trip = trip_with([MAYA, LEO], (MAYA, 5_000, "Lunch"), (LEO, 5_000, "Dinner"))

    assert format_settle_up(trip).endswith("Everyone's already even.")
