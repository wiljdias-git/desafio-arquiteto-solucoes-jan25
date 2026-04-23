from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_entries (
    id TEXT PRIMARY KEY,
    entry_date TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK(entry_type IN ('credit', 'debit')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    description TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consolidation_backlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL UNIQUE,
    entry_date TEXT NOT NULL,
    signed_amount_cents INTEGER NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0 CHECK(processed IN (0, 1)),
    created_at TEXT NOT NULL,
    processed_at TEXT,
    FOREIGN KEY(entry_id) REFERENCES ledger_entries(id)
);

CREATE TABLE IF NOT EXISTS daily_balances (
    entry_date TEXT PRIMARY KEY,
    balance_cents INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def initialize_database(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, check_same_thread=False, timeout=30) as connection:
        connection.execute("PRAGMA busy_timeout=30000;")
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA foreign_keys=ON;")
        connection.executescript(SCHEMA)
        connection.commit()


@contextmanager
def get_connection(db_path: str) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000;")
    connection.execute("PRAGMA foreign_keys=ON;")
    try:
        yield connection
    finally:
        connection.close()
