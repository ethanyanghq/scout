"""scout's brain: shows Claude the trip and the chat, then runs the tools it picks."""

import logging
from datetime import date
from pathlib import Path

import anthropic

from scout.agent_tools import TOOL_DEFINITIONS, run_tool
from scout.group_summary import DateWindow, format_window, summarize_group
from scout.money import format_usd
from scout.outside_services import NO_OUTSIDE_SERVICES, OutsideServices
from scout.settle_up import plan_payments
from scout.trip import IncomingMessage, Member, Trip
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
RECENT_MESSAGE_COUNT = 30
# If a safety classifier declines a request, the API retries it on a
# recommended fallback model instead of returning nothing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NO_REPLY = "NO_REPLY"
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

    def respond(self, trip: Trip, message: IncomingMessage) -> list[str]:
        """Returns the texts scout should send in reply, possibly none."""
        actions = TripActions(
            self._store, trip.space_id, message.sender_phone, self._services
        )
        conversation = [
            {"role": "user", "content": self._show_situation(trip, message)}
        ]

        response = self._ask_claude(conversation)
        tool_rounds = 0
        while response.stop_reason == "tool_use":
            tool_rounds += 1
            if tool_rounds > MAX_TOOL_ROUNDS:
                logger.warning("Gave up after %d tool rounds", MAX_TOOL_ROUNDS)
                return actions.outbox
            # Append the whole response, not just its text: the API needs the
            # tool_use blocks (and thinking) to match up the results we send.
            conversation.append({"role": "assistant", "content": response.content})
            conversation.append(
                {"role": "user", "content": _run_tool_calls(actions, response.content)}
            )
            response = self._ask_claude(conversation)

        if response.stop_reason == "refusal":
            logger.warning("Claude declined to respond: %s", response.stop_details)
            return actions.outbox

        reply = _reply_text(response.content)
        return [reply, *actions.outbox] if reply else actions.outbox

    def _ask_claude(self, conversation: list[dict]):
        return self._client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=conversation,
            output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

    def _show_situation(self, trip: Trip, message: IncomingMessage) -> list[dict]:
        """The first prompt: the situation in words, plus any photo just sent."""
        situation = {"type": "text", "text": self._describe_situation(trip, message)}
        if message.photo is None:
            return [situation]
        photo = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": message.photo.media_type,
                "data": message.photo.base64_data,
            },
        }
        return [photo, situation]

    def _describe_situation(self, trip: Trip, message: IncomingMessage) -> str:
        recent = self._store.recent_messages(trip.space_id, RECENT_MESSAGE_COUNT)
        labels = {member.phone: member.label for member in trip.members}
        chat = "\n".join(
            f"[{labels.get(logged.sender_phone, 'scout')}] {logged.text}"
            for logged in recent
        )
        sender = trip.find_member(message.sender_phone)
        tagged = (
            "It tags or addresses you."
            if message.mentions_scout
            else ("It does not tag you.")
        )
        if message.photo is not None:
            tagged += " It comes with the photo above."
        today = date.today()
        return (
            f"Today is {today:%A, %B} {today.day}, {today.year}.\n\n"
            f"# Trip state\n{_describe_trip(trip)}\n\n"
            f"# Recent chat, oldest first\n{chat}\n\n"
            f"# Newest message\nFrom {sender.label}. {tagged}\n"
            f"{message.text}"
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
        lines.extend(f"  {day.day:%a %Y-%m-%d}: {day.plan}" for day in trip.itinerary)
    lines.append("Members:")
    lines.extend(f"- {_describe_member(member)}" for member in trip.members)
    if summary.shared_window:
        lines.append(
            f"Dates that work for everyone: {format_window(summary.shared_window)}"
        )
    if summary.dates_conflict:
        lines.append("Dates that work for everyone: none, they conflict")
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
    if trip.place_suggestions:
        lines.append("Places you last suggested:")
        lines.extend(
            f"  {number}. {place.name}"
            for number, place in enumerate(trip.place_suggestions, start=1)
        )
    lines.extend(_describe_costs(trip))
    return "\n".join(lines)


def _describe_costs(trip: Trip) -> list[str]:
    """Expenses, what's still owed, and any receipt waiting to be confirmed."""
    lines = []
    if trip.expenses:
        lines.append("Expenses, split evenly across everyone:")
        lines.extend(
            f"  #{expense.id} {expense.description}: "
            f"{format_usd(expense.amount_cents)}, paid by "
            f"{trip.find_member(expense.payer_phone).label}"
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
        logger.info("Tool %s(%s) -> %s", block.name, block.input, outcome)
        results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": outcome,
                "is_error": is_error,
            }
        )
    return results


def _reply_text(content: list) -> str | None:
    text = "".join(block.text for block in content if block.type == "text").strip()
    if not text or text == NO_REPLY:
        return None
    return text
