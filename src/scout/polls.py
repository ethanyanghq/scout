"""Reading votes from plain texts and deciding a poll's winner.

SMS has no buttons, so members vote by replying with a number or an option's
name. Parsing is deliberately strict: "tulum looks pricey" is chatter, not a
vote. Anything looser goes to the agent, which can record a vote by tool.
"""

import re
from dataclasses import dataclass

from scout.trip import SCOUT_MENTION, DestinationOption, Poll

VOTE_PREFIXES = ("i vote for", "i vote", "vote for", "vote", "option", "number", "#")


@dataclass(frozen=True)
class PollResult:
    winner: DestinationOption
    winning_votes: int
    # Options that tied with the winner on votes; empty when the win was outright.
    tied_with: list[DestinationOption]


def parse_vote(text: str, option_names: list[str]) -> int | None:
    """Returns the 0-based index of the option a message votes for, or None.

    Works for any numbered list scout posts: destinations, or places nearby.
    """
    vote = _normalize(text)
    for prefix in VOTE_PREFIXES:
        if vote.startswith(prefix):
            vote = vote.removeprefix(prefix).strip()
            break

    if vote.isdigit():
        number = int(vote)
        return number - 1 if 1 <= number <= len(option_names) else None

    for index, name in enumerate(option_names):
        full_name = _normalize(name)
        # "Tulum, Mexico" can be voted for as just "tulum".
        short_name = _normalize(name.split(",")[0])
        if vote in (full_name, short_name):
            return index
    return None


def decide_winner(poll: Poll) -> PollResult | None:
    """Most votes wins. Ties go to the cheapest option. None if nobody voted."""
    if not poll.votes:
        return None
    counts = count_votes(poll)
    top_count = max(counts)
    leaders = [
        option
        for option, count in zip(poll.options, counts, strict=True)
        if count == top_count
    ]
    winner = min(leaders, key=lambda option: option.estimated_cost_per_person_usd)
    return PollResult(
        winner=winner,
        winning_votes=top_count,
        tied_with=[option for option in leaders if option != winner],
    )


def count_votes(poll: Poll) -> list[int]:
    counts = [0] * len(poll.options)
    for option_index in poll.votes.values():
        counts[option_index] += 1
    return counts


def format_poll(options: list[DestinationOption]) -> str:
    lines = ["🗳️ Where should we go? Reply with a number:"]
    for number, option in enumerate(options, start=1):
        lines.append(
            f"{number}. {option.name} (~${option.estimated_cost_per_person_usd:,}"
            f"/person est.): {option.reason}"
        )
    return "\n".join(lines)


def format_result(result: PollResult, voter_count: int) -> str:
    winner = result.winner
    if not result.tied_with:
        return (
            f"🎉 Poll closed! {winner.name} wins with {result.winning_votes} "
            f"of {voter_count} votes."
        )
    tied_names = " and ".join(option.name for option in [*result.tied_with, winner])
    cheaper_than = ", ".join(
        f"~${option.estimated_cost_per_person_usd:,}" for option in result.tied_with
    )
    return (
        f"🗳️ It's a tie between {tied_names} ({result.winning_votes} votes each). "
        f"I'd go with {winner.name}: it's the cheapest at "
        f"~${winner.estimated_cost_per_person_usd:,}/person vs {cheaper_than}."
    )


def _normalize(text: str) -> str:
    without_mention = SCOUT_MENTION.sub(" ", text.lower())
    without_punctuation = re.sub(r"[^\w\s#]", " ", without_mention)
    return " ".join(without_punctuation.split())
