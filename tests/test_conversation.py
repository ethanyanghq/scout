"""The whole message flow, with Claude replaced by a stand-in.

Claude is the one external service here, so it's the one thing faked. The
store, polls, and summaries are all real.
"""

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from scout.conversation import (
    INTRODUCTION_SNAG_REPLY,
    SNAG_REPLY,
    handle_message,
    handle_reaction,
)
from scout.outgoing import Card, Link, React, Say, Tapback
from scout.places import Coordinates, Place
from scout.polls import format_poll
from scout.trip import (
    DeckActivity,
    DestinationOption,
    IncomingMessage,
    IncomingReaction,
    MediaKind,
    Rating,
    SharedMedia,
    TripStage,
)


def said(outgoing):
    """The texts scout sent, failing on anything that isn't a plain text."""
    assert all(isinstance(item, Say) for item in outgoing), outgoing
    return [item.text for item in outgoing]


SPACE = "group-chat-1"
MAYA = "+15550000001"
LEO = "+15550000002"
PRIYA = "+15550000003"
EVERYONE = (MAYA, LEO, PRIYA)
RECEIPT_MEDIA = SharedMedia(
    id="a1b2c3d4",
    kind=MediaKind.PHOTO,
    original_path=Path("media/group-chat-1/a1b2c3d4.heic"),
    readable_path=Path("media/group-chat-1/a1b2c3d4.readable.jpg"),
    transcript="A receipt from Casa Brisa, total $164.00",
)
BOSTON_VOICE_NOTE = SharedMedia(
    id="e5f6a7b8",
    kind=MediaKind.VOICE_NOTE,
    original_path=Path("media/group-chat-1/e5f6a7b8.caf"),
    readable_path=Path("media/group-chat-1/e5f6a7b8.readable.m4a"),
    transcript="I'm flying from Boston.",
)
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
        return [Say(text) for text in self.replies]


class FakeGate:
    """Says SPEAK to messages containing "trigger" and SILENT to the rest, so a
    test picks which untagged messages scout looks at."""

    def should_speak(self, trip, message):
        return "trigger" in message.text


class BrokenAgent:
    def respond(self, trip, message):
        raise ConnectionError("Claude is unreachable")


def send(store, agent, sender, text, media=None):
    message = IncomingMessage(
        space_id=SPACE,
        sender_phone=sender,
        text=text,
        sent_at=datetime(2026, 10, 2, 9, 0),
        participant_phones=EVERYONE,
        media=media,
    )
    return said(handle_message(message, store, agent, FakeGate()))


def send_from_line(store, agent, sender, text, message_id):
    """Sends a message the way a real line does: with the line's ID for it."""
    message = IncomingMessage(
        space_id=SPACE,
        sender_phone=sender,
        text=text,
        sent_at=datetime(2026, 10, 2, 9, 0),
        participant_phones=EVERYONE,
        message_id=message_id,
    )
    return handle_message(message, store, agent, FakeGate())


def scout_joins(store):
    """A chat scout already introduced itself in."""
    store.create_trip(SPACE)
    store.log_message(SPACE, None, "Hey all, I'm scout 👋", datetime(2026, 10, 2, 8, 0))


def start_voting(store):
    scout_joins(store)
    store.add_members(SPACE, list(EVERYONE))
    store.open_poll(SPACE, OPTIONS)


def choose_san_juan(store):
    start_voting(store)
    poll_id = store.get_trip(SPACE).open_poll.id
    store.close_poll(poll_id, "San Juan, Puerto Rico", None)


def test_scout_introduces_itself_then_sends_the_trip_interview_card(store):
    agent = FakeAgent(replies=["Hey all, I'm scout 👋 Yep, I'm here!"])

    *introduction, card, nudge = send_from_line(
        store, agent, MAYA, "@scout you there?", None
    )

    assert agent.messages_seen == ["@scout you there?"]
    assert said(introduction) == ["Hey all, I'm scout 👋 Yep, I'm here!"]
    assert isinstance(card, Card)
    assert card.caption == "Plan your trip"
    assert nudge == Say(
        "fill this out, takes like 30 sec. i'll come back with options once "
        "everyone's in"
    )


