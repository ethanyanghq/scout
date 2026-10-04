"""The interactive cards scout sends into the chat.

A card is a HermesShare layout: declarative JSON that an Apple-signed iMessage
extension draws as native SwiftUI. iMessage runs no HTML or JavaScript, so the
payload is parameters for a fixed vocabulary of views, never code.

Only sending is built. What someone taps on a card can't reach scout: Linq's
ingest flattens an inbound `imessage_app` part to a single replacement
character before any webhook sees it, so the group still votes in text.
"""

import base64
import json
import urllib.parse
from dataclasses import dataclass
from datetime import date

from scout.activity_deck import PICKS_LEAD
from scout.best_flights import (
    HomeCityFlight,
    describe_stops,
    format_clock,
    format_day,
    format_duration,
    format_landing,
)
from scout.best_hotel import describe_rating
from scout.expense_report import describe_items, describe_split, member_totals
from scout.flights import Layover, OneWay
from scout.group_summary import format_window, summarize_group
from scout.hotels import Hotel
from scout.itinerary import events_by_day, format_date, format_start
from scout.money import format_usd
from scout.settle_up import plan_payments
from scout.trip import (
    DeckActivity,
    Expense,
    ItineraryAddOn,
    ItineraryDay,
    Rating,
    Trip,
)

# Every scout card is white text on HermesShare's near-black `atmosphere`
# background, so it looks the same whatever mode the phone is in. Scout blue is
# the one accent: buttons, icons, picks and the price tag. It is too dark to
# read as small text on near-black, so headings and small print stay gray.
SCOUT_BLUE_HEX = "#2B2EF3"
SOFT_GRAY_HEX = "#A1A1AA"
# Tints the atmosphere background's glow; this dark it reads as plain black.
NIGHT_GLOW_HEX = "#1B2422"
# The trip interview's Send button fills in a text that tags scout, so the
# answers arrive as an ordinary message: Linq can't carry a card reply back.
INTERVIEW_ANSWER_LEAD = "@scout my trip:"
# Linq's limit on a card's data: URL, mirrored from bridge/hermes-card.ts.
MAX_CARD_URL_CHARS = 16_384
CARD_URL_PREFIX = "data:application/json;base64,"
# The activity deck's swipes. (rating, label, swipe direction, SF Symbol)
SWIPE_CHOICES = [
    (Rating.NAH, "Nah", "left", "arrow.left"),
    (Rating.MEH, "Meh", "up", "arrow.up"),
    (Rating.YEAH, "Yeah", "right", "arrow.right"),
]
# One line above the stack that says which way each swipe goes.
SWIPE_LEGEND = "←  Nah      ↑  Meh      Yeah  →"
# The budget slider, per person in US dollars: $500 to $3,000 in $100 steps,
# labeled every $500 and starting at $1,000.
BUDGET_SLIDER_MIN_USD = 500
BUDGET_SLIDER_MAX_USD = 3_000
BUDGET_SLIDER_STEP_USD = 100
BUDGET_SLIDER_LABEL_EVERY_USD = 500
BUDGET_SLIDER_START_USD = 1_000
# The kind of trip, a 2x2 grid of names alone; "Other" turns into a text
# field. (id, label, SF Symbol)
TRIP_KINDS = [
    ("resort", "All-inclusive resort", "sparkles"),
    ("lakeside", "Lakeside", "water.waves"),
    ("city", "City break", "building.2.fill"),
    ("other", "Other", "pencil"),
]
# Chunks are fitted with the longest title a ledger card could get, so the
# real "(1 of 3)" never pushes a full card over Linq's limit.
LEDGER_TITLE = "Every expense"
LONGEST_LEDGER_TITLE = f"{LEDGER_TITLE} (99 of 99)"
OTHER_TRIP_KIND_PLACEHOLDER = "Describe your trip"
# What each person is into; they can tick any number. (id, label, sublabel,
# SF Symbol)
TRIP_STYLES = [
    (
        "nightlife",
        "Clubs and nightlife",
        "Late nights, bars, parties",
        "moon.stars.fill",
    ),
    ("early-riser", "Early riser", "Sunrise hikes, morning dives", "sunrise.fill"),
    ("outdoors", "Hiking and outdoors", "Trails, views, waterfalls", "figure.hiking"),
    ("food", "Food and culture", "Markets, tours, long dinners", "fork.knife"),
    ("beach", "Beach and chill", "Pool, sand, a good book", "beach.umbrella.fill"),
    ("adventure", "Adventure sports", "Diving, surfing, ziplines", "figure.surfing"),
    ("wellness", "Wellness and spa", "Massages, yoga, slow mornings", "leaf.fill"),
    ("shopping", "Shopping and markets", "Boutiques, crafts, souvenirs", "bag.fill"),
]
# A flight's stops badge: green for a nonstop, amber flags a layover. Both are
# Apple's dark-mode system colors, bright enough to read on near-black.
NONSTOP_HEX = "#30D158"
CONNECTING_HEX = "#FF9F0A"
# The hotel card's amenity tags: light gray, since the scout blue accent is
# too dark to read as small text on near-black.
AMENITY_TAG_HEX = "#E4E4E7"
MAX_AMENITIES = 6
MAX_NEARBY_PLACES = 3
# Amenities shown ahead of the rest, as Google Hotels names them.
DECIDING_AMENITIES = [
    "Free breakfast",
    "Beach access",
    "Outdoor pool",
    "Pool",
    "Kitchen",
    "Free parking",
    "Free Wi-Fi",
    "Air conditioning",
    "Hot tub",
    "Fitness center",
]
# The expense report's bubble: a calculator and a notebook of sums, so it
# reads as the trip's money at a glance. CC0, on Wikimedia Commons.
EXPENSES_THUMBNAIL_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/"
    "Desktop_with_laptop_and_calculator_%28Unsplash%29.jpg/"
    "1280px-Desktop_with_laptop_and_calculator_%28Unsplash%29.jpg"
)
# The flight card's bubble: a plane's wing above the clouds, so it reads as
# flights at a glance. Public domain, on Wikimedia Commons.
FLIGHTS_THUMBNAIL_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1d/"
    "A_wing_tip_of_an_airplane_%2840118125441%29.jpg/"
    "1280px-A_wing_tip_of_an_airplane_%2840118125441%29.jpg"
)


