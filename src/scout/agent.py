"""scout's brain: shows Claude the trip and the chat, then runs the tools it picks."""

import logging
import re
from datetime import date
from pathlib import Path

import anthropic

from scout.activity_deck import describe_ratings
from scout.agent_tools import TOOL_DEFINITIONS, describe_tool_call, run_tool
from scout.expense_report import describe_split
from scout.group_summary import DateWindow, format_window, summarize_group
from scout.money import format_usd
from scout.outgoing import Outgoing, Say
from scout.outside_services import NO_OUTSIDE_SERVICES, OutsideServices
from scout.settle_up import plan_payments
from scout.speak_gate import is_addressed_to_scout
from scout.trip import IncomingMessage, ItineraryDay, Member, MessagePhoto, Trip
from scout.trip_actions import TripActionError, TripActions
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
# Low effort keeps simple replies near the PRD's ~10 second target (§9).
EFFORT = "low"
MAX_OUTPUT_TOKENS = 16_000
# Enough for a busy turn (save, summarize, poll) without letting a confused
# model loop forever.
MAX_TOOL_ROUNDS = 6
# If a safety classifier declines a request, the API retries it on a
# recommended fallback model instead of returning nothing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Anthropic runs web searches and page fetches on its own servers, so their
# results arrive inside Claude's response with nothing for us to run. They're
# kept out of TOOL_DEFINITIONS because the OpenAI agent can't use them. The caps
# keep a curious model from blowing the ~10 second reply target.
MAX_WEB_SEARCHES_PER_REPLY = 3
MAX_WEB_FETCHES_PER_REPLY = 2
MAX_FETCHED_PAGE_TOKENS = 10_000
WEB_TOOLS = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": MAX_WEB_SEARCHES_PER_REPLY,
    },
    {
        "type": "web_fetch_20260209",
        "name": "web_fetch",
        "max_uses": MAX_WEB_FETCHES_PER_REPLY,
        "max_content_tokens": MAX_FETCHED_PAGE_TOKENS,
    },
]
NO_REPLY = "NO_REPLY"
UNTAGGED_MESSAGE_NOTE = (
    "It does not tag you. A quick check guessed you might have something to "
    "add, and that check is often wrong, so reply NO_REPLY unless the group "
    "clearly needs you. A progress teaser after saving someone's details "
    "still goes out."
)
PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.md").read_text()


class ScoutAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        store: TripStore,
        services: OutsideServices = NO_OUTSIDE_SERVICES,
    ):
        self._client = client
        self._store = store
        self._services = services

    def respond(self, trip: Trip, message: IncomingMessage) -> list[Outgoing]:
        """Returns what scout should send in reply, possibly nothing."""
        actions = TripActions(
            self._store,
            trip.space_id,
            message.sender_phone,
            self._services,
            message.message_id,
        )
        conversation = [
            {"role": "user", "content": describe_situation(self._store, trip, message)}
        ]

        response = self._ask_claude(conversation)
        tool_rounds = 0
        while response.stop_reason in ("tool_use", "pause_turn"):
            tool_rounds += 1
            if tool_rounds > MAX_TOOL_ROUNDS:
                logger.warning("Gave up after %d tool rounds", MAX_TOOL_ROUNDS)
                return actions.outbox
            # Append the whole response, not just its text: the API needs the
            # tool_use blocks (and thinking) to match up the results we send.
            conversation.append({"role": "assistant", "content": response.content})
            # On pause_turn, Anthropic paused a long web lookup: sending the
            # conversation back unchanged lets it pick up where it left off.
            if response.stop_reason == "tool_use":
                conversation.append(
                    {
                        "role": "user",
                        "content": _run_tool_calls(actions, response.content),
                    }
                )
            response = self._ask_claude(conversation)

        if response.stop_reason == "refusal":
            logger.warning("Claude declined to respond: %s", response.stop_details)
            return actions.outbox

        reply = _reply_text(response.content)
        return [*as_text_bubbles(reply), *actions.outbox] if reply else actions.outbox

    def _ask_claude(self, conversation: list[dict]):
        response = self._client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[*TOOL_DEFINITIONS, *WEB_TOOLS],
            messages=conversation,
            output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        _log_web_lookups(response.content)
        return response


