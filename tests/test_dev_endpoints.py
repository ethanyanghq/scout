"""The developer endpoints, called over HTTP the way the developer console does."""

import pytest
from fastapi.testclient import TestClient

from scout.app import create_app

MAYA = {"phone": "+15550000001", "name": "Maya"}
LEO = {"phone": "+15550000002", "name": "Leo"}
PRIYA = {"phone": "+15550000003", "name": "Priya"}
GROUP = [MAYA, LEO, PRIYA]


class UnusedAgent:
    def respond(self, trip, message):
        raise AssertionError("seeded trips and plain votes shouldn't need Claude")


@pytest.fixture
def client(store):
    return TestClient(create_app(store, UnusedAgent()))


def seed(client, stage, members=GROUP, chat="chat-1"):
    return client.post(
        f"/dev/trips/{chat}/seed", json={"stage": stage, "members": members}
    )


def vote(client, member, text, chat="chat-1"):
    response = client.post(
        "/messages",
        json={
            "space_id": chat,
            "sender_phone": member["phone"],
            "text": text,
            "sent_at": "2026-10-03T12:00:00Z",
            "participant_phones": [person["phone"] for person in GROUP],
        },
    )
    return response.json()["replies"]


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


def test_a_seeded_poll_counts_plain_votes_and_announces_the_winner(client):
    seed(client, "poll-open")

    vote(client, MAYA, "2")
    vote(client, LEO, "2")
    replies = vote(client, PRIYA, "1")

    assert "San Juan, Puerto Rico wins" in replies[0]


def test_seeding_past_the_vote_locks_in_san_juan_and_the_shared_dates(client):
    trip = seed(client, "destination-chosen").json()

    assert trip["stage"] == "destination_chosen"
    assert trip["destination"] == "San Juan, Puerto Rico"
    assert trip["dates"] == {"start": "2027-03-14", "end": "2027-03-20"}
    assert trip["open_poll"] is None


def test_seeding_never_overwrites_an_existing_trip(client):
    seed(client, "poll-open")

    response = seed(client, "destination-chosen")

    assert response.status_code == 409
    assert client.get("/dev/trips/chat-1").json()["stage"] == "voting"


def test_a_chat_without_a_trip_is_not_found(client):
    assert client.get("/dev/trips/never-seen").status_code == 404


def test_reset_forgets_the_chats_trip(client):
    seed(client, "poll-open")

    response = client.delete("/dev/trips/chat-1")

    assert response.status_code == 204
    assert client.get("/dev/trips/chat-1").status_code == 404