@dataclass(frozen=True)
class Activity:
    """Something to do at a destination, shown with its photo in the article."""

    name: str
    estimated_cost_usd: int
    photo_url: str | None = None


@dataclass(frozen=True)
class CostEstimate:
    """One part of a destination's per-person estimate, e.g. flights."""

    label: str
    estimated_usd: int
    sf_symbol: str


@dataclass(frozen=True)
class Brochure:
    """One destination, as the group sees it in its card."""

    # As the agent named it, e.g. "Cancún, Mexico".
    destination: str
    # Where it is, e.g. "Quintana Roo, Mexico".
    region: str
    # A sentence on why it fits the group.
    detail: str
    hotel: str
    costs: list[CostEstimate]
    activities: list[Activity]
    hero_photo_url: str | None = None

    @property
    def estimated_cost_per_person_usd(self) -> int:
        return sum(cost.estimated_usd for cost in self.costs)

    @property
    def place_name(self) -> str:
        """The name a card leads with: "Cancún" rather than "Cancún, Mexico"."""
        return self.destination.split(",")[0].strip()


def destination_article(brochure: Brochure, nights: int) -> dict:
    """One destination as a short travel article: photos, what it costs, why it
    fits, where to stay and things to do, then the full cost breakdown."""
    return {
        "version": 1,
        "title": brochure.place_name,
        "subtitle": brochure.region,
        "accentColorHex": SCOUT_BLUE_HEX,
        # `atmosphere` draws a near-black card and switches its text to white.
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 16,
            "alignment": "leading",
            "children": [
                *_photo_strip(brochure),
                _price_per_person(brochure),
                _text(brochure.detail, role="body"),
                _section_heading("Where you'll stay"),
                _text(brochure.hotel, role="headline"),
                _section_heading("Things to do"),
                _activities(brochure.activities),
                _section_heading("What it costs"),
                _cost_breakdown(brochure),
                _text(
                    f"Estimates for {nights} nights. Nothing is booked.",
                    role="footnote",
                    color_hex=SOFT_GRAY_HEX,
                ),
            ],
        },
    }


