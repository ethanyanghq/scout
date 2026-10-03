"""The HTTP endpoint the Photon bridge calls with each incoming text."""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import anthropic
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from scout.agent import ScoutAgent
from scout.conversation import handle_message
from scout.outside_services import connect_outside_services
from scout.trip import IncomingMessage, MessagePhoto
from scout.trip_store import TripStore

# Only the bridge on this machine should reach scout, never the internet.
HOST = "127.0.0.1"
PORT = 8787
DEFAULT_DB_PATH = "scout.db"


class IncomingPhoto(BaseModel):
    # The image types Claude can read. The bridge converts iPhone HEIC photos
    # to JPEG before sending them.
    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"]
    base64_data: str


class IncomingText(BaseModel):
    space_id: str
    sender_phone: str
    # Empty when someone sends only a photo.
    text: str
    sent_at: datetime
    participant_phones: list[str] = []
    photo: IncomingPhoto | None = None


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
            photo=(
                MessagePhoto(incoming.photo.media_type, incoming.photo.base64_data)
                if incoming.photo
                else None
            ),
        )
        return Replies(replies=handle_message(message, store, agent))

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    store = TripStore(Path(os.environ.get("SCOUT_DB_PATH", DEFAULT_DB_PATH)))
    agent = ScoutAgent(anthropic.Anthropic(), store, connect_outside_services())
    uvicorn.run(create_app(store, agent), host=HOST, port=PORT)
