"""The changes scout can make to a trip on behalf of whoever just texted.

Both the agent (through tools) and the fast vote path in conversation.py use
these, so the rules live in one place. Each action saves its change, adds any
chat messages it produces to `outbox`, and returns a short status for the
agent to read.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, time

from scout import polls
from scout.activity_deck import (
    MAX_DECK_ACTIVITIES,
    MIN_DECK_ACTIVITIES,
    PICK_SEPARATOR,
    RATING_WORDS,
    find_deck_photos,
    format_deck,
)
from scout.best_flights import (
    HomeAirport,
    HomeCityFlight,
    NoFlightFound,
    find_best_flights,
    format_best_flights,
)
from scout.best_hotel import NoHotelAvailable, find_best_hotel, format_best_hotel
from scout.booking_links import format_booking_links
from scout.brochures import (
    DestinationPitch,
    NoHotelFound,
    build_brochures,
    format_brochure,
)
from scout.calendar_feed import (
    calendar_subscription_url,
    format_calendar_message,
    format_plan_set_message,
)
from scout.cards import (
    EXPENSES_THUMBNAIL_URL,
    FLIGHTS_THUMBNAIL_URL,
    activity_deck,
    best_flights,
    best_hotel,
    destination_article,
    expense_report,
    fits_in_one_message,
    itinerary,
    trip_interview,
)
from scout.expense_report import (
    describe_items,
    describe_split,
    format_expense_ledger,
    format_expense_summary,
)
from scout.expense_split import split_by_items, split_evenly
from scout.flights import FlightsError
from scout.group_summary import format_group_summary, format_window, summarize_group
from scout.hotels import HotelsError
from scout.itinerary import format_itinerary
from scout.media import load_photo
from scout.money import format_usd
from scout.nearby import directions_link, format_directions, format_nearby_places
from scout.outgoing import Card, Link, Outgoing, React, Say, Tapback
from scout.outside_services import NO_OUTSIDE_SERVICES, OutsideServices
from scout.places import Coordinates, GooglePlaces, PlacesError
from scout.settle_up import (
    Payment,
    format_payments_left,
    format_settle_up,
    plan_payments,
)
from scout.trip import (
    DateWindow,
    DeckActivity,
    DestinationOption,
    Expense,
    ExpenseItem,
    ItineraryAddOn,
    ItineraryDay,
    MediaKind,
    Member,
    MessagePhoto,
    NewExpense,
    PendingReceipt,
    PreferenceUpdate,
    Rating,
    Settlement,
    Trip,
)
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

DESTINATION_OPTION_COUNT = 3
NEARBY_SUGGESTION_COUNT = 3
# Sent after the third brochure, so the group knows how to pick one.
FINAL_DECISION_PROMPT = "once you're ready, let me know your final decision with @scout"
# The trip interview card has no destination yet, so its bubble shows a beach.
INTERVIEW_THUMBNAIL_PLACE = "Grace Bay Beach, Turks and Caicos"
# Sent after the flight card, since flights come first and the stay is next.
HOTEL_OFFER = "want me to find a hotel too?"
TRIP_CARD_NUDGE = (
    "fill this out, takes like 30 sec. i'll come back with options once everyone's in"
)
INTERVIEW_FALLBACK_TEXT = (
    "tell me about your trip: the kind of trip (resort, lakeside, city break or "
    "something else), when you're free, your budget per person, where you're "
    "flying from, and what you're into."
)


class TripActionError(Exception):
    """The action can't be done as asked. The message says why, for the agent."""


@dataclass(frozen=True)
class ItemDraft:
    """One line of a receipt, with the members who shared it as the chat names them."""

    name: str
    amount_cents: int
    # Empty means whoever the whole expense is split among.
    shared_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpenseDraft:
    """A cost as the sender described it, before scout works out who owes what."""

    amount_cents: int
    description: str
    paid_on: date | None = None
    # The members who share it, as the chat names them. Empty means everyone.
    split_among: tuple[str, ...] = ()
    # When the receipt's lines were split by who had what.
    items: tuple[ItemDraft, ...] = ()


class _NoDestinationPhoto(Exception):
    """There's no photo of the destination to put on a card. The message says why."""


