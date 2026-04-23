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

ensure_runtime() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    python3 -m venv "$ROOT_DIR/.venv"
  fi

  if ! "$VENV_PYTHON" - <<'PY' >/dev/null 2>&1
import fastapi, httpx, pydantic, pytest, uvicorn
PY
  then
    "$VENV_PIP" install -r "$ROOT_DIR/requirements.txt"
  fi
}

assert_json_expr() {
  local label="$1"
  local payload="$2"
  local expression="$3"

  JSON_PAYLOAD="$payload" ASSERT_EXPRESSION="$expression" ASSERT_LABEL="$label" "$VENV_PYTHON" - <<'PY'
import json
import os

data = json.loads(os.environ["JSON_PAYLOAD"])
expression = os.environ["ASSERT_EXPRESSION"]
label = os.environ["ASSERT_LABEL"]

safe_globals = {"__builtins__": {}, "len": len}

if not eval(expression, safe_globals, {"data": data}):
    raise SystemExit(f"Validacao falhou para {label}: {expression} com payload={data}")
PY
}

trap cleanup EXIT

mkdir -p "$ROOT_DIR/data"
rm -f "$DB_PATH" "$DB_PATH-shm" "$DB_PATH-wal" "$TRANSACTIONS_LOG" "$BALANCE_LOG"

ensure_runtime

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

transactions_health_initial="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
balance_health_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/health")"
assert_json_expr "transactions health inicial" "$transactions_health_initial" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"
assert_json_expr "balance health inicial" "$balance_health_initial" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"

echo "==> Registrando lancamentos iniciais"
first_credit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa"}')"
printf '%s\n' "$first_credit"
assert_json_expr "primeiro credito" "$first_credit" "data['type'] == 'credit' and data['amount'] == '100.00'"

first_debit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor"}')"
printf '%s\n' "$first_debit"
assert_json_expr "primeiro debito" "$first_debit" "data['type'] == 'debit' and data['amount'] == '25.50'"

sleep 1

entries_initial="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/entries?entry_date=2026-01-25")"
echo "==> Extrato inicial"
printf '%s\n' "$entries_initial"
assert_json_expr "extrato inicial" "$entries_initial" "len(data) == 2"

echo "==> Saldo consolidado inicial"
balance_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25")"
printf '%s\n' "$balance_initial"
assert_json_expr "saldo inicial" "$balance_initial" "data['balance'] == '74.50'"

balances_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances?start_date=2026-01-25&end_date=2026-01-25")"
echo "==> Lista de saldos inicial"
printf '%s\n' "$balances_initial"
assert_json_expr "lista de saldos inicial" "$balances_initial" "len(data) == 1 and data[0]['balance'] == '74.50'"

echo "==> Derrubando Balance Service"
kill "$BALANCE_PID"
wait "$BALANCE_PID" 2>/dev/null || true
unset BALANCE_PID

echo "==> Enviando lancamentos com consolidado offline"
offline_credit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"credit","amount":"10.00","date":"2026-01-25","description":"Venda com consolidado offline"}')"
printf '%s\n' "$offline_credit"
assert_json_expr "credito offline" "$offline_credit" "data['type'] == 'credit' and data['amount'] == '10.00'"

offline_debit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"debit","amount":"2.00","date":"2026-01-25","description":"Despesa com consolidado offline"}')"
printf '%s\n' "$offline_debit"
assert_json_expr "debito offline" "$offline_debit" "data['type'] == 'debit' and data['amount'] == '2.00'"

echo "==> Health do Transactions Service com backlog pendente"
transactions_health_pending="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
printf '%s\n' "$transactions_health_pending"
assert_json_expr "health com backlog" "$transactions_health_pending" "data['pending_backlog_entries'] == 2"

echo "==> Reiniciando Balance Service"
CASHFLOW_DB_PATH="$DB_PATH" BALANCE_WORKER_POLL_INTERVAL_SECONDS=0.1 \
  "$UVICORN" services.balance_service.main:app \
  --host 127.0.0.1 --port "$BALANCE_PORT" >"$BALANCE_LOG" 2>&1 &
BALANCE_PID=$!
wait_for_url "http://127.0.0.1:${BALANCE_PORT}/health"
sleep 1

echo "==> Saldo consolidado apos recuperacao"
balance_recovered="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25")"
printf '%s\n' "$balance_recovered"
assert_json_expr "saldo apos recuperacao" "$balance_recovered" "data['balance'] == '82.50'"

entries_recovered="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/entries?entry_date=2026-01-25")"
echo "==> Extrato apos recuperacao"
printf '%s\n' "$entries_recovered"
assert_json_expr "extrato apos recuperacao" "$entries_recovered" "len(data) == 4"

balances_recovered="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances?start_date=2026-01-25&end_date=2026-01-25")"
echo "==> Lista de saldos apos recuperacao"
printf '%s\n' "$balances_recovered"
assert_json_expr "lista de saldos apos recuperacao" "$balances_recovered" "len(data) == 1 and data[0]['balance'] == '82.50'"

echo "==> Health final"
transactions_health_final="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
balance_health_final="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/health")"
printf '%s\n' "$transactions_health_final"
printf '%s\n' "$balance_health_final"
assert_json_expr "transactions health final" "$transactions_health_final" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"
assert_json_expr "balance health final" "$balance_health_final" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"

echo "==> Carga no Balance Service"
load_output="$(CASHFLOW_DB_PATH="$DB_PATH" "$VENV_PYTHON" "$ROOT_DIR/scripts/load_balance_service.py" \
  --url "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25" \
  --requests 100 --concurrency 50 --min-rps 50 --max-loss-percentage 5.0)"
printf '%s\n' "$load_output"

echo "==> Logs"
echo "Transactions log: $TRANSACTIONS_LOG"
echo "Balance log: $BALANCE_LOG"
