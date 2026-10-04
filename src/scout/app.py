"""The HTTP endpoint the Photon bridge calls with each incoming text."""

import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from scout.ai_provider import connect_agent
from scout.conversation import Agent, handle_message, handle_reaction
from scout.dev_endpoints import create_dev_router
from scout.outgoing import Card, Link, Outgoing, React, Say
from scout.trip import IncomingMessage, IncomingReaction, MessagePhoto
from scout.trip_store import TripStore

# Only the bridge on this machine should reach scout, never the internet.
HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_DB_PATH = "scout.db"
ACTION_TYPES = {Say: "say", React: "react", Link: "link", Card: "card"}


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
    message_id: str | None = None
    reply_to_text: str | None = None


class IncomingTapback(BaseModel):
    space_id: str
    sender_phone: str
    # A tapback's name ("like"), or the emoji of any other reaction.
    tapback: str
    # The line's ID for the message it's on, and its words, or None if the
    # bridge can't find them.
    message_id: str
    message_text: str | None
    sent_at: datetime


class Actions(BaseModel):
    # Each action is its type ("say", "react", "link" or "card") plus that type's
    # fields in outgoing.py, which the bridge turns into iMessages.
    actions: list[dict]


def create_app(store: TripStore, agent: Agent) -> FastAPI:
    app = FastAPI(title="scout")

    # A plain `def` (not `async def`) makes FastAPI run this in a worker
    # thread, so the slow AI call doesn't freeze the server.
    @app.post("/messages")
    def receive_message(incoming: IncomingText) -> Actions:
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
            message_id=incoming.message_id,
            reply_to_text=incoming.reply_to_text,
        )
        return _as_actions(handle_message(message, store, agent))

    @app.post("/reactions")
    def receive_reaction(incoming: IncomingTapback) -> Actions:
        reaction = IncomingReaction(**incoming.model_dump())
        return _as_actions(handle_reaction(reaction, store))

    app.include_router(create_dev_router(store))
    return app


def _as_actions(outgoing: list[Outgoing]) -> Actions:
    return Actions(
        actions=[
            {"type": ACTION_TYPES[type(item)], **asdict(item)} for item in outgoing
        ]
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    store = TripStore(Path(os.environ.get("SCOUT_DB_PATH", DEFAULT_DB_PATH)))
    agent = connect_agent(store)
    port = int(os.environ.get("SCOUT_PORT", DEFAULT_PORT))
    uvicorn.run(create_app(store, agent), host=HOST, port=port)
