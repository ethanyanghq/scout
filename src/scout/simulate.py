"""Play a whole group chat with scout in your terminal, no phones needed.

    uv run scout-simulate maya leo jordan priya

Then type messages as "name: text", for example "leo: mar 14-20, $600, nyc".
Uses the real agent (and your Anthropic or OpenAI API key) with a throwaway
database.
"""

import argparse
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from scout.ai_provider import connect_agent, connect_speak_gate
from scout.conversation import Agent, Gate, handle_message
from scout.outgoing import as_plain_text
from scout.outside_services import connect_outside_services
from scout.trip import IncomingMessage
from scout.trip_store import TripStore

SIMULATED_SPACE_ID = "simulated-group-chat"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("people", nargs="+", help="names of everyone in the chat")
    parser.add_argument(
        "--verbose", action="store_true", help="show tool calls and other logs"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    phones = {
        name.lower(): f"+1555000{number:04d}"
        for number, name in enumerate(args.people, start=1)
    }
    with tempfile.TemporaryDirectory() as scratch:
        store = TripStore(Path(scratch) / "simulated.db")
        agent = connect_agent(store, connect_outside_services())
        gate = connect_speak_gate(store)
        print(f"Group chat with {', '.join(args.people)}. Ctrl-D to quit.")
        _chat(phones, store, agent, gate)


def _chat(phones: dict[str, str], store: TripStore, agent: Agent, gate: Gate) -> None:
    while True:
        try:
            line = input("> ")
        except EOFError:
            return
        name, separator, text = line.partition(":")
        if not separator or name.strip().lower() not in phones:
            print(f"Start with one of: {', '.join(phones)}, then a colon.")
            continue

        message = IncomingMessage(
            space_id=SIMULATED_SPACE_ID,
            sender_phone=phones[name.strip().lower()],
            text=text.strip(),
            sent_at=datetime.now(),
            participant_phones=tuple(phones.values()),
        )
        for reply in handle_message(message, store, agent, gate):
            print(f"\nscout: {as_plain_text(reply)}\n")
