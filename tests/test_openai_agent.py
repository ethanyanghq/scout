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
from scout.trip import IncomingMessage, MessagePhoto

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


def maya_says(store, words, photo=None):
    store.create_trip(SPACE)
    store.add_members(SPACE, [MAYA])
    store.log_message(SPACE, MAYA, words, datetime(2026, 10, 2, 9, 0))
    message = IncomingMessage(
        SPACE, MAYA, words, datetime(2026, 10, 2, 9, 0), photo=photo
    )
    return store.get_trip(SPACE), message


def test_saves_preferences_and_confirms(store):
    trip, message = maya_says(store, "i'm maya, $800")
    preferences = {
        "member": "…0001",
        "display_name": "Maya",
        "available_from": None,
        "available_to": None,
        "budget_usd": 800,
        "home_city": None,
        "must_haves": None,
    }
    model = ScriptedOpenAI(
        calls("save_member_preferences", preferences),
        says("Got it, Maya: ~$800. Dates and home city?"),
    )

    replies = OpenAIScoutAgent(model, store).respond(trip, message)

    assert said(replies) == ["Got it, Maya: ~$800. Dates and home city?"]
    assert store.get_trip(SPACE).find_member(MAYA).budget_usd == 800
    tool_result = model.requests[1]["messages"][-1]
    assert tool_result["role"] == "tool"
    assert tool_result["tool_call_id"] == "call_1"


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


def test_posted_summaries_follow_the_lead_in_line(store):
    trip, message = maya_says(store, "@scout where are we at?")
    model = ScriptedOpenAI(calls("post_group_summary", {}), says("Here you go!"))

    replies = said(OpenAIScoutAgent(model, store).respond(trip, message))

    assert replies[0] == "Here you go!"
    assert replies[1].startswith("Here's where everyone landed:")


def test_no_reply_means_scout_stays_quiet(store):
    trip, message = maya_says(store, "lol same")
    model = ScriptedOpenAI(says("NO_REPLY"))

    assert OpenAIScoutAgent(model, store).respond(trip, message) == []


def test_a_refusal_sends_nothing(store):
    trip, message = maya_says(store, "@scout hi")
    refusal = ChatCompletionMessage(
        role="assistant", content=None, refusal="I can't help with that."
    )
    model = ScriptedOpenAI(refusal)

    assert OpenAIScoutAgent(model, store).respond(trip, message) == []


def test_a_photo_is_shown_before_the_situation(store):
    receipt = MessagePhoto("image/jpeg", "cmVjZWlwdA==")
    trip, message = maya_says(store, "casa brisa dinner", photo=receipt)
    model = ScriptedOpenAI(says("NO_REPLY"))

    OpenAIScoutAgent(model, store).respond(trip, message)

    photo, situation = model.requests[0]["messages"][1]["content"]
    assert photo["image_url"]["url"] == "data:image/jpeg;base64,cmVjZWlwdA=="
    assert "It comes with the photo above." in situation["text"]


def test_claude_is_used_when_its_key_is_set(store, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert isinstance(connect_agent(store), ScoutAgent)


def test_openai_is_the_fallback_without_a_claude_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert isinstance(connect_agent(store), OpenAIScoutAgent)


def test_claude_is_the_default_without_any_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert isinstance(connect_agent(store), ScoutAgent)
