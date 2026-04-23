from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI

from services.common.database import initialize_database
from services.common.repositories import get_pending_backlog_count, list_entries, register_entry
from services.common.schemas import EntryCreate, EntryRead, HealthRead
from services.common.settings import AppSettings, load_settings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or load_settings("transactions-service")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(app_settings.db_path)
        yield

    app = FastAPI(
        title="Transactions Service",
        version="1.0.0",
        description="Servico responsavel pelo controle de lancamentos de debito e credito.",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthRead)
    def health() -> HealthRead:
        return HealthRead(
            service=app_settings.service_name,
            status="ok",
            pending_backlog_entries=get_pending_backlog_count(app_settings.db_path),
        )

    @app.post("/entries", response_model=EntryRead, status_code=201)
    def create_entry(payload: EntryCreate) -> EntryRead:
        return EntryRead.model_validate(register_entry(app_settings.db_path, payload))

    @app.get("/entries", response_model=list[EntryRead])
    def read_entries(entry_date: date | None = None) -> list[EntryRead]:
        return [
            EntryRead.model_validate(item)
            for item in list_entries(app_settings.db_path, entry_date)
        ]

    return app


app = create_app()
