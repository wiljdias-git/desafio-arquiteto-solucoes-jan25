from __future__ import annotations


def test_register_credit_and_debit_entries(transactions_client):
    """Registra credito e debito e comprova que os lancamentos ficam persistidos com backlog pendente para consolidacao."""
    credit_response = transactions_client.post(
        "/entries",
        json={
            "type": "credit",
            "amount": "100.00",
            "date": "2026-01-25",
            "description": "Venda no caixa",
        },
    )
    debit_response = transactions_client.post(
        "/entries",
        json={
            "type": "debit",
            "amount": "25.50",
            "date": "2026-01-25",
            "description": "Pagamento de fornecedor",
        },
    )

    assert credit_response.status_code == 201
    assert debit_response.status_code == 201

    entries_response = transactions_client.get("/entries", params={"entry_date": "2026-01-25"})
    health_response = transactions_client.get("/health")

    assert entries_response.status_code == 200
    assert len(entries_response.json()) == 2
    assert health_response.status_code == 200
    assert health_response.json()["pending_backlog_entries"] == 2


def test_transactions_service_accepts_requests_without_balance_service(transactions_client):
    """Mantem o servico transacional aceitando lancamentos mesmo sem o consolidado disponivel."""
    response = transactions_client.post(
        "/entries",
        json={
            "type": "credit",
            "amount": "10.00",
            "date": "2026-01-26",
            "description": "Venda avulsa",
        },
    )

    assert response.status_code == 201
    assert response.json()["type"] == "credit"


def test_transactions_service_rejects_invalid_amount(transactions_client):
    """Rejeita valores invalidos para proteger a integridade do fluxo de caixa."""
    response = transactions_client.post(
        "/entries",
        json={"type": "credit", "amount": "0.00", "date": "2026-01-26"},
    )

    assert response.status_code == 422
