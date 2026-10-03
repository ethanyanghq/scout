# scout

An AI trip planner that lives in your group chat. Add scout to a group text and it collects everyone's dates, budget, and must-haves, suggests three destinations, and runs the vote. See [scout-PRD.md](scout-PRD.md) for the full product.

**Status:** Phase 1 (the core loop: join, collect preferences, vote on a destination).

## How it fits together

```
iMessage ⇄ Photon (spectrum-ts) ⇄ bridge/  ──HTTP──▶  src/scout/  ⇄ Claude API
                                  TypeScript          Python         + SQLite
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
| `trip_store.py` | Saving everything to SQLite. |
| `simulate.py` | A fake group chat in your terminal for testing without phones. |

## Setup

You need [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh), and an Anthropic API key.

```sh
uv sync
cd bridge && bun install && cd ..
export ANTHROPIC_API_KEY=sk-ant-...
```

## Try it without phones

Run a whole group chat in your terminal, playing every person yourself:

```sh
uv run scout-simulate maya leo jordan priya
> maya: hey @scout, spring break?
> maya: i'm maya, free mar 13-20, ~$800, flying from boston, need a beach
> leo: leo here, mar 14-22, 600, nyc
...
> leo: 2
```

Add `--verbose` to see each tool scout calls.

## Run it on iMessage

scout needs its own iMessage account. In local mode that's an Apple ID signed into Messages on a Mac, ideally in a separate macOS user called "scout" so it never sees your own chats. The Mac has to stay on and awake, with the scout user logged in (switch users from the menu bar; don't log out).

1. In the scout user, sign into Messages with scout's Apple ID and set **Messages → Settings → Share Name and Photo** to "scout".
2. Give Terminal Full Disk Access (**System Settings → Privacy & Security**) so the bridge can read Messages.
3. Install [uv](https://docs.astral.sh/uv/) and [Bun](https://bun.sh), clone this repo, then run `uv sync` and `cd bridge && bun install`.
4. Create `.env` in the repo root with your Anthropic key:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
5. Create `bridge/.env` with one of these:
   - Local mode, which runs on this Mac's Messages account and needs no Photon plan. See [scout-imessage-groups.md](scout-imessage-groups.md). scout only reads and replies in the one group chat named here, which must match the group's name in Messages exactly:
     ```
     IMESSAGE_MODE=local
     SCOUT_GROUP_NAME="BRH Spring Break Trip"
     ```
   - A Photon cloud line:
     ```
     IMESSAGE_MODE=cloud
     PHOTON_PROJECT_ID=...
     PHOTON_PROJECT_SECRET=...
     ```
6. Run `./start.sh`. It starts the Python service, waits for it, then starts the bridge, and keeps the Mac awake until you press Ctrl-C. On a MacBook, closing the lid still sleeps it: leave the lid open, or run `sudo pmset -a disablesleep 1` (and `sudo pmset -a disablesleep 0` afterwards).
7. Add scout's Apple ID or number to a group text and say "hi scout".

In local mode scout ignores every chat except `SCOUT_GROUP_NAME`, so it can run on a real person's Messages account. It also ignores messages sent from that account, so whoever owns it shouldn't type in the group while scout is running. On a cloud line scout plans in any group chat and ignores one-on-one texts.

## Development

```sh
uv run pytest                  # tests
uv run ruff check src tests    # lint
uv run ruff format src tests   # format
cd bridge && bun run typecheck # type-check the bridge
```
