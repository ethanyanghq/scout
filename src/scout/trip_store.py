"""Saves trips to SQLite so nothing is lost if scout restarts (PRD §9)."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from scout.places import Coordinates, Place
from scout.trip import (
    DateWindow,
    DestinationOption,
    Expense,
    ItineraryDay,
    MediaKind,
    Member,
    PendingReceipt,
    Poll,
    PreferenceUpdate,
    Settlement,
    SharedMedia,
    Trip,
    TripStage,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    space_id    TEXT PRIMARY KEY,
    stage       TEXT NOT NULL,
    destination TEXT,
    starts_on   TEXT,
    ends_on     TEXT,
    created_at  TEXT NOT NULL
);

-- One row per person per trip. Preferences live here because each member has
-- exactly one set of them.
CREATE TABLE IF NOT EXISTS members (
    space_id       TEXT NOT NULL REFERENCES trips (space_id),
    phone          TEXT NOT NULL,
    display_name   TEXT,
    available_from TEXT,
    available_to   TEXT,
    budget_usd     INTEGER,
    home_city      TEXT,
    must_haves     TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (space_id, phone)
);

CREATE TABLE IF NOT EXISTS polls (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id TEXT NOT NULL REFERENCES trips (space_id),
    options  TEXT NOT NULL,
    is_open  INTEGER NOT NULL
);

-- The primary key means a second vote from the same person replaces the first.
CREATE TABLE IF NOT EXISTS votes (
    poll_id      INTEGER NOT NULL REFERENCES polls (id),
    phone        TEXT NOT NULL,
    option_index INTEGER NOT NULL,
    PRIMARY KEY (poll_id, phone)
);

CREATE TABLE IF NOT EXISTS itinerary_days (
    space_id TEXT NOT NULL REFERENCES trips (space_id),
    day      TEXT NOT NULL,
    plan     TEXT NOT NULL,
    PRIMARY KEY (space_id, day)
);

CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id     TEXT NOT NULL REFERENCES trips (space_id),
    payer_phone  TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    description  TEXT NOT NULL
);

-- Payments already made. What's still owed is worked out from expenses and
-- these, so there's no separate "unpaid" state to keep in sync.
CREATE TABLE IF NOT EXISTS settlements (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id             TEXT NOT NULL REFERENCES trips (space_id),
    payer_phone          TEXT NOT NULL,
    payee_phone          TEXT NOT NULL,
    amount_cents         INTEGER NOT NULL
);

-- At most one receipt per trip waits for its payer to confirm; a newer one
-- replaces it.
CREATE TABLE IF NOT EXISTS pending_receipts (
    space_id    TEXT PRIMARY KEY REFERENCES trips (space_id),
    payer_phone TEXT NOT NULL,
    merchant    TEXT NOT NULL,
    total_cents INTEGER NOT NULL
);

-- Only the latest suggestions are kept: they're what "2" or "the first one"
-- refers to.
CREATE TABLE IF NOT EXISTS place_suggestions (
    space_id  TEXT NOT NULL REFERENCES trips (space_id),
    position  INTEGER NOT NULL,
    place_id  TEXT NOT NULL,
    name      TEXT NOT NULL,
    latitude  REAL NOT NULL,
    longitude REAL NOT NULL,
    price     TEXT,
    summary   TEXT,
    PRIMARY KEY (space_id, position)
);

CREATE TABLE IF NOT EXISTS chat_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id     TEXT NOT NULL REFERENCES trips (space_id),
    sender_phone TEXT,
    text         TEXT NOT NULL,
    sent_at      TEXT NOT NULL
);

-- The photos and voice notes members sent. The files live in the media
-- folder (media.py); this says where, and what's in each in words.
CREATE TABLE IF NOT EXISTS media (
    space_id      TEXT NOT NULL REFERENCES trips (space_id),
    id            TEXT NOT NULL,
    kind          TEXT NOT NULL,
    original_path TEXT NOT NULL,
    readable_path TEXT NOT NULL,
    transcript    TEXT,
    PRIMARY KEY (space_id, id)
);
"""

# Every table with a space_id column, with trips last because the others refer
# to it. delete_trip clears each one, so a new table belongs here too.
TABLES_BY_SPACE = (
    "members",
    "polls",
    "itinerary_days",
    "expenses",
    "settlements",
    "pending_receipts",
    "place_suggestions",
    "chat_log",
    "media",
    "trips",
)


@dataclass(frozen=True)
class LoggedMessage:
    # None when scout sent the message.
    sender_phone: str | None
    text: str
    sent_at: datetime


class TripStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        with self._transaction() as db:
            db.executescript(SCHEMA)

    def get_trip(self, space_id: str) -> Trip | None:
        with self._transaction() as db:
            row = db.execute(
                "SELECT * FROM trips WHERE space_id = ?", (space_id,)
            ).fetchone()
            if row is None:
                return None
            return Trip(
                space_id=space_id,
                stage=TripStage(row["stage"]),
                destination=row["destination"],
                dates=_load_dates(row),
                members=_load_members(db, space_id),
                open_poll=_load_open_poll(db, space_id),
                itinerary=_load_itinerary(db, space_id),
                expenses=_load_expenses(db, space_id),
                settlements=_load_settlements(db, space_id),
                pending_receipt=_load_pending_receipt(db, space_id),
                place_suggestions=_load_place_suggestions(db, space_id),
            )

    def create_trip(self, space_id: str) -> None:
        with self._transaction() as db:
            db.execute(
                "INSERT INTO trips (space_id, stage, created_at) VALUES (?, ?, ?)",
                (
                    space_id,
                    TripStage.COLLECTING_PREFERENCES,
                    datetime.now().isoformat(),
                ),
            )

    def delete_trip(self, space_id: str) -> None:
        """Forgets everything about one chat, so its next message starts over."""
        with self._transaction() as db:
            db.execute(
                "DELETE FROM votes WHERE poll_id IN "
                "(SELECT id FROM polls WHERE space_id = ?)",
                (space_id,),
            )
            # Table names come from TABLES_BY_SPACE, never from user input.
            for table in TABLES_BY_SPACE:
                db.execute(f"DELETE FROM {table} WHERE space_id = ?", (space_id,))

    def add_members(self, space_id: str, phones: list[str]) -> None:
        """Adds anyone not already on the trip. Existing members are untouched."""
        with self._transaction() as db:
            db.executemany(
                "INSERT OR IGNORE INTO members (space_id, phone) VALUES (?, ?)",
                [(space_id, phone) for phone in phones],
            )

    def save_preferences(
        self, space_id: str, phone: str, update: PreferenceUpdate
    ) -> None:
        """Overwrites only the fields the update mentions."""
        changed = {
            field: value for field, value in asdict(update).items() if value is not None
        }
        if not changed:
            return
        if "must_haves" in changed:
            changed["must_haves"] = json.dumps(changed["must_haves"])
        for field in ("available_from", "available_to"):
            if field in changed:
                changed[field] = changed[field].isoformat()

        # Column names come from PreferenceUpdate's fields, never from user input.
        assignments = ", ".join(f"{column} = ?" for column in changed)
        with self._transaction() as db:
            db.execute(
                f"UPDATE members SET {assignments} WHERE space_id = ? AND phone = ?",
                (*changed.values(), space_id, phone),
            )

    def open_poll(self, space_id: str, options: list[DestinationOption]) -> None:
        with self._transaction() as db:
            db.execute(
                "INSERT INTO polls (space_id, options, is_open) VALUES (?, ?, 1)",
                (space_id, json.dumps([asdict(option) for option in options])),
            )
            db.execute(
                "UPDATE trips SET stage = ? WHERE space_id = ?",
                (TripStage.VOTING, space_id),
            )

    def record_vote(self, poll_id: int, phone: str, option_index: int) -> None:
        with self._transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO votes (poll_id, phone, option_index) "
                "VALUES (?, ?, ?)",
                (poll_id, phone, option_index),
            )

    def close_poll(
        self, poll_id: int, destination: str, dates: DateWindow | None
    ) -> None:
        with self._transaction() as db:
            space_id = db.execute(
                "SELECT space_id FROM polls WHERE id = ?", (poll_id,)
            ).fetchone()["space_id"]
            db.execute("UPDATE polls SET is_open = 0 WHERE id = ?", (poll_id,))
            db.execute(
                "UPDATE trips SET stage = ?, destination = ?, starts_on = ?, "
                "ends_on = ? WHERE space_id = ?",
                (
                    TripStage.DESTINATION_CHOSEN,
                    destination,
                    dates.start.isoformat() if dates else None,
                    dates.end.isoformat() if dates else None,
                    space_id,
                ),
            )

    def lock_in_destination(
        self, space_id: str, destination: str, dates: DateWindow | None
    ) -> None:
        """Sets the trip's destination and dates, closing any open poll."""
        with self._transaction() as db:
            db.execute(
                "UPDATE polls SET is_open = 0 WHERE space_id = ? AND is_open = 1",
                (space_id,),
            )
            db.execute(
                "UPDATE trips SET stage = ?, destination = ?, starts_on = ?, "
                "ends_on = ? WHERE space_id = ?",
                (
                    TripStage.DESTINATION_CHOSEN,
                    destination,
                    dates.start.isoformat() if dates else None,
                    dates.end.isoformat() if dates else None,
                    space_id,
                ),
            )

    def replace_itinerary(self, space_id: str, days: list[ItineraryDay]) -> None:
        with self._transaction() as db:
            db.execute("DELETE FROM itinerary_days WHERE space_id = ?", (space_id,))
            db.executemany(
                "INSERT INTO itinerary_days (space_id, day, plan) VALUES (?, ?, ?)",
                [(space_id, day.day.isoformat(), day.plan) for day in days],
            )

    def add_expense(
        self, space_id: str, payer_phone: str, amount_cents: int, description: str
    ) -> int:
        """Saves a new expense and returns its ID."""
        with self._transaction() as db:
            cursor = db.execute(
                "INSERT INTO expenses (space_id, payer_phone, amount_cents, "
                "description) VALUES (?, ?, ?, ?)",
                (space_id, payer_phone, amount_cents, description),
            )
            return cursor.lastrowid

    def remove_expense(self, space_id: str, expense_id: int) -> None:
        with self._transaction() as db:
            db.execute(
                "DELETE FROM expenses WHERE space_id = ? AND id = ?",
                (space_id, expense_id),
            )

    def save_pending_receipt(self, space_id: str, receipt: PendingReceipt) -> None:
        with self._transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO pending_receipts "
                "(space_id, payer_phone, merchant, total_cents) VALUES (?, ?, ?, ?)",
                (space_id, receipt.payer_phone, receipt.merchant, receipt.total_cents),
            )

    def clear_pending_receipt(self, space_id: str) -> None:
        with self._transaction() as db:
            db.execute("DELETE FROM pending_receipts WHERE space_id = ?", (space_id,))

    def replace_place_suggestions(self, space_id: str, places: list[Place]) -> None:
        with self._transaction() as db:
            db.execute("DELETE FROM place_suggestions WHERE space_id = ?", (space_id,))
            db.executemany(
                "INSERT INTO place_suggestions (space_id, position, place_id, name, "
                "latitude, longitude, price, summary) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        space_id,
                        position,
                        place.place_id,
                        place.name,
                        place.location.latitude,
                        place.location.longitude,
                        place.price,
                        place.summary,
                    )
                    for position, place in enumerate(places)
                ],
            )

    def clear_place_suggestions(self, space_id: str) -> None:
        with self._transaction() as db:
            db.execute("DELETE FROM place_suggestions WHERE space_id = ?", (space_id,))

    def add_settlement(self, space_id: str, settlement: Settlement) -> None:
        with self._transaction() as db:
            db.execute(
                "INSERT INTO settlements (space_id, payer_phone, payee_phone, "
                "amount_cents) VALUES (?, ?, ?, ?)",
                (
                    space_id,
                    settlement.payer_phone,
                    settlement.payee_phone,
                    settlement.amount_cents,
                ),
            )

    def log_message(
        self, space_id: str, sender_phone: str | None, text: str, sent_at: datetime
    ) -> None:
        with self._transaction() as db:
            db.execute(
                "INSERT INTO chat_log (space_id, sender_phone, text, sent_at) "
                "VALUES (?, ?, ?, ?)",
                (space_id, sender_phone, text, sent_at.isoformat()),
            )

    def save_media(self, space_id: str, media: SharedMedia) -> None:
        with self._transaction() as db:
            db.execute(
                "INSERT INTO media (space_id, id, kind, original_path, "
                "readable_path, transcript) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    space_id,
                    media.id,
                    media.kind,
                    str(media.original_path),
                    str(media.readable_path),
                    media.transcript,
                ),
            )

    def find_media(self, space_id: str, media_id: str) -> SharedMedia | None:
        """A photo or voice note sent in this chat, or None if it has none by
        that ID."""
        with self._transaction() as db:
            row = db.execute(
                "SELECT * FROM media WHERE space_id = ? AND id = ?",
                (space_id, media_id),
            ).fetchone()
        if row is None:
            return None
        return SharedMedia(
            id=row["id"],
            kind=MediaKind(row["kind"]),
            original_path=Path(row["original_path"]),
            readable_path=Path(row["readable_path"]),
            transcript=row["transcript"],
        )

    def has_scout_spoken(self, space_id: str) -> bool:
        """Whether scout has sent anything in the chat yet."""
        with self._transaction() as db:
            row = db.execute(
                "SELECT 1 FROM chat_log WHERE space_id = ? AND sender_phone IS NULL",
                (space_id,),
            ).fetchone()
        return row is not None

    def chat_history(self, space_id: str) -> list[LoggedMessage]:
        """Every message in the chat since scout joined, oldest first."""
        with self._transaction() as db:
            rows = db.execute(
                "SELECT sender_phone, text, sent_at FROM chat_log "
                "WHERE space_id = ? ORDER BY id",
                (space_id,),
            ).fetchall()
        return [
            LoggedMessage(
                row["sender_phone"], row["text"], datetime.fromisoformat(row["sent_at"])
            )
            for row in rows
        ]

    def recent_messages(self, space_id: str, limit: int) -> list[LoggedMessage]:
        """The latest messages in the chat, oldest first."""
        with self._transaction() as db:
            rows = db.execute(
                "SELECT sender_phone, text, sent_at FROM chat_log "
                "WHERE space_id = ? ORDER BY id DESC LIMIT ?",
                (space_id, limit),
            ).fetchall()
        return [
            LoggedMessage(
                row["sender_phone"], row["text"], datetime.fromisoformat(row["sent_at"])
            )
            for row in reversed(rows)
        ]

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        # A fresh connection per operation keeps the store safe to call from
        # the web server's worker threads.
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _load_dates(trip_row: sqlite3.Row) -> DateWindow | None:
    if trip_row["starts_on"] is None:
        return None
    return DateWindow(
        date.fromisoformat(trip_row["starts_on"]),
        date.fromisoformat(trip_row["ends_on"]),
    )


