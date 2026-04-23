from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    service_name: str
    db_path: str
    worker_poll_interval_seconds: float = 0.5
    worker_batch_size: int = 500


def load_settings(service_name: str) -> AppSettings:
    repository_root = Path(__file__).resolve().parents[2]
    default_db_path = repository_root / "data" / "cashflow.db"
    return AppSettings(
        service_name=service_name,
        db_path=os.getenv("CASHFLOW_DB_PATH", str(default_db_path)),
        worker_poll_interval_seconds=float(
            os.getenv("BALANCE_WORKER_POLL_INTERVAL_SECONDS", "0.5")
        ),
        worker_batch_size=int(os.getenv("BALANCE_WORKER_BATCH_SIZE", "500")),
    )

