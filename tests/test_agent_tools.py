import pytest

from scout.agent_tools import run_tool
from scout.trip import DestinationOption
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

    run_tool(maya_actions, "record_sender_vote", {"option_number": 3})

    assert store.get_trip(SPACE).open_poll.votes == {MAYA: 2}


def test_agent_dates_must_be_real_calendar_dates(maya_actions):
    tool_input = {
        "display_name": None,
        "available_from": "March 13",
        "available_to": None,
        "budget_usd": None,
        "home_city": None,
        "must_haves": None,
    }

    with pytest.raises(TripActionError, match="YYYY-MM-DD"):
        run_tool(maya_actions, "save_sender_preferences", tool_input)
