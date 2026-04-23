# Evidencias de execucao

Este arquivo registra evidencias reais coletadas a partir de:

- testes automatizados
- teste E2E com servicos reais via HTTP
- demonstracao manual automatizada por script
- teste de carga do servico de consolidado

## Evidencia 1 - suite de testes automatizados

Comando executado:

```bash
.venv/bin/pytest
```

Saida observada:

```text
================================================= test session starts ==================================================
platform linux -- Python 3.12.3, pytest-8.3.5, pluggy-1.6.0
rootdir: /home/wiljdias/git/personal/desafio-arquiteto-solucoes-jan25
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.13.0
collecting ... collected 6 items

tests/test_balance_service.py ..
tests/test_e2e_live.py .
tests/test_transactions_api.py ...

================================================== 6 passed in 2.55s ===================================================
```

## Evidencia 2 - demonstracao real ponta a ponta

Comando executado:

```bash
./scripts/demo_real.sh
```

Saida observada:

```text
==> Iniciando Transactions Service
==> Iniciando Balance Service
==> Registrando lancamentos iniciais
{"id":"9eabc4f0-ac01-4f95-9836-2505b6c6b26b","type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa","created_at":"2026-04-23T20:44:26.854881Z"}
{"id":"00f87cbb-33d7-4215-93ca-2435ecbcab9a","type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor","created_at":"2026-04-23T20:44:26.879454Z"}
==> Extrato inicial
[{"id":"00f87cbb-33d7-4215-93ca-2435ecbcab9a","type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor","created_at":"2026-04-23T20:44:26.879454Z"},{"id":"9eabc4f0-ac01-4f95-9836-2505b6c6b26b","type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa","created_at":"2026-04-23T20:44:26.854881Z"}]
==> Saldo consolidado inicial
{"date":"2026-01-25","balance":"74.50","updated_at":"2026-04-23T20:44:27.135431Z"}
==> Lista de saldos inicial
[{"date":"2026-01-25","balance":"74.50","updated_at":"2026-04-23T20:44:27.135431Z"}]
==> Derrubando Balance Service
==> Enviando lancamentos com consolidado offline
{"id":"401fe2fc-57db-4e67-adea-e878d22aad9b","type":"credit","amount":"10.00","date":"2026-01-25","description":"Venda com consolidado offline","created_at":"2026-04-23T20:44:28.257669Z"}
{"id":"9b726702-9973-46aa-b073-9a74f8b59793","type":"debit","amount":"2.00","date":"2026-01-25","description":"Despesa com consolidado offline","created_at":"2026-04-23T20:44:28.284641Z"}
==> Health do Transactions Service com backlog pendente
{"service":"transactions-service","status":"ok","pending_backlog_entries":2}
==> Reiniciando Balance Service
==> Saldo consolidado apos recuperacao
{"date":"2026-01-25","balance":"82.50","updated_at":"2026-04-23T20:44:28.611918Z"}
==> Extrato apos recuperacao
[{"id":"9b726702-9973-46aa-b073-9a74f8b59793","type":"debit","amount":"2.00","date":"2026-01-25","description":"Despesa com consolidado offline","created_at":"2026-04-23T20:44:28.284641Z"},{"id":"401fe2fc-57db-4e67-adea-e878d22aad9b","type":"credit","amount":"10.00","date":"2026-01-25","description":"Venda com consolidado offline","created_at":"2026-04-23T20:44:28.257669Z"},{"id":"00f87cbb-33d7-4215-93ca-2435ecbcab9a","type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor","created_at":"2026-04-23T20:44:26.879454Z"},{"id":"9eabc4f0-ac01-4f95-9836-2505b6c6b26b","type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa","created_at":"2026-04-23T20:44:26.854881Z"}]
==> Lista de saldos apos recuperacao
[{"date":"2026-01-25","balance":"82.50","updated_at":"2026-04-23T20:44:28.611918Z"}]
==> Health final
{"service":"transactions-service","status":"ok","pending_backlog_entries":0}
{"service":"balance-service","status":"ok","pending_backlog_entries":0}
==> Carga no Balance Service
total=100 success=100 failed=0 loss_percent=0.00 rps=419.16
```

## Evidencia 3 - imports do ambiente Python

O workspace esta apontado para `.venv/bin/python`, com configuracao em `.vscode/settings.json` e `pyrightconfig.json`.

Snippet executado:

```python
import fastapi, httpx, pydantic, pytest
print({'fastapi': fastapi.__version__, 'httpx': httpx.__version__, 'pydantic': pydantic.__version__, 'pytest': pytest.__version__})
```

Saida observada:

```text
{'fastapi': '0.115.12', 'httpx': '0.28.1', 'pydantic': '2.13.3', 'pytest': '8.3.5'}
```
