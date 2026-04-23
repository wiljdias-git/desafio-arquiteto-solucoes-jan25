from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"


def _venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _module_available(interpreter: Path, module_name: str) -> bool:
    result = subprocess.run(
        [str(interpreter), "-c", f"import {module_name}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        cwd=ROOT_DIR,
    )
    return result.returncode == 0


def ensure_runtime() -> None:
    target_python = _venv_python_path()

    if not target_python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True, cwd=ROOT_DIR)

    required_modules = ("fastapi", "httpx", "pydantic", "uvicorn")
    if any(not _module_available(target_python, module) for module in required_modules):
        subprocess.run(
            [str(target_python), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
            check=True,
            cwd=ROOT_DIR,
        )

    current_python = Path(sys.executable).resolve()
    if current_python != target_python.resolve():
        completed = subprocess.run(
            [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=ROOT_DIR,
            env=os.environ.copy(),
            check=False,
        )
        raise SystemExit(completed.returncode)


ensure_runtime()

import httpx  # noqa: E402


def format_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class EntrySpec:
    entry_type: str
    amount: Decimal
    description: str


@dataclass
class DemoConfig:
    demo_date: str
    transactions_port: int
    balance_port: int
    db_path: Path
    transactions_log: Path
    balance_log: Path
    worker_poll_interval_seconds: float
    load_requests: int
    load_concurrency: int
    load_min_rps: Decimal
    load_max_loss_percentage: Decimal
    initial_entries: list[EntrySpec]
    offline_entries: list[EntrySpec]

    @classmethod
    def from_env(cls) -> "DemoConfig":
        transactions_port = int(os.getenv("TRANSACTIONS_PORT", str(find_free_port())))
        balance_port = int(os.getenv("BALANCE_PORT", str(find_free_port())))
        while balance_port == transactions_port:
            balance_port = find_free_port()

        return cls(
            demo_date=os.getenv("DEMO_DATE", "2026-01-25"),
            transactions_port=transactions_port,
            balance_port=balance_port,
            db_path=Path(os.getenv("DEMO_DB_PATH", str(ROOT_DIR / "data" / "demo-real.db"))),
            transactions_log=Path(
                os.getenv("TRANSACTIONS_LOG", str(ROOT_DIR / "data" / "demo-transactions.log"))
            ),
            balance_log=Path(
                os.getenv("BALANCE_LOG", str(ROOT_DIR / "data" / "demo-balance.log"))
            ),
            worker_poll_interval_seconds=float(
                os.getenv("BALANCE_WORKER_POLL_INTERVAL_SECONDS", "0.1")
            ),
            load_requests=int(os.getenv("LOAD_REQUESTS", "100")),
            load_concurrency=int(os.getenv("LOAD_CONCURRENCY", "50")),
            load_min_rps=Decimal(os.getenv("LOAD_MIN_RPS", "50")),
            load_max_loss_percentage=Decimal(os.getenv("LOAD_MAX_LOSS_PERCENTAGE", "5.0")),
            initial_entries=[
                EntrySpec(
                    "credit",
                    Decimal(os.getenv("INITIAL_CREDIT_AMOUNT", "100.00")),
                    os.getenv("INITIAL_CREDIT_DESCRIPTION", "Venda no caixa"),
                ),
                EntrySpec(
                    "debit",
                    Decimal(os.getenv("INITIAL_DEBIT_AMOUNT", "25.50")),
                    os.getenv("INITIAL_DEBIT_DESCRIPTION", "Pagamento de fornecedor"),
                ),
            ],
            offline_entries=[
                EntrySpec(
                    "credit",
                    Decimal(os.getenv("OFFLINE_CREDIT_AMOUNT", "10.00")),
                    os.getenv("OFFLINE_CREDIT_DESCRIPTION", "Venda com consolidado offline"),
                ),
                EntrySpec(
                    "debit",
                    Decimal(os.getenv("OFFLINE_DEBIT_AMOUNT", "2.00")),
                    os.getenv("OFFLINE_DEBIT_DESCRIPTION", "Despesa com consolidado offline"),
                ),
            ],
        )


class DemoError(RuntimeError):
    pass


class DemoRunner:
    def __init__(self, config: DemoConfig) -> None:
        self.config = config
        self.current_stage = "inicializacao"
        self.processes: list[subprocess.Popen[str]] = []
        self.log_handles: list[Any] = []

    def section(self, title: str) -> None:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)

    def step(self, title: str) -> None:
        self.current_stage = title
        print(f"\n[ETAPA] {title}")

    def cleanup(self) -> None:
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        self.processes.clear()

        for handle in self.log_handles:
            handle.close()
        self.log_handles.clear()

    def wait_for_url(self, client: httpx.Client, url: str, attempts: int = 60) -> None:
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                response = client.get(url)
                if response.status_code == 200:
                    return
            except Exception as exc:  # pragma: no cover - retry loop
                last_error = exc
            time.sleep(0.2)

        if last_error is not None:
            raise DemoError(f"Timeout aguardando {url}: {last_error}") from last_error
        raise DemoError(f"Timeout aguardando {url}")

    def start_service(self, module_path: str, port: int, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8")
        env = {
            **os.environ,
            "CASHFLOW_DB_PATH": str(self.config.db_path),
            "BALANCE_WORKER_POLL_INTERVAL_SECONDS": str(
                self.config.worker_poll_interval_seconds
            ),
        }
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                module_path,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT_DIR,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.processes.append(process)
        self.log_handles.append(log_handle)

    def stop_last_process(self) -> None:
        if not self.processes:
            return
        process = self.processes.pop()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self.log_handles:
            handle = self.log_handles.pop()
            handle.close()

    def assert_condition(self, label: str, condition: bool, detail: str) -> None:
        status = "OK" if condition else "FAIL"
        print(f"[{status}] {label}: {detail}")
        if not condition:
            raise DemoError(f"{label} | {detail}")

    def post_entry(self, client: httpx.Client, entry: EntrySpec) -> dict[str, Any]:
        payload = {
            "type": entry.entry_type,
            "amount": format_decimal(entry.amount),
            "date": self.config.demo_date,
            "description": entry.description,
        }
        response = client.post(
            f"http://127.0.0.1:{self.config.transactions_port}/entries",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def get_json(self, client: httpx.Client, url: str) -> Any:
        response = client.get(url)
        response.raise_for_status()
        return response.json()

    def expected_balance(self, entries: list[EntrySpec]) -> Decimal:
        total = Decimal("0.00")
        for entry in entries:
            if entry.entry_type == "credit":
                total += entry.amount
            else:
                total -= entry.amount
        return total

    def show_json_block(
        self,
        title: str,
        payload: Any,
        *,
        expected_amount: Decimal | None = None,
        expected_balance: Decimal | None = None,
        expected_count: int | None = None,
        expected_pending: int | None = None,
    ) -> None:
        print(f"[RESULTADO] {title}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        if isinstance(payload, dict) and {"status", "pending_backlog_entries"} <= payload.keys():
            print(
                f"  -> Status retornado={payload['status']}; backlog atual={payload['pending_backlog_entries']}."
            )
            if expected_pending is not None:
                print(f"  -> Comparação: backlog esperado={expected_pending}.")
            if int(payload["pending_backlog_entries"]) == 0:
                print("  -> Interpretação: o serviço está sincronizado e sem pendências.")
            else:
                print(
                    "  -> Interpretação: o serviço segue online com "
                    f"{payload['pending_backlog_entries']} item(ns) pendentes."
                )
            return

        if isinstance(payload, dict) and {"type", "amount", "date"} <= payload.keys():
            signal = "+" if payload["type"] == "credit" else "-"
            print(
                "  -> Lançamento aceito com "
                f"id={payload['id']}, efeito={signal}{payload['amount']}, data={payload['date']}."
            )
            if expected_amount is not None:
                print(
                    "  -> Comparação: "
                    f"valor esperado={format_decimal(expected_amount)}; valor retornado={payload['amount']}."
                )
            return

        if isinstance(payload, dict) and {"balance", "date"} <= payload.keys():
            print(f"  -> Saldo retornado={payload['balance']} para a data {payload['date']}.")
            if expected_balance is not None:
                delta = Decimal(payload["balance"]) - expected_balance
                print(
                    "  -> Comparação: "
                    f"esperado={format_decimal(expected_balance)}; diferença={format_decimal(delta)}."
                )
            return

        if isinstance(payload, list):
            if payload and isinstance(payload[0], dict) and {"type", "amount"} <= payload[0].keys():
                credits = sum(
                    Decimal(item["amount"]) for item in payload if item["type"] == "credit"
                )
                debits = sum(
                    Decimal(item["amount"]) for item in payload if item["type"] == "debit"
                )
                net = credits - debits
                print(
                    "  -> O extrato retornou "
                    f"{len(payload)} lançamento(s): créditos={format_decimal(credits)}; "
                    f"débitos={format_decimal(debits)}; líquido={format_decimal(net)}."
                )
            else:
                rendered = ", ".join(
                    f"{item['date']}={item['balance']}" for item in payload
                ) or "nenhum saldo"
                print(
                    f"  -> A consulta por intervalo retornou {len(payload)} item(ns): {rendered}."
                )
            if expected_count is not None:
                print(
                    "  -> Comparação: "
                    f"quantidade esperada={expected_count}; retornada={len(payload)}."
                )

    def run_load_test(self) -> dict[str, str]:
        command = [
            sys.executable,
            str(ROOT_DIR / "scripts" / "load_balance_service.py"),
            "--url",
            f"http://127.0.0.1:{self.config.balance_port}/balances/{self.config.demo_date}",
            "--requests",
            str(self.config.load_requests),
            "--concurrency",
            str(self.config.load_concurrency),
            "--min-rps",
            format_decimal(self.config.load_min_rps),
            "--max-loss-percentage",
            format_decimal(self.config.load_max_loss_percentage),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT_DIR,
            env={**os.environ, "CASHFLOW_DB_PATH": str(self.config.db_path)},
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise DemoError(completed.stderr.strip() or completed.stdout.strip())

        parts = dict(item.split("=", 1) for item in completed.stdout.strip().split())
        print("[RESULTADO] Teste de carga do balance-service")
        for key in ("total", "success", "failed", "loss_percent", "rps"):
            print(f"  - {key}: {parts[key]}")
        print(
            "  -> Comparação: "
            f"rps mínimo esperado={format_decimal(self.config.load_min_rps)}; "
            f"rps observado={parts['rps']}; "
            f"perda máxima esperada={format_decimal(self.config.load_max_loss_percentage)}%; "
            f"perda observada={parts['loss_percent']}%."
        )
        if (
            Decimal(parts["rps"]) >= self.config.load_min_rps
            and Decimal(parts["loss_percent"]) <= self.config.load_max_loss_percentage
        ):
            print("  -> Interpretação: a API sustentou a carga alvo com folga.")
        else:
            print("  -> Interpretação: a API não atingiu os critérios definidos.")
        return parts

    def summary_line(self, label: str, ok: bool, detail: str) -> None:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {label}: {detail}")

    def run(self) -> None:
        self.section("DEMONSTRACAO AUTOMATIZADA DO DESAFIO")
        print("Objetivo: executar uma prova real, com avaliacao dinamica baseada nos retornos da API.")
        print(
            "Configuracao desta execucao: "
            f"data={self.config.demo_date}, "
            f"porta transactions={self.config.transactions_port}, "
            f"porta balance={self.config.balance_port}."
        )

        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (
            self.config.db_path,
            self.config.db_path.with_name(self.config.db_path.name + "-shm"),
            self.config.db_path.with_name(self.config.db_path.name + "-wal"),
            self.config.transactions_log,
            self.config.balance_log,
        ):
            if path.exists():
                path.unlink()

        with httpx.Client(timeout=5.0) as client:
            self.section("1) SUBIDA DOS SERVICOS")
            self.step(
                f"Iniciando transactions-service em 127.0.0.1:{self.config.transactions_port}"
            )
            self.start_service(
                "services.transactions_service.main:app",
                self.config.transactions_port,
                self.config.transactions_log,
            )
            self.wait_for_url(client, f"http://127.0.0.1:{self.config.transactions_port}/health")

            self.step(f"Iniciando balance-service em 127.0.0.1:{self.config.balance_port}")
            self.start_service(
                "services.balance_service.main:app",
                self.config.balance_port,
                self.config.balance_log,
            )
            self.wait_for_url(client, f"http://127.0.0.1:{self.config.balance_port}/health")

            transactions_health_initial = self.get_json(
                client, f"http://127.0.0.1:{self.config.transactions_port}/health"
            )
            balance_health_initial = self.get_json(
                client, f"http://127.0.0.1:{self.config.balance_port}/health"
            )
            self.assert_condition(
                "transactions-service iniciou saudavel",
                transactions_health_initial["status"] == "ok"
                and transactions_health_initial["pending_backlog_entries"] == 0,
                (
                    f"status={transactions_health_initial['status']}, "
                    f"backlog={transactions_health_initial['pending_backlog_entries']}"
                ),
            )
            self.assert_condition(
                "balance-service iniciou saudavel",
                balance_health_initial["status"] == "ok"
                and balance_health_initial["pending_backlog_entries"] == 0,
                (
                    f"status={balance_health_initial['status']}, "
                    f"backlog={balance_health_initial['pending_backlog_entries']}"
                ),
            )
            self.show_json_block(
                "Health inicial do transactions-service",
                transactions_health_initial,
                expected_pending=0,
            )
            self.show_json_block(
                "Health inicial do balance-service",
                balance_health_initial,
                expected_pending=0,
            )

            self.section("2) LANCAMENTOS INICIAIS E CONSOLIDACAO")
            first_entry = self.config.initial_entries[0]
            self.step(f"Registrando {first_entry.entry_type} inicial de {format_decimal(first_entry.amount)}")
            first_credit = self.post_entry(client, first_entry)
            self.assert_condition(
                "credito inicial aceito",
                first_credit["type"] == first_entry.entry_type
                and first_credit["amount"] == format_decimal(first_entry.amount)
                and first_credit["date"] == self.config.demo_date,
                (
                    f"tipo={first_credit['type']}, "
                    f"valor={first_credit['amount']}, "
                    f"data={first_credit['date']}"
                ),
            )
            self.show_json_block(
                "Credito inicial registrado",
                first_credit,
                expected_amount=first_entry.amount,
            )

            second_entry = self.config.initial_entries[1]
            self.step(
                f"Registrando {second_entry.entry_type} inicial de {format_decimal(second_entry.amount)}"
            )
            first_debit = self.post_entry(client, second_entry)
            self.assert_condition(
                "debito inicial aceito",
                first_debit["type"] == second_entry.entry_type
                and first_debit["amount"] == format_decimal(second_entry.amount)
                and first_debit["date"] == self.config.demo_date,
                (
                    f"tipo={first_debit['type']}, "
                    f"valor={first_debit['amount']}, "
                    f"data={first_debit['date']}"
                ),
            )
            self.show_json_block(
                "Debito inicial registrado",
                first_debit,
                expected_amount=second_entry.amount,
            )

            time.sleep(1)

            entries_initial = self.get_json(
                client,
                f"http://127.0.0.1:{self.config.transactions_port}/entries?entry_date={self.config.demo_date}",
            )
            expected_initial_count = len(self.config.initial_entries)
            self.assert_condition(
                "extrato inicial consistente",
                len(entries_initial) == expected_initial_count,
                f"quantidade={len(entries_initial)}",
            )
            self.show_json_block(
                "Extrato inicial",
                entries_initial,
                expected_count=expected_initial_count,
            )

            expected_initial_balance = self.expected_balance(self.config.initial_entries)
            balance_initial = self.get_json(
                client, f"http://127.0.0.1:{self.config.balance_port}/balances/{self.config.demo_date}"
            )
            self.assert_condition(
                "saldo inicial consolidado correto",
                Decimal(balance_initial["balance"]) == expected_initial_balance,
                f"saldo={balance_initial['balance']}, data={balance_initial['date']}",
            )
            self.show_json_block(
                "Saldo consolidado inicial",
                balance_initial,
                expected_balance=expected_initial_balance,
            )

            balances_initial = self.get_json(
                client,
                (
                    f"http://127.0.0.1:{self.config.balance_port}/balances"
                    f"?start_date={self.config.demo_date}&end_date={self.config.demo_date}"
                ),
            )
            self.assert_condition(
                "lista inicial de saldos consistente",
                len(balances_initial) == 1
                and Decimal(balances_initial[0]["balance"]) == expected_initial_balance,
                f"quantidade={len(balances_initial)}",
            )
            self.show_json_block(
                "Lista inicial de saldos",
                balances_initial,
                expected_count=1,
            )

            self.section("3) FALHA CONTROLADA DO CONSOLIDADO")
            self.step("Derrubando balance-service para simular indisponibilidade")
            self.stop_last_process()
            print("[INFO] balance-service foi interrompido de forma controlada para validar a resiliencia.")

            self.step("Enviando novos lancamentos enquanto o consolidado esta offline")
            third_entry = self.config.offline_entries[0]
            offline_credit = self.post_entry(client, third_entry)
            self.assert_condition(
                "credito offline aceito",
                offline_credit["type"] == third_entry.entry_type
                and offline_credit["amount"] == format_decimal(third_entry.amount)
                and offline_credit["date"] == self.config.demo_date,
                (
                    f"tipo={offline_credit['type']}, "
                    f"valor={offline_credit['amount']}, "
                    f"data={offline_credit['date']}"
                ),
            )
            self.show_json_block(
                "Credito com consolidado offline",
                offline_credit,
                expected_amount=third_entry.amount,
            )

            fourth_entry = self.config.offline_entries[1]
            offline_debit = self.post_entry(client, fourth_entry)
            self.assert_condition(
                "debito offline aceito",
                offline_debit["type"] == fourth_entry.entry_type
                and offline_debit["amount"] == format_decimal(fourth_entry.amount)
                and offline_debit["date"] == self.config.demo_date,
                (
                    f"tipo={offline_debit['type']}, "
                    f"valor={offline_debit['amount']}, "
                    f"data={offline_debit['date']}"
                ),
            )
            self.show_json_block(
                "Debito com consolidado offline",
                offline_debit,
                expected_amount=fourth_entry.amount,
            )

            transactions_health_pending = self.get_json(
                client, f"http://127.0.0.1:{self.config.transactions_port}/health"
            )
            expected_pending_backlog = len(self.config.offline_entries)
            self.assert_condition(
                "transactions-service acumulou backlog pendente esperado",
                transactions_health_pending["status"] == "ok"
                and transactions_health_pending["pending_backlog_entries"]
                == expected_pending_backlog,
                (
                    f"status={transactions_health_pending['status']}, "
                    f"backlog={transactions_health_pending['pending_backlog_entries']}"
                ),
            )
            self.show_json_block(
                "Health com backlog pendente",
                transactions_health_pending,
                expected_pending=expected_pending_backlog,
            )

            self.section("4) RECUPERACAO AUTOMATICA DO BACKLOG")
            self.step(f"Subindo novamente balance-service em 127.0.0.1:{self.config.balance_port}")
            self.start_service(
                "services.balance_service.main:app",
                self.config.balance_port,
                self.config.balance_log,
            )
            self.wait_for_url(client, f"http://127.0.0.1:{self.config.balance_port}/health")
            time.sleep(1)

            all_entries = self.config.initial_entries + self.config.offline_entries
            expected_final_balance = self.expected_balance(all_entries)
            balance_recovered = self.get_json(
                client, f"http://127.0.0.1:{self.config.balance_port}/balances/{self.config.demo_date}"
            )
            self.assert_condition(
                "saldo final recomposto corretamente",
                Decimal(balance_recovered["balance"]) == expected_final_balance,
                f"saldo={balance_recovered['balance']}, data={balance_recovered['date']}",
            )
            self.show_json_block(
                "Saldo apos recuperacao",
                balance_recovered,
                expected_balance=expected_final_balance,
            )

            entries_recovered = self.get_json(
                client,
                f"http://127.0.0.1:{self.config.transactions_port}/entries?entry_date={self.config.demo_date}",
            )
            expected_final_count = len(all_entries)
            self.assert_condition(
                "extrato final contem todos os lancamentos esperados",
                len(entries_recovered) == expected_final_count,
                f"quantidade={len(entries_recovered)}",
            )
            self.show_json_block(
                "Extrato apos recuperacao",
                entries_recovered,
                expected_count=expected_final_count,
            )

            balances_recovered = self.get_json(
                client,
                (
                    f"http://127.0.0.1:{self.config.balance_port}/balances"
                    f"?start_date={self.config.demo_date}&end_date={self.config.demo_date}"
                ),
            )
            self.assert_condition(
                "lista final de saldos permanece consistente",
                len(balances_recovered) == 1
                and Decimal(balances_recovered[0]["balance"]) == expected_final_balance,
                f"quantidade={len(balances_recovered)}",
            )
            self.show_json_block(
                "Lista final de saldos",
                balances_recovered,
                expected_count=1,
            )

            transactions_health_final = self.get_json(
                client, f"http://127.0.0.1:{self.config.transactions_port}/health"
            )
            balance_health_final = self.get_json(
                client, f"http://127.0.0.1:{self.config.balance_port}/health"
            )
            self.assert_condition(
                "transactions-service terminou sem backlog",
                transactions_health_final["status"] == "ok"
                and transactions_health_final["pending_backlog_entries"] == 0,
                (
                    f"status={transactions_health_final['status']}, "
                    f"backlog={transactions_health_final['pending_backlog_entries']}"
                ),
            )
            self.assert_condition(
                "balance-service terminou saudavel",
                balance_health_final["status"] == "ok"
                and balance_health_final["pending_backlog_entries"] == 0,
                (
                    f"status={balance_health_final['status']}, "
                    f"backlog={balance_health_final['pending_backlog_entries']}"
                ),
            )
            self.show_json_block(
                "Health final do transactions-service",
                transactions_health_final,
                expected_pending=0,
            )
            self.show_json_block(
                "Health final do balance-service",
                balance_health_final,
                expected_pending=0,
            )

            self.section("5) TESTE DE CARGA NO CONSOLIDADO")
            load_result = self.run_load_test()

            self.section("RESUMO FINAL")
            self.summary_line(
                "Inicializacao dos servicos",
                transactions_health_initial["status"] == "ok"
                and transactions_health_initial["pending_backlog_entries"] == 0,
                (
                    f"status inicial={transactions_health_initial['status']}; "
                    f"backlog inicial={transactions_health_initial['pending_backlog_entries']}."
                ),
            )
            self.summary_line(
                "Consolidacao inicial",
                Decimal(balance_initial["balance"]) == expected_initial_balance
                and len(entries_initial) == expected_initial_count,
                (
                    f"esperado={format_decimal(expected_initial_balance)}; "
                    f"retornado={balance_initial['balance']}; "
                    f"lancamentos={len(entries_initial)}."
                ),
            )
            self.summary_line(
                "Resiliencia durante a falha",
                transactions_health_pending["pending_backlog_entries"]
                == expected_pending_backlog,
                (
                    f"backlog esperado={expected_pending_backlog}; "
                    f"backlog observado={transactions_health_pending['pending_backlog_entries']}."
                ),
            )
            self.summary_line(
                "Recuperacao apos a falha",
                Decimal(balance_recovered["balance"]) == expected_final_balance
                and len(entries_recovered) == expected_final_count
                and transactions_health_final["pending_backlog_entries"] == 0,
                (
                    f"saldo esperado={format_decimal(expected_final_balance)}; "
                    f"saldo retornado={balance_recovered['balance']}; "
                    f"lancamentos={len(entries_recovered)}; "
                    f"backlog final={transactions_health_final['pending_backlog_entries']}."
                ),
            )
            self.summary_line(
                "Teste de carga",
                Decimal(load_result["rps"]) >= self.config.load_min_rps
                and Decimal(load_result["loss_percent"]) <= self.config.load_max_loss_percentage,
                (
                    f"rps minimo={format_decimal(self.config.load_min_rps)}; "
                    f"rps observado={load_result['rps']}; "
                    f"perda maxima={format_decimal(self.config.load_max_loss_percentage)}%; "
                    f"perda observada={load_result['loss_percent']}%."
                ),
            )

            print("\nLogs gerados:")
            print(f"  - {self.config.transactions_log}")
            print(f"  - {self.config.balance_log}")
            print(f"Banco usado nesta execucao: {self.config.db_path}")


def main() -> None:
    config = DemoConfig.from_env()
    runner = DemoRunner(config)
    try:
        runner.run()
    except Exception as exc:
        runner.section("FALHA NA DEMONSTRACAO")
        print(f"[FAIL] Etapa atual: {runner.current_stage}")
        print(f"[FAIL] Erro: {exc}")
        print("\nLogs capturados:")
        print(f"  - {config.transactions_log}")
        print(f"  - {config.balance_log}")
        raise SystemExit(1) from exc
    finally:
        runner.cleanup()


if __name__ == "__main__":
    main()
