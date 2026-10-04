"""The HTTP endpoint the Photon bridge calls with each incoming text."""

import base64
import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from scout.ai_provider import connect_agent, connect_speak_gate
from scout.calendar_feed import build_calendar_feed
from scout.conversation import Agent, Gate, handle_message, handle_reaction
from scout.dev_endpoints import create_dev_router
from scout.media import Attachment, MediaLibrary
from scout.openai_transcriber import connect_transcriber
from scout.outgoing import Card, Link, Outgoing, React, Say
from scout.outside_services import (
    NO_OUTSIDE_SERVICES,
    OutsideServices,
    connect_outside_services,
)
from scout.trip import IncomingMessage, IncomingReaction
from scout.trip_store import TripStore

logger = logging.getLogger(__name__)

# Only the bridge on this machine should reach scout, never the internet.
HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_DB_PATH = "scout.db"
DEFAULT_MEDIA_DIR = "media"
# The tunnel that makes calendar feeds public adds this header, and the bridge
# on this machine never does.
TUNNEL_HEADER = "x-forwarded-for"
PUBLIC_PATH_PREFIX = "/calendars/"
ACTION_TYPES = {Say: "say", React: "react", Link: "link", Card: "card"}


class IncomingAttachment(BaseModel):
    # A photo (image/...) or voice note (audio/...), exactly as it was sent,
    # like an iPhone's image/heic or audio/x-caf. scout converts it (media.py).
    media_type: str = Field(pattern=r"^(image|audio)/")
    base64_data: str


class IncomingText(BaseModel):
    space_id: str
    sender_phone: str
    # Empty when someone sends only a photo or voice note.
    text: str
    sent_at: datetime
    participant_phones: list[str] = []
    attachment: IncomingAttachment | None = None
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


def create_app(
    store: TripStore,
    agent: Agent,
    gate: Gate,
    media: MediaLibrary,
    services: OutsideServices = NO_OUTSIDE_SERVICES,
) -> FastAPI:
    app = FastAPI(title="scout")

    @app.middleware("http")
    async def keep_the_tunnel_to_calendars(request: Request, call_next):
        # /messages and /dev are for this machine only, so a request that came
        # through the tunnel gets nothing but calendar feeds.
        came_through_tunnel = TUNNEL_HEADER in request.headers
        if came_through_tunnel and not request.url.path.startswith(PUBLIC_PATH_PREFIX):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return await call_next(request)

    # A plain `def` (not `async def`) makes FastAPI run this in a worker
    # thread, so the slow AI and transcription calls don't freeze the server.
    @app.post("/messages")
    def receive_message(incoming: IncomingText) -> Actions:
        kept = (
            media.keep(incoming.space_id, _as_attachment(incoming.attachment))
            if incoming.attachment
            else None
        )
        message = IncomingMessage(
            space_id=incoming.space_id,
            sender_phone=incoming.sender_phone,
            text=incoming.text,
            sent_at=incoming.sent_at,
            participant_phones=tuple(incoming.participant_phones),
            media=kept,
            message_id=incoming.message_id,
            reply_to_text=incoming.reply_to_text,
            received_at=datetime.now(UTC),
        )
        return _as_actions(handle_message(message, store, agent, gate, services))

    @app.post("/reactions")
    def receive_reaction(incoming: IncomingTapback) -> Actions:
        reaction = IncomingReaction(**incoming.model_dump())
        return _as_actions(handle_reaction(reaction, store))

    @app.get("/calendars/{space_id}.ics")
    def show_calendar(space_id: str) -> Response:
        """The chat's itinerary as a calendar feed that phones subscribe to."""
        trip = store.get_trip(space_id)
        if trip is None or not trip.itinerary:
            raise HTTPException(404, "This chat has no itinerary yet.")
        feed = build_calendar_feed(trip, datetime.now(UTC))
        return Response(feed, media_type="text/calendar")

    app.include_router(create_dev_router(store, media))
    return app


def _as_attachment(incoming: IncomingAttachment) -> Attachment:
    return Attachment(incoming.media_type, base64.b64decode(incoming.base64_data))


def _as_actions(outgoing: list[Outgoing]) -> Actions:
    return Actions(
        actions=[
            {"type": ACTION_TYPES[type(item)], **asdict(item)} for item in outgoing
        ]
    )


def main() -> None:
    _log_decisions_only()
    store = TripStore(Path(os.environ.get("SCOUT_DB_PATH", DEFAULT_DB_PATH)))
    services = connect_outside_services()
    agent = connect_agent(store, services)
    gate = connect_speak_gate(store)
    media = MediaLibrary(
        Path(os.environ.get("SCOUT_MEDIA_DIR", DEFAULT_MEDIA_DIR)),
        connect_transcriber(),
    )
    port = int(os.environ.get("SCOUT_PORT", DEFAULT_PORT))
    logger.info("scout service is listening on http://%s:%d", HOST, port)
    # The bridge logs every message, so a line per request would only repeat it.
    uvicorn.run(
        create_app(store, agent, gate, media, services),
        host=HOST,
        port=port,
        access_log=False,
        log_level="warning",
    )


def _log_decisions_only() -> None:
    """Logs what scout decided and why, in plain lines, and anything worse
    with its level. The HTTP clients' per-request lines would bury those."""
    handler = logging.StreamHandler()
    handler.setFormatter(_ReadableFormatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    for chatty in ("httpx", "httpx2"):
        logging.getLogger(chatty).setLevel(logging.WARNING)


class _ReadableFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        return line if record.levelno <= logging.INFO else f"{record.levelname}: {line}"
