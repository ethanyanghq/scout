import pytest

from scout.polls import decide_winner, format_poll, format_result, parse_vote
from scout.trip import DestinationOption, Poll

TULUM = DestinationOption("Tulum, Mexico", 900, "Beaches and cenotes")
SAN_JUAN = DestinationOption("San Juan, Puerto Rico", 750, "No passport needed")
MIAMI = DestinationOption("Miami, Florida", 800, "Easy flights from everywhere")
OPTIONS = [TULUM, SAN_JUAN, MIAMI]
OPTION_NAMES = [option.name for option in OPTIONS]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2", 1),
        ("2!", 1),
        ("#3", 2),
        ("option 1", 0),
        ("I vote 2", 1),
        ("@scout 2", 1),
        ("tulum", 0),
        ("Tulum!!", 0),
        ("San Juan, Puerto Rico", 1),
    ],
)
def test_reads_votes_by_number_or_name(text, expected):
    assert parse_vote(text, OPTION_NAMES) == expected


@pytest.mark.parametrize(
    "text",
    [
        "tulum looks pricey tbh",
        "4",
        "0",
        "i'm free on the 2nd",
        "lol",
    ],
)
def test_ignores_chatter_and_numbers_that_are_not_options(text):
    assert parse_vote(text, OPTION_NAMES) is None


def test_most_votes_wins():
    poll = Poll(id=1, options=OPTIONS, votes={"maya": 0, "leo": 0, "priya": 1})

    result = decide_winner(poll)

    assert result.winner == TULUM
    assert result.winning_votes == 2
    assert result.tied_with == []


def test_tie_goes_to_the_cheapest_option():
    poll = Poll(id=1, options=OPTIONS, votes={"maya": 0, "leo": 1})

    result = decide_winner(poll)

    assert result.winner == SAN_JUAN
    assert result.tied_with == [TULUM]


def test_no_winner_when_nobody_voted():
    assert decide_winner(Poll(id=1, options=OPTIONS, votes={})) is None


def test_poll_lists_numbered_options_with_estimated_prices():
    text = format_poll(OPTIONS)

    assert "1. Tulum, Mexico (~$900/person est.): Beaches and cenotes" in text
    assert "3. Miami, Florida" in text


def test_tie_announcement_explains_the_cost_tiebreak():
    poll = Poll(id=1, options=OPTIONS, votes={"maya": 0, "leo": 1})

    text = format_result(decide_winner(poll), voter_count=2)

    assert "tie between Tulum, Mexico and San Juan, Puerto Rico" in text
    assert "I'd go with San Juan, Puerto Rico" in text
    assert "~$750/person" in text
