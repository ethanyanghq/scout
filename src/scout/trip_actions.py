"""The changes scout can make to a trip on behalf of whoever just texted.

Both the agent (through tools) and the fast vote path in conversation.py use
these, so the rules live in one place. Each action saves its change, adds any
chat messages it produces to `outbox`, and returns a short status for the
agent to read.
"""

from collections.abc import Callable
from datetime import date

from scout import polls
from scout.booking_links import format_booking_links
from scout.brochures import (
    DestinationPitch,
    NoHotelFound,
    build_brochures,
    format_brochures,
)
from scout.calendar_link import format_calendar_message, google_calendar_link
from scout.cards import brochure_thumbnail_url, destination_brochures
from scout.group_summary import format_group_summary, summarize_group
from scout.itinerary import format_itinerary
from scout.money import format_usd
from scout.nearby import directions_link, format_directions, format_nearby_places
from scout.outgoing import Card, Link, Outgoing, Say
from scout.outside_services import NO_OUTSIDE_SERVICES, OutsideServices
from scout.places import Coordinates, GooglePlaces, PlacesError
from scout.settle_up import (
    Payment,
    format_payments_left,
    format_settle_up,
    plan_payments,
)
from scout.trip import (
    DestinationOption,
    ItineraryDay,
    Member,
    PendingReceipt,
    PreferenceUpdate,
    Settlement,
    Trip,
)
from scout.trip_store import TripStore

DESTINATION_OPTION_COUNT = 3
NEARBY_SUGGESTION_COUNT = 3


class TripActionError(Exception):
    """The action can't be done as asked. The message says why, for the agent."""


