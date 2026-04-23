# Evidencias de execucao

Este arquivo registra evidencias reais coletadas a partir de:

- testes automatizados
- teste E2E com servicos reais via HTTP
- demonstracao automatizada ponta a ponta
- teste de carga do servico de consolidado

## Evidencia 1 - suite de testes automatizados

Comando executado:

```bash
python -m pytest -q
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
  [PASS] Processa o backlog pendente e retorna o saldo diario consolidado correto. (0.01s)
  [PASS] Recupera backlog acumulado apos indisponibilidade do consolidado sem perder lancamentos. (0.02s)
  [PASS] Executa o fluxo ponta a ponta com servicos reais via HTTP, incluindo queda e recuperacao do consolidado. (2.08s)
  [PASS] Registra credito e debito e comprova que os lancamentos ficam persistidos com backlog pendente para consolidacao. (0.02s)
  [PASS] Mantem o servico transacional aceitando lancamentos mesmo sem o consolidado disponivel. (0.01s)
  [PASS] Rejeita valores invalidos para proteger a integridade do fluxo de caixa. (0.00s)
Leitura recomendada: cada linha [PASS]/[FAIL]/[SKIP] descreve o comportamento validado.
6 passed in 2.23s
```

## Evidencia 2 - demonstracao real ponta a ponta

Comando canonico:

```bash
python scripts/demo_real.py
```

Wrappers equivalentes:

```bash
./scripts/demo_real.sh
```

```bat
scripts\demo_real.bat
```

Saida observada:

```text
======================================================================
DEMONSTRACAO AUTOMATIZADA DO DESAFIO
======================================================================
Objetivo: executar uma prova real, com avaliacao dinamica baseada nos retornos da API.
Configuracao desta execucao: data=2026-01-25, porta transactions=50523, porta balance=35815.

======================================================================
1) SUBIDA DOS SERVICOS
======================================================================

[ETAPA] Iniciando transactions-service em 127.0.0.1:50523

[ETAPA] Iniciando balance-service em 127.0.0.1:35815
[OK] transactions-service iniciou saudavel: status=ok, backlog=0
[OK] balance-service iniciou saudavel: status=ok, backlog=0
[RESULTADO] Health inicial do transactions-service
{
  "service": "transactions-service",
  "status": "ok",
  "pending_backlog_entries": 0
}
[RESULTADO] Health inicial do balance-service
{
  "service": "balance-service",
  "status": "ok",
  "pending_backlog_entries": 0
}

======================================================================
2) LANCAMENTOS INICIAIS E CONSOLIDACAO
======================================================================

[ETAPA] Registrando credit inicial de 100.00
[OK] credito inicial aceito: tipo=credit, valor=100.00, data=2026-01-25
[RESULTADO] Credito inicial registrado
{
  "id": "d309f620-673a-40e6-be22-b611b0d0442c",
  "type": "credit",
  "amount": "100.00",
  "date": "2026-01-25",
  "description": "Venda no caixa",
  "created_at": "2026-04-23T21:28:15.656928Z"
}
[ETAPA] Registrando debit inicial de 25.50
[OK] debito inicial aceito: tipo=debit, valor=25.50, data=2026-01-25
[RESULTADO] Debito inicial registrado
{
  "id": "1bc72398-cc0d-4360-b10c-d7ef94235816",
  "type": "debit",
  "amount": "25.50",
  "date": "2026-01-25",
  "description": "Pagamento de fornecedor",
  "created_at": "2026-04-23T21:28:15.662948Z"
}
[OK] extrato inicial consistente: quantidade=2
[OK] saldo inicial consolidado correto: saldo=74.50, data=2026-01-25
[OK] lista inicial de saldos consistente: quantidade=1

======================================================================
3) FALHA CONTROLADA DO CONSOLIDADO
======================================================================

[ETAPA] Derrubando balance-service para simular indisponibilidade
[INFO] balance-service foi interrompido de forma controlada para validar a resiliencia.
[ETAPA] Enviando novos lancamentos enquanto o consolidado esta offline
[OK] credito offline aceito: tipo=credit, valor=10.00, data=2026-01-25
[OK] debito offline aceito: tipo=debit, valor=2.00, data=2026-01-25
[OK] transactions-service acumulou backlog pendente esperado: status=ok, backlog=2

======================================================================
4) RECUPERACAO AUTOMATICA DO BACKLOG
======================================================================

[ETAPA] Subindo novamente balance-service em 127.0.0.1:35815
[OK] saldo final recomposto corretamente: saldo=82.50, data=2026-01-25
[OK] extrato final contem todos os lancamentos esperados: quantidade=4
[OK] lista final de saldos permanece consistente: quantidade=1
[OK] transactions-service terminou sem backlog: status=ok, backlog=0
[OK] balance-service terminou saudavel: status=ok, backlog=0

======================================================================
5) TESTE DE CARGA NO CONSOLIDADO
======================================================================
[RESULTADO] Teste de carga do balance-service
  - total: 100
  - success: 100
  - failed: 0
  - loss_percent: 0.00
  - rps: 426.51
  -> Comparação: rps mínimo esperado=50.00; rps observado=426.51; perda máxima esperada=5.00%; perda observada=0.00%.
  -> Interpretação: a API sustentou a carga alvo com folga.

======================================================================
RESUMO FINAL
======================================================================
[OK] Inicializacao dos servicos: status inicial=ok; backlog inicial=0.
[OK] Consolidacao inicial: esperado=74.50; retornado=74.50; lancamentos=2.
[OK] Resiliencia durante a falha: backlog esperado=2; backlog observado=2.
[OK] Recuperacao apos a falha: saldo esperado=82.50; saldo retornado=82.50; lancamentos=4; backlog final=0.
[OK] Teste de carga: rps minimo=50.00; rps observado=426.51; perda maxima=5.00%; perda observada=0.00%.

Logs gerados:
  - /home/wiljdias/git/personal/desafio-arquiteto-solucoes-jan25/data/demo-transactions.log
  - /home/wiljdias/git/personal/desafio-arquiteto-solucoes-jan25/data/demo-balance.log
Banco usado nesta execucao: /home/wiljdias/git/personal/desafio-arquiteto-solucoes-jan25/data/demo-real.db
```

Os campos de ids, timestamps, portas, throughput e caminhos variam a cada execucao. O que permanece fixo e a logica de avaliacao: `scripts/demo_real.py` calcula os valores esperados dinamicamente, compara com o retorno real das APIs e emite `[OK]` ou `[FAIL]` conforme o resultado observado.

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
