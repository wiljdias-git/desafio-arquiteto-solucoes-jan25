PYTHON ?= python3
VENV ?= .venv
VENV_BIN := $(VENV)/bin
PIP := $(VENV_BIN)/pip
PYTEST := $(VENV_BIN)/pytest
UVICORN := $(VENV_BIN)/uvicorn

.PHONY: venv install test run-transactions run-balance

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install -r requirements.txt

test:
	$(PYTEST)

run-transactions:
	$(UVICORN) services.transactions_service.main:app --host 0.0.0.0 --port 8000

run-balance:
	$(UVICORN) services.balance_service.main:app --host 0.0.0.0 --port 8001
