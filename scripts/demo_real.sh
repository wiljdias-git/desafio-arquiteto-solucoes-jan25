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

section() {
  printf '\n%s\n' "======================================================================"
  printf '%s\n' "$1"
  printf '%s\n' "======================================================================"
}

step() {
  printf '\n[ETAPA] %s\n' "$1"
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

show_json_block() {
  local title="$1"
  local payload="$2"

  BLOCK_TITLE="$title" JSON_PAYLOAD="$payload" "$VENV_PYTHON" - <<'PY'
import json
import os

title = os.environ["BLOCK_TITLE"]
data = json.loads(os.environ["JSON_PAYLOAD"])

print(f"[RESULTADO] {title}")
print(json.dumps(data, indent=2, ensure_ascii=False))

if title == "Health inicial do transactions-service":
    print("  -> O serviço transacional está online e começa sem backlog pendente.")
elif title == "Health inicial do balance-service":
    print("  -> O serviço de consolidado está online e pronto para consumir backlog.")
elif title == "Crédito inicial registrado":
    print(f"  -> Crédito aceito: +{data['amount']} na data {data['date']}.")
elif title == "Débito inicial registrado":
    print(f"  -> Débito aceito: -{data['amount']} na data {data['date']}.")
elif title == "Extrato inicial":
    print(f"  -> O extrato inicial tem {len(data)} lançamentos persistidos.")
elif title == "Saldo consolidado inicial":
    print(f"  -> O saldo do dia após os dois primeiros lançamentos é {data['balance']}.")
elif title == "Lista inicial de saldos":
    print(f"  -> Há {len(data)} dia consolidado disponível para consulta.")
elif title == "Crédito com consolidado offline":
    print("  -> Mesmo com o consolidado fora do ar, o lançamento continuou sendo aceito.")
elif title == "Débito com consolidado offline":
    print("  -> O desacoplamento permitiu seguir gravando débito durante a falha.")
elif title == "Health com backlog pendente":
    print(f"  -> O transactions-service segue online e acumulou backlog={data['pending_backlog_entries']}.")
elif title == "Saldo após recuperação":
    print(f"  -> Após a volta do consolidado, o saldo reprocessado ficou em {data['balance']}.")
elif title == "Extrato após recuperação":
    print(f"  -> O extrato final contém {len(data)} lançamentos, incluindo os feitos durante a falha.")
elif title == "Lista final de saldos":
    print(f"  -> A consulta por intervalo continua consistente e mostra saldo {data[0]['balance']}.")
elif title == "Health final do transactions-service":
    print("  -> O backlog voltou para zero no serviço transacional.")
elif title == "Health final do balance-service":
    print("  -> O serviço de consolidado terminou saudável e sincronizado.")
PY
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
    raise SystemExit(f"Validação falhou para {label}: {expression} com payload={data}")
PY
  printf '[OK] %s\n' "$label"
}

show_load_output() {
  local payload="$1"

  LOAD_OUTPUT="$payload" "$VENV_PYTHON" - <<'PY'
import os

raw = os.environ["LOAD_OUTPUT"].strip()
parts = dict(item.split("=", 1) for item in raw.split())

print("[RESULTADO] Teste de carga do balance-service")
for key in ("total", "success", "failed", "loss_percent", "rps"):
    print(f"  - {key}: {parts[key]}")

print(
    "  -> A API de leitura consolidada sustentou a carga mínima pedida, "
    f"com throughput de {parts['rps']} rps e perda de {parts['loss_percent']}%."
)
PY
}

trap cleanup EXIT

section "DEMONSTRAÇÃO AUTOMATIZADA DO DESAFIO"
printf '%s\n' "Objetivo: provar, de forma legível para um avaliador humano, que a solução funciona ponta a ponta."

mkdir -p "$ROOT_DIR/data"
rm -f "$DB_PATH" "$DB_PATH-shm" "$DB_PATH-wal" "$TRANSACTIONS_LOG" "$BALANCE_LOG"
ensure_runtime

section "1) SUBIDA DOS SERVIÇOS"
step "Iniciando transactions-service"
CASHFLOW_DB_PATH="$DB_PATH" "$UVICORN" services.transactions_service.main:app \
  --host 127.0.0.1 --port "$TRANSACTIONS_PORT" >"$TRANSACTIONS_LOG" 2>&1 &
TRANSACTIONS_PID=$!
wait_for_url "http://127.0.0.1:${TRANSACTIONS_PORT}/health"

step "Iniciando balance-service"
CASHFLOW_DB_PATH="$DB_PATH" BALANCE_WORKER_POLL_INTERVAL_SECONDS=0.1 \
  "$UVICORN" services.balance_service.main:app \
  --host 127.0.0.1 --port "$BALANCE_PORT" >"$BALANCE_LOG" 2>&1 &
BALANCE_PID=$!
wait_for_url "http://127.0.0.1:${BALANCE_PORT}/health"

transactions_health_initial="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
balance_health_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/health")"
assert_json_expr "transactions-service inicia saudável" "$transactions_health_initial" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"
assert_json_expr "balance-service inicia saudável" "$balance_health_initial" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"
show_json_block "Health inicial do transactions-service" "$transactions_health_initial"
show_json_block "Health inicial do balance-service" "$balance_health_initial"

section "2) LANÇAMENTOS INICIAIS E CONSOLIDAÇÃO"
step "Registrando crédito inicial"
first_credit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa"}')"
assert_json_expr "crédito inicial aceito" "$first_credit" "data['type'] == 'credit' and data['amount'] == '100.00'"
show_json_block "Crédito inicial registrado" "$first_credit"

step "Registrando débito inicial"
first_debit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor"}')"
assert_json_expr "débito inicial aceito" "$first_debit" "data['type'] == 'debit' and data['amount'] == '25.50'"
show_json_block "Débito inicial registrado" "$first_debit"

sleep 1

entries_initial="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/entries?entry_date=2026-01-25")"
assert_json_expr "extrato inicial possui dois lançamentos" "$entries_initial" "len(data) == 2"
show_json_block "Extrato inicial" "$entries_initial"

