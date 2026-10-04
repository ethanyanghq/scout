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

from scout.activity_deck import PASS_LABEL, PICKS_LEAD
from scout.best_flights import (
    HomeCityFlight,
    describe_stops,
    format_clock,
    format_duration,
)
from scout.expense_report import describe_items, describe_split, member_totals
from scout.group_summary import format_window, summarize_group
from scout.itinerary import format_day, format_start
from scout.money import format_usd
from scout.settle_up import plan_payments
from scout.trip import DeckActivity, Expense, ItineraryAddOn, ItineraryDay, Trip

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
# The budget slider, per person in US dollars: $0 to $3,000 in $100 steps,
# labeled every $500 and starting at $1,000.
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
# A nonstop is the good case, so it wears scout blue; amber flags a layover.
CONNECTING_HEX = "#FF9F0A"


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
                    "minValue": 0,
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


def activity_deck(
    destination: str, activities: list[DeckActivity], destination_photo_url: str | None
) -> dict:
    """A deck of things to do, each with its own in-or-pass picker. Send puts
    the activities someone is in for in the chat as text."""
    lead = urllib.parse.quote(PICKS_LEAD)
    photo = (
        [
            {
                "type": "gallery",
                "urls": [destination_photo_url],
                "heightPt": 180,
                "cornerRadius": 18,
            }
        ]
        if destination_photo_url
        else []
    )
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
                *photo,
                _text(
                    "Tick what you'd do, then send. Your picks drop into the chat.",
                    role="body",
                    color_hex=SOFT_GRAY_HEX,
                ),
                *[
                    _activity_picker(position, activity)
                    for position, activity in enumerate(activities)
                ],
                _text(
                    "Prices are estimates per person. Nothing is booked.",
                    role="footnote",
                    color_hex=SOFT_GRAY_HEX,
                ),
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


def _activity_picker(position: int, activity: DeckActivity) -> dict:
    # Each activity is its own single-select field, because HermesShare's form
    # holds one answer per field. The "in" option is labeled with the activity
    # itself, so the sent text names what someone picked.
    picked = _option(
        "in",
        activity.name,
        f"~${activity.estimated_cost_usd:,} · {activity.description}",
        "checkmark.circle",
    )
    if activity.photo_url:
        picked["imageUrl"] = activity.photo_url
    passed = _option("pass", PASS_LABEL, "Not for me", "xmark.circle")
    return _picker(f"activity-{position}", "list", [picked, passed])


