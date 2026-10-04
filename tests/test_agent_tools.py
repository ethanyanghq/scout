import pytest

from scout.agent_tools import run_tool
from scout.trip import Chronotype, DestinationOption
from scout.trip_actions import TripActionError, TripActions

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport"),
    DestinationOption("Miami, Florida", 800, "Easy flights"),
]


@pytest.fixture
def maya_actions(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    return TripActions(store, SPACE, MAYA)


def test_agent_votes_use_the_numbers_shown_in_the_poll(maya_actions, store):
    maya_actions.start_destination_poll(OPTIONS)

    run_tool(
        maya_actions, "record_member_vote", {"member": "…0001", "option_number": 3}
    )

    assert store.get_trip(SPACE).open_poll.votes == {MAYA: 2}


def preferences_input(**shared):
    """A save_member_preferences call for Maya that mentions only `shared`."""
    nothing_mentioned = {
        "display_name": None,
        "available_from": None,
        "available_to": None,
        "budget_usd": None,
        "home_city": None,
        "must_haves": None,
        "chronotype": None,
    }
    return {"member": "…0001", **nothing_mentioned, **shared}


def test_agent_dates_must_be_real_calendar_dates(maya_actions):
    tool_input = preferences_input(available_from="March 13")

    with pytest.raises(TripActionError, match="YYYY-MM-DD"):
        run_tool(maya_actions, "save_member_preferences", tool_input)


def test_saves_when_a_member_likes_to_start_the_day(maya_actions, store):
    tool_input = preferences_input(chronotype="night owl")

    run_tool(maya_actions, "save_member_preferences", tool_input)

    assert store.get_trip(SPACE).find_member(MAYA).chronotype == Chronotype.NIGHT_OWL


@pytest.mark.parametrize(
    ("amount_usd", "expected_cents"), [(1240, 124_000), (164.5, 16_450), (0.29, 29)]
)
def test_agent_dollar_amounts_become_exact_cents(
    maya_actions, store, amount_usd, expected_cents
):
    tool_input = {"amount_usd": amount_usd, "description": "Dinner"}

    run_tool(maya_actions, "log_sender_expense", tool_input)

    assert store.get_trip(SPACE).expenses[0].amount_cents == expected_cents


def test_agent_amounts_cannot_split_a_cent(maya_actions):
    tool_input = {"amount_usd": 10.005, "description": "Dinner"}

    with pytest.raises(TripActionError, match="fractions of a cent"):
        run_tool(maya_actions, "log_sender_expense", tool_input)


def test_agent_chronotypes_must_be_one_of_the_three(maya_actions):
    tool_input = preferences_input(chronotype="morning person")

    with pytest.raises(TripActionError, match="'early riser', 'late riser'"):
        run_tool(maya_actions, "save_member_preferences", tool_input)
