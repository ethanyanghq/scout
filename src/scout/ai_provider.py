"""Picks the AI behind scout: Claude, or OpenAI when only an OpenAI key is set."""

import os

import anthropic
import openai

from scout.agent import ScoutAgent
from scout.conversation import Agent
from scout.openai_agent import OpenAIScoutAgent
from scout.outside_services import connect_outside_services
from scout.trip_store import TripStore


def connect_agent(store: TripStore) -> Agent:
    # With neither key set, scout still starts on Claude: replies that need
    # the model fail, but the ones handled in code (like counting votes) work.
    if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("OPENAI_API_KEY"):
        return OpenAIScoutAgent(openai.OpenAI(), store, connect_outside_services())
    return ScoutAgent(anthropic.Anthropic(), store, connect_outside_services())
