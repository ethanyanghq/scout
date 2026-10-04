"""The trip a group is planning, and the people planning it."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import IntEnum, StrEnum
from pathlib import Path

from scout.places import Place

# Matches "@scout" and "@Scout?", but not "@scouting".
SCOUT_MENTION = re.compile(r"@scout\b", re.IGNORECASE)
# Saying scout's name to it counts as a tag, typed or spoken: "@scout" or
# "at scout" as a transcript writes it, "hey/hi/yo/okay scout", or opening
# with "Scout,". Talking about scout ("let's ask scout later", "scout seems
# useful") doesn't. Voice notes and dictation often hear the name as "Scott".
ADDRESSES_SCOUT = re.compile(
    r"(?:@|\b(?:at|hey|hi|hello|yo|ok|okay)\s+)(?:scout|scott)\b"
    r"|^\W*(?:scout|scott)\s*,",
    re.IGNORECASE,
)


class TripStage(StrEnum):
    COLLECTING_PREFERENCES = "collecting_preferences"
    VOTING = "voting"
    DESTINATION_CHOSEN = "destination_chosen"


class Chronotype(StrEnum):
    """When someone likes to get going, used only to pace the itinerary (PR-6)."""

    EARLY_RISER = "early riser"
    LATE_RISER = "late riser"
    NIGHT_OWL = "night owl"


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date


@dataclass(frozen=True)
class MessagePhoto:
    # One of the image types Claude reads: image/jpeg, png, gif, or webp.
    media_type: str
    base64_data: str


class MediaKind(StrEnum):
    PHOTO = "photo"
    VOICE_NOTE = "voice note"


@dataclass(frozen=True)
class SharedMedia:
    """A photo or voice note a member sent, kept on disk (media.py)."""

    id: str
    kind: MediaKind
    # The file exactly as it was sent.
    original_path: Path
    # A copy the AI services can read: a JPEG photo, or audio OpenAI transcribes.
    readable_path: Path
    # A photo's description or a voice note's words. None if it couldn't be
    # put into words.
    transcript: str | None

    @property
    def addresses_scout(self) -> bool:
        """Whether a voice note says scout's name to it, like a spoken tag."""
        if self.kind is not MediaKind.VOICE_NOTE or self.transcript is None:
            return False
        return ADDRESSES_SCOUT.search(self.transcript) is not None

    @property
    def chat_label(self) -> str:
        """How it reads in the chat log, with where the original is kept."""
        if self.transcript is None:
            content = "couldn't be transcribed"
        elif self.kind is MediaKind.VOICE_NOTE:
            content = f'"{self.transcript}"'
        else:
            content = self.transcript
        return f"[{self.kind} {self.id} ({self.original_path}): {content}]"


@dataclass(frozen=True)
class IncomingMessage:
    space_id: str
    sender_phone: str
    text: str
    sent_at: datetime
    # Everyone in the chat, including people who haven't spoken yet. Empty when
    # the messaging provider can't list participants (for example, in a DM).
    participant_phones: tuple[str, ...] = ()
    # The photo or voice note the message carries, as scout kept it.
    media: SharedMedia | None = None
    # The line's ID for this message, so scout can react or reply to it. None
    # where there's no line, as in scout-simulate.
    message_id: str | None = None
    # The words of the message this one is a threaded reply to, if it is one
    # and the bridge could find them.
    reply_to_text: str | None = None

    @property
    def mentions_scout(self) -> bool:
        if ADDRESSES_SCOUT.search(self.text) is not None:
            return True
        return self.media is not None and self.media.addresses_scout

    @property
    def readable_text(self) -> str:
        """The words, after any photo's description or voice note's words."""
        if self.media is None:
            return self.text
        return f"{self.media.chat_label} {self.text}".strip()


@dataclass(frozen=True)
class IncomingReaction:
    """A tapback (or other reaction) a member added to a message in the chat."""

    space_id: str
    sender_phone: str
    # A tapback's name ("like"), or the emoji of any other reaction.
    tapback: str
    # The line's ID for the message it's on, and that message's words when the
    # bridge can find them.
    message_id: str
    message_text: str | None
    sent_at: datetime


@dataclass(frozen=True)
class PreferenceUpdate:
    """What a member shared in one message. None means "didn't mention it"."""

    display_name: str | None = None
    available_from: date | None = None
    available_to: date | None = None
    budget_usd: int | None = None
    home_city: str | None = None
    must_haves: list[str] | None = None
    chronotype: Chronotype | None = None


def is_majority(count: int, group_size: int) -> bool:
    """More than half the group: 2 of 3, 3 of 4, or both of 2. scout moves on
    once a majority has answered rather than waiting on everyone."""
    return count * 2 > group_size


@dataclass
class Member:
    phone: str
    display_name: str | None = None
    available_from: date | None = None
    available_to: date | None = None
    budget_usd: int | None = None
    home_city: str | None = None
    must_haves: list[str] = field(default_factory=list)
    # Optional, like must-haves: the plan goes ahead without it.
    chronotype: Chronotype | None = None

    @property
    def label(self) -> str:
        """How scout refers to this person in the chat."""
        return self.display_name or f"…{self.phone[-4:]}"

    @property
    def has_shared_preferences(self) -> bool:
        # Must-haves are optional: "anything works" is a valid answer.
        return all(
            value is not None
            for value in (
                self.available_from,
                self.available_to,
                self.budget_usd,
                self.home_city,
            )
        )

    @property
    def missing_preferences(self) -> list[str]:
        # Not a name: scout calls people by what the chat shows, and never asks.
        missing = []
        if self.available_from is None or self.available_to is None:
            missing.append("dates")
        if self.budget_usd is None:
            missing.append("budget")
        if self.home_city is None:
            missing.append("home city")
        return missing


