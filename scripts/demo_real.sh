#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOTSTRAP_PYTHON="${BOOTSTRAP_PYTHON:-python3}"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
VENV_PIP="$ROOT_DIR/.venv/bin/pip"
UVICORN="$ROOT_DIR/.venv/bin/uvicorn"

find_free_port() {
  "$BOOTSTRAP_PYTHON" - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}

TRANSACTIONS_PORT="${TRANSACTIONS_PORT:-$(find_free_port)}"
BALANCE_PORT="${BALANCE_PORT:-$(find_free_port)}"
while [[ "$BALANCE_PORT" == "$TRANSACTIONS_PORT" ]]; do
  BALANCE_PORT="$(find_free_port)"
done

DEMO_DATE="${DEMO_DATE:-2026-01-25}"
INITIAL_CREDIT_AMOUNT="${INITIAL_CREDIT_AMOUNT:-100.00}"
INITIAL_DEBIT_AMOUNT="${INITIAL_DEBIT_AMOUNT:-25.50}"
OFFLINE_CREDIT_AMOUNT="${OFFLINE_CREDIT_AMOUNT:-10.00}"
OFFLINE_DEBIT_AMOUNT="${OFFLINE_DEBIT_AMOUNT:-2.00}"
INITIAL_CREDIT_DESCRIPTION="${INITIAL_CREDIT_DESCRIPTION:-Venda no caixa}"
INITIAL_DEBIT_DESCRIPTION="${INITIAL_DEBIT_DESCRIPTION:-Pagamento de fornecedor}"
OFFLINE_CREDIT_DESCRIPTION="${OFFLINE_CREDIT_DESCRIPTION:-Venda com consolidado offline}"
OFFLINE_DEBIT_DESCRIPTION="${OFFLINE_DEBIT_DESCRIPTION:-Despesa com consolidado offline}"
LOAD_REQUESTS="${LOAD_REQUESTS:-100}"
LOAD_CONCURRENCY="${LOAD_CONCURRENCY:-50}"
LOAD_MIN_RPS="${LOAD_MIN_RPS:-50}"
LOAD_MAX_LOSS_PERCENTAGE="${LOAD_MAX_LOSS_PERCENTAGE:-5.0}"
BALANCE_WORKER_POLL_INTERVAL_SECONDS="${BALANCE_WORKER_POLL_INTERVAL_SECONDS:-0.1}"
DB_PATH="${DEMO_DB_PATH:-$ROOT_DIR/data/demo-real.db}"
TRANSACTIONS_LOG="${TRANSACTIONS_LOG:-$ROOT_DIR/data/demo-transactions.log}"
BALANCE_LOG="${BALANCE_LOG:-$ROOT_DIR/data/demo-balance.log}"

INITIAL_ENTRY_COUNT=2
OFFLINE_ENTRY_COUNT=2
FINAL_ENTRY_COUNT=$((INITIAL_ENTRY_COUNT + OFFLINE_ENTRY_COUNT))
EXPECTED_PENDING_BACKLOG="$OFFLINE_ENTRY_COUNT"

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

run_python() {
  if [[ -x "$VENV_PYTHON" ]]; then
    "$VENV_PYTHON" "$@"
  else
    "$BOOTSTRAP_PYTHON" "$@"
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
    "$BOOTSTRAP_PYTHON" -m venv "$ROOT_DIR/.venv"
  fi

  if ! "$VENV_PYTHON" - <<'PY' >/dev/null 2>&1
import fastapi, httpx, pydantic, pytest, uvicorn
PY
  then
    "$VENV_PIP" install -r "$ROOT_DIR/requirements.txt"
  fi
}

build_entry_payload() {
  local entry_type="$1"
  local amount="$2"
  local entry_date="$3"
  local description="$4"

  ENTRY_TYPE="$entry_type" ENTRY_AMOUNT="$amount" ENTRY_DATE="$entry_date" ENTRY_DESCRIPTION="$description" run_python - <<'PY'
import json
import os

print(
    json.dumps(
        {
            "type": os.environ["ENTRY_TYPE"],
            "amount": os.environ["ENTRY_AMOUNT"],
            "date": os.environ["ENTRY_DATE"],
            "description": os.environ["ENTRY_DESCRIPTION"],
        },
        ensure_ascii=False,
    )
)
PY
}

