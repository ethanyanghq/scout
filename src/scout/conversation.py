"""Decides what scout does with each message in a chat.

Cheap, predictable cases (counting a plain "2" or a 👍 on a poll option as a
vote, the picks sent from the activity deck, a pick of a nearby place) are
handled here in code. Messages that tag scout go straight to the agent, which
reads the whole chat to catch up. Any other message first goes past a cheap
gate that decides whether scout has anything to add. Messages arrive one at a
time per chat (the bridge waits for each reply), so two votes can't race to
close the same poll.
"""

import logging
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Protocol

from scout import polls
from scout.activity_deck import parse_picks
from scout.cards import INTERVIEW_ANSWER_LEAD
from scout.outgoing import Outgoing, React, Say, Tapback, as_plain_text
from scout.outside_services import NO_OUTSIDE_SERVICES, OutsideServices
from scout.private_chat import handle_private_message, is_private_chat
from scout.speak_gate import is_addressed_to_scout
from scout.trip import IncomingMessage, IncomingReaction, Trip
from scout.trip_actions import TripActions
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

INTRODUCTION_SNAG_REPLY = (
    "hey all, i'm scout. hit a snag on my end so i can't help just yet, "
    "tag @scout in a minute to try again"
)
SNAG_REPLY = "ugh, hit a snag on my end. mind trying that again in a minute?"
# Tapbacks that mean "this one" on a poll option. A 😂 on Miami isn't a vote.
VOTING_TAPBACKS = {Tapback.LIKE, Tapback.LOVE}


class Agent(Protocol):
    def respond(self, trip: Trip, message: IncomingMessage) -> list[Outgoing]: ...


class Gate(Protocol):
    def should_speak(self, trip: Trip, message: IncomingMessage) -> bool: ...


def handle_message(
    message: IncomingMessage,
    store: TripStore,
    agent: Agent,
    gate: Gate,
    services: OutsideServices = NO_OUTSIDE_SERVICES,
) -> list[Outgoing]:
    """Records the message and returns what scout should send back."""
    if is_private_chat(message):
        return handle_private_message(message, store)
    if message.arrived_late:
        # It should take seconds. The bridge's log says whether Linq delivered
        # it late or it waited behind scout's earlier replies.
        logger.warning(
            "This message reached scout %ds after it was sent, so the AI is told",
            message.delivery_delay.total_seconds(),
        )

    if store.get_trip(message.space_id) is None:
        store.create_trip(message.space_id)

    store.add_members(
        message.space_id, [message.sender_phone, *message.participant_phones]
    )
    if message.media is not None:
        store.save_media(message.space_id, message.media)
    store.log_message(
        message.space_id, message.sender_phone, _chat_log_text(message), message.sent_at
    )

    trip = store.get_trip(message.space_id)
    is_introduction = not store.has_scout_spoken(message.space_id)
    replies = _respond(trip, message, store, agent, gate)
    if is_introduction and replies and replies[0] != Say(INTRODUCTION_SNAG_REPLY):
        # Sent in code, not left to the AI, so every group gets the interview.
        actions = TripActions(store, message.space_id, message.sender_phone, services)
        actions.send_trip_interview(date.today())
        replies = [*replies, *actions.outbox]
    _log_sent(store, message.space_id, replies)
    return replies


def handle_reaction(reaction: IncomingReaction, store: TripStore) -> list[Outgoing]:
    """Counts a 👍 or ❤️ on an option of the open poll as a vote for it. Any
    other reaction is just chat, so scout stays quiet."""
    trip = store.get_trip(reaction.space_id)
    if trip is None or trip.open_poll is None or reaction.message_text is None:
        return []
    if reaction.tapback not in VOTING_TAPBACKS:
        return []
    option_names = [option.name for option in trip.open_poll.options]
    choice = polls.option_in_poll_message(reaction.message_text, option_names)
    if choice is None:
        return []

    store.add_members(reaction.space_id, [reaction.sender_phone])
    store.log_message(
        reaction.space_id,
        reaction.sender_phone,
        f"({reaction.tapback} tapback on poll option {choice + 1})",
        reaction.sent_at,
    )
    actions = TripActions(store, trip.space_id, reaction.sender_phone)
    # Threaded under the option they tapped, so the main chat stays clear.
    actions.record_sender_vote(
        choice, confirm=lambda text: Say(text, reply_to=reaction.message_id)
    )
    _log_sent(store, reaction.space_id, actions.outbox)
    return actions.outbox


