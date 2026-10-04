"""Opens the activity deck in a browser, to try its layout and swipes without a
phone. The page is a stand-in: it draws the layout JSON that `cards.activity_deck`
builds, but HermesShare's own SwiftUI renderer is what people actually see.
"""

import json
import tempfile
import webbrowser
from pathlib import Path

from scout.cards import activity_deck
from scout.trip import DeckActivity

PAGE_TEMPLATE = Path(__file__).with_name("deck_preview.html")
LAYOUT_PLACEHOLDER = "__LAYOUT_JSON__"

SAMPLE_ACTIVITIES = [
    DeckActivity(
        "Myrtle Beach Boardwalk",
        "Stroll the oceanfront strip past arcades, snack stands and the SkyWheel. "
        "Allow 2 to 3 hours; free to walk, rides and food extra. Great at sunset.",
        0,
    ),
    DeckActivity(
        "Night kayak in the bio bay",
        "Paddle a glowing bay in a guided group. About 2 hours, kayak and guide "
        "included. Best for people comfortable on the water.",
        60,
    ),
    DeckActivity(
        "Old San Juan food tour",
        "Taste your way through the old town with a local guide. About 3 hours, "
        "six tastings included. Suits anyone who likes to eat.",
        75,
    ),
]


def main() -> None:
    layout = activity_deck("Myrtle Beach", SAMPLE_ACTIVITIES)
    page = PAGE_TEMPLATE.read_text().replace(LAYOUT_PLACEHOLDER, json.dumps(layout))
    path = Path(tempfile.gettempdir()) / "scout-deck-preview.html"
    path.write_text(page)
    print(f"Opening {path}")
    webbrowser.open(path.as_uri())
