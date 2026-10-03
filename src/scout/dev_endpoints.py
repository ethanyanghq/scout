"""Endpoints for developer tools: start a chat's trip partway through the
journey, read it, or reset it.

Like /messages, these are only reachable from this machine (see app.py).
"""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from scout.trip import Trip
from scout.trip_seeds import SeedMember, SeedStage, seed_trip
from scout.trip_store import TripStore

# Enough to see what scout said when a chat was seeded, or lately.
RECENT_MESSAGE_COUNT = 30


class SeededMember(BaseModel):
    phone: str
    name: str


class SeedRequest(BaseModel):
    stage: SeedStage
    members: list[SeededMember] = Field(min_length=1)


def create_dev_router(store: TripStore) -> APIRouter:
    router = APIRouter(prefix="/dev/trips")

    @router.post("/{space_id}/seed", status_code=201)
    def seed(space_id: str, request: SeedRequest) -> Trip:
        # Seeding never overwrites a trip, so it can't wipe a real group's plans.
        if store.get_trip(space_id) is not None:
            raise HTTPException(
                409, f"Chat {space_id} already has a trip. Reset it first."
            )
        members = [SeedMember(member.phone, member.name) for member in request.members]
        seed_trip(store, space_id, request.stage, members)
        return store.get_trip(space_id)

    @router.get("/{space_id}")
    def show(space_id: str) -> Trip:
        trip = store.get_trip(space_id)
        if trip is None:
            raise HTTPException(404, f"Chat {space_id} has no trip.")
        return trip

    @router.get("/{space_id}/messages")
    def show_messages(space_id: str) -> list[dict]:
        """The chat's latest messages, oldest first. A sender of None is scout."""
        return [
            {"sender_phone": logged.sender_phone, "text": logged.text}
            for logged in store.recent_messages(space_id, RECENT_MESSAGE_COUNT)
        ]

    @router.delete("/{space_id}", status_code=204)
    def reset(space_id: str) -> Response:
        store.delete_trip(space_id)
        return Response(status_code=204)

    return router
