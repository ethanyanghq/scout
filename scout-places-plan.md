# Plan: hotels, activities and photos from Google Places

| | |
| --- | --- |
| **Goal** | Every hotel and activity scout shows the group is a real place from Google Places, with a rating and a photo any phone can load. That's the data the brochure and the activity deck in [integration.md](integration.md) are drawn from. Until the cards exist, the same data reads well as text, so each step can be shown in the developer console. |
| **Status** | Not started. Nothing here waits on the HermesShare pipe or the demo phones. Only the last step, a public HTTPS address for photos, waits on hosting (TODO, section 1). Last updated October 4, 2026. |
| **Design** | [integration.md](integration.md), stages 3 and 4 and section 5 |
| **Builds toward** | Milestone 4 of [scout-group-chat-plan.md](scout-group-chat-plan.md): the brochure card and the activity deck |
| **Google's docs** | [Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search), [data fields and SKUs](https://developers.google.com/maps/documentation/places/web-service/data-fields), [Place Photos](https://developers.google.com/maps/documentation/places/web-service/place-photos), [policies](https://developers.google.com/maps/documentation/places/web-service/policies), read October 4, 2026 |

Check items off in the pull request that finishes them.

## What exists today

- `src/scout/places.py` runs Text Search and returns each place's ID, name, location, price level and a one-line summary. Only on-trip suggestions use it (`suggest_nearby_places`), along with finding the spot the group names ("near our Airbnb in Condado").
- Destinations are Claude's picks. `DestinationOption` is a name, an estimate and a reason, with no hotel and no photo.
- There are no activities. The itinerary is written from the group's must-haves.
- The service listens on `127.0.0.1` only, so nothing on the internet can reach it, including a phone loading a photo.

## What Google's docs change

Each of these either corrects our docs or shapes the design below.

- **Rating, review count and photos add no cost per search.** A Text Search is billed at the highest tier among the fields it asks for. `editorialSummary`, already in `FIELD_MASK`, is in the top tier (Enterprise + Atmosphere). `rating` and `userRatingCount` are Enterprise, and `photos` and `googleMapsUri` are Pro. So integration.md (section 5) and the PRD (tech stack, Hotels and activities) are wrong to say the new fields raise the cost. Photo downloads are billed separately, once per request.
- **No hotel amenities and no room rates.** Places has no pool, spa or all-inclusive fields. Its amenity flags are about restaurants (outdoor seating, serves dinner). It gives a price level from `$` to `$$$$`, not a nightly rate.
- **Text Search can't sort by rating.** It can filter by type (`includedType: "lodging"`) and by a minimum rating, and it ranks by relevance or distance. Picking the top-rated hotel is scout's job.
- **Photos can't be stored, and photo names expire.** Only place IDs may be kept. A photo has to be fetched fresh from its place each time someone loads it.
- **Places content shown outside a Google map needs credit.** That means "Google Maps" (the logo or the words), the photo author's name, and a way to open the place on Google Maps (`googleMapsUri`). The nearby list scout posts today shows none of these.

## Decisions

- **Claude picks, Places grounds.** Claude still chooses the three destinations and the activity ideas, because it's the part that reads the group's interests. scout then looks up every hotel and activity in Places, and only what Places returns goes to the group. An idea Places can't find is dropped, not shown. This is how `suggest_nearby_places` already works.
- **Code picks the hotel, not Claude.** For each destination: `lodging` places rated 4.0 or higher, and of those with at least 100 reviews, the highest rated. A 5.0 from twelve reviews shouldn't beat a 4.7 from three thousand. Because code picks, "top-rated" means the same thing every run and can be tested.
- **Activities are searched near the hotel**, out to Google's maximum bias radius of 50 km, because a day trip counts as reachable. The 2 km radius for on-trip suggestions stays as it is.
- **Prices stay Claude's estimates, labeled with "~".** Places has no tour prices or room rates. Flights are already estimated this way.
- **The brochure shows Google's summary of the hotel, not a list of amenities.** Claude making up a spa for a real hotel is exactly the kind of invented fact the PRD rules out. This changes DS-2 and the brochure mockup in integration.md, which the first pull request updates.
- **A Places failure never blocks the poll.** If there's no key, Google is down, or no hotel qualifies, the destination goes out without a hotel. The vote is a critical user journey; the hotel is decoration.
- **Photos come from a separate public app.** The service stays private to the bridge. A second small FastAPI app on its own port serves only photos, and the tunnel or host exposes only that port, so `/messages` and the dev endpoints never reach the internet.
- **The photo app serves only places scout has shown.** It answers for place IDs in `scout.db` and returns 404 for anything else, so a stranger can't spend the Google budget by guessing IDs.

