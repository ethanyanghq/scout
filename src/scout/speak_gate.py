"""Decides whether scout should chime in on a message that doesn't tag it.

Most messages in a group chat are friends talking to each other, so a quick,
cheap model call looks at the latest messages first. Only when it says SPEAK
does the full agent run, which keeps scout quiet and the AI bill small.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from scout.group_summary import summarize_group
from scout.trip import IncomingMessage, Trip
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

SPEAK = "SPEAK"
RECENT_MESSAGE_COUNT = 12
GATE_PROMPT = (Path(__file__).parent / "speak_gate_prompt.md").read_text()

# Sends the gate prompt and a situation to a small model and returns its answer.
AskModel = Callable[[str, str], str]


def is_addressed_to_scout(store: TripStore, message: IncomingMessage) -> bool:
    """Whether the message tags scout or replies in a thread to one of its texts."""
    if message.mentions_scout:
        return True
    if message.reply_to_text is None:
        return False
    return store.has_scout_said(message.space_id, message.reply_to_text)


class SpeakGate:
    def __init__(self, ask_model: AskModel, store: TripStore):
        self._ask_model = ask_model
        self._store = store

    def should_speak(self, trip: Trip, message: IncomingMessage) -> bool:
        """Whether scout should look at this untagged message. If the model
        can't be reached, scout stays quiet: nobody asked it anything."""
        situation = self._describe_situation(trip, message)
        try:
            verdict = self._ask_model(GATE_PROMPT, situation)
        except Exception:
            logger.exception("Speak gate failed in %s, staying quiet", message.space_id)
            return False
        return verdict.strip().upper().startswith(SPEAK)

    def _describe_situation(self, trip: Trip, message: IncomingMessage) -> str:
        labels = {member.phone: member.label for member in trip.members}
        recent = self._store.recent_messages(trip.space_id, RECENT_MESSAGE_COUNT)
        chat = "\n".join(
            f"[{labels.get(logged.sender_phone, 'scout')}] {logged.text}"
            for logged in recent
        )
        still_to_share = summarize_group(trip.members).members_still_to_share
        facts = [
            f"scout has spoken in this chat: "
            f"{'yes' if self._store.has_scout_spoken(trip.space_id) else 'no'}",
            f"Trip stage: {trip.stage}",
            f"Still waiting on trip details from: "
            f"{', '.join(member.label for member in still_to_share) or 'nobody'}",
        ]
        if trip.destination:
            facts.append(f"The group chose {trip.destination}.")
        if trip.open_poll:
            facts.append("A destination poll is open.")
        if trip.activity_deck:
            facts.append("An activity deck is out for everyone to pick from.")
        return (
            "# Where the trip is\n" + "\n".join(facts) + "\n\n"
            "# The latest messages, oldest first\n" + chat + "\n\n"
            "# Newest message\n"
            f"From {labels.get(message.sender_phone, 'someone')}: "
            f"{message.readable_text}"
        )
