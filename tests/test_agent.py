"""The agent loop, with a scripted stand-in for the Claude API."""

from datetime import date, datetime
from types import SimpleNamespace

from scout.agent import ScoutAgent
from scout.trip import (
    DateWindow,
    DestinationOption,
    IncomingMessage,
    ItineraryDay,
    PreferenceUpdate,
)

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
                "save_sender_preferences",
                {
                    "display_name": "Maya",
                    "available_from": None,
                    "available_to": None,
                    "budget_usd": 800,
                    "home_city": None,
                    "must_haves": None,
                },
            ),
        ),
        response("end_turn", text("Got it, Maya: ~$800. Dates and home city?")),
    )

    replies = ScoutAgent(claude, store).respond(trip, message)

    assert replies == ["Got it, Maya: ~$800. Dates and home city?"]
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

    replies = ScoutAgent(claude, store).respond(trip, message)

    tool_result = claude.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"]
    assert "no open poll" in tool_result["content"]
    assert replies == ["There's no poll open yet."]


def test_no_reply_means_scout_stays_quiet(store):
    trip, message = maya_says(store, "lol same")
    claude = ScriptedClaude(response("end_turn", text("NO_REPLY")))

    assert ScoutAgent(claude, store).respond(trip, message) == []


def test_posted_summaries_follow_the_lead_in_line(store):
    trip, message = maya_says(store, "@scout where are we at?")
    claude = ScriptedClaude(
        response("tool_use", tool_call("post_group_summary", {})),
        response("end_turn", text("Here you go!")),
    )

    replies = ScoutAgent(claude, store).respond(trip, message)

    assert replies[0] == "Here you go!"
    assert replies[1].startswith("Here's where everyone landed:")


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

    situation = claude.requests[0]["messages"][0]["content"]
    assert "It tags or addresses you." in situation
    assert "[…0001] @scout hi" in situation


def test_shows_claude_the_locked_in_dates_and_plan(store):
    trip, message = maya_says(store, "@scout what's tuesday again?")
    store.open_poll(SPACE, [DestinationOption("San Juan, Puerto Rico", 750, "Beach")])
    poll_id = store.get_trip(SPACE).open_poll.id
    store.close_poll(
        poll_id,
        "San Juan, Puerto Rico",
        DateWindow(date(2027, 3, 14), date(2027, 3, 19)),
    )
    store.replace_itinerary(
        SPACE, [ItineraryDay(date(2027, 3, 16), "Waterfall hike in El Yunque")]
    )
    claude = ScriptedClaude(response("end_turn", text("El Yunque hike!")))

    ScoutAgent(claude, store).respond(store.get_trip(SPACE), message)

    situation = claude.requests[0]["messages"][0]["content"]
    assert "Trip dates: Mar 14–19 2027" in situation
    assert "Tue 2027-03-16: Waterfall hike in El Yunque" in situation


def test_shows_claude_each_expense_with_its_number_and_payer(store):
    trip, message = maya_says(store, "@scout what have we spent?")
    store.save_preferences(SPACE, MAYA, PreferenceUpdate(display_name="Maya"))
    expense_id = store.add_expense(SPACE, MAYA, 19_600, "Bio bay kayaks")
    claude = ScriptedClaude(response("end_turn", text("$196 so far.")))

    ScoutAgent(claude, store).respond(store.get_trip(SPACE), message)

    situation = claude.requests[0]["messages"][0]["content"]
    assert f"#{expense_id} Bio bay kayaks: $196, paid by Maya" in situation