class TripActions:
    def __init__(
        self,
        store: TripStore,
        space_id: str,
        sender_phone: str,
        services: OutsideServices = NO_OUTSIDE_SERVICES,
        message_id: str | None = None,
    ):
        self._store = store
        self._space_id = space_id
        self._sender_phone = sender_phone
        self._services = services
        # The sender's newest message, which a confirmation can be a 👍 on.
        # None where there's no line to react on, as in scout-simulate.
        self._message_id = message_id
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
        status = (
            f"Saved. {member.label} is still missing: "
            f"{', '.join(member.missing_preferences) or 'nothing'}. "
            f"Group still waiting on: "
            f"{', '.join(m.label for m in still_waiting_on) or 'nobody'}."
        )
        if self._confirm_with_thumbs_up(member):
            status += (
                " A 👍 is going on their newest message to confirm it, so "
                "don't confirm in text unless something is unclear."
            )
        return status

    def _confirm_with_thumbs_up(self, saved: Member) -> bool:
        """Confirms a save with a 👍 on the sender's message instead of a text,
        when the details are the sender's own. A friend's details get a text,
        so the friend can correct them."""
        if saved.phone != self._sender_phone or self._message_id is None:
            return False
        already_confirmed = any(
            isinstance(sent, React) and sent.message_id == self._message_id
            for sent in self.outbox
        )
        if not already_confirmed:
            self.outbox.append(
                React(
                    self._message_id,
                    Tapback.LIKE,
                    fallback_text=_describe_saved_details(saved),
                )
            )
        return True

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
                f"got it, {voter.label} → {poll.options[option_index].name} "
                f"({len(poll.votes)} of {len(trip.members)} voted)"
            )
        )
        return "Vote recorded."

    def close_poll(self) -> str:
        trip = self._load_trip()
        if trip.open_poll is None:
            raise TripActionError("there is no open poll")
        return self._close(trip)

    def lock_in_group_choice(self, destination: str) -> str:
        """Locks in the destination one member chose for the whole group ("we
        picked San Juan"), closing any open poll without waiting for votes."""
        if not destination.strip():
            raise TripActionError("name the destination the group chose")
        trip = self._load_trip()
        if trip.open_poll is not None:
            option_names = [option.name for option in trip.open_poll.options]
            choice = polls.parse_vote(destination, option_names)
            if choice is not None:
                destination = option_names[choice]

        dates = summarize_group(trip.members).shared_window
        self._store.lock_in_destination(self._space_id, destination, dates)
        if dates is None:
            self.outbox.append(Say(f"{destination} it is, the group's pick 🎉"))
        else:
            self.outbox.append(
                Say(f"locked in: {destination}, {format_window(dates)} 🎉")
            )
        return (
            f"Destination is now {destination}. {_describe_dates_and_next_step(dates)}"
        )

    def post_itinerary(
        self, days: list[ItineraryDay], add_ons: list[ItineraryAddOn]
    ) -> str:
        """Posts the day-by-day plan, with what only one member wanted offered
        as optional add-ons. Replaces any earlier plan."""
        trip = self._load_locked_in_trip()
        if not days:
            raise TripActionError("an itinerary needs at least one day")
        for day in {event.day for event in days}:
            if not trip.dates.start <= day <= trip.dates.end:
                raise TripActionError(
                    f"{day} is outside the trip dates, "
                    f"{trip.dates.start} to {trip.dates.end}"
                )

        # Saved under the member's label as the chat shows it, not as the
        # agent spelled it.
        add_ons = [
            replace(add_on, wanted_by=self._find_member(add_on.wanted_by).label)
            for add_on in add_ons
        ]

        in_order = sorted(
            days, key=lambda event: (event.day, event.starts_at or time.min)
        )
        self._store.replace_itinerary(self._space_id, in_order, add_ons)
        is_first_plan = not trip.itinerary
        if is_first_plan:
            self.outbox.append(Say(format_plan_set_message(trip)))
        status = self._send_itinerary(self._load_trip())
        if not is_first_plan:
            # The link is already in the chat, and its feed shows the new plan.
            return f"{status} The calendar feed now shows the new plan."
        return f"{status} {self._send_calendar(self._load_trip())}"

    def _send_itinerary(self, trip: Trip) -> str:
        """Sends the plan as a card, or as text when there's no photo of the
        destination to show on the card, and says which happened."""
        text = format_itinerary(trip.itinerary, trip.itinerary_add_ons)
        try:
            photo_url = self._destination_photo_url(trip)
        except _NoDestinationPhoto as no_photo:
            self.outbox.append(Say(text))
            return f"Itinerary posted as text: {no_photo}"
        self.outbox.append(
            Card(
                layout=itinerary(trip, photo_url),
                caption=f"The plan for {trip.destination}",
                thumbnail_url=photo_url,
                fallback_text=text,
            )
        )
        return "Itinerary posted."

    def send_booking_links(self) -> str:
        self.outbox.append(Say(format_booking_links(self._load_locked_in_trip())))
        return "Booking links posted."

    def send_best_flights(
        self, home_airports: list[HomeAirport], arrival_airport: str
    ) -> str:
        """Posts a card with the best round trip from each home city, live from
        Google Flights, for the chosen destination and dates."""
        trip = self._load_locked_in_trip()
        flights = self._services.flights
        if flights is None:
            raise TripActionError(
                "flight search isn't set up, so send booking links instead"
            )
        _check_every_home_city_has_an_airport(trip, home_airports)

        try:
            home_city_flights = find_best_flights(
                flights, trip, home_airports, arrival_airport
            )
        except FlightsError as error:
            raise TripActionError(f"flight search isn't working: {error}") from error
        except NoFlightFound as error:
            raise TripActionError(
                f"{error}; try a nearby airport or send booking links"
            ) from error

        self.outbox.append(Say(_introduce_flights(home_city_flights)))
        self.outbox.append(
            Card(
                layout=best_flights(trip, home_city_flights),
                caption=f"Flights to {trip.destination}",
                thumbnail_url=FLIGHTS_THUMBNAIL_URL,
                fallback_text=format_best_flights(trip, home_city_flights),
            )
        )
        # A card's buttons don't open links inside iMessage, so each booking
        # link goes out as a message of its own, which does.
        for home_city_flight in home_city_flights:
            self.outbox.append(Say(f"book from {home_city_flight.home_city}:"))
            self.outbox.append(Link(home_city_flight.flight.booking_url))
        self.outbox.append(Say(HOTEL_OFFER))
        return "Flights posted."

    def send_best_hotel(self) -> str:
        """Posts a card with the best hotel, live from Google Hotels, for the
        chosen destination and dates."""
        trip = self._load_locked_in_trip()
        hotels = self._services.hotels
        if hotels is None:
            raise TripActionError(
                "hotel search isn't set up, so send booking links instead"
            )

        try:
            hotel = find_best_hotel(hotels, trip)
        except HotelsError as error:
            raise TripActionError(f"hotel search isn't working: {error}") from error
        except NoHotelAvailable as error:
            raise TripActionError(f"{error}; send booking links instead") from error

        self.outbox.append(Say(_introduce_hotel(trip)))
        self.outbox.append(
            Card(
                layout=best_hotel(trip, hotel),
                caption=f"Where to stay in {trip.destination}",
                thumbnail_url=hotel.photo_url,
                fallback_text=format_best_hotel(trip, hotel),
            )
        )
        # Sent on its own for the same reason as the flight links.
        self.outbox.append(Link(hotel.booking_url))
        return "Hotel posted."

    def log_sender_expense(self, draft: ExpenseDraft) -> str:
        """Logs a cost the sender paid, split among the members who shared it.
        Only payers log their own costs."""
        if draft.amount_cents <= 0:
            raise TripActionError("an expense must be more than $0")
        if not draft.description.strip():
            raise TripActionError("an expense needs a description, e.g. 'Airbnb'")

        trip = self._load_trip()
        new_expense = self._divide_among_members(trip, draft)
        expense_id = self._store.add_expense(self._space_id, new_expense)
        if (
            trip.pending_receipt
            and trip.pending_receipt.payer_phone == self._sender_phone
        ):
            # Logging is how the payer confirms (or corrects) their receipt.
            self._store.clear_pending_receipt(self._space_id)
        expense = Expense(**vars(new_expense), id=expense_id)
        self.outbox.append(Say(_describe_logged_expense(expense, trip)))
        return f"Logged as expense #{expense_id}."

    def _divide_among_members(self, trip: Trip, draft: ExpenseDraft) -> NewExpense:
        """Works out what each member owes toward the cost, to the cent."""
        everyone = tuple(member.phone for member in trip.members)
        split_among = self._find_member_phones(draft.split_among) or everyone
        items = tuple(
            _to_expense_item(
                item, self._find_member_phones(item.shared_by) or split_among
            )
            for item in draft.items
        )
        if items:
            shares = split_by_items(items, draft.amount_cents)
        else:
            shares = split_evenly(draft.amount_cents, split_among)

        if any(cents < 0 for cents in shares.values()):
            raise TripActionError(
                "the receipt's discount is bigger than the items it comes off"
            )
        if set(shares) <= {self._sender_phone}:
            raise TripActionError(
                "nobody else is sharing this, so there's nothing to split; "
                "ask who shared it"
            )
        return NewExpense(
            payer_phone=self._sender_phone,
            amount_cents=draft.amount_cents,
            description=draft.description,
            shares=shares,
            paid_on=draft.paid_on,
            items=items,
        )

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
                f"from the receipt: {merchant}{when}, {format_usd(total_cents)} total, "
                f"paid by {payer.label}. split it {len(trip.members)} ways, or "
                "tell me who had what?"
            )
        )
        return f"Asked {payer.label} to confirm. Log it once they do."

    def drop_pending_receipt(self) -> str:
        """Forgets the receipt waiting for confirmation, e.g. if it isn't shared."""
        if self._load_trip().pending_receipt is None:
            raise TripActionError("no receipt is waiting for confirmation")
        self._store.clear_pending_receipt(self._space_id)
        return "Receipt dropped. Nothing was logged."

    def view_photo(self, photo_id: str) -> MessagePhoto:
        """A photo sent earlier in this chat, for the agent to look at again."""
        media = self._store.find_media(self._space_id, photo_id)
        if media is None or media.kind is not MediaKind.PHOTO:
            raise TripActionError(f"there is no photo {photo_id} in this chat")
        return load_photo(media.readable_path)

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
            Say(f"removed: {expense.description}, {format_usd(expense.amount_cents)}.")
        )
        return "Expense removed."

    def post_settle_up(self) -> str:
        trip = self._load_trip()
        if not trip.expenses:
            raise TripActionError("nobody has logged an expense yet")
        self.outbox.append(Say(format_settle_up(trip)))
        return "Settle-up posted."

    def post_expense_report(self) -> str:
        """Posts the whole trip's spending as cards: every expense and its
        split, who paid what, and who owes whom."""
        trip = self._load_trip()
        if not trip.expenses:
            raise TripActionError("nobody has logged an expense yet")
        pages = expense_report(trip)
        for page in pages:
            self.outbox.append(
                Card(
                    layout=page.layout,
                    caption=page.caption,
                    thumbnail_url=EXPENSES_THUMBNAIL_URL,
                    fallback_text=(
                        format_expense_ledger(trip, page.expenses)
                        if page.expenses
                        else format_expense_summary(trip)
                    ),
                )
            )
        return f"Expense report posted as {len(pages)} cards."

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
            f"paid ✓ {payment.payer.label} → {payment.payee.label} "
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

    def send_activity_deck(self, activities: list[DeckActivity]) -> str:
        """Posts the deck of things to do at the destination for each member to
        tick, replacing any earlier deck and its picks."""
        trip = self._load_trip()
        if trip.destination is None:
            raise TripActionError("the group hasn't picked a destination yet")
        _check_deck_activities(activities)

        destination_photo, missing_photo = None, "place search isn't set up"
        places = self._services.places
        if places is not None:
            try:
                destination_photo, activities = find_deck_photos(
                    places, trip.destination, activities
                )
                missing_photo = f"no photo of {trip.destination}"
            except PlacesError as error:
                missing_photo = f"place search isn't working: {error}"

        self._store.replace_activity_deck(self._space_id, activities)
        layout = activity_deck(trip.destination, activities)
        if not fits_in_one_message(layout):
            # Photo links are most of a deck, and some of Google's are long.
            without_photos = [replace(a, photo_url=None) for a in activities]
            layout = activity_deck(trip.destination, without_photos)
        # Without a thumbnail, the bridge sends the deck's text instead.
        self.outbox.append(
            Card(
                layout=layout,
                caption=f"What are you up for in {trip.destination}?",
                thumbnail_url=destination_photo,
                fallback_text=format_deck(trip.destination, activities),
            )
        )
        if destination_photo is None:
            return f"Activity deck posted as text: {missing_photo}."
        return "Activity deck posted."

    def record_sender_picks(
        self,
        ratings: dict[int, Rating],
        confirm: Callable[[str], Outgoing] = Say,
    ) -> str:
        """Saves how the sender rated the activities (those left out are nah).
        Unless they're the last to send, `confirm` turns the confirmation text
        into what scout sends."""
        return self._record_picks(self._sender_phone, ratings, confirm)

    def record_member_picks(self, member_label: str, ratings: dict[int, Rating]) -> str:
        """Saves how any member rated the activities, including ratings a
        friend reported for them."""
        member = self._find_member(member_label)
        return self._record_picks(member.phone, ratings, Say)

    def _record_picks(
        self,
        phone: str,
        ratings: dict[int, Rating],
        confirm: Callable[[str], Outgoing],
    ) -> str:
        trip = self._load_trip()
        deck = trip.activity_deck
        if deck is None:
            raise TripActionError("there is no activity deck; send one first")
        for position in ratings:
            if not 0 <= position < len(deck.activities):
                raise TripActionError(f"activity {position + 1} isn't on the deck")

        picks = {p: r for p, r in sorted(ratings.items()) if r != Rating.NAH}
        self._store.save_activity_picks(self._space_id, phone, picks)
        deck.picks[phone] = picks
        if len(deck.picks) == len(trip.members):
            return (
                "Picks recorded. Everyone has sent theirs. Don't wait to be "
                "asked: in this same turn, call post_itinerary as the next step."
            )

        member = trip.find_member(phone)
        self.outbox.append(
            confirm(
                f"got {member.label}'s picks "
                f"({len(deck.picks)} of {len(trip.members)} sent)"
            )
        )
        return "Picks recorded."

    def send_trip_interview(self, today: date) -> str:
        """Posts the card each member taps through to say what trip they want."""
        self.outbox.append(
            Card(
                layout=trip_interview(today),
                caption="Plan your trip",
                thumbnail_url=self._interview_thumbnail_url(),
                fallback_text=INTERVIEW_FALLBACK_TEXT,
            )
        )
        self.outbox.append(Say(TRIP_CARD_NUDGE))
        return "Trip interview posted."

    def _interview_thumbnail_url(self) -> str | None:
        """A beach photo for the card's bubble. Without one, the bridge sends
        the card's text instead, which still asks everything."""
        places = self._services.places
        if places is None:
            return None
        try:
            beach = places.find_photographed(INTERVIEW_THUMBNAIL_PLACE, photo_count=1)
        except PlacesError:
            logger.warning("No beach photo for the trip interview", exc_info=True)
            return None
        return beach.photo_urls[0] if beach and beach.photo_urls else None

    def send_destination_brochures(
        self, pitches: list[DestinationPitch], nights: int
    ) -> str:
        """Posts a card for each of three destinations, each a short article
        with real photos, its top hotel, things to do and an all-in estimate."""
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

        self.outbox.extend(
            Card(
                layout=destination_article(brochure, nights),
                caption=brochure.place_name,
                thumbnail_url=brochure.hero_photo_url,
                fallback_text=format_brochure(brochure, nights),
            )
            for brochure in brochures
        )
        self.outbox.append(Say(FINAL_DECISION_PROMPT))
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
        return (
            f"Poll closed. Destination is now {result.winner.name}. "
            f"{_describe_dates_and_next_step(dates)}"
        )

    def _send_calendar(self, trip: Trip) -> str:
        """Sends the link to subscribe to the plan's calendar, if scout has a
        public address to serve it from, and says which happened."""
        public_url = self._services.public_url
        if public_url is None:
            return "No calendar link: SCOUT_PUBLIC_URL isn't set."
        self.outbox.extend(
            [
                Say(format_calendar_message()),
                Link(calendar_subscription_url(public_url, trip.space_id)),
            ]
        )
        return "Sent the calendar link."

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

    def _destination_photo_url(self, trip: Trip) -> str:
        """A photo of the destination for a card's unopened bubble."""
        if trip.destination is None:
            raise _NoDestinationPhoto("the group hasn't picked a destination yet.")
        places = self._services.places
        if places is None:
            raise _NoDestinationPhoto("place search isn't set up.")
        try:
            destination = places.find_photographed(trip.destination, photo_count=1)
        except PlacesError as error:
            raise _NoDestinationPhoto(f"place search isn't working: {error}") from error
        if destination is None or not destination.photo_urls:
            raise _NoDestinationPhoto(f"no photo of {trip.destination}.")
        return destination.photo_urls[0]

    def _find_member_phones(self, member_labels: tuple[str, ...]) -> tuple[str, ...]:
        """The members the chat calls these names, each once, in the order given."""
        phones = (self._find_member(label).phone for label in member_labels)
        return tuple(dict.fromkeys(phones))

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


