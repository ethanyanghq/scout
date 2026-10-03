# Plan: scout's group chat connector and developer tools

| | |
| --- | --- |
| **Goal** | scout lives in real iMessage group chats through a Linq line running inside Photon's Spectrum SDK. Teammates and their AI agents build and test group chat features, including tapbacks, threaded replies and link cards, without phones, and the demo group can be set up in minutes. |
| **Status** | Milestone 1 is built, apart from running the two Claude scripts against the real API. Milestones 2 and 3 aren't started. Last updated October 3, 2026. |
| **Design** | [scout-imessage-groups.md](scout-imessage-groups.md): why Linq, how it plugs into Spectrum, the developer console |
| **How to use it** | [DEVELOPING.md](DEVELOPING.md): what exists today, and how to test without phones |
| **Rest of the demo** | [TODO.md](TODO.md) |

Check items off in the pull request that finishes them. When a pull request ships a tool, it also updates DEVELOPING.md's "What exists today" table.

## Decisions

- **Groups run on a Linq line.** Photon's Pro plan can't join groups, Business costs $250 per number per month, and scout can't get an Apple ID. A Linq line is a real iMessage number that members add to their group.
- **Linq runs inside Photon.** The hackathon requires Photon in the message path, which we read as Photon's Spectrum SDK carrying the messages. Linq becomes a custom Spectrum platform (`definePlatform`), so the bridge has one message loop for every line.
- **Each teammate develops on their own Linq line**, so nobody receives anyone else's webhooks.
- **The bridge runs on a Mac only.** It converts iPhone photos with macOS's `sips`.
- **The developer console is a second custom Spectrum platform.** A fake group goes through the real bridge and service. People and AI agents script it, agents run it one shell command at a time, and it previews link cards the way iMessage will show them.
- **Scripts read like the chat.** They check the trip's state, words a reply must contain and link card fields, never whole replies, because Claude's wording changes between runs.
- **iMessage never runs HTML or JavaScript.** Anything interactive is a page scout hosts, sent as a link card.
- **We're not building an SDK.** Each iMessage action gets added only when a feature needs it, in four parts: a case in the bridge, an action type and agent tool in Python, how the console shows it, and a script that uses it. No packaging, versioning or docs for outsiders. The capability report waits until two lines in use support different actions.

## Checklist

### 0. Docs

- [x] Rewrite the design doc for Linq inside Photon ([scout-imessage-groups.md](scout-imessage-groups.md)).
- [x] Update the PRD, README and TODO so nothing plans around an Apple ID or BlueBubbles.
- [x] Write [DEVELOPING.md](DEVELOPING.md) for teammates and their agents. Add rules for real messages to AGENTS.md, and a CLAUDE.md that imports AGENTS.md so Claude Code follows the same rules.
- [x] Commit the docs.

### 1. Developer tools

Shipped when a teammate can start everything with one command and script a group conversation that runs through the real bridge, and an AI agent can do the same from a shell. Design: [scout-imessage-groups.md](scout-imessage-groups.md), section 4.

