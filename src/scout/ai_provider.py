"""Picks the AI behind scout: Claude, or OpenAI when only an OpenAI key is set."""

import logging
import os

import anthropic
import openai

from scout.agent import ScoutAgent
from scout.conversation import Agent
from scout.openai_agent import OpenAIScoutAgent
from scout.outside_services import OutsideServices
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)


def connect_agent(store: TripStore, services: OutsideServices) -> Agent:
    # With neither key set, scout still starts on Claude: replies that need
    # the model fail, but the ones handled in code (like counting votes) work.
    if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("OPENAI_API_KEY"):
        logger.info("Tagged messages go to OpenAI, since no ANTHROPIC_API_KEY is set")
        return OpenAIScoutAgent(openai.OpenAI(), store, services)
    return ScoutAgent(anthropic.Anthropic(), store, services)
