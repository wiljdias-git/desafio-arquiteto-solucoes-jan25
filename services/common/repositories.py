from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from services.common.database import get_connection
from services.common.schemas import EntryCreate, cents_to_decimal, amount_to_cents


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_entry(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["entry_type"],
        "amount": cents_to_decimal(row["amount_cents"]),
        "date": date.fromisoformat(row["entry_date"]),
        "description": row["description"],
        "created_at": datetime.fromisoformat(row["created_at"]),
    }


def _serialize_balance(entry_date: str, balance_cents: int, updated_at: str) -> dict[str, Any]:
    return {
        "date": date.fromisoformat(entry_date),
        "balance": cents_to_decimal(balance_cents),
        "updated_at": datetime.fromisoformat(updated_at),
    }


def register_entry(db_path: str, payload: EntryCreate) -> dict[str, Any]:
    now = _utc_now().isoformat()
    amount_cents = amount_to_cents(payload.amount)
    signed_amount_cents = amount_cents if payload.type == "credit" else -amount_cents
    entry_id = str(uuid4())

    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT INTO ledger_entries (id, entry_date, entry_type, amount_cents, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                payload.date.isoformat(),
                payload.type,
                amount_cents,
                payload.description,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO consolidation_backlog (entry_id, entry_date, signed_amount_cents, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (entry_id, payload.date.isoformat(), signed_amount_cents, now),
        )
        row = connection.execute(
            "SELECT * FROM ledger_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        connection.commit()

    return _serialize_entry(row)


def list_entries(db_path: str, entry_date: date | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM ledger_entries"
    parameters: list[Any] = []
    if entry_date is not None:
        query += " WHERE entry_date = ?"
        parameters.append(entry_date.isoformat())
    query += " ORDER BY created_at DESC"

    with get_connection(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_serialize_entry(row) for row in rows]


def get_pending_backlog_count(db_path: str) -> int:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM consolidation_backlog WHERE processed = 0"
        ).fetchone()
    return int(row["total"])


def process_backlog_batch(db_path: str, batch_size: int = 500) -> dict[str, int]:
    now = _utc_now().isoformat()
    with get_connection(db_path) as connection:
        pending_rows = connection.execute(
            """
            SELECT id, entry_date, signed_amount_cents
            FROM consolidation_backlog
            WHERE processed = 0
            ORDER BY id
            LIMIT ?
            """,
            (batch_size,),
        ).fetchall()

        if not pending_rows:
            return {"processed_entries": 0, "pending_entries": 0}

        connection.execute("BEGIN")
        for row in pending_rows:
            connection.execute(
                """
                INSERT INTO daily_balances (entry_date, balance_cents, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(entry_date) DO UPDATE SET
                    balance_cents = daily_balances.balance_cents + excluded.balance_cents,
                    updated_at = excluded.updated_at
                """,
                (row["entry_date"], row["signed_amount_cents"], now),
            )
            connection.execute(
                """
                UPDATE consolidation_backlog
                SET processed = 1, processed_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )

        pending_count = connection.execute(
            "SELECT COUNT(*) AS total FROM consolidation_backlog WHERE processed = 0"
        ).fetchone()
        connection.commit()

    return {
        "processed_entries": len(pending_rows),
        "pending_entries": int(pending_count["total"]),
    }


def get_daily_balance(db_path: str, entry_date: date) -> dict[str, Any]:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT entry_date, balance_cents, updated_at
            FROM daily_balances
            WHERE entry_date = ?
            """,
            (entry_date.isoformat(),),
        ).fetchone()

    if row is None:
        now = _utc_now().isoformat()
        return _serialize_balance(entry_date.isoformat(), 0, now)

    return _serialize_balance(row["entry_date"], row["balance_cents"], row["updated_at"])


def list_daily_balances(
    db_path: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT entry_date, balance_cents, updated_at FROM daily_balances WHERE 1 = 1"
    parameters: list[Any] = []
    if start_date is not None:
        query += " AND entry_date >= ?"
        parameters.append(start_date.isoformat())
    if end_date is not None:
        query += " AND entry_date <= ?"
        parameters.append(end_date.isoformat())
    query += " ORDER BY entry_date ASC"

    with get_connection(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [
        _serialize_balance(row["entry_date"], row["balance_cents"], row["updated_at"])
        for row in rows
    ]

