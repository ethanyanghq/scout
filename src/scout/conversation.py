"""Decides what scout does with each message in a chat.

Cheap, predictable cases (introducing scout, counting a plain "2" as a vote or
a pick of a nearby place) are handled here in code. Everything that needs
language understanding goes to the agent. Messages arrive one at a time per
chat (the bridge waits for each reply), so two votes can't race to close the
same poll.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from scout import polls
from scout.outgoing import Outgoing, React, Say, Tapback, as_plain_text
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
    def respond(self, trip: Trip, message: IncomingMessage) -> list[Outgoing]: ...


def handle_message(
    message: IncomingMessage, store: TripStore, agent: Agent
) -> list[Outgoing]:
    """Records the message and returns what scout should send back."""
    replies: list[Outgoing] = []
    if store.get_trip(message.space_id) is None:
        store.create_trip(message.space_id)
        replies.append(Say(INTRODUCTION))

    store.add_members(
        message.space_id, [message.sender_phone, *message.participant_phones]
    )
    store.log_message(
        message.space_id, message.sender_phone, _chat_log_text(message), message.sent_at
    )
    # Log the introduction before the agent runs so the agent can see it.
    _log_sent(store, message.space_id, replies)

    trip = store.get_trip(message.space_id)
    new_replies = _respond(trip, message, store, agent)
    _log_sent(store, message.space_id, new_replies)
    return replies + new_replies


def _respond(
    trip: Trip, message: IncomingMessage, store: TripStore, agent: Agent
) -> list[Outgoing]:
    if trip.open_poll is not None:
        option_names = [option.name for option in trip.open_poll.options]
        choice = polls.parse_vote(message.text, option_names)
        if choice is not None:
            actions = TripActions(store, trip.space_id, message.sender_phone)
            actions.record_sender_vote(choice, confirm=_tapback_on(message))
            return actions.outbox

    if trip.place_suggestions:
        place_names = [place.name for place in trip.place_suggestions]
        pick = polls.parse_vote(message.text, place_names)
        if pick is not None:
            actions = TripActions(store, trip.space_id, message.sender_phone)
            actions.send_directions(pick)
            return actions.outbox

    if not (message.mentions_scout or _needs_agent_untagged(trip, message)):
        return []

    try:
        return agent.respond(trip, message)
    except Exception:
        # The group shouldn't be left hanging when they asked scout directly,
        # but scout shouldn't apologize for messages it was never asked about.
        logger.exception("Agent failed on message in %s", message.space_id)
        return [Say(SNAG_REPLY)] if message.mentions_scout else []


def _tapback_on(message: IncomingMessage) -> Callable[[str], Outgoing]:
    """Confirms with a 👍 on the message, so a vote doesn't add a line to the
    chat. Without a message ID (scout-simulate), the confirmation is a text."""
    if message.message_id is None:
        return Say
    message_id = message.message_id
    return lambda text: React(message_id, Tapback.LIKE, fallback_text=text)


def _needs_agent_untagged(trip: Trip, message: IncomingMessage) -> bool:
    """Whether an untagged message might be something scout should act on."""
    if trip.stage == TripStage.COLLECTING_PREFERENCES:
        return True
    # Before the destination is chosen, dollar amounts and photos are budgets,
    # price talk, and memes, not expenses.
    if trip.destination is None:
        return False
    # CS-1 and CS-7: people log what they paid in plain messages ("dinner was
    # me, $164") or by texting a receipt, without tagging scout.
    if message.mentions_money or message.photo is not None:
        return True
    # The payer's reply to "Split it 4 ways?" is usually just "yep".
    receipt = trip.pending_receipt
    return receipt is not None and receipt.payer_phone == message.sender_phone


def _log_sent(store: TripStore, space_id: str, sent: list[Outgoing]) -> None:
    for outgoing in sent:
        store.log_message(space_id, None, as_plain_text(outgoing), datetime.now())


def _chat_log_text(message: IncomingMessage) -> str:
    # The photo itself isn't kept, but later turns should know one was sent.
    if message.photo is None:
        return message.text
    return f"[photo] {message.text}".strip()