decimal_eval() {
  local expression="$1"
  DECIMAL_EXPRESSION="$expression" run_python - <<'PY'
from decimal import Decimal
import os

expression = os.environ["DECIMAL_EXPRESSION"]
safe_globals = {"__builtins__": {}, "Decimal": Decimal}
value = eval(expression, safe_globals, {})
print(f"{Decimal(value):.2f}")
PY
}

json_query() {
  local payload="$1"
  local expression="$2"

  JSON_PAYLOAD="$payload" JSON_QUERY_EXPRESSION="$expression" run_python - <<'PY'
import json
import os
from decimal import Decimal

data = json.loads(os.environ["JSON_PAYLOAD"])
expression = os.environ["JSON_QUERY_EXPRESSION"]
safe_globals = {"__builtins__": {}, "len": len, "Decimal": Decimal}
value = eval(expression, safe_globals, {"data": data})
if isinstance(value, Decimal):
    print(f"{value:.2f}")
else:
    print(value)
PY
}

load_query() {
  local payload="$1"
  local field="$2"

  LOAD_OUTPUT="$payload" LOAD_FIELD="$field" run_python - <<'PY'
import os

parts = dict(item.split("=", 1) for item in os.environ["LOAD_OUTPUT"].split())
print(parts[os.environ["LOAD_FIELD"]])
PY
}

show_json_block() {
  local title="$1"
  local payload="$2"
  local kind="${3:-generic}"
  local context_json="${4:-}"

  if [[ -z "$context_json" ]]; then
    context_json='{}'
  fi

  BLOCK_TITLE="$title" JSON_PAYLOAD="$payload" BLOCK_KIND="$kind" BLOCK_CONTEXT="$context_json" run_python - <<'PY'
import json
import os
from decimal import Decimal

title = os.environ["BLOCK_TITLE"]
data = json.loads(os.environ["JSON_PAYLOAD"])
kind = os.environ["BLOCK_KIND"]
ctx = json.loads(os.environ["BLOCK_CONTEXT"])

print(f"[RESULTADO] {title}")
print(json.dumps(data, indent=2, ensure_ascii=False))

if kind == "health":
    status = data["status"]
    pending = int(data["pending_backlog_entries"])
    expected_pending = ctx.get("expected_pending")
    print(f"  -> Status retornado={status}; backlog atual={pending}.")
    if expected_pending is not None:
        print(f"  -> Comparação: backlog esperado={expected_pending}.")
    if pending == 0:
        print("  -> Interpretação: o serviço está sincronizado e sem pendências.")
    else:
        print(f"  -> Interpretação: o serviço segue online com {pending} item(ns) pendentes.")
elif kind == "entry":
    signal = "+" if data["type"] == "credit" else "-"
    expected_amount = ctx.get("expected_amount")
    print(
        "  -> Lançamento aceito com "
        f"id={data['id']}, efeito={signal}{data['amount']}, data={data['date']}."
    )
    if expected_amount is not None:
        print(f"  -> Comparação: valor esperado={expected_amount}; valor retornado={data['amount']}.")
elif kind == "entries":
    entries = data if isinstance(data, list) else []
    credits = sum(Decimal(item["amount"]) for item in entries if item["type"] == "credit")
    debits = sum(Decimal(item["amount"]) for item in entries if item["type"] == "debit")
    net = credits - debits
    print(
        "  -> O extrato retornou "
        f"{len(entries)} lançamento(s): créditos={credits:.2f}; débitos={debits:.2f}; líquido={net:.2f}."
    )
    if "expected_count" in ctx:
        print(f"  -> Comparação: quantidade esperada={ctx['expected_count']}; retornada={len(entries)}.")
elif kind == "balance":
    actual = Decimal(data["balance"])
    print(f"  -> Saldo retornado={actual:.2f} para a data {data['date']}.")
    if "expected_balance" in ctx:
        expected = Decimal(str(ctx["expected_balance"]))
        delta = actual - expected
        print(f"  -> Comparação: esperado={expected:.2f}; diferença={delta:.2f}.")
elif kind == "balances":
    balances = data if isinstance(data, list) else []
    rendered = ", ".join(f"{item['date']}={item['balance']}" for item in balances) or "nenhum saldo"
    print(f"  -> A consulta por intervalo retornou {len(balances)} item(ns): {rendered}.")
    if "expected_count" in ctx:
        print(f"  -> Comparação: quantidade esperada={ctx['expected_count']}; retornada={len(balances)}.")
PY
}

