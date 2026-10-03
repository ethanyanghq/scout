from datetime import datetime

import pytest

from scout.trip import IncomingMessage


def message(text):
    return IncomingMessage("group-chat-1", "+15550000001", text, datetime(2027, 3, 16))


@pytest.mark.parametrize(
    "text",
    [
        "fyi I paid the airbnb, $1,240",
        "dinner was me, $ 164",
        "got the kayaks, 196 dollars",
        "gas was 40 bucks",
        "parking 12.50 USD",
    ],
)
def test_dollar_amounts_count_as_money_mentions(text):
    assert message(text).mentions_money


@pytest.mark.parametrize(
    "text",
    ["2", "meet at 7", "we need 4 towels", "see you in 10 min", "dollars to donuts"],
)
def test_plain_numbers_are_not_money_mentions(text):
    assert not message(text).mentions_money
