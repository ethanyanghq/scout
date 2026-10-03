# iMessage group chats without Photon Business

| | |
| --- | --- |
| **Question** | How does scout work in iMessage group chats when we're on Photon's Pro plan, not Business? |
| **Decision** | A bridge program on a Mac signs into an Apple ID created just for scout, joins groups as that account and relays them to scout's agent on Photon Pro. The agent controls the group through commands the bridge carries out. |
| **Docs version** | Photon Stable docs, read October 2, 2026 |
| **Related** | [scout-PRD.md](scout-PRD.md): GC-1, GC-4, GC-6, DS-1 to DS-3, AL-4, and the messaging risks in the risks table |

## Summary

Photon Pro can't do iMessage group chats. Business can, at $250 per number per month. We get groups anyway by giving scout a real iMessage account on a Mac we control:

- **In the group.** scout has its own Apple ID, and members add it to their group like any person. BlueBubbles Server, running on that Mac, gives the bridge nearly every native iMessage feature: tapbacks, typing indicators, threaded replies and more.
- **Bridge to agent.** The bridge passes group messages to scout's agent on Photon Pro and carries out the commands the agent sends back.
- **Private chats.** Scout's private DMs with members go straight through Photon Pro's iMessage line, which fully supports one-to-one chats, native polls included.

The demo needs build steps 1–3. Steps 4–5 add features.

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

A program can't join an iMessage group by itself either: Apple has no join link and no API for it. The only way in is for a member to add an iMessage account. So scout needs a real iMessage account, signed in on a device we control.

## Architecture

```
iMessage group (A, B, C) ◀──────▶ scout's account on a dedicated Mac
                                     │  BlueBubbles + Private API: native features in the group
                                     │  imessage-kit: backup if the Private API breaks
                                     ▼
                                   Bridge: groups only, group tags, message IDs,
                                     │     events, runs or mimics each command
                                     │  JSON commands and events
                                     ▼
                                   Photon Pro (Telegram link) ──▶ scout agent (each command is an AI tool)
                                                                       │
                     Members' private DMs ◀── Photon Pro iMessage line ┘ (native polls, tapbacks, typing)
```

### 1. Identity: a dedicated Apple ID named "scout"

- We create a new Apple ID only for scout. Its Messages database holds no one's private chats. If Apple flags it, nobody loses their own iMessage.
- Creating the account needs a trusted phone number for two-factor authentication. A teammate's number works. It only receives sign-in codes and never becomes scout's iMessage address.
- On a Mac, iMessage uses the Apple ID's email address. Only an iPhone with a SIM can register a phone number to the account. The email address is enough, because members can add an email address to a group. If we want a number later, a prepaid SIM in a spare iPhone can register one.
- The account runs in its own macOS user on an always-on Mac, because Messages allows only one iMessage account per macOS user.
- Turn on **Messages → Settings → Share Name and Photo** with the name "scout" and an icon.
- Members add scout to their group by the account's email address.

### 2. Native group features: BlueBubbles with the Private API

