# Demo script: "spring break, finally"

A five-minute walkthrough of every key scout feature, told as one group chat. Use it as the live demo, as the storyboard for a screen recording, or as the spec for a console script.

**The cast** (four friends, deliberately different so scout has real tradeoffs to handle):

| Who | Home | Budget | Vibe |
| --- | --- | --- | --- |
| Maya | Boston | ~$800 | the organizer, needs a beach |
| Leo | NYC | $600 | cheap, wants scuba, night owl |
| Priya | Chicago | $700 | food person, shares by voice note |
| Jordan | Austin | $900 | quiet, early riser, pays for things |

**The arc** (each beat maps to a feature, so you can cut it short at any point):

1. Scout stays quiet, then joins and sends the trip card → *speak gate, introduction, interview card*
2. Preferences via the trip card, plain words and a voice note → *trip interview card, extraction, 👍 confirmation, who hasn't answered*
3. Summary and the destination vote → *date overlap, poll, votes by number and tapback*
4. Activities and a plan → *activity deck, picks counted, itinerary paced to chronotype, solo picks as add-ons*
5. Booking and calendar → *booking links, best flights, calendar link*
6. On the trip → *nearby places, directions, a photo of a receipt, splitting costs, settling up*

Legend: `👍` is a tapback, `↪` is a threaded reply, `📷`/`🎤` are media, and `[card]` is a rich link card.

---

## Act 1: friends talk, scout listens, then scout joins with the trip card

> Shows: scout is in the chat but isn't annoying (the trust-building beat, so don't skip it), and the **trip interview card** it sends the moment it introduces itself.

```
maya:    omg can't believe it's already october
leo:     lol the semester is cooked
priya:   we NEED a trip
                                                     (scout stays quiet)
jordan:  ok but where though
                                                     (scout stays quiet)
maya:    @scout hey, you there?
scout:   hey all, i'm scout 👋 i'll help turn this chat into an actual trip.
scout:   [card: "Let's plan your trip", "A few taps, then send"]
           Trip vibe       [All-inclusive resort] [Lakeside] [City break] [Other…]
           When            (calendar: first and last day)
           Budget / person ($0 ──●────── $3,000 slider)
           Flying from     [City or airport, e.g. Boston]
           What are you into?  ☐ Clubs and nightlife  ☐ Early riser  ☐ Hiking and outdoors
                               ☐ Food and culture  ☐ Beach and chill  ☐ Adventure sports
                               ☐ Wellness and spa  ☐ Shopping and markets
           [ ✈ Send my answers ]
```

**Say out loud:** "It didn't jump in on the first four messages. It only speaks when tagged or when the chat is clearly asking it something. And it doesn't interrogate anyone: one card, a few taps."

**Detail worth knowing:** the intro is deliberately one short bubble, and the card goes out only with that introduction, never again. Scout never asks anyone's name, since iMessage doesn't give it one. It calls people whatever the chat calls them.

## Act 2: everyone shares (the card, plain words, a voice note)

> Shows: three ways to give the same info, all landing in the same saved trip. Scout confirms with a 👍 instead of a wall of text, tracks who's missing, and takes what friends say for each other.

Tapping **Send my answers** can't send anything back to scout directly, so the card fills the message box with a text, which the person sends. That text is what scout reads:

```
maya:    @scout my trip: Lakeside · Mar 14 – Mar 20, 2027 · $800 · from Boston · Beach and chill, Food and culture
scout:   👍
leo:     @scout my trip: City break · Mar 14 – Mar 22, 2027 · $600 · from New York · Adventure sports, Clubs and nightlife
scout:   👍                                          (and Leo is now a night owl)
priya:   🎤 (voice note: "hey scout, priya here, i can do march 14 to 21, around seven
         hundred, flying out of chicago, and honestly i just want amazing food")
scout:   👍
maya:    jordan's flying from austin, has like $900 and is an early riser
scout:   got jordan down for austin, ~$900 and early riser. jordan, still need your
         exact dates, mar 14-20 right?
jordan:  yep mar 14-20
scout:   👍
```

