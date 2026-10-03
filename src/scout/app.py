"""The HTTP endpoint the Photon bridge calls with each incoming text."""

import logging
import os
from datetime import datetime
from pathlib import Path

import anthropic
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from scout.agent import ScoutAgent
from scout.conversation import handle_message
from scout.trip import IncomingMessage
from scout.trip_store import TripStore

# Only the bridge on this machine should reach scout, never the internet.
HOST = "127.0.0.1"
PORT = 8787
DEFAULT_DB_PATH = "scout.db"


class IncomingText(BaseModel):
    space_id: str
    sender_phone: str
    text: str
    sent_at: datetime
    participant_phones: list[str] = []


class Replies(BaseModel):
    replies: list[str]


def create_app(store: TripStore, agent: ScoutAgent) -> FastAPI:
    app = FastAPI(title="scout")

    # A plain `def` (not `async def`) makes FastAPI run this in a worker
    # thread, so the slow Claude call doesn't freeze the server.
    @app.post("/messages")
    def receive_message(incoming: IncomingText) -> Replies:
        message = IncomingMessage(
            space_id=incoming.space_id,
            sender_phone=incoming.sender_phone,
            text=incoming.text,
            sent_at=incoming.sent_at,
            participant_phones=tuple(incoming.participant_phones),
        )
        return Replies(replies=handle_message(message, store, agent))

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    store = TripStore(Path(os.environ.get("SCOUT_DB_PATH", DEFAULT_DB_PATH)))
    agent = ScoutAgent(anthropic.Anthropic(), store)
    uvicorn.run(create_app(store, agent), host=HOST, port=PORT)
