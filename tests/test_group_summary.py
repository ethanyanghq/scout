from datetime import date

from scout.group_summary import (
    DateWindow,
    format_window,
    summarize_group,
)
from scout.trip import Member


def member(name, start, end, budget, city, must_haves=()):
    return Member(
        phone=f"+1555{name}",
        display_name=name,
        available_from=start,
        available_to=end,
        budget_usd=budget,
        home_city=city,
        must_haves=list(must_haves),
    )


def test_finds_the_days_everyone_can_travel():
    members = [
        member("Maya", date(2027, 3, 13), date(2027, 3, 20), 800, "Boston"),
        member("Leo", date(2027, 3, 14), date(2027, 3, 22), 600, "NYC"),
    ]

    summary = summarize_group(members)

    assert summary.shared_window == DateWindow(date(2027, 3, 14), date(2027, 3, 20))
    assert not summary.dates_conflict


def test_flags_a_conflict_when_no_single_day_works():
    members = [
        member("Maya", date(2027, 3, 13), date(2027, 3, 16), 800, "Boston"),
        member("Leo", date(2027, 3, 18), date(2027, 3, 22), 600, "NYC"),
    ]

    summary = summarize_group(members)

    assert summary.shared_window is None
    assert summary.dates_conflict
    assert not summary.is_complete


def test_budget_range_spans_lowest_to_highest():
    members = [
        member("Maya", date(2027, 3, 13), date(2027, 3, 20), 800, "Boston"),
        member("Leo", date(2027, 3, 13), date(2027, 3, 20), 600, "NYC"),
        member("Priya", date(2027, 3, 13), date(2027, 3, 20), 900, "Boston"),
    ]

    summary = summarize_group(members)

    assert summary.budget_range == (600, 900)
    assert summary.home_cities == ["Boston", "NYC"]


def test_lists_members_who_have_not_shared_yet():
    quiet_member = Member(phone="+15550000004", display_name="Jordan")
    members = [
        member("Maya", date(2027, 3, 13), date(2027, 3, 20), 800, "Boston"),
        quiet_member,
    ]

    summary = summarize_group(members)

    assert summary.members_still_to_share == [quiet_member]
    assert not summary.is_complete


def test_nobody_sharing_is_not_a_date_conflict():
    summary = summarize_group([Member(phone="+15550000001")])

    assert summary.shared_window is None
    assert not summary.dates_conflict


def test_must_haves_are_combined_without_repeats():
    members = [
        member("Maya", date(2027, 3, 13), date(2027, 3, 20), 800, "Boston", ["Beach"]),
        member(
            "Leo", date(2027, 3, 13), date(2027, 3, 20), 600, "NYC", ["beach", "food"]
        ),
    ]

    assert summarize_group(members).must_haves == ["Beach", "food"]


def test_formats_windows_the_way_people_text_them():
    assert (
        format_window(DateWindow(date(2027, 3, 14), date(2027, 3, 20))) == "Mar 14–20"
    )
    assert (
        format_window(DateWindow(date(2027, 3, 28), date(2027, 4, 3))) == "Mar 28–Apr 3"
    )
