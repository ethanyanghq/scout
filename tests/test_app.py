"""What the bridge sends scout over HTTP, and the actions it gets back."""

import pytest
from fastapi.testclient import TestClient

from scout.app import create_app
from scout.polls import format_poll
from scout.trip import DestinationOption

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport"),
]


class UnusedAgent:
    def respond(self, trip, message):
        raise AssertionError("votes shouldn't need Claude")


@pytest.fixture
def client(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA, LEO])
    store.open_poll(SPACE, OPTIONS)
    return TestClient(create_app(store, UnusedAgent()))


def test_a_vote_with_a_message_id_comes_back_as_a_tapback_on_it(client):
    response = client.post(
        "/messages",
        json={
            "space_id": SPACE,
            "sender_phone": MAYA,
            "text": "2",
            "sent_at": "2026-10-03T12:00:00Z",
            "participant_phones": [MAYA, LEO],
            "message_id": "maya-vote",
        },
    )

    assert response.json() == {
        "actions": [
            {
                "type": "react",
                "message_id": "maya-vote",
                "tapback": "like",
                "fallback_text": "Got it, …0001 → San Juan, Puerto Rico (1 of 2 voted)",
            }
        ]
    }


def test_a_tapback_on_a_poll_option_comes_back_as_a_confirmation(client):
    response = client.post(
        "/reactions",
        json={
            "space_id": SPACE,
            "sender_phone": LEO,
            "tapback": "like",
            "message_text": format_poll(OPTIONS)[1],
            "sent_at": "2026-10-03T12:00:00Z",
        },
    )

    assert response.json() == {
        "actions": [
            {
                "type": "say",
                "text": "Got it, …0002 → Tulum, Mexico (1 of 2 voted)",
                "reply_to": None,
            }
        ]
    }