assert_json_expr() {
  local label="$1"
  local payload="$2"
  local expression="$3"
  local context_json="${4:-}"

  if [[ -z "$context_json" ]]; then
    context_json='{}'
  fi

  JSON_PAYLOAD="$payload" ASSERT_EXPRESSION="$expression" ASSERT_LABEL="$label" ASSERT_CONTEXT="$context_json" run_python - <<'PY'
import json
import os
from decimal import Decimal

data = json.loads(os.environ["JSON_PAYLOAD"])
expression = os.environ["ASSERT_EXPRESSION"]
label = os.environ["ASSERT_LABEL"]
ctx = json.loads(os.environ["ASSERT_CONTEXT"])
safe_globals = {"__builtins__": {}, "len": len, "Decimal": Decimal}

if not eval(expression, safe_globals, {"data": data, "ctx": ctx}):
    raise SystemExit(f"Avaliação falhou para {label}: {expression} com payload={data} e contexto={ctx}")

summary = ""
if isinstance(data, dict) and {"status", "pending_backlog_entries"} <= data.keys():
    summary = f"status={data['status']}, backlog={data['pending_backlog_entries']}"
elif isinstance(data, dict) and {"type", "amount", "date"} <= data.keys():
    summary = f"tipo={data['type']}, valor={data['amount']}, data={data['date']}"
elif isinstance(data, dict) and {"balance", "date"} <= data.keys():
    summary = f"saldo={data['balance']}, data={data['date']}"
elif isinstance(data, list):
    summary = f"quantidade={len(data)}"

if summary:
    print(f"[OK] {label}: {summary}")
else:
    print(f"[OK] {label}")
PY
}

show_load_output() {
  local payload="$1"
  local context_json="$2"

  LOAD_OUTPUT="$payload" LOAD_CONTEXT="$context_json" run_python - <<'PY'
import json
import os
from decimal import Decimal

parts = dict(item.split("=", 1) for item in os.environ["LOAD_OUTPUT"].split())
ctx = json.loads(os.environ["LOAD_CONTEXT"])
rps = Decimal(parts["rps"])
loss_percent = Decimal(parts["loss_percent"])
min_rps = Decimal(str(ctx["min_rps"]))
max_loss = Decimal(str(ctx["max_loss_percentage"]))

print("[RESULTADO] Teste de carga do balance-service")
for key in ("total", "success", "failed", "loss_percent", "rps"):
    print(f"  - {key}: {parts[key]}")
print(
    "  -> Comparação: "
    f"rps mínimo esperado={min_rps:.2f}; rps observado={rps:.2f}; "
    f"perda máxima esperada={max_loss:.2f}%; perda observada={loss_percent:.2f}%."
)
if rps >= min_rps and loss_percent <= max_loss:
    print("  -> Interpretação: a API sustentou a carga alvo com folga.")
else:
    print("  -> Interpretação: a API não atingiu os critérios definidos.")
PY
}

start_transactions_service() {
  CASHFLOW_DB_PATH="$DB_PATH" "$UVICORN" services.transactions_service.main:app \
    --host 127.0.0.1 --port "$TRANSACTIONS_PORT" >"$TRANSACTIONS_LOG" 2>&1 &
  TRANSACTIONS_PID=$!
  wait_for_url "http://127.0.0.1:${TRANSACTIONS_PORT}/health"
}

start_balance_service() {
  CASHFLOW_DB_PATH="$DB_PATH" BALANCE_WORKER_POLL_INTERVAL_SECONDS="$BALANCE_WORKER_POLL_INTERVAL_SECONDS" \
    "$UVICORN" services.balance_service.main:app \
    --host 127.0.0.1 --port "$BALANCE_PORT" >"$BALANCE_LOG" 2>&1 &
  BALANCE_PID=$!
  wait_for_url "http://127.0.0.1:${BALANCE_PORT}/health"
}

post_entry() {
  local payload="$1"
  curl --silent --show-error --request POST "http://127.0.0.1:${TRANSACTIONS_PORT}/entries" \
    --header 'Content-Type: application/json' \
    --data "$payload"
}