def _describe_dates_and_next_step(dates: DateWindow | None) -> str:
    """What the agent is told once a destination is locked in: the dates, and
    that picking activities is next."""
    next_step = (
        "Don't wait to be asked: in this same turn, call send_activity_deck as "
        "the next step."
    )
    if dates is None:
        return f"No dates work for everyone, so the trip has no dates. {next_step}"
    return f"The trip is {format_window(dates)}. {next_step}"


def _describe_saved_details(member: Member) -> str:
    """What scout saved for someone, as a short text: "got it maya: mar 13–20 ·
    ~$800 · boston · beach"."""
    details = []
    if member.available_from and member.available_to:
        details.append(
            format_window(DateWindow(member.available_from, member.available_to))
        )
    if member.budget_usd is not None:
        details.append(f"~${member.budget_usd}")
    if member.home_city:
        details.append(member.home_city)
    details.extend(member.must_haves)
    if member.chronotype:
        details.append(member.chronotype)
    # Someone whose name isn't known is left out, never called by their number.
    who = f" {member.display_name}" if member.display_name else ""
    return f"got it{who}: {' · '.join(details)}".lower()


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


def _check_deck_activities(activities: list[DeckActivity]) -> None:
    if not MIN_DECK_ACTIVITIES <= len(activities) <= MAX_DECK_ACTIVITIES:
        raise TripActionError(
            f"a deck needs {MIN_DECK_ACTIVITIES} to {MAX_DECK_ACTIVITIES} "
            f"activities, got {len(activities)}"
        )
    names = [activity.name.strip().casefold() for activity in activities]
    if len(set(names)) != len(names):
        raise TripActionError("each activity needs its own name")
    for activity in activities:
        # The sent picks are names separated by these, so a name can't have one.
        if PICK_SEPARATOR.search(activity.name):
            raise TripActionError(f"{activity.name!r} can't contain '·' or ','")
        # "Food tour meh" is a rating, so a name can't end in a rating word.
        if activity.name.strip().casefold().split()[-1] in RATING_WORDS:
            raise TripActionError(
                f"{activity.name!r} can't end in {' or '.join(RATING_WORDS)}"
            )
        if activity.estimated_cost_usd < 0:
            raise TripActionError(f"{activity.name!r} can't cost less than $0")


