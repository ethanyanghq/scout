# Developing scout

How to run scout, test a change in a group chat, and set up the demo group. It's written for teammates and their coding agents (Claude Code, Codex) alike.

- [AGENTS.md](AGENTS.md): coding rules, and rules for agents working with real messages.
- [scout-imessage-groups.md](scout-imessage-groups.md): why group chats run on a Linq line inside Photon's Spectrum SDK, and the plan for the tools below.
- [scout-group-chat-plan.md](scout-group-chat-plan.md): the plan for these tools, with its checklist.
- [TODO.md](TODO.md): everything else the demo needs.

## What exists today

Several tools are planned but not built yet. **If a tool is marked planned, it doesn't exist: use the "Today" column, and don't create it unless that's your task.**

| Tool | Status | Today |
| --- | --- | --- |
| Python service and TypeScript bridge | Built | |
| Linq group chats (`IMESSAGE_MODE=linq`) | Built, beside Spectrum rather than inside it | |
| Scripted chats with `scout-simulate` | Built | |
| Calling the service with `curl` | Built | |
| `bun run dev`: one command for everything | Built | |
| Event trace: one bridge log line per message | Built | |
| Developer console (`devchat`), scripts and `bun run e2e` | Built. Photos convert only on a Mac and can't have a caption yet. | |
| Seeded stages and resetting one chat | Built | |
| Linq as a Spectrum platform | Planned (plan, milestone 2) | The Linq relay in `bridge/linq.ts` |
| Tapbacks, threaded replies, effects and link cards | Planned (plan, milestone 2) | Text and photos only |
| Demo group commands | Planned (plan, milestone 3) | [Set up the demo group by hand](#set-up-the-demo-group) |

When a pull request ships one of these, it updates this table and the instructions below.

## How a message flows

```
iPhone in the group
  → Linq (scout's number)
  → linq webhooks listen, which relays to the bridge at 127.0.0.1:8788/linq-events
  → bridge/ (TypeScript), which posts to the service at 127.0.0.1:8787/messages
  → src/scout/conversation.py decides what to do
  ← the replies, a list of texts (empty means scout stays quiet)
  ← the bridge sends each one back to the group through Linq
```

- **One message at a time.** The bridge waits for scout's replies before reading the next message, so two votes can't race.
- **The bridge drops** private chats (in Linq mode), scout's own messages, messages with nothing to read (stickers, voice memos) and repeat deliveries.
- **The bridge logs one line per message**: `handled` with the reply count and time, `skipped` with the reason, or `failed` with the error.
- **The service decides whether to speak** (`conversation.py`). The first message in a chat gets the introduction. A plain vote ("2") or a pick of a nearby place is handled in code. Tagged messages, and untagged ones at certain stages, go to Claude. Everything else gets no reply.
- **Each chat is one trip**, saved in `scout.db` under the chat's ID (`space_id`).

## Test a change without phones

| You changed | Check it with |
| --- | --- |
| Rules, parsing or math (`polls.py`, `settle_up.py`, `group_summary.py`, …) | `uv run pytest` |
| What scout does with a message (`conversation.py`) | `uv run pytest tests/test_conversation.py`, which fakes Claude |
| What Claude says or does (`system_prompt.md`, `agent_tools.py`, `trip_actions.py`) | The developer console, or a console script |
| The bridge (`bridge/*.ts`) | `cd bridge && bun test && bun run typecheck`, then the developer console |
| A whole critical user journey | `cd bridge && bun run e2e` |

Whenever a message goes to Claude, these use the real Claude API, so they need `ANTHROPIC_API_KEY` in `.env`. Each such message takes about 10 seconds and costs tokens, so keep chats short and start from a seeded stage when you can. Claude's wording changes from run to run, so check what happened to the trip, not the exact text.

### Play a group chat with the developer console

The console plays a whole group through the real bridge and the running service, one shell command at a time, so AI agents can drive it too. Start the service first (`cd bridge && bun run dev`, or `uv run --env-file .env scout-server`), then from `bridge/`:

```sh
bun run devchat start maya leo priya --from poll-open   # a new chat, starting at the open poll
bun run devchat say maya 2                              # prints scout's replies once it's done
bun run devchat say leo "@scout is tulum too far?"
bun run devchat photo leo receipt.jpg                   # Mac only
bun run devchat transcript
bun run devchat state                                   # the trip, as JSON
bun run devchat reset                                   # clears this chat's trip and transcript
```

- Each `say` waits until scout has finished, then prints the message and scout's replies with their IDs (`[m3] scout: ...`). If scout didn't reply, it prints `(scout stayed quiet)` or why the bridge skipped the message.
- `start` without `--from` begins before the introduction. `--from poll-open` begins with everyone's preferences shared and the destination poll open. `--from destination-chosen` begins with San Juan picked for March 14–20, 2027.
- Members get the same numbers as in `scout-simulate`: +15550000001, +15550000002 and so on.
- The console's chat is saved in `bridge/.devchat/`, so each command picks up where the last one left off.
- `state --chat <id>` and `reset --chat <id>` work on any chat, including a real group's. Its chat ID is in the bridge's log lines.
- A photo can't have a caption yet. Send the caption as its own message.

### Script a conversation

A script is a plain-text file that reads like the chat. `bun run devchat run <file>` plays it in a new chat, prints the conversation, and stops at the first failure with its line number:

```
# Plain votes close the poll and announce the winner.
members maya leo priya
from poll-open

maya: 2
expect scout ~ "1 of 3 voted"
leo: lol this is taking forever
expect scout quiet
leo: 2
priya: 1
expect scout ~ "San Juan, Puerto Rico wins"
expect state destination = "San Juan, Puerto Rico"
```

| Line | Means |
| --- | --- |
| `members maya leo priya` | Who's in the chat. Required, before any message. |
| `from poll-open` | Start at a seeded stage: `poll-open` or `destination-chosen`. Optional. |
| `maya: text` | Maya sends a message. |
| `maya photo receipt.jpg` | Maya sends a photo. The path is relative to the script (Mac only). |
| `expect scout ~ "words"` | A reply to the latest message contains the words, ignoring case. |
| `expect scout quiet` | scout didn't reply to the latest message. |
| `expect state path = value` | The trip's value at a dotted path, such as `members.0.budget_usd`, equals a value: `"text"`, a number, `true`, `false` or `null`. `bun run devchat state` shows the paths. |
| `expect state path ~ "words"` | The trip's value at that path contains the words, ignoring case. |

Lines starting with `#` are comments. Check the trip's state, or a word a reply must contain, never whole replies.

### Run the end-to-end tests

`bridge/e2e/` holds a script for each critical user journey in AGENTS.md. `cd bridge && bun run e2e` starts a throwaway service on a free port, plays every script, and stops the service. `bun run e2e votes-and-winner.chat` runs one script. The service's log and database stay in `bridge/.devchat/e2e/` so you can look into failures.

Most journeys go through Claude. Without `ANTHROPIC_API_KEY`, only the introduction and the vote pass.

### Without the bridge: scout-simulate and curl

These skip the bridge and talk to the Python service directly.

Pipe a chat into `scout-simulate`, one message per line, as `name: message`. The run stops at the end of the input, so an agent can run it from a shell:

```sh
uv run --env-file .env scout-simulate maya leo priya --verbose <<'EOF'
maya: hey @scout, spring break?
maya: i'm maya, free mar 13-20, ~$800, flying from boston, need a beach
leo: leo here, mar 14-22, 600, nyc
priya: priya, mar 13-21, 700, chicago, want good food
leo: 2
EOF
```

- The members' phone numbers are +15550000001, +15550000002 and so on, in the order you name them.
- `--verbose` also prints each tool scout calls.
- Every run starts with an empty, throwaway database, and can't start at a seeded stage.
- Leave out the `<<'EOF'` block to type the chat yourself.

To call the service yourself, start it with its own database so your `scout.db` stays clean:

```sh
SCOUT_DB_PATH=/tmp/scout-test.db uv run --env-file .env scout-server
```

Then post messages to it. The same `space_id` means the same chat:

```sh
curl -s http://127.0.0.1:8787/messages -H 'Content-Type: application/json' -d '{
  "space_id": "test-chat-1",
  "sender_phone": "+15550000001",
  "text": "hey @scout, spring break?",
  "sent_at": "2026-10-03T12:00:00Z",
  "participant_phones": ["+15550000001", "+15550000002", "+15550000003"]
}'
# {"replies": ["Hey all, I'm scout 👋 ..."]}
```

- `participant_phones` is everyone in the group, including people who haven't texted yet.
- To send a photo, add `"photo": {"media_type": "image/jpeg", "base64_data": "..."}`. `text` can be empty.
- `GET /dev/trips/<space_id>` shows the trip, and `DELETE /dev/trips/<space_id>` resets it.
- To start over, use a new `space_id`, or stop the service and delete `/tmp/scout-test.db`.

## Run scout in a real group

This needs a Mac (the bridge converts iPhone photos with macOS's `sips`) and your own Linq line.

1. Get a line once: `npm i -g @linqapp/cli && linq signup`. `linq whoami` shows scout's number.
2. In `bridge/.env`, set `IMESSAGE_MODE=linq` and `LINQ_API_KEY` (copy `bridge/.env.example`).
3. Start everything with `cd bridge && bun run dev`. It checks your settings, the Linq login and free ports first, then runs the service, the bridge and the Linq relay in one terminal with labeled logs. Ctrl-C stops them all.
4. Add each tester with `linq contacts add` (the free line allows up to 20). Each tester texts scout's number privately once, because the free line only answers people who texted it first. scout ignores those private texts.
5. From an iPhone in the group, tap the group's name, then **Add Member**, and enter scout's number. Everyone must be on iMessage, and Apple may require at least three other members.

### When scout doesn't reply

1. **Find the bridge's line for the message** (`[bridge]` in `bun run dev`). `skipped` says why: a private chat, scout's own message, nothing to read, or a repeat delivery. `failed` shows the error from Linq's API or the service. `handled … scout stayed quiet` means the service chose not to reply (step 3).
2. **No line at all?** The message never reached the bridge. Is the relay running (`[relay]` in `bun run dev`)? Did the sender text scout privately first? The free line ignores anyone who hasn't.
3. **Did scout choose to stay quiet?** The service log shows each request. An untagged message only reaches Claude while preferences are being collected, or after a destination is chosen if it mentions money or has a photo (`_needs_agent_untagged` in `conversation.py`).
4. **Did the database layout change?** There are no migrations. Delete `scout.db`, and every group gets the introduction again.

## Add a group chat feature

| The feature needs | Where the code goes |
| --- | --- |
| A rule handled in code, like counting a vote | `conversation.py` (and a module like `polls.py`), tested in `tests/test_conversation.py` |
| Something Claude decides to do | A tool in `agent_tools.py`, the change in `trip_actions.py`, guidance in `system_prompt.md` |
| A new kind of incoming message, like a photo | The bridge's parsing (`bridge/spectrum.ts` for Spectrum, `bridge/linq.ts` for Linq), `IncomingText` in both `bridge/scout.ts` and `src/scout/app.py` (keep them identical), and `IncomingMessage` in `trip.py` |
| scout sending more than text (tapbacks, threaded replies, effects, link cards) | Not possible yet: the service only returns texts. See "Events in, actions out" in the design doc. |
| A test that starts later in the journey | A seeded stage in `src/scout/trip_seeds.py`, then `from <stage>` in a console script |

When a feature changes a critical user journey, update or add its script in `bridge/e2e/`.

When "events in, actions out" ships, each new action will land with four parts: a case in the bridge, an action type and agent tool in Python, how the developer console shows it, and a script that uses it.

### Link cards

iMessage never runs HTML or JavaScript in the chat. A link card is a preview of a page, and anything interactive lives on that page. Linq's rules:

- The link must be the only thing in its message.
- The URL must be HTTPS, and at most 2,048 characters.
- The card is built from the page's `og:title`, `og:description` and `og:image`, then Twitter Card tags, then the page's `<title>` and first image.
- The card is a snapshot from when it was sent. To show new state, send a new link.

Where scout's pages will be hosted isn't decided yet (TODO, Decide).

## Set up the demo group

Until the demo group commands exist (plan, milestone 3):

1. Pick one teammate's line as the demo line, and run the service, bridge and relay on the demo Mac.
2. Add every demo phone (Maya, Leo, Jordan, Priya) with `linq contacts add`, and have each one text scout once.
3. Make a group of the demo phones on iMessage, and have one member add scout's number.
4. To rehearse again in the same group, reset its trip: `cd bridge && bun run devchat reset --chat <chat ID>`. The chat ID is in the bridge's log lines.

Never commit the demo phones' real numbers.
