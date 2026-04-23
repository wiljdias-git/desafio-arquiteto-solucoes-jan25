# Evidencias de execucao

Este arquivo registra evidencias reais coletadas a partir de:

- testes automatizados
- teste E2E com servicos reais via HTTP
- demonstracao manual automatizada por script
- teste de carga do servico de consolidado

## Evidencia 1 - suite de testes automatizados

Comando executado:

```bash
.venv/bin/pytest -q
```

Saida observada em formato humano:

```text
[100%]
============================================== Resumo humano da validacao ==============================================
Total de cenarios: 6
Aprovados: 6
Falhas: 0
Pulados: 0

Leitura por cenario:
  [PASS] Processa o backlog pendente e retorna o saldo diario consolidado correto.
  [PASS] Recupera backlog acumulado apos indisponibilidade do consolidado sem perder lancamentos.
  [PASS] Executa o fluxo ponta a ponta com servicos reais via HTTP, incluindo queda e recuperacao do consolidado.
  [PASS] Registra credito e debito e comprova que os lancamentos ficam persistidos com backlog pendente para consolidacao.
  [PASS] Mantem o servico transacional aceitando lancamentos mesmo sem o consolidado disponivel.
  [PASS] Rejeita valores invalidos para proteger a integridade do fluxo de caixa.

6 passed
```

## Evidencia 2 - demonstracao real ponta a ponta

Comando executado:

```bash
./scripts/demo_real.sh
```

Saida observada:

```text
======================================================================
DEMONSTRAÇÃO AUTOMATIZADA DO DESAFIO
======================================================================
Objetivo: provar, de forma legível para um avaliador humano, que a solução funciona ponta a ponta.

======================================================================
1) SUBIDA DOS SERVIÇOS
======================================================================
[OK] transactions-service inicia saudável
[OK] balance-service inicia saudável
[RESULTADO] Health inicial do transactions-service
{
  "service": "transactions-service",
  "status": "ok",
  "pending_backlog_entries": 0
}
  -> O serviço transacional está online e começa sem backlog pendente.

======================================================================
2) LANÇAMENTOS INICIAIS E CONSOLIDAÇÃO
======================================================================
[OK] crédito inicial aceito
[RESULTADO] Crédito inicial registrado
{
  "id": "<uuid-dinamico>",
  "type": "credit",
  "amount": "100.00",
  "date": "2026-01-25",
  "description": "Venda no caixa",
  "created_at": "<timestamp-dinamico>"
}
  -> Crédito aceito: +100.00 na data 2026-01-25.
[OK] saldo inicial consolidado correto
[RESULTADO] Saldo consolidado inicial
{
  "date": "2026-01-25",
  "balance": "74.50",
  "updated_at": "<timestamp-dinamico>"
}
  -> O saldo do dia após os dois primeiros lançamentos é 74.50.

======================================================================
3) FALHA CONTROLADA DO CONSOLIDADO
======================================================================
[OK] transactions-service acumula backlog pendente
[RESULTADO] Health com backlog pendente
{
  "service": "transactions-service",
  "status": "ok",
  "pending_backlog_entries": 2
}
  -> O transactions-service segue online e acumulou backlog=2.

======================================================================
4) RECUPERAÇÃO AUTOMÁTICA DO BACKLOG
======================================================================
[OK] saldo final recomposto corretamente
[RESULTADO] Saldo após recuperação
{
  "date": "2026-01-25",
  "balance": "82.50",
  "updated_at": "<timestamp-dinamico>"
}
  -> Após a volta do consolidado, o saldo reprocessado ficou em 82.50.

======================================================================
5) TESTE DE CARGA NO CONSOLIDADO
======================================================================
[RESULTADO] Teste de carga do balance-service
  - total: 100
  - success: 100
  - failed: 0
  - loss_percent: 0.00
  - rps: <valor-dinamico>
  -> A API de leitura consolidada sustentou a carga mínima pedida.
```

Os campos `id`, `created_at`, `updated_at` e `rps` variam a cada execucao, mas a estrutura e os checkpoints validados permanecem os mesmos.

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