def itinerary(trip: Trip, destination_photo_url: str) -> dict:
    """The trip's plan as a timeline, one stop per day with when it starts,
    then the optional add-ons and who wanted each.

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
            "spacing": 18,
            "alignment": "leading",
            "children": [
                {
                    "type": "gallery",
                    "urls": [destination_photo_url],
                    "heightPt": 200,
                    "cornerRadius": 18,
                },
                {
                    "type": "card",
                    "child": {
                        "type": "timeline",
                        "entries": [_timeline_entry(day) for day in trip.itinerary],
                    },
                },
                *_add_ons(trip.itinerary_add_ons),
                _text(
                    "Times are a suggestion. Nothing is booked.",
                    role="footnote",
                    color_hex=SOFT_GRAY_HEX,
                ),
            ],
        },
    }


def _timeline_entry(day: ItineraryDay) -> dict:
    entry = {"time": format_day(day), "title": day.plan, "state": "future"}
    start = format_start(day)
    if start:
        entry["subtitle"] = f"Starts {start}"
    return entry


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
    """A departure board for each home city's flight, with its fare and a
    button that opens it on Google Flights.

    Expects a trip whose destination and dates are locked in.
    """
    return {
        "version": 1,
        "title": f"Flights to {trip.destination}",
        "subtitle": f"{format_window(trip.dates)} · round trip",
        "accentColorHex": SCOUT_BLUE_HEX,
        # The board is drawn dark, so the card around it goes dark too.
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 16,
            "alignment": "leading",
            "children": [
                node
                for home_city_flight in home_city_flights
                for node in _flight_nodes(trip, home_city_flight)
            ],
        },
        "actions": [_booking_action(f) for f in home_city_flights],
    }


def flights_thumbnail_url(home_city_flights: list[HomeCityFlight]) -> str | None:
    """The photo iMessage shows on the unopened bubble: the destination city."""
    return next(
        (
            f.flight.destination_photo_url
            for f in home_city_flights
            if f.flight.destination_photo_url
        ),
        None,
    )


def _flight_nodes(trip: Trip, home_city_flight: HomeCityFlight) -> list[dict]:
    flight = home_city_flight.flight
    board = {
        "type": "flightBoard",
        "board": {
            "origin": flight.departure_airport,
            "destination": flight.arrival_airport,
            "originCity": home_city_flight.home_city,
            "destinationCity": trip.destination,
            "flightCode": flight.flight_numbers[0],
            "departTime": format_clock(flight.departs_at),
            "arriveTime": format_clock(flight.arrives_at),
            "status": describe_stops(flight),
            "statusColorHex": (
                CONNECTING_HEX if flight.layover_airports else SCOUT_BLUE_HEX
            ),
        },
    }
    fare = {
        "type": "card",
        "child": {
            "type": "vstack",
            "spacing": 4,
            "children": [
                _row("Fare", f"${flight.price_usd:,} per person", "dollarsign.circle"),
                _row("Airline", " / ".join(flight.airlines), "airplane"),
                _row("Flying time", format_duration(flight.duration_minutes), "clock"),
                _row("For", ", ".join(home_city_flight.travelers), "person.2.fill"),
            ],
        },
    }
    return [board, fare]


def _row(key: str, value: str, sf_symbol: str) -> dict:
    return {
        "type": "keyValueRow",
        "key": key,
        "value": value,
        "iconSystemName": sf_symbol,
    }


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


def expense_report(trip: Trip, destination_photo_url: str) -> list[ExpenseReportPage]:
    """Everything the trip cost, as a summary card (who paid what, who owes
    whom) followed by as many ledger cards as the expenses need, since one
    message only holds so much. Expects a trip with at least one expense."""
    summary = ExpenseReportPage(
        _expense_summary(trip, destination_photo_url), "Trip expenses", ()
    )
    chunks = _fit_expense_chunks(trip, destination_photo_url)
    pages = [summary]
    for number, chunk in enumerate(chunks, start=1):
        caption = LEDGER_TITLE
        if len(chunks) > 1:
            caption += f" ({number} of {len(chunks)})"
        layout = _expense_ledger(trip, chunk, destination_photo_url, caption)
        pages.append(ExpenseReportPage(layout, caption, tuple(chunk)))
    return pages


def _fit_expense_chunks(trip: Trip, photo_url: str) -> list[list[Expense]]:
    """Splits the expenses, in order, into the fewest runs that each fit on a card."""
    chunks: list[list[Expense]] = [[]]
    for expense in trip.expenses:
        candidate = [*chunks[-1], expense]
        fits = fits_in_one_message(
            _expense_ledger(trip, candidate, photo_url, LONGEST_LEDGER_TITLE)
        )
        if fits or not chunks[-1]:
            chunks[-1] = candidate
        else:
            chunks.append([expense])
    return chunks


def _expense_summary(trip: Trip, photo_url: str) -> dict:
    total_cents = sum(expense.amount_cents for expense in trip.expenses)
    payments = [
        _row(
            f"{p.payer.label} → {p.payee.label}",
            format_usd(p.amount_cents),
            "arrow.right.circle",
        )
        for p in plan_payments(trip)
    ] or [_row("Everyone's settled up", "🎉", "checkmark.circle")]
    who_paid_what = [
        _row(
            t.member.label,
            f"paid {format_usd(t.paid_cents)} · owes {format_usd(t.share_cents)}",
            "person.fill",
        )
        for t in member_totals(trip)
    ]
    return _expense_card(
        trip,
        "Trip expenses",
        photo_url,
        [
            {
                "type": "statusBadge",
                "label": f"{format_usd(total_cents)} across "
                f"{len(trip.expenses)} expenses",
                "colorHex": SCOUT_BLUE_HEX,
            },
            _section_heading("Who paid what"),
            _card_of_rows(who_paid_what),
            _section_heading("Who owes who"),
            _card_of_rows(payments),
        ],
    )


def _expense_ledger(
    trip: Trip, expenses: list[Expense], photo_url: str, title: str
) -> dict:
    nodes = [_expense_nodes(trip, expense) for expense in expenses]
    return _expense_card(trip, title, photo_url, nodes)


def _expense_card(trip: Trip, title: str, photo_url: str, children: list[dict]) -> dict:
    subtitle = format_window(trip.dates) if trip.dates else trip.destination or ""
    return {
        "version": 1,
        "title": title,
        "subtitle": subtitle,
        "accentColorHex": SCOUT_BLUE_HEX,
        "background": {"kind": "atmosphere", "colorsHex": [NIGHT_GLOW_HEX]},
        "root": {
            "type": "vstack",
            "spacing": 18,
            "alignment": "leading",
            "children": [
                {
                    "type": "gallery",
                    "urls": [photo_url],
                    "heightPt": 160,
                    "cornerRadius": 18,
                },
                *children,
            ],
        },
    }


def _card_of_rows(rows: list[dict]) -> dict:
    return {"type": "card", "child": {"type": "vstack", "spacing": 4, "children": rows}}


def _expense_nodes(trip: Trip, expense: Expense) -> dict:
    payer = trip.find_member(expense.payer_phone)
    amount = format_usd(expense.amount_cents)
    details = [describe_split(expense, trip.members)]
    items = describe_items(expense, trip.members)
    if items:
        details.append(items)
    return _card_of_rows(
        [
            _row(expense.description, f"{amount} · {payer.label}", "receipt"),
            *[_text(d, role="footnote", color_hex=SOFT_GRAY_HEX) for d in details],
        ]
    )
