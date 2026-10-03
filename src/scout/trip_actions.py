"""The changes scout can make to a trip on behalf of whoever just texted.

Both the agent (through tools) and the fast vote path in conversation.py use
these, so the rules live in one place. Each action saves its change, adds any
chat messages it produces to `outbox`, and returns a short status for the
agent to read.
"""

from scout import polls
from scout.group_summary import format_group_summary, summarize_group
from scout.trip import DestinationOption, PreferenceUpdate, Trip
from scout.trip_store import TripStore

DESTINATION_OPTION_COUNT = 3


class TripActionError(Exception):
    """The action can't be done as asked. The message says why, for the agent."""


class TripActions:
    def __init__(self, store: TripStore, space_id: str, sender_phone: str):
        self._store = store
        self._space_id = space_id
        self._sender_phone = sender_phone
        self.outbox: list[str] = []

    def save_sender_preferences(self, update: PreferenceUpdate) -> str:
        from_date, to_date = update.available_from, update.available_to
        if from_date and to_date and from_date > to_date:
            raise TripActionError(f"available_from {from_date} is after {to_date}")
        if update.budget_usd is not None and update.budget_usd <= 0:
            raise TripActionError("budget_usd must be a positive whole number")

        self._store.save_preferences(self._space_id, self._sender_phone, update)
        trip = self._load_trip()
        sender = trip.find_member(self._sender_phone)
        still_waiting_on = summarize_group(trip.members).members_still_to_share
        return (
            f"Saved. {sender.label} is still missing: "
            f"{', '.join(sender.missing_preferences) or 'nothing'}. "
            f"Group still waiting on: "
            f"{', '.join(m.label for m in still_waiting_on) or 'nobody'}."
        )

    def post_group_summary(self) -> str:
        trip = self._load_trip()
        summary = summarize_group(trip.members)
        self.outbox.append(format_group_summary(summary, trip.members))
        if summary.dates_conflict:
            return "Summary posted. No dates work for everyone yet."
        return "Summary posted."

    def start_destination_poll(self, options: list[DestinationOption]) -> str:
        if len(options) != DESTINATION_OPTION_COUNT:
            raise TripActionError(
                f"expected {DESTINATION_OPTION_COUNT} options, got {len(options)}"
            )
        if self._load_trip().open_poll is not None:
            raise TripActionError("a poll is already open; close it first")

        self._store.open_poll(self._space_id, options)
        self.outbox.append(polls.format_poll(options))
        return "Poll posted."

    def record_sender_vote(self, option_index: int) -> str:
        trip = self._load_trip()
        poll = trip.open_poll
        if poll is None:
            raise TripActionError("there is no open poll")
        if not 0 <= option_index < len(poll.options):
            raise TripActionError(f"option {option_index + 1} doesn't exist")

        self._store.record_vote(poll.id, self._sender_phone, option_index)
        poll.votes[self._sender_phone] = option_index
        if len(poll.votes) == len(trip.members):
            return self._close(trip)

        voter = trip.find_member(self._sender_phone)
        self.outbox.append(
            f"Got it, {voter.label} → {poll.options[option_index].name} "
            f"({len(poll.votes)} of {len(trip.members)} voted)"
        )
        return "Vote recorded."

    def close_poll(self) -> str:
        trip = self._load_trip()
        if trip.open_poll is None:
            raise TripActionError("there is no open poll")
        return self._close(trip)

    def _close(self, trip: Trip) -> str:
        result = polls.decide_winner(trip.open_poll)
        if result is None:
            raise TripActionError("nobody has voted yet, so there's no winner")

        self._store.close_poll(trip.open_poll.id, result.winner.name)
        self.outbox.append(polls.format_result(result, len(trip.open_poll.votes)))
        return f"Poll closed. Destination is now {result.winner.name}."

    def _load_trip(self) -> Trip:
        trip = self._store.get_trip(self._space_id)
        if trip is None:
            raise LookupError(f"no trip for space {self._space_id}")
        return trip
