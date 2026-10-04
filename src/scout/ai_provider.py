"""Picks the AI behind scout: Claude, or OpenAI when only an OpenAI key is set."""

import logging
import os

import anthropic
import openai

from scout.agent import ScoutAgent
from scout.conversation import Agent
from scout.openai_agent import OpenAIScoutAgent
from scout.outside_services import OutsideServices
from scout.speak_gate import AskModel, SpeakGate
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

# The gate answers one word, so the smallest, fastest models are plenty.
CLAUDE_GATE_MODEL = "claude-haiku-4-5"
OPENAI_GATE_MODEL = "gpt-5.4-mini"
# Room for the one-word answer, plus any reasoning a model does first.
GATE_MAX_OUTPUT_TOKENS = 100


def connect_agent(store: TripStore, services: OutsideServices) -> Agent:
    # With neither key set, scout still starts on Claude: replies that need
    # the model fail, but the ones handled in code (like counting votes) work.
    if _uses_openai():
        logger.info("Messages go to OpenAI, since no ANTHROPIC_API_KEY is set")
        return OpenAIScoutAgent(openai.OpenAI(), store, services)
    return ScoutAgent(anthropic.Anthropic(), store, services)


def connect_speak_gate(store: TripStore) -> SpeakGate:
    """The gate that decides whether scout speaks up on an untagged message,
    on the same provider as the agent."""
    if _uses_openai():
        return SpeakGate(_ask_openai(openai.OpenAI()), store)
    return SpeakGate(_ask_claude(anthropic.Anthropic()), store)


def _uses_openai() -> bool:
    return not os.environ.get("ANTHROPIC_API_KEY") and bool(
        os.environ.get("OPENAI_API_KEY")
    )


def _ask_claude(client: anthropic.Anthropic) -> AskModel:
    def ask(system: str, situation: str) -> str:
        response = client.messages.create(
            model=CLAUDE_GATE_MODEL,
            max_tokens=GATE_MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": situation}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    return ask


def _ask_openai(client: openai.OpenAI) -> AskModel:
    def ask(system: str, situation: str) -> str:
        response = client.responses.create(
            model=OPENAI_GATE_MODEL,
            instructions=system,
            input=situation,
            reasoning={"effort": "none"},
            max_output_tokens=GATE_MAX_OUTPUT_TOKENS,
        )
        return response.output_text

    return ask
