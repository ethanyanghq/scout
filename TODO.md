# scout demo to-do

scout is a hackathon demo and won't launch to real users, so this lists only what the demo needs, plus the developer tools and group chat connector that get us there. The bar (PRD §11) is the full journey in a real group text: add scout, share preferences, a live vote, an itinerary, an on-the-spot recommendation, and a settle-up. The Capital One prize rides on "@scout pay Leo → Paid ✓".

Work top to bottom. Check items off in the commit or PR that finishes them.

## 1. Blockers: do these first

- [ ] Each teammate: get a Linq line and key (`npm i -g @linqapp/cli && linq signup`) and send it a test text ([scout-imessage-groups.md](scout-imessage-groups.md), Setup).
- [ ] Set up the demo Mac: Bun, uv and the Linq CLI installed, and kept awake (`caffeinate -dims`).
- [ ] Get an Anthropic API key.
- [ ] Get a Nessie API key from nessieisreal.com.
- [ ] Create a Google Cloud key with Places API (New) enabled and billing on, and add a budget alert.
- [ ] Put the keys in `.env` and `bridge/.env` (copy the `.env.example` templates).
- [ ] Pick the demo line: one teammate's Linq line, with its `LINQ_API_KEY` in `bridge/.env` on the demo Mac and the `linq` CLI logged into the same line.
- [ ] Line up the demo phones: at least 3 besides scout (Maya, Leo, Jordan, Priya), one per member, charged and on iMessage. Put their numbers in `bridge/demo/roster.json` (copy `roster.example.json`, never commit it).

## 2. First real run

Nothing after the vote has ever run against real Claude, so expect fixes here.

- [ ] Play the whole trip in `uv run --env-file .env scout-simulate maya leo jordan priya`: preferences, vote, "@scout plan it", "@scout where do we book", "@scout cozy taco spot near Condado", "2", "fyi I paid the airbnb, $1,240", "@scout who owes what", "@scout pay leo".
- [ ] Fix whatever breaks.
- [ ] With the real Nessie key, check that opening a customer and account works with scout's fields (`nessie.py`).
- [ ] With the real Nessie key, check that deposits accept the same fields as withdrawals.
- [ ] Check that Nessie balances actually change after a payment.
- [ ] With the real Google key, check that a vibe search returns three real places with price levels.
- [ ] Run the journey in a real iMessage group: at least 3 other members, all on iMessage. Include a real iPhone receipt photo.

## 3. Group chat connector, developer tools and demo group

Follow the checklist in [scout-group-chat-plan.md](scout-group-chat-plan.md). The demo needs its milestone 2 (the hackathon requires Photon in the message path) and milestone 3 (the demo group). Milestone 1, the developer tools, makes everything after it faster.

The code for all three milestones is built. What's left waits on section 1: a real Linq line, the demo phones and a Claude key. In plan order:

- [ ] Milestone 1: run `bun run e2e` with a real `ANTHROPIC_API_KEY`, and fix the two scripts that need Claude until they pass reliably.
- [ ] Milestone 2: record real Linq webhooks as test fixtures, find out what the free line supports, and run the journey in a real group on the new connector.
- [ ] Milestone 3: check on the demo line that Linq can create a group and share a contact card, then run `bun run demo setup` until every phone has texted scout, and rehearse a member adding scout to a group on stage.

## 4. Fixes that protect the demo

- [ ] Check the Nessie key at startup (an empty `POST /customers` answers 401 for a bad key). Today a bad key silently turns every payment into "simulated".
- [ ] Add a way to open everyone's Nessie accounts before going on stage, so a slow API can't stall the first payment.
- [ ] When a photo can't be converted, still forward its caption instead of dropping the whole message (`bridge/index.ts`, `bridge/linq.ts`).

## 5. Decide

- [ ] The shared trip album (AL-1, AL-2): cut it from the demo, or build it? It isn't part of the §11 bar, and building it means hosting and storage. If it's cut, take it out of the script and the journey page.
- [ ] Where scout's web pages are hosted. Link cards need a public HTTPS URL, and so would the album: a tunnel from the demo Mac, or a separate host ([scout-imessage-groups.md](scout-imessage-groups.md), Open questions)? Today the calendar link's card is titled "Google Calendar - Sign in to Access & Edit Your Schedule", which a page of scout's own would replace. scout's contact card also has no photo until there's an HTTPS URL for one, or someone adds it in Linq's dashboard.

## 6. Script and rehearsal

- [ ] Write the demo script: who types what on which phone, following the journey page, with San Juan as the destination.
- [ ] Make "@scout pay Leo → Paid ✓" the high point, for the Capital One judges.
- [ ] Rehearse end to end at least twice, and time the replies (the PRD's target is about 10 seconds).

## 7. Fallbacks

- [ ] Rehearse a `scout-simulate` run on a laptop, ready to show if iMessage fails.
- [ ] Keep a console script of the whole journey ready to replay if iMessage fails.
- [ ] Keep the interactive journey page open in a tab.
- [ ] Rehearse a payment with Nessie unreachable, so "(simulated)" doesn't surprise anyone.

## 8. Day of

- [ ] Run `bun run demo setup` the day before, so every phone has been offered scout's contact card.
- [ ] Start a fresh group of the demo phones, without scout in it, so a member can add scout on stage.
- [ ] Mac plugged in, awake, and online. Service, bridge and `linq webhooks listen` running.
- [ ] Send a test text 30 minutes before going on stage.
- [ ] Open the Nessie accounts (see section 4).

## Team

- [ ] Everyone runs `git config pull.rebase true` in their own clone.
- [ ] Land changes through pull requests, not direct pushes to `main`.
- [x] Merge PR #4 (the `.env.example` templates).
