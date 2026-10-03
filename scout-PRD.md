# scout: Product Requirements Document

| | |
|---|---|
| **Product** | scout, an AI trip and outing planner that lives in group chats |
| **Status** | Draft |
| **Context** | Class / hackathon project |
| **Last updated** | October 2026 |
| **Owner** | [Your name] |
| **Interactive journey** | [scout user journey](https://claude.ai/artifact/F2mTb9DJeGZR4mq2bFLFEu) (private until you share it) |

---

## 1. Summary

scout is an AI agent that plans group outings and trips from inside the group chat itself. Anyone can add its phone number to an existing text thread, so there's no app to download and no one has to sign up for anything. The flagship use case is a friend group planning spring break: instead of a chaotic thread where ideas get buried and no one commits, scout collects each person's constraints (dates, budget, home city, must-dos), suggests destinations and day-by-day itineraries, runs polls so the group can vote, and keeps a running summary of what's been decided. Once the group decides, it texts a link that puts the trip on everyone's Google Calendar in one tap. During the trip it handles in-the-moment requests like "find us a cozy taco spot with outdoor seating nearby" and sends directions once the group picks. Once money starts moving, it tracks who paid for what (members can just text a photo of the receipt), splits shared costs, tells everyone who owes whom, and settles each payment in the chat ("@scout pay Leo") over a sandbox bank, Capital One's Nessie API. It also creates a shared trip album, adds everyone in the group, and collects the photos people take along the way.

## 2. Problem

Group plans die in the group chat. Planning a trip with friends usually means hundreds of messages, ideas that get buried, people who never answer, and no single person willing to force a decision. The person who does step up becomes the unpaid travel agent and the one who has to chase everyone for money afterward.

Existing tools don't fix this because they live outside the conversation. Travel apps, shared docs, poll apps, and expense splitters each require everyone to download something, create an account, and remember to check it. Most friend groups never get everyone onboarded, so the plan stays in the chat, unstructured.

## 3. Goals and non-goals

### Goals

| Goal | What it means in practice |
|---|---|
| Turn group chat discussion into decisions | A group that adds scout ends up with a chosen destination, dates, and a plan, without one person doing all the coordination. |
| Zero onboarding | Adding a phone number to the thread is the entire setup. No app, no accounts, works on any phone. |
| Stay useful during the trip | Answer vibe-based "where should we go right now" questions with nearby options and directions. |
| Make money less awkward | Log shared expenses from normal messages and settle up with the fewest possible payments, paid right from the chat. |
| Keep the trip's photos together | One shared album with everyone in it, so photos don't stay scattered across camera rolls. |

### Non-goals

scout does **not** book flights, lodging, or reservations, and it never holds or moves real money. It recommends, organizes, and links out; the group books through the services they already use. To show settling up end to end, scout pays members back over Capital One's Nessie API, a sandbox bank whose customers, accounts, and balances are all fake. Nessie is a demo payment rail, not a real one: every payment message says it's sandbox money, and taking scout to real users would mean swapping in a real rail (or going back to payment-app links) and taking on the liability that comes with it. This keeps the scope demoable and avoids payment and booking liability. scout is also not a general-purpose chatbot: it stays focused on the group's plans.

## 4. Target users

The core user is **any friend group** coordinating a shared plan over group text, from a week-long spring break to a Saturday dinner. Within a group, members tend to play recognizable roles, and scout should serve each of them.

| Role | Example from the journey | What they need from scout |
|---|---|---|
| The organizer | Maya, who adds scout to the chat | Plans that actually happen without being the one who nags everyone |
| The constrained member | Leo, who can only do certain dates and needs a beach | Confidence that their constraints are heard and respected |
| The opinionated voter | Priya, who wants Tulum | A fair, transparent way to decide, even when they don't win |
| The money-anxious member | Jordan, "scared to ask" who owes what | Clear numbers and a painless way to settle up |
| The quiet member | Anyone who rarely replies | A gentle nudge so their input still counts |

## 5. User journey

The core journey follows one group from "we should go somewhere" to "everyone's paid up." The interactive version linked above plays out each step as a sample conversation.

| Step | What the group does | What scout does |
|---|---|---|
| 1. Add scout | A member adds scout's number to the existing group text. | Introduces itself and asks everyone for dates, budget, home city, and one must-have. |
| 2. Share preferences | Members reply casually ("mar 13–20, ~$800, flying from boston"). | Extracts constraints, finds the date overlap, and posts a summary of where everyone landed. |
| 3. Vote on a destination | Members vote on the options. | Suggests 3 destinations that fit everyone's dates and budget, runs the poll, announces the result, and breaks ties with cost or fit. Texts a link to add the trip to Google Calendar. |
| 4. Get the itinerary | A member asks for a plan ("not too packed pls"). | Builds a day-by-day itinerary around the group's must-haves and sends booking links for flights and lodging. Creates a shared trip album and texts everyone the link. |
| 5. Explore on the trip | A member asks for a vibe ("cozy, outdoor seating, not touristy"). Members add photos as the trip goes. | Returns 3 nearby options with walking time and price level, then sends directions once the group picks. Adds photos members upload or text to it into the album. |
| 6. Settle up | Members mention what they paid ("I paid the airbnb, $1,240") or text a photo of the receipt. | Reads receipts, logs each expense, calculates the fewest payments to settle up, pays each one over the Nessie sandbox when the payer says "@scout pay Leo", and shows who still owes. Reminds everyone to add their last photos to the album. |

scout also works for smaller plans with the same building blocks: a birthday dinner for eight, tacos before a concert, a ski weekend, or splitting a cabin rental.

## 6. Functional requirements

Priorities: **P0** is required for the demo, **P1** is a stretch goal, and **P2** is future work.

### 6.1 Group chat presence

| ID | Requirement | Priority |
|---|---|---|
| GC-1 | Users can add scout to an existing group text by adding its phone number (a Linq line). No app or account is required for anyone. | P0 |
| GC-2 | On joining, scout sends one short introduction that explains what it does and asks for each person's name, dates, budget, home city, and one must-have. iMessage only gives scout phone numbers, so it has to ask for names. Without a "member joined" event, scout treats the first message it sees in a chat as joining. | P0 |
| GC-3 | scout responds when tagged with "@scout" or addressed by name. | P0 |
| GC-4 | scout attributes each message to the right group member by phone number and learns display names from context. | P0 |
| GC-5 | Any member can pause or remove scout with a plain command ("@scout pause"). | P1 |
| GC-6 | Members can text scout privately to share constraints they don't want in the group, such as a hard budget cap. | P2 |

### 6.2 Preference collection

| ID | Requirement | Priority |
|---|---|---|
| PR-1 | Extract dates, budget, departure city, and must-haves from free-form messages, including casual phrasing and typos. | P0 |
| PR-2 | Compute the date window that works for everyone and the group's budget range, and post a short summary. | P0 |
| PR-3 | Nudge members who haven't shared preferences after a set period. | P1 |
| PR-4 | Let members update their preferences at any time and refresh the summary. | P1 |

### 6.3 Destination suggestions and polls

| ID | Requirement | Priority |
|---|---|---|
| DS-1 | Suggest 3 destinations that fit the shared dates, budget, and must-haves, each with an estimated per-person cost and a one-line reason. | P0 |
| DS-2 | Run a poll in the thread. Over SMS, members vote by replying with a number or the option name. | P0 |
| DS-3 | Announce the winner when everyone has voted or the poll closes. On a tie, recommend one option and explain why (for example, lower cost). | P0 |
| DS-4 | Reuse the same poll flow for any group decision, such as restaurants or activities. | P1 |

### 6.4 Itinerary and booking links

| ID | Requirement | Priority |
|---|---|---|
| IT-1 | Generate a day-by-day itinerary with one anchor activity per day, respecting must-haves and the group's requested pace. | P0 |
| IT-2 | Send booking links for flights from each member's home city and for lodging that fits the group size and budget. scout never books on the group's behalf. | P0 |
| IT-3 | Edit the itinerary on request ("swap Tuesday and Wednesday"). | P1 |
| IT-4 | Keep a trip summary (destination, dates, plan, bookings) that any member can request with "@scout summary." | P1 |

### 6.5 On-trip discovery

| ID | Requirement | Priority |
|---|---|---|
| OT-1 | Turn vibe-based requests into 3 nearby options, each with walking or driving time, price level, and a short description. | P0 |
| OT-2 | Determine location from a place the group names ("near our Airbnb"), the lodging address on file, or a location a member shares. | P0 |
| OT-3 | Send a directions link once the group picks a spot. | P0 |
| OT-4 | Account for opening hours and group size when recommending. | P1 |

### 6.6 Cost splitting

| ID | Requirement | Priority |
|---|---|---|
| CS-1 | Log expenses from natural messages ("dinner was me, $164") and confirm each one so mistakes get caught early. | P0 |
| CS-2 | Split shared costs evenly and calculate the fewest payments needed to settle up. | P0 |
| CS-3 | Members settle a payment from the chat ("@scout pay Leo"). scout moves the amount between their Capital One Nessie sandbox accounts, which it opens for each member on their first payment, and confirms with "Paid ✓". Every confirmation says it's sandbox money. If Nessie is unreachable, scout records the payment anyway and labels it simulated. | P0 |
| CS-4 | Mark a payment as done as soon as it goes through, and list the payments still left (and who owes them) after each one and whenever someone asks. Scheduled reminders come later. | P1 |
| CS-5 | Support uneven splits, such as an activity only some members joined. | P1 |
| CS-6 | Show a running balance on request. | P1 |
| CS-7 | Members can text a photo of a receipt (in the group or directly to scout). scout reads the merchant, date, and total, asks who it should be split among, and logs it once the payer confirms. Blurry or unclear receipts prompt a request for the total instead of a guess. | P0 |
| CS-8 | Split a receipt by item when members ordered different things ("I had the mofongo and a margarita"), dividing tax and tip proportionally. | P1 |
| CS-9 | Keep each receipt attached to its expense so anyone can view it when checking the balance. | P1 |
| CS-10 | Convert receipts in other currencies (for example, pesos on a Tulum trip) into the group's home currency. | P2 |

### 6.7 Shared trip album

| ID | Requirement | Priority |
|---|---|---|
| AL-1 | When the destination is locked in, or when a member asks ("@scout make an album"), create a shared album for the trip and add every group member by texting them the link. Nobody needs an account to view or add photos. | P0 |
| AL-2 | Members can add photos by uploading through the album link or by texting photos directly to scout. | P0 |
| AL-3 | If the group opts in, photos sent in the group thread during the trip dates are added to the album automatically. Receipts are recognized and routed to cost-splitting instead of the album. Any member can remove a photo they added. | P1 |
| AL-4 | Anyone who joins the group text later is added to the album automatically. | P1 |
| AL-5 | After the trip, remind everyone to add their photos, and let any member download the full album. | P1 |
| AL-6 | Organize photos by itinerary day so the album reads like the trip. | P2 |
| AL-7 | Let members save the album into their own photo library (for example, Google Photos or iCloud Photos). | P2 |

### 6.8 Google Calendar

scout puts the plan on people's calendars before it ever reads them. The first requirements use plain "Add to Google Calendar" links, which need no sign-in and keep the zero-onboarding promise. Reading calendars comes later, and only for members who choose to connect.

| ID | Requirement | Priority |
|---|---|---|
| CAL-1 | When the destination and dates are locked in, text one "Add to Google Calendar" link for the trip: an all-day event across the shared dates, with the destination as the location and the trip summary as the description. Tapping it opens Google Calendar with the event filled in. Nobody signs in, and scout stores nothing. | P0 |
| CAL-2 | Send a standard calendar file (.ics) with the link so members on Apple Calendar or Outlook can add the trip too. Most iMessage users are on iPhone, and many use Apple Calendar rather than Google. | P1 |
| CAL-3 | Once the itinerary exists, send it as one calendar file with an event for each day's anchor activity. Members can also ask for a single day ("@scout add Tuesday to my calendar"). One file per trip keeps the thread from filling with links. | P1 |
| CAL-4 | When the dates or itinerary change (IT-3), text an updated link and say what changed. A link can't edit an event someone already added, so scout tells them to remove the old one. | P1 |
| CAL-5 | Members can optionally connect Google Calendar through a sign-in link that scout texts them privately. scout asks only for free/busy access: it sees when someone is busy, never event names, attendees, or locations. Members can disconnect at any time, which deletes scout's access. | P2 |
| CAL-6 | For connected members, scout finds their free dates in the trip's rough timeframe and asks them to confirm instead of typing dates. Members who don't connect share dates by text as before. Connecting is never required. | P2 |

## 7. Interaction model

The biggest open design question is when scout should speak. A group chat agent that talks too much gets muted or removed; one that talks too little doesn't move the plan forward.

**Decision (October 2026): scout reads every message and speaks only when it's useful.** It always replies when tagged or addressed by name. While collecting preferences, it saves details people share without tagging it and confirms each in one line, asking only for what's still missing. While a poll is open, it counts plain votes like "2" or "Tulum" without being tagged. Everything else (chatter, side conversations) gets no reply. It also speaks unprompted at a few moments where the group clearly benefits: after everyone has shared preferences, when a poll closes, and later for payment reminders. A daily cap on proactive messages and a pause command (GC-5) are still planned. Validate this with real groups and loosen or tighten it based on how often groups pause or remove scout.

## 8. Conversation design

scout's messages are read on phones, often in a busy thread, so every message should be short, scannable, and clearly actionable. It writes in a friendly, plain tone that matches how friends text, uses emoji sparingly, and avoids lecturing. It always confirms what it understood or logged ("Got it: Airbnb, $1,240, paid by Leo") so the group can correct it. It never implies it booked something, it labels prices as estimates, and every payment it confirms is labeled as Nessie sandbox money.

Because SMS has no rich cards or buttons, structured content (summaries, polls, itineraries, settle-up lists) should be formatted as short numbered or line-by-line text that reads well in any messaging app. Long content should be split into a few messages rather than one wall of text.

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| Speed | Simple replies arrive within about 10 seconds; itineraries and suggestions within about 30 seconds, with a short "working on it" message if longer. |
| Accuracy | Places come only from a maps or places data source, never invented. Prices are labeled as estimates. |
| Privacy | scout tells the group what it reads and stores when it joins, stores only trip-relevant information, and deletes trip data on request or after a set period once the trip ends. Calendar access is opt-in, read-only, and limited to free/busy times. Calendar tokens are deleted when a member disconnects or the trip data is deleted. |
| Compatibility | Works on iPhone and Android in standard group texts. |
| Reliability | Every logged expense and vote is persisted, so nothing is lost if a message fails or the service restarts. |

## 10. Technical approach (hackathon scope)

| Component | Proposed approach | Notes |
|---|---|---|
| Messaging | iMessage through [Photon](https://photon.codes)'s Spectrum SDK (`spectrum-ts`). Group chats run on a [Linq](https://linqapp.com) line, plugged into Spectrum as a custom platform. | Photon's cheaper plans use shared numbers that can't join group chats, and Business costs $250 per number per month. A Linq line is a real iMessage number that members add to their group, with no Apple ID needed. On Linq's free line, every member texts scout privately once first. See [scout-imessage-groups.md](scout-imessage-groups.md). |
| Agent | Claude Opus 5.5 via the Anthropic API, with tool calling | Claude handles language: extracting preferences, deciding when to speak, suggesting destinations. Plain code handles the rules: date overlap, budget range, vote counting, tie-breaks. |
| Places and directions | [Google Places API (New)](https://developers.google.com/maps/documentation/places/web-service/text-search) Text Search, and Google Maps directions links | Text Search takes a free-text request ("cozy tacos with outdoor seating"), which fits a vibe better than category filters, and returns each place's name, location, price level, and a short summary. scout first finds the place the group names ("near our Airbnb in Condado"), then searches near it. Walking and driving times are estimated from straight-line distance and labeled as estimates, which avoids a second, routing API. Directions links (`google.com/maps/dir/?api=1`) need no API and open with the member's own location as the start. Needs a Google Cloud key with billing on; without one, scout says recommendations aren't set up rather than inventing places. |
| Travel prices | Flight and lodging search APIs, or cached estimates for the demo | Estimates are acceptable for the demo if clearly labeled. |
| Payments | [Capital One's Nessie API](https://api.nessieisreal.com), a sandbox bank, as a demo payment rail | HTTPS only, with the API key as a `?key=` query parameter. Each member gets a Nessie customer and checking account with a starting sandbox balance. Nessie's transfer endpoint has no payee field, so a payment is a withdrawal from the payer's account plus a deposit into the payee's. Nessie amounts are whole dollars, so scout's own ledger keeps exact cents and stays the source of truth for who owes whom. Calls time out after a few seconds; if the key is missing or a call fails, the payment is recorded and labeled simulated. Nessie's enterprise endpoints show every team's data to anyone with a key, so scout sends it no names or phone numbers. |
| Photo album | A scout-hosted web album backed by file storage, shared through a private link | Hosting the album keeps it account-free and works the same on iPhone and Android. Google retired its Photos API method for sharing albums in March 2025, and Apple doesn't offer a public API for iCloud Shared Albums, so building on either is unreliable. Photos texted to scout arrive as MMS attachments through the messaging provider. |
| Calendar | "Add to Google Calendar" links (`calendar.google.com/calendar/render?action=TEMPLATE`) and .ics files at first. Later, the Google Calendar API's `freebusy.query` with the `calendar.freebusy` scope, behind a scout-hosted Google sign-in page | Links and .ics files need no API, credentials, or Google review. For an all-day trip, the link's end date is the day after the last day. Calendar scopes count as sensitive, so reading calendars beyond a small test group needs Google's OAuth app verification. |
| Receipt reading | The same vision-capable language model reads receipt photos | The bridge forwards photos to the Python service along with the text. The model extracts merchant, date, total, and line items, and tells receipts apart from trip photos. Every extracted total is confirmed in the chat before it's logged. |
| Storage | SQLite | Stores trips, members, preferences, polls, itineraries, expenses, payments, and the recent chat. |
| Polls | Numbered text replies ("1", "2", "3") | Plain-number replies work on every line and for members on SMS. Linq reports native iMessage poll votes as webhook events, so native polls are possible later (untested). |

### Architecture

Photon can only send messages from its TypeScript SDK, but scout's logic is written in Python. A small TypeScript **bridge** (`bridge/`) receives each text through Photon's SDK (from the Linq line, for group chats), posts it to scout's **Python service** (`src/scout/`) on the same machine, and sends back whatever scout replies. The bridge handles one message at a time, so scout always finishes one reply before reading the next. That way two votes can never race to close the same poll.

### Core data model

| Entity | Key fields |
|---|---|
| Trip | Group thread ID, destination, dates, status |
| Member | Phone number, display name, home city, Nessie account ID (opened on the member's first payment) |
| Preference | Member, available dates, budget, must-haves |
| Poll | Question, options, votes by member, result |
| Itinerary day | Date, anchor activity, notes |
| Expense | Payer, amount in cents, description, who it's split among, receipt image (optional) |
| Receipt line item | Expense, item, price, who it belongs to |
| Settlement | From, to, amount in cents, Nessie withdrawal and deposit IDs (empty when simulated). A settlement exists only once it's paid; what's still owed is worked out from expenses and settlements. |
| Album | Trip, private share link, auto-add setting |
| Photo | Album, uploader, timestamp, itinerary day |
| Place suggestion | Trip, number in the list, name, Google place ID, location. Only the latest three are kept, until the group picks one. |
| Calendar connection | Member, Google account, encrypted refresh token, connected at (P2, only for members who connect) |

### Settle-up logic

scout computes each member's net balance (what they paid minus their share), then repeatedly matches the member who owes the most with the member who is owed the most until everyone is at zero. This produces at most one fewer payment than the number of members. In the sample journey, $1,600 of shared costs split four ways is $400 each. Leo paid $1,240 and is owed $840, so Jordan pays Leo $400, Priya pays Leo $236, and Maya pays Leo $204.

Payments already made count toward each balance, so after Maya pays, the plan shows only Jordan's and Priya's payments. When a share doesn't divide evenly, the leftover cents go to the first few members so the shares add up to the exact total.

## 11. Success metrics

For the hackathon, success means the full journey runs end to end in a real group text during the demo: adding scout, collecting preferences, a live vote, an itinerary, an on-the-spot recommendation, and a settle-up.

If the project continues beyond the demo, these metrics would show whether scout is working:

| Metric | Why it matters |
|---|---|
| Share of groups that reach a decision within 48 hours of adding scout | Measures the core promise: chat turns into plans. |
| Messages from first mention to decision, compared with groups not using scout | Shows whether it actually cuts the back-and-forth. |
| Share of logged expenses settled within 7 days of the trip ending | Measures the cost-splitting value. |
| Share of trips where most members add photos to the album | Shows whether the album becomes the group's real photo home. |
| Share of groups that use scout again for another plan | Indicates real, repeat value. |
| Share of groups that pause or remove scout | Flags when it's too noisy or not useful. |

## 12. Scope and milestones

| Phase | Scope | Outcome |
|---|---|---|
| 1. Core loop (built, not yet tested in a real group) | GC-1 to GC-4, PR-1 and PR-2, DS-1 to DS-3 | scout joins a group text, gathers preferences, and runs a destination vote. |
| 2. Full journey | IT-1 and IT-2, OT-1 to OT-3, CS-1 to CS-4, CS-7, AL-1 and AL-2, CAL-1 | The complete six-step journey works end to end. |
| 3. Polish and demo | Selected P1 items, demo script, fallback plan | A reliable live demo plus the interactive journey as backup. |

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Photon's shared-number plans (Free and Pro) can't join group chats. | Run group chats on a Linq line plugged into Photon's Spectrum SDK, and test it in a real group on day one. Keep a fallback demo (1:1 texting, `scout-simulate`, or the interactive journey page) ready. |
| Linq's free line takes only 20 contacts, and each must text scout privately first. A demo phone that skipped this can't reach scout. | Add every demo phone and have each text scout days before the demo. Each teammate develops on their own line. |
| Apple flags scout's number for automated messaging. | Follow Photon's deliverability guidance: people message scout first, no cold outreach, no message bursts, and stay well under Linq's rate limits. |
| On lines that can't list a group's members (Photon's shared lines and local mode), people who never text are invisible to scout. Linq lists them. | Ask everyone to reply to the introduction. The agent only posts the summary once the people it knows about have all shared, and anyone can ask for it with "@scout summary." |
| scout becomes noisy or annoying. | Tag-first interaction model, a daily cap on proactive messages, and a pause command. |
| Suggestions include made-up places or wrong prices. | Pull places only from a data source and label all prices as estimates. |
| The Places API key is missing, over quota, or unreachable during the demo. | Set a budget alert on the Google Cloud project, test the key before going on stage, and keep a rehearsed `scout-simulate` run as backup. scout never falls back to made-up places. |
| Members feel uneasy that an AI reads their chat. | Explain what it reads and stores when it joins, keep only trip data, and support deletion on request. |
| Disputes over money. | Confirm every logged expense, let only the payer log or remove what they paid, and never handle real money. |
| Nessie is down or slow during the demo. It has been flaky at past hackathons, its docs page is offline, and plain HTTP no longer works. | Short timeouts. If a call fails or no key is set, scout records the payment in its own ledger and says it was simulated, so the settle-up still finishes. Open members' accounts before going on stage. |
| People mistake sandbox payments for real ones, or expect real money to move. | Every payment confirmation says it's Capital One sandbox money. Real payments would need a real rail and are out of scope. |
| Nessie's live API differs from its docs (no payee on transfers, whole-dollar amounts, inconsistent `_id`/`id` fields), and its balance behavior hasn't been verified. | Keep scout's ledger as the source of truth and mirror each payment as a withdrawal plus a deposit. Check balances against a real key before the demo. |
| Other teams can read anything stored in Nessie through its shared enterprise endpoints. | Send Nessie placeholder names and addresses only, never members' names or phone numbers. |
| A receipt is misread, so someone is charged the wrong amount. | Always show the extracted total for confirmation, ask instead of guessing when a receipt is unclear, and keep the receipt image attached so anyone can check it. |
| Receipt photos show partial card numbers or other personal details. | Store only what's needed for the split, limit receipt images to group members, and delete them with the rest of the trip data. |
| Someone's photo ends up in the album when they didn't want it there, or the album link spreads beyond the group. | Make automatic adding opt-in, let members remove their own photos, and use unguessable links that only group members receive. |
| Members are uneasy giving an AI access to their calendar. | Lead with links that need no access at all. When reading calendars arrives, make it opt-in, ask only for free/busy, explain in one line what scout can and can't see, and let people disconnect any time. |
| Google requires app verification before many people can grant calendar access, and an unverified app shows a warning screen. | Links and .ics files avoid this entirely. Treat free/busy reading as post-demo work, and start verification early if the project continues. |
| Added events go stale when plans change, because a link can't update an event that's already on someone's calendar. | Text an updated link with a clear note about what changed (CAL-4). Revisit live sync only if groups ask for it. |

## 14. Open questions

The interaction model from section 7 is decided for now; what's left is checking it with real groups. How scout joins iMessage groups is also decided: a Linq line plugged into Photon's Spectrum SDK (see [scout-imessage-groups.md](scout-imessage-groups.md), which lists what's left to test there). Other questions to settle include how members should share their location during a trip, whether private one-on-one texting for sensitive constraints like budgets is worth building, whether groups would rather have the album live in a photo app they already use than in scout's own web album, whether enough members would connect their calendars to make reading free/busy (CAL-5, CAL-6) worth Google's verification process, and, if the project continues past the class, how scout would sustain itself (for example, booking affiliate links versus a paid tier).
