"""The tools Claude can call, and how each call maps onto a TripAction."""

from datetime import date, time
from decimal import Decimal
from typing import Any

from scout.best_flights import HomeAirport
from scout.brochures import ActivityPitch, DestinationPitch
from scout.money import CENTS_PER_DOLLAR
from scout.trip import (
    Chronotype,
    DeckActivity,
    DestinationOption,
    ItineraryAddOn,
    ItineraryDay,
    MessagePhoto,
    PreferenceUpdate,
    Rating,
)
from scout.trip_actions import ExpenseDraft, ItemDraft, TripActionError, TripActions


def _nullable(json_type: str, description: str) -> dict:
    return {"type": [json_type, "null"], "description": description}


# `strict` makes the API guarantee inputs match these schemas, which requires
# every property to be listed in `required`; optional ones are nullable instead.
TOOL_DEFINITIONS = [
    {
        "name": "save_member_preferences",
        "description": (
            "Save one member's trip preferences from anywhere in the chat, "
            "tagged or not: what they shared, or what a friend said for them. "
            "Pass null for anything nobody mentioned; it keeps whatever was "
            "saved before."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "member": {
                    "type": "string",
                    "description": (
                        "Who shared these details, exactly as the chat labels "
                        "them, like 'Maya' or '…0002'."
                    ),
                },
                "display_name": _nullable("string", "Their first name."),
                "available_from": _nullable(
                    "string", "First day they can travel, as YYYY-MM-DD."
                ),
                "available_to": _nullable(
                    "string", "Last day they can travel, as YYYY-MM-DD."
                ),
                "budget_usd": _nullable(
                    "integer", "Total trip budget per person in US dollars."
                ),
                "home_city": _nullable("string", "City they'd travel from."),
                "must_haves": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": (
                        "Their complete must-have list, replacing any earlier "
                        "list. Short phrases like 'beach' or 'good nightlife'."
                    ),
                },
                # A plain string rather than an enum: an enum makes the strict
                # tool grammar too large for the API to compile.
                "chronotype": _nullable(
                    "string",
                    "When they like to start the day: 'early riser', "
                    "'late riser' or 'night owl'.",
                ),
            },
            "required": [
                "member",
                "display_name",
                "available_from",
                "available_to",
                "budget_usd",
                "home_city",
                "must_haves",
                "chronotype",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "post_group_summary",
        "description": (
            "Post a summary of everyone's preferences: shared dates, budget "
            "range, home cities, must-haves, and who hasn't replied."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "start_destination_poll",
        "description": (
            "Post a poll with exactly 3 destinations that fit the group's shared "
            "dates, everyone's budget, and their must-haves."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Destination, e.g. 'Tulum, Mexico'.",
                            },
                            "estimated_cost_per_person_usd": {
                                "type": "integer",
                                "description": (
                                    "Rough total per person: flights, lodging, "
                                    "food, and activities."
                                ),
                            },
                            "reason": {
                                "type": "string",
                                "description": (
                                    "Why it fits this group, under 12 words."
                                ),
                            },
                        },
                        "required": [
                            "name",
                            "estimated_cost_per_person_usd",
                            "reason",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["options"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_member_vote",
        "description": (
            "Record one member's vote in the open poll: the sender's, or one a "
            "friend reported for them. Closes the poll and announces the winner "
            "automatically once everyone has voted."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "member": {
                    "type": "string",
                    "description": (
                        "Whose vote this is, exactly as the chat labels them, "
                        "like 'Maya' or '…0002'."
                    ),
                },
                "option_number": {
                    "type": "integer",
                    "description": "The option's number as shown in the poll (1-3).",
                },
            },
            "required": ["member", "option_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_activity_deck",
        "description": (
            "Post a deck of things to do at the chosen destination for each "
            "member to tick. Replaces any earlier deck and its picks."
        ),
        # Not strict, like post_itinerary, to keep the strict tools' grammar
        # small enough for the API. The action checks every value.
        "strict": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "activities": {
                    "type": "array",
                    "description": "3 to 8 real, well-known activities there.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": (
                                    "Under 6 words, without commas, e.g. "
                                    "'Night kayak in the bio bay'."
                                ),
                            },
                            "description": {
                                "type": "string",
                                "description": "One short line on what it is.",
                            },
                            "estimated_cost_usd": {
                                "type": "integer",
                                "description": "Rough cost per person in US dollars.",
                            },
                        },
                        "required": ["name", "description", "estimated_cost_usd"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["activities"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_member_picks",
        "description": (
            "Record how one member rated the deck activities, from what they "
            "or a friend said in words. Replaces their earlier ratings; any "
            "activity in neither list counts as nah. Posts the tally "
            "automatically once everyone has sent picks."
        ),
        "strict": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "member": {
                    "type": "string",
                    "description": (
                        "Whose picks these are, exactly as the chat labels "
                        "them, like 'Maya' or '…0002'."
                    ),
                },
                "yeah_numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Every activity they're definitely in for, by its "
                        "number on the deck. Empty if none."
                    ),
                },
                "meh_numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Every activity they'd do but aren't excited about, "
                        "by its number on the deck. Empty if none."
                    ),
                },
            },
            "required": ["member", "yeah_numbers", "meh_numbers"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lock_in_group_choice",
        "description": (
            "Lock in the destination when someone speaks for the whole group: "
            '"we\'ve chosen San Juan", "we\'re all going with 2", "talked '
            "it over, it's Tulum\". One member saying it for everyone is "
            "enough; don't wait for the others to vote or confirm. Closes any "
            "open poll. For one person's own pick, "
            "use record_member_vote instead."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": (
                        "The place the group chose: a poll option's name or "
                        "number as shown, or any destination they named."
                    ),
                },
            },
            "required": ["destination"],
            "additionalProperties": False,
        },
    },
    {
        "name": "close_poll",
        "description": (
            "Close the open poll now and announce the winner. Ties go to the "
            "cheapest option."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "post_itinerary",
        "description": (
            "Post a day-by-day plan for the chosen destination: a table of "
            "the events on each day within the trip dates, plus optional "
            "add-ons for what only one person wanted. The first plan also sends "
            "the group a calendar link that stays up to date. Replaces any "
            "earlier plan, so include every day and add-on when editing."
        ),
        # Not strict: with it, every strict tool together compiles to a grammar
        # too large for the API. post_itinerary checks every value it's given.
        "strict": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "array",
                    "description": "Every event of the trip, in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": (
                                    "The day, as YYYY-MM-DD. Give a day several "
                                    "entries to list several events on it."
                                ),
                            },
                            "plan": {
                                "type": "string",
                                "description": (
                                    "One event, under 10 words, e.g. 'Night kayak on "
                                    "a bioluminescent bay'."
                                ),
                            },
                            "starts_at": _nullable(
                                "string",
                                "When the event starts, as 24-hour HH:MM, paced "
                                "to the group. Null for something loose, like "
                                "a free afternoon or a travel day.",
                            ),
                        },
                        "required": ["date", "plan", "starts_at"],
                        "additionalProperties": False,
                    },
                },
                "optional_add_ons": {
                    "type": "array",
                    "description": (
                        "Activities only one person asked for, offered as "
                        "optional instead of scheduled for everyone. Empty if "
                        "there are none."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "activity": {
                                "type": "string",
                                "description": (
                                    "Under 8 words, e.g. 'Scuba at Escambrón'."
                                ),
                            },
                            "wanted_by": {
                                "type": "string",
                                "description": (
                                    "Who asked for it, as the chat labels them, "
                                    "like 'Leo'."
                                ),
                            },
                        },
                        "required": ["activity", "wanted_by"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["days", "optional_add_ons"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_booking_links",
        "description": (
            "Post flight search links from each member's home city and a stay "
            "search link sized for the group, for the chosen destination and "
            "trip dates."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_best_flights",
        "description": (
            "Post a card with the best round-trip flight from each member's home "
            "city to the chosen destination on the trip dates, with live Google "
            "Flights fares and a link to book each one."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "home_airports": {
                    "type": "array",
                    "description": "One entry for every home city in the trip.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "home_city": {
                                "type": "string",
                                "description": "As shown in the trip state.",
                            },
                            "airport_code": {
                                "type": "string",
                                "description": (
                                    "The IATA code of its main airport, e.g. "
                                    "'BOS', or a city code like 'NYC' where a "
                                    "city has several."
                                ),
                            },
                        },
                        "required": ["home_city", "airport_code"],
                        "additionalProperties": False,
                    },
                },
                "arrival_airport_code": {
                    "type": "string",
                    "description": (
                        "The IATA code of the destination's main airport, e.g. "
                        "'SJU' for San Juan."
                    ),
                },
            },
            "required": ["home_airports", "arrival_airport_code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_best_hotel",
        "description": (
            "Post a card with the best hotel at the chosen destination for the "
            "trip dates, with its live Google Hotels rate and a link to book it."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "suggest_nearby_places",
        "description": (
            "Post three real nearby places that fit what the group asked for, "
            "with price level and a rough travel time from where they are."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": (
                        "What they want, in search words, e.g. 'cozy taco "
                        "restaurant with outdoor seating, not touristy'."
                    ),
                },
                "near": _nullable(
                    "string",
                    (
                        "Where they are, as they named it, e.g. 'Condado' or "
                        "'Old San Juan'. Null if nobody said; ask if it matters."
                    ),
                ),
            },
            "required": ["request", "near"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_directions",
        "description": (
            "Send a Google Maps directions link to one of the places you last "
            "suggested, once the group picks it. Plain replies like '2' are "
            "handled automatically before you see them."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "option_number": {
                    "type": "integer",
                    "description": "The place's number as shown in the list (1-3).",
                },
            },
            "required": ["option_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_destination_brochures",
        "description": (
            "Post 3 cards, one per destination, each a short travel article "
            "the group can open and scroll: a real photo, its top-rated hotel, "
            "things to do with photos, and an all-in price estimate per person. "
            "Use it when someone asks to see or browse destinations. It doesn't "
            "start a vote."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "nights": {
                    "type": "integer",
                    "description": (
                        "How many nights the estimates assume: the trip's dates "
                        "if set, otherwise what the group said, otherwise 5."
                    ),
                },
                "destinations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Destination, e.g. 'Tulum, Mexico'.",
                            },
                            "region": {
                                "type": "string",
                                "description": (
                                    "Where it is, e.g. 'Quintana Roo, Mexico'."
                                ),
                            },
                            "description": {
                                "type": "string",
                                "description": (
                                    "What it's like and why it fits the group, "
                                    "under 30 words."
                                ),
                            },
                            "flights_usd": {
                                "type": "integer",
                                "description": (
                                    "Estimated round-trip flight per person "
                                    "from the group's home cities."
                                ),
                            },
                            "hotel_usd": {
                                "type": "integer",
                                "description": (
                                    "Estimated hotel cost per person for all "
                                    "nights, sharing rooms."
                                ),
                            },
                            "food_and_activities_usd": {
                                "type": "integer",
                                "description": (
                                    "Estimated food, local transport and the "
                                    "activities below, per person."
                                ),
                            },
                            "activities": {
                                "type": "array",
                                "description": "3 fun, real things to do there.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": (
                                                "Under 6 words, searchable, e.g. "
                                                "'Snorkel Akumal Bay'."
                                            ),
                                        },
                                        "estimated_cost_usd": {
                                            "type": "integer",
                                            "description": "Per person.",
                                        },
                                    },
                                    "required": ["name", "estimated_cost_usd"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": [
                            "name",
                            "region",
                            "description",
                            "flights_usd",
                            "hotel_usd",
                            "food_and_activities_usd",
                            "activities",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["nights", "destinations"],
            "additionalProperties": False,
        },
    },
    {
        "name": "log_sender_expense",
        "description": (
            "Log a trip cost that the sender of the newest message paid. By "
            "default it's split evenly across everyone in the trip. If only some "
            "people shared it, pass split_among with just their names. If people "
            "had different things (a receipt where each person ordered their "
            "own), pass items with who shared each one: tax and tip are then "
            "split in proportion to what each person had. Only log costs the "
            "sender says they paid themselves. Never guess who shared it: if "
            "it's unclear, ask first."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_usd": {
                    "type": "number",
                    "description": (
                        "The full amount they paid in US dollars, tax and tip "
                        "included, e.g. 1240 or 164.5."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "What it was for, under 5 words, e.g. 'Airbnb' or "
                        "'Casa Brisa dinner'."
                    ),
                },
                "paid_on": _nullable(
                    "string", "The date it was paid as YYYY-MM-DD, if known."
                ),
                "split_among": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": (
                        "Names of the only people who share it, or null for everyone."
                    ),
                },
                "items": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "amount_usd": {"type": "number"},
                            "shared_by": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "amount_usd", "shared_by"],
                        "additionalProperties": False,
                    },
                    "description": (
                        "The receipt's lines, each with who shared it, or null "
                        "to split the whole amount evenly. An empty shared_by "
                        "means everyone in split_among."
                    ),
                },
            },
            "required": [
                "amount_usd",
                "description",
                "paid_on",
                "split_among",
                "items",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_to_confirm_receipt",
        "description": (
            "When the sender's photo is a clear receipt, post what you read from "
            "it and ask them to confirm before anything is logged. Once they "
            "confirm, call log_sender_expense with the total (or their corrected "
            "amount). Don't use it for unclear receipts: ask for the total instead."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant": {
                    "type": "string",
                    "description": "The business name, e.g. 'Casa Brisa'.",
                },
                "purchased_on": _nullable(
                    "string", "The receipt's date as YYYY-MM-DD, if it shows one."
                ),
                "total_usd": {
                    "type": "number",
                    "description": "The final total, including tax and tip.",
                },
            },
            "required": ["merchant", "purchased_on", "total_usd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "drop_pending_receipt",
        "description": (
            "Forget the receipt waiting for confirmation, when its payer says not "
            "to split it."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "view_photo",
        "description": (
            "Look at a photo someone sent earlier, when its description in the "
            "chat isn't enough, like reading a receipt's total or a "
            "screenshot's small print. The chat shows each photo as "
            "[photo <id> (<file>): <description>]."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "photo_id": {
                    "type": "string",
                    "description": "The photo's id from the chat, like 'a1b2c3d4'.",
                },
            },
            "required": ["photo_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remove_expense",
        "description": (
            "Remove an expense the sender logged by mistake. Only the person who "
            "paid it can remove it. To fix an amount, remove the old expense and "
            "log the right one."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "expense_number": {
                    "type": "integer",
                    "description": "The expense's # as shown in the trip state.",
                },
            },
            "required": ["expense_number"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_sender_payment",
        "description": (
            "Record that the sender of the newest message has paid one person "
            "what the settle-up plan says they owe. scout moves no money: this "
            "only records the payment, then posts the confirmation and what's left."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "payee_name": {
                    "type": "string",
                    "description": "Who they paid, as named in the trip state.",
                },
            },
            "required": ["payee_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "post_expense_report",
        "description": (
            "Post the trip's full expense report: every expense with who paid "
            "it and how it was split, each person's total paid and owed, and "
            "who owes whom. Use it when someone asks to wrap up the money or "
            "for the whole breakdown; post_settle_up is the quick version."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "post_settle_up",
        "description": (
            "Post the total shared cost, each person's share, and the fewest "
            "payments that settle everyone up."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
]


# Long inputs, like a whole itinerary, are cut short in the log.
MAX_LOGGED_INPUT_CHARACTERS = 200


def describe_tool_call(
    name: str, tool_input: dict[str, Any], outcome: str | MessagePhoto
) -> str:
    """One readable log line for a tool the AI used: what it passed, leaving
    out empty fields, and what came back."""
    if isinstance(outcome, MessagePhoto):
        outcome = "showed the photo"
    passed = ", ".join(
        f"{field}={_plain(value)}"
        for field, value in tool_input.items()
        if value not in (None, [], "")
    )
    if len(passed) > MAX_LOGGED_INPUT_CHARACTERS:
        passed = passed[:MAX_LOGGED_INPUT_CHARACTERS] + "…"
    return f"  AI used {name}({passed}) → {outcome}"


def _plain(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(_plain(item) for item in value)
    return str(value)


def run_tool(
    actions: TripActions, name: str, tool_input: dict[str, Any]
) -> str | MessagePhoto:
    """Runs one tool call and returns its status for the AI, or the photo it
    asked to see. Raises TripActionError if the input can't be used."""
    match name:
        case "save_member_preferences":
            return actions.save_member_preferences(
                tool_input["member"], _to_preference_update(tool_input)
            )
        case "post_group_summary":
            return actions.post_group_summary()
        case "start_destination_poll":
            options = [DestinationOption(**option) for option in tool_input["options"]]
            return actions.start_destination_poll(options)
        case "record_member_vote":
            return actions.record_member_vote(
                tool_input["member"], tool_input["option_number"] - 1
            )
        case "close_poll":
            return actions.close_poll()
        case "send_activity_deck":
            return actions.send_activity_deck(
                [DeckActivity(**activity) for activity in tool_input["activities"]]
            )
        case "record_member_picks":
            return actions.record_member_picks(
                tool_input["member"],
                {
                    **{n - 1: Rating.MEH for n in tool_input["meh_numbers"]},
                    **{n - 1: Rating.YEAH for n in tool_input["yeah_numbers"]},
                },
            )
        case "lock_in_group_choice":
            return actions.lock_in_group_choice(tool_input["destination"])
        case "post_itinerary":
            return actions.post_itinerary(
                _to_itinerary(tool_input),
                [
                    ItineraryAddOn(**add_on)
                    for add_on in tool_input.get("optional_add_ons", [])
                ],
            )
        case "send_booking_links":
            return actions.send_booking_links()
        case "send_best_flights":
            return actions.send_best_flights(
                [HomeAirport(**home) for home in tool_input["home_airports"]],
                tool_input["arrival_airport_code"],
            )
        case "send_best_hotel":
            return actions.send_best_hotel()
        case "suggest_nearby_places":
            return actions.suggest_nearby_places(
                tool_input["request"], tool_input["near"]
            )
        case "send_directions":
            return actions.send_directions(tool_input["option_number"] - 1)
        case "send_destination_brochures":
            return actions.send_destination_brochures(
                _to_pitches(tool_input["destinations"]), tool_input["nights"]
            )
        case "log_sender_expense":
            return actions.log_sender_expense(_to_expense_draft(tool_input))
        case "post_expense_report":
            return actions.post_expense_report()
        case "ask_to_confirm_receipt":
            return actions.ask_to_confirm_receipt(
                tool_input["merchant"],
                _parse_date(tool_input["purchased_on"]),
                _to_cents(tool_input["total_usd"]),
            )
        case "drop_pending_receipt":
            return actions.drop_pending_receipt()
        case "view_photo":
            return actions.view_photo(tool_input["photo_id"])
        case "remove_expense":
            return actions.remove_expense(tool_input["expense_number"])
        case "post_settle_up":
            return actions.post_settle_up()
        case "record_sender_payment":
            return actions.record_sender_payment(tool_input["payee_name"])
        case _:
            raise TripActionError(f"unknown tool {name}")


def _to_expense_draft(tool_input: dict[str, Any]) -> ExpenseDraft:
    return ExpenseDraft(
        amount_cents=_to_cents(tool_input["amount_usd"]),
        description=tool_input["description"],
        paid_on=_parse_date(tool_input.get("paid_on")),
        split_among=tuple(tool_input.get("split_among") or ()),
        items=tuple(
            ItemDraft(
                item["name"],
                _to_cents(item["amount_usd"]),
                tuple(item["shared_by"]),
            )
            for item in tool_input.get("items") or ()
        ),
    )


def _to_preference_update(tool_input: dict[str, Any]) -> PreferenceUpdate:
    return PreferenceUpdate(
        display_name=tool_input["display_name"],
        available_from=_parse_date(tool_input["available_from"]),
        available_to=_parse_date(tool_input["available_to"]),
        budget_usd=tool_input["budget_usd"],
        home_city=tool_input["home_city"],
        must_haves=tool_input["must_haves"],
        chronotype=_parse_chronotype(tool_input["chronotype"]),
    )


def _to_itinerary(tool_input: dict[str, Any]) -> list[ItineraryDay]:
    return [
        ItineraryDay(
            day=_parse_date(day["date"]),
            plan=day["plan"],
            starts_at=_parse_time(day.get("starts_at")),
        )
        for day in tool_input["days"]
    ]


def _to_pitches(destinations: list[dict[str, Any]]) -> list[DestinationPitch]:
    return [
        DestinationPitch(
            **{key: value for key, value in pitch.items() if key != "activities"},
            activities=[ActivityPitch(**activity) for activity in pitch["activities"]],
        )
        for pitch in destinations
    ]


def _to_cents(amount_usd: float) -> int:
    # Decimal avoids float rounding: 0.29 * 100 is 28.999999999999996.
    cents = Decimal(str(amount_usd)) * CENTS_PER_DOLLAR
    if cents != cents.to_integral_value():
        raise TripActionError(f"{amount_usd} has fractions of a cent")
    return int(cents)


def _parse_chronotype(value: str | None) -> Chronotype | None:
    if value is None:
        return None
    try:
        return Chronotype(value)
    except ValueError as error:
        choices = ", ".join(repr(pace.value) for pace in Chronotype)
        raise TripActionError(f"{value!r} is not one of {choices}") from error


def _parse_time(value: str | None) -> time | None:
    if value is None:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise TripActionError(f"{value!r} is not an HH:MM time") from error


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise TripActionError(f"{value!r} is not a YYYY-MM-DD date") from error
