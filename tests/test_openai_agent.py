"""The OpenAI agent loop, with a scripted stand-in for the OpenAI API."""

import json
from datetime import datetime
from types import SimpleNamespace

from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseFunctionWebSearch,
    ResponseOutputMessage,
)

from scout.agent import ScoutAgent
from scout.ai_provider import connect_agent
from scout.openai_agent import OpenAIScoutAgent
from scout.outgoing import Say
from scout.outside_services import NO_OUTSIDE_SERVICES
from scout.trip import IncomingMessage, MediaKind, SharedMedia

SPACE = "group-chat-1"
MAYA = "+15550000001"


class ScriptedOpenAI:
    """Returns pre-written responses in order and keeps every request it got.
    Each response is the list of items OpenAI would put in its output."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **request):
        # Copy the list: the agent keeps appending to the same conversation.
        self.requests.append({**request, "input": list(request["input"])})
        return SimpleNamespace(output=self._responses.pop(0))


def output_message(*parts):
    return ResponseOutputMessage(
        id="msg_1", type="message", role="assistant", status="completed", content=parts
    )


def says(text):
    return [output_message({"type": "output_text", "text": text, "annotations": []})]


def calls(name, tool_input, call_id="call_1"):
    return [
        ResponseFunctionToolCall(
            type="function_call",
            call_id=call_id,
            name=name,
            arguments=json.dumps(tool_input),
        )
    ]


def searches(query):
    return ResponseFunctionWebSearch(
        id="ws_1",
        type="web_search_call",
        status="completed",
        action={"type": "search", "query": query},
    )


def said(outgoing):
    """The texts scout sent, failing on anything that isn't a plain text."""
    assert all(isinstance(item, Say) for item in outgoing), outgoing
    return [item.text for item in outgoing]


def maya_says(store, words):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])
    store.log_message(SPACE, MAYA, words, datetime(2026, 10, 2, 9, 0))
    message = IncomingMessage(SPACE, MAYA, words, datetime(2026, 10, 2, 9, 0))
    return store.get_trip(SPACE), message


def test_bad_tool_input_goes_back_to_openai_as_an_error(store):
    trip, message = maya_says(store, "@scout close the poll")
    model = ScriptedOpenAI(
        calls("close_poll", {}),
        says("There's no poll open yet."),
    )

    replies = OpenAIScoutAgent(model, store).respond(trip, message)

    tool_result = model.requests[1]["input"][-1]
    assert tool_result["call_id"] == "call_1"
    assert tool_result["output"].startswith("Error:")
    assert "no open poll" in tool_result["output"]
    assert said(replies) == ["There's no poll open yet."]


def test_a_photo_openai_asks_to_view_comes_back_as_an_image(store, tmp_path):
    trip, message = maya_says(store, "@scout what was the total on that receipt?")
    readable = tmp_path / "a1b2c3d4.readable.jpg"
    readable.write_bytes(b"jpeg bytes")
    store.save_media(
        SPACE,
        SharedMedia(
            "a1b2c3d4", MediaKind.PHOTO, tmp_path / "a1b2c3d4.heic", readable, None
        ),
    )
    model = ScriptedOpenAI(
        calls("view_photo", {"photo_id": "a1b2c3d4"}),
        says("$164 at Casa Brisa."),
    )

    OpenAIScoutAgent(model, store).respond(trip, message)

    tool_result = model.requests[1]["input"][-1]
    assert tool_result["output"] == [
        {"type": "input_image", "image_url": "data:image/jpeg;base64,anBlZyBieXRlcw=="}
    ]


def test_openai_can_search_the_web(store):
    trip, message = maya_says(store, "@scout anything happening in tulum in march?")
    model = ScriptedOpenAI(says("NO_REPLY"))

    OpenAIScoutAgent(model, store).respond(trip, message)

    offered = [tool["type"] for tool in model.requests[0]["tools"]]
    assert "web_search" in offered


def test_texts_only_what_openai_wrote_after_searching(store):
    trip, message = maya_says(store, "@scout anything happening in tulum in march?")
    model = ScriptedOpenAI(
        [
            *says("Let me check."),
            searches("Tulum events March 2027"),
            *says("Tulum Jazz Festival runs March 10–14."),
        ]
    )

    replies = OpenAIScoutAgent(model, store).respond(trip, message)

    assert said(replies) == ["Tulum Jazz Festival runs March 10–14."]


def test_a_refusal_sends_nothing(store):
    trip, message = maya_says(store, "@scout hi")
    model = ScriptedOpenAI(
        [output_message({"type": "refusal", "refusal": "Can't help."})]
    )

    assert OpenAIScoutAgent(model, store).respond(trip, message) == []


def test_openai_is_the_fallback_without_a_claude_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert isinstance(connect_agent(store, NO_OUTSIDE_SERVICES), OpenAIScoutAgent)


def test_claude_is_the_default_without_any_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert isinstance(connect_agent(store, NO_OUTSIDE_SERVICES), ScoutAgent)