- [x] `bun run dev`: checks the `.env` files, the keys the chosen mode needs, the Linq login (`linq whoami`) and free ports, then starts the service, the bridge and the Linq relay with labeled logs. Ctrl-C stops all three.
- [x] Event trace: the bridge logs one line per event, either handled (with how long scout took) or skipped and why (private chat, scout's own message, a sticker, a repeat delivery).
- [x] Dev-only service endpoints: start a chat at a seeded stage (`poll-open`, `destination-chosen`), read a chat's trip, and reset one chat's trip.
- [x] The developer console (`devchat`): a fake group, as a Spectrum platform, that goes through the real bridge and service.
- [x] Console commands an agent can run from a shell: `start`, `say`, `photo`, `state`, `transcript` and `reset`. Each waits until scout has finished replying, then prints the replies with their message IDs.
- [x] Console scripts: `devchat run <script>` replays one, and `bun run e2e` runs every script in `bridge/e2e/`. It's separate from `bun test`, so the fast tests stay fast and free.
- [x] A script for each critical user journey in `AGENTS.md`, and AGENTS.md's "E2E tests" line pointing at them.
- [ ] Run `bun run e2e` with a real `ANTHROPIC_API_KEY`, and adjust the two scripts that need Claude (`shares-preferences.chat`, `posts-summary-and-poll.chat`) until they pass reliably. The other two pass without Claude.
- [ ] Photos with a caption in the console. Spectrum delivers them as a group of messages, which the console can't build yet.
- [x] DEVELOPING.md covers `bun run dev`, the console and scripts, and its "What exists today" table marks them built.

### 2. Group chat connector: Linq inside Photon

Shipped when a real iMessage group runs the whole journey through Photon's Spectrum SDK with no Linq-only code path left, and scout can send and receive more than text. Design: [scout-imessage-groups.md](scout-imessage-groups.md), sections 2 and 3.

The console plugs into the bridge's existing Spectrum loop, so milestone 1 doesn't wait for this one, and its scripts then check that the switch broke nothing.

- [ ] Record real Linq webhooks as test fixtures: a group text, a photo with a caption, a tapback, a threaded reply, and someone joining. Swap every real phone number for a 555 number before committing.
- [ ] Linq as a Spectrum platform (`definePlatform("linq")`): group messages and photos in, text out by chat ID, and the group's members. Tested against the fixtures.
- [ ] One message loop in `bridge/index.ts` for every provider, with `IMESSAGE_MODE` choosing the providers. Today's behavior stays: private chats ignored, repeat deliveries skipped, one message at a time, and one failed message never stops the bridge.
- [ ] The console scripts from milestone 1 still pass after the switch.
- [ ] Find out what Linq's free line supports (tapbacks, threaded replies, typing, effects, link cards, polls, renaming the group) and record the answers in the design doc's open questions.
- [ ] Events in, actions out: scout receives tapbacks and threaded replies, and sends tapbacks and threaded replies. Each lands with its console display (`devchat react`, `devchat reply`) and a script.
- [ ] Link cards: scout can send one, and the console previews it. The preview builds the card from the page's Open Graph tags, saves the card image to a file, and warns about anything Linq would refuse (a link sharing its message, a non-HTTPS or over-long URL, no title or image). Add a script that checks a card.
- [ ] Run the real-group journey (TODO, First real run) again on the new connector.

### 3. Demo group

Shipped when the demo phones can be set up for scout in a few minutes, a rehearsal group can be made and reset with one command each, and the on-stage "add scout" moment has been rehearsed. This milestone doesn't depend on 1 or 2.

- [ ] Check on the demo line that Linq's API can create a group chat and send a contact card. The commands below depend on both.
- [ ] A demo roster: each demo phone's persona and number (Maya, Leo, Jordan, Priya; at least 3 phones besides scout, all on iMessage) in a git-ignored file. Real numbers are never committed.
- [ ] A setup command (name not final): adds every roster phone as a contact on the demo line, prints scout's number for each phone to text once, and shows who has texted so far. It also sends scout's contact card in that private chat, so phones can save "scout" with its photo instead of showing a number.
- [ ] A group command: for rehearsals, creates a fresh group of every roster phone plus scout through Linq, so nobody builds groups by hand.
- [ ] A reset command: clears the demo group's trip, so the journey can rerun in the same group without deleting `scout.db`.
- [ ] Rehearse the on-stage moment: a member adds scout's number to a group of the demo phones, and scout introduces itself. On stage this is done by hand, not with the group command, because it's the moment the demo shows.
- [ ] DEVELOPING.md's "Set up the demo group" section uses the new commands.

## Still open

- **Free-line features, payload shapes and photo format.** These get answered by milestone 2's first items. The full list is in the design doc's open questions.
- **Where scout's web pages are hosted.** Link cards need a public HTTPS URL, and so would the album. This is tracked in TODO's Decide section.
- **Private chats (GC-6).** Photon's cloud line, or the Linq line's private chats.

## Later, not in this plan

- Native iMessage polls through Linq, if poll events work on our line.
- Building scout's web pages, once hosting is decided.
- Publishing the Linq provider or the console for other Spectrum developers. Decide after the demo.
