from datetime import date

import pytest

from scout.trip import DestinationOption, PreferenceUpdate
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


def test_saving_preferences_reports_what_is_still_missing(maya_actions):
    status = maya_actions.save_sender_preferences(
        PreferenceUpdate(display_name="Maya", budget_usd=800)
    )

    assert "Maya is still missing: dates, home city" in status
    assert "waiting on: Maya, …0002" in status


def test_rejects_dates_that_end_before_they_start(maya_actions):
    with pytest.raises(TripActionError):
        maya_actions.save_sender_preferences(
            PreferenceUpdate(
                available_from=date(2027, 3, 20), available_to=date(2027, 3, 13)
            )
        )


def test_starting_a_poll_posts_it_to_the_chat(maya_actions):
    maya_actions.start_destination_poll(OPTIONS)

    assert maya_actions.outbox[0].startswith("🗳️ Where should we go?")


def test_cannot_start_a_second_poll_while_one_is_open(maya_actions):
    maya_actions.start_destination_poll(OPTIONS)

    with pytest.raises(TripActionError):
        maya_actions.start_destination_poll(OPTIONS)


def test_a_poll_needs_exactly_three_options(maya_actions):
    with pytest.raises(TripActionError):
        maya_actions.start_destination_poll(OPTIONS[:2])


def test_closing_a_poll_nobody_voted_in_is_refused(maya_actions):
    maya_actions.start_destination_poll(OPTIONS)

    with pytest.raises(TripActionError):
        maya_actions.close_poll()