def _photo_strip(brochure: Brochure) -> list[dict]:
    """The hero photo, then each activity's, to swipe through.

    A `gallery` sizes and clips every photo itself. HermesShare's `image`
    node doesn't, so one large photo stretches the whole card off screen.
    """
    activity_photos = [a.photo_url for a in brochure.activities if a.photo_url]
    photos = (
        [brochure.hero_photo_url, *activity_photos]
        if brochure.hero_photo_url
        else activity_photos
    )
    if not photos:
        return []
    return [{"type": "gallery", "urls": photos, "heightPt": 230, "cornerRadius": 18}]


def _price_per_person(brochure: Brochure) -> dict:
    # A blue icon beside white text: scout blue is too dark to read as text
    # on the near-black card.
    price = f"~${brochure.estimated_cost_per_person_usd:,} per person, all in"
    return {
        "type": "hstack",
        "spacing": 8,
        "alignment": "center",
        "children": [
            {
                "type": "icon",
                "systemName": "tag.fill",
                "sizePt": 18,
                "colorHex": SCOUT_BLUE_HEX,
            },
            _text(price, role="headline"),
        ],
    }


def _activities(activities: list[Activity]) -> dict:
    """Each activity and its price, in the same kind of panel as the costs."""
    rows = [
        {
            "type": "keyValueRow",
            "key": activity.name,
            "value": f"~${activity.estimated_cost_usd:,}",
        }
        for activity in activities
    ]
    return {"type": "card", "child": {"type": "vstack", "spacing": 4, "children": rows}}


def _cost_breakdown(brochure: Brochure) -> dict:
    total = f"~${brochure.estimated_cost_per_person_usd:,}"
    return {
        "type": "card",
        "child": {
            "type": "vstack",
            "spacing": 4,
            "children": [
                *[
                    _row(cost.label, f"~${cost.estimated_usd:,}", cost.sf_symbol)
                    for cost in brochure.costs
                ],
                {"type": "divider"},
                _row("Per person, all in", total, "sun.max.fill"),
            ],
        },
    }


def _section_heading(title: str) -> dict:
    heading = _text(title.upper(), role="subheadline", color_hex=SOFT_GRAY_HEX)
    heading["style"]["weight"] = "bold"
    return heading


def _text(words: str, role: str, color_hex: str | None = None) -> dict:
    style = {"role": role}
    if color_hex:
        style["colorHex"] = color_hex
    return {"type": "text", "text": words, "style": style}


def trip_interview(today: date) -> dict:
    """A quick interview each member taps through: the kind of trip, their
    dates, budget, home city and what they're into. Send puts their answers in
    the chat as text."""
    lead = urllib.parse.quote(INTERVIEW_ANSWER_LEAD)
    return {
        "version": 1,
        # HermesShare requires one on any card with form inputs.
        "formId": "trip-interview",
        "title": "Let's plan your trip",
        "subtitle": "A few taps, then send",
        "accentColorHex": SCOUT_BLUE_HEX,
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 14,
            "alignment": "leading",
            "children": [
                _text(
                    "Pick what fits you. Your answers drop into the chat for me.",
                    role="body",
                    color_hex=SOFT_GRAY_HEX,
                ),
                _section_heading("Trip vibe"),
                _picker("kind", "grid", _trip_kind_options()),
                _section_heading("When"),
                {
                    "type": "dateRangePicker",
                    "fieldId": "dates",
                    "earliestDate": today.isoformat(),
                },
                _section_heading("Budget per person"),
                {
                    "type": "slider",
                    "fieldId": "budget",
                    "minValue": BUDGET_SLIDER_MIN_USD,
                    "maxValue": BUDGET_SLIDER_MAX_USD,
                    "step": BUDGET_SLIDER_STEP_USD,
                    "value": BUDGET_SLIDER_START_USD,
                    "tickStep": BUDGET_SLIDER_LABEL_EVERY_USD,
                    "valuePrefix": "$",
                },
                _section_heading("Flying from"),
                {
                    "type": "textInput",
                    "fieldId": "home",
                    "placeholder": "City or airport, e.g. Boston",
                    "summaryPrefix": "from ",
                },
                _section_heading("What are you into?"),
                {
                    "type": "multiPicker",
                    "fieldId": "style",
                    "options": [_option(*style) for style in TRIP_STYLES],
                },
            ],
        },
        "actions": [
            {
                "id": "send-trip-answers",
                "label": "Send my answers",
                "systemImage": "paperplane.fill",
                # A `text` action puts the picks in the message box as plain text.
                "deepLinkURL": f"hermesshare://text?lead={lead}",
            }
        ],
    }