trap cleanup EXIT

ensure_runtime
INITIAL_EXPECTED_BALANCE="$(decimal_eval "Decimal('$INITIAL_CREDIT_AMOUNT') - Decimal('$INITIAL_DEBIT_AMOUNT')")"
FINAL_EXPECTED_BALANCE="$(decimal_eval "Decimal('$INITIAL_CREDIT_AMOUNT') - Decimal('$INITIAL_DEBIT_AMOUNT') + Decimal('$OFFLINE_CREDIT_AMOUNT') - Decimal('$OFFLINE_DEBIT_AMOUNT')")"

initial_health_ctx="$(printf '{"expected_pending": 0}')"
pending_health_ctx="$(printf '{"expected_pending": %s}' "$EXPECTED_PENDING_BACKLOG")"
initial_credit_ctx="$(printf '{"expected_amount": "%s"}' "$INITIAL_CREDIT_AMOUNT")"
initial_debit_ctx="$(printf '{"expected_amount": "%s"}' "$INITIAL_DEBIT_AMOUNT")"
offline_credit_ctx="$(printf '{"expected_amount": "%s"}' "$OFFLINE_CREDIT_AMOUNT")"
offline_debit_ctx="$(printf '{"expected_amount": "%s"}' "$OFFLINE_DEBIT_AMOUNT")"
initial_entries_ctx="$(printf '{"expected_count": %s}' "$INITIAL_ENTRY_COUNT")"
final_entries_ctx="$(printf '{"expected_count": %s}' "$FINAL_ENTRY_COUNT")"
initial_balance_ctx="$(printf '{"expected_balance": "%s"}' "$INITIAL_EXPECTED_BALANCE")"
final_balance_ctx="$(printf '{"expected_balance": "%s"}' "$FINAL_EXPECTED_BALANCE")"
initial_balances_ctx="$(printf '{"expected_count": 1}')"
final_balances_ctx="$(printf '{"expected_count": 1}')"
load_ctx="$(printf '{"min_rps": %s, "max_loss_percentage": %s}' "$LOAD_MIN_RPS" "$LOAD_MAX_LOSS_PERCENTAGE")"

initial_credit_payload="$(build_entry_payload "credit" "$INITIAL_CREDIT_AMOUNT" "$DEMO_DATE" "$INITIAL_CREDIT_DESCRIPTION")"
initial_debit_payload="$(build_entry_payload "debit" "$INITIAL_DEBIT_AMOUNT" "$DEMO_DATE" "$INITIAL_DEBIT_DESCRIPTION")"
offline_credit_payload="$(build_entry_payload "credit" "$OFFLINE_CREDIT_AMOUNT" "$DEMO_DATE" "$OFFLINE_CREDIT_DESCRIPTION")"
offline_debit_payload="$(build_entry_payload "debit" "$OFFLINE_DEBIT_AMOUNT" "$DEMO_DATE" "$OFFLINE_DEBIT_DESCRIPTION")"

section "DEMONSTRAÇÃO AUTOMATIZADA DO DESAFIO"
printf '%s\n' "Objetivo: executar uma prova real, com avaliação dinâmica baseada nos retornos da API."
printf '%s\n' "Configuração desta execução: data=$DEMO_DATE, porta transactions=$TRANSACTIONS_PORT, porta balance=$BALANCE_PORT."

mkdir -p "$ROOT_DIR/data"
rm -f "$DB_PATH" "$DB_PATH-shm" "$DB_PATH-wal" "$TRANSACTIONS_LOG" "$BALANCE_LOG"

section "1) SUBIDA DOS SERVIÇOS"
step "Iniciando transactions-service em 127.0.0.1:$TRANSACTIONS_PORT"
start_transactions_service
step "Iniciando balance-service em 127.0.0.1:$BALANCE_PORT"
start_balance_service

transactions_health_initial="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
balance_health_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/health")"
assert_json_expr "transactions-service iniciou saudável" "$transactions_health_initial" "data['pending_backlog_entries'] == ctx['expected_pending'] and data['status'] == 'ok'" "$initial_health_ctx"
assert_json_expr "balance-service iniciou saudável" "$balance_health_initial" "data['pending_backlog_entries'] == ctx['expected_pending'] and data['status'] == 'ok'" "$initial_health_ctx"
show_json_block "Health inicial do transactions-service" "$transactions_health_initial" "health" "$initial_health_ctx"
show_json_block "Health inicial do balance-service" "$balance_health_initial" "health" "$initial_health_ctx"

