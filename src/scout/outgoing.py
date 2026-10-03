"""What scout sends to a chat: texts, tapbacks and link cards.

The bridge turns each one into an iMessage on whatever line the group uses,
and falls back to plain text where a line can't do the rest.
"""

from dataclasses import dataclass
from enum import StrEnum


class Tapback(StrEnum):
    LOVE = "love"
    LIKE = "like"
    DISLIKE = "dislike"
    LAUGH = "laugh"
    EMPHASIZE = "emphasize"
    QUESTION = "question"


@dataclass(frozen=True)
class Say:
    text: str
    # The message to thread this under, or None for the main chat.
    reply_to: str | None = None


@dataclass(frozen=True)
class React:
    message_id: str
    tapback: Tapback
    # Sent instead on lines that can't send tapbacks.
    fallback_text: str


@dataclass(frozen=True)
class Link:
    """A link sent on its own, so iMessage shows it as a card."""

    url: str


Outgoing = Say | React | Link


def as_plain_text(outgoing: Outgoing) -> str:
    """How something scout sent reads as text: in the chat log the agent
    sees, and in scout-simulate."""
    match outgoing:
        case Say(text=text):
            return text
        case React(tapback=tapback, fallback_text=fallback_text):
            return f"({tapback} tapback) {fallback_text}"
        case Link(url=url):
            return url
