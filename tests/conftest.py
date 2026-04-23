from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services.common.settings import AppSettings
from services.balance_service.main import create_app as create_balance_app
from services.transactions_service.main import create_app as create_transactions_app


TEST_DESCRIPTIONS: dict[str, str] = {}
TEST_RESULTS: list[tuple[str, str, float]] = []
TERMINAL_REPORTER: Any = None


def _describe_test(item: pytest.Item) -> str:
    test_object = getattr(item, "obj", None)
    docstring = inspect.getdoc(test_object) if test_object is not None else None
    if docstring:
        return docstring.splitlines()[0].strip()
    return item.name.replace("_", " ")


def pytest_configure(config: pytest.Config) -> None:
    global TERMINAL_REPORTER
    TERMINAL_REPORTER = config.pluginmanager.get_plugin("terminalreporter")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    TEST_DESCRIPTIONS.clear()
    TEST_RESULTS.clear()
    for item in items:
        TEST_DESCRIPTIONS[item.nodeid] = _describe_test(item)


@pytest.hookimpl(tryfirst=True)
def pytest_report_teststatus(report: pytest.TestReport, config: pytest.Config):
    if report.when != "call":
        return None
    if report.passed:
        return ("passed", " ", "PASS")
    if report.failed:
        return ("failed", " ", "FAIL")
    if report.skipped:
        return ("skipped", " ", "SKIP")
    return None


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call":
        return

    outcome = "PASS"
    if report.failed:
        outcome = "FAIL"
    elif report.skipped:
        outcome = "SKIP"

    TEST_RESULTS.append((outcome, report.nodeid, report.duration))

    if TERMINAL_REPORTER is None:
        return

    description = TEST_DESCRIPTIONS.get(report.nodeid, report.nodeid)
    TERMINAL_REPORTER.write_line(f"[{outcome}] {description} ({report.duration:.2f}s)")


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    if not TEST_RESULTS:
        return

    total = len(TEST_RESULTS)
    passed = sum(1 for outcome, _, _ in TEST_RESULTS if outcome == "PASS")
    failed = sum(1 for outcome, _, _ in TEST_RESULTS if outcome == "FAIL")
    skipped = sum(1 for outcome, _, _ in TEST_RESULTS if outcome == "SKIP")

    terminalreporter.write_sep("=", "Resumo humano da validacao")
    terminalreporter.write_line(f"Total de cenarios: {total}")
    terminalreporter.write_line(f"Aprovados: {passed}")
    terminalreporter.write_line(f"Falhas: {failed}")
    terminalreporter.write_line(f"Pulados: {skipped}")
    terminalreporter.write_line("")
    terminalreporter.write_line("Leitura por cenario:")
    for outcome, nodeid, duration in TEST_RESULTS:
        description = TEST_DESCRIPTIONS.get(nodeid, nodeid)
        terminalreporter.write_line(f"  [{outcome}] {description} ({duration:.2f}s)")
    terminalreporter.write_line(
        "Leitura recomendada: cada linha [PASS]/[FAIL]/[SKIP] descreve o comportamento validado."
    )


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
