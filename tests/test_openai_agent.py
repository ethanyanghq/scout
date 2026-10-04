"""The OpenAI agent loop, with a scripted stand-in for the OpenAI API."""

import json
from datetime import datetime
from types import SimpleNamespace

from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
)

from scout.agent import ScoutAgent
from scout.ai_provider import connect_agent
from scout.openai_agent import OpenAIScoutAgent
from scout.outgoing import Say
from scout.trip import IncomingMessage, MediaKind, SharedMedia

SPACE = "group-chat-1"
MAYA = "+15550000001"


class ScriptedOpenAI:
    """Returns pre-written replies in order and keeps every request it got."""

    def __init__(self, *replies):
        self._replies = list(replies)
        self.requests = []
        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)

    def _create(self, **request):
        # Copy the list: the agent keeps appending to the same conversation.
        self.requests.append({**request, "messages": list(request["messages"])})
        reply = self._replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=reply)])


def says(text):
    return ChatCompletionMessage(role="assistant", content=text)


def calls(name, tool_input, call_id="call_1"):
    call = ChatCompletionMessageFunctionToolCall(
        id=call_id,
        type="function",
        function={"name": name, "arguments": json.dumps(tool_input)},
    )
    return ChatCompletionMessage(role="assistant", content=None, tool_calls=[call])


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

    tool_result = model.requests[1]["messages"][-1]
    assert tool_result["content"].startswith("Error:")
    assert "no open poll" in tool_result["content"]
    assert said(replies) == ["There's no poll open yet."]


def test_a_photo_openai_asks_to_view_follows_the_tool_results(store, tmp_path):
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

    tool_result, photos = model.requests[1]["messages"][-2:]
    assert tool_result["role"] == "tool"
    assert photos == {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,anBlZyBieXRlcw=="},
            }
        ],
    }


def test_openai_is_the_fallback_without_a_claude_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert isinstance(connect_agent(store), OpenAIScoutAgent)


def test_claude_is_the_default_without_any_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert isinstance(connect_agent(store), ScoutAgent)
