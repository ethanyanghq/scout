"""The speak gate, with a scripted stand-in for the small model it asks."""

from datetime import datetime

import pytest

from scout.speak_gate import GATE_PROMPT, SpeakGate, is_addressed_to_scout
from scout.trip import IncomingMessage

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"


class ScriptedModel:
    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def __call__(self, system, situation):
        self.requests.append((system, situation))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def say(store, sender, text, reply_to_text=None):
    """Logs a member's message and returns it, the way the service would."""
    store.create_trip(SPACE) if store.get_trip(SPACE) is None else None
    store.add_members(SPACE, [MAYA, LEO])
    store.log_message(SPACE, sender, text, datetime(2026, 10, 2, 9, 0))
    message = IncomingMessage(
        SPACE, sender, text, datetime(2026, 10, 2, 9, 0), reply_to_text=reply_to_text
    )
    return store.get_trip(SPACE), message


@pytest.mark.parametrize("answer", ["SPEAK", "speak", " Speak.\n"])
def test_speaks_when_the_model_says_speak(store, answer):
    trip, message = say(store, MAYA, "can someone find flights?")

    assert SpeakGate(ScriptedModel(answer), store).should_speak(trip, message)


@pytest.mark.parametrize("answer", ["SILENT", "silent", "", "not sure"])
def test_stays_quiet_unless_the_model_says_speak(store, answer):
    trip, message = say(store, MAYA, "lol same")

    assert not SpeakGate(ScriptedModel(answer), store).should_speak(trip, message)


def test_stays_quiet_when_the_model_cant_be_reached(store):
    trip, message = say(store, MAYA, "can someone find flights?")
    gate = SpeakGate(ScriptedModel(ConnectionError("down")), store)

    assert not gate.should_speak(trip, message)


def test_shows_the_model_the_latest_chat_and_where_the_trip_is(store):
    say(store, MAYA, "should we do tulum")
    store.log_message(SPACE, None, "up to you all", datetime(2026, 10, 2, 9, 1))
    trip, message = say(store, LEO, "can someone find flights?")
    model = ScriptedModel("SILENT")

    SpeakGate(model, store).should_speak(trip, message)

    system, situation = model.requests[0]
    assert system == GATE_PROMPT
    assert "scout has spoken in this chat: yes" in situation
    assert "Trip stage: collecting_preferences" in situation
    assert "[…0001] should we do tulum\n[scout] up to you all\n[…0002] can" in situation
    assert situation.endswith("From …0002: can someone find flights?")


def test_a_tag_or_a_threaded_reply_to_scout_is_addressed_to_scout(store):
    _, tagged = say(store, MAYA, "@scout hi")
    store.log_message(SPACE, None, "want flights?", datetime(2026, 10, 2, 9, 1))
    _, reply = say(store, LEO, "yes", reply_to_text="want flights?")

    assert is_addressed_to_scout(store, tagged)
    assert is_addressed_to_scout(store, reply)


def test_a_threaded_reply_to_a_friend_is_not_addressed_to_scout(store):
    _, reply = say(store, LEO, "same", reply_to_text="i'm free mar 14-20")

    assert not is_addressed_to_scout(store, reply)
