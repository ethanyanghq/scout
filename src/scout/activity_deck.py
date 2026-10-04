"""The activity deck: what each member is up for at the destination (AC-1 to AC-3).

Picks come back as an ordinary text, "@scout my picks: Scuba · Pass · Food
tour", because Linq flattens a card's own reply to one unreadable character.
The card's Send button fills that text in from the options people tapped;
anyone without the card types the activity numbers instead.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from scout import polls
from scout.places import GooglePlaces
from scout.trip import ActivityDeck, DeckActivity, Member

PICKS_LEAD = "@scout my picks:"
# What the card calls not wanting an activity. It's in the sent text, but it
# isn't a pick.
PASS_LABEL = "Pass"
MIN_DECK_ACTIVITIES = 3
MAX_DECK_ACTIVITIES = 8
# The card joins picks with " · ", and people typing use commas.
PICK_SEPARATOR = re.compile(r"[·,]")


def parse_picks(text: str, activity_names: list[str]) -> list[int] | None:
    """The 0-based indexes of the activities a picks message is in for.

    None if the message isn't a picks message, or names something that isn't
    on the deck, so a person can sort it out in words instead.
    """
    message = text.strip()
    if not message.casefold().startswith(PICKS_LEAD.casefold()):
        return None
    picks = []
    for answer in PICK_SEPARATOR.split(message[len(PICKS_LEAD) :]):
        answer = answer.strip()
        if not answer or answer.casefold() == PASS_LABEL.casefold():
            continue
        index = polls.parse_vote(answer, activity_names)
        if index is None:
            return None
        if index not in picks:
            picks.append(index)
    return sorted(picks)


def format_deck(destination: str, activities: list[DeckActivity]) -> str:
    """The deck as text, for phones that can't open its card."""
    lines = [f"what are you up for in {destination}?"]
    for number, activity in enumerate(activities, start=1):
        lines.append(f"{number}. {activity.name} · ~${activity.estimated_cost_usd:,}")
        lines.append(f"   {activity.description}")
    lines.append(f'reply with the numbers you\'d do, like "{PICKS_LEAD} 1, 3"')
    return "\n".join(lines)


def format_tally(deck: ActivityDeck, members: list[Member]) -> str:
    """Who's in for what, once everyone has sent their picks: the activities
    everyone wants first, down to the ones nobody does."""
    fans = [
        [m.label for m in members if index in deck.picks.get(m.phone, [])]
        for index in range(len(deck.activities))
    ]
    lines = ["everyone's picks are in:"]
    for count in sorted({len(f) for f in fans}, reverse=True):
        who_wants = _describe_fan_count(count, len(members))
        names = [
            # Naming who keeps one person's pick from looking like nobody's.
            f"{activity.name} ({who[0]})" if who_wants == "just one" else activity.name
            for activity, who in zip(deck.activities, fans, strict=True)
            if len(who) == count
        ]
        lines.append(f"{who_wants}: {', '.join(names)}")
    return "\n".join(lines)


def _describe_fan_count(count: int, member_count: int) -> str:
    if count == member_count:
        return "everyone"
    if count == 1:
        return "just one"
    if count == 0:
        return "nobody"
    return f"{count} of {member_count}"


def find_deck_photos(
    places: GooglePlaces, destination: str, activities: list[DeckActivity]
) -> tuple[str | None, list[DeckActivity]]:
    """A photo of the destination, and the activities with a photo each where
    Google has one, all looked up at once. Raises PlacesError if Google can't
    be reached."""
    queries = [destination, *(f"{a.name} in {destination}" for a in activities)]
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        found = list(pool.map(lambda q: places.find_photographed(q, 1), queries))
    photos = [
        place.photo_urls[0] if place and place.photo_urls else None for place in found
    ]
    destination_photo, *activity_photos = photos
    return destination_photo, [
        replace(activity, photo_url=photo)
        for activity, photo in zip(activities, activity_photos, strict=True)
    ]
