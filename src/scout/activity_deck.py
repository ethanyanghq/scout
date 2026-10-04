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
from scout.trip import ActivityDeck, DeckActivity, Member, Rating

PICKS_LEAD = "@scout my picks:"
RATING_WORDS = {rating.name.lower(): rating for rating in Rating}
MIN_DECK_ACTIVITIES = 3
MAX_DECK_ACTIVITIES = 8
# The card joins picks with " · ", and people typing use commas.
PICK_SEPARATOR = re.compile(r"[·,]")


def parse_picks(text: str, activity_names: list[str]) -> dict[int, Rating] | None:
    """The meh and yeah ratings in a picks message, by 0-based activity index.

    None if the message isn't a picks message, or names something that isn't
    on the deck, so a person can sort it out in words instead.
    """
    message = text.strip()
    if not message.casefold().startswith(PICKS_LEAD.casefold()):
        return None
    ratings: dict[int, Rating] = {}
    for answer in PICK_SEPARATOR.split(message[len(PICKS_LEAD) :]):
        answer = answer.strip()
        if not answer:
            continue
        activity, rating = _split_rating(answer)
        index = polls.parse_vote(activity, activity_names)
        if index is None:
            return None
        ratings[index] = rating
    return {index: r for index, r in sorted(ratings.items()) if r != Rating.NAH}


def _split_rating(answer: str) -> tuple[str, Rating]:
    """ "Food tour meh" as ("Food tour", MEH). With no rating word it's a yeah."""
    activity, _, last_word = answer.rpartition(" ")
    rating = RATING_WORDS.get(last_word.strip(":").casefold())
    if rating is None or not activity:
        return answer, Rating.YEAH
    return activity.strip().rstrip(":"), rating


def format_deck(destination: str, activities: list[DeckActivity]) -> str:
    """The deck as text, for phones that can't open its card."""
    lines = [f"what are you up for in {destination}?"]
    for number, activity in enumerate(activities, start=1):
        lines.append(f"{number}. {activity.name} · ~${activity.estimated_cost_usd:,}")
        lines.append(f"   {activity.description}")
    lines.append(
        "reply with how you feel about each number (yeah, meh or nah), "
        f'like "{PICKS_LEAD} 1 yeah, 2 meh, 3 nah"'
    )
    return "\n".join(lines)


def format_tally(deck: ActivityDeck, members: list[Member]) -> str:
    """Everyone's swipes once all are in, best-liked activity first (a yeah
    counts double a meh), naming who swiped what so one person's yeah doesn't
    look like nobody's."""
    by_score = sorted(range(len(deck.activities)), key=lambda index: -deck.score(index))
    lines = ["everyone's picks are in, best first:"]
    for index in by_score:
        lines.append(
            f"{deck.activities[index].name}: {describe_ratings(deck, members, index)}"
        )
    return "\n".join(lines)


def describe_ratings(deck: ActivityDeck, members: list[Member], index: int) -> str:
    """Who said yeah and who said meh to one activity, or "nobody"."""
    parts = []
    for rating in (Rating.YEAH, Rating.MEH):
        who = [
            m.label for m in members if deck.picks.get(m.phone, {}).get(index) == rating
        ]
        if who:
            parts.append(f"{rating.name.lower()} {', '.join(who)}")
    return " · ".join(parts) or "nobody"


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