def _respond(
    trip: Trip,
    message: IncomingMessage,
    store: TripStore,
    agent: Agent,
    gate: Gate,
) -> list[Outgoing]:
    if trip.open_poll is not None:
        option_names = [option.name for option in trip.open_poll.options]
        choice = polls.parse_vote(message.text, option_names)
        if choice is not None:
            logger.info("A vote for option %d, counted without the AI", choice + 1)
            actions = TripActions(store, trip.space_id, message.sender_phone)
            actions.record_sender_vote(choice, confirm=_tapback_on(message))
            return actions.outbox

    if trip.activity_deck is not None:
        activity_names = [activity.name for activity in trip.activity_deck.activities]
        picks = parse_picks(message.text, activity_names)
        if picks is not None:
            logger.info("Activity picks %s, saved without the AI", picks)
            had_a_majority = trip.activity_deck.has_picks_from_a_majority(trip.members)
            actions = TripActions(store, trip.space_id, message.sender_phone)
            actions.record_sender_picks(picks, confirm=_tapback_on(message))
            trip = store.get_trip(trip.space_id)
            has_a_majority = trip.activity_deck.has_picks_from_a_majority(trip.members)
            if had_a_majority or not has_a_majority:
                return actions.outbox
            # These picks make a majority, so the AI posts the itinerary.
            logger.info("A majority has sent picks, so asking the AI for the plan")
            is_addressed = is_addressed_to_scout(store, message)
            return [
                *actions.outbox,
                *_ask_agent(trip, message, store, agent, is_addressed),
            ]

    if trip.place_suggestions:
        place_names = [place.name for place in trip.place_suggestions]
        pick = polls.parse_vote(message.text, place_names)
        if pick is not None:
            logger.info("A pick of place %d, sent directions without the AI", pick + 1)
            actions = TripActions(store, trip.space_id, message.sender_phone)
            actions.send_directions(pick)
            return actions.outbox

    # A tag always gets scout's attention. Anything else only does when the
    # gate (a small, quick model) thinks scout has something to add.
    is_addressed = is_addressed_to_scout(store, message)
    if is_addressed:
        logger.info("Tagged, so asking the AI")
    elif gate.should_speak(trip, message):
        logger.info("Not tagged, but the gate says scout may have something to add")
    else:
        logger.info("Not tagged, and the gate says to stay quiet")
        return []

    return _ask_agent(trip, message, store, agent, is_addressed)


def _ask_agent(
    trip: Trip,
    message: IncomingMessage,
    store: TripStore,
    agent: Agent,
    is_addressed: bool,
) -> list[Outgoing]:
    is_trip_card_answer = message.text.startswith(INTERVIEW_ANSWER_LEAD)
    if is_trip_card_answer and _answered_trip_card_before(store, message):
        # The card is filled in once; a resend would only repeat the same answers.
        logger.info("Already has this member's trip card answers, so no reply")
        return []

    started = time.monotonic()
    try:
        replies = agent.respond(trip, message)
        took = time.monotonic() - started
        outcome = "replied" if replies else "chose not to reply"
        logger.info("The AI %s after %.1fs", outcome, took)
        return replies
    except Exception:
        logger.exception("Agent failed on message in %s", message.space_id)
        # Nobody asked scout anything, so a snag isn't worth interrupting for.
        if not is_addressed:
            return []
        if store.has_scout_spoken(message.space_id):
            return [Say(SNAG_REPLY)]
        # Joining with a canned greeting would hide that scout is broken.
        return [Say(INTRODUCTION_SNAG_REPLY)]


def _answered_trip_card_before(store: TripStore, message: IncomingMessage) -> bool:
    """Whether the sender sent trip card answers before this message, which is
    already in the log."""
    answers = [
        logged
        for logged in store.chat_history(message.space_id)
        if logged.sender_phone == message.sender_phone
        and logged.text.startswith(INTERVIEW_ANSWER_LEAD)
    ]
    return len(answers) > 1


def _tapback_on(message: IncomingMessage) -> Callable[[str], Outgoing]:
    """Confirms with a 👍 on the message, so a vote doesn't add a line to the
    chat. Without a message ID (scout-simulate), the confirmation is a text."""
    if message.message_id is None:
        return Say
    message_id = message.message_id
    return lambda text: React(message_id, Tapback.LIKE, fallback_text=text)


def _log_sent(store: TripStore, space_id: str, sent: list[Outgoing]) -> None:
    for outgoing in sent:
        store.log_message(space_id, None, as_plain_text(outgoing), datetime.now())


def _chat_log_text(message: IncomingMessage) -> str:
    """How a member's message reads in the chat log the agent sees."""
    # A photo or voice note reads as its words, so later turns can follow
    # along without seeing or hearing it again.
    text = message.readable_text
    # A threaded reply makes sense only next to what it answers.
    if message.reply_to_text is not None:
        text = f'(replying to "{message.reply_to_text}") {text}'
    return text
