from scout.money import format_usd


def test_whole_dollars_have_no_cents():
    assert format_usd(124_000) == "$1,240"


def test_partial_dollars_show_both_cent_digits():
    assert format_usd(23_650) == "$236.50"
    assert format_usd(5) == "$0.05"
