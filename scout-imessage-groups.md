# iMessage group chats through Linq and Photon

| | |
| --- | --- |
| **Question** | How does scout join iMessage group chats when we're on Photon's Pro plan, not Business, and can't get an Apple ID for scout? |
| **Decision** | scout's iMessage number is a Linq line, and members add it to their group like any person. The bridge plugs Linq into Photon's Spectrum SDK as a custom platform, so every group message still goes through Photon. This replaces the October 2 plan, which ran scout's own Apple ID on a Mac with BlueBubbles. |
| **Docs version** | spectrum-ts 12.10.1 and Linq Partner API v3, read October 3, 2026 |
| **Related** | [scout-PRD.md](scout-PRD.md): GC-1, GC-4, GC-6, DS-1 to DS-3, AL-4, and the messaging risks in the risks table |

## Summary

Photon Pro can't do iMessage group chats, and Business costs $250 per number per month. The earlier workaround needed an Apple ID created just for scout, and we can't get one. So:

- **In the group.** A [Linq](https://linqapp.com) line is a real iMessage phone number. Members add it to their group. Linq reports every message as a webhook and sends scout's replies by chat ID.
- **Through Photon.** The bridge registers Linq as a custom Spectrum platform (`definePlatform`), next to Photon's built-in providers. The hackathon requires Photon in the message path, and this keeps it there. It also gives the bridge one message loop for every line.
- **Native features.** Linq's API covers tapbacks, threaded replies, typing indicators, member changes, native polls, message effects and link cards. Each maps once onto Spectrum's content types, so scout's features don't depend on which line carries them.
- **Testing without phones.** A second custom platform, the developer console, plays a whole group in the terminal. Developers and AI agents script group conversations with it, and it shows link cards the way iMessage will.

The build plan and its checklist are in [scout-group-chat-plan.md](scout-group-chat-plan.md).

## Why Pro blocks groups

From Photon's [iMessage connection and routing](https://photon.codes/docs/spectrum-ts/providers/imessage/connection-and-routing.md) and [troubleshooting](https://photon.codes/docs/spectrum-ts/troubleshooting/imessage.md) docs:

- **Pro numbers are shared.** Each person is "routed through a number from a shared pool," and that number "may differ across recipients." Two friends in the same group could see scout on two different numbers, so a group can't be built around it.
- **Pro can't create groups or follow group changes.** Passing more than one person to `space.create()` throws an `UnsupportedError`. Pro also never receives group events such as members joining or leaving, or the group being renamed.
- **Pro only messages registered people.** Every recipient must be added as a user in the Photon dashboard first, or the send fails with "Target not allowed for this project." Pro allows 100 users.

| Plan | Price | Numbers | Groups |
| --- | --- | --- | --- |
| Free | $0 | Shared pool | Limited |
| Pro (ours) | $25/month | Shared pool | Limited |
| Business | $250 per number per month | One dedicated number | Full |

Apple has no join link and no API for joining a group. The only way in is for a member to add an iMessage account, so scout needs a real iMessage number of its own. Linq provides one without an Apple ID.

## Architecture

```
iMessage group (Maya, Leo, Priya + scout's Linq number)
        │ webhooks                   ▲ send, react, reply, typing
        ▼                            │
      Linq (Partner API v3)  ────────┘
        │ linq webhooks listen --forward-to relays events to this Mac
        ▼
      bridge/: one Spectrum app (Photon's SDK)
        │  providers: linq (custom) · devchat (custom, the developer console) · imessage (Photon line)
        │  HTTP: events in, actions out
        ▼
      src/scout/: conversation rules, Claude agent, SQLite
```

### 1. scout's number: a Linq line

- **One line per teammate.** Each developer runs `linq signup` and gets their own number and API key, so teammates never receive each other's webhooks.
- **Free line limits.** A free line takes up to 20 contacts, and each contact must text the line before it can message them. So every member texts scout's number privately once (after `linq contacts add`). scout ignores those private texts.
- **Groups.** Group chats take up to 31 handles and must be iMessage (or RCS), not SMS.
- **Rate limits.** 7,000 messages per line per day, and 30 per minute between scout and any one person. Going over returns HTTP 429.
- **Delivery.** Webhooks arrive at least once, so the bridge skips repeats by `event_id`. Deliveries are signed (Standard Webhooks headers).
- **No public URL.** In development, `linq webhooks listen --forward-to` relays events to the bridge on `127.0.0.1`. The bridge runs on a Mac because it converts iPhone photos to JPEG with macOS's `sips`.

### 2. Linq inside Photon: a custom Spectrum platform

spectrum-ts exports `definePlatform` from `spectrum-ts/authoring` ([Building a custom platform](https://photon.codes/docs/spectrum-ts/custom-platforms.md)). A platform supplies a config schema, `user.resolve`, `space.create`, a client, a `messages` generator for inbound messages, and one `send` function that handles every outbound content type. For webhook platforms, Spectrum's `fusor` turns each delivery into an inbound message. Custom platforms run in the same `Spectrum()` app as built-in ones and need no Photon cloud credentials.

| Linq | Spectrum |
| --- | --- |
| `message.received` (text and media parts) | Inbound message: text, attachment, or a group of both |
| `reaction.added`, `reaction.removed` | Inbound reaction |
| `participant.added`, `participant.removed` | Member events, if a custom platform can raise them (to test) |
| Send a message to a chat ID | `send` with text, or a reply to a message ID |
| React to a message | `send` with a reaction |
| Typing indicator | `send` with typing start and stop |
| A chat's handles | `space.getMembers()` |

Once Linq is a platform, `bridge/index.ts` goes back to one `for await (… of app.messages)` loop, and `IMESSAGE_MODE` only chooses which providers to register. Photon's cloud line stays available for one-on-one chats. Local mode stays in the code, but it needs an Apple ID signed into Messages on the Mac.

### 3. Bridge to scout: events in, actions out

Built. A list of strings couldn't carry tapback votes, threaded replies or anything else iMessage does, so the bridge sends scout events and gets back actions that refer to messages by the line's IDs:

```json
POST /messages   {"space_id": "c1", "sender_phone": "+15551234567", "text": "2", "message_id": "m42", "reply_to_text": null, ...}
POST /reactions  {"space_id": "c1", "sender_phone": "+15551234567", "tapback": "like", "message_id": "m40", "message_text": "2. San Juan, Puerto Rico (~$750/person est.): No passport needed", ...}

{"actions": [
  {"type": "react", "message_id": "m42", "tapback": "like", "fallback_text": "Got it, Leo → San Juan, Puerto Rico (1 of 3 voted)"},
  {"type": "say", "text": "Got it, Maya → San Juan, Puerto Rico (2 of 3 voted)", "reply_to": "m40"},
  {"type": "link", "url": "https://calendar.google.com/calendar/render?..."}
]}
```

- **Messages are found by their words.** A tapback arrives with the text of the message it's on, and a threaded reply with the text of what it answers. A poll option's text says which option it is, so nothing needs remembering between messages or restarts. The bridge finds the text among the messages it has seen, or asks the line through Spectrum's `getMessage` (Linq's API, or the console's transcript).
- **Every action has a plain-text fallback.** Spectrum resolves a send to nothing when a line can't do it, and the bridge then sends the text version.
- **Not built yet:** message effects, member joins and leaves, and typing. Each lands when a feature needs it.
- **Capabilities, later.** Once two lines in use support different actions (local mode has no reactions, for example), the bridge will tell scout which actions work so the agent only offers those. Linq and the developer console support the same actions, so this waits.
- **Link cards.** A `link` action sends one URL as a message of its own, which Linq requires. iMessage shows it as a card built from the page's Open Graph tags, and tapping it opens the page in Safari. iMessage never runs HTML or JavaScript in the chat, so anything interactive (a live poll board, the itinerary with a map, the album) lives on a page scout hosts. The card is a snapshot from when it was sent, so scout sends a new link to show new state.
- **The agent never writes this format.** scout's code builds the actions (`src/scout/outgoing.py`), and the bridge turns each into one Spectrum `send`.
- **Typing** has to start before scout's reply is ready, so it needs either a streamed response or a second call from the service. Decide this when building it.

### 4. Testing without phones: the developer console

The developer console is a second custom Spectrum platform (`devchat`) that plays a whole group in the terminal. Messages go through the same bridge, service and agent as a real group; only Linq is swapped out. Unlike `scout-simulate`, which calls the Python service directly, it tests the bridge too. It shows everything a group would see: text, photos, tapbacks, threaded replies, effects, polls and link cards.

#### Scripts

A script is a plain-text file that reads like the chat it plays. People and AI agents write it the same way. A sketch (syntax not final):

```
# The group votes, and scout announces the winner with a link card.
members maya leo priya
from poll-open

maya: 1
leo: 2
priya: 1
leo react like scout.last
maya reply scout.last: tulum!!

expect state destination = "Tulum, Mexico"
expect scout ~ "Tulum"
expect card title ~ "Tulum"
```

- **`name: text`** sends a message. `react`, `reply` and `photo` send a tapback, a threaded reply or a photo.
- **`from`** starts the chat at a seeded stage, such as `poll-open` or `destination-chosen`, so a script about voting doesn't replay preference collection through Claude.
- **Messages are named, never numbered.** A script points at `scout.last` or a label, because message IDs change between runs.
- **`expect` checks the trip and scout's replies.** Claude's wording changes between runs, so scripts check the trip's state, a word a reply must contain (`~`), or a link card's fields, never whole replies.
- **Two ways to run them.** `devchat run <script>` replays a script and prints the transcript. `bun run e2e` runs every script in `bridge/e2e/` against a throwaway service, as the E2E tests for the critical user journeys in `AGENTS.md`. It's separate from `bun test`, so the fast tests stay fast and free. Scripts call the real Claude API, so seeded stages also keep them short and cheap.
- **Built.** Messages, tapbacks, threaded replies, photos, link card previews, the seeded stages, and checks on replies, tapbacks, threads, cards and state. DEVELOPING.md lists every script line.

#### One command at a time, for agents

The same steps also run as separate shell commands, so an AI agent can explore without writing a script first. Each command waits until scout has finished replying, then prints the replies with their message IDs. A message is finished when the bridge asks the console for the next message, so commands never wait a fixed time.

```sh
devchat start maya leo priya --from poll-open
devchat say leo "2"
devchat react priya like scout.last
devchat state          # the trip: stage, members, preferences, poll and votes, expenses
devchat transcript
devchat reset          # clears this chat's trip, without deleting all of scout.db
```

`state`, `reset` and the seeded stages need a few dev-only endpoints on the Python service. `reset` also works on a real group's chat ID.

#### Link cards

When scout sends a link, the console builds the card the way Linq does: from `og:title`, `og:description` and `og:image`, then Twitter Card tags, then the page's `<title>` and first image. It prints the card's text, saves the card image as a file a person or agent can open, and warns about anything Linq would refuse or show badly:

- the URL isn't HTTPS, or is longer than 2,048 characters;
- the page doesn't load, or has no title or no image.

A link is always its own action, so it never shares its message. Here's the console's preview of the calendar link scout sends after a vote:

```
[m13] scout: 🔗 link card  https://calendar.google.com/calendar/render?action=TEMPLATE&...
       title        Google Calendar - Sign in to Access & Edit Your Schedule
       description  (none)
       image        bridge/.devchat/cards/devchat-78599650-m13.png
```

The preview caught a real problem: Google's page makes the card read like a login. A page of scout's own would fix it (see open questions).

Once scout serves its own pages, they can come from the local service in development, so cards and the pages behind them can be built and checked before any public hosting exists.

**Nothing ships that the console can't show.** Each new action lands together with how the console displays it and a script that uses it.

## Feature sources

| Feature | Source |
| --- | --- |
| Real iMessage group, blue bubbles | scout's Linq line |
| Who said what (GC-4) | The sender's handle on each Linq message |
| Quiet members (people who haven't texted) | The Linq chat's handles |
| Tapbacks in and out | Linq reactions, as Spectrum reactions |
| Threaded replies | Linq replies, as Spectrum replies |
| Typing indicator | Linq's typing indicator |
| Receipt photos (CS-7) | Linq media URLs, converted to JPEG by the bridge |
| Members joining or leaving (AL-4) | Linq participant events |
| Native group polls (DS-2) | Linq poll events (untested); numbered replies until then |
| Link cards for scout's pages (live poll board, itinerary, album) | Linq `link` parts, as Spectrum rich links; the pages are hosted by scout |
| Message effects (confetti for the winner) | Linq message effects |
| Pictures scout makes (an itinerary card, poll results) | Linq media uploads |
| Chat background, group name and photo | Linq (renaming and the group photo to confirm) |
| Private chats (GC-6) | Not decided: Photon's cloud line or the Linq line's private chats |

## Setup

1. Install the CLI and get a line: `npm i -g @linqapp/cli && linq signup`. It prints scout's number and an API key.
2. In `bridge/.env`, set `IMESSAGE_MODE=linq` and `LINQ_API_KEY`.
3. Add each tester with `linq contacts add`, and have each one text scout's number once.
4. Start the service (`uv run --env-file .env scout-server`), the bridge (`cd bridge && bun start`), and the relay (`linq webhooks listen --forward-to http://127.0.0.1:8788/linq-events`).
5. Keep the Mac awake (`caffeinate -dims`). A sleeping Mac stops relaying.

### Getting scout into a group

From an iPhone in the group, tap the group's name, then **Add Member**, and enter scout's number.

- Every member must be on iMessage (blue bubbles). SMS groups don't allow adding people.
- Apple may only allow adding people to a group that already has at least three other members. If the group is smaller, start a new group that includes scout.

## Build order

The milestones and their checklist are in [scout-group-chat-plan.md](scout-group-chat-plan.md). Today the bridge relays Linq group chats beside Spectrum, not inside it (`bridge/linq.ts`).

## Open questions to test

- **Free-line features.** Do reactions, threaded replies, typing, polls, effects and link cards work on Linq's free line, or only on paid lines? Can scout rename the group and set its photo?
- **Hosting scout's pages.** Link cards need a public HTTPS URL, but the bridge and service run on a Mac. Should that be a tunnel from the Mac, or a separate host? The calendar link's card reads "Google Calendar - Sign in to Access & Edit Your Schedule", so a page of scout's own would help the demo too.
- **Payload shapes.** What do `reaction.added` and `participant.added` look like, and does `message.received` say which message it replies to? Record real payloads as test fixtures.
- **Photo format.** Do iPhone photos arrive from Linq as HEIC, or already as JPEG?
- **Spectrum events.** Can a custom platform raise member joins and leaves, or only messages?
- **Private chats (GC-6).** Photon's cloud line, or the Linq line's private chats?

## Risks

| Risk | Mitigation |
| --- | --- |
| The free line's 20-contact cap and texted-first rule block a demo phone. | Add every demo phone and have it text scout days ahead. Each teammate has their own line, so their testers don't share one cap. |
| Apple flags scout's number for automated messaging. | Follow Photon's [deliverability guide](https://photon.codes/docs/best-practices/imessage-deliverability.md): people text scout first (the free line requires it anyway), no cold outreach, no bursts, and stay well under Linq's limits. |
| Linq, the CLI relay, or the Mac goes down during the demo. | Keep the Mac awake and plugged in, send a test text 30 minutes before, and keep the developer console, `scout-simulate` and the journey page ready as fallbacks. |
| A spectrum-ts update changes the custom platform API. | Upgrade spectrum-ts on purpose, never in the week of the demo, and keep the console's scripts as the check that nothing broke. |
| An Android member turns the group into SMS, which this setup can't handle. | Out of scope: we're targeting iMessage only. |

## Options considered

| Option | Why not chosen |
| --- | --- |
| scout's own Apple ID on a Mac, with BlueBubbles (the October 2 plan) | We can't get an Apple ID for scout. It also needed a dedicated Mac with System Integrity Protection partly turned off for BlueBubbles' Private API. |
| Linq on its own, outside Spectrum | It's how the bridge works today, but the hackathon needs Photon in the message path. It also means a second message loop, with every rich feature built twice. |
| Buy Photon Business | $250 per number per month. |
| Use a teammate's personal Apple ID | Its Messages database holds their private chats, and a ban would cost them their own iMessage. People who have them saved as a contact would see their name instead of "scout." |
| Fake a group with DMs from Pro | Loses the main selling point: adding scout to the group text you already have. |
| Move groups to Telegram | Telegram bots join groups natively and it's free, but friends would have to plan outside their existing group text. |
| WhatsApp Business | Photon's WhatsApp provider supports one-to-one chats only. |

## Sources

- [Photon pricing](https://photon.codes/pricing)
- [iMessage connection and routing](https://photon.codes/docs/spectrum-ts/providers/imessage/connection-and-routing.md)
- [iMessage troubleshooting](https://photon.codes/docs/spectrum-ts/troubleshooting/imessage.md)
- [iMessage deliverability](https://photon.codes/docs/best-practices/imessage-deliverability.md)
- [Building a custom platform](https://photon.codes/docs/spectrum-ts/custom-platforms.md)
- [Linq CLI](https://linqapp.com/cli)
- [Linq key concepts](https://docs.linqapp.com/channel/imessage/getting-started/key-concepts/)
- [Linq webhook events](https://docs.linqapp.com/api/resources/webhook_subscriptions/)
- [Linq iMessage capabilities](https://docs.linqapp.com/channel/imessage/index.md)
- [Linq rich link previews](https://docs.linqapp.com/guides/messaging/rich-link-previews/)
