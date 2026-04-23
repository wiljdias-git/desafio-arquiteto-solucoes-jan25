from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.common.settings import AppSettings
from services.balance_service.main import create_app as create_balance_app
from services.transactions_service.main import create_app as create_transactions_app


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "cashflow.db")


@pytest.fixture
def transactions_settings(db_path: str) -> AppSettings:
    return AppSettings(service_name="transactions-service", db_path=db_path)


@pytest.fixture
def balance_settings(db_path: str) -> AppSettings:
    return AppSettings(
        service_name="balance-service",
        db_path=db_path,
        worker_poll_interval_seconds=3600,
    )


@pytest.fixture
def transactions_client(transactions_settings: AppSettings):
    app = create_transactions_app(transactions_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def balance_client(balance_settings: AppSettings):
    app = create_balance_app(balance_settings)
    with TestClient(app) as client:
        yield client

