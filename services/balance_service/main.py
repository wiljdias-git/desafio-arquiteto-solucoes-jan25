from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from threading import Lock

from fastapi import FastAPI

from services.common.database import initialize_database
from services.common.repositories import (
    get_daily_balance,
    get_pending_backlog_count,
    list_daily_balances,
    process_backlog_batch,
)
from services.common.schemas import BalanceRead, BacklogProcessResult, HealthRead
from services.common.settings import AppSettings, load_settings


async def _worker_loop(
    settings: AppSettings, stop_event: asyncio.Event, process_lock: Lock
) -> None:
    while not stop_event.is_set():
        with process_lock:
            process_backlog_batch(settings.db_path, settings.worker_batch_size)
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.worker_poll_interval_seconds
            )
        except asyncio.TimeoutError:
            continue


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or load_settings("balance-service")
    process_lock = Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(app_settings.db_path)
        stop_event = asyncio.Event()
        worker_task = asyncio.create_task(
            _worker_loop(app_settings, stop_event, process_lock)
        )
        app.state.process_lock = process_lock
        try:
            yield
        finally:
            stop_event.set()
            await worker_task

    app = FastAPI(
        title="Balance Service",
        version="1.0.0",
        description="Servico responsavel por consolidar e consultar saldo diario.",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthRead)
    def health() -> HealthRead:
        return HealthRead(
            service=app_settings.service_name,
            status="ok",
            pending_backlog_entries=get_pending_backlog_count(app_settings.db_path),
        )

    @app.get("/balances/{entry_date}", response_model=BalanceRead)
    def read_daily_balance(entry_date: date) -> BalanceRead:
        return BalanceRead.model_validate(get_daily_balance(app_settings.db_path, entry_date))

    @app.get("/balances", response_model=list[BalanceRead])
    def read_balances(
        start_date: date | None = None, end_date: date | None = None
    ) -> list[BalanceRead]:
        return [
            BalanceRead.model_validate(item)
            for item in list_daily_balances(app_settings.db_path, start_date, end_date)
        ]

    @app.post("/internal/process-backlog", response_model=BacklogProcessResult)
    def process_backlog() -> BacklogProcessResult:
        with app.state.process_lock:
            result = process_backlog_batch(
                app_settings.db_path, app_settings.worker_batch_size
            )
        return BacklogProcessResult.model_validate(result)

    return app


app = create_app()