**Features hit:**
- **The trip card** gives exact dates (a real calendar, not "sometime in March"), a budget as a number, a home city, a trip kind, and interests, in one Send. Scout saves the dates and budget directly and treats the trip kind and each interest as must-haves.
- **Interests do double duty.** "Clubs and nightlife" makes Leo a night owl and "Early riser" makes Jordan an early bird, which paces the itinerary in Act 4.
- **Plain words still work**, for the friend who ignores the card.
- **A voice note** that says "scout" counts as a tag, and its transcript gets saved.
- **A friend answering for someone else**: scout saves it and asks the rest.
- **The 👍** confirms each member's own details. Scout only writes text when something is unclear or when it saved details for someone else.

**Demo tip:** let one person (Maya) use the card, since the card is the visual wow, and have the others use words and a voice note to show it's flexible.

## Act 3: the summary and the vote

> Shows: the group-level reasoning that no individual could do alone.

```
leo:     ok so where do we even go
scout:   here's where you stand 📋
         - dates: everyone's free **mar 14-20** (7 nights)
         - budget: $600-$900 each, so i'm aiming around $600-700 to keep leo in
         - flying from: boston, nyc, chicago, austin
         - vibe: beach, food, scuba, early mornings and late nights
         [brochure card] 1. San Juan, Puerto Rico, a historic old town, great food, snorkel and dive spots
         [brochure card] 2. Tulum, Mexico, beaches and cenotes, a bit pricier on flights
         [brochure card] 3. Key West, Florida, diving, easy flights, short trip
         vote by tapping send on a card, or reply with a number.

maya:    2
scout:   👍
leo:     tulum looks sick but flights from nyc 😬
scout:   fair, here's the real number: Tulum comes to about $780 each from NYC,
         $540 for San Juan. San Juan fits your $600 cap.
leo:     ok 1 then
priya:   👍 on "1. San Juan"
                                                     (scout replies ↪ in a thread: "2 of 4 voted")
jordan:  1
scout:   San Juan, Puerto Rico wins 🎉 (3 votes to 1). dates locked: mar 14-20, 2027.
         [card] Add it to your calendar
```

**Features hit:** date overlap and budget range, three tappable brochures with photo, hotel and total cost, votes by number and by tapback, scout answering a side question with real numbers, then announcing the winner and a calendar link.

## Act 4: what do we actually do there?

> Shows: group preferences turning into a plan, paced to the people in it.

```
maya:    @scout what should we do while we're there?
scout:   [activity deck] 1. old san juan food tour ($65)  2. night snorkel in bioluminescent bay ($70)
         3. scuba day trip to the reefs ($140)  4. el yunque rainforest hike ($40)
         5. beach club day ($55)  6. sunrise kayak ($50)
         tick what you're up for, or reply "@scout my picks: 1, 2".

maya:    @scout my picks: 1, 2, 5
scout:   👍
leo:     @scout my picks: 2, 3
priya:   @scout my picks: 1, 2
jordan:  @scout my picks: 4, 6
scout:   everyone's picks are in. the group agreed on **#2 bioluminescent bay**,
         and 1 and 3 each have two takers.

priya:   @scout can you make us a plan?
scout:   here's the plan 🗓
         day 1 (arrive): check in, easy dinner in old san juan
         day 2: food tour, beach club, bioluminescent bay at night
         ...
         the group is split between night owls and an early bird, so mornings start
         at 10 and nights run late. jordan, your sunrise kayak and el yunque hike are
         add-ons you can do solo while everyone sleeps in. leo, the scuba day trip is
         an add-on too, since nobody else wanted it.
```

**Features hit:** the activity deck with prices, picks counted in code (no AI needed), consensus versus solo picks, and an itinerary paced to chronotype with solo picks offered as add-ons instead of forced on everyone.

## Act 5: make it real (scout never books anything)

```
maya:    @scout how do we actually book this?
scout:   i don't book or touch money, but here's everything pre-searched:
         [card] Airbnb for 4, mar 14-20 (about $210 each)
         flights, cheapest good option from each city:
         - boston: $182 (1 stop)  - nyc: $164 (nonstop)  - chicago: $247  - austin: $289
         [card] Google Flights links for each of you
jordan:  nice, i'll grab the airbnb
```

**Features hit:** one lodging link for the group, live per-city flight prices, and honest "you book, i find" framing.

## Act 6: on the trip, scout becomes the group's accountant

> Shows: the part that people hate most about group trips.