@dataclass(frozen=True)
class DestinationOption:
    name: str
    estimated_cost_per_person_usd: int
    reason: str


@dataclass
class Poll:
    id: int
    options: list[DestinationOption]
    # Voter phone number -> index into options.
    votes: dict[str, int]


@dataclass(frozen=True)
class ItineraryDay:
    """One event on a day of the trip. A day with several events has several
    of these, in the order they happen."""

    day: date
    # What happens, e.g. "Night kayak on a bio bay".
    plan: str
    # When it starts, paced to the group. None for something loose, like a free
    # afternoon or a travel day.
    starts_at: time | None = None


@dataclass(frozen=True)
class DeckActivity:
    """One thing to do at the destination, as the activity deck shows it."""

    name: str
    # A line on what it is, e.g. "Boat from the hotel dock, gear included".
    description: str
    estimated_cost_usd: int
    photo_url: str | None = None


class Rating(IntEnum):
    """How a member rated an activity. The value is its weight in the
    group's tally, so a meh keeps an activity alive without beating a yeah."""

    NAH = 0
    MEH = 1
    YEAH = 2


@dataclass
class ActivityDeck:
    """The activities scout put to the group, and how each member rated them
    (AC-1)."""

    activities: list[DeckActivity]
    # Member phone -> 0-based index of an activity -> their rating. Only
    # members who have sent their picks are here, and only activities they
    # rated meh or yeah, so an empty dict means "sent, and nah to everything".
    picks: dict[str, dict[int, Rating]]

    def has_picks_from_a_majority(self, members: list[Member]) -> bool:
        sent = sum(1 for member in members if member.phone in self.picks)
        return is_majority(sent, len(members))

    def score(self, activity_index: int) -> int:
        return sum(
            ratings.get(activity_index, Rating.NAH) for ratings in self.picks.values()
        )


@dataclass(frozen=True)
class ItineraryAddOn:
    """Something only one member wanted, offered as optional rather than
    scheduled for everyone or dropped (IT-2)."""

    activity: str
    # The member's label, e.g. "Leo".
    wanted_by: str


@dataclass(frozen=True)
class ExpenseItem:
    """One line of an itemized receipt, and who split it."""

    name: str
    amount_cents: int
    # Phones of the members who share this item. Never empty.
    shared_by: tuple[str, ...]


@dataclass(frozen=True)
class NewExpense:
    """A cost one member paid, and what each member owes toward it.

    Costs the whole group shares and costs only a few shared are the same
    thing: the members left out of `shares` owe nothing.
    """

    payer_phone: str
    amount_cents: int
    # What it was for, e.g. "Airbnb" or "Casa Brisa dinner".
    description: str
    # Member phone -> cents they owe toward it. Adds up to `amount_cents`.
    shares: dict[str, int]
    paid_on: date | None = None
    # The receipt's lines, when the split followed what each person had. What
    # they don't add up to (tax, tip, fees, a discount) is in `shares` too.
    items: tuple[ExpenseItem, ...] = ()


@dataclass(frozen=True)
class Expense(NewExpense):
    """A saved expense. Its ID is how people refer to it in the chat."""

    id: int = field(kw_only=True)


@dataclass(frozen=True)
class PendingReceipt:
    """A receipt scout read and asked its payer to confirm before logging."""

    payer_phone: str
    merchant: str
    total_cents: int


@dataclass(frozen=True)
class Settlement:
    """A payment one member told scout they made to another, to settle up.

    scout never moves money. Members pay each other however they like, and
    this record keeps the settle-up plan showing only what's still owed.
    """

    payer_phone: str
    payee_phone: str
    amount_cents: int


@dataclass
class Trip:
    space_id: str
    stage: TripStage
    destination: str | None
    # Locked in when the destination poll closes. None if no dates worked for
    # everyone at that point.
    dates: DateWindow | None
    members: list[Member]
    open_poll: Poll | None
    itinerary: list[ItineraryDay]
    itinerary_add_ons: list[ItineraryAddOn]
    activity_deck: ActivityDeck | None
    expenses: list[Expense]
    settlements: list[Settlement]
    pending_receipt: PendingReceipt | None
    # The latest nearby places scout suggested, in the order it numbered them.
    place_suggestions: list[Place]

    def find_member(self, phone: str) -> Member:
        for member in self.members:
            if member.phone == phone:
                return member
        raise KeyError(f"{phone} is not a member of trip {self.space_id}")

    def find_member_by_label(self, label: str) -> Member | None:
        """The one member scout calls `label` in the chat (their name, or …1234
        before they've shared it), or None if no single member matches."""
        wanted = label.strip().casefold()
        matches = [
            member
            for member in self.members
            if wanted in (member.label.casefold(), f"…{member.phone[-4:]}")
        ]
        return matches[0] if len(matches) == 1 else None
