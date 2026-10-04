from scout.activity_deck import format_tally, parse_picks
from scout.trip import ActivityDeck, DeckActivity, Member, Rating

ACTIVITY_NAMES = [
    "Night kayak in the bio bay",
    "Old San Juan food tour",
    "El Yunque hike",
]
MAYA = Member("+15550000001", display_name="Maya")
LEO = Member("+15550000002", display_name="Leo")
PRIYA = Member("+15550000003", display_name="Priya")


def test_reads_the_swipes_the_card_fills_in_leaving_out_nahs():
    text = (
        "@scout my picks: Night kayak in the bio bay yeah · "
        "Old San Juan food tour nah · El Yunque hike meh"
    )

    assert parse_picks(text, ACTIVITY_NAMES) == {0: Rating.YEAH, 2: Rating.MEH}


def test_reads_ratings_typed_against_numbers():
    assert parse_picks("@Scout my picks: 3 meh, 1 yeah", ACTIVITY_NAMES) == {
        0: Rating.YEAH,
        2: Rating.MEH,
    }


def test_a_pick_with_no_rating_is_a_yeah():
    assert parse_picks("@scout my picks: 3, 1", ACTIVITY_NAMES) == {
        0: Rating.YEAH,
        2: Rating.YEAH,
    }


def test_sending_no_picks_means_nah_to_everything():
    assert parse_picks("@scout my picks:", ACTIVITY_NAMES) == {}


def test_a_message_that_isnt_picks_is_left_for_the_agent():
    assert parse_picks("@scout what's the plan?", ACTIVITY_NAMES) is None


def test_picks_naming_something_off_the_deck_are_left_for_the_agent():
    assert parse_picks("@scout my picks: 1, skydiving meh", ACTIVITY_NAMES) is None


def test_the_tally_ranks_activities_by_score_and_names_who_swiped_what():
    deck = ActivityDeck(
        activities=[DeckActivity(name, "", 50) for name in ACTIVITY_NAMES],
        picks={
            MAYA.phone: {1: Rating.YEAH, 2: Rating.MEH},
            LEO.phone: {1: Rating.MEH, 2: Rating.MEH},
            PRIYA.phone: {2: Rating.YEAH},
        },
    )

    assert format_tally(deck, [MAYA, LEO, PRIYA]) == (
        "everyone's picks are in, best first:\n"
        "El Yunque hike: yeah Priya · meh Maya, Leo\n"
        "Old San Juan food tour: yeah Maya · meh Leo\n"
        "Night kayak in the bio bay: nobody"
    )