def _image_block(photo: MessagePhoto) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": photo.media_type,
            "data": photo.base64_data,
        },
    }


def as_text_bubbles(reply: str) -> list[Say]:
    """The model's reply as separate texts, the way people text: each
    paragraph (split by a blank line) becomes its own bubble."""
    paragraphs = (paragraph.strip() for paragraph in PARAGRAPH_BREAK.split(reply))
    return [Say(paragraph) for paragraph in paragraphs if paragraph]


def describe_situation(store: TripStore, trip: Trip, message: IncomingMessage) -> str:
    """The trip, the whole chat, and the newest message, in words for the model."""
    labels = {member.phone: member.label for member in trip.members}
    chat = "\n".join(
        f"[{labels.get(logged.sender_phone, 'scout')}] {logged.text}"
        for logged in store.chat_history(trip.space_id)
    )
    sender = trip.find_member(message.sender_phone)
    tagged = (
        "It tags or addresses you."
        if is_addressed_to_scout(store, message)
        else UNTAGGED_MESSAGE_NOTE
    )
    if message.reply_to_text is not None:
        tagged += f' It replies in a thread to: "{message.reply_to_text}".'
    if not store.has_scout_spoken(trip.space_id):
        tagged += " You haven't said anything in this chat yet."
    today = date.today()
    return (
        f"Today is {today:%A, %B} {today.day}, {today.year}.\n\n"
        f"# Trip state\n{_describe_trip(trip)}\n\n"
        f"# The chat so far, oldest first\n{chat}\n\n"
        f"# Newest message\nFrom {sender.label}. {tagged}\n"
        f"{message.readable_text}"
    )


def _describe_trip(trip: Trip) -> str:
    summary = summarize_group(trip.members)
    lines = [f"Stage: {trip.stage}"]
    if trip.destination:
        lines.append(f"Chosen destination: {trip.destination}")
    if trip.dates:
        lines.append(f"Trip dates: {format_window(trip.dates)} {trip.dates.start.year}")
    if trip.itinerary:
        lines.append("Itinerary:")
        lines.extend(f"  {_describe_itinerary_day(day)}" for day in trip.itinerary)
        lines.extend(
            f"  Optional add-on: {add_on.activity} ({add_on.wanted_by})"
            for add_on in trip.itinerary_add_ons
        )
    lines.append("Members:")
    lines.extend(f"- {_describe_member(member)}" for member in trip.members)
    if summary.shared_window:
        lines.append(
            f"Dates that work for everyone: {format_window(summary.shared_window)}"
        )
    if summary.dates_conflict:
        lines.append("Dates that work for everyone: none, they conflict")
    if summary.pace:
        lines.append(f"Group pace: {summary.pace}s")
    waiting_on = ", ".join(m.label for m in summary.members_still_to_share)
    lines.append(f"Still waiting on: {waiting_on or 'nobody'}")
    if trip.open_poll:
        lines.append("Open poll:")
        for number, option in enumerate(trip.open_poll.options, start=1):
            voters = [
                trip.find_member(phone).label
                for phone, choice in trip.open_poll.votes.items()
                if choice == number - 1
            ]
            lines.append(
                f"  {number}. {option.name} (~${option.estimated_cost_per_person_usd})"
                f" votes: {', '.join(voters) or 'none'}"
            )
    if trip.activity_deck:
        lines.extend(_describe_activity_deck(trip))
    if trip.place_suggestions:
        lines.append("Places you last suggested:")
        lines.extend(
            f"  {number}. {place.name}"
            for number, place in enumerate(trip.place_suggestions, start=1)
        )
    lines.extend(_describe_costs(trip))
    return "\n".join(lines)