def _to_expense_item(item: ItemDraft, shared_by: tuple[str, ...]) -> ExpenseItem:
    if item.amount_cents <= 0:
        raise TripActionError(f"{item.name!r} must cost more than $0")
    return ExpenseItem(item.name, item.amount_cents, shared_by)


def _describe_logged_expense(expense: Expense, trip: Trip) -> str:
    payer = trip.find_member(expense.payer_phone)
    lines = [
        f"got it: {expense.description}, {format_usd(expense.amount_cents)}, "
        f"paid by {payer.label}. {describe_split(expense, trip.members)}."
    ]
    items = describe_items(expense, trip.members)
    if items:
        lines.append(f"{items} (tax and tip split by what each person had)")
    return "\n".join(lines)


def _introduce_flights(home_city_flights: list[HomeCityFlight]) -> str:
    if len(home_city_flights) == 1:
        return "this flight seems like the best deal"
    return "these flights seem like the best deals"


def _introduce_hotel(trip: Trip) -> str:
    # The first person to talk to scout is the likeliest to book for everyone.
    return (
        f"{trip.initiator.label}, are you making the booking for the group? "
        "i'll help figure out the accounting later. book this hotel:"
    )


def _check_every_home_city_has_an_airport(
    trip: Trip, home_airports: list[HomeAirport]
) -> None:
    if not home_airports:
        raise TripActionError("give an airport for at least one home city")
    named = {home.home_city.casefold() for home in home_airports}
    missing = [
        city
        for city in summarize_group(trip.members).home_cities
        if city.casefold() not in named
    ]
    if missing:
        raise TripActionError(f"no airport given for {', '.join(missing)}")


def _locate(places: GooglePlaces, spot: str, destination: str) -> Coordinates:
    """Where a place the group named is, e.g. "our Airbnb in Condado" (OT-2)."""
    matches = places.search(f"{spot}, {destination}", limit=1)
    if not matches:
        raise TripActionError(f"couldn't find {spot!r} in {destination}")
    return matches[0].location