def _load_members(db: sqlite3.Connection, space_id: str) -> list[Member]:
    rows = db.execute(
        "SELECT * FROM members WHERE space_id = ? ORDER BY rowid", (space_id,)
    ).fetchall()
    return [
        Member(
            phone=row["phone"],
            display_name=row["display_name"],
            available_from=_parse_date(row["available_from"]),
            available_to=_parse_date(row["available_to"]),
            budget_usd=row["budget_usd"],
            home_city=row["home_city"],
            must_haves=json.loads(row["must_haves"]),
        )
        for row in rows
    ]


def _load_open_poll(db: sqlite3.Connection, space_id: str) -> Poll | None:
    row = db.execute(
        "SELECT * FROM polls WHERE space_id = ? AND is_open = 1", (space_id,)
    ).fetchone()
    if row is None:
        return None
    votes = db.execute(
        "SELECT phone, option_index FROM votes WHERE poll_id = ?", (row["id"],)
    ).fetchall()
    return Poll(
        id=row["id"],
        options=[DestinationOption(**option) for option in json.loads(row["options"])],
        votes={vote["phone"]: vote["option_index"] for vote in votes},
    )


def _load_itinerary(db: sqlite3.Connection, space_id: str) -> list[ItineraryDay]:
    rows = db.execute(
        "SELECT day, plan FROM itinerary_days WHERE space_id = ? ORDER BY day",
        (space_id,),
    ).fetchall()
    return [ItineraryDay(date.fromisoformat(row["day"]), row["plan"]) for row in rows]