class TripActions:
    def __init__(
        self,
        store: TripStore,
        space_id: str,
        sender_phone: str,
        services: OutsideServices = NO_OUTSIDE_SERVICES,
    ):
        self._store = store
        self._space_id = space_id
        self._sender_phone = sender_phone
        self._services = services
        self.outbox: list[Outgoing] = []

    def save_member_preferences(
        self, member_label: str, update: PreferenceUpdate
    ) -> str:
        """Saves one member's details from anywhere in the chat: what they
        shared, or what a friend shared for them."""
        from_date, to_date = update.available_from, update.available_to
        if from_date and to_date and from_date > to_date:
            raise TripActionError(f"available_from {from_date} is after {to_date}")
        if update.budget_usd is not None and update.budget_usd <= 0:
            raise TripActionError("budget_usd must be a positive whole number")
        member = self._find_member(member_label)

        self._store.save_preferences(self._space_id, member.phone, update)
        trip = self._load_trip()
        member = trip.find_member(member.phone)
        still_waiting_on = summarize_group(trip.members).members_still_to_share
        return (
            f"Saved. {member.label} is still missing: "
            f"{', '.join(member.missing_preferences) or 'nothing'}. "
            f"Group still waiting on: "
            f"{', '.join(m.label for m in still_waiting_on) or 'nobody'}."
        )

    def post_group_summary(self) -> str:
        trip = self._load_trip()
        summary = summarize_group(trip.members)
        self.outbox.append(Say(format_group_summary(summary, trip.members)))
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
        self.outbox.extend(Say(text) for text in polls.format_poll(options))
        return "Poll posted."

    def record_sender_vote(
        self, option_index: int, confirm: Callable[[str], Outgoing] = Say
    ) -> str:
        """Counts the sender's vote. Unless it closes the poll, `confirm` turns
        the confirmation text into what scout sends: by default, that text."""
        return self._record_vote(self._sender_phone, option_index, confirm)

    def record_member_vote(self, member_label: str, option_index: int) -> str:
        """Counts a vote for any member, including one a friend reported for
        them ("ethan said he's in too")."""
        member = self._find_member(member_label)
        return self._record_vote(member.phone, option_index, Say)

    def _record_vote(
        self, voter_phone: str, option_index: int, confirm: Callable[[str], Outgoing]
    ) -> str:
        trip = self._load_trip()
        poll = trip.open_poll
        if poll is None:
            raise TripActionError("there is no open poll")
        if not 0 <= option_index < len(poll.options):
            raise TripActionError(f"option {option_index + 1} doesn't exist")

        self._store.record_vote(poll.id, voter_phone, option_index)
        poll.votes[voter_phone] = option_index
        if len(poll.votes) == len(trip.members):
            return self._close(trip)

        voter = trip.find_member(voter_phone)
        self.outbox.append(
            confirm(
                f"Got it, {voter.label} → {poll.options[option_index].name} "
                f"({len(poll.votes)} of {len(trip.members)} voted)"
            )
        )
        return "Vote recorded."

    def close_poll(self) -> str:
        trip = self._load_trip()
        if trip.open_poll is None:
            raise TripActionError("there is no open poll")
        return self._close(trip)

    def post_itinerary(self, days: list[ItineraryDay]) -> str:
        trip = self._load_locked_in_trip()
        if not days:
            raise TripActionError("an itinerary needs at least one day")
        planned_days = [day.day for day in days]
        if len(set(planned_days)) != len(planned_days):
            raise TripActionError("each date can appear only once")
        for day in planned_days:
            if not trip.dates.start <= day <= trip.dates.end:
                raise TripActionError(
                    f"{day} is outside the trip dates, "
                    f"{trip.dates.start} to {trip.dates.end}"
                )

        in_order = sorted(days, key=lambda day: day.day)
        self._store.replace_itinerary(self._space_id, in_order)
        self.outbox.append(Say(format_itinerary(in_order)))
        return "Itinerary posted."

    def send_booking_links(self) -> str:
        self.outbox.append(Say(format_booking_links(self._load_locked_in_trip())))
        return "Booking links posted."

    def log_sender_expense(self, amount_cents: int, description: str) -> str:
        """Logs a shared cost the sender paid. Only payers log their own costs."""
        if amount_cents <= 0:
            raise TripActionError("an expense must be more than $0")
        if not description.strip():
            raise TripActionError("an expense needs a description, e.g. 'Airbnb'")

        expense_id = self._store.add_expense(
            self._space_id, self._sender_phone, amount_cents, description
        )
        trip = self._load_trip()
        if (
            trip.pending_receipt
            and trip.pending_receipt.payer_phone == self._sender_phone
        ):
            # Logging is how the payer confirms (or corrects) their receipt.
            self._store.clear_pending_receipt(self._space_id)
        payer = trip.find_member(self._sender_phone)
        self.outbox.append(
            Say(
                f"Got it: {description}, {format_usd(amount_cents)}, paid by "
                f"{payer.label}. Split {len(trip.members)} ways."
            )
        )
        return f"Logged as expense #{expense_id}."

    def ask_to_confirm_receipt(
        self, merchant: str, purchased_on: date | None, total_cents: int
    ) -> str:
        """Shows what scout read from the sender's receipt, before logging it (CS-7)."""
        if total_cents <= 0:
            raise TripActionError("a receipt total must be more than $0")

        receipt = PendingReceipt(self._sender_phone, merchant, total_cents)
        self._store.save_pending_receipt(self._space_id, receipt)
        trip = self._load_trip()
        payer = trip.find_member(self._sender_phone)
        when = f", {purchased_on:%b} {purchased_on.day}" if purchased_on else ""
        self.outbox.append(
            Say(
                f"From the receipt: {merchant}{when}, {format_usd(total_cents)} total, "
                f"paid by {payer.label}. Split it {len(trip.members)} ways?"
            )
        )
        return f"Asked {payer.label} to confirm. Log it once they do."

    def drop_pending_receipt(self) -> str:
        """Forgets the receipt waiting for confirmation, e.g. if it isn't shared."""
        if self._load_trip().pending_receipt is None:
            raise TripActionError("no receipt is waiting for confirmation")
        self._store.clear_pending_receipt(self._space_id)
        return "Receipt dropped. Nothing was logged."

    def remove_expense(self, expense_id: int) -> str:
        """Removes one of the sender's own expenses, e.g. one logged by mistake."""
        trip = self._load_trip()
        expense = next((e for e in trip.expenses if e.id == expense_id), None)
        if expense is None:
            raise TripActionError(f"there is no expense #{expense_id}")
        if expense.payer_phone != self._sender_phone:
            payer = trip.find_member(expense.payer_phone)
            raise TripActionError(
                f"expense #{expense_id} was paid by {payer.label}, "
                "and only they can remove it"
            )

        self._store.remove_expense(self._space_id, expense_id)
        self.outbox.append(
            Say(f"Removed: {expense.description}, {format_usd(expense.amount_cents)}.")
        )
        return "Expense removed."

    def post_settle_up(self) -> str:
        trip = self._load_trip()
        if not trip.expenses:
            raise TripActionError("nobody has logged an expense yet")
        self.outbox.append(Say(format_settle_up(trip)))
        return "Settle-up posted."

    def record_sender_payment(self, payee_label: str) -> str:
        """Records that the sender paid what they owed one person."""
        trip = self._load_trip()
        payment = _find_sender_payment(trip, self._sender_phone, payee_label)
        self._store.add_settlement(
            self._space_id,
            Settlement(
                payer_phone=payment.payer.phone,
                payee_phone=payment.payee.phone,
                amount_cents=payment.amount_cents,
            ),
        )
        paid = (
            f"Paid ✓ {payment.payer.label} → {payment.payee.label} "
            f"{format_usd(payment.amount_cents)}"
        )
        self.outbox.append(Say(f"{paid}\n{format_payments_left(self._load_trip())}"))
        return "Payment recorded."

    def suggest_nearby_places(self, request: str, near: str | None) -> str:
        """Posts three real places that fit a vibe, near where the group is."""
        trip = self._load_trip()
        if trip.destination is None:
            raise TripActionError("the group hasn't picked a destination yet")
        places = self._services.places
        if places is None:
            raise TripActionError(
                "place search isn't set up, so tell the group recommendations "
                "aren't available yet"
            )

        try:
            start = _locate(places, near, trip.destination) if near else None
            found = places.search(
                f"{request} in {trip.destination}",
                limit=NEARBY_SUGGESTION_COUNT,
                near=start,
            )
        except PlacesError as error:
            raise TripActionError(f"place search isn't working: {error}") from error
        if not found:
            raise TripActionError(f"no places matched {request!r}; try other words")

        self._store.replace_place_suggestions(self._space_id, found)
        self.outbox.append(
            Say(format_nearby_places(found, start, near or trip.destination))
        )
        return "Places posted."

    def send_directions(self, option_index: int) -> str:
        """Sends directions to the place the group picked (OT-3)."""
        suggestions = self._load_trip().place_suggestions
        if not suggestions:
            raise TripActionError("there are no place suggestions to pick from")
        if not 0 <= option_index < len(suggestions):
            raise TripActionError(f"place {option_index + 1} doesn't exist")

        # Once the group has picked, a later "2" is just chat again.
        self._store.clear_place_suggestions(self._space_id)
        place = suggestions[option_index]
        self.outbox.extend(
            [Say(format_directions(place)), Link(directions_link(place))]
        )
        return "Directions sent."

    def send_destination_brochures(
        self, pitches: list[DestinationPitch], nights: int
    ) -> str:
        """Posts a card the group can scroll: three destinations, each with
        real photos, its top hotel, things to do and an all-in estimate."""
        if len(pitches) != DESTINATION_OPTION_COUNT:
            raise TripActionError(
                f"expected {DESTINATION_OPTION_COUNT} destinations, got {len(pitches)}"
            )
        places = self._services.places
        if places is None:
            raise TripActionError(
                "place search isn't set up, so tell the group brochures "
                "aren't available yet"
            )

        try:
            brochures = build_brochures(places, pitches)
        except PlacesError as error:
            raise TripActionError(f"place search isn't working: {error}") from error
        except NoHotelFound as error:
            raise TripActionError(f"{error}; pick another destination") from error

        self.outbox.append(
            Card(
                layout=destination_brochures(brochures),
                caption=f"{len(brochures)} spots to look around",
                thumbnail_url=brochure_thumbnail_url(brochures),
                fallback_text=format_brochures(brochures, nights),
            )
        )
        return "Brochures posted."

    def _close(self, trip: Trip) -> str:
        result = polls.decide_winner(trip.open_poll)
        if result is None:
            raise TripActionError("nobody has voted yet, so there's no winner")

        # Lock in the dates everyone shares right now, so later preference
        # edits can't quietly move a trip people have started booking.
        dates = summarize_group(trip.members).shared_window
        self._store.close_poll(trip.open_poll.id, result.winner.name, dates)
        self.outbox.append(Say(polls.format_result(result, len(trip.open_poll.votes))))
        if dates is None:
            return (
                f"Poll closed. Destination is now {result.winner.name}, "
                "but no dates work for everyone, so the trip has no dates."
            )
        self.outbox.extend(
            [
                Say(format_calendar_message(result.winner.name, dates)),
                Link(google_calendar_link(result.winner.name, dates)),
            ]
        )
        return f"Poll closed. Destination is now {result.winner.name}."

    def _load_locked_in_trip(self) -> Trip:
        """Loads a trip whose destination and dates are both settled."""
        trip = self._load_trip()
        if trip.destination is None:
            raise TripActionError("the group hasn't picked a destination yet")
        if trip.dates is None:
            raise TripActionError(
                "the trip has no dates because none worked for everyone "
                "when the poll closed"
            )
        return trip

    def _find_member(self, member_label: str) -> Member:
        trip = self._load_trip()
        member = trip.find_member_by_label(member_label)
        if member is None:
            labels = ", ".join(m.label for m in trip.members)
            raise TripActionError(
                f"no single member is called {member_label!r}; members are: {labels}"
            )
        return member

    def _load_trip(self) -> Trip:
        trip = self._store.get_trip(self._space_id)
        if trip is None:
            raise LookupError(f"no trip for space {self._space_id}")
        return trip


def _find_sender_payment(trip: Trip, sender_phone: str, payee_label: str) -> Payment:
    """The planned payment from the sender to the person they named."""
    sender_owes = [p for p in plan_payments(trip) if p.payer.phone == sender_phone]
    for payment in sender_owes:
        if payment.payee.label.casefold() == payee_label.strip().casefold():
            return payment
    payees = ", ".join(p.payee.label for p in sender_owes)
    sender = trip.find_member(sender_phone)
    raise TripActionError(
        f"{sender.label} doesn't owe {payee_label} anything. "
        f"They owe: {payees or 'nobody'}"
    )


def _locate(places: GooglePlaces, spot: str, destination: str) -> Coordinates:
    """Where a place the group named is, e.g. "our Airbnb in Condado" (OT-2)."""
    matches = places.search(f"{spot}, {destination}", limit=1)
    if not matches:
        raise TripActionError(f"couldn't find {spot!r} in {destination}")
    return matches[0].location
