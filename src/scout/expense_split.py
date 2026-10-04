"""How one expense divides into what each member owes, in whole cents.

Every division adds up to exactly the amount: no cent is lost or invented.
"""

from collections import Counter
from collections.abc import Mapping, Sequence

from scout.trip import ExpenseItem


def split_evenly(amount_cents: int, phones: Sequence[str]) -> dict[str, int]:
    return allocate(amount_cents, {phone: 1 for phone in phones})


def split_by_items(items: Sequence[ExpenseItem], amount_cents: int) -> dict[str, int]:
    """Each item divides evenly among the members who shared it. What the
    items don't add up to (tax, tip, fees, or a discount) divides in
    proportion to what each member's items cost, so someone who skipped the
    steak doesn't pay tax on it.
    """
    owed: Counter[str] = Counter()
    for item in items:
        owed.update(split_evenly(item.amount_cents, item.shared_by))
    unlisted_cents = amount_cents - sum(item.amount_cents for item in items)
    owed.update(allocate(unlisted_cents, owed))
    return dict(owed)


def allocate(total_cents: int, weights: Mapping[str, int]) -> dict[str, int]:
    """Divides `total_cents` in proportion to `weights`, to the cent.

    Everyone gets their rounded-down portion, then the cents left over go to
    whoever lost the most to rounding. Ties go to whoever is listed first.
    A negative total (a discount) divides the same way, as a reduction.
    """
    if total_cents < 0:
        return {key: -cents for key, cents in allocate(-total_cents, weights).items()}
    weight_total = sum(weights.values())
    if weight_total <= 0:
        raise ValueError("there is nobody to divide it among")

    portions = {
        key: total_cents * weight // weight_total for key, weight in weights.items()
    }
    cents_left = total_cents - sum(portions.values())
    lost_to_rounding = sorted(
        weights, key=lambda key: -(total_cents * weights[key] % weight_total)
    )
    for key in lost_to_rounding[:cents_left]:
        portions[key] += 1
    return portions
