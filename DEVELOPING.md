# Developing scout

How to run scout, test a change in a group chat, and set up the demo group. It's written for teammates and their coding agents (Claude Code, Codex) alike.

- [AGENTS.md](AGENTS.md): coding rules, and rules for agents working with real messages.
- [scout-imessage-groups.md](scout-imessage-groups.md): why group chats run on a Linq line inside Photon's Spectrum SDK, and the plan for the tools below.
- [scout-group-chat-plan.md](scout-group-chat-plan.md): the plan for these tools, with its checklist.
- [integration.md](integration.md): the card-driven trip flow — the eight stages, the four cards, and how a card comes back.
- [TODO.md](TODO.md): everything else the demo needs.

## What exists today

Several tools are planned but not built yet. **If a tool is marked planned, it doesn't exist: use the "Today" column, and don't create it unless that's your task.**

| Tool | Status | Today |
| --- | --- | --- |
| Python service and TypeScript bridge | Built | |
| Linq group chats (`IMESSAGE_MODE=linq`), as a Spectrum platform | Built | |
| Scripted chats with `scout-simulate` | Built | |
| Calling the service with `curl` | Built | |
| `bun run dev`: one command for everything | Built | |
| Event trace: one bridge log line per message | Built | |
| Developer console (`devchat`), scripts and `bun run e2e` | Built. Photos and voice notes convert only on a Mac, and a photo can't have a caption yet. | |
| Photos and voice notes: kept in `media/`, put into words by OpenAI, and photos viewable again by the AI (`view_photo`) | Built. Needs `OPENAI_API_KEY` to transcribe and a Mac to convert. Videos are dropped. | |
| Web search and page reading for the AI | Built. Anthropic or OpenAI runs the searches, so there's no extra key. Each reply gets at most 3 searches (and, on Claude, 2 page reads). | |
| Seeded stages and resetting one chat | Built | |
| Tapbacks, threaded replies and link cards, with console previews | Built, but only tested against a stand-in for Linq's API | |
| Message effects (confetti) | Planned (design doc, events in, actions out) | Plain text |
| HermesShare cards (brochure, activity deck, itinerary, booking) | The destination brochure (`send_destination_brochures`), the activity deck (`send_activity_deck`, an in-or-pass pick per activity whose Send button fills in an `@scout my picks: …` text that scout counts without the AI), the itinerary card (`post_itinerary`, a timeline of each day's start time with optional add-ons, needs `GOOGLE_PLACES_API_KEY` for its photo) and the flight card (`send_best_flights`, live Google Flights fares through SerpApi, needs `SERPAPI_API_KEY`) are built, but only tested against stand-ins for Linq's API, Google Places and SerpApi. Their photos are Google's own links, so they need no hosting. Taps don't reach scout, so the deck and the trip interview come back as text the card fills in. The rest are planned ([integration.md](integration.md)). | The numbered text poll for voting, the deck as a numbered list people answer with `@scout my picks: 1, 3`, the plan as text without a Places key, and flight search links without a SerpApi key |
| Card previews in the console | Built: the caption, thumbnail, the text phones without the extension get, and why Linq would refuse it | |
| Expenses: logging costs split among everyone or only some people, itemized receipts with tax and tip shared by what each person had, and an end-of-trip report (`post_expense_report`) | Built. The report is HermesShare cards (a summary, then as many ledger cards as the expenses need) when there's a destination photo, so it has the same hosting and thumbnail limits as the other cards, and text otherwise. Only tested against stand-ins for Linq's API and Google Places, and not yet played through the console with real Claude. | The report as text |
| Demo group commands (`bun run demo`) | Built, but only tested against a stand-in for Linq's API | |

When a pull request ships one of these, it updates this table and the instructions below.

## How a message flows

```
iPhone in the group
  → Linq (scout's number)
  → linq webhooks listen, which relays to the bridge at 127.0.0.1:8788/linq-events
  → bridge/linq.ts, a Spectrum platform, so the message goes through Photon's SDK
  → bridge/spectrum.ts, the one relay loop, which posts to the service:
      a message to 127.0.0.1:8787/messages, a tapback to /reactions
  → src/scout/conversation.py decides what to do
  ← actions (src/scout/outgoing.py): say (maybe threaded), react, link, or card
  ← the relay performs each one through Spectrum and Linq
```

- **One message at a time.** The bridge waits for scout's actions before reading the next message, so two votes can't race.
- **scout types before it texts.** Before each text, link or card, the relay shows the typing bubble and waits about as long as the text would take to type (0.8 to 5 seconds, `typingPauseFor` in `spectrum.ts`). Linq can't show the bubble in group chats, so there scout only pauses. The developer console and the tests skip the wait.
- **Actions fall back to text.** If a line can't send a tapback, a threaded reply or a link card, or the bridge can't find the message it targets, the plain-text version goes instead.
- **The bridge drops** private chats (in Linq mode), scout's own messages, messages with nothing to read (stickers, videos) and repeat deliveries.
- **Photos and voice notes become words.** The bridge sends the file as it arrived. The service keeps it in `media/<chat>/` (`SCOUT_MEDIA_DIR`), makes a copy the AI can read (a JPEG through macOS's `sips`, or m4a audio through `afconvert`), and asks OpenAI for a photo's description or a voice note's words (`media.py`, `openai_transcriber.py`). The chat log holds `[photo <id> (<file>): description]` or `[voice note <id> (<file>): "words"]`, so later turns cost no image or audio. The AI only sees a photo's description, including the newest one; it looks at the photo itself with `view_photo` when the description isn't enough. Receipts and screenshots are described in full, every line and number. It never hears audio, only reads the words. Every photo and voice note is transcribed when it arrives, tagged or not, so each costs an OpenAI call.
- **The log reads like the chat.** `bun run dev` shows each message as it arrives (time, the chat's first 8 characters, the sender's last 4 digits, their words), then the service's decision in plain words (`Not tagged, and the gate says to stay quiet`, a counted vote, or the AI's tool calls and timing), then what scout sent and how long it took, `· no reply`, `· skipped:` with the reason, or `✗` with the error. Request lines, scout's own sends, delivery and read receipts, and the relay's setup details (including its signing secret) are hidden.
- **The service decides whether to speak** (`conversation.py`). A plain vote ("2"), a 👍 or ❤️ on a poll option, and a pick of a nearby place are handled in code. A message that tags `@scout`, replies in a thread to one of scout's texts, or is a voice note that says scout's name to it ("hey scout", "at scout", opening with "Scout,") goes straight to the AI. Every other message first goes past the speak gate (`speak_gate.py`, prompt in `speak_gate_prompt.md`): one call to a small model (Claude Haiku, or `gpt-5.4-mini` when only an OpenAI key is set) that sees the latest 12 messages and answers SPEAK or SILENT. It leans hard toward SILENT, and when it can't be reached scout stays quiet. Only on SPEAK does the AI run, and it can still choose `NO_REPLY`. The AI reads the whole chat to catch up: it introduces itself the first time, and saves the trip details and votes in it, including ones a friend gave for someone else. If that AI call fails on a tagged message, scout says it hit a snag. Each untagged text, photo and voice note therefore costs one small gate call, and messages that need a reply cost the full AI call as well.
- **Votes stay quiet.** A vote by number gets a 👍 tapback, and a tapback vote gets a reply threaded under the option, instead of a new line in the chat.
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
bun run devchat react priya like "2. San Juan"          # a tapback on scout's message with those words
bun run devchat reply maya "2. San Juan" this one!      # a reply threaded under it
bun run devchat photo leo receipt.jpg                   # Mac only
bun run devchat voice maya memo.caf                     # a voice note, Mac only
bun run devchat transcript
bun run devchat state                                   # the trip, as JSON
bun run devchat reset                                   # clears this chat's trip, transcript and media files
```

- Each command waits until scout has finished, then prints the message and scout's replies with their IDs (`[m3] scout: ...`). A tapback shows as `👍 on m3`, and a threaded message as `scout ↪ m3: ...`. If scout didn't reply, it prints `(scout stayed quiet)` or why the bridge skipped the message.
- `react` and `reply` take a target: a message ID (`m3`), `scout.last`, or quoted words, which pick scout's latest message containing them. Quote an option the way it reads ("2. San Juan"), because scout's confirmations mention the same names.
- When scout sends a link, the console prints the card iMessage would show: its title, description, the path of its saved picture (open it to see the card's image), and warnings about anything Linq would refuse or show badly.
- `start` without `--from` begins before the introduction. `--from poll-open` begins with everyone's preferences shared and the destination poll open. `--from destination-chosen` begins with San Juan picked for March 14–20, 2027. A seeded chat starts with the messages scout "already sent", such as the poll, so members can tap them.
- Members get the same numbers as in `scout-simulate`: +15550000001, +15550000002 and so on.
- The console's chat is saved in `bridge/.devchat/`, so each command picks up where the last one left off.
- `state --chat <id>` and `reset --chat <id>` work on any chat, including a real group's. Its chat ID is in the bridge's log lines.
- A photo can't have a caption yet. Send the caption as its own message.

### Script a conversation

A script is a plain-text file that reads like the chat. `bun run devchat run <file>` plays it in a new chat, prints the conversation, and stops at the first failure with its line number:

```
# Votes by number and by tapback close the poll and announce the winner.
members maya leo priya
from poll-open

maya: 2
expect scout reacted like
leo react love "2. San Juan"
expect thread ~ "2 of 3 voted"
leo: lol this is taking forever
expect scout quiet
priya: 1
expect scout ~ "San Juan, Puerto Rico wins"
expect card url ~ "calendar.google.com"
expect state destination = "San Juan, Puerto Rico"
```

| Line | Means |
| --- | --- |
| `members maya leo priya` | Who's in the chat. Required, before any message. |
| `from poll-open` | Start at a seeded stage: `poll-open` or `destination-chosen`. Optional. |
| `maya: text` | Maya sends a message. |
| `maya react like "2. San Juan"` | Maya adds a tapback (love, like, dislike, laugh, emphasize or question) to scout's latest message containing the words, or to `scout.last`. |
| `maya reply "2. San Juan": text` | Maya replies in a thread under that message. |
| `maya photo receipt.jpg` | Maya sends a photo. The path is relative to the script (Mac only). |
| `maya voice memo.caf` | Maya sends a voice note. The path is relative to the script (Mac only). |
| `expect scout ~ "words"` | A reply to the latest message contains the words, ignoring case. |
| `expect scout !~ "words"` | No reply to the latest message contains the words, ignoring case. Staying quiet passes. |
| `expect scout quiet` | scout didn't reply to the latest message. |
| `expect scout reacted like` | scout added that tapback in reply to the latest message. |
| `expect thread ~ "words"` | scout replied in a thread, with the words. |
| `expect card title ~ "words"` | scout sent a link card whose title (or `description`, or `url`) contains the words. |
| `expect card no warnings` | Linq would show scout's link card as it is. |
| `expect state path = value` | The trip's value at a dotted path, such as `members.0.budget_usd`, equals a value: `"text"`, a number, `true`, `false` or `null`. `bun run devchat state` shows the paths. |
| `expect state path ~ "words"` | The trip's value at that path contains the words, ignoring case. |

Lines starting with `#` are comments. Check the trip's state, or a word a reply must contain, never whole replies.

### Run the end-to-end tests

`bridge/e2e/` holds a script for each critical user journey in AGENTS.md. `cd bridge && bun run e2e` starts a throwaway service on a free port, plays every script, and stops the service. `bun run e2e votes-and-winner.chat` runs one script. The service's log and database stay in `bridge/.devchat/e2e/` so you can look into failures.

Most journeys go through the AI. Without `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, only the vote passes. `shares-preferences-by-voice-note.chat` also needs `OPENAI_API_KEY` to transcribe, and a Mac.

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
# {"actions": [{"type": "say", "text": "hey all, i'm scout ...", ...}]}
```

- `participant_phones` is everyone in the group, including people who haven't texted yet.
- To send a photo or voice note, add `"attachment": {"media_type": "image/heic", "base64_data": "..."}` with the file as it was sent (`image/...` or `audio/...`, like `audio/x-caf`). `text` can be empty.
- `GET /dev/trips/<space_id>` shows the trip, and `DELETE /dev/trips/<space_id>` resets it, deleting its photos and voice notes from disk too.
- To start over, use a new `space_id`, or stop the service and delete `/tmp/scout-test.db`.

## Run scout in a real group

This needs a Mac (the service converts iPhone photos and voice memos with macOS's `sips` and `afconvert`) and your own Linq line.

1. Get a line once: `npm i -g @linqapp/cli && linq signup`. `linq whoami` shows scout's number.
2. In `bridge/.env`, set `IMESSAGE_MODE=linq` and `LINQ_API_KEY` (copy `bridge/.env.example`).
3. Start everything with `cd bridge && bun run dev`. It checks your settings, the Linq login and free ports first, then runs the service, the bridge and the Linq relay in one terminal with labeled logs. Ctrl-C stops them all.
4. Add each tester with `linq contacts add` (the free line allows up to 20). Each tester texts scout's number privately once, because the free line only answers people who texted it first. scout ignores those private texts.
5. From an iPhone in the group, tap the group's name, then **Add Member**, and enter scout's number. Everyone must be on iMessage, and Apple may require at least three other members.

### When scout doesn't reply

1. **Find the message in the log** (`[bridge]` in `bun run dev`). `skipped` says why: a private chat, scout's own message, nothing to read, or a repeat delivery. `✗` shows the error from Linq's API or the service. `· no reply` means the service chose not to reply, and the `[service]` line above it says why (step 3).
2. **No line at all?** The message never reached the bridge. Is the relay running (`[relay]` in `bun run dev`)? Did the sender text scout privately first? The free line ignores anyone who hasn't.
3. **Was scout tagged, or did the gate say SPEAK?** A tag (`@scout`, a threaded reply to scout, or a voice note that addresses scout: "hey scout", "at scout") always reaches the AI. Anything else goes to the gate first, and the `[service]` line says `Not tagged, and the gate says to stay quiet` when it said SILENT. If scout is too quiet or too chatty, change `speak_gate_prompt.md`; once the AI is running, its own `NO_REPLY` rules are in `system_prompt.md` ("When to speak").
4. **Did the database layout change?** There are no migrations. Delete `scout.db`, and every group gets the introduction again.

## Add a group chat feature

| The feature needs | Where the code goes |
| --- | --- |
| A rule handled in code, like counting a vote | `conversation.py` (and a module like `polls.py`), tested in `tests/test_conversation.py` |
| Something Claude decides to do | A tool in `agent_tools.py`, the change in `trip_actions.py`, guidance in `system_prompt.md` |
| A new kind of incoming message, like a photo | The platforms' parsing (`bridge/linq.ts`, `bridge/devchat/platform.ts`), the relay (`bridge/spectrum.ts`), the request types in both `bridge/scout.ts` and `src/scout/app.py` (keep them identical), and `IncomingMessage` in `trip.py` |
| scout sending something new, like a message effect | An action type in `src/scout/outgoing.py` and `bridge/scout.ts`, a case in `perform` in `bridge/spectrum.ts` with a plain-text fallback, how Linq sends it (`bridge/linq.ts`), how the console shows it (`bridge/devchat/platform.ts`), and a script check |
| A test that starts later in the journey | A seeded stage in `src/scout/trip_seeds.py`, then `from <stage>` in a console script |

When a feature changes a critical user journey, update or add its script in `bridge/e2e/`.

Every action lands with the same parts: its type on both sides, a case in the relay with a plain-text fallback, how Linq and the console handle it, and a script that uses it. Only add one when a feature needs it.

### Link cards

iMessage never runs HTML or JavaScript in the chat. A link card is a preview of a page, and anything web-shaped lives on that page. Interactive content in the bubble itself is a HermesShare card instead, which is declarative JSON rather than code ([integration.md](integration.md)) — planned, not built. Linq's rules for link cards:

- The link must be the only thing in its message.
- The URL must be HTTPS, and at most 2,048 characters.
- The card is built from the page's `og:title`, `og:description` and `og:image`, then Twitter Card tags, then the page's `<title>` and first image.
- The card is a snapshot from when it was sent. To show new state, send a new link.

scout sends a link as its own action (`Link` in `outgoing.py`), so it's always alone in its message. The console previews every card scout sends, and its preview of the calendar link shows a real problem: Google's page titles the card "Google Calendar - Sign in to Access & Edit Your Schedule". A page scout hosts would fix that, but where scout's pages will be hosted isn't decided yet (TODO, Decide).

## Set up the demo group

The demo runs on one teammate's Linq line, from the demo Mac. `bun run demo` gets the demo phones (Maya, Leo, Jordan, Priya) ready and makes rehearsal groups. **These commands send real iMessages to the phones on the roster**, so only run them on the demo line, when you mean to.

1. Put each demo phone's persona and number in `bridge/demo/roster.json` (copy `bridge/demo/roster.example.json`). It's git-ignored: never commit the real numbers. It needs at least 3 phones besides scout, all on iMessage.
2. Set `LINQ_API_KEY` in `bridge/.env` to the demo line's key, and log the Linq CLI into the same line.
3. From `bridge/`, run `bun run demo setup`. It adds every phone as a contact (on a shared line, which only answers its contacts), creates scout's contact card if the line has none, and prints scout's number with who has texted it so far. Each phone that has texted gets a hi from scout and scout's contact card, so the phone can save "scout" instead of showing a number.
4. From each phone marked ✗, text scout's number once, then run `bun run demo setup` again until every phone has a ✓. It's safe to rerun: scout says hi to each phone once, and sends the card again each run (Linq suggests at most once a day, since nobody can tell whether a phone saved it).
5. Start everything with `bun run dev`.

Then rehearse:

- `bun run demo group` makes a fresh group of every phone plus scout, named "Rehearsal 1", "Rehearsal 2" and so on. Any member texts the group to get scout's introduction.
- `bun run demo reset` clears the trip of the newest group of demo phones on scout's line, whether the group command made it or a member did, so the journey can run again in the same group. It needs the scout service running. To reset another chat, use `bun run devchat reset --chat <chat ID>`.

On stage, a member makes the group of demo phones and adds scout's number by hand, because that's the moment the demo shows. Don't use the group command for it.

- A new contact card is named "scout" with no photo. Add the photo in Linq's dashboard (Contact cards). Linq takes a moment to apply a new card, so `setup` sends it on the next run.
- `group` stops if a phone hasn't texted scout yet, since Linq won't let scout add it. It also stops if Linq sends to an existing unnamed group of the same phones instead of making a new one. Name that group in Messages, then run it again.
