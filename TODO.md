# scout demo to-do

scout is a hackathon demo and won't launch to real users, so this lists only what the demo needs. The bar (PRD §11) is the full journey in a real group text: add scout, share preferences, a live vote, an itinerary, an on-the-spot recommendation, and a settle-up. The Capital One prize rides on "@scout pay Leo → Paid ✓".

Work top to bottom. Check items off in the commit or PR that finishes them.

## 1. Blockers: do these first

- [ ] Create scout's Apple ID (an email handle), sign it into Messages on the demo Mac, and send a test text. New Apple IDs sometimes fail to activate iMessage, so do this today ([scout-imessage-groups.md](scout-imessage-groups.md), Setup).
- [ ] Set up the Mac: a "scout" macOS user, Full Disk Access for the terminal, and kept awake (`caffeinate -dims`).
- [ ] Get an Anthropic API key.
- [ ] Get a Nessie API key from nessieisreal.com.
- [ ] Create a Google Cloud key with Places API (New) enabled and billing on, and add a budget alert.
- [ ] Put the keys in `.env` and `bridge/.env` (copy the `.env.example` templates).

## 2. First real run

Nothing after the vote has ever run against real Claude, so expect fixes here.

- [ ] Play the whole trip in `uv run --env-file .env scout-simulate maya leo jordan priya`: preferences, vote, "@scout plan it", "@scout where do we book", "@scout cozy taco spot near Condado", "2", "fyi I paid the airbnb, $1,240", "@scout who owes what", "@scout pay leo".
- [ ] Fix whatever breaks.
- [ ] With the real Nessie key, check that opening a customer and account works with scout's fields (`nessie.py`).
- [ ] With the real Nessie key, check that deposits accept the same fields as withdrawals.
- [ ] With the real Nessie key, check that scout starts: the startup key check expects an empty `POST /customers` to answer 400, not create a customer.
- [ ] Check that Nessie balances actually change after a payment.
- [ ] With the real Google key, check that a vibe search returns three real places with price levels.
- [ ] Run the journey in a real iMessage group: at least 3 other members, all on iMessage. Include a real iPhone receipt photo.

## 3. Fixes that protect the demo

- [x] Check the Nessie key at startup, so a bad key stops the server instead of silently turning every payment into "simulated".
- [x] Open everyone's Nessie accounts when scout posts who owes whom, so a slow API can't stall the first payment.
- [ ] When a photo can't be converted, still forward its caption instead of dropping the whole message (`bridge/index.ts`).

## 4. Decide

- [ ] The shared trip album (AL-1, AL-2): cut it from the demo, or build it? It isn't part of the §11 bar, and building it means hosting and storage. If it's cut, take it out of the script and the journey page.

## 5. Script and rehearsal

- [ ] Write the demo script: who types what on which phone, following the journey page, with San Juan as the destination.
- [ ] Make "@scout pay Leo → Paid ✓" the high point, for the Capital One judges.
- [ ] Line up the phones: one per member, all on iMessage.
- [ ] Rehearse end to end at least twice, and time the replies (the PRD's target is about 10 seconds).

## 6. Fallbacks

- [ ] Rehearse a `scout-simulate` run on a laptop, ready to show if iMessage fails.
- [ ] Keep the interactive journey page open in a tab.
- [ ] Rehearse a payment with Nessie unreachable, so "(simulated)" doesn't surprise anyone.

## 7. Day of

- [ ] Delete the old `scout.db` and start a fresh group chat.
- [ ] Mac plugged in, awake, and online. Service and bridge running.
- [ ] Send a test text 30 minutes before going on stage.

## Team

- [ ] Everyone runs `git config pull.rebase true` in their own clone.
- [ ] Land changes through pull requests, not direct pushes to `main`.
- [x] Merge PR #4 (the `.env.example` templates).