[BlueBubbles Server](https://bluebubbles.app) (open source, Apache-2.0) has an optional Private API mode. It loads a helper inside the Messages app and calls the same internal functions the app uses when someone taps a button. That unlocks what Apple's public scripting can't do:

- tapbacks, typing indicators, threaded replies
- edit, unsend, message effects, read receipts
- renaming the group, changing its photo, adding and removing members, creating groups

**Backup:** keep Photon's [`imessage-kit`](https://github.com/photon-hq/imessage-kit) (MIT) installed. It reads the Messages database and sends through AppleScript, so it handles text, photos and links with no Private API. If a macOS update breaks the Private API helper, the bridge drops to `imessage-kit` without going offline.

### 3. The bridge

The bridge runs in scout's macOS user and is the core of the system.

- **Groups only.** Private chats go through the Photon Pro line (see [Private DMs](#6-private-dms-gc-6-the-photon-pro-imessage-line)), so the bridge ignores direct messages to scout's account. The account belongs to scout alone, so every group it's in is one somebody added it to, and the bridge forwards all of them without an allow list.
- **Routing.** It tags each group with a short ID, gives every message an ID, and ignores scout's own outgoing messages so it never loops.
- **Events.** It passes reactions, people joining or leaving, and photos up to the agent, not only text.
- **Commands.** It carries out each agent command natively where it can and mimics it where it can't (see [Commands](#commands)).
- **Capability report.** At startup it tells the agent which commands work right now. If the Private API breaks, the agent stops asking for native features without any change to its code.

### 4. Bridge to agent: Photon Pro over Telegram

The bridge talks to scout's agent through Photon Pro's Telegram provider rather than by iMessage DM. Every group message would otherwise create a second iMessage from scout's account. That doubles the bot-like traffic Apple filters for, on a new account with no history to vouch for it. Telegram also carries JSON without the risk of iMessage turning links into preview cards.

A Telegram bot can't message another bot, so the bridge uses a Telegram *user* account (through a library such as [gramjs](https://gram.js.org)) to message scout's Photon bot.

### 5. The agent

Each command is an AI tool: `say`, `poll`, `react`, `reply_to`, `send_photo` and so on. When the agent calls one, the call becomes a single JSON command. The model never writes command syntax by hand, so it can't produce a malformed command.

### 6. Private DMs (GC-6): the Photon Pro iMessage line

Pro fully supports one-to-one iMessage, including native polls, tapbacks, typing indicators and contact cards, which is more than anything inside the group.

- **Registration.** Pro only messages registered users. Photon's CLI has `photon spectrum users add`, so the bridge could register members automatically as they appear in groups.
- **Capacity.** The 100-user cap covers about 20 groups of five.
- **Trade-off.** Private chats come from a Photon number, not the email address scout uses in groups. Scout explains this once ("for private stuff, text me here") and sends its contact card.

## Feature sources

| Feature | Source |
| --- | --- |
| Real iMessage group, blue bubbles | scout's Apple ID on the Mac |
| Tapbacks, typing, threaded replies, edit/unsend, effects | BlueBubbles Private API |
| Rename, group photo, add/remove members | BlueBubbles Private API |
| Group polls (DS-1 to DS-3) | Native if BlueBubbles supports them, otherwise 👍 voting on one message per option |
| Join/leave events (AL-4), incoming tapbacks, photos (CS-7, AL-3) | Bridge events |
| Who said what (GC-4) | Sender's phone number on every forwarded message |
| Private DMs with native polls and contact cards (GC-6) | Photon Pro iMessage line |
| Message history for context | The Mac's Messages database |

## Commands

The agent sends commands and the bridge sends events, both as JSON. Every message carries its group tag in `g`.

```json
{"g": "a1b2c3", "cmd": "poll", "question": "Where to?", "options": ["Tulum", "Miami", "Austin"]}
{"g": "a1b2c3", "event": "message", "id": "m42", "from": "+15551234567", "text": "@scout tacos nearby?"}
{"g": "a1b2c3", "event": "reaction", "on": "m40", "from": "+15551234567", "tapback": "like"}
{"event": "hello", "capabilities": {"poll": "emulated", "react": "native", "typing": "native"}}
```

How the bridge handles each command, depending on whether the Private API is working:

| Command | With BlueBubbles Private API | Backup (`imessage-kit`) |
| --- | --- | --- |
| `say` | Native | Native |
| `send_photo` | Native | Native (download the file first; `imessage-kit` only sends local files) |
| `link` (album, directions, booking) | Native, with Messages' link preview | Native, with Messages' link preview |
| `poll` | Native if supported, otherwise 👍 voting | 👍 voting: one message per option, bridge counts tapbacks |
| `react` | Native tapback | Short text such as "✅ logged" |
| `reply_to` | Native threaded reply | Quote: "↪ Maya: 'tacos?' …" |
| `typing` | Native | Skipped |
| `rename_group`, `add_member` | Native | Not possible |

## Setup

### Mac and account

1. Create scout's Apple ID at [account.apple.com](https://account.apple.com), with a teammate's phone number for two-factor codes.
2. On an always-on Mac, create a macOS user called "scout."
3. Log in as "scout," sign into Messages with scout's Apple ID, and set Share Name and Photo to "scout."
4. Send a test message to a teammate right away. New Apple IDs sometimes fail to activate iMessage on a Mac. If it won't activate, fix that before building anything else, through Apple Support if needed.
5. Grant Full Disk Access to Terminal (and later to BlueBubbles and the bridge) under **System Settings → Privacy & Security**.
6. Switch back to another user from Control Center *without logging scout out*. Scout's session keeps running in the background.
7. Keep the Mac awake and set it to restart after a power cut. A sleeping Mac stops receiving messages. For a quick test, `caffeinate -dims` in scout's session is enough.

### Getting scout into a group

From an iPhone in the group, tap the group's name, then **Add Member**, and enter scout's email address.

- Every member must be on iMessage (blue bubbles). SMS groups don't allow adding people.
- Apple may only allow adding people to a group that already has at least three other members. If the group is smaller, start a new group that includes scout.

### Keeping it running

- Run the bridge and BlueBubbles as macOS background services (launchd) that restart automatically if they crash.
- Turn off automatic macOS updates once BlueBubbles works on the current version.
- Have a scheduled check text scout from a test account and alert us if no reply comes.

## Build order

1. **Set up the account and test the Mac (one afternoon).** Create scout's Apple ID and confirm iMessage activates on the Mac. This is the step most likely to fail, so do it first. Then install BlueBubbles, turn on the Private API, and check each feature in a test group: tapback, typing, threaded reply, rename, add member, native poll. The results decide which commands can be native.
2. **Basic bridge.** Use `imessage-kit` only: forward group messages to the agent, ignore direct messages, tag groups, route replies back.
3. **Protocol.** Add the JSON commands and events, the agent's tools and the capability report.
4. **Native features.** Switch the bridge's in-group actions to BlueBubbles, with `imessage-kit` as the backup.
5. **Private DMs.** Add Pro DMs and automatic user registration.

Steps 1–3 are enough for the demo.

## Open questions to test

- **Native group polls.** iMessage polls are new in iOS 26. Photon's paid server can create them, but nothing in BlueBubbles' public issues or releases shows it can.
- **Incoming tapbacks.** `imessage-kit`'s `Message` type has a `reaction` field, so 👍 voting should work in backup mode. Test it.
- **Telegram on Pro.** Photon's Telegram setup docs ask only for a bot token and project credentials, but nothing says which plans include it.
- **Registering users from code.** Check whether `photon spectrum users add` can run without prompts so the bridge can call it.

## Risks

| Risk | Mitigation |
| --- | --- |
| The new Apple ID won't activate iMessage on the Mac. | Create the account and sign into Messages before building anything that depends on it. Contact Apple Support if activation fails. |
| Apple flags scout's Apple ID as a bot. A new account has no history, which makes this more likely, and there's no recovery process like Photon offers Business customers. | Keep machine traffic off iMessage (Telegram link), have people message scout first, pace replies, no late-night messages, no more than 2–3 follow-ups. See Photon's [deliverability guide](https://photon.codes/docs/best-practices/imessage-deliverability.md). If the account is banned anyway, create a new one. No one's personal account is affected. |
| A macOS update breaks the BlueBubbles Private API. | Turn off automatic updates. The bridge falls back to `imessage-kit` and reports reduced capabilities. |
| Private API mode weakens macOS security on that Mac (System Integrity Protection is partly turned off). | Use a dedicated Mac with nothing personal on it, never a daily laptop. |
| The Mac sleeps, restarts or loses Wi-Fi, and scout goes offline. | Background services, sleep disabled, health check alerts, and the PRD's fallback demo ready. |
| An Android member turns the group into SMS, which this setup can't handle. | Out of scope: we're targeting iMessage only. |

## Options considered

| Option | Why not chosen |
| --- | --- |
| Buy Photon Business | $250 per number per month. |
| Use a teammate's personal Apple ID | Its Messages database holds their private chats, so the bridge would need an allow list to keep those away from the AI. A ban would cost them their own iMessage. People who have them saved as a contact would see their name instead of "scout," and their iPhone would show every scout group. |
| Test whether Pro handles existing groups | The docs hint that Pro can "reference an existing group," but every member would need registering, membership changes aren't reported, and the number is shared. Worth a 15-minute test, not a foundation. |
| Mac with `imessage-kit` only | Works, and it's our backup mode, but there are no tapbacks, typing indicators, threaded replies or native polls in the group. |
| Fake a group with DMs from Pro | Loses the main selling point: adding scout to the group text you already have. |
| Move groups to Telegram | Telegram bots join groups natively and it's free, but friends would have to plan outside their existing group text. Kept as a fallback if Apple flags the account. |
| WhatsApp Business | Photon's WhatsApp provider supports one-to-one chats only. |

## Sources

- [Photon pricing](https://photon.codes/pricing)
- [iMessage connection and routing](https://photon.codes/docs/spectrum-ts/providers/imessage/connection-and-routing.md)
- [iMessage troubleshooting](https://photon.codes/docs/spectrum-ts/troubleshooting/imessage.md)
- [iMessage deliverability](https://photon.codes/docs/best-practices/imessage-deliverability.md)
- [Telegram setup](https://photon.codes/docs/spectrum-ts/providers/telegram/setup.md) and [conversations](https://photon.codes/docs/spectrum-ts/providers/telegram/conversations-and-features.md)
- [WhatsApp Business conversations](https://photon.codes/docs/spectrum-ts/providers/whatsapp-business/conversations.md)
- [Photon CLI: Spectrum commands](https://photon.codes/docs/cli/spectrum.md)
- [Building a custom platform](https://photon.codes/docs/spectrum-ts/custom-platforms.md)
- [imessage-kit on GitHub](https://github.com/photon-hq/imessage-kit)
- [advanced-imessage-kit on GitHub](https://github.com/photon-hq/advanced-imessage-kit)
- [BlueBubbles Server on GitHub](https://github.com/BlueBubblesApp/bluebubbles-server)
