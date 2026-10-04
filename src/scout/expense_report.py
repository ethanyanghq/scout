"""How a trip's spending reads: each expense and its split, who paid what,
and who still owes whom. The end-of-trip document (CS-5).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from scout.money import format_usd
from scout.settle_up import plan_payments
from scout.trip import Expense, ExpenseItem, Member, Trip


@dataclass(frozen=True)
class MemberTotals:
    member: Member
    # What they paid out of pocket for the trip.
    paid_cents: int
    # What they owe toward everything the group bought, whoever paid.
    share_cents: int

    @property
    def net_cents(self) -> int:
        """Positive means the group owes them, before any payments back."""
        return self.paid_cents - self.share_cents


def format_expense_summary(trip: Trip) -> str:
    """The report without its ledger, for the card that only summarizes."""
    return "\n\n".join(
        [
            _describe_totals(trip),
            _describe_who_paid_what(trip),
            _describe_settle_up(trip),
        ]
    )


def format_expense_ledger(trip: Trip, expenses: tuple[Expense, ...]) -> str:
    return _describe_ledger(trip, expenses)


def member_totals(trip: Trip) -> list[MemberTotals]:
    return [
        MemberTotals(
            member,
            paid_cents=sum(
                e.amount_cents for e in trip.expenses if e.payer_phone == member.phone
            ),
            share_cents=sum(e.shares.get(member.phone, 0) for e in trip.expenses),
        )
        for member in trip.members
    ]


def describe_split(expense: Expense, members: list[Member]) -> str:
    """Who it was split among, and what each of them owes."""
    owing = [
        (m.label, expense.shares[m.phone]) for m in members if m.phone in expense.shares
    ]
    cents = [owed for _, owed in owing]
    if max(cents) - min(cents) > 1:
        return "split: " + ", ".join(f"{label} {format_usd(c)}" for label, c in owing)
    each = format_usd(min(cents))
    if not expense.items and len(owing) == len(members):
        return f"split {len(members)} ways"
    approximately = "" if max(cents) == min(cents) else "about "
    labels = _join_names([label for label, _ in owing])
    return f"split between {labels}, {approximately}{each} each"


def describe_items(expense: Expense, members: list[Member]) -> str | None:
    """The receipt's lines and who had each, or None if it wasn't itemized."""
    if not expense.items:
        return None
    labels = {member.phone: member.label for member in members}
    parts = [_describe_item(item, labels) for item in expense.items]
    unlisted_cents = expense.amount_cents - sum(i.amount_cents for i in expense.items)
    if unlisted_cents > 0:
        parts.append(f"tax, tip and fees {format_usd(unlisted_cents)}")
    elif unlisted_cents < 0:
        parts.append(f"discount -{format_usd(-unlisted_cents)}")
    return " · ".join(parts)


def _describe_item(item: ExpenseItem, labels: dict[str, str]) -> str:
    sharers = ", ".join(labels[phone] for phone in item.shared_by)
    return f"{item.name} {format_usd(item.amount_cents)} ({sharers})"


def _describe_totals(trip: Trip) -> str:
    total_cents = sum(expense.amount_cents for expense in trip.expenses)
    noun = "expense" if len(trip.expenses) == 1 else "expenses"
    heading = "trip expenses" + (f" · {trip.destination}" if trip.destination else "")
    return f"{heading}\n{format_usd(total_cents)} across {len(trip.expenses)} {noun}"


def _describe_who_paid_what(trip: Trip) -> str:
    lines = ["who paid what:"]
    for totals in member_totals(trip):
        lines.append(
            f"{totals.member.label}: paid {format_usd(totals.paid_cents)}, "
            f"owes {format_usd(totals.share_cents)} · {_describe_net(totals.net_cents)}"
        )
    return "\n".join(lines)


def _describe_net(net_cents: int) -> str:
    if net_cents > 0:
        return f"is owed {format_usd(net_cents)}"
    if net_cents < 0:
        return f"owes {format_usd(-net_cents)} more"
    return "even"


def _describe_ledger(trip: Trip, expenses: Iterable[Expense]) -> str:
    lines = ["every expense:"]
    for expense in expenses:
        payer = trip.find_member(expense.payer_phone)
        when = (
            f" · {expense.paid_on:%b} {expense.paid_on.day}" if expense.paid_on else ""
        )
        lines.append(
            f"#{expense.id} {expense.description} · {format_usd(expense.amount_cents)}"
            f" · paid by {payer.label}{when}"
        )
        lines.append(f"   {describe_split(expense, trip.members)}")
        items = describe_items(expense, trip.members)
        if items:
            lines.append(f"   {items}")
    return "\n".join(lines)


def _describe_settle_up(trip: Trip) -> str:
    payments = plan_payments(trip)
    lines = ["to settle up:"]
    if payments:
        lines.extend(
            f"{p.payer.label} → {p.payee.label} {format_usd(p.amount_cents)}"
            for p in payments
        )
    else:
        lines.append("everyone's settled up 🎉")
    if trip.settlements:
        lines.append("already paid back:")
        lines.extend(
            f"{trip.find_member(s.payer_phone).label} → "
            f"{trip.find_member(s.payee_phone).label} {format_usd(s.amount_cents)}"
            for s in trip.settlements
        )
    return "\n".join(lines)


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
