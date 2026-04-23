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


def parse_key_value_output(output: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for chunk in output.strip().split():
        key, value = chunk.split("=", 1)
        parsed[key] = value
    return parsed


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


@dataclass(frozen=True)
class StartupState:
    transactions_health: dict[str, Any]
    balance_health: dict[str, Any]


@dataclass(frozen=True)
class InitialFlowState:
    entries: list[dict[str, Any]]
    expected_count: int
    balance: dict[str, Any]
    expected_balance: Decimal
    balances: list[dict[str, Any]]


@dataclass(frozen=True)
class FailureState:
    transactions_health: dict[str, Any]
    expected_pending_backlog: int


@dataclass(frozen=True)
class RecoveryState:
    balance: dict[str, Any]
    expected_balance: Decimal
    entries: list[dict[str, Any]]
    expected_count: int
    balances: list[dict[str, Any]]
    transactions_health: dict[str, Any]
    balance_health: dict[str, Any]


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

    def transactions_health_url(self) -> str:
        return f"http://127.0.0.1:{self.config.transactions_port}/health"

    def balance_health_url(self) -> str:
        return f"http://127.0.0.1:{self.config.balance_port}/health"

    def entries_url(self) -> str:
        return (
            f"http://127.0.0.1:{self.config.transactions_port}/entries"
            f"?entry_date={self.config.demo_date}"
        )

    def balance_url(self) -> str:
        return f"http://127.0.0.1:{self.config.balance_port}/balances/{self.config.demo_date}"

    def balance_list_url(self) -> str:
        return (
            f"http://127.0.0.1:{self.config.balance_port}/balances"
            f"?start_date={self.config.demo_date}&end_date={self.config.demo_date}"
        )

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

    def _show_status_payload(
        self, payload: Any, expected_pending: int | None
    ) -> bool:
        if not (isinstance(payload, dict) and {"status", "pending_backlog_entries"} <= payload.keys()):
            return False

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
        return True

    def _show_entry_payload(self, payload: Any, expected_amount: Decimal | None) -> bool:
        if not (isinstance(payload, dict) and {"type", "amount", "date"} <= payload.keys()):
            return False

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
        return True

    def _show_balance_payload(self, payload: Any, expected_balance: Decimal | None) -> bool:
        if not (isinstance(payload, dict) and {"balance", "date"} <= payload.keys()):
            return False

        print(f"  -> Saldo retornado={payload['balance']} para a data {payload['date']}.")
        if expected_balance is not None:
            delta = Decimal(payload["balance"]) - expected_balance
            print(
                "  -> Comparação: "
                f"esperado={format_decimal(expected_balance)}; diferença={format_decimal(delta)}."
            )
        return True

    def _show_list_payload(self, payload: Any, expected_count: int | None) -> None:
        if not isinstance(payload, list):
            return

        if payload and isinstance(payload[0], dict) and {"type", "amount"} <= payload[0].keys():
            credit_total = sum(
                (Decimal(item["amount"]) for item in payload if item["type"] == "credit"),
                start=Decimal("0.00"),
            )
            debit_total = sum(
                (Decimal(item["amount"]) for item in payload if item["type"] == "debit"),
                start=Decimal("0.00"),
            )
            net_total = credit_total - debit_total
            print(
                "  -> O extrato retornou "
                f"{len(payload)} lançamento(s): créditos={format_decimal(credit_total)}; "
                f"débitos={format_decimal(debit_total)}; líquido={format_decimal(net_total)}."
            )
        else:
            rendered = ", ".join(f"{item['date']}={item['balance']}" for item in payload) or "nenhum saldo"
            print(f"  -> A consulta por intervalo retornou {len(payload)} item(ns): {rendered}.")

        if expected_count is not None:
            print(
                "  -> Comparação: "
                f"quantidade esperada={expected_count}; retornada={len(payload)}."
            )

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

        if self._show_status_payload(payload, expected_pending):
            return

        if self._show_entry_payload(payload, expected_amount):
            return

        if self._show_balance_payload(payload, expected_balance):
            return

        self._show_list_payload(payload, expected_count)

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

        parts = parse_key_value_output(completed.stdout)
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

    def prepare_demo_files(self) -> None:
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

    def print_intro(self) -> None:
        self.section("DEMONSTRACAO AUTOMATIZADA DO DESAFIO")
        print(
            "Objetivo: executar uma prova real, com avaliacao dinamica baseada nos retornos da API."
        )
        print(
            "Configuracao desta execucao: "
            f"data={self.config.demo_date}, "
            f"porta transactions={self.config.transactions_port}, "
            f"porta balance={self.config.balance_port}."
        )

    def startup_phase(self, client: httpx.Client) -> StartupState:
        self.section("1) SUBIDA DOS SERVICOS")
        self.step(f"Iniciando transactions-service em 127.0.0.1:{self.config.transactions_port}")
        self.start_service(
            "services.transactions_service.main:app",
            self.config.transactions_port,
            self.config.transactions_log,
        )
        self.wait_for_url(client, self.transactions_health_url())

        self.step(f"Iniciando balance-service em 127.0.0.1:{self.config.balance_port}")
        self.start_service(
            "services.balance_service.main:app",
            self.config.balance_port,
            self.config.balance_log,
        )
        self.wait_for_url(client, self.balance_health_url())

        transactions_health = self.get_json(client, self.transactions_health_url())
        balance_health = self.get_json(client, self.balance_health_url())
        self.assert_condition(
            "transactions-service iniciou saudavel",
            transactions_health["status"] == "ok" and transactions_health["pending_backlog_entries"] == 0,
            f"status={transactions_health['status']}, backlog={transactions_health['pending_backlog_entries']}",
        )
        self.assert_condition(
            "balance-service iniciou saudavel",
            balance_health["status"] == "ok" and balance_health["pending_backlog_entries"] == 0,
            f"status={balance_health['status']}, backlog={balance_health['pending_backlog_entries']}",
        )
        self.show_json_block("Health inicial do transactions-service", transactions_health, expected_pending=0)
        self.show_json_block("Health inicial do balance-service", balance_health, expected_pending=0)
        return StartupState(transactions_health=transactions_health, balance_health=balance_health)

    def _assert_entry_response(
        self, label: str, response: dict[str, Any], entry: EntrySpec
    ) -> None:
        self.assert_condition(
            label,
            response["type"] == entry.entry_type
            and response["amount"] == format_decimal(entry.amount)
            and response["date"] == self.config.demo_date,
            f"tipo={response['type']}, valor={response['amount']}, data={response['date']}",
        )

    def initial_consolidation_phase(self, client: httpx.Client) -> InitialFlowState:
        self.section("2) LANCAMENTOS INICIAIS E CONSOLIDACAO")
        first_entry = self.config.initial_entries[0]
        self.step(f"Registrando {first_entry.entry_type} inicial de {format_decimal(first_entry.amount)}")
        first_credit = self.post_entry(client, first_entry)
        self._assert_entry_response("credito inicial aceito", first_credit, first_entry)
        self.show_json_block("Credito inicial registrado", first_credit, expected_amount=first_entry.amount)

        second_entry = self.config.initial_entries[1]
        self.step(f"Registrando {second_entry.entry_type} inicial de {format_decimal(second_entry.amount)}")
        first_debit = self.post_entry(client, second_entry)
        self._assert_entry_response("debito inicial aceito", first_debit, second_entry)
        self.show_json_block("Debito inicial registrado", first_debit, expected_amount=second_entry.amount)

        time.sleep(1)

        entries = self.get_json(client, self.entries_url())
        expected_count = len(self.config.initial_entries)
        self.assert_condition(
            "extrato inicial consistente",
            len(entries) == expected_count,
            f"quantidade={len(entries)}",
        )
        self.show_json_block("Extrato inicial", entries, expected_count=expected_count)

        expected_balance = self.expected_balance(self.config.initial_entries)
        balance = self.get_json(client, self.balance_url())
        self.assert_condition(
            "saldo inicial consolidado correto",
            Decimal(balance["balance"]) == expected_balance,
            f"saldo={balance['balance']}, data={balance['date']}",
        )
        self.show_json_block("Saldo consolidado inicial", balance, expected_balance=expected_balance)

        balances = self.get_json(client, self.balance_list_url())
        self.assert_condition(
            "lista inicial de saldos consistente",
            len(balances) == 1 and Decimal(balances[0]["balance"]) == expected_balance,
            f"quantidade={len(balances)}",
        )
        self.show_json_block("Lista inicial de saldos", balances, expected_count=1)
        return InitialFlowState(
            entries=entries,
            expected_count=expected_count,
            balance=balance,
            expected_balance=expected_balance,
            balances=balances,
        )

    def failure_phase(self, client: httpx.Client) -> FailureState:
        self.section("3) FALHA CONTROLADA DO CONSOLIDADO")
        self.step("Derrubando balance-service para simular indisponibilidade")
        self.stop_last_process()
        print("[INFO] balance-service foi interrompido de forma controlada para validar a resiliencia.")

        self.step("Enviando novos lancamentos enquanto o consolidado esta offline")
        offline_credit_entry = self.config.offline_entries[0]
        offline_credit = self.post_entry(client, offline_credit_entry)
        self._assert_entry_response("credito offline aceito", offline_credit, offline_credit_entry)
        self.show_json_block(
            "Credito com consolidado offline",
            offline_credit,
            expected_amount=offline_credit_entry.amount,
        )

        offline_debit_entry = self.config.offline_entries[1]
        offline_debit = self.post_entry(client, offline_debit_entry)
        self._assert_entry_response("debito offline aceito", offline_debit, offline_debit_entry)
        self.show_json_block(
            "Debito com consolidado offline",
            offline_debit,
            expected_amount=offline_debit_entry.amount,
        )

        transactions_health = self.get_json(client, self.transactions_health_url())
        expected_pending_backlog = len(self.config.offline_entries)
        self.assert_condition(
            "transactions-service acumulou backlog pendente esperado",
            transactions_health["status"] == "ok"
            and transactions_health["pending_backlog_entries"] == expected_pending_backlog,
            f"status={transactions_health['status']}, backlog={transactions_health['pending_backlog_entries']}",
        )
        self.show_json_block(
            "Health com backlog pendente",
            transactions_health,
            expected_pending=expected_pending_backlog,
        )
        return FailureState(
            transactions_health=transactions_health,
            expected_pending_backlog=expected_pending_backlog,
        )

    def recovery_phase(self, client: httpx.Client) -> RecoveryState:
        self.section("4) RECUPERACAO AUTOMATICA DO BACKLOG")
        self.step(f"Subindo novamente balance-service em 127.0.0.1:{self.config.balance_port}")
        self.start_service(
            "services.balance_service.main:app",
            self.config.balance_port,
            self.config.balance_log,
        )
        self.wait_for_url(client, self.balance_health_url())
        time.sleep(1)

        all_entries = self.config.initial_entries + self.config.offline_entries
        expected_balance = self.expected_balance(all_entries)
        balance = self.get_json(client, self.balance_url())
        self.assert_condition(
            "saldo final recomposto corretamente",
            Decimal(balance["balance"]) == expected_balance,
            f"saldo={balance['balance']}, data={balance['date']}",
        )
        self.show_json_block("Saldo apos recuperacao", balance, expected_balance=expected_balance)

        entries = self.get_json(client, self.entries_url())
        expected_count = len(all_entries)
        self.assert_condition(
            "extrato final contem todos os lancamentos esperados",
            len(entries) == expected_count,
            f"quantidade={len(entries)}",
        )
        self.show_json_block("Extrato apos recuperacao", entries, expected_count=expected_count)

        balances = self.get_json(client, self.balance_list_url())
        self.assert_condition(
            "lista final de saldos permanece consistente",
            len(balances) == 1 and Decimal(balances[0]["balance"]) == expected_balance,
            f"quantidade={len(balances)}",
        )
        self.show_json_block("Lista final de saldos", balances, expected_count=1)

        transactions_health = self.get_json(client, self.transactions_health_url())
        balance_health = self.get_json(client, self.balance_health_url())
        self.assert_condition(
            "transactions-service terminou sem backlog",
            transactions_health["status"] == "ok" and transactions_health["pending_backlog_entries"] == 0,
            f"status={transactions_health['status']}, backlog={transactions_health['pending_backlog_entries']}",
        )
        self.assert_condition(
            "balance-service terminou saudavel",
            balance_health["status"] == "ok" and balance_health["pending_backlog_entries"] == 0,
            f"status={balance_health['status']}, backlog={balance_health['pending_backlog_entries']}",
        )
        self.show_json_block("Health final do transactions-service", transactions_health, expected_pending=0)
        self.show_json_block("Health final do balance-service", balance_health, expected_pending=0)
        return RecoveryState(
            balance=balance,
            expected_balance=expected_balance,
            entries=entries,
            expected_count=expected_count,
            balances=balances,
            transactions_health=transactions_health,
            balance_health=balance_health,
        )

    def print_final_summary(
        self,
        startup: StartupState,
        initial: InitialFlowState,
        failure: FailureState,
        recovery: RecoveryState,
        load_result: dict[str, str],
    ) -> None:
        self.section("RESUMO FINAL")
        self.summary_line(
            "Inicializacao dos servicos",
            startup.transactions_health["status"] == "ok"
            and startup.transactions_health["pending_backlog_entries"] == 0,
            (
                f"status inicial={startup.transactions_health['status']}; "
                f"backlog inicial={startup.transactions_health['pending_backlog_entries']}."
            ),
        )
        self.summary_line(
            "Consolidacao inicial",
            Decimal(initial.balance["balance"]) == initial.expected_balance
            and len(initial.entries) == initial.expected_count,
            (
                f"esperado={format_decimal(initial.expected_balance)}; "
                f"retornado={initial.balance['balance']}; "
                f"lancamentos={len(initial.entries)}."
            ),
        )
        self.summary_line(
            "Resiliencia durante a falha",
            failure.transactions_health["pending_backlog_entries"] == failure.expected_pending_backlog,
            (
                f"backlog esperado={failure.expected_pending_backlog}; "
                f"backlog observado={failure.transactions_health['pending_backlog_entries']}."
            ),
        )
        self.summary_line(
            "Recuperacao apos a falha",
            Decimal(recovery.balance["balance"]) == recovery.expected_balance
            and len(recovery.entries) == recovery.expected_count
            and recovery.transactions_health["pending_backlog_entries"] == 0,
            (
                f"saldo esperado={format_decimal(recovery.expected_balance)}; "
                f"saldo retornado={recovery.balance['balance']}; "
                f"lancamentos={len(recovery.entries)}; "
                f"backlog final={recovery.transactions_health['pending_backlog_entries']}."
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

    def run(self) -> None:
        self.print_intro()
        self.prepare_demo_files()

        with httpx.Client(timeout=5.0) as client:
            startup = self.startup_phase(client)
            initial = self.initial_consolidation_phase(client)
            failure = self.failure_phase(client)
            recovery = self.recovery_phase(client)
            self.section("5) TESTE DE CARGA NO CONSOLIDADO")
            load_result = self.run_load_test()
            self.print_final_summary(startup, initial, failure, recovery, load_result)


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
