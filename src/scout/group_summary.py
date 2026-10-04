"""Where the group landed: shared dates, budget range, and who's still missing."""

from dataclasses import dataclass

from scout.trip import DateWindow, Member


@dataclass(frozen=True)
class GroupSummary:
    # None until someone shares dates, or when no single day works for everyone.
    shared_window: DateWindow | None
    dates_conflict: bool
    budget_range: tuple[int, int] | None
    home_cities: list[str]
    must_haves: list[str]
    members_still_to_share: list[Member]

    @property
    def is_complete(self) -> bool:
        return not self.members_still_to_share and not self.dates_conflict


def summarize_group(members: list[Member]) -> GroupSummary:
    # Each detail counts from everyone who shared it, so a group that moves on
    # without someone's home city still plans around that person's dates.
    with_dates = [member for member in members if _has_dates(member)]
    shared_window = _find_shared_window(with_dates)
    budgets = [member.budget_usd for member in members if member.budget_usd]
    return GroupSummary(
        shared_window=shared_window,
        dates_conflict=bool(with_dates) and shared_window is None,
        budget_range=(min(budgets), max(budgets)) if budgets else None,
        home_cities=_unique_in_order(
            member.home_city for member in members if member.home_city
        ),
        must_haves=_unique_in_order(
            must_have for member in members for must_have in member.must_haves
        ),
        members_still_to_share=[
            member for member in members if not member.has_shared_preferences
        ],
    )


def format_group_summary(summary: GroupSummary, members: list[Member]) -> str:
    lines = ["Here's where everyone landed:"]
    if summary.shared_window:
        who = (
            "everyone" if all(map(_has_dates, members)) else "everyone who shared dates"
        )
        lines.append(f"📅 {format_window(summary.shared_window)} works for {who}")
    elif summary.dates_conflict:
        lines.append("📅 No dates work for everyone yet:")
        lines.extend(
            f"   {member.label}: {_format_member_dates(member)}"
            for member in members
            if _has_dates(member)
        )
    if summary.budget_range:
        lowest, highest = summary.budget_range
        budget = f"${lowest:,}" if lowest == highest else f"${lowest:,}–${highest:,}"
        lines.append(f"💸 Budget: {budget} per person")
    if summary.home_cities:
        lines.append(f"🏠 Coming from: {', '.join(summary.home_cities)}")
    if summary.must_haves:
        lines.append(f"✨ Must-haves: {', '.join(summary.must_haves)}")
    if summary.members_still_to_share:
        waiting_on = ", ".join(m.label for m in summary.members_still_to_share)
        lines.append(f"⏳ Still waiting on: {waiting_on}")
    return "\n".join(lines)


def format_window(window: DateWindow) -> str:
    """Formats dates the way people text them: "Mar 14–20" or "Mar 28–Apr 3"."""
    start = f"{window.start:%b} {window.start.day}"
    if (window.start.year, window.start.month) == (window.end.year, window.end.month):
        return f"{start}–{window.end.day}"
    return f"{start}–{window.end:%b} {window.end.day}"


def _find_shared_window(members: list[Member]) -> DateWindow | None:
    if not members:
        return None
    latest_start = max(member.available_from for member in members)
    earliest_end = min(member.available_to for member in members)
    if latest_start > earliest_end:
        return None
    return DateWindow(latest_start, earliest_end)


def _has_dates(member: Member) -> bool:
    return member.available_from is not None and member.available_to is not None


def _format_member_dates(member: Member) -> str:
    return format_window(DateWindow(member.available_from, member.available_to))


def _unique_in_order(values) -> list[str]:
    """Drops repeats, ignoring case, keeping the first spelling seen."""
    seen = set()
    unique = []
    for value in values:
        if value.lower() not in seen:
            seen.add(value.lower())
            unique.append(value)
    return unique