def test_the_trip_interview_card_goes_out_only_with_the_introduction(store):
    agent = FakeAgent(replies=["Hey all, I'm scout 👋"])
    send_from_line(store, agent, MAYA, "@scout you there?", None)
    agent.replies = ["Got it, Leo"]

    replies = send(store, agent, LEO, "@scout leo here, march works")

    assert replies == ["Got it, Leo"]


def test_scout_stays_quiet_about_a_snag_on_a_message_nobody_tagged_it_in(store):
    scout_joins(store)

    replies = send(store, BrokenAgent(), LEO, "trigger: can someone find flights?")

    assert replies == []


def test_scout_says_it_hit_a_snag_when_it_cant_introduce_itself(store):
    replies = send(store, BrokenAgent(), MAYA, "@scout hey")

    assert replies == [INTRODUCTION_SNAG_REPLY]


def test_scout_stays_silent_in_a_new_chat_when_the_gate_says_silent(store):
    agent = FakeAgent(replies=["Hey all, I'm scout 👋"])

    first = send(store, agent, MAYA, "hey everyone, someone added a bot?")
    *introduction, _card, _nudge = send_from_line(
        store, agent, LEO, "@scout you there?", None
    )

    assert first == []
    assert agent.messages_seen == ["@scout you there?"]
    assert said(introduction) == ["Hey all, I'm scout 👋"]


def test_everyone_in_the_chat_joins_the_trip_including_quiet_members(store):
    send(store, FakeAgent(), MAYA, "hey everyone")

    members = store.get_trip(SPACE).members
    assert {member.phone for member in members} == set(EVERYONE)


def test_talking_about_scout_without_the_at_sign_is_left_to_the_gate(store):
    scout_joins(store)
    agent = FakeAgent()

    replies = send(store, agent, LEO, "scout seems useful")

    assert replies == []
    assert agent.messages_seen == []


def test_greeting_scout_by_name_in_a_text_is_a_tag(store):
    scout_joins(store)
    agent = FakeAgent()

    for greeting in ["Yo Scout", "hey scout, where are we at?", "Scout, help"]:
        send(store, agent, MAYA, greeting)

    assert agent.messages_seen == [
        "Yo Scout",
        "hey scout, where are we at?",
        "Scout, help",
    ]


def test_scout_misheard_as_scott_is_still_a_tag(store):
    scout_joins(store)
    agent = FakeAgent()
    misheard = replace(
        BOSTON_VOICE_NOTE, transcript="Hey Scott, I'm flying from Boston."
    )

    send(store, agent, MAYA, "", media=misheard)
    send(store, agent, LEO, "at Scott what's the plan")

    assert len(agent.messages_seen) == 2


def test_a_voice_note_that_says_scouts_name_to_it_is_a_tag(store):
    scout_joins(store)
    agent = FakeAgent()

    spoken_tags = [
        "Hey Scout, I'm flying from Boston.",
        "at scout what's the plan",
        "Scout, help",
    ]
    for number, words in enumerate(spoken_tags):
        voice_note = replace(BOSTON_VOICE_NOTE, id=f"note{number}", transcript=words)
        send(store, agent, MAYA, "", media=voice_note)

    assert len(agent.messages_seen) == 3


def test_a_voice_note_that_only_talks_about_scout_is_not_a_tag(store):
    scout_joins(store)
    agent = FakeAgent()
    in_passing = replace(BOSTON_VOICE_NOTE, transcript="let's ask scout later")

    send(store, agent, MAYA, "", media=in_passing)

    assert agent.messages_seen == []


def test_untagged_trip_details_get_no_reply_when_the_gate_says_silent(store):
    scout_joins(store)
    agent = FakeAgent()

    replies = send(store, agent, LEO, "mar 14-20, $600, nyc")

    assert replies == []
    assert agent.messages_seen == []