def _trip_kind_options() -> list[dict]:
    options = [
        {"id": kind_id, "label": label, "systemImage": symbol}
        for kind_id, label, symbol in TRIP_KINDS
    ]
    options[-1]["textEntryPlaceholder"] = OTHER_TRIP_KIND_PLACEHOLDER
    return options


def _picker(field_id: str, style: str, options: list[dict]) -> dict:
    # A `fieldId` makes the picker a form input that the Send button reads.
    return {
        "type": "optionPicker",
        "fieldId": field_id,
        "pickerStyle": style,
        "options": options,
    }


def _option(
    option_id: str, label: str, sublabel: str, sf_symbol: str | None = None
) -> dict:
    option = {"id": option_id, "label": label, "sublabel": sublabel}
    if sf_symbol:
        option["systemImage"] = sf_symbol
    return option


def fits_in_one_message(layout: dict) -> bool:
    """Whether Linq will send the card. It refuses one whose data: URL is
    longer than MAX_CARD_URL_CHARS (bridge/hermes-card.ts). Python's JSON is
    a little longer than the bridge's, so this errs on the safe side."""
    encoded = base64.b64encode(json.dumps(layout).encode())
    return len(CARD_URL_PREFIX) + len(encoded) <= MAX_CARD_URL_CHARS


def activity_deck(destination: str, activities: list[DeckActivity]) -> dict:
    """A stack of things to do to swipe through: left is nah, up is meh, right
    is yeah. Send puts the swipes in the chat as text. It has no photo of its
    own, so the stack gets the whole screen without scrolling."""
    lead = urllib.parse.quote(PICKS_LEAD)
    return {
        "version": 1,
        # HermesShare requires one on any card with form inputs.
        "formId": "activity-deck",
        "title": "What are you up for?",
        "subtitle": destination,
        "accentColorHex": SCOUT_BLUE_HEX,
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 14,
            "alignment": "leading",
            "children": [
                _text(SWIPE_LEGEND, role="callout", color_hex=SOFT_GRAY_HEX),
                _swipe_deck(activities),
            ],
        },
        "actions": [
            {
                "id": "send-activity-picks",
                "label": "Send my picks",
                "systemImage": "paperplane.fill",
                # A `text` action puts the picks in the message box as plain text.
                "deepLinkURL": f"hermesshare://text?lead={lead}",
            }
        ],
    }


def _swipe_deck(activities: list[DeckActivity]) -> dict:
    # A swipeDeck is a form input like a picker: it holds one choice per card
    # and fires nothing until Send. Its text summary is each card's title and
    # the chosen choice's id, "Night kayak yeah", joined with " · ", which is
    # what parse_picks reads back.
    return {
        "type": "swipeDeck",
        "fieldId": "activities",
        "cards": [_swipe_card(position, a) for position, a in enumerate(activities)],
        "choices": [
            {
                "id": rating.name.lower(),
                "label": label,
                "swipeDirection": direction,
                "systemImage": sf_symbol,
            }
            for rating, label, direction, sf_symbol in SWIPE_CHOICES
        ],
    }


def _swipe_card(position: int, activity: DeckActivity) -> dict:
    card = {
        "id": f"activity-{position}",
        "title": activity.name,
        "subtitle": (
            f"~${activity.estimated_cost_usd:,} per person · {activity.description}"
        ),
    }
    if activity.photo_url:
        card["imageUrl"] = activity.photo_url
    return card


def itinerary(trip: Trip, destination_photo_url: str) -> dict:
    """The trip's plan as a table for each day, headed by the date and listing
    that day's events with when each starts, then the optional add-ons and who
    wanted each.

    Expects a trip whose destination, dates and itinerary are set.
    """
    pace = summarize_group(trip.members).pace
    subtitle = format_window(trip.dates)
    if pace:
        subtitle += f" · paced for {pace}s"
    return {
        "version": 1,
        "title": trip.destination,
        "subtitle": subtitle,
        "accentColorHex": SCOUT_BLUE_HEX,
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 14,
            "alignment": "leading",
            "children": [
                {
                    "type": "gallery",
                    "urls": [destination_photo_url],
                    "heightPt": 200,
                    "cornerRadius": 18,
                },
                *[
                    _day_table(day, events)
                    for day, events in events_by_day(trip.itinerary)
                ],
                *_add_ons(trip.itinerary_add_ons),
                _text(
                    "Times are a suggestion. Nothing is booked.",
                    role="footnote",
                    color_hex=SOFT_GRAY_HEX,
                ),
            ],
        },
    }


