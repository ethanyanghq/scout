"""The agent loop, with a scripted stand-in for the Claude API."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from scout.agent import ScoutAgent
from scout.outgoing import Say
from scout.trip import (
    IncomingMessage,
    MediaKind,
    SharedMedia,
)


def said(outgoing):
    """The texts scout sent, failing on anything that isn't a plain text."""
    assert all(isinstance(item, Say) for item in outgoing), outgoing
    return [item.text for item in outgoing]


SPACE = "group-chat-1"
MAYA = "+15550000001"


class ScriptedClaude:
    """Returns pre-written responses in order and keeps every request it got."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **request):
        # Copy the list: the agent keeps appending to the same conversation.
        self.requests.append({**request, "messages": list(request["messages"])})
        return self._responses.pop(0)


def response(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def text(value):
    return SimpleNamespace(type="text", text=value)


def tool_call(name, tool_input, call_id="call_1"):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=tool_input)


def situation_text(claude):
    """The words of scout's first prompt."""
    return claude.requests[0]["messages"][0]["content"]


def maya_says(store, words):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])
    store.log_message(SPACE, MAYA, words, datetime(2026, 10, 2, 9, 0))
    message = IncomingMessage(SPACE, MAYA, words, datetime(2026, 10, 2, 9, 0))
    return store.get_trip(SPACE), message


def test_saves_preferences_and_confirms(store):
    trip, message = maya_says(store, "i'm maya, $800")
    claude = ScriptedClaude(
        response(
            "tool_use",
            tool_call(
                "save_member_preferences",
                {
                    "member": "…0001",
                    "display_name": "Maya",
                    "available_from": None,
                    "available_to": None,
                    "budget_usd": 800,
                    "home_city": None,
                    "must_haves": None,
                    "chronotype": None,
                },
            ),
        ),
        response("end_turn", text("got it, Maya: ~$800. Dates and home city?")),
    )

    replies = said(ScoutAgent(claude, store).respond(trip, message))

    assert replies == ["got it, Maya: ~$800. Dates and home city?"]
    assert store.get_trip(SPACE).find_member(MAYA).budget_usd == 800
    tool_result = claude.requests[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "call_1"
    assert not tool_result["is_error"]


def test_bad_tool_input_goes_back_to_claude_as_an_error(store):
    trip, message = maya_says(store, "@scout close the poll")
    claude = ScriptedClaude(
        response("tool_use", tool_call("close_poll", {})),
        response("end_turn", text("There's no poll open yet.")),
    )

    replies = said(ScoutAgent(claude, store).respond(trip, message))

    tool_result = claude.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"]
    assert "no open poll" in tool_result["content"]
    assert replies == ["There's no poll open yet."]


def test_no_reply_means_scout_stays_quiet(store):
    trip, message = maya_says(store, "lol same")
    claude = ScriptedClaude(response("end_turn", text("NO_REPLY")))

    assert ScoutAgent(claude, store).respond(trip, message) == []


def test_each_paragraph_of_a_reply_is_its_own_text(store):
    trip, message = maya_says(store, "@scout hello!")
    reply = (
        "Hey all, I'm scout 👋\n\nWhat I need:\n1. name\n2. dates\n\n  \nTag me anytime"
    )
    claude = ScriptedClaude(response("end_turn", text(reply)))

    replies = said(ScoutAgent(claude, store).respond(trip, message))

    assert replies == [
        "Hey all, I'm scout 👋",
        "What I need:\n1. name\n2. dates",
        "Tag me anytime",
    ]


def test_posted_summaries_follow_the_lead_in_line(store):
    trip, message = maya_says(store, "@scout where are we at?")
    claude = ScriptedClaude(
        response("tool_use", tool_call("post_group_summary", {})),
        response("end_turn", text("Here you go!")),
    )

    replies = said(ScoutAgent(claude, store).respond(trip, message))

    assert replies[0] == "Here you go!"
    assert replies[1].startswith("here's where everyone landed:")


def test_a_refusal_sends_nothing(store):
    trip, message = maya_says(store, "@scout hi")
    refusal = response("refusal")
    refusal.stop_details = SimpleNamespace(category=None)
    claude = ScriptedClaude(refusal)

    assert ScoutAgent(claude, store).respond(trip, message) == []


def test_tells_claude_whether_it_was_tagged(store):
    trip, message = maya_says(store, "@scout hi")
    claude = ScriptedClaude(response("end_turn", text("Hey!")))

    ScoutAgent(claude, store).respond(trip, message)

    situation = situation_text(claude)
    assert "It tags or addresses you." in situation
    assert "[…0001] @scout hi" in situation


def test_a_new_photo_reaches_claude_as_its_description_not_an_image(store):
    trip, _ = maya_says(store, "")
    receipt = SharedMedia(
        "a1b2c3d4",
        MediaKind.PHOTO,
        Path("media/group-chat-1/a1b2c3d4.heic"),
        Path("media/group-chat-1/a1b2c3d4.readable.jpg"),
        "Receipt from Casa Brisa. Total $164.00",
    )
    message = IncomingMessage(
        SPACE, MAYA, "@scout split this", datetime(2026, 10, 2, 9, 0), media=receipt
    )
    claude = ScriptedClaude(response("end_turn", text("NO_REPLY")))

    ScoutAgent(claude, store).respond(trip, message)

    assert situation_text(claude).endswith(
        "[photo a1b2c3d4 (media/group-chat-1/a1b2c3d4.heic): "
        "Receipt from Casa Brisa. Total $164.00] @scout split this"
    )


def test_a_photo_claude_asks_to_view_comes_back_as_an_image(store, tmp_path):
    trip, message = maya_says(store, "@scout what was the total on that receipt?")
    readable = tmp_path / "a1b2c3d4.readable.jpg"
    readable.write_bytes(b"jpeg bytes")
    store.save_media(
        SPACE,
        SharedMedia(
            "a1b2c3d4", MediaKind.PHOTO, tmp_path / "a1b2c3d4.heic", readable, None
        ),
    )
    claude = ScriptedClaude(
        response("tool_use", tool_call("view_photo", {"photo_id": "a1b2c3d4"})),
        response("end_turn", text("$164 at Casa Brisa.")),
    )

    ScoutAgent(claude, store).respond(trip, message)

    tool_result = claude.requests[1]["messages"][-1]["content"][0]
    assert tool_result["content"] == [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "anBlZyBieXRlcw==",
            },
        }
    ]


def test_claude_reads_a_voice_notes_words_as_the_newest_message(store):
    trip, _ = maya_says(store, "")
    voice_note = SharedMedia(
        "e5f6a7b8",
        MediaKind.VOICE_NOTE,
        Path("media/group-chat-1/e5f6a7b8.caf"),
        Path("media/group-chat-1/e5f6a7b8.readable.m4a"),
        "I'm flying from Boston.",
    )
    message = IncomingMessage(
        SPACE, MAYA, "@scout", datetime(2026, 10, 2, 9, 0), media=voice_note
    )
    claude = ScriptedClaude(response("end_turn", text("NO_REPLY")))

    ScoutAgent(claude, store).respond(trip, message)

    assert situation_text(claude).endswith(
        "[voice note e5f6a7b8 (media/group-chat-1/e5f6a7b8.caf): "
        '"I\'m flying from Boston."] @scout'
    )
