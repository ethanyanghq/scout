"""Trips that start partway through the journey, for testing.

Reaching the vote for real means every member sharing preferences through
Claude first. A seeded trip skips that, so a test about voting starts at the
vote.
"""

import itertools
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum

from scout import polls
from scout.calendar_link import format_calendar_message, google_calendar_link
from scout.group_summary import summarize_group
from scout.trip import DestinationOption, PreferenceUpdate
from scout.trip_store import TripStore


class SeedStage(StrEnum):
    POLL_OPEN = "poll-open"
    DESTINATION_CHOSEN = "destination-chosen"


@dataclass(frozen=True)
class SeedMember:
    phone: str
    name: str


# Handed out to seeded members in order, so any group of them shares some
# dates: the first three share March 14–20, 2027, and all four March 14–19.
SEED_PREFERENCES = [
    PreferenceUpdate(
        available_from=date(2027, 3, 13),
        available_to=date(2027, 3, 20),
        budget_usd=800,
        home_city="Boston",
        must_haves=["beach"],
    ),
    PreferenceUpdate(
        available_from=date(2027, 3, 14),
        available_to=date(2027, 3, 22),
        budget_usd=600,
        home_city="New York",
        must_haves=[],
    ),
    PreferenceUpdate(
        available_from=date(2027, 3, 13),
        available_to=date(2027, 3, 21),
        budget_usd=700,
        home_city="Chicago",
        must_haves=["good food"],
    ),
    PreferenceUpdate(
        available_from=date(2027, 3, 12),
        available_to=date(2027, 3, 19),
        budget_usd=900,
        home_city="Austin",
        must_haves=["nightlife"],
    ),
]
SEED_POLL_OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches and cenotes"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport needed"),
    DestinationOption("Miami, Florida", 800, "Easy flights from everywhere"),
]
# San Juan, the destination in the demo script.
SEED_DESTINATION = SEED_POLL_OPTIONS[1]


def seed_trip(
    store: TripStore, space_id: str, stage: SeedStage, members: list[SeedMember]
) -> None:
    """Creates a chat's trip at the given stage, as if the group got there."""
    store.create_trip(space_id)
    store.add_members(space_id, [member.phone for member in members])
    for member, preferences in zip(
        members, itertools.cycle(SEED_PREFERENCES), strict=False
    ):
        store.save_preferences(
            space_id, member.phone, replace(preferences, display_name=member.name)
        )

    store.open_poll(space_id, SEED_POLL_OPTIONS)
    # The agent reads the recent chat, so it should see the poll it "posted".
    for text in polls.format_poll(SEED_POLL_OPTIONS):
        store.log_message(space_id, None, text, datetime.now())
    if stage == SeedStage.DESTINATION_CHOSEN:
        _close_poll_for_everyone(store, space_id)


def _close_poll_for_everyone(store: TripStore, space_id: str) -> None:
    """Closes the poll as if everyone voted for SEED_DESTINATION, and logs the
    announcement scout would have sent."""
    trip = store.get_trip(space_id)
    dates = summarize_group(trip.members).shared_window
    store.close_poll(trip.open_poll.id, SEED_DESTINATION.name, dates)
    everyone = len(trip.members)
    result = polls.PollResult(SEED_DESTINATION, winning_votes=everyone, tied_with=[])
    announcements = [polls.format_result(result, everyone)]
    if dates is not None:
        announcements.append(format_calendar_message(SEED_DESTINATION.name, dates))
        announcements.append(google_calendar_link(SEED_DESTINATION.name, dates))
    for text in announcements:
        store.log_message(space_id, None, text, datetime.now())