def _day_table(day: date, events: list[ItineraryDay]) -> dict:
    heading = _text(format_date(day), role="headline")
    rows = [
        {
            "type": "keyValueRow",
            "key": event.plan,
            "value": format_start(event) or "Anytime",
        }
        for event in events
    ]
    return {
        "type": "card",
        "child": {
            "type": "vstack",
            "spacing": 6,
            "alignment": "leading",
            "children": [heading, {"type": "divider"}, *rows],
        },
    }


def _add_ons(add_ons: list[ItineraryAddOn]) -> list[dict]:
    if not add_ons:
        return []
    rows = [
        _row(add_on.activity, f"{add_on.wanted_by}'s pick", "plus.circle")
        for add_on in add_ons
    ]
    return [
        _section_heading("Optional add-ons"),
        {"type": "card", "child": {"type": "vstack", "spacing": 4, "children": rows}},
    ]


def best_flights(trip: Trip, home_city_flights: list[HomeCityFlight]) -> dict:
    """Each home city's recommended round trip, the way out and the way back
    with every stop, then its fare and a button that opens it on Google Flights.

    Expects a trip whose destination and dates are locked in.
    """
    return {
        "version": 1,
        "title": f"Flights to {trip.destination}",
        "subtitle": f"{format_window(trip.dates)} · round trip",
        "accentColorHex": SCOUT_BLUE_HEX,
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 12,
            "alignment": "leading",
            "children": [
                node
                for home_city_flight in home_city_flights
                for node in _flight_nodes(trip, home_city_flight)
            ],
        },
        "actions": [_booking_action(f) for f in home_city_flights],
    }


def _flight_nodes(trip: Trip, home_city_flight: HomeCityFlight) -> list[dict]:
    flight = home_city_flight.flight
    home_city = home_city_flight.home_city
    fare = _card_of_rows(
        [
            _row("Round trip", f"${flight.price_usd:,} per person"),
            _row("For", ", ".join(home_city_flight.travelers)),
        ]
    )
    return [
        _section_heading(f"From {home_city}"),
        _one_way_card("Out", flight.outbound, home_city, trip.destination),
        _one_way_card("Back", flight.homebound, trip.destination, home_city),
        fare,
    ]


def _one_way_card(
    direction: str, one_way: OneWay, from_city: str, to_city: str
) -> dict:
    """One direction as rows down the card: takeoff, each layover, landing."""
    heading = {
        "type": "hstack",
        "spacing": 8,
        "alignment": "center",
        "children": [
            _text(
                f"{direction} · {format_day(one_way.departs_at)}",
                role="headline",
            ),
            {
                "type": "statusBadge",
                "label": describe_stops(one_way),
                "colorHex": CONNECTING_HEX if one_way.layovers else NONSTOP_HEX,
            },
        ],
    }
    stops = [
        _row(f"Change planes in {layover.airport}", _layover_wait(layover))
        for layover in one_way.layovers
    ]
    airline = (
        f"{' / '.join(one_way.airlines)} {' · '.join(one_way.flight_numbers)}"
        f" · {format_duration(one_way.duration_minutes)} total"
    )
    return {
        "type": "card",
        "child": {
            "type": "vstack",
            "spacing": 10,
            "alignment": "leading",
            "children": [
                heading,
                {"type": "divider"},
                _row(
                    f"Leave {one_way.departure_airport} · {from_city}",
                    format_clock(one_way.departs_at),
                ),
                *stops,
                _row(
                    f"Land {one_way.arrival_airport} · {to_city}",
                    format_landing(one_way),
                ),
                _text(airline, role="footnote", color_hex=SOFT_GRAY_HEX),
            ],
        },
    }


def _layover_wait(layover: Layover) -> str:
    return f"{format_duration(layover.duration_minutes)} wait"


