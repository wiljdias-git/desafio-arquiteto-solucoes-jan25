from __future__ import annotations

from fastapi.testclient import TestClient

from services.balance_service.main import create_app


def test_balance_service_processes_backlog_and_returns_daily_balance(
    transactions_client, balance_client
):
    transactions_client.post(
        "/entries",
        json={"type": "credit", "amount": "100.00", "date": "2026-01-25"},
    )
    transactions_client.post(
        "/entries",
        json={"type": "debit", "amount": "25.50", "date": "2026-01-25"},
    )

    process_response = balance_client.post("/internal/process-backlog")
    balance_response = balance_client.get("/balances/2026-01-25")
    health_response = balance_client.get("/health")

    assert process_response.status_code == 200
    assert process_response.json()["processed_entries"] == 2
    assert balance_response.status_code == 200
    assert balance_response.json()["balance"] == "74.50"
    assert health_response.json()["pending_backlog_entries"] == 0


def test_balance_service_catches_up_after_downtime(
    db_path, transactions_client, balance_settings
):
    transactions_client.post(
        "/entries",
        json={"type": "credit", "amount": "50.00", "date": "2026-01-27"},
    )
    transactions_client.post(
        "/entries",
        json={"type": "debit", "amount": "20.00", "date": "2026-01-27"},
    )

    balance_app = create_app(balance_settings)
    with TestClient(balance_app) as balance_client:
        balance_response = balance_client.get("/balances/2026-01-27")
        health_response = balance_client.get("/health")

    assert balance_response.json()["balance"] == "30.00"
    assert health_response.json()["pending_backlog_entries"] == 0
