"""Which AI answers the speak gate, with stand-ins for both providers' clients."""

from types import SimpleNamespace

from scout.ai_provider import (
    CLAUDE_GATE_MODEL,
    OPENAI_GATE_MODEL,
    _ask_claude,
    _ask_openai,
    connect_speak_gate,
)
from scout.speak_gate import SpeakGate


def test_asks_claude_for_a_one_word_answer():
    requests = []

    def create(**request):
        requests.append(request)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="SPEAK")])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))

    answer = _ask_claude(client)("the rules", "the situation")

    assert answer == "SPEAK"
    assert requests[0]["model"] == CLAUDE_GATE_MODEL
    assert requests[0]["system"] == "the rules"
    assert requests[0]["messages"] == [{"role": "user", "content": "the situation"}]


def test_asks_openai_for_a_one_word_answer():
    requests = []

    def create(**request):
        requests.append(request)
        return SimpleNamespace(output_text="SILENT")

    client = SimpleNamespace(responses=SimpleNamespace(create=create))

    answer = _ask_openai(client)("the rules", "the situation")

    assert answer == "SILENT"
    assert requests[0]["model"] == OPENAI_GATE_MODEL
    assert requests[0]["instructions"] == "the rules"
    assert requests[0]["input"] == "the situation"


def test_the_gate_follows_whichever_key_is_set(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    assert isinstance(connect_speak_gate(store), SpeakGate)
