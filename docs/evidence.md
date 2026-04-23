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

================================================== 6 passed in 5.38s ===================================================
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
{"id":"dda1f09c-6ffc-49ac-8827-30079a5eaf0e","type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa","created_at":"2026-04-23T20:16:49.908647Z"}
{"id":"d0e43fbe-063d-4189-b95b-3d098a758735","type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor","created_at":"2026-04-23T20:16:49.920164Z"}
==> Saldo consolidado inicial
{"date":"2026-01-25","balance":"74.50","updated_at":"2026-04-23T20:16:50.008111Z"}
==> Derrubando Balance Service
==> Enviando lancamentos com consolidado offline
{"id":"585b1eba-f1e7-4a01-96f7-fba4a8d5dc17","type":"credit","amount":"10.00","date":"2026-01-25","description":"Venda com consolidado offline","created_at":"2026-04-23T20:16:51.130302Z"}
{"id":"aa25b21e-9fa9-497e-98e1-606129edd989","type":"debit","amount":"2.00","date":"2026-01-25","description":"Despesa com consolidado offline","created_at":"2026-04-23T20:16:51.143401Z"}
==> Health do Transactions Service com backlog pendente
{"service":"transactions-service","status":"ok","pending_backlog_entries":2}
==> Reiniciando Balance Service
==> Saldo consolidado apos recuperacao
{"date":"2026-01-25","balance":"82.50","updated_at":"2026-04-23T20:16:51.466957Z"}
==> Health final
{"service":"transactions-service","status":"ok","pending_backlog_entries":0}
{"service":"balance-service","status":"ok","pending_backlog_entries":0}
==> Carga no Balance Service
total=100 success=100 failed=0 loss_percent=0.00 rps=357.75
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
