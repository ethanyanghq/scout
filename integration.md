# Integration: the card-driven trip flow

| | |
| --- | --- |
| **Question** | How does the whole trip get planned, end to end, now that scout can put native interactive cards in the group chat? |
| **Decision** | scout keeps the conversation in plain text and uses a card at each of the four moments where a group has to choose something: the destination, the activities, the itinerary and each booking. Cards are [HermesShare](https://github.com/time-attack/HermesShare) layouts, sent as a Linq `imessage_app` part. |
| **Docs version** | HermesShare `main`, read October 3, 2026. Linq Partner API v3. |
| **Related** | [scout-PRD.md](scout-PRD.md) for what scout is for, [scout-imessage-groups.md](scout-imessage-groups.md) for how messages reach it, [scout-group-chat-plan.md](scout-group-chat-plan.md) for the build order |
| **Status** | Spec. None of this is built. See [DEVELOPING.md](DEVELOPING.md)'s "What exists today". |

## Summary

The trip goes through eight stages. A member adds scout to a group they already
have, scout interviews everyone about logistics, and from there each decision is
a card: three destination brochures that double as a ballot, an activity deck
everyone ticks through, the itinerary that falls out of it, and one hotel and
one flight that land in the shared ledger. It ends with a calendar everyone can
add in one tap and a shared album link.

The group never leaves the thread, nobody installs scout, and nothing is booked
on anyone's behalf.

## What changes from today

scout already does preferences, a numbered destination poll, an itinerary,
booking search links, nearby places, expenses and settle-up, all in plain text.
This flow keeps the engine and changes the surface and the order:

| Today | This flow |
| --- | --- |
| Preferences: name, dates, budget, home city, must-have | Adds vacation interest and chronotype |
| Destination poll as four text messages, vote by number or 👍 | One brochure card; each person's submit is their vote |
| Itinerary written from must-haves | Itinerary written from what the group actually swiped yeah on |
| Flight and stay search links for every home city | One hotel and one flight, each confirmed into the ledger |
| Calendar link right after the poll closes | Calendar at the end, with every booking and activity on it |
| Album "coming soon" | Album link closes the flow |

## Assumptions

Stated here rather than buried, because they cut a lot of scope:

- **No loyalty points, fares or status.** Prices are estimates, always labeled.
- **One of everything.** The group shares one origin, one set of dates, one
  hotel, one flight and one itinerary. Nobody books separately, nobody arrives
  a day early.
- **scout still books nothing.** It links out; a member books and tells scout
  what it cost. This is unchanged from the PRD's non-goals.

---

## 1. The flow

| Stage | Starts when | scout does | Card |
| --- | --- | --- | --- |
| 1. Join | A member adds scout's number | Introduces itself, then opens the interview | — |
| 2. Logistics | Immediately after the intro | Saves each reply, confirms it in one line, chases what's missing | — |
| 3. Destination | Everyone has answered | Posts the summary, then three brochures | **Brochure** |
| 4. Activities | The destination is locked | Posts a deck of activities at that destination and hotel | **Deck** |
| 5. Itinerary | Everyone has submitted their picks | Builds the plan from the aggregate | **Itinerary** |
| 6. Hotel | The itinerary is posted | Asks the member who added scout to book the room | **Booking** |
| 7. Flight | The hotel is in the ledger | Posts the one best-value flight | **Booking** |
| 8. Wrap | The flight is in the ledger | Calendar for everything, then the album link | — |

### Stage 1 — Join

iMessage gives scout no "member joined" event, so the first message it sees in a
chat is treated as joining (GC-2, unchanged). Its first words are fixed:

> Hi, I'm scout 👋 I'm a personal travel assistant. I help you plan your trips
> and keep track of what everyone spends.

Then, in the same message, the interview. A typical opener from the group is
"@scout we're planning spring break in the Bahamas, can you help?", and scout
should fold anything it already learned from that into the interview rather than
asking for it again.

### Stage 2 — Logistics

Five things from each person, in the chat, interview style:

| Field | Example | Why |
| --- | --- | --- |
| Name | "Maya" | iMessage gives scout only phone numbers (GC-4) |
| Dates free | "mar 13–20" | The shared window |
| Budget | "~$800" | The group's ceiling is the lowest budget in it |
| Leaving from | "Boston" | One origin for everyone (see Assumptions) |
| Vacation interest | "beach", "lakefront", "tropical", "city" | Shapes the three destinations |
| Chronotype | early riser / late riser / night owl | **Only** used to pace the itinerary |

Vacation interest is new. Everything else exists today.

Chronotype earns its place by doing exactly one job: a group of night owls gets
late starts and dinner-first days, early risers get sunrise hikes and the
anchor activity before noon. If it isn't visible in the itinerary, don't ask
for it.

scout confirms each reply in one line so mistakes get caught
("Got it, Leo: Mar 14–20 · ~$600 · from NYC · beach · night owl"), and asks only
for what's still missing. It does not post the summary until everyone it knows
about has answered, which is why it reads the chat's handles rather than only
the people who have spoken.

**Consensus.** The group talks among themselves, and scout stays out of it. It
speaks when tagged, when someone shares their details, and once at the end —
when nobody is left to wait on, it posts the summary and moves to stage 3. If
somebody says "the final plan is…" and it conflicts with what scout saved, the
person's words win and scout re-confirms.

### Stage 3 — Destination

scout posts the group summary as text, then **one brochure card** holding three
destinations that fit the shared dates, the lowest budget, the shared origin and
the group's interests.

Each row is collapsed to a name and an estimate. Tapping it opens the brochure:
a photo, the top-rated hotel there with its rating, the amenities, and the
estimated total for the whole trip per person.

```
┌──────────────────────────────────────┐
│ 3 spots that fit Mar 13–20           │
│ Tap one to look around, then send    │
│ ──────────────────────────────────── │
│ ▼ Cancun, MX                 ~$780   │
│   [photo]                            │
│   Hotel Xcaret Arte · ★4.7           │
│   All-inclusive · beach · spa · pool  │
│   Flights ~$320 · 6 nights ~$460     │
│ ▶ Punta Cana, DR             ~$840   │
│ ▶ San Juan, PR               ~$720   │
│ ──────────────────────────────────── │
│ [          Lock my pick          ]   │
└──────────────────────────────────────┘
```

**The card is the ballot.** Each person's submit is their vote. This keeps the
vote counting, the tie-break and the quiet-member tracking that are already
built and tested (`polls.py`): most votes wins, a tie goes to the cheapest
option, and scout announces the result when everyone has submitted.

The group can still settle it in words. "@scout we'd like to go to Cancun" locks
the destination immediately, whatever the ballot says, because an agreement in
the chat beats a half-finished poll.

### Stage 4 — Activities

Everything in this stage is tied to the chosen destination **and its hotel** —
activities at the hotel, or close enough to reach from it.

One **deck card**, around eight activities, shown as a stack to swipe through,
Hinge or Tinder style. Each card is a photo, a name, a price and a line on what
it is. Swipe **left for nah, up for meh, right for yeah** (three buttons do the
same for anyone who'd rather tap). The card has one submit bar at the end.

```
┌──────────────────────────────────────┐
│ Cancun — what are you up for?        │
│ ┌──────────────────────────────────┐ │
│ │ [photo]                          │ │
│ │ Scuba at Cozumel Reef       $120 │ │
│ │ Boat from the hotel dock,        │ │
│ │ gear included.                   │ │
│ └──────────────────────────────────┘ │
│   ( ✕ Nah )    ( – Meh )   ( ♥ Yeah ) │
│ ──────────────────────────────────── │
│ [         Send my picks         ]    │
└──────────────────────────────────────┘
```

**Nothing sends until the submit bar is tapped.** That is a property of the
renderer, not a choice (see §3): a control with a `fieldId` holds its state and
fires nothing. So four people swiping eight activities produces four messages,
not thirty-two.

It is one deck for the whole group, in the group thread, so people can see each
other's picks. That is not Tinder — there is no privacy until a match — but it
suits a friend group arguing about whether to get up for the ruins.

scout stays silent for every submit except the last. When the final person
sends, it posts the tally, best-liked first, naming who said yeah and who said
meh to each. A yeah is worth 2 and a meh 1, so a meh keeps an activity alive
without beating a yeah, and the itinerary schedules the highest scorers.

Built: `send_activity_deck` (`src/scout/trip_actions.py`), `activity_deck.py`
for reading swipes and the tally, and `cards.activity_deck` for the layout. A
card's own submit never reaches scout (Linq flattens it to one character), so
the deck works like the trip interview: Send fills in a text, "@scout my picks:
Night kayak yeah · Food tour nah · Hike meh", and `conversation.py` counts it
in code without a Claude call. A rating left off means yeah and an activity
left out means nah. Instead of silence, each submit before the last gets a 👍
tapback, as plain votes do. Without a Places key, or on a phone without the
card, the deck goes out as a numbered list, answered with
"@scout my picks: 1 yeah, 2 meh, 3 nah".

**The `swipeDeck` node.** The deck needs a layout node HermesShare's renderer
has to draw (our fork adds it; upstream has no swipe component):

```json
{
  "type": "swipeDeck",
  "fieldId": "activities",
  "cards": [{"id": "activity-0", "title": "Scuba", "subtitle": "~$120 · Boat…", "imageUrl": "https://…"}],
  "choices": [
    {"id": "nah", "label": "Nah", "swipeDirection": "left", "systemImage": "xmark"},
    {"id": "meh", "label": "Meh", "swipeDirection": "up", "systemImage": "minus"},
    {"id": "yeah", "label": "Yeah", "swipeDirection": "right", "systemImage": "heart.fill"}
  ]
}
```

It holds one choice id per card, and its text summary, which the Send action
appends after the `lead`, is each card's `title`, a space and its choice id
(`Scuba yeah`), joined with ` · `. A card nobody swiped is left out, which
scout reads as nah. `imageUrl` is optional.

### Stage 5 — Itinerary

Built from the aggregate, not from must-haves. Several events a day,
first and last days kept light for travel, paced by the group's chronotype.
Activities the group scores highest (a yeah is 2, a meh 1) are scheduled;
activities only one person said yeah to are offered as optional add-ons rather
than dropped silently.

Posted as a read-only **itinerary card**, with the text version in the thread
underneath so it is still readable on a phone without HermesShare installed.

Built: `post_itinerary` (`src/scout/trip_actions.py`), `itinerary.py` for the
text version, and `cards.itinerary` for the layout, a table for each day (headed "Monday,
October 5") listing that day's events and when each starts, under a photo of
the destination. The text version is the card's
`fallback_text`, as with the flight card, rather than a second message. The
card needs `GOOGLE_PLACES_API_KEY` for its photo; without it the plan goes out
as text. The agent builds the plan from the activity deck's picks, or from
what people say in the chat when there's no deck, and puts what only one person
picked in the add-ons.

### Stage 6 — Hotel

scout @-mentions the member who added it to the chat — the organizer — and asks
them directly:

> @Maya want to book the room for all four of you? Here's the one from the
> brochure.

A **booking card** carries the hotel, the dates, the guest count, the estimated
total and a button that opens the booking site. scout does not book it. Once
Maya has, she confirms on the card and the amount goes into the ledger as an
expense she paid, split evenly — the same path as any other shared cost
(`log_sender_expense`), so settle-up already understands it.

### Stage 7 — Flight

One flight: the best value Google Flights finds for the whole group from the
shared origin on the shared dates, looked up live through SerpApi. If members
still leave from different cities, the card holds one flight per home city.

The card leads with HermesShare's `flightBoard`, a split-flap departure board
(airport codes, flight number, departure and arrival times, nonstop or the
layovers), then the fare per person, the airline, the flying time and who flies
it. Its button opens the same search on Google Flights, where the group books.

```
┌──────────────────────────────────────┐
│ Flights to San Juan, Puerto Rico     │
│ Mar 14–19 · round trip               │
│ ┌──────────────────────────────────┐ │
│ │ B6 101               1 stop · FLL│ │
│ │ [B][O][S] ──────✈──── [S][J][U]  │ │
│ │ Boston        San Juan, PR       │ │
│ │ DEPARTS 6:15 AM  ARRIVES 2:20 PM │ │
│ └──────────────────────────────────┘ │
│ Fare            $312 per person      │
│ Airline         JetBlue              │
│ Flying time     8h 5m                │
│ For             Maya, Leo            │
│ [       Book from Boston        ]    │
└──────────────────────────────────────┘
```

The fare is live, not an estimate, but it can change before anyone books, and
the card says so. Taps don't reach scout yet, so the booker texts what they
actually paid and it goes into the ledger like any other shared cost.

Built: `send_best_flights` (`src/scout/trip_actions.py`), `flights.py` for the
SerpApi search, `best_flights.py` for the text version, and `cards.best_flights`
for the layout. It needs `SERPAPI_API_KEY`; without it scout sends flight search
links instead.

Right after the flights, scout offers a hotel. `send_best_hotel` posts one card
in the same style: a photo, the hotel's name, its nightly rate and the stay total
for one room of two, its guest rating, and a button that opens the search on
Google Hotels. The hotel is Google Hotels' top-ranked pick that has a room on the
trip dates (`hotels.py`, `best_hotel.py`, `cards.best_hotel`), so it may not be the
cheapest. Without `SERPAPI_API_KEY`, scout sends stay search links instead.

### Stage 8 — Wrap

Two messages, in order:

1. **Calendar.** Everything at once: the trip itself, each day's anchor
   activity, the hotel check-in and the flight. One tap to add.
2. **Album.** A shared album for the trip, as a link. Nobody needs an account.

This is where the calendar now lives. Today it fires the moment the poll closes,
which means it goes out before anyone knows what the trip actually is.

---

## 2. Why these cards and not HTML

The group chat plan said *"iMessage never runs HTML or JavaScript in the chat,
so anything interactive … lives on a page scout hosts."* The first half is still
true and always will be. Apple forbids runtime code execution in an iMessage
extension, so there is no way to put a web app in a bubble and no JavaScript to
write.

HermesShare gets around it the way Scriptable and Widgy do:

> the app ships a **fixed, Apple-signed renderer**, and incoming messages carry
> **declarative JSON** that selects from a known vocabulary of native views.

So a card is data, not code. scout sends a layout tree and the extension draws
real SwiftUI from it. That is better than a hosted page for these four moments —
it stays in the thread, it works offline, and it looks native — and it does not
change the plan's conclusion for anything genuinely web-shaped, like the photo
album, which stays a hosted page behind a link card.

**The cost:** every phone in the group needs HermesShare installed. Without it
the bubble shows `fallback_text` and nothing else. See §6.

---

## 3. How a card comes back

This is the part that constrains the design, so it is worth being precise.

Only three node types accept a `fieldId` and become form inputs: `optionPicker`,
`quickReplyRow` and `seatChart`. `checklist` and `taskList` look right for an
activity deck and are the wrong tool — neither takes a `fieldId`, and both are
device-local by design:

> Checklists, quiz answers, tabs and disclosures maintain local state; they do
> not imply external submission or grading.

With a `fieldId` set, a control renders without its own confirm button and sends
nothing when tapped. The card's single submit bar is the only thing that sends,
and it carries every field at once:

```swift
public struct HermesSubmission: Codable, Equatable, Sendable {
    public let protocolVersion: Int        // wire key "protocol" — always 2
    public let formId: String?             // echoed verbatim from the card
    public let actionId: String            // the tapped action's id
    public let values: [String: [String]]  // fieldId → [selected option ids]
}
```

Fields nobody answered are omitted entirely rather than sent as null.

### One picker per activity, not one checkbox list

`values` is typed as arrays, which looks like multi-select. The renderer's state
store is not:

> `[String: String]`, single-select only. That covers seat / option / chip
> pickers, which is every input the schema has. Multi-select or typed values
> (numbers, dates) would need `[String: [HermesValue]]` and a value enum — add
> it when a node needs it.

So the deck gives **each activity its own `fieldId` with two options**
(`in` / `pass`) rather than one picker listing eight activities. To the person
tapping, it is the same thing. If multi-select ever lands upstream, the deck
collapses into a single picker and the parse path barely changes.

### Parsing it

A submission arrives as an ordinary inbound message. It is handled as a fast
case in `conversation.py`, ahead of the agent, exactly like today's plain-vote
path — scout should never spend a Claude call reading a button press.

**Unverified:** whether the thread receives the raw `HermesSubmission` JSON or a
human-readable summary. `HermesFormState.summary(for:)` joins the selected
labels with ` · `, which suggests the latter, but the submit path was not traced
end to end. Build the parser to accept both: try JSON first, fall back to
matching labels against the card's options the way
`polls.option_in_poll_message` matches a poll option today. **Resolve this with
one real send before writing the parser** (§6).

---

## 4. Sending a card

A card goes out as one Linq message part, alongside the `text` and `link` parts
scout already sends:

```python
{"type": "imessage_app",
 "app": {"name": "HermesShare",
         "team_id": "6PPS68Y9RP",
         "bundle_id": "com.hermesshare.app.MessagesExtension"},
 "url": "data:application/json;base64,<encoded layout>",
 "fallback_text": "Open in HermesShare",
 "interactive": False,
 "layout": {"caption": …, "subcaption": …, "image_url": …}}
```

Three rules that are not negotiable:

- **`interactive: False`.** With it true, "iOS then runs the extension inside
  the bubble … cannot be opened at all."
- **`MAX_URL_CHARS = 16384`** on the encoded payload. Over it, the send is
  refused.
- **An HTTPS thumbnail is required.** No image, no card: *"An HTTPS thumbnail is
  required; card NOT sent."*

Only HTTPS and `data:` URIs are accepted. No custom schemes.

### Where it fits in the pipe

The existing path is unchanged; this adds one action and one part type.

```
src/scout/outgoing.py     a new Card action beside Say, React and Link
  → bridge/scout.ts       a new ScoutAction case
  → bridge/spectrum.ts    perform() dispatches it
  → bridge/linq.ts        sendParts() emits the imessage_app part
  → Linq → the group
```

Per the group chat plan's rule, each iMessage action lands in four parts: the
bridge case, the action type and agent tool in Python, how the console shows it,
and a script that uses it. The console must be able to preview a card — render
the layout tree as text, warn when the payload is over the cap, when the
thumbnail is missing or not HTTPS, and when a `fieldId` has no submit action to
carry it. **Nothing ships that the console can't show.**

---

## 5. What the code needs

Reusing what exists wherever it already works.

| Need | Reuse | Change |
| --- | --- | --- |
| Stages | `TripStage` (`src/scout/trip.py`) | `VOTING` → `CHOOSING_DESTINATION`; add `PICKING_ACTIVITIES`, `BOOKING`, `TRIP_SET` |
| Interview | `Member`, `PreferenceUpdate` (`src/scout/trip.py`) | add `vacation_interest`; `chronotype` is built |
| Ballot | `polls.decide_winner`, `count_votes`, `format_result` | unchanged; a submit becomes a vote |
| Brochure data | `DestinationOption` (`src/scout/trip.py`) | add `hotel`, `amenities`, `photo_url` |
| Activities | — | built: `DeckActivity` and `ActivityDeck` (`src/scout/trip.py`) |
| Bookings | `Expense`, `log_sender_expense` (`src/scout/trip_actions.py`) | new `Booking`, logged as an expense on confirm |
| Hotels and activities | `GooglePlaces.search` (`src/scout/places.py`) | extend `FIELD_MASK` with `rating`, `userRatingCount`, `photos` |
| Flight | `GoogleFlights` (`src/scout/flights.py`), through SerpApi | built: one flight per home city, live fare, `flightBoard` card |
| Calendar | `build_calendar_feed` (`src/scout/calendar_feed.py`) | built: a subscribable feed with one event per itinerary day, linked when the first plan is posted |
| Outgoing | `Say` / `React` / `Link` (`src/scout/outgoing.py`) | add `Card` |
| Bridge | `perform()` (`bridge/spectrum.ts`), `sendParts()` (`bridge/linq.ts`) | add the `imessage_app` part |
| Console | `bridge/devchat/link-card.ts` | a card preview beside the link card preview |

### Where the data comes from

Hotels and activities come from **Google Places API (New)**, which scout already
uses for on-trip recommendations. It returns a real name, rating, price level
and photo, which also solves the mandatory card thumbnail. The PRD's rule holds:
scout never invents a place.

`FIELD_MASK` in `places.py` is deliberately minimal because *"Google bills by
the fields requested."* Adding `rating`, `userRatingCount` and `photos` raises
the per-search cost — worth knowing before turning it on with a budget alert set.

Flights come from **Google Flights through SerpApi**, live, one search per home
city. Whole-trip totals on the brochures are still **Claude estimates, labeled
as estimates**, because they're shown before a destination or dates exist to
search.

---

## 6. Risks and open questions

| Risk | Mitigation |
| --- | --- |
| **Every demo phone must have HermesShare installed**, or cards show only their fallback text. | Sideload `docs/install/HermesShare.ipa` on each demo phone during setup, and check it the morning of. Write every card's `fallback_text` so the thread still makes sense without it. |
| **Public HTTPS hosting is now required, not deferred.** Card thumbnails will not send without it. | This was already open in three docs. It is now a blocker: decide between a tunnel from the demo Mac and a separate host, and do it before any card work. |
| **Google Places photo URLs carry the API key**, so they cannot go in a payload that lands on phones. | scout's host proxies and caches the photos, serving its own HTTPS URLs. Folds into the hosting decision above. |
| **Unverified: what a submit actually puts in the thread.** | One real send to a real group, before the parser is written. Parse both shapes until it is known. |
| **Unverified: whether Linq's free line accepts `imessage_app` parts.** | Sits with the existing "what does the free line support" question. Test it on the demo line early. |
| **The deck could exceed the 16,384-char cap.** | Measure the eight-activity deck. Photos are URLs, not data, so there is headroom, but trim descriptions if not. |
| Someone taps through the deck and never hits send. | scout names who it is still waiting on, the same way it chases missing preferences. |
| Cards make scout feel like an app, and the group stops talking to it in words. | Every card has a text equivalent, and every decision a card makes can be made by saying it instead. |

---

## Build order

Each step is demoable on its own, and the first one unblocks the rest.

1. **Prove the pipe.** Clone HermesShare, send one hand-written card to a real
   Linq group, submit it, and record what comes back. Answers three of the
   open questions above.
2. **Hosting**, since nothing can be sent without a thumbnail URL.
3. **The `Card` action** end to end: Python action, bridge part, console
   preview, one script.
4. **The brochure card**, reusing the poll engine underneath.
5. **The activity deck**, and the aggregate.
6. **Itinerary, bookings, calendar and album**, in flow order.
