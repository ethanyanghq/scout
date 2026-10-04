"""The one-on-one chat each member has with scout before joining a group.

On Linq's free line, a member has to text scout privately before scout can be
added to their group, and iMessage gives scout only a phone number. So scout
uses that first text to ask what to call them, and remembers the answer for
every group they are in.
"""

import re

from scout.outgoing import Outgoing, Say
from scout.trip import IncomingMessage
from scout.trip_store import TripStore

ASK_NAME_REPLY = (
    "hi, i'm scout 👋 i help friend groups plan trips. what should i call you?"
)
ASK_AGAIN_REPLY = "just your first name is fine, what should i call you?"
NEXT_STEP = "add me to your group chat and i'll take it from there"
GROUPS_ONLY_REPLY = (
    "{name}, I only work within group chats. "
    "Add me to one and I'll help you plan a trip!"
)
LONGEST_NAME_WORDS = 3

# "i'm Maya", "my name is Maya", "call me Maya"
NAME_LEAD = re.compile(
    r"^(?:hi|hey|hello)?[\s,!.]*"
    r"(?:i'?m|i am|it'?s|its|this is|my name is|name'?s|call me)\s+",
    re.IGNORECASE,
)


def is_private_chat(message: IncomingMessage) -> bool:
    """Whether the message is in a chat of only the sender and scout. Linq lists
    a chat's members without scout, so a private chat lists just the sender."""
    return message.participant_phones == (message.sender_phone,)


def handle_private_message(
    message: IncomingMessage, store: TripStore
) -> list[Outgoing]:
    """Asks a new person for their name, saves what they answer, and after that
    points them to a group chat."""
    phone = message.sender_phone
    if not store.has_asked_for_name(phone):
        store.note_name_asked(phone)
        return [Say(ASK_NAME_REPLY)]
    known_name = store.find_name(phone)
    if known_name is not None:
        return [Say(GROUPS_ONLY_REPLY.format(name=known_name))]

    name = parse_name(message.text)
    if name is None:
        return [Say(ASK_AGAIN_REPLY)]
    store.save_name(phone, name)
    return [Say(f"nice to meet you, {name}! {NEXT_STEP}")]


def parse_name(reply: str) -> str | None:
    """The name in a reply like "Maya" or "it's Maya", or None if it reads as a
    sentence rather than a name."""
    words = NAME_LEAD.sub("", reply.strip()).strip(" .!,").split()
    if not 1 <= len(words) <= LONGEST_NAME_WORDS:
        return None
    return " ".join(word[0].upper() + word[1:] for word in words)