def test_an_untagged_message_the_gate_approves_reaches_the_agent(store):
    scout_joins(store)
    agent = FakeAgent()

    replies = send(store, agent, LEO, "anyone know a trigger for flights?")

    assert replies == ["agent reply"]


def test_an_untagged_message_the_gate_approves_can_be_answered_with_silence(store):
    scout_joins(store)

    replies = send(store, FakeAgent(replies=[]), LEO, "trigger: lol same")

    assert replies == []


def test_a_tag_skips_the_gate(store):
    scout_joins(store)

    class GateThatMustNotRun:
        def should_speak(self, trip, message):
            raise AssertionError("a tag shouldn't need the gate")

    message = IncomingMessage(
        SPACE,
        LEO,
        "@scout hi",
        datetime(2026, 10, 2, 9, 0),
        participant_phones=EVERYONE,
    )
    agent = FakeAgent()

    handle_message(message, store, agent, GateThatMustNotRun())

    assert agent.messages_seen == ["@scout hi"]


def test_a_threaded_reply_to_scouts_own_text_skips_the_gate(store):
    scout_joins(store)
    store.log_message(
        SPACE, None, "want me to pull flights?", datetime(2026, 10, 2, 8, 5)
    )
    agent = FakeAgent()

    reply_in_thread(
        store, agent, LEO, "yes pls", replying_to="want me to pull flights?"
    )

    assert agent.messages_seen == ["yes pls"]


def test_tagged_messages_always_reach_the_agent(store):
    start_voting(store)
    agent = FakeAgent()

    replies = send(store, agent, LEO, "@scout which one has better food?")

    assert replies == ["agent reply"]


def test_a_plain_vote_gets_a_thumbs_up_instead_of_a_line_in_the_chat(store):
    start_voting(store)

    replies = send_from_line(store, FakeAgent(), LEO, "2", message_id="leo-vote")

    assert replies == [
        React(
            "leo-vote",
            Tapback.LIKE,
            fallback_text="got it, …0002 → San Juan, Puerto Rico (1 of 3 voted)",
        )
    ]


def test_the_vote_that_closes_the_poll_gets_the_announcement_not_a_tapback(store):
    start_voting(store)
    send_from_line(store, FakeAgent(), MAYA, "1", message_id="maya-vote")
    send_from_line(store, FakeAgent(), LEO, "1", message_id="leo-vote")

    replies = send_from_line(store, FakeAgent(), PRIYA, "3", message_id="priya-vote")

    assert replies[0] == Say("poll's closed: Tulum, Mexico wins with 2 of 3 votes 🎉")


def test_last_vote_closes_the_poll_and_announces_the_winner(store):
    start_voting(store)
    agent = FakeAgent()

    send(store, agent, MAYA, "1")
    send(store, agent, LEO, "1")
    replies = send(store, agent, PRIYA, "3")

    trip = store.get_trip(SPACE)
    assert trip.stage == TripStage.DESTINATION_CHOSEN
    assert trip.destination == "Tulum, Mexico"
    assert replies == ["poll's closed: Tulum, Mexico wins with 2 of 3 votes 🎉"]


def test_scout_apologizes_when_it_fails_on_a_message_addressed_to_it(store):
    start_voting(store)

    replies = send(store, BrokenAgent(), LEO, "@scout what are the options again?")

    assert replies == [SNAG_REPLY]


def test_scout_stays_quiet_when_it_fails_on_a_message_not_addressed_to_it(store):
    scout_joins(store)

    replies = send(store, BrokenAgent(), LEO, "mar 14-20, $600, nyc")

    assert replies == []


def test_replies_are_saved_so_the_agent_sees_them_next_time(store):
    agent = FakeAgent(replies=["got it, Maya"])
    send_from_line(store, agent, MAYA, "@scout hey, I'm maya", None)

    logged = [(m.sender_phone, m.text) for m in store.recent_messages(SPACE, 10)]
    assert logged == [
        (MAYA, "@scout hey, I'm maya"),
        (None, "got it, Maya"),
        (None, "[card] Plan your trip"),
        (
            None,
            "fill this out, takes like 30 sec. i'll come back with options once "
            "everyone's in",
        ),
    ]


