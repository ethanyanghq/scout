from scout.activity_deck import format_tally, parse_picks
from scout.trip import ActivityDeck, DeckActivity, Member

ACTIVITY_NAMES = [
    "Night kayak in the bio bay",
    "Old San Juan food tour",
    "El Yunque hike",
]
MAYA = Member("+15550000001", display_name="Maya")
LEO = Member("+15550000002", display_name="Leo")
PRIYA = Member("+15550000003", display_name="Priya")


def test_reads_the_picks_the_card_fills_in_skipping_passes():
    text = "@scout my picks: Night kayak in the bio bay · Pass · El Yunque hike"

    assert parse_picks(text, ACTIVITY_NAMES) == [0, 2]


def test_reads_picks_typed_as_numbers():
    assert parse_picks("@Scout my picks: 3, 1", ACTIVITY_NAMES) == [0, 2]


def test_sending_no_picks_means_in_for_nothing():
    assert parse_picks("@scout my picks:", ACTIVITY_NAMES) == []


def test_a_message_that_isnt_picks_is_left_for_the_agent():
    assert parse_picks("@scout what's the plan?", ACTIVITY_NAMES) is None


def test_picks_naming_something_off_the_deck_are_left_for_the_agent():
    assert parse_picks("@scout my picks: 1, skydiving", ACTIVITY_NAMES) is None


def test_the_tally_runs_from_what_everyone_wants_to_what_nobody_does():
    deck = ActivityDeck(
        activities=[DeckActivity(name, "", 50) for name in ACTIVITY_NAMES],
        picks={MAYA.phone: [0, 1], LEO.phone: [0], PRIYA.phone: [0]},
    )

    assert format_tally(deck, [MAYA, LEO, PRIYA]) == (
        "everyone's picks are in:\n"
        "everyone: Night kayak in the bio bay\n"
        "just one: Old San Juan food tour (Maya)\n"
        "nobody: El Yunque hike"
    )


def test_the_tally_counts_activities_some_but_not_all_want():
    deck = ActivityDeck(
        activities=[DeckActivity(name, "", 50) for name in ACTIVITY_NAMES],
        picks={MAYA.phone: [0, 2], LEO.phone: [0, 2], PRIYA.phone: [1]},
    )

    assert format_tally(deck, [MAYA, LEO, PRIYA]).split("\n")[1:] == [
        "2 of 3: Night kayak in the bio bay, El Yunque hike",
        "just one: Old San Juan food tour (Priya)",
    ]
