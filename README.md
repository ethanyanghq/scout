<p align="center">
  <img src="assets/logo.png" alt="scout logo" width="140">
</p>

<p align="center">
  <img src="assets/banner.svg" alt="scout: trips that make it out of the group chat" width="100%">
</p>

# scout

**trips that make it out of the group chat.**

hi, i'm scout.

you know the thread. someone says "we should go somewhere," everyone hearts it, and six hundred messages later nobody has booked a thing. add me to that chat and i'll get you from "we should go somewhere" to an actual trip.

here's how it goes:

1. **add me.** put my number in the group text. no app, no accounts, nobody signs up for anything.
2. **tell me what you want.** i send a quick trip card: pick the kind of trip, your dates on a calendar, your budget on a slider, where you're flying from, and what you're into. one tap sends it, and i keep track of who hasn't answered yet.
3. **i pitch three places.** once everyone's in, i look up well-reviewed spots that fit the whole group and send three brochures: photos, the best hotel there, things to do, and what the whole trip runs per person. tell me your final decision ("final decision: cancun") and i'll lock it in.
4. **you tell me what you'd actually do.** i send a deck of things to do at that hotel and that town, each with a picture and a price. rate each one nah, meh or yeah, send once, and i'll tell you what the group agreed on.
5. **i plan the days.** a day-by-day plan built from what you actually picked, paced for whether you're up at six or noon. then one room and one flight for everyone — you book, i put what it cost in the ledger.
6. **i put it on your calendar.** once the itinerary is posted, one link to subscribe to with every day of the plan as an event, kept up to date if the plan changes, then a shared album link for the photos.
7. **we settle up.** tell me what you paid ("i got the airbnb, $1,240") or text me a photo of the receipt. i split it, work out the fewest payments to square everyone up, and check each one off when you tell me you've paid ("i paid leo").

i never book anything or touch real money. i find the links, you book. and i stay quiet unless you tag me or tell me something about the trip, because a scout that talks too much gets kicked out of the chat.

**where i'm at:** the trip card, the brochures, the swipe deck, the itinerary, flights, the calendar link and cost splitting are all built. the cards are drawn right inside iMessage by [HermesShare](https://github.com/time-attack/HermesShare), an iMessage extension, so for now everyone needs our build of it on their phone; without it, every card falls back to plain text. on-trip recommendations and a shared photo album are still to come. the full plan lives in [scout-PRD.md](scout-PRD.md), and how the cards work lives in [integration.md](integration.md).

## What it looks like

<p align="center">
  <img src="assets/trip-card.jpg" alt="The trip card: trip vibe, calendar and budget" width="30%">
  &nbsp;
  <img src="assets/brochure.jpg" alt="A destination brochure for Cancún" width="30%">
  &nbsp;
  <img src="assets/swipe-deck.jpg" alt="The activity deck: swipe nah, meh or yeah" width="30%">
</p>

<p align="center"><sub>the trip card everyone fills out · a destination brochure · the activity deck you swipe through</sub></p>

## How it fits together

```
iMessage ⇄ Linq line (groups) ⇄ bridge/: Photon's spectrum-ts ──HTTP──▶ src/scout/ ⇄ Claude API
                                 TypeScript                             Python      + SQLite
```

