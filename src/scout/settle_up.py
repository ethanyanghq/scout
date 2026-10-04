"""Who owes whom once the trip's costs are in (CS-2, CS-4)."""

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
    noun = "expense" if len(trip.expenses) == 1 else "expenses"
    lead_in = (
        f"shared costs: {format_usd(total_cents)} across {len(trip.expenses)} {noun}."
    )
    payments = plan_payments(trip)
    if not payments:
        return f"{lead_in} everyone's already even."
    lines = [f"{lead_in} fewest payments to settle up:"]
    lines.extend(_format_payment(payment) for payment in payments)
    payee = payments[0].payee.label
    lines.append(f'once you\'ve paid, text "@scout i paid {payee}".')
    return "\n".join(lines)


def format_payments_left(trip: Trip) -> str:
    """One line on what's still owed, for after someone pays."""
    payments = plan_payments(trip)
    if not payments:
        return "everyone's settled up 🎉"
    count = "1 payment" if len(payments) == 1 else f"{len(payments)} payments"
    return f"{count} left: {', '.join(_format_payment(p) for p in payments)}"


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
    """What each member paid minus what they owe, after settlements, in cents.

    Positive means the group owes them.
    """
    balances = {member.phone: 0 for member in trip.members}
    for expense in trip.expenses:
        balances[expense.payer_phone] += expense.amount_cents
        for phone, share_cents in expense.shares.items():
            balances[phone] -= share_cents
    for settlement in trip.settlements:
        balances[settlement.payer_phone] += settlement.amount_cents
        balances[settlement.payee_phone] -= settlement.amount_cents
    return balances


def _format_payment(payment: Payment) -> str:
    return (
        f"{payment.payer.label} → {payment.payee.label} "
        f"{format_usd(payment.amount_cents)}"
    )
