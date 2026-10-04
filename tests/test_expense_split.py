import pytest

from scout.expense_split import split_by_items, split_evenly
from scout.trip import ExpenseItem

MAYA = "+15550000001"
LEO = "+15550000002"
JORDAN = "+15550000003"
PRIYA = "+15550000004"


def test_an_even_split_covers_every_cent():
    shares = split_evenly(10_000, [MAYA, LEO, JORDAN])

    # The extra cent goes to whoever is listed first.
    assert shares == {MAYA: 3_334, LEO: 3_333, JORDAN: 3_333}


def test_only_the_people_named_pay_for_something_a_few_shared():
    shares = split_evenly(19_600, [MAYA, LEO])

    assert shares == {MAYA: 9_800, LEO: 9_800}


def test_each_item_splits_among_only_the_people_who_shared_it():
    items = [
        ExpenseItem("Steak", 4_000, (MAYA,)),
        ExpenseItem("Nachos", 1_200, (MAYA, LEO)),
        ExpenseItem("Salad", 1_800, (LEO,)),
    ]

    shares = split_by_items(items, amount_cents=7_000)

    assert shares == {MAYA: 4_600, LEO: 2_400}


def test_tax_and_tip_follow_what_each_person_had():
    items = [
        ExpenseItem("Steak", 4_000, (MAYA,)),
        ExpenseItem("Salad", 1_000, (LEO,)),
    ]

    # $50 of food, plus $10 of tax and tip: Maya had 80% of the food.
    shares = split_by_items(items, amount_cents=6_000)

    assert shares == {MAYA: 4_800, LEO: 1_200}


def test_someone_who_had_nothing_owes_nothing_even_for_tax_and_tip():
    items = [ExpenseItem("Pizza", 2_000, (MAYA, LEO))]

    shares = split_by_items(items, amount_cents=2_400)

    assert PRIYA not in shares
    assert shares == {MAYA: 1_200, LEO: 1_200}


def test_a_discount_comes_off_in_proportion_too():
    items = [
        ExpenseItem("Kayak", 6_000, (MAYA,)),
        ExpenseItem("Kayak", 4_000, (LEO,)),
    ]

    shares = split_by_items(items, amount_cents=9_000)

    assert shares == {MAYA: 5_400, LEO: 3_600}


@pytest.mark.parametrize("amount_cents", [1, 7, 100, 1_001, 12_345])
def test_odd_amounts_never_lose_a_cent(amount_cents):
    people = [MAYA, LEO, JORDAN, PRIYA]
    items = [
        ExpenseItem("A", amount_cents, (MAYA, LEO, JORDAN)),
        ExpenseItem("B", amount_cents, (JORDAN, PRIYA)),
    ]

    assert sum(split_evenly(amount_cents, people).values()) == amount_cents
    extras = 37
    shares = split_by_items(items, amount_cents=2 * amount_cents + extras)
    assert sum(shares.values()) == 2 * amount_cents + extras
