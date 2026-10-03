"""What the bridge sends scout over HTTP, and the actions it gets back."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from scout.app import create_app
from scout.polls import format_poll
from scout.trip import DestinationOption, PreferenceUpdate

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


def test_a_tapback_on_a_poll_option_comes_back_as_a_threaded_confirmation(client):
    response = client.post(
        "/reactions",
        json={
            "space_id": SPACE,
            "sender_phone": LEO,
            "tapback": "like",
            "message_id": "tulum-option",
            "message_text": format_poll(OPTIONS)[1],
            "sent_at": "2026-10-03T12:00:00Z",
        },
    )

    assert response.json() == {
        "actions": [
            {
                "type": "say",
                "text": "Got it, …0002 → Tulum, Mexico (1 of 2 voted)",
                "reply_to": "tulum-option",
            }
        ]
    }


def test_the_calendar_link_comes_back_as_a_link_of_its_own(client, store):
    free_in_march = PreferenceUpdate(
        available_from=date(2027, 3, 14),
        available_to=date(2027, 3, 19),
        budget_usd=800,
        home_city="Boston",
    )
    for member in (MAYA, LEO):
        store.save_preferences(SPACE, member, free_in_march)

    for voter in (MAYA, LEO):
        response = client.post(
            "/messages",
            json={
                "space_id": SPACE,
                "sender_phone": voter,
                "text": "2",
                "sent_at": "2026-10-03T12:00:00Z",
                "participant_phones": [MAYA, LEO],
            },
        )

    *announcements, link = response.json()["actions"]
    assert announcements[0]["text"].startswith("🎉 Poll closed!")
    assert link["type"] == "link"
    assert link["url"].startswith("https://calendar.google.com/calendar/render?")