def test_untagged_receipt_photos_get_no_reply_when_the_gate_says_silent(store):
    choose_san_juan(store)
    agent = FakeAgent()

    send(store, agent, PRIYA, "casa brisa dinner 👆", media=RECEIPT_MEDIA)

    assert agent.messages_seen == []


def test_the_chat_log_holds_a_photos_description_and_where_its_kept(store):
    choose_san_juan(store)

    send(store, FakeAgent(), PRIYA, "casa brisa dinner", media=RECEIPT_MEDIA)

    assert store.recent_messages(SPACE, limit=1)[0].text == (
        "[photo a1b2c3d4 (media/group-chat-1/a1b2c3d4.heic): "
        "A receipt from Casa Brisa, total $164.00] casa brisa dinner"
    )


def test_the_chat_log_holds_a_voice_notes_words(store):
    scout_joins(store)

    send(store, FakeAgent(), MAYA, "", media=BOSTON_VOICE_NOTE)

    assert store.recent_messages(SPACE, limit=1)[0].text == (
        "[voice note e5f6a7b8 (media/group-chat-1/e5f6a7b8.caf): "
        '"I\'m flying from Boston."]'
    )


def test_a_shared_photo_can_be_found_again_by_its_id(store):
    choose_san_juan(store)

    send(store, FakeAgent(), PRIYA, "", media=RECEIPT_MEDIA)

    assert store.find_media(SPACE, "a1b2c3d4") == RECEIPT_MEDIA


TACO_SPOTS = [
    Place("place-1", "Lote 23", Coordinates(18.45, -66.07), "$$", None),
    Place("place-2", "Taco Bar", Coordinates(18.46, -66.08), "$", None),
]


def test_a_plain_pick_sends_directions_without_the_agent(store):
    choose_san_juan(store)
    store.replace_place_suggestions(SPACE, TACO_SPOTS)
    agent = FakeAgent()

    replies = send_from_line(store, agent, LEO, "2", message_id="leo-pick")

    assert agent.messages_seen == []
    assert replies[0] == Say("directions to Taco Bar:")
    assert isinstance(replies[1], Link)


def test_picks_sent_from_the_deck_are_saved_without_the_agent(store):
    choose_san_juan(store)
    store.replace_activity_deck(
        SPACE,
        [DeckActivity("Night kayak", "", 60), DeckActivity("Food tour", "", 80)],
    )
    agent = FakeAgent()

    replies = send_from_line(
        store,
        agent,
        LEO,
        "@scout my picks: Night kayak nah · Food tour meh",
        message_id="leo-picks",
    )

    assert agent.messages_seen == []
    assert replies == [
        React(
            "leo-picks", Tapback.LIKE, fallback_text="got …0002's picks (1 of 3 sent)"
        )
    ]
    assert store.get_trip(SPACE).activity_deck.picks == {LEO: {1: Rating.MEH}}


def test_the_last_picks_from_the_deck_bring_the_agent_in_to_plan(store):
    choose_san_juan(store)
    store.replace_activity_deck(SPACE, [DeckActivity("Night kayak", "", 60)])
    agent = FakeAgent(replies=["the plan: ..."])
    for sender in (MAYA, LEO):
        send_from_line(
            store, agent, sender, "@scout my picks: Night kayak yeah", message_id="x"
        )
    assert agent.messages_seen == []

    replies = send_from_line(
        store, agent, PRIYA, "@scout my picks: Night kayak yeah", message_id="priya"
    )

    assert agent.messages_seen == ["@scout my picks: Night kayak yeah"]
    assert replies == [Say("the plan: ...")]


def tapback(store, sender, on_text, kind="like", on_id="option-message"):
    reaction = IncomingReaction(
        space_id=SPACE,
        sender_phone=sender,
        tapback=kind,
        message_id=on_id,
        message_text=on_text,
        sent_at=datetime(2026, 10, 2, 9, 0),
    )
    return handle_reaction(reaction, store)


