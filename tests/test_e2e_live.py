from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx


ROOT_DIR = Path(__file__).resolve().parents[1]


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_json(url: str, timeout_seconds: float = 15.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return response.json()
        except Exception as exc:  # pragma: no cover - retry loop
            last_error = exc
        time.sleep(0.2)
    if last_error is not None:
        raise last_error
    raise TimeoutError(f"Timeout aguardando resposta de {url}")


@contextmanager
def _run_service(module: str, port: int, env: dict[str, str]) -> Iterator[subprocess.Popen[str]]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            module,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_live_services_recover_backlog_after_balance_downtime(tmp_path: Path) -> None:
    db_path = tmp_path / "cashflow-live.db"
    transactions_port = _get_free_port()
    balance_port = _get_free_port()

    env = {
        **os.environ,
        "CASHFLOW_DB_PATH": str(db_path),
        "BALANCE_WORKER_POLL_INTERVAL_SECONDS": "0.1",
    }

    with _run_service("services.transactions_service.main:app", transactions_port, env):
        _wait_for_json(f"http://127.0.0.1:{transactions_port}/health")

        with _run_service("services.balance_service.main:app", balance_port, env):
            _wait_for_json(f"http://127.0.0.1:{balance_port}/health")

            first_credit = httpx.post(
                f"http://127.0.0.1:{transactions_port}/entries",
                json={
                    "type": "credit",
                    "amount": "100.00",
                    "date": "2026-01-25",
                    "description": "Venda no caixa",
                },
                timeout=5.0,
            )
            first_debit = httpx.post(
                f"http://127.0.0.1:{transactions_port}/entries",
                json={
                    "type": "debit",
                    "amount": "25.50",
                    "date": "2026-01-25",
                    "description": "Pagamento de fornecedor",
                },
                timeout=5.0,
            )
            assert first_credit.status_code == 201
            assert first_debit.status_code == 201

            deadline = time.time() + 10
            initial_balance: dict | None = None
            while time.time() < deadline:
                balance_response = httpx.get(
                    f"http://127.0.0.1:{balance_port}/balances/2026-01-25",
                    timeout=5.0,
                )
                initial_balance = balance_response.json()
                if initial_balance["balance"] == "74.50":
                    break
                time.sleep(0.2)

            assert initial_balance is not None
            assert initial_balance["balance"] == "74.50"

        offline_credit = httpx.post(
            f"http://127.0.0.1:{transactions_port}/entries",
            json={
                "type": "credit",
                "amount": "10.00",
                "date": "2026-01-25",
                "description": "Venda com consolidado offline",
            },
            timeout=5.0,
        )
        offline_debit = httpx.post(
            f"http://127.0.0.1:{transactions_port}/entries",
            json={
                "type": "debit",
                "amount": "2.00",
                "date": "2026-01-25",
                "description": "Despesa com consolidado offline",
            },
            timeout=5.0,
        )
        assert offline_credit.status_code == 201
        assert offline_debit.status_code == 201

        transactions_health = httpx.get(
            f"http://127.0.0.1:{transactions_port}/health", timeout=5.0
        ).json()
        assert transactions_health["pending_backlog_entries"] == 2

        with _run_service("services.balance_service.main:app", balance_port, env):
            _wait_for_json(f"http://127.0.0.1:{balance_port}/health")

            deadline = time.time() + 10
            recovered_balance: dict | None = None
            recovered_health: dict | None = None
            while time.time() < deadline:
                recovered_balance = httpx.get(
                    f"http://127.0.0.1:{balance_port}/balances/2026-01-25",
                    timeout=5.0,
                ).json()
                recovered_health = httpx.get(
                    f"http://127.0.0.1:{transactions_port}/health",
                    timeout=5.0,
                ).json()
                if (
                    recovered_balance["balance"] == "82.50"
                    and recovered_health["pending_backlog_entries"] == 0
                ):
                    break
                time.sleep(0.2)

            assert recovered_balance is not None
            assert recovered_health is not None
            assert recovered_balance["balance"] == "82.50"
            assert recovered_health["pending_backlog_entries"] == 0

