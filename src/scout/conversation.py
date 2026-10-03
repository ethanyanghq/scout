"""Decides what scout does with each message in a chat.

Cheap, predictable cases (introducing scout, counting a plain "2" as a vote)
are handled here in code. Everything that needs language understanding goes
to the agent. Messages arrive one at a time per chat (the bridge waits for
each reply), so two votes can't race to close the same poll.
"""

import logging
from datetime import datetime
from typing import Protocol

from scout import polls
from scout.trip import IncomingMessage, Trip, TripStage
from scout.trip_actions import TripActions
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

INTRODUCTION = (
    "Hey all, I'm scout 👋 I'll help you turn this chat into an actual trip.\n"
    "Everyone reply with:\n"
    "1. Your name\n"
    "2. Dates you're free\n"
    "3. Budget per person\n"
    "4. Where you're coming from\n"
    "5. One must-have\n"
    "I read this chat to keep track of the plan and only save trip details. "
    "Tag @scout anytime."
)
SNAG_REPLY = "Sorry, I hit a snag on my end. Mind trying that again in a minute?"


class Agent(Protocol):
    def respond(self, trip: Trip, message: IncomingMessage) -> list[str]: ...


def handle_message(
    message: IncomingMessage, store: TripStore, agent: Agent
) -> list[str]:
    """Records the message and returns the texts scout should send back."""
    replies = []
    if store.get_trip(message.space_id) is None:
        store.create_trip(message.space_id)
        replies.append(INTRODUCTION)

    store.add_members(
        message.space_id, [message.sender_phone, *message.participant_phones]
    )
    store.log_message(
        message.space_id, message.sender_phone, message.text, message.sent_at
    )
    # Log the introduction before the agent runs so the agent can see it.
    for reply in replies:
        store.log_message(message.space_id, None, reply, datetime.now())

    trip = store.get_trip(message.space_id)
    new_replies = _respond(trip, message, store, agent)
    for reply in new_replies:
        store.log_message(message.space_id, None, reply, datetime.now())
    return replies + new_replies


def _respond(
    trip: Trip, message: IncomingMessage, store: TripStore, agent: Agent
) -> list[str]:
    if trip.open_poll is not None:
        choice = polls.parse_vote(message.text, trip.open_poll.options)
        if choice is not None:
            actions = TripActions(store, trip.space_id, message.sender_phone)
            actions.record_sender_vote(choice)
            return actions.outbox

    is_collecting = trip.stage == TripStage.COLLECTING_PREFERENCES
    # CS-1: people log what they paid in plain messages ("dinner was me, $164"),
    # without tagging scout. Before the destination is chosen, dollar amounts
    # are budgets and price talk, not expenses.
    might_log_expense = trip.destination is not None and message.mentions_money
    if not (message.mentions_scout or is_collecting or might_log_expense):
        return []

    try:
        return agent.respond(trip, message)
    except Exception:
        # The group shouldn't be left hanging when they asked scout directly,
        # but scout shouldn't apologize for messages it was never asked about.
        logger.exception("Agent failed on message in %s", message.space_id)
        return [SNAG_REPLY] if message.mentions_scout else []
