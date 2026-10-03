# scout

An AI trip planner that lives in your group chat. Add scout to a group text and it collects everyone's dates, budget, and must-haves, suggests three destinations, runs the vote, and then plans the days and sends booking and calendar links. See [scout-PRD.md](scout-PRD.md) for the full product.

**Status:** Phase 1 (join, collect preferences, vote on a destination) is done. Phase 2 so far has the itinerary, booking links, the Add to Google Calendar link, and cost splitting: logging expenses from the chat or a receipt photo, and settling up over Capital One's Nessie sandbox.

## How it fits together

```
iMessage ⇄ Photon (spectrum-ts) ⇄ bridge/  ──HTTP──▶  src/scout/  ⇄ Claude API
                                  TypeScript          Python         + SQLite
                                                                     + Nessie
```

Photon only sends messages from TypeScript, so `bridge/` is a thin relay. Everything scout knows and decides lives in the Python service:

| File | What it does |
| --- | --- |
| `conversation.py` | Decides what happens with each message: introduce scout, count a vote, ask the agent, or stay quiet. |
| `agent.py` | Shows Claude the trip and the recent chat, then runs the tools Claude picks. |
| `system_prompt.md` | scout's instructions: when to speak, how to text, the planning flow. |
| `agent_tools.py` | The tools Claude can call, and how each call maps onto a trip action. |
| `trip_actions.py` | The changes scout can make to a trip (save preferences, post a poll, record a vote). |
| `group_summary.py` | Date overlap, budget range, and who hasn't replied. |
| `polls.py` | Reading "2" or "tulum" as a vote, and picking the winner. |
| `itinerary.py` | How the day-by-day plan reads in the chat. |
| `booking_links.py` | Google Flights links from each home city and an Airbnb link for the group. |
| `calendar_link.py` | The "Add to Google Calendar" link sent once the trip is locked in. |
| `money.py` | How amounts of money read in the chat. |
| `settle_up.py` | Who owes whom: each person's share and the fewest payments to settle up. |
| `nessie.py` | Paying members back with sandbox money over Capital One's Nessie API. |
| `trip_store.py` | Saving everything to SQLite. |
| `simulate.py` | A fake group chat in your terminal for testing without phones. |

## Setup

You need [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh), and an Anthropic API key.

```sh
uv sync
cd bridge && bun install && cd ..
export ANTHROPIC_API_KEY=sk-ant-...
export NESSIE_API_KEY=...   # optional; without it, payments are simulated
```

Settling up pays members back over [Nessie](https://api.nessieisreal.com), Capital One's sandbox bank, so no real money moves. scout opens a Nessie account for each member on their first payment. If `NESSIE_API_KEY` isn't set, or Nessie is down, scout still records the payment and says in the chat that it was simulated.

There are no database migrations yet. After pulling a change to the database layout, delete your local `scout.db`.

## Try it without phones

Run a whole group chat in your terminal, playing every person yourself:

```sh
uv run scout-simulate maya leo jordan priya
> maya: hey @scout, spring break?
> maya: i'm maya, free mar 13-20, ~$800, flying from boston, need a beach
> leo: leo here, mar 14-22, 600, nyc
...
> leo: 2
> leo: fyi I paid the airbnb, $1,240
> jordan: @scout who owes what
> jordan: @scout pay leo
```

Add `--verbose` to see each tool scout calls.

## Run it on iMessage

1. Start the Python service: `uv run scout-server` (listens on `127.0.0.1:8787`).
2. Create `bridge/.env` with one of these:
   - Local mode, which runs on this Mac's Messages account. It needs Full Disk Access for your terminal, and no Photon plan. See [scout-imessage-groups.md](scout-imessage-groups.md).
     ```
     IMESSAGE_MODE=local
     ```
   - A Photon cloud line:
     ```
     IMESSAGE_MODE=cloud
     PHOTON_PROJECT_ID=...
     PHOTON_PROJECT_SECRET=...
     ```
3. Start the bridge: `cd bridge && bun start`.
4. Add scout's number or Apple ID to a group text and say hi.

## Development

```sh
uv run pytest                  # tests
uv run ruff check src tests    # lint
uv run ruff format src tests   # format
cd bridge && bun run typecheck # type-check the bridge
```