def best_hotel(trip: Trip, hotel: Hotel) -> dict:
    """The recommended hotel with what the group needs to judge it: what kind
    of place it is, its price against the typical one, what guests think,
    what's there and nearby, and a button that opens it on Google Hotels.

    Expects a trip whose destination and dates are locked in.
    """
    photo = (
        [
            {
                "type": "gallery",
                "urls": [hotel.photo_url],
                "heightPt": 200,
                "cornerRadius": 18,
            }
        ]
        if hotel.photo_url
        else []
    )
    return {
        "version": 1,
        "title": f"Where to stay in {trip.destination}",
        "subtitle": f"{format_window(trip.dates)} · {hotel.nights} nights",
        "accentColorHex": SCOUT_BLUE_HEX,
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 14,
            "alignment": "leading",
            "children": [
                *photo,
                *_hotel_heading(hotel),
                _hotel_price(hotel),
                *_hotel_reviews(hotel),
                *_hotel_surroundings(hotel),
            ],
        },
        "actions": [
            {
                "id": "book-hotel",
                "label": "Book on Google Hotels",
                "systemImage": "bed.double.fill",
                # An https link opens Google Hotels rather than posting a reply.
                "deepLinkURL": hotel.booking_url,
            }
        ],
    }


def _hotel_heading(hotel: Hotel) -> list[dict]:
    """The name, what kind of place it is, and Google's deal flag if it has one."""
    kind = " · ".join(filter(None, [hotel.kind, *hotel.room_details]))
    return [
        _text(hotel.name, role="title3"),
        *([_text(kind, role="subheadline", color_hex=SOFT_GRAY_HEX)] if kind else []),
        *(
            [
                {
                    "type": "statusBadge",
                    "label": f"Deal · {hotel.deal}",
                    "colorHex": NONSTOP_HEX,
                }
            ]
            if hotel.deal
            else []
        ),
    ]


def _hotel_price(hotel: Hotel) -> dict:
    typical = hotel.typical_nightly_rate_usd
    rows = [
        _row("Per night", f"${hotel.nightly_rate_usd:,}"),
        _row(f"All {hotel.nights} nights", f"${hotel.stay_total_usd:,}"),
        *([_row("Typical here", f"${typical:,} a night")] if typical else []),
    ]
    note = _text(
        "With taxes and fees, for 2 guests. Rates can change until you book.",
        role="footnote",
        color_hex=SOFT_GRAY_HEX,
    )
    return {
        "type": "card",
        "child": {
            "type": "vstack",
            "spacing": 8,
            "alignment": "leading",
            "children": [*rows, note],
        },
    }


def _hotel_reviews(hotel: Hotel) -> list[dict]:
    """What guests think and when the stay starts and ends, if Google says."""
    rating = describe_rating(hotel)
    location = hotel.location_rating
    rows = [
        *([_row("Guests say", rating)] if rating else []),
        *([_row("Location", f"{location:g} out of 5")] if location else []),
        *([_row("Check-in", hotel.check_in_time)] if hotel.check_in_time else []),
        *([_row("Check-out", hotel.check_out_time)] if hotel.check_out_time else []),
    ]
    return [_card_of_rows(rows)] if rows else []


def _hotel_surroundings(hotel: Hotel) -> list[dict]:
    """What's at the hotel and what's a short trip away, then a map."""
    nodes = []
    amenities = pick_amenities(hotel.amenities)
    if amenities:
        nodes += [
            _section_heading("What's there"),
            {"type": "tagRow", "labels": amenities, "colorHex": AMENITY_TAG_HEX},
        ]
    nearby = hotel.nearby_places[:MAX_NEARBY_PLACES]
    if nearby:
        nodes += [
            _section_heading("Nearby"),
            _card_of_rows([_row(place.name, place.trip) for place in nearby]),
        ]
    if hotel.coordinates:
        nodes.append(
            {
                "type": "mapPreview",
                "latitude": hotel.coordinates.latitude,
                "longitude": hotel.coordinates.longitude,
                "label": hotel.name,
            }
        )
    return nodes


def pick_amenities(amenities: list[str]) -> list[str]:
    """The amenities a group most often decides on first, then the rest, up to
    a row or two of tags."""
    wanted_first = [a for a in DECIDING_AMENITIES if a in amenities]
    rest = [a for a in amenities if a not in DECIDING_AMENITIES]
    return (wanted_first + rest)[:MAX_AMENITIES]


def _row(key: str, value: str, sf_symbol: str | None = None) -> dict:
    row = {"type": "keyValueRow", "key": key, "value": value}
    if sf_symbol:
        row["iconSystemName"] = sf_symbol
    return row


