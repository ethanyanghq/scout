"""Saves trips to SQLite so nothing is lost if scout restarts (PRD §9)."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from scout.trip import (
    DestinationOption,
    Member,
    Poll,
    PreferenceUpdate,
    Trip,
    TripStage,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    space_id    TEXT PRIMARY KEY,
    stage       TEXT NOT NULL,
    destination TEXT,
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

CREATE TABLE IF NOT EXISTS chat_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id     TEXT NOT NULL REFERENCES trips (space_id),
    sender_phone TEXT,
    text         TEXT NOT NULL,
    sent_at      TEXT NOT NULL
);
"""


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
                members=_load_members(db, space_id),
                open_poll=_load_open_poll(db, space_id),
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

    def close_poll(self, poll_id: int, destination: str) -> None:
        with self._transaction() as db:
            space_id = db.execute(
                "SELECT space_id FROM polls WHERE id = ?", (poll_id,)
            ).fetchone()["space_id"]
            db.execute("UPDATE polls SET is_open = 0 WHERE id = ?", (poll_id,))
            db.execute(
                "UPDATE trips SET stage = ?, destination = ? WHERE space_id = ?",
                (TripStage.DESTINATION_CHOSEN, destination, space_id),
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


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