balance_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25")"
assert_json_expr "saldo inicial consolidado correto" "$balance_initial" "data['balance'] == '74.50'"
show_json_block "Saldo consolidado inicial" "$balance_initial"

balances_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances?start_date=2026-01-25&end_date=2026-01-25")"
assert_json_expr "lista inicial de saldos consistente" "$balances_initial" "len(data) == 1 and data[0]['balance'] == '74.50'"
show_json_block "Lista inicial de saldos" "$balances_initial"

section "3) FALHA CONTROLADA DO CONSOLIDADO"
step "Derrubando balance-service para simular indisponibilidade"
kill "$BALANCE_PID"
wait "$BALANCE_PID" 2>/dev/null || true
unset BALANCE_PID
printf '%s\n' "[OK] balance-service parado propositalmente para testar resiliência."

step "Enviando novos lançamentos enquanto o consolidado está offline"
offline_credit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"credit","amount":"10.00","date":"2026-01-25","description":"Venda com consolidado offline"}')"
assert_json_expr "crédito offline aceito" "$offline_credit" "data['type'] == 'credit' and data['amount'] == '10.00'"
show_json_block "Crédito com consolidado offline" "$offline_credit"

offline_debit="$(curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
  --header 'Content-Type: application/json' \
  --data '{"type":"debit","amount":"2.00","date":"2026-01-25","description":"Despesa com consolidado offline"}')"
assert_json_expr "débito offline aceito" "$offline_debit" "data['type'] == 'debit' and data['amount'] == '2.00'"
show_json_block "Débito com consolidado offline" "$offline_debit"

transactions_health_pending="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
assert_json_expr "transactions-service acumula backlog pendente" "$transactions_health_pending" "data['pending_backlog_entries'] == 2"
show_json_block "Health com backlog pendente" "$transactions_health_pending"

section "4) RECUPERAÇÃO AUTOMÁTICA DO BACKLOG"
step "Subindo novamente o balance-service"
CASHFLOW_DB_PATH="$DB_PATH" BALANCE_WORKER_POLL_INTERVAL_SECONDS=0.1 \
  "$UVICORN" services.balance_service.main:app \
  --host 127.0.0.1 --port "$BALANCE_PORT" >"$BALANCE_LOG" 2>&1 &
BALANCE_PID=$!
wait_for_url "http://127.0.0.1:${BALANCE_PORT}/health"
sleep 1

balance_recovered="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25")"
assert_json_expr "saldo final recomposto corretamente" "$balance_recovered" "data['balance'] == '82.50'"
show_json_block "Saldo após recuperação" "$balance_recovered"

entries_recovered="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/entries?entry_date=2026-01-25")"
assert_json_expr "extrato final possui quatro lançamentos" "$entries_recovered" "len(data) == 4"
show_json_block "Extrato após recuperação" "$entries_recovered"

balances_recovered="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances?start_date=2026-01-25&end_date=2026-01-25")"
assert_json_expr "lista final de saldos consistente" "$balances_recovered" "len(data) == 1 and data[0]['balance'] == '82.50'"
show_json_block "Lista final de saldos" "$balances_recovered"

transactions_health_final="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
balance_health_final="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/health")"
assert_json_expr "transactions-service termina sem backlog" "$transactions_health_final" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"
assert_json_expr "balance-service termina saudável" "$balance_health_final" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'"
show_json_block "Health final do transactions-service" "$transactions_health_final"
show_json_block "Health final do balance-service" "$balance_health_final"

section "5) TESTE DE CARGA NO CONSOLIDADO"
load_output="$(CASHFLOW_DB_PATH="$DB_PATH" "$VENV_PYTHON" "$ROOT_DIR/scripts/load_balance_service.py" \
  --url "http://127.0.0.1:${BALANCE_PORT}/balances/2026-01-25" \
  --requests 100 --concurrency 50 --min-rps 50 --max-loss-percentage 5.0)"
show_load_output "$load_output"

section "RESUMO FINAL"
printf '%s\n' "[OK] Cenário 1: serviços subiram saudáveis."
printf '%s\n' "[OK] Cenário 2: crédito e débito iniciais foram registrados e consolidados."
printf '%s\n' "[OK] Cenário 3: o transactions-service continuou funcionando durante a falha do consolidado."
printf '%s\n' "[OK] Cenário 4: o backlog foi reprocessado automaticamente após a recuperação."
printf '%s\n' "[OK] Cenário 5: o balance-service sustentou a carga mínima exigida."
printf '\n%s\n' "Logs gerados:"
printf '  - %s\n' "$TRANSACTIONS_LOG"
printf '  - %s\n' "$BALANCE_LOG"
