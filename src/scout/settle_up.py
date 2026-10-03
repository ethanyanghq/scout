"""Who owes whom once the trip's shared costs are in (CS-2)."""

from dataclasses import dataclass

from scout.money import format_usd
from scout.trip import Member, Trip


@dataclass(frozen=True)
class Payment:
    """One payment scout suggests so the group ends up even."""

    payer: Member
    payee: Member
    amount_cents: int


def format_settle_up(trip: Trip) -> str:
    """Expects a trip with at least one expense."""
    total_cents = sum(expense.amount_cents for expense in trip.expenses)
    share = _describe_share(total_cents, len(trip.members))
    payments = plan_payments(trip)
    lead_in = f"💸 Shared costs: {format_usd(total_cents)}, so {share} each."
    if not payments:
        return f"{lead_in} Everyone's already even."
    lines = [f"{lead_in} Fewest payments to settle up:"]
    lines.extend(_format_payment(payment) for payment in payments)
    return "\n".join(lines)


def plan_payments(trip: Trip) -> list[Payment]:
    """The fewest payments that bring everyone's balance to zero.

    Repeatedly matches whoever owes the most with whoever is owed the most.
    That takes at most one payment fewer than the number of members (PRD §10).
    """
    balances = _net_balances(trip)
    payments = []
    while True:
        # On ties, min and max pick the earliest member, so plans are stable.
        debtor = min(balances, key=balances.get)
        creditor = max(balances, key=balances.get)
        # Balances always sum to zero, so nobody owing means everyone's even.
        if balances[debtor] >= 0:
            return payments
        amount = min(-balances[debtor], balances[creditor])
        payments.append(
            Payment(trip.find_member(debtor), trip.find_member(creditor), amount)
        )
        balances[debtor] += amount
        balances[creditor] -= amount


def _net_balances(trip: Trip) -> dict[str, int]:
    """What each member paid minus their share, in cents. Positive means owed."""
    total_cents = sum(expense.amount_cents for expense in trip.expenses)
    base_share, leftover_cents = divmod(total_cents, len(trip.members))
    balances = {}
    for position, member in enumerate(trip.members):
        # The first few members cover the leftover cents, a cent each, so the
        # shares add up to exactly the total.
        share = base_share + (1 if position < leftover_cents else 0)
        balances[member.phone] = -share
    for expense in trip.expenses:
        balances[expense.payer_phone] += expense.amount_cents
    return balances


def _describe_share(total_cents: int, member_count: int) -> str:
    base_share, leftover_cents = divmod(total_cents, member_count)
    if leftover_cents == 0:
        return format_usd(base_share)
    return f"about {format_usd(base_share)}"


def _format_payment(payment: Payment) -> str:
    return (
        f"{payment.payer.label} → {payment.payee.label} "
        f"{format_usd(payment.amount_cents)}"
    )
