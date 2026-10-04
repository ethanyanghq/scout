# scout demo to-do

scout is a hackathon demo and won't launch to real users, so this lists only what the demo needs, plus the developer tools and group chat connector that get us there. The bar (PRD §11) is the full journey in a real group text: add scout, share preferences, pick a destination off the brochure card, tick the activity deck, an itinerary, book the room and the flight into the ledger, an on-the-spot recommendation, and a settle-up. The card flow is specified in [integration.md](integration.md) and built as milestone 4 of [scout-group-chat-plan.md](scout-group-chat-plan.md); none of it exists yet.

Work top to bottom. Check items off in the commit or PR that finishes them.

## 1. Blockers: do these first

- [ ] Each teammate: get a Linq line and key (`npm i -g @linqapp/cli && linq signup`) and send it a test text ([scout-imessage-groups.md](scout-imessage-groups.md), Setup).
- [ ] Set up the demo Mac: Bun, uv and the Linq CLI installed, and kept awake (`caffeinate -dims`).
- [ ] Get an Anthropic API key.
- [ ] Create a Google Cloud key with Places API (New) enabled and billing on, and add a budget alert.
- [ ] Get a SerpApi key for live Google Flights fares (`SERPAPI_API_KEY`). The free plan's monthly searches cover rehearsals if nobody leaves it in a loop: each flight card uses one search per home city.
- [ ] Put the keys in `.env` and `bridge/.env` (copy the `.env.example` templates).
<<<<<<< HEAD
- [ ] Pick the demo line: one teammate's Linq line, with its `LINQ_API_KEY` in `bridge/.env` on the demo Mac and the `linq` CLI logged into the same line.
- [ ] Line up the demo phones: at least 3 besides scout (Maya, Leo, Jordan, Priya), one per member, charged and on iMessage. Put their numbers in `bridge/demo/roster.json` (copy `roster.example.json`, never commit it).
=======
- [ ] Decide where scout's pages are hosted and stand it up. Every HermesShare card needs an HTTPS thumbnail URL or it won't send, and the host also has to proxy Google Places photos, whose URLs embed the API key. This blocks every card.
- [ ] Prove the card pipe: clone HermesShare, send one hand-written card to a real Linq group, submit it, and write down what lands in the thread. Answers whether a submit arrives as `HermesSubmission` JSON or as a readable summary, whether the free line accepts `imessage_app` parts, and how big a payload really gets.
- [ ] Sideload `docs/install/HermesShare.ipa` on every demo phone. Without it, a card is only its fallback text.
>>>>>>> d39c6e1 (Added plan file)

## 2. First real run

Nothing after the vote has ever run against real Claude, so expect fixes here.

- [ ] Play the whole trip in `uv run --env-file .env scout-simulate maya leo jordan priya`: preferences, vote, "@scout plan it", "@scout where do we book", "@scout cozy taco spot near Condado", "2", "fyi I paid the airbnb, $1,240", "@scout who owes what", "@scout I paid leo".
- [ ] Fix whatever breaks.
- [ ] With the real Google key, check that a vibe search returns three real places with price levels.
- [ ] Run the journey in a real iMessage group: at least 3 other members, all on iMessage. Include a real iPhone receipt photo.

## 3. Group chat connector, developer tools and demo group

Follow the checklist in [scout-group-chat-plan.md](scout-group-chat-plan.md). The demo needs its milestone 2 (the hackathon requires Photon in the message path), milestone 3 (the demo group) and milestone 4 (the cards the new flow is built on). Milestone 1, the developer tools, makes everything after it faster.

The code for all three milestones is built. What's left waits on section 1: a real Linq line, the demo phones and a Claude key. In plan order:

- [ ] Milestone 1: run `bun run e2e` with a real `ANTHROPIC_API_KEY`, and fix the two scripts that need Claude until they pass reliably.
- [ ] Milestone 2: record real Linq webhooks as test fixtures, find out what the free line supports, and run the journey in a real group on the new connector.
- [ ] Milestone 3: check on the demo line that Linq can create a group and share a contact card, then run `bun run demo setup` until every phone has texted scout, and rehearse a member adding scout to a group on stage.

## 4. Fixes that protect the demo

- [ ] When a photo or voice note can't be converted, still keep its caption instead of failing the whole message (`src/scout/media.py`, `src/scout/app.py`).

## 5. Decide

<<<<<<< HEAD
- [ ] The shared trip album (AL-1, AL-2): cut it from the demo, or build it? It isn't part of the §11 bar, and building it means hosting and storage. If it's cut, take it out of the script and the journey page.
- [ ] Where scout's web pages are hosted. Link cards need a public HTTPS URL, and so would the album: a tunnel from the demo Mac, or a separate host ([scout-imessage-groups.md](scout-imessage-groups.md), Open questions)? Today the calendar link's card is titled "Google Calendar - Sign in to Access & Edit Your Schedule", which a page of scout's own would replace. scout's contact card also has no photo until there's an HTTPS URL for one, or someone adds it in Linq's dashboard.
=======
- [ ] The shared trip album (AL-1, AL-2): cut it from the demo, or build it? The new flow ends on it ([integration.md](integration.md), stage 8), so cutting it means the demo stops on the calendar instead. Hosting is being stood up for the cards anyway, so the remaining cost is storage. If it's cut, take it out of the script and the journey page.
- [x] Where scout's web pages are hosted. No longer a question, only work: it's a blocker in section 1 above, because no card sends without an HTTPS thumbnail. Still to pick: a tunnel from the demo Mac, or a separate host ([scout-imessage-groups.md](scout-imessage-groups.md), Open questions). Today the calendar link's card is titled "Google Calendar - Sign in to Access & Edit Your Schedule", which a page of scout's own would replace.
- [ ] Whether the demo leans on cards or stays in text. If the extension can't be sideloaded on every demo phone in time, fall back to the numbered text poll (DS-5) and show the cards on one phone only.
>>>>>>> d39c6e1 (Added plan file)

## 6. Script and rehearsal

- [ ] Write the demo script: who types what on which phone, following the journey page, with San Juan as the destination. Say who taps which card and when.
- [ ] Rehearse end to end at least twice, and time the replies (the PRD's target is about 10 seconds).

## 7. Fallbacks

- [ ] Rehearse a `scout-simulate` run on a laptop, ready to show if iMessage fails.
- [ ] Keep a console script of the whole journey ready to replay if iMessage fails.
- [ ] Keep the interactive journey page open in a tab.
- [ ] Rehearse the journey with cards falling back to text, in case a phone can't render them.

## 8. Day of

- [ ] Run `bun run demo setup` the day before, so every phone has been offered scout's contact card.
- [ ] Start a fresh group of the demo phones, without scout in it, so a member can add scout on stage.
- [ ] Mac plugged in, awake, and online. Service, bridge and `linq webhooks listen` running.
- [ ] Send a test text 30 minutes before going on stage.
- [ ] Check that every demo phone still has the HermesShare extension, by opening one card.

## Team

- [ ] Everyone runs `git config pull.rebase true` in their own clone.
- [ ] Land changes through pull requests, not direct pushes to `main`.
- [x] Merge PR #4 (the `.env.example` templates).
