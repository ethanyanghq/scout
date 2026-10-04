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
from scout.trip import IncomingMessage, MessagePhoto, Trip
from scout.trip_actions import TripActionError, TripActions
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

MODEL = "gpt-5.5"
# Low effort keeps simple replies near the PRD's ~10 second target (§9). OpenAI
# warns that web search answers get worse with reasoning off entirely.
REASONING_EFFORT = "low"
MAX_OUTPUT_TOKENS = 16_000
# OpenAI's web search opens and reads pages itself, so it covers both of
# Claude's web tools. Capped like Claude's to keep replies quick.
MAX_WEB_LOOKUPS_PER_REPLY = 3

# The Claude tool schemas already meet OpenAI's strict-mode rules (every
# property required, no extra properties), so they carry over unchanged.
OPENAI_TOOLS = [
    *(
        {
            "type": "function",
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
            "strict": True,
        }
        for tool in TOOL_DEFINITIONS
    ),
    # OpenAI runs the searches, so results arrive in its response with
    # nothing for us to run.
    {"type": "web_search"},
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
            self._store,
            trip.space_id,
            message.sender_phone,
            self._services,
            message.message_id,
        )
        conversation = [
            {"role": "user", "content": describe_situation(self._store, trip, message)}
        ]

        response = self._ask_openai(conversation)
        tool_rounds = 0
        while tool_calls := _function_calls(response.output):
            tool_rounds += 1
            if tool_rounds > MAX_TOOL_ROUNDS:
                logger.warning("Gave up after %d tool rounds", MAX_TOOL_ROUNDS)
                return actions.outbox
            # Send back everything, not just the calls: the API matches each
            # result to its call and needs the reasoning that led to it.
            conversation.extend(response.output)
            conversation.extend(_run_tool_calls(actions, tool_calls))
            response = self._ask_openai(conversation)

        if refusal := _refusal(response.output):
            logger.warning("OpenAI declined to respond: %s", refusal)
            return actions.outbox

        text = _reply_text(response.output)
        if not text or text == NO_REPLY:
            return actions.outbox
        return [*as_text_bubbles(text), *actions.outbox]

    def _ask_openai(self, conversation: list):
        response = self._client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=conversation,
            tools=OPENAI_TOOLS,
            max_tool_calls=MAX_WEB_LOOKUPS_PER_REPLY,
            reasoning={"effort": REASONING_EFFORT},
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        _log_web_lookups(response.output)
        return response


def _function_calls(output: list) -> list:
    return [item for item in output if item.type == "function_call"]


def _image_part(photo: MessagePhoto) -> dict:
    photo_url = f"data:{photo.media_type};base64,{photo.base64_data}"
    return {"type": "input_image", "image_url": photo_url}


def _run_tool_calls(actions: TripActions, tool_calls: list) -> list[dict]:
    """Runs every tool call in a response and returns one result per call."""
    results = []
    for call in tool_calls:
        tool_input = json.loads(call.arguments)
        try:
            outcome = run_tool(actions, call.name, tool_input)
        except TripActionError as error:
            outcome = f"Error: {error}"
        logger.info(describe_tool_call(call.name, tool_input, outcome))
        results.append(
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                # A photo the AI asked to see comes back as the image itself.
                "output": (
                    [_image_part(outcome)]
                    if isinstance(outcome, MessagePhoto)
                    else outcome
                ),
            }
        )
    return results


def _log_web_lookups(output: list) -> None:
    for item in output:
        if item.type == "web_search_call":
            logger.info("OpenAI ran web_search %s", item.action)


def _message_parts(output: list) -> list:
    return [part for item in output if item.type == "message" for part in item.content]


def _refusal(output: list) -> str | None:
    refusals = (
        part.refusal for part in _message_parts(output) if part.type == "refusal"
    )
    return next(refusals, None)


def _reply_text(output: list) -> str:
    # Text before a web search is the model narrating ("let me check that"),
    # so only what it wrote after the last search is the reply.
    last_search = max(
        (i for i, item in enumerate(output) if item.type == "web_search_call"),
        default=-1,
    )
    parts = _message_parts(output[last_search + 1 :])
    return "".join(part.text for part in parts if part.type == "output_text").strip()
