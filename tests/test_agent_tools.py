from datetime import date

import pytest

from scout.agent_tools import run_tool
from scout.outgoing import Link, Say
from scout.places import Coordinates, Place
from scout.trip import DateWindow, DestinationOption, ItineraryDay
from scout.trip_actions import TripActionError, TripActions


def said(outgoing):
    """The texts scout sent, failing on anything that isn't a plain text."""
    assert all(isinstance(item, Say) for item in outgoing), outgoing
    return [item.text for item in outgoing]


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
        "member": "…0001",
        "display_name": None,
        "available_from": "March 13",
        "available_to": None,
        "budget_usd": None,
        "home_city": None,
        "must_haves": None,
    }

    with pytest.raises(TripActionError, match="YYYY-MM-DD"):
        run_tool(maya_actions, "save_member_preferences", tool_input)


def test_agent_itinerary_dates_become_planned_days(maya_actions, store):
    maya_actions.start_destination_poll(OPTIONS)
    poll_id = store.get_trip(SPACE).open_poll.id
    dates = DateWindow(date(2027, 3, 14), date(2027, 3, 19))
    store.close_poll(poll_id, "San Juan, Puerto Rico", dates)
    tool_input = {"days": [{"date": "2027-03-14", "plan": "Land and check in"}]}

    run_tool(maya_actions, "post_itinerary", tool_input)

    assert store.get_trip(SPACE).itinerary == [
        ItineraryDay(date(2027, 3, 14), "Land and check in")
    ]


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


def test_agent_removes_expenses_by_the_number_it_was_shown(maya_actions, store):
    expense_id = store.add_expense(SPACE, MAYA, 19_600, "Bio bay kayaks")

    run_tool(maya_actions, "remove_expense", {"expense_number": expense_id})

    assert store.get_trip(SPACE).expenses == []


def test_agent_receipt_totals_and_dates_are_read_back(maya_actions, store):
    tool_input = {
        "merchant": "Casa Brisa",
        "purchased_on": "2027-03-16",
        "total_usd": 164,
    }

    run_tool(maya_actions, "ask_to_confirm_receipt", tool_input)

    assert store.get_trip(SPACE).pending_receipt.total_cents == 16_400
    assert "Casa Brisa, Mar 16, $164 total" in said(maya_actions.outbox)[0]


def test_agent_picks_use_the_numbers_shown_in_the_list(maya_actions, store):
    store.replace_place_suggestions(
        SPACE,
        [
            Place("place-1", "Lote 23", Coordinates(18.45, -66.07), None, None),
            Place("place-2", "Taco Bar", Coordinates(18.46, -66.08), None, None),
        ],
    )

    run_tool(maya_actions, "send_directions", {"option_number": 2})

    lead_in, link = maya_actions.outbox
    assert lead_in == Say("🧭 Directions to Taco Bar:")
    assert isinstance(link, Link)


def test_brochure_tool_input_reaches_the_action(maya_actions):
    destination = {
        "name": "Tulum, Mexico",
        "region": "Quintana Roo, Mexico",
        "description": "White sand and cenotes.",
        "flights_usd": 400,
        "hotel_usd": 500,
        "food_and_activities_usd": 200,
        "activities": [{"name": "Swim a cenote", "estimated_cost_usd": 30}],
    }

    # Without place search the action refuses, which shows the input parsed.
    with pytest.raises(TripActionError, match="brochures aren't available"):
        run_tool(
            maya_actions,
            "send_destination_brochures",
            {"nights": 5, "destinations": [destination] * 3},
        )
