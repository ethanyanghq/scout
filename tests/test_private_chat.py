from datetime import datetime

from scout.outgoing import Say
from scout.private_chat import handle_private_message
from scout.trip import IncomingMessage

YUVRAJ = "+15550007695"


def dm(store, text):
    message = IncomingMessage(
        "dm-yuvraj", YUVRAJ, text, datetime(2026, 10, 4, 2, 35), (YUVRAJ,)
    )
    return handle_private_message(message, store)


def test_a_first_text_asks_for_the_persons_name(store):
    [reply] = dm(store, "hello")

    assert "what should i call you?" in reply.text


def test_the_name_they_give_is_greeted_and_remembered(store):
    dm(store, "hello")

    assert dm(store, "Yuvraj") == [
        Say(
            "nice to meet you, Yuvraj! "
            "add me to your group chat and i'll take it from there"
        )
    ]
    assert store.find_name(YUVRAJ) == "Yuvraj"


def test_later_texts_say_scout_only_works_in_group_chats(store):
    dm(store, "hello")
    dm(store, "Yuvraj")

    assert dm(store, "can you plan a trip for me?") == [
        Say(
            "Yuvraj, I only work within group chats. "
            "Add me to one and I'll help you plan a trip!"
        )
    ]