def _booking_action(home_city_flight: HomeCityFlight) -> dict:
    # An https link opens Google Flights rather than posting a reply in the chat.
    return {
        "id": f"book-{_slug(home_city_flight.home_city)}",
        "label": f"Book from {home_city_flight.home_city}",
        "systemImage": "airplane.departure",
        "deepLinkURL": home_city_flight.flight.booking_url,
    }


def _slug(text: str) -> str:
    kept = [c.lower() if c.isalnum() else "-" for c in text]
    return "".join(kept).strip("-").replace("--", "-")


@dataclass(frozen=True)
class ExpenseReportPage:
    """One card of the expense report, and what it covers."""

    layout: dict
    caption: str
    # The expenses it lists. Empty on the summary card.
    expenses: tuple[Expense, ...]


def expense_report(trip: Trip) -> list[ExpenseReportPage]:
    """Everything the trip cost, as a summary card (who paid what, who owes
    whom) followed by as many ledger cards as the expenses need, since one
    message only holds so much. Expects a trip with at least one expense."""
    summary = ExpenseReportPage(_expense_summary(trip), "Trip expenses", ())
    chunks = _fit_expense_chunks(trip)
    pages = [summary]
    for number, chunk in enumerate(chunks, start=1):
        caption = LEDGER_TITLE
        if len(chunks) > 1:
            caption += f" ({number} of {len(chunks)})"
        layout = _expense_card(trip, caption, _expense_nodes(trip, chunk))
        pages.append(ExpenseReportPage(layout, caption, tuple(chunk)))
    return pages


def _fit_expense_chunks(trip: Trip) -> list[list[Expense]]:
    """Splits the expenses, in order, into the fewest runs that each fit on a card."""
    chunks: list[list[Expense]] = [[]]
    for expense in trip.expenses:
        candidate = [*chunks[-1], expense]
        fits = fits_in_one_message(
            _expense_card(trip, LONGEST_LEDGER_TITLE, _expense_nodes(trip, candidate))
        )
        if fits or not chunks[-1]:
            chunks[-1] = candidate
        else:
            chunks.append([expense])
    return chunks


def _expense_summary(trip: Trip) -> dict:
    total_cents = sum(expense.amount_cents for expense in trip.expenses)
    plural = "" if len(trip.expenses) == 1 else "s"
    payments = [
        _row(f"{p.payer.label} → {p.payee.label}", format_usd(p.amount_cents))
        for p in plan_payments(trip)
    ] or [_row("Everyone's settled up", "🎉")]
    who_paid_what = [
        _row(
            t.member.label,
            f"paid {format_usd(t.paid_cents)} · owes {format_usd(t.share_cents)}",
        )
        for t in member_totals(trip)
    ]
    return _expense_card(
        trip,
        "Trip expenses",
        [
            {
                "type": "vstack",
                "spacing": 2,
                "alignment": "leading",
                "children": [
                    _text(format_usd(total_cents), role="largeTitle"),
                    _text(
                        f"spent across {len(trip.expenses)} expense{plural}",
                        role="subheadline",
                        color_hex=SOFT_GRAY_HEX,
                    ),
                ],
            },
            _section_heading("Who owes who"),
            _card_of_rows(payments),
            _section_heading("Who paid what"),
            _card_of_rows(who_paid_what),
        ],
    )


def _expense_card(trip: Trip, title: str, children: list[dict]) -> dict:
    subtitle = format_window(trip.dates) if trip.dates else trip.destination or ""
    return {
        "version": 1,
        "title": title,
        "subtitle": subtitle,
        "accentColorHex": SCOUT_BLUE_HEX,
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 14,
            "alignment": "leading",
            "children": children,
        },
    }


def _card_of_rows(rows: list[dict]) -> dict:
    return {"type": "card", "child": {"type": "vstack", "spacing": 4, "children": rows}}


def _expense_nodes(trip: Trip, expenses: list[Expense]) -> list[dict]:
    return [_expense_entry(trip, expense) for expense in expenses]


def _expense_entry(trip: Trip, expense: Expense) -> dict:
    payer = trip.find_member(expense.payer_phone)
    amount = format_usd(expense.amount_cents)
    details = [describe_split(expense, trip.members)]
    items = describe_items(expense, trip.members)
    if items:
        details.append(items)
    return _card_of_rows(
        [
            _row(expense.description, f"{amount} · {payer.label}"),
            *[_text(d, role="footnote", color_hex=SOFT_GRAY_HEX) for d in details],
        ]
    )