def _load_expenses(db: sqlite3.Connection, space_id: str) -> list[Expense]:
    rows = db.execute(
        "SELECT id, payer_phone, amount_cents, description FROM expenses "
        "WHERE space_id = ? ORDER BY id",
        (space_id,),
    ).fetchall()
    return [
        Expense(
            id=row["id"],
            payer_phone=row["payer_phone"],
            amount_cents=row["amount_cents"],
            description=row["description"],
        )
        for row in rows
    ]


def _load_settlements(db: sqlite3.Connection, space_id: str) -> list[Settlement]:
    rows = db.execute(
        "SELECT payer_phone, payee_phone, amount_cents FROM settlements "
        "WHERE space_id = ? ORDER BY id",
        (space_id,),
    ).fetchall()
    return [
        Settlement(
            payer_phone=row["payer_phone"],
            payee_phone=row["payee_phone"],
            amount_cents=row["amount_cents"],
        )
        for row in rows
    ]


def _load_pending_receipt(
    db: sqlite3.Connection, space_id: str
) -> PendingReceipt | None:
    row = db.execute(
        "SELECT payer_phone, merchant, total_cents FROM pending_receipts "
        "WHERE space_id = ?",
        (space_id,),
    ).fetchone()
    if row is None:
        return None
    return PendingReceipt(row["payer_phone"], row["merchant"], row["total_cents"])


def _load_place_suggestions(db: sqlite3.Connection, space_id: str) -> list[Place]:
    rows = db.execute(
        "SELECT * FROM place_suggestions WHERE space_id = ? ORDER BY position",
        (space_id,),
    ).fetchall()
    return [
        Place(
            place_id=row["place_id"],
            name=row["name"],
            location=Coordinates(row["latitude"], row["longitude"]),
            price=row["price"],
            summary=row["summary"],
        )
        for row in rows
    ]


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
