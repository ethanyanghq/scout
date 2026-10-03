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
| `bun run dev`: one command for everything | Planned (plan, milestone 1) | Three terminals ([Run scout in a real group](#run-scout-in-a-real-group)) |
| Event trace: why the bridge skipped a message | Planned (plan, milestone 1) | [When scout doesn't reply](#when-scout-doesnt-reply) |
| Developer console (`devchat`), scripts and `e2e/` tests | Planned (plan, milestone 1) | `scout-simulate` with piped input |
| Seeded stages and resetting one chat | Planned (plan, milestone 1) | Start over with a new chat ID or a fresh database |
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
- **The service decides whether to speak** (`conversation.py`). The first message in a chat gets the introduction. A plain vote ("2") or a pick of a nearby place is handled in code. Tagged messages, and untagged ones at certain stages, go to Claude. Everything else gets no reply.
- **Each chat is one trip**, saved in `scout.db` under the chat's ID (`space_id`).

## Test a change without phones

| You changed | Check it with |
| --- | --- |
| Rules, parsing or math (`polls.py`, `settle_up.py`, `group_summary.py`, …) | `uv run pytest` |
| What scout does with a message (`conversation.py`) | `uv run pytest tests/test_conversation.py`, which fakes Claude |
| What Claude says or does (`system_prompt.md`, `agent_tools.py`, `trip_actions.py`) | A scripted chat with `scout-simulate` |
| The HTTP endpoint (`app.py`) | `curl` |
| The bridge (`bridge/*.ts`) | `cd bridge && bun test && bun run typecheck`, then a real group |

The last two ways below use the real Claude API, so they need `ANTHROPIC_API_KEY` in `.env`. Each message that reaches Claude takes about 10 seconds and costs tokens, so keep scripted chats short. Claude's wording changes from run to run, so check what happened to the trip, not the exact text.

### Script a chat with scout-simulate

Pipe in one message per line, as `name: message`. The run stops at the end of the input, so an agent can run it from a shell:

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
- Every run starts with an empty, throwaway database. To test the vote, the script has to collect everyone's preferences first.
- Leave out the `<<'EOF'` block to type the chat yourself.

### Call the service with curl

Use this when you need a chat to last across several commands. Start the service with its own database so your `scout.db` stays clean:

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
- To start over, use a new `space_id`, or stop the service and delete `/tmp/scout-test.db`.

## Run scout in a real group

This needs a Mac (the bridge converts iPhone photos with macOS's `sips`) and your own Linq line.

1. Get a line once: `npm i -g @linqapp/cli && linq signup`. `linq whoami` shows scout's number.
2. In `bridge/.env`, set `IMESSAGE_MODE=linq` and `LINQ_API_KEY` (copy `bridge/.env.example`).
3. Start three terminals:
   ```sh
   uv run --env-file .env scout-server
   cd bridge && bun start
   linq webhooks listen --forward-to http://127.0.0.1:8788/linq-events
   ```
4. Add each tester with `linq contacts add` (the free line allows up to 20). Each tester texts scout's number privately once, because the free line only answers people who texted it first. scout ignores those private texts.
5. From an iPhone in the group, tap the group's name, then **Add Member**, and enter scout's number. Everyone must be on iMessage, and Apple may require at least three other members.

### When scout doesn't reply

1. **Was it a private chat?** In Linq mode, scout only answers group chats.
2. **Is the relay running?** `linq webhooks listen` must forward to `http://127.0.0.1:8788/linq-events`. The bridge prints that address when it starts.
3. **Did the sender text scout privately first?** The free line ignores anyone who hasn't.
4. **Did the bridge log an error?** Look for `Couldn't handle Linq event` in the bridge's terminal. It means Linq's API or the service returned an error.
5. **Did scout choose to stay quiet?** The service log shows each request. An untagged message only reaches Claude while preferences are being collected, or after a destination is chosen if it mentions money or has a photo (`_needs_agent_untagged` in `conversation.py`).
6. **Did the database layout change?** There are no migrations. Delete `scout.db`, and every group gets the introduction again.

## Add a group chat feature

| The feature needs | Where the code goes |
| --- | --- |
| A rule handled in code, like counting a vote | `conversation.py` (and a module like `polls.py`), tested in `tests/test_conversation.py` |
| Something Claude decides to do | A tool in `agent_tools.py`, the change in `trip_actions.py`, guidance in `system_prompt.md` |
| A new kind of incoming message, like a photo | The bridge's parsing (`bridge/index.ts` for Spectrum, `bridge/linq.ts` for Linq), `IncomingText` in both `bridge/scout.ts` and `src/scout/app.py` (keep them identical), and `IncomingMessage` in `trip.py` |
| scout sending more than text (tapbacks, threaded replies, effects, link cards) | Not possible yet: the service only returns texts. See "Events in, actions out" in the design doc. |

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
4. To rehearse again, start a new group, or delete `scout.db`.

Never commit the demo phones' real numbers.
