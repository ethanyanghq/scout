"""The developer endpoints, called over HTTP the way the developer console does."""

import pytest
from fastapi.testclient import TestClient

from scout.app import create_app
from scout.media import MediaLibrary

MAYA = {"phone": "+15550000001", "name": "Maya"}
LEO = {"phone": "+15550000002", "name": "Leo"}
PRIYA = {"phone": "+15550000003", "name": "Priya"}
GROUP = [MAYA, LEO, PRIYA]


class UnusedAgent:
    def respond(self, trip, message):
        raise AssertionError("seeded trips and plain votes shouldn't need Claude")


@pytest.fixture
def client(store, tmp_path):
    return TestClient(
        create_app(store, UnusedAgent(), MediaLibrary(tmp_path / "media", None))
    )


def seed(client, stage, members=GROUP, chat="chat-1"):
    return client.post(
        f"/dev/trips/{chat}/seed", json={"stage": stage, "members": members}
    )


def test_seeding_at_the_poll_opens_the_vote_with_everyones_preferences(client):
    response = seed(client, "poll-open")

    assert response.status_code == 201
    trip = response.json()
    assert trip["stage"] == "voting"
    assert [member["display_name"] for member in trip["members"]] == [
        "Maya",
        "Leo",
        "Priya",
    ]
    assert all(member["budget_usd"] for member in trip["members"])
    assert [option["name"] for option in trip["open_poll"]["options"]] == [
        "Tulum, Mexico",
        "San Juan, Puerto Rico",
        "Miami, Florida",
    ]


def test_seeding_never_overwrites_an_existing_trip(client):
    seed(client, "poll-open")

    response = seed(client, "destination-chosen")

    assert response.status_code == 409
    assert client.get("/dev/trips/chat-1").json()["stage"] == "voting"


def test_reset_forgets_the_chats_trip(client):
    seed(client, "poll-open")

    response = client.delete("/dev/trips/chat-1")

    assert response.status_code == 204
    assert client.get("/dev/trips/chat-1").status_code == 404
