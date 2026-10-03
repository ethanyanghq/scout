"""The trip a group is planning, and the people planning it."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

# Matches "@scout", "scout,", "Scout?" but not "scouting".
SCOUT_MENTION = re.compile(r"\bscout\b", re.IGNORECASE)
# Matches "$164", "$ 40", "164 dollars", "40 bucks", "12.50 usd".
MONEY_MENTION = re.compile(
    r"\$\s?\d|\b\d[\d,]*(\.\d+)?\s?(dollars|bucks|usd)\b", re.IGNORECASE
)


class TripStage(StrEnum):
    COLLECTING_PREFERENCES = "collecting_preferences"
    VOTING = "voting"
    DESTINATION_CHOSEN = "destination_chosen"


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date


@dataclass(frozen=True)
class MessagePhoto:
    # One of the image types Claude reads: image/jpeg, png, gif, or webp.
    media_type: str
    base64_data: str


@dataclass(frozen=True)
class IncomingMessage:
    space_id: str
    sender_phone: str
    text: str
    sent_at: datetime
    # Everyone in the chat, including people who haven't spoken yet. Empty when
    # the messaging provider can't list participants (for example, in a DM).
    participant_phones: tuple[str, ...] = ()
    photo: MessagePhoto | None = None

    @property
    def mentions_scout(self) -> bool:
        return SCOUT_MENTION.search(self.text) is not None

    @property
    def mentions_money(self) -> bool:
        return MONEY_MENTION.search(self.text) is not None


@dataclass(frozen=True)
class PreferenceUpdate:
    """What a member shared in one message. None means "didn't mention it"."""

    display_name: str | None = None
    available_from: date | None = None
    available_to: date | None = None
    budget_usd: int | None = None
    home_city: str | None = None
    must_haves: list[str] | None = None


@dataclass
class Member:
    phone: str
    display_name: str | None = None
    available_from: date | None = None
    available_to: date | None = None
    budget_usd: int | None = None
    home_city: str | None = None
    must_haves: list[str] = field(default_factory=list)
    # Their Capital One Nessie sandbox account, opened on their first payment.
    nessie_account_id: str | None = None

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
        missing = []
        if self.display_name is None:
            missing.append("name")
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
    day: date
    # The one big thing planned for the day, e.g. "Night kayak on a bio bay".
    plan: str


@dataclass(frozen=True)
class Expense:
    """A shared cost one member paid, split evenly across the whole group."""

    id: int
    payer_phone: str
    amount_cents: int
    # What it was for, e.g. "Airbnb" or "Casa Brisa dinner".
    description: str


@dataclass(frozen=True)
class PendingReceipt:
    """A receipt scout read and asked its payer to confirm before logging."""

    payer_phone: str
    merchant: str
    total_cents: int


@dataclass(frozen=True)
class Settlement:
    """A payment one member made to another through scout to settle up."""

    payer_phone: str
    payee_phone: str
    amount_cents: int
    # False when Nessie was unreachable or not set up, so no sandbox money moved.
    went_through_nessie: bool


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
    expenses: list[Expense]
    settlements: list[Settlement]
    pending_receipt: PendingReceipt | None

    def find_member(self, phone: str) -> Member:
        for member in self.members:
            if member.phone == phone:
                return member
        raise KeyError(f"{phone} is not a member of trip {self.space_id}")