section "2) LANÇAMENTOS INICIAIS E CONSOLIDAÇÃO"
step "Registrando crédito inicial de $INITIAL_CREDIT_AMOUNT"
first_credit="$(post_entry "$initial_credit_payload")"
assert_json_expr "crédito inicial aceito" "$first_credit" "data['type'] == 'credit' and data['amount'] == ctx['expected_amount'] and data['date'] == '$DEMO_DATE'" "$initial_credit_ctx"
show_json_block "Crédito inicial registrado" "$first_credit" "entry" "$initial_credit_ctx"

step "Registrando débito inicial de $INITIAL_DEBIT_AMOUNT"
first_debit="$(post_entry "$initial_debit_payload")"
assert_json_expr "débito inicial aceito" "$first_debit" "data['type'] == 'debit' and data['amount'] == ctx['expected_amount'] and data['date'] == '$DEMO_DATE'" "$initial_debit_ctx"
show_json_block "Débito inicial registrado" "$first_debit" "entry" "$initial_debit_ctx"

sleep 1

entries_initial="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/entries?entry_date=$DEMO_DATE")"
assert_json_expr "extrato inicial consistente" "$entries_initial" "len(data) == ctx['expected_count']" "$initial_entries_ctx"
show_json_block "Extrato inicial" "$entries_initial" "entries" "$initial_entries_ctx"

balance_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/$DEMO_DATE")"
assert_json_expr "saldo inicial consolidado correto" "$balance_initial" "data['balance'] == ctx['expected_balance']" "$initial_balance_ctx"
show_json_block "Saldo consolidado inicial" "$balance_initial" "balance" "$initial_balance_ctx"

balances_initial="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances?start_date=$DEMO_DATE&end_date=$DEMO_DATE")"
assert_json_expr "lista inicial de saldos consistente" "$balances_initial" "len(data) == ctx['expected_count'] and data[0]['balance'] == '$INITIAL_EXPECTED_BALANCE'" "$initial_balances_ctx"
show_json_block "Lista inicial de saldos" "$balances_initial" "balances" "$initial_balances_ctx"

section "3) FALHA CONTROLADA DO CONSOLIDADO"
step "Derrubando balance-service para simular indisponibilidade"
kill "$BALANCE_PID"
wait "$BALANCE_PID" 2>/dev/null || true
unset BALANCE_PID
printf '%s\n' "[INFO] balance-service foi interrompido de forma controlada para validar a resiliência."

step "Enviando novos lançamentos enquanto o consolidado está offline"
offline_credit="$(post_entry "$offline_credit_payload")"
assert_json_expr "crédito offline aceito" "$offline_credit" "data['type'] == 'credit' and data['amount'] == ctx['expected_amount'] and data['date'] == '$DEMO_DATE'" "$offline_credit_ctx"
show_json_block "Crédito com consolidado offline" "$offline_credit" "entry" "$offline_credit_ctx"

offline_debit="$(post_entry "$offline_debit_payload")"
assert_json_expr "débito offline aceito" "$offline_debit" "data['type'] == 'debit' and data['amount'] == ctx['expected_amount'] and data['date'] == '$DEMO_DATE'" "$offline_debit_ctx"
show_json_block "Débito com consolidado offline" "$offline_debit" "entry" "$offline_debit_ctx"

transactions_health_pending="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
assert_json_expr "transactions-service acumulou backlog pendente esperado" "$transactions_health_pending" "data['pending_backlog_entries'] == ctx['expected_pending'] and data['status'] == 'ok'" "$pending_health_ctx"
show_json_block "Health com backlog pendente" "$transactions_health_pending" "health" "$pending_health_ctx"

section "4) RECUPERAÇÃO AUTOMÁTICA DO BACKLOG"
step "Subindo novamente o balance-service"
start_balance_service
sleep 1

balance_recovered="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances/$DEMO_DATE")"
assert_json_expr "saldo final recomposto corretamente" "$balance_recovered" "data['balance'] == ctx['expected_balance']" "$final_balance_ctx"
show_json_block "Saldo após recuperação" "$balance_recovered" "balance" "$final_balance_ctx"

