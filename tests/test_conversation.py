"""The whole message flow, with Claude replaced by a stand-in.

Claude is the one external service here, so it's the one thing faked. The
store, polls, and summaries are all real.
"""

from datetime import date, datetime

from scout.conversation import INTRODUCTION, SNAG_REPLY, handle_message
from scout.trip import DestinationOption, IncomingMessage, PreferenceUpdate, TripStage

SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
PRIYA = "+15550000003"
EVERYONE = (MAYA, LEO, PRIYA)
OPTIONS = [
    DestinationOption("Tulum, Mexico", 900, "Beaches"),
    DestinationOption("San Juan, Puerto Rico", 750, "No passport"),
    DestinationOption("Miami, Florida", 800, "Easy flights"),
]


class FakeAgent:
    def __init__(self, replies=("agent reply",)):
        self.replies = list(replies)
        self.messages_seen = []

    def respond(self, trip, message):
        self.messages_seen.append(message.text)
        return self.replies


class BrokenAgent:
    def respond(self, trip, message):
        raise ConnectionError("Claude is unreachable")


def send(store, agent, sender, text):
    message = IncomingMessage(
        space_id=SPACE,
        sender_phone=sender,
        text=text,
        sent_at=datetime(2026, 10, 2, 9, 0),
        participant_phones=EVERYONE,
    )
    return handle_message(message, store, agent)


def start_voting(store):
    store.create_trip(SPACE)
    store.add_members(SPACE, list(EVERYONE))
    store.open_poll(SPACE, OPTIONS)


def test_first_message_in_a_chat_gets_the_introduction(store):
    replies = send(store, FakeAgent(replies=[]), MAYA, "hey everyone")

    assert replies == [INTRODUCTION]


def test_everyone_in_the_chat_joins_the_trip_including_quiet_members(store):
    send(store, FakeAgent(), MAYA, "hey everyone")

    members = store.get_trip(SPACE).members
    assert {member.phone for member in members} == set(EVERYONE)


def test_untagged_messages_go_to_the_agent_while_collecting_preferences(store):
    agent = FakeAgent()
    send(store, agent, MAYA, "hey everyone")

    replies = send(store, agent, LEO, "mar 14-20, $600, nyc")

    assert agent.messages_seen[-1] == "mar 14-20, $600, nyc"
    assert replies == ["agent reply"]


def test_untagged_chatter_is_ignored_once_preferences_are_done(store):
    start_voting(store)
    agent = FakeAgent()

    replies = send(store, agent, LEO, "did anyone see the game")

    assert replies == []
    assert agent.messages_seen == []


def test_tagged_messages_always_reach_the_agent(store):
    start_voting(store)
    agent = FakeAgent()

    replies = send(store, agent, LEO, "@scout which one has better food?")

    assert replies == ["agent reply"]


def test_a_plain_vote_is_counted_without_the_agent(store):
    start_voting(store)
    agent = FakeAgent()

    replies = send(store, agent, LEO, "2")

    assert agent.messages_seen == []
    assert store.get_trip(SPACE).open_poll.votes == {LEO: 1}
    assert replies == ["Got it, …0002 → San Juan, Puerto Rico (1 of 3 voted)"]


def test_last_vote_closes_the_poll_and_announces_the_winner(store):
    start_voting(store)
    agent = FakeAgent()

    send(store, agent, MAYA, "1")
    send(store, agent, LEO, "1")
    replies = send(store, agent, PRIYA, "3")

    trip = store.get_trip(SPACE)
    assert trip.stage == TripStage.DESTINATION_CHOSEN
    assert trip.destination == "Tulum, Mexico"
    assert replies == ["🎉 Poll closed! Tulum, Mexico wins with 2 of 3 votes."]


def test_last_vote_also_sends_a_calendar_link_for_the_shared_dates(store):
    start_voting(store)
    for member in EVERYONE:
        store.save_preferences(
            SPACE,
            member,
            PreferenceUpdate(
                available_from=date(2027, 3, 14),
                available_to=date(2027, 3, 19),
                budget_usd=800,
                home_city="Boston",
            ),
        )
    agent = FakeAgent()

    send(store, agent, MAYA, "2")
    send(store, agent, LEO, "2")
    replies = send(store, agent, PRIYA, "2")

    assert replies[0] == "🎉 Poll closed! San Juan, Puerto Rico wins with 3 of 3 votes."
    assert replies[1].startswith("📅 Locked in: San Juan, Puerto Rico, Mar 14–19.")


def test_scout_apologizes_when_it_fails_on_a_message_addressed_to_it(store):
    start_voting(store)

    replies = send(store, BrokenAgent(), LEO, "@scout what are the options again?")

    assert replies == [SNAG_REPLY]


def test_scout_stays_quiet_when_it_fails_on_a_message_not_addressed_to_it(store):
    store.create_trip(SPACE)

    replies = send(store, BrokenAgent(), LEO, "mar 14-20, $600, nyc")

    assert replies == []


def test_replies_are_saved_so_the_agent_sees_them_next_time(store):
    send(store, FakeAgent(replies=["Got it, Maya"]), MAYA, "hey, I'm maya")

    logged = [(m.sender_phone, m.text) for m in store.recent_messages(SPACE, 10)]
    assert logged == [
        (MAYA, "hey, I'm maya"),
        (None, INTRODUCTION),
        (None, "Got it, Maya"),
    ]