My number is a [Linq](https://linqapp.com) line, a real iMessage number you can add to a group. Photon's cheaper plans can't join groups, so Linq gets me in, as a custom platform in Photon's Spectrum SDK, so every message goes through Photon ([scout-imessage-groups.md](scout-imessage-groups.md)). Photon only sends messages from TypeScript, so `bridge/` is a thin relay. Everything I know and decide lives in the Python service:

| File | What it does |
| --- | --- |
| `conversation.py` | Decides what happens with each message: count a vote, ask the agent when someone tags @scout, or stay quiet. |
| `agent.py` | Shows Claude the trip and the whole chat, then runs the tools Claude picks. |
| `system_prompt.md` | scout's instructions: when to speak, how to text, the planning flow. |
| `agent_tools.py` | The tools Claude can call, and how each call maps onto a trip action. |
| `trip_actions.py` | The changes scout can make to a trip (save preferences, post a poll, record a vote). |
| `group_summary.py` | Date overlap, budget range, and who hasn't replied. |
| `polls.py` | Reading "2" or "tulum" as a vote, and picking the winner. |
| `itinerary.py` | How the day-by-day plan reads in the chat. |
| `booking_links.py` | Google Flights links from each home city and an Airbnb link for the group. |
| `flights.py` | Live Google Flights search through SerpApi. |
| `best_flights.py` | The best flight from each home city, and how it reads in the chat. |
| `hotels.py` | Live Google Hotels search through SerpApi. |
| `best_hotel.py` | The hotel scout recommends for the trip, and how it reads in the chat. |
| `serpapi.py` | The request that the flight and hotel searches share. |
| `calendar_feed.py` | The subscribable calendar feed of the itinerary, and the link to it sent when the first plan is posted. |
| `money.py` | How amounts of money read in the chat. |
| `settle_up.py` | Who owes whom: each person's share and the fewest payments to settle up. |
| `trip_store.py` | Saving everything to SQLite. |
| `simulate.py` | A fake group chat in your terminal for testing without phones. |

## Setup

You need [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh), and an Anthropic API key.

```sh
uv sync
cd bridge && bun install && cd ..
export ANTHROPIC_API_KEY=sk-ant-...
# or, without an Anthropic key, run me on OpenAI:
# export OPENAI_API_KEY=sk-...
```

There are no database migrations yet. After pulling a change to the database layout, delete your local `scout.db`.

## Take me for a spin (no phones needed)

Run a whole group chat in your terminal, playing every person yourself:

```sh
uv run scout-simulate maya leo jordan priya
> maya: hey @scout, spring break?
> maya: i'm maya, free mar 13-20, ~$800, flying from boston, need a beach
> leo: leo here, mar 14-22, 600, nyc
...
> leo: 2
> leo: fyi I paid the airbnb, $1,240
> jordan: @scout who owes what
> jordan: @scout I paid leo
```

Add `--verbose` to see each tool I call.

## Put me in a real group chat

1. Start the Python service: `uv run scout-server` (listens on `127.0.0.1:8787`).
2. Create `bridge/.env` with one of these:
   - A Linq line, for group chats. Each teammate gets their own free line and key with `npm i -g @linqapp/cli && linq signup`. See [scout-imessage-groups.md](scout-imessage-groups.md).
     ```
     IMESSAGE_MODE=linq
     LINQ_API_KEY=...
     ```
   - A Photon cloud line, for one-on-one chats:
     ```
     IMESSAGE_MODE=cloud
     PHOTON_PROJECT_ID=...
     PHOTON_PROJECT_SECRET=...
     ```
   - Local mode, which runs on this Mac's Messages account. It needs an Apple ID signed into Messages and Full Disk Access for your terminal.
     ```
     IMESSAGE_MODE=local
     ```
3. Start the bridge: `cd bridge && bun start`.
   - In Linq mode, also run `linq webhooks listen --forward-to http://127.0.0.1:8788/linq-events` in another terminal. It relays Linq's events to the bridge.
   - Or start the service, the bridge and the relay together with `cd bridge && bun run dev`.
4. Add my number to a group text and say hi.
   - On Linq's free line, everyone in the group texts my number privately first (`linq contacts add` each of them, up to 20). I ignore those private texts.

## Development

[DEVELOPING.md](DEVELOPING.md) covers testing a change without phones, running me in a real group, and setting up the demo group. It's written for teammates and their coding agents.

```sh
uv run pytest                  # tests
uv run ruff check src tests    # lint
uv run ruff format src tests   # format
cd bridge && bun test          # bridge tests
cd bridge && bun run dev       # service, bridge and Linq relay in one terminal
cd bridge && bun run devchat   # play a group chat through the bridge, no phones
cd bridge && bun run e2e       # end-to-end journeys (needs ANTHROPIC_API_KEY)
cd bridge && bun run typecheck # type-check the bridge
```
