from datetime import date

import pytest

from scout.trip import DateWindow, DestinationOption, ItineraryDay, PreferenceUpdate
from scout.trip_actions import TripActionError, TripActions

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport"),
    DestinationOption("Miami, Florida", 800, "Easy flights"),
]


MAYA_PREFERENCES = PreferenceUpdate(
    display_name="Maya",
    available_from=date(2027, 3, 13),
    available_to=date(2027, 3, 20),
    budget_usd=800,
    home_city="Boston",
)
LEO_PREFERENCES = PreferenceUpdate(
    display_name="Leo",
    available_from=date(2027, 3, 14),
    available_to=date(2027, 3, 19),
    budget_usd=600,
    home_city="New York",
)


@pytest.fixture
def maya_actions(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    return TripActions(store, SPACE, MAYA)


def everyone_votes_for_san_juan(store, leo_preferences=LEO_PREFERENCES):
    """Runs a trip up to the moment the poll closes. Returns the closing actions."""
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.save_preferences(SPACE, MAYA, MAYA_PREFERENCES)
    store.save_preferences(SPACE, LEO, leo_preferences)
    TripActions(store, SPACE, MAYA).start_destination_poll(OPTIONS)
    TripActions(store, SPACE, MAYA).record_sender_vote(1)
    leo_actions = TripActions(store, SPACE, LEO)
    leo_actions.record_sender_vote(1)
    return leo_actions


@pytest.fixture
def locked_in_actions(store):
    everyone_votes_for_san_juan(store)
    return TripActions(store, SPACE, MAYA)


def plan_day(day_of_march, plan):
    return ItineraryDay(date(2027, 3, day_of_march), plan)


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


def test_closing_the_poll_locks_in_the_dates_everyone_shares(store):
    everyone_votes_for_san_juan(store)

    trip = store.get_trip(SPACE)
    assert trip.destination == "San Juan, Puerto Rico"
    assert trip.dates == DateWindow(date(2027, 3, 14), date(2027, 3, 19))


def test_closing_the_poll_sends_a_calendar_link_after_the_winner(store):
    closing = everyone_votes_for_san_juan(store)

    winner, calendar = closing.outbox
    assert winner.startswith("🎉 Poll closed! San Juan, Puerto Rico wins")
    assert calendar.startswith("📅 Locked in: San Juan, Puerto Rico, Mar 14–19.")
    assert "calendar.google.com" in calendar


def test_no_calendar_link_when_no_dates_work_for_everyone(store):
    leo_in_april = PreferenceUpdate(
        display_name="Leo",
        available_from=date(2027, 4, 1),
        available_to=date(2027, 4, 5),
        budget_usd=600,
        home_city="New York",
    )

    closing = everyone_votes_for_san_juan(store, leo_preferences=leo_in_april)

    assert store.get_trip(SPACE).dates is None
    assert len(closing.outbox) == 1


def test_itinerary_is_posted_in_date_order(locked_in_actions):
    locked_in_actions.post_itinerary(
        [plan_day(15, "Beach day in Condado"), plan_day(14, "Land and check in")]
    )

    assert locked_in_actions.outbox == [
        "🗓️ The plan:\nSun 3/14 · Land and check in\nMon 3/15 · Beach day in Condado"
    ]


def test_a_new_itinerary_replaces_the_old_one(locked_in_actions, store):
    locked_in_actions.post_itinerary([plan_day(14, "Land"), plan_day(15, "Beach")])

    locked_in_actions.post_itinerary([plan_day(16, "Rainforest hike")])

    assert store.get_trip(SPACE).itinerary == [plan_day(16, "Rainforest hike")]


def test_itinerary_days_must_fall_within_the_trip(locked_in_actions):
    with pytest.raises(TripActionError, match="outside the trip dates"):
        locked_in_actions.post_itinerary([plan_day(20, "One more beach day")])


def test_itinerary_cannot_plan_the_same_day_twice(locked_in_actions):
    with pytest.raises(TripActionError, match="only once"):
        locked_in_actions.post_itinerary([plan_day(14, "Beach"), plan_day(14, "Hike")])


def test_no_itinerary_before_a_destination_is_chosen(maya_actions):
    with pytest.raises(TripActionError, match="destination"):
        maya_actions.post_itinerary([plan_day(14, "Beach")])


def test_booking_links_cover_each_home_city_and_a_stay(locked_in_actions):
    locked_in_actions.send_booking_links()

    lines = locked_in_actions.outbox[0].split("\n")
    assert lines[0] == "✈️ Flights for Mar 14–19:"
    assert lines[1].startswith("Boston: https://www.google.com/travel/flights?")
    assert lines[2].startswith("New York: https://www.google.com/travel/flights?")
    assert lines[3].startswith("🏠 Stays for 2: https://www.airbnb.com/s/")


def test_no_booking_links_before_a_destination_is_chosen(maya_actions):
    with pytest.raises(TripActionError, match="destination"):
        maya_actions.send_booking_links()