```
leo:     @scout is there good coffee near the airbnb
scout:   three within a 10 minute walk: 1. Café Cuatro Sombras (4.7)  2. Hacienda ... 3. ...
leo:     2
scout:   [card] directions to Hacienda

jordan:  @scout i got the airbnb, $1,260
scout:   logged: jordan paid $1,260 for the airbnb, split 4 ways ($315 each)
maya:    📷 (a photo of a restaurant receipt)
scout:   i read it: pizzeria, 4 items, subtotal $86, tax $7.40, tip $17.20.
         is this one you paid for, maya? reply yes to log it
maya:    yes. leo only had the water and the flan though
scout:   got it: tax and tip are shared by what each person had.
leo:     @scout the kayak rental was just jordan and me, $60, jordan paid
scout:   logged: $60 split between jordan and leo only.

maya:    @scout who owes what
scout:   settle up 💸 (fewest payments)
         - leo pays jordan $148
         - priya pays jordan $121
         - maya pays jordan $92
leo:     @scout i paid jordan
scout:   ✅ checked off. two payments left.
priya:   @scout trip report?
scout:   [report cards] total $2,310, per person, by category, and who's settled.
```

**Features hit:** nearby places and directions, expenses split among everyone or only some people, itemized receipt reading with tax and tip shared by what each person had, the fewest payments to settle up, per-payment check-offs, and the end-of-trip report.

---

## Making the demo land

- **Open on the problem, not the product.** Start by showing a real dead group chat ("we should go somewhere" with 40 hearts), then add scout.
- **Keep the three "wow" beats in view:** scout staying quiet (Act 1), the trip card (or a voice note) turning into saved preferences (Act 2), and the receipt photo splitting by who ate what (Act 6).
- **Tell people early that it never books or moves money.** That answers the trust question before anyone asks it.
- **Cut for time:** a two-minute version is Acts 1, 3 and 6 (quiet, vote, settle up).

## Running it

Claude's wording changes every run, so the dialogue above is the storyboard, not a recording. Check the trip's state, not exact replies.

| Goal | How |
| --- | --- |
| Rehearse without phones | `cd bridge && bun run dev`, then `bun run devchat start maya leo priya jordan` and `bun run devchat say <name> "<message>"` |
| Skip ahead to a later act | `bun run devchat start maya leo priya jordan --from poll-open` (Act 3) or `--from destination-chosen` (Acts 4 to 6) |
| Replay the whole thing | the console script below, run with `bun run devchat run <file>` |
| Live demo in a real group | follow [DEVELOPING.md](DEVELOPING.md). Linq sends real iMessages, so rehearse in the console first |

Needs: `ANTHROPIC_API_KEY` for the AI, `OPENAI_API_KEY` for the voice note and receipt photo (Mac only), `SERPAPI_API_KEY` for live flights and `GOOGLE_PLACES_API_KEY` for photos and nearby places. Without the last two, scout falls back to search links and text.

### Console script version

Not yet checked into `bridge/e2e/`, because it's long and untested against real Claude. Check the state values against `bun run devchat state` before relying on them.

```
members maya leo priya jordan

leo: lol the semester is cooked
expect scout quiet
maya: @scout hey, you there?
expect scout ~ "i'm scout"
maya: @scout my trip: Lakeside · Mar 14 – Mar 20, 2027 · $800 · from Boston · Beach and chill, Food and culture
expect scout reacted like
expect state members.0.budget_usd = 800
leo: @scout my trip: City break · Mar 14 – Mar 22, 2027 · $600 · from New York · Adventure sports, Clubs and nightlife
priya: priya here, mar 14-21, 700, flying from chicago, want amazing food
jordan: jordan, mar 14-20, 900, austin, early bird
maya: @scout where should we go?
expect state stage = "voting"
maya: 1
leo: 1
priya: 1
expect state destination ~ "San Juan"
maya: @scout what should we do while we're there?
expect state activity_deck.activities ~ "name"
maya: @scout my picks: 1, 2
leo: @scout my picks: 2, 3
priya: @scout my picks: 1, 2
jordan: @scout my picks: 4
priya: @scout can you make us a plan?
expect state itinerary ~ "2027-03-14"
jordan: @scout i got the airbnb, $1,260
maya: @scout who owes what
expect scout ~ "jordan"
leo: @scout i paid jordan
expect scout ~ "paid"
```
