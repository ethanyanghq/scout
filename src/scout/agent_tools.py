"""The tools Claude can call, and how each call maps onto a TripAction."""

from datetime import date
from typing import Any

from scout.trip import DestinationOption, ItineraryDay, PreferenceUpdate
from scout.trip_actions import TripActionError, TripActions


def _nullable(json_type: str, description: str) -> dict:
    return {"type": [json_type, "null"], "description": description}


# `strict` makes the API guarantee inputs match these schemas, which requires
# every property to be listed in `required`; optional ones are nullable instead.
TOOL_DEFINITIONS = [
    {
        "name": "save_sender_preferences",
        "description": (
            "Save trip preferences shared by the person who sent the newest "
            "message. Pass null for anything they didn't mention; it keeps "
            "whatever was saved before. Only save what this person said about "
            "themselves."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
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
            },
            "required": [
                "display_name",
                "available_from",
                "available_to",
                "budget_usd",
                "home_city",
                "must_haves",
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
        "name": "record_sender_vote",
        "description": (
            "Record the sender's vote in the open poll. Closes the poll and "
            "announces the winner automatically once everyone has voted."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "option_number": {
                    "type": "integer",
                    "description": "The option's number as shown in the poll (1-3).",
                },
            },
            "required": ["option_number"],
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
            "Post a day-by-day plan for the chosen destination, one anchor "
            "activity per day within the trip dates. Replaces any earlier plan, "
            "so include every day when editing."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "The day, as YYYY-MM-DD.",
                            },
                            "plan": {
                                "type": "string",
                                "description": (
                                    "The day's one big thing, under 10 words, "
                                    "e.g. 'Night kayak on a bioluminescent bay'."
                                ),
                            },
                        },
                        "required": ["date", "plan"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["days"],
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
]


def run_tool(actions: TripActions, name: str, tool_input: dict[str, Any]) -> str:
    """Runs one tool call. Raises TripActionError if the input can't be used."""
    match name:
        case "save_sender_preferences":
            return actions.save_sender_preferences(_to_preference_update(tool_input))
        case "post_group_summary":
            return actions.post_group_summary()
        case "start_destination_poll":
            options = [DestinationOption(**option) for option in tool_input["options"]]
            return actions.start_destination_poll(options)
        case "record_sender_vote":
            return actions.record_sender_vote(tool_input["option_number"] - 1)
        case "close_poll":
            return actions.close_poll()
        case "post_itinerary":
            return actions.post_itinerary(_to_itinerary(tool_input))
        case "send_booking_links":
            return actions.send_booking_links()
        case _:
            raise TripActionError(f"unknown tool {name}")


def _to_preference_update(tool_input: dict[str, Any]) -> PreferenceUpdate:
    return PreferenceUpdate(
        display_name=tool_input["display_name"],
        available_from=_parse_date(tool_input["available_from"]),
        available_to=_parse_date(tool_input["available_to"]),
        budget_usd=tool_input["budget_usd"],
        home_city=tool_input["home_city"],
        must_haves=tool_input["must_haves"],
    )


def _to_itinerary(tool_input: dict[str, Any]) -> list[ItineraryDay]:
    return [
        ItineraryDay(day=_parse_date(day["date"]), plan=day["plan"])
        for day in tool_input["days"]
    ]


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise TripActionError(f"{value!r} is not a YYYY-MM-DD date") from error
