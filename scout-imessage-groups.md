# iMessage group chats without Photon Business

| | |
| --- | --- |
| **Question** | How does scout work in iMessage group chats when we're on Photon's Pro plan, not Business? |
| **Recommendation** | Run scout's iMessage account on a Mac we own, using Photon's free, open-source local SDK. |
| **Docs version** | Photon Stable docs, read October 2, 2026 |
| **Related** | [scout-PRD.md](scout-PRD.md): GC-1, GC-6, DS-1 to DS-3, and the messaging risks in the risks table |

## Summary

Pro alone can't give scout real group chats. Pro numbers come from a shared pool, and Photon turns off group features on them. Business ($250 per number per month) is the only cloud plan with groups.

Photon also publishes a free SDK that runs on a Mac and uses that Mac's own Messages account. It doesn't go through Photon's cloud, so the plan limits don't apply. If a friend adds scout's Apple ID to their group text, scout can read and reply in that group. It costs a Mac (one-time, or free if we have one) plus about $10–15 a month for a prepaid SIM.

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

## Recommended: run scout on a Mac we control

Photon's SDK can connect to iMessage three ways: **Cloud** (the paid plans), **Self-hosted** (Photon's own server software, which isn't open source) and **Local**. Local reads the Mac's Messages database and sends through the Messages app. It needs no Photon account.

### Setup

1. **Mac.** Use an always-on Mac: a spare MacBook, or a used Mac mini for about $300–500. Turn off sleep.
2. **Apple ID.** Create a new Apple ID for scout and sign it into Messages on the Mac.
3. **Phone number (optional).** An Apple ID email works for iMessage on its own. For a real phone number, put a prepaid SIM in a spare iPhone signed into the same Apple ID. Then turn that number on for Messages on the Mac.
4. **Permissions.** Grant Full Disk Access to whatever runs scout (the terminal or the app) under **System Settings → Privacy & Security**. Restart it afterwards.
5. **SDK.** Choose one:
   - `@spectrum-ts/imessage-local`: the same Spectrum code we'd write for the cloud, with no project credentials.
   - `@photon-ai/imessage-kit` (MIT licence): the library the local package is built on. It has an `onGroupMessage` handler, sends to an existing group by its chat ID, and reports `memberAdded`, `memberRemoved` and `nameChanged` events.

### How a group starts

A friend adds scout's handle to their existing group text. Scout receives every message in that group and replies in the same thread. This matches GC-1 in the PRD.

Every group starting with a person adding scout also follows Photon's main [deliverability](https://photon.codes/docs/best-practices/imessage-deliverability.md) advice: people message first and scout never messages strangers cold, which keeps Apple from flagging the account.

### What it fixes from the PRD

The PRD lists this as a risk: adding a regular phone number (for example, Twilio) to an iMessage group turns it into a green-bubble SMS group. An Apple ID on a Mac is a real iMessage account, so the group stays blue.

### What the local SDK can't do

Local mode supports text, attachments and contact cards in groups. It doesn't support:

- tapback reactions
- threaded replies
- native iMessage polls
- typing indicators
- creating groups, renaming them, or adding and removing members

How scout works around these:

| Need | Workaround |
| --- | --- |
| Votes (DS-1 to DS-3) | People reply "1", "2" or "3", or tap a link to a small web poll. |
| Receipts and album photos | Supported: attachments work in local mode. |
| Confirming scout heard a message | Send a short text reply instead of a tapback. |

## Later upgrade: full iMessage features

If we need tapbacks, typing indicators, or creating groups and managing their members, install [BlueBubbles Server](https://bluebubbles.app) (open source) on the same Mac. It uses Apple's private Messages API to unlock those features.

The catch: we'd have to partly turn off System Integrity Protection, a macOS security feature.

To keep scout's code the same either way, wrap BlueBubbles as a custom platform with Spectrum's [`definePlatform`](https://photon.codes/docs/spectrum-ts/custom-platforms.md).

## Other options considered

### Test whether Pro handles existing groups

The docs say Pro can still "reference an existing group" with `space.get(chatGuid)`, and the pricing page lists Pro's group messaging as "Limited," not "none." A 15-minute test would settle it:

1. Register three test users in the dashboard.
2. Have one of them add their Pro number to a group with the other two.
3. Check whether group messages reach `app.messages` and whether scout can reply.

**Why we shouldn't build on it even if it works:** every member has to be pre-registered, the 100-user cap covers only about 20 groups of five, membership changes aren't reported, and the number is shared with other Photon customers.

### Fake a group with DMs

Scout DMs each member and relays messages between them. This works on Pro today, but it drops the main selling point: adding scout to the group text you already have. Keep it as a demo backup only.

### Use Cloud and Local together

One Spectrum app can register both. Pro handles private one-to-one chats (GC-6) and the Mac handles groups. The downside is that scout messages people from two different numbers, which is confusing. For the hackathon, run everything on the Mac.

## Risks

| Risk | Mitigation |
| --- | --- |
| Apple flags or bans scout's Apple ID. | Follow Photon's deliverability rules: no message bursts, no messages between midnight and morning, no cold outreach, and no more than 2–3 follow-ups. Apple also deactivates numbers that go unused for about two months. |
| Automating a personal Apple ID is a grey area under Apple's terms. | Acceptable for a class demo. Revisit before real users. |
| An Android member turns the group into SMS, which a Mac can't send on its own. | Out of scope: we're targeting iMessage only. |
| The Mac sleeps, restarts or loses Wi-Fi, and scout goes offline. | Turn off sleep, set scout to restart automatically, and keep the PRD's fallback demo ready. |

## Next steps

1. Run the 15-minute Pro group test (cheap, and it settles the open question).
2. Pick the Mac and create scout's Apple ID.
3. Build a minimal prototype: receive a group message and reply when someone writes "@scout".
4. Rework the vote flow (DS-1 to DS-3) as numbered replies or a web poll.

## Sources

- [Photon pricing](https://photon.codes/pricing)
- [iMessage connection and routing](https://photon.codes/docs/spectrum-ts/providers/imessage/connection-and-routing.md)
- [iMessage troubleshooting](https://photon.codes/docs/spectrum-ts/troubleshooting/imessage.md)
- [iMessage deliverability](https://photon.codes/docs/best-practices/imessage-deliverability.md)
- [Chat SDK iMessage adapter](https://photon.codes/docs/integrations/chat-sdk.md)
- [Building a custom platform](https://photon.codes/docs/spectrum-ts/custom-platforms.md)
- [imessage-kit on GitHub](https://github.com/photon-hq/imessage-kit)
- [advanced-imessage-kit on GitHub](https://github.com/photon-hq/advanced-imessage-kit)