entries_recovered="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/entries?entry_date=$DEMO_DATE")"
assert_json_expr "extrato final contém todos os lançamentos esperados" "$entries_recovered" "len(data) == ctx['expected_count']" "$final_entries_ctx"
show_json_block "Extrato após recuperação" "$entries_recovered" "entries" "$final_entries_ctx"

balances_recovered="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/balances?start_date=$DEMO_DATE&end_date=$DEMO_DATE")"
assert_json_expr "lista final de saldos permanece consistente" "$balances_recovered" "len(data) == ctx['expected_count'] and data[0]['balance'] == '$FINAL_EXPECTED_BALANCE'" "$final_balances_ctx"
show_json_block "Lista final de saldos" "$balances_recovered" "balances" "$final_balances_ctx"

transactions_health_final="$(curl --silent --show-error "http://127.0.0.1:${TRANSACTIONS_PORT}/health")"
balance_health_final="$(curl --silent --show-error "http://127.0.0.1:${BALANCE_PORT}/health")"
assert_json_expr "transactions-service terminou sem backlog" "$transactions_health_final" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'" "$initial_health_ctx"
assert_json_expr "balance-service terminou saudável" "$balance_health_final" "data['pending_backlog_entries'] == 0 and data['status'] == 'ok'" "$initial_health_ctx"
show_json_block "Health final do transactions-service" "$transactions_health_final" "health" "$initial_health_ctx"
show_json_block "Health final do balance-service" "$balance_health_final" "health" "$initial_health_ctx"

section "5) TESTE DE CARGA NO CONSOLIDADO"
load_output="$(CASHFLOW_DB_PATH="$DB_PATH" "$VENV_PYTHON" "$ROOT_DIR/scripts/load_balance_service.py" \
  --url "http://127.0.0.1:${BALANCE_PORT}/balances/$DEMO_DATE" \
  --requests "$LOAD_REQUESTS" --concurrency "$LOAD_CONCURRENCY" \
  --min-rps "$LOAD_MIN_RPS" --max-loss-percentage "$LOAD_MAX_LOSS_PERCENTAGE")"
show_load_output "$load_output" "$load_ctx"

INITIAL_BALANCE_ACTUAL="$(json_query "$balance_initial" "data['balance']")"
FINAL_BALANCE_ACTUAL="$(json_query "$balance_recovered" "data['balance']")"
PENDING_BACKLOG_ACTUAL="$(json_query "$transactions_health_pending" "data['pending_backlog_entries']")"
FINAL_BACKLOG_ACTUAL="$(json_query "$transactions_health_final" "data['pending_backlog_entries']")"
LOAD_RPS_ACTUAL="$(load_query "$load_output" "rps")"
LOAD_LOSS_ACTUAL="$(load_query "$load_output" "loss_percent")"
INITIAL_ENTRY_COUNT_ACTUAL="$(json_query "$entries_initial" "len(data)")"
FINAL_ENTRY_COUNT_ACTUAL="$(json_query "$entries_recovered" "len(data)")"

section "RESUMO FINAL"
printf '%s\n' "[OK] Serviços iniciaram com backlog inicial zero e status saudavel."
printf '%s\n' "[OK] Saldo inicial: esperado=$INITIAL_EXPECTED_BALANCE | retornado=$INITIAL_BALANCE_ACTUAL | lançamentos no extrato=$INITIAL_ENTRY_COUNT_ACTUAL."
printf '%s\n' "[OK] Durante a falha do consolidado, o backlog observado foi $PENDING_BACKLOG_ACTUAL."
printf '%s\n' "[OK] Após a recuperação, saldo final esperado=$FINAL_EXPECTED_BALANCE | retornado=$FINAL_BALANCE_ACTUAL | lançamentos finais=$FINAL_ENTRY_COUNT_ACTUAL."
printf '%s\n' "[OK] Teste de carga: rps observado=$LOAD_RPS_ACTUAL | perda observada=${LOAD_LOSS_ACTUAL}%."
printf '\n%s\n' "Logs gerados:"
printf '  - %s\n' "$TRANSACTIONS_LOG"
printf '  - %s\n' "$BALANCE_LOG"
printf '%s\n' "Banco usado nesta execução: $DB_PATH"