POLL_QUESTION, TULUM_OPTION, SAN_JUAN_OPTION, MIAMI_OPTION = format_poll(OPTIONS)


def test_a_thumbs_up_on_a_poll_option_counts_as_a_vote(store):
    start_voting(store)

    replies = tapback(store, LEO, SAN_JUAN_OPTION, on_id="san-juan-option")

    assert store.get_trip(SPACE).open_poll.votes == {LEO: 1}
    assert replies == [
        Say(
            "got it, …0002 → San Juan, Puerto Rico (1 of 3 voted)",
            reply_to="san-juan-option",
        )
    ]


def test_a_laugh_on_a_poll_option_is_not_a_vote(store):
    start_voting(store)

    replies = tapback(store, LEO, MIAMI_OPTION, kind="laugh")

    assert replies == []
    assert store.get_trip(SPACE).open_poll.votes == {}


def reply_in_thread(store, agent, sender, text, replying_to):
    message = IncomingMessage(
        space_id=SPACE,
        sender_phone=sender,
        text=text,
        sent_at=datetime(2026, 10, 2, 9, 0),
        participant_phones=EVERYONE,
        message_id="reply-message",
        reply_to_text=replying_to,
    )
    return handle_message(message, store, agent, FakeGate())


def test_an_untagged_threaded_reply_under_a_poll_option_is_just_chat(store):
    start_voting(store)
    agent = FakeAgent()

    reply_in_thread(store, agent, LEO, "this one!", replying_to=SAN_JUAN_OPTION)

    assert agent.messages_seen == []


def test_the_chat_log_shows_what_a_threaded_reply_answers(store):
    start_voting(store)

    reply_in_thread(
        store, FakeAgent(replies=[]), LEO, "this one!", replying_to=SAN_JUAN_OPTION
    )

    logged = store.recent_messages(SPACE, limit=1)[0]
    assert logged.text == f'(replying to "{SAN_JUAN_OPTION}") this one!'


def test_the_first_trip_card_answer_gets_scouts_progress_teaser_and_no_canned_reply(
    store,
):
    scout_joins(store)
    teaser = "1 of 3 in. leaning lakeside under ~$1,200… waiting on 2 more"
    agent = FakeAgent(replies=[teaser])

    replies = send(
        store, agent, MAYA, "@scout my trip: Lakeside · $1,200 · from Boston"
    )

    assert replies == [teaser]
    assert agent.messages_seen == ["@scout my trip: Lakeside · $1,200 · from Boston"]


class ThumbsUpAgent:
    """Reacts with a 👍 to the message it answers, as a preference save does."""

    def respond(self, trip, message):
        return [React(message.message_id, Tapback.LIKE, fallback_text="saved")]


def test_the_first_trip_card_answer_keeps_its_thumbs_up(store):
    scout_joins(store)

    replies = send_from_line(
        store,
        ThumbsUpAgent(),
        MAYA,
        "@scout my trip: Lakeside · $1,200 · from Boston",
        message_id="maya-card-answer",
    )

    assert replies == [React("maya-card-answer", Tapback.LIKE, fallback_text="saved")]


def test_sending_the_trip_card_again_gets_no_reply(store):
    scout_joins(store)
    agent = FakeAgent(replies=[])
    send(store, agent, MAYA, "@scout my trip: Lakeside · $1,200 · from Boston")

    again = send(store, agent, MAYA, "@scout my trip: Lakeside · $1,200 · from Boston")

    assert again == []
    assert len(agent.messages_seen) == 1


def test_a_later_trip_card_answer_gets_only_the_thumbs_up(store):
    scout_joins(store)
    send(store, FakeAgent(replies=[]), MAYA, "@scout my trip: Lakeside · $1,200")

    leos = send_from_line(
        store,
        ThumbsUpAgent(),
        LEO,
        "@scout my trip: City break · $900 · from NYC",
        message_id="leo-card-answer",
    )

    assert leos == [React("leo-card-answer", Tapback.LIKE, fallback_text="saved")]
