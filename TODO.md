# scout to-do

Everything still open, grouped by what it unblocks. Requirement IDs point to [scout-PRD.md](scout-PRD.md). Check items off in the same commit that finishes them.

## Version control

- [x] Pull with rebase instead of merge commits (`git config pull.rebase true`, set per clone).
- [ ] Everyone on the team runs `git config pull.rebase true` in their own clone.
- [ ] Agree to land changes through pull requests instead of pushing to `main`. GitHub can't enforce this: branch protection needs GitHub Pro or a public repo.
- [ ] Merge the `receipts-and-photos` PR (receipt photos, bridge photo forwarding, README).

## Before the demo: setup

- [ ] Create scout's Apple ID (an email handle) and confirm iMessage activates on the Mac. This is the step most likely to fail ([scout-imessage-groups.md](scout-imessage-groups.md), Setup).
- [ ] Set up the Mac: a "scout" macOS user, Full Disk Access for the terminal, kept awake.
- [ ] Get an Anthropic API key and set `ANTHROPIC_API_KEY`.
- [ ] Get a Nessie API key from nessieisreal.com and set `NESSIE_API_KEY`.
- [ ] Delete any old local `scout.db`. The schema changed and there are no migrations.

## Before the demo: verify

- [ ] Run a whole trip in `uv run scout-simulate maya leo jordan priya`. Steps 4–6 (itinerary, booking links, cost splitting) have never run against real Claude.
- [ ] With a real Nessie key, check that opening a customer and account works with scout's fields (`nessie.py`).
- [ ] With a real Nessie key, check that deposits accept the same fields as withdrawals.
- [ ] Check that Nessie balances actually change after a withdrawal and deposit.
- [ ] Check what Nessie does when a withdrawal is bigger than the balance.
- [ ] Text a real receipt photo (HEIC from an iPhone) through the bridge and confirm scout reads it back.
- [ ] Test scout in a real iMessage group end to end: join, preferences, vote, plan, expenses, "@scout pay Leo".
- [ ] Rehearse the "@scout pay Leo → Paid ✓" moment for the Capital One prize, and the simulated fallback if Nessie is down.
- [ ] Open everyone's Nessie accounts before going on stage, so a slow API can't stall the first payment.

## Phase 2: still to build (P0)

- [ ] On-trip discovery: 3 nearby options for a vibe, with travel time and price level (OT-1).
- [ ] Work out the group's location from a named place, the lodging, or a shared location (OT-2).
- [ ] Send a directions link once the group picks (OT-3).
- [ ] Create the shared trip album and text everyone the link (AL-1).
- [ ] Add photos texted to scout or uploaded through the link (AL-2).
- [ ] Keep receipt photos out of the album once it exists (AL-3, CS-7).

## Decisions needed

- [ ] Pick the places API for on-trip discovery (OT-1 to OT-3).
- [ ] Pick album hosting (AL-1, AL-2). The PRD proposes a scout-hosted web album.
- [ ] Decide whether payments made outside scout (cash, Venmo, "sent 💸") can be recorded, or everything goes through Nessie.

## Cost splitting follow-ups

- [ ] Remind people who still owe on a schedule, not just when someone asks (CS-4).
- [ ] Uneven splits, such as an activity only some members joined (CS-5).
- [ ] Show a running balance on request (CS-6).
- [ ] Split a receipt by item, with tax and tip shared proportionally (CS-8).
- [ ] Keep each receipt image with its expense (CS-9).
- [ ] Convert receipts in other currencies (CS-10, P2).
- [ ] When a photo can't be converted, still forward its caption instead of dropping the whole message (`bridge/index.ts`).
- [ ] When a Nessie deposit fails after the withdrawal went through, say so instead of only logging it.
- [ ] Check the Nessie key at startup (an empty `POST /customers` answers 401 for a bad key), so a bad key doesn't silently make every payment simulated.

## Tests

- [ ] Add an HTTP test for the `/messages` endpoint, including photos. FastAPI's test client needs `httpx`, which isn't installed.
- [ ] Add end-to-end tests for the critical user journeys (AGENTS.md). There are none yet.

## Phase 3 and later (P1/P2)

- [ ] Pause or remove scout with "@scout pause" (GC-5).
- [ ] Cap proactive messages per day (PRD §7).
- [ ] Nudge members who haven't shared preferences (PR-3).
- [ ] Reuse polls for restaurants and activities (DS-4).
- [ ] "@scout summary" for the whole trip (IT-4).
- [ ] Opening hours and group size in recommendations (OT-4).
- [ ] .ics files and per-day calendar events (CAL-2, CAL-3), and updated links when plans change (CAL-4).
- [ ] Album extras: auto-add with opt-in, late joiners, post-trip reminder, download (AL-3 to AL-5).
- [ ] Private DMs with scout for sensitive constraints (GC-6).
- [ ] Database migrations, so schema changes don't mean deleting `scout.db`.

## iMessage questions to test

- [ ] Native group polls through BlueBubbles.
- [ ] Incoming tapbacks as votes.
- [ ] Whether Photon Pro includes Telegram.
- [ ] Whether `photon spectrum users add` runs without prompts.