## Checklist

### 1. Hotels on the destination poll

Shipped when the destination poll names a real top-rated hotel for each option, with its rating, and the poll still posts when Places is unavailable. Seen in the console with `devchat start ... --from poll-open` and in `scout-simulate`.

- [ ] `Place` gains `rating`, `review_count`, `google_maps_url` and `photo_credit` (the first photo's author), and `FIELD_MASK` asks for `rating`, `userRatingCount`, `photos` and `googleMapsUri`. Saved place suggestions in `scout.db` keep loading after the change. Tested against the stand-in Places server in `tests/test_places.py`.
- [ ] Search can be narrowed to a place type with a minimum rating, which the hotel lookup needs.
- [ ] Picking the top hotel for a destination, by the rule above. Tests: a 4.7 with 3,000 reviews beats a 5.0 with 12; no hotel qualifies, so there's none.
- [ ] `DestinationOption` gains `hotel: Place | None`. `start_destination_poll` looks up a hotel for each of Claude's three destinations before posting, and the poll shows it (`🏨 Hotel Xcaret Arte ★4.7 (3,214)`). The `poll-open` seed gets hotels too.
- [ ] Every list built from Places ends with "via Google Maps", the nearby list included.
- [ ] Fix the cost claim in integration.md and the PRD, and replace amenities with Google's summary in DS-2 and the brochure mockup.
- [ ] Update `posts-summary-and-poll.chat` if its checks depend on the poll's wording.

### 2. Activities near the hotel

Shipped when, once a destination is chosen, scout can post about eight real activities near the hotel, each with a rating and an estimated price. Text for now; milestone 4's deck replaces the text with a card.

- [ ] An `Activity`: the place, Claude's estimated price, and a one-line description (Google's summary, or else Claude's).
- [ ] An agent tool for proposing activities. Claude gives about eight ideas, each a search phrase and an estimated price. scout searches each one near the hotel, keeps the top hit, and drops ideas with no result and repeats of the same place. Then it posts the list.
- [ ] The `destination-chosen` seed includes the winning destination's hotel, so the console can start right here.
- [ ] A console script that starts at `destination-chosen`, asks for activities, and checks that the trip saved them.

### 3. Photos phones can load

Shipped when every hotel and activity has an HTTPS photo URL that loads on a phone, the API key never leaves the Mac, and nothing from Google is stored except place IDs.

- [ ] The photo app: `GET /places/{place_id}/photo` looks up the place's first photo with a fresh Place Details call, then streams the image from Place Photos at a width that suits a card (1,200 px). It stores nothing. It returns 404 for a place scout hasn't shown, and 502 with a log line when Google fails.
- [ ] `Place` gets a photo URL built from a new `SCOUT_PUBLIC_URL` setting. During development that's the photo app on localhost, which the console's card preview will flag as not HTTPS.
- [ ] `bun run dev` starts the photo app, and `.env.example` documents `SCOUT_PUBLIC_URL` and the photo app's port.
- [ ] Tests against a stand-in for Place Details and Place Photos: the image streams through, an unknown place gets a 404, Google failing gets a 502.
- [ ] Point the tunnel or host chosen in TODO, section 1, at the photo app's port only, then load one photo on a real phone.
- [ ] DEVELOPING.md's "What exists today" table gets a row for the photo app.

## Still open

- **Who fetches a card's thumbnail, and how often?** Linq once at send time, or every phone each time the card is shown? This decides what a photo costs, because each load is a billed Place Details call plus a billed photo download. The photo app's log answers it during milestone 4's "prove the pipe" send.
- **Where the credit goes on a card.** The brochure and the deck each need room for "Google Maps", the photo's author and a link to the place.
- **Whether 100 reviews is the right bar.** A small island may have no hotel that clears it. Check the three destinations the demo uses.
- **What scout keeps in `scout.db`.** Saved place suggestions already hold names and locations, and Google's policy allows only place IDs to be kept long-term. That's fine for a demo that won't launch, but it would need fixing before real users.

## Not in this plan

- The cards themselves, reading submits, activity votes, the itinerary built from picks, and bookings. Those are milestone 4 of [scout-group-chat-plan.md](scout-group-chat-plan.md).
- Flight data, and real hotel prices or availability.