def _describe_activity_deck(trip: Trip) -> list[str]:
    """Each deck activity and who said yeah or meh to it, and who hasn't sent
    picks."""
    deck = trip.activity_deck
    waiting_on = [m.label for m in trip.members if m.phone not in deck.picks]
    lines = [
        "Activity deck (still waiting on picks from: "
        f"{', '.join(waiting_on) or 'nobody'}):"
    ]
    for number, activity in enumerate(deck.activities, start=1):
        lines.append(
            f"  {number}. {activity.name} (~${activity.estimated_cost_usd}) "
            f"{describe_ratings(deck, trip.members, number - 1)}"
        )
    return lines


def _describe_costs(trip: Trip) -> list[str]:
    """Expenses, what's still owed, and any receipt waiting to be confirmed."""
    lines = []
    if trip.expenses:
        lines.append("Expenses:")
        lines.extend(
            f"  #{expense.id} {expense.description}: "
            f"{format_usd(expense.amount_cents)}, paid by "
            f"{trip.find_member(expense.payer_phone).label}, "
            f"{describe_split(expense, trip.members)}"
            for expense in trip.expenses
        )
        lines.append("Payments still owed:")
        lines.extend(
            f"  {payment.payer.label} → {payment.payee.label} "
            f"{format_usd(payment.amount_cents)}"
            for payment in plan_payments(trip)
        )
    if trip.pending_receipt:
        receipt = trip.pending_receipt
        lines.append(
            f"Receipt waiting for {trip.find_member(receipt.payer_phone).label} "
            f"to confirm: {receipt.merchant}, {format_usd(receipt.total_cents)}"
        )
    return lines


def _describe_itinerary_day(day: ItineraryDay) -> str:
    starts_at = f" {day.starts_at:%H:%M}" if day.starts_at else ""
    return f"{day.day:%a %Y-%m-%d}{starts_at}: {day.plan}"


def _describe_member(member: Member) -> str:
    details = []
    if member.available_from and member.available_to:
        window = DateWindow(member.available_from, member.available_to)
        details.append(f"{format_window(window)} {member.available_from.year}")
    if member.budget_usd is not None:
        details.append(f"${member.budget_usd}")
    if member.home_city:
        details.append(f"from {member.home_city}")
    if member.must_haves:
        details.append(f"must-haves: {', '.join(member.must_haves)}")
    if member.chronotype:
        details.append(member.chronotype)
    if member.missing_preferences:
        details.append(f"missing: {', '.join(member.missing_preferences)}")
    return f"{member.label}: {'; '.join(details)}"


def _run_tool_calls(actions: TripActions, content: list) -> list[dict]:
    """Runs every tool call in a response and returns all results together."""
    results = []
    for block in content:
        if block.type != "tool_use":
            continue
        try:
            outcome = run_tool(actions, block.name, block.input)
            is_error = False
        except TripActionError as error:
            outcome = f"Error: {error}"
            is_error = True
        logger.info(describe_tool_call(block.name, block.input, outcome))
        results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                # A photo the AI asked to see comes back as the image itself.
                "content": (
                    [_image_block(outcome)]
                    if isinstance(outcome, MessagePhoto)
                    else outcome
                ),
                "is_error": is_error,
            }
        )
    return results


def _log_web_lookups(content: list) -> None:
    for block in content:
        if block.type == "server_tool_use":
            logger.info("Claude ran %s %s", block.name, block.input)


def _reply_text(content: list) -> str | None:
    # Text before a web lookup is Claude narrating ("let me check that"), so
    # only what it wrote after the last result is the reply.
    last_result = max(
        (i for i, block in enumerate(content) if block.type.endswith("_tool_result")),
        default=-1,
    )
    text = "".join(
        block.text for block in content[last_result + 1 :] if block.type == "text"
    ).strip()
    if not text or text == NO_REPLY:
        return None
    return text
