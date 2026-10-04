"""scout's brain on OpenAI: the same prompt, tools, and trip as the Claude agent."""

import json
import logging

import openai

from scout.agent import (
    MAX_TOOL_ROUNDS,
    NO_REPLY,
    SYSTEM_PROMPT,
    as_text_bubbles,
    describe_situation,
)
from scout.agent_tools import TOOL_DEFINITIONS, describe_tool_call, run_tool
from scout.outgoing import Outgoing
from scout.outside_services import NO_OUTSIDE_SERVICES, OutsideServices
from scout.trip import IncomingMessage, Trip
from scout.trip_actions import TripActionError, TripActions
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

MODEL = "gpt-5.5"
# Chat Completions only allows tools on gpt-5.5 with reasoning off. That also
# keeps replies well inside the PRD's ~10 second target (§9).
REASONING_EFFORT = "none"
MAX_OUTPUT_TOKENS = 16_000

# The Claude tool schemas already meet OpenAI's strict-mode rules (every
# property required, no extra properties), so they carry over unchanged.
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
            "strict": True,
        },
    }
    for tool in TOOL_DEFINITIONS
]


class OpenAIScoutAgent:
    def __init__(
        self,
        client: openai.OpenAI,
        store: TripStore,
        services: OutsideServices = NO_OUTSIDE_SERVICES,
    ):
        self._client = client
        self._store = store
        self._services = services

    def respond(self, trip: Trip, message: IncomingMessage) -> list[Outgoing]:
        """Returns what scout should send in reply, possibly nothing."""
        actions = TripActions(
            self._store, trip.space_id, message.sender_phone, self._services
        )
        conversation = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._show_situation(trip, message)},
        ]

        reply = self._ask_openai(conversation)
        tool_rounds = 0
        while reply.tool_calls:
            tool_rounds += 1
            if tool_rounds > MAX_TOOL_ROUNDS:
                logger.warning("Gave up after %d tool rounds", MAX_TOOL_ROUNDS)
                return actions.outbox
            # The API matches each tool result to a call in this message.
            conversation.append(reply.model_dump(exclude_none=True))
            conversation.extend(_run_tool_calls(actions, reply.tool_calls))
            reply = self._ask_openai(conversation)

        if reply.refusal:
            logger.warning("OpenAI declined to respond: %s", reply.refusal)
            return actions.outbox

        text = (reply.content or "").strip()
        if not text or text == NO_REPLY:
            return actions.outbox
        return [*as_text_bubbles(text), *actions.outbox]

    def _ask_openai(self, conversation: list[dict]):
        response = self._client.chat.completions.create(
            model=MODEL,
            messages=conversation,
            tools=OPENAI_TOOLS,
            reasoning_effort=REASONING_EFFORT,
            max_completion_tokens=MAX_OUTPUT_TOKENS,
        )
        return response.choices[0].message

    def _show_situation(self, trip: Trip, message: IncomingMessage) -> list[dict]:
        """The first prompt: any photo just sent, then the situation in words."""
        situation = {
            "type": "text",
            "text": describe_situation(self._store, trip, message),
        }
        if message.photo is None:
            return [situation]
        photo_url = (
            f"data:{message.photo.media_type};base64,{message.photo.base64_data}"
        )
        photo = {"type": "image_url", "image_url": {"url": photo_url}}
        return [photo, situation]


def _run_tool_calls(actions: TripActions, tool_calls: list) -> list[dict]:
    """Runs every tool call in a reply and returns one result message per call."""
    results = []
    for call in tool_calls:
        tool_input = json.loads(call.function.arguments)
        try:
            outcome = run_tool(actions, call.function.name, tool_input)
        except TripActionError as error:
            outcome = f"Error: {error}"
        logger.info(describe_tool_call(call.function.name, tool_input, outcome))
        results.append({"role": "tool", "tool_call_id": call.id, "content": outcome})
    return results
