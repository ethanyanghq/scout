"""What the bridge sends scout over HTTP, and the actions it gets back."""

import base64
import re
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scout.app import create_app
from scout.media import MediaLibrary
from scout.trip import DateWindow, DestinationOption, ItineraryDay

FIXTURES = Path(__file__).parent / "fixtures"
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


class SilentGate:
    def should_speak(self, trip, message):
        return False


@pytest.fixture
def client(store, tmp_path):
    store.create_trip(SPACE)
    store.log_message(SPACE, None, "Hey all, I'm scout 👋", datetime(2026, 10, 3, 9, 0))
    store.add_members(SPACE, [MAYA, LEO])
    store.open_poll(SPACE, OPTIONS)
    return TestClient(
        create_app(
            store, UnusedAgent(), SilentGate(), MediaLibrary(tmp_path / "media", None)
        )
    )


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
                "fallback_text": "got it, …0001 → San Juan, Puerto Rico (1 of 2 voted)",
            }
        ]
    }


def send_attachment(client, media_type, data):
    return client.post(
        "/messages",
        json={
            "space_id": SPACE,
            "sender_phone": MAYA,
            "text": "",
            "sent_at": "2026-10-03T12:00:00Z",
            "attachment": {
                "media_type": media_type,
                "base64_data": base64.b64encode(data).decode("ascii"),
            },
        },
    )


@pytest.mark.skipif(
    shutil.which("afconvert") is None, reason="voice memos need macOS's afconvert"
)
def test_a_voice_memo_is_kept_and_noted_in_the_chat(client, store):
    voice_memo = (FIXTURES / "voice-memo.caf").read_bytes()

    response = send_attachment(client, "audio/x-caf", voice_memo)

    assert response.status_code == 200
    logged = store.recent_messages(SPACE, limit=1)[0].text
    [media_id] = re.findall(r"^\[voice note (\w+) ", logged)
    kept = store.find_media(SPACE, media_id)
    assert kept.original_path.read_bytes() == voice_memo
    assert logged == (
        f"[voice note {media_id} ({kept.original_path}): couldn't be transcribed]"
    )


def test_a_chat_with_a_plan_serves_it_as_a_calendar_feed(client, store):
    store.lock_in_destination(
        SPACE, "San Juan, Puerto Rico", DateWindow(date(2027, 3, 14), date(2027, 3, 19))
    )
    store.replace_itinerary(
        SPACE, [ItineraryDay(date(2027, 3, 14), "Land and check in")], []
    )

    response = client.get(f"/calendars/{SPACE}.ics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Land and check in" in response.text


def test_requests_through_the_tunnel_reach_only_calendar_feeds(client):
    through_tunnel = {"X-Forwarded-For": "203.0.113.9"}

    assert client.get(f"/dev/trips/{SPACE}", headers=through_tunnel).status_code == 404
    assert (
        client.delete(f"/dev/trips/{SPACE}", headers=through_tunnel).status_code == 404
    )
    assert (
        client.get(f"/calendars/{SPACE}.ics", headers=through_tunnel).status_code == 404
    )
    assert client.get(f"/dev/trips/{SPACE}").status_code == 200


def test_a_chat_with_a_plan_serves_its_feed_through_the_tunnel(client, store):
    store.lock_in_destination(
        SPACE, "San Juan, Puerto Rico", DateWindow(date(2027, 3, 14), date(2027, 3, 19))
    )
    store.replace_itinerary(SPACE, [ItineraryDay(date(2027, 3, 14), "Land")], [])

    response = client.get(
        f"/calendars/{SPACE}.ics", headers={"X-Forwarded-For": "203.0.113.9"}
    )

    assert response.status_code == 200


def test_a_chat_without_a_plan_has_no_calendar_feed(client):
    assert client.get(f"/calendars/{SPACE}.ics").status_code == 404
