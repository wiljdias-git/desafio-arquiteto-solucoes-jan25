#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
VENV_PIP="$ROOT_DIR/.venv/bin/pip"
UVICORN="$ROOT_DIR/.venv/bin/uvicorn"
DB_PATH="$ROOT_DIR/data/demo-real.db"
TRANSACTIONS_PORT=18080
BALANCE_PORT=18081
TRANSACTIONS_LOG="$ROOT_DIR/data/demo-transactions.log"
BALANCE_LOG="$ROOT_DIR/data/demo-balance.log"

cleanup() {
  if [[ -n "${BALANCE_PID:-}" ]]; then
    kill "$BALANCE_PID" 2>/dev/null || true
    wait "$BALANCE_PID" 2>/dev/null || true
  fi
  if [[ -n "${TRANSACTIONS_PID:-}" ]]; then
    kill "$TRANSACTIONS_PID" 2>/dev/null || true
    wait "$TRANSACTIONS_PID" 2>/dev/null || true
  fi
}

wait_for_url() {
  local url="$1"
  local max_attempts="${2:-60}"
  local attempt=1

  while (( attempt <= max_attempts )); do
    if curl --silent --fail "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
    attempt=$((attempt + 1))
  done

  echo "Timeout aguardando $url" >&2
  return 1
}

trap cleanup EXIT

mkdir -p "$ROOT_DIR/data"
rm -f "$DB_PATH" "$DB_PATH-shm" "$DB_PATH-wal" "$TRANSACTIONS_LOG" "$BALANCE_LOG"

if [[ ! -x "$VENV_PYTHON" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
  "$VENV_PIP" install -r "$ROOT_DIR/requirements.txt"
fi

echo "==> Iniciando Transactions Service"
CASHFLOW_DB_PATH="$DB_PATH" "$UVICORN" services.transactions_service.main:app \
  --host 127.0.0.1 --port "$TRANSACTIONS_PORT" >"$TRANSACTIONS_LOG" 2>&1 &
TRANSACTIONS_PID=$!
wait_for_url "http://127.0.0.1:${TRANSACTIONS_PORT}/health"

echo "==> Iniciando Balance Service"
CASHFLOW_DB_PATH="$DB_PATH" BALANCE_WORKER_POLL_INTERVAL_SECONDS=0.1 \
  "$UVICORN" services.balance_service.main:app \
  --host 127.0.0.1 --port "$BALANCE_PORT" >"$BALANCE_LOG" 2>&1 &
BALANCE_PID=$!
wait_for_url "http://127.0.0.1:${BALANCE_PORT}/health"

echo "==> Registrando lancamentos iniciais"
curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa"}'
echo
curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor"}'
echo
sleep 1

echo "==> Saldo consolidado inicial"
curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25"
echo

echo "==> Derrubando Balance Service"
kill "$BALANCE_PID"
wait "$BALANCE_PID" 2>/dev/null || true
unset BALANCE_PID

echo "==> Enviando lancamentos com consolidado offline"
curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"credit","amount":"10.00","date":"2026-01-25","description":"Venda com consolidado offline"}'
echo
curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"debit","amount":"2.00","date":"2026-01-25","description":"Despesa com consolidado offline"}'
echo

echo "==> Health do Transactions Service com backlog pendente"
curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health"
echo

echo "==> Reiniciando Balance Service"
CASHFLOW_DB_PATH="$DB_PATH" BALANCE_WORKER_POLL_INTERVAL_SECONDS=0.1 \
  "$UVICORN" services.balance_service.main:app \
  --host 127.0.0.1 --port "$BALANCE_PORT" >"$BALANCE_LOG" 2>&1 &
BALANCE_PID=$!
wait_for_url "http://127.0.0.1:${BALANCE_PORT}/health"
sleep 1

echo "==> Saldo consolidado apos recuperacao"
curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25"
echo

echo "==> Health final"
curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health"
echo
curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/health"
echo

echo "==> Carga no Balance Service"
CASHFLOW_DB_PATH="$DB_PATH" "$VENV_PYTHON" "$ROOT_DIR/scripts/load_balance_service.py" \
  --url "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25" \
  --requests 100 --concurrency 50

echo "==> Logs"
echo "Transactions log: $TRANSACTIONS_LOG"
echo "Balance log: $BALANCE_LOG"

