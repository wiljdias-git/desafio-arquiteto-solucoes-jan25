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
Objetivo: executar uma prova real, com avaliação dinâmica baseada nos retornos da API.
Configuração desta execução: data=<data-configurada>, porta transactions=<porta-dinamica>, porta balance=<porta-dinamica>.

======================================================================
1) SUBIDA DOS SERVIÇOS
======================================================================
[OK] transactions-service iniciou saudável: status=ok, backlog=0
[OK] balance-service iniciou saudável: status=ok, backlog=0
[RESULTADO] Health inicial do transactions-service
{
  "service": "transactions-service",
  "status": "ok",
  "pending_backlog_entries": 0
}
  -> Status retornado=ok; backlog atual=0.
  -> Comparação: backlog esperado=0.
  -> Interpretação: o serviço está sincronizado e sem pendências.

======================================================================
2) LANÇAMENTOS INICIAIS E CONSOLIDAÇÃO
======================================================================
[ETAPA] Registrando crédito inicial de <valor-configurado>
[OK] crédito inicial aceito: tipo=credit, valor=<valor-configurado>, data=<data-configurada>
[RESULTADO] Crédito inicial registrado
{
  "id": "<uuid-dinamico>",
  "type": "credit",
  "amount": "<valor-configurado>",
  "date": "<data-configurada>",
  "description": "<descricao-configurada>",
  "created_at": "<timestamp-dinamico>"
}
  -> Lançamento aceito com id=<uuid-dinamico>, efeito=+<valor-configurado>, data=<data-configurada>.
  -> Comparação: valor esperado=<valor-configurado>; valor retornado=<valor-configurado>.
[OK] extrato inicial consistente: quantidade=2
[OK] saldo inicial consolidado correto: saldo=<saldo-dinamico>, data=<data-configurada>
[RESULTADO] Saldo consolidado inicial
{
  "date": "<data-configurada>",
  "balance": "<saldo-dinamico>",
  "updated_at": "<timestamp-dinamico>"
}
  -> Saldo retornado=<saldo-dinamico> para a data <data-configurada>.
  -> Comparação: esperado=<saldo-esperado>; diferença=0.00.

======================================================================
3) FALHA CONTROLADA DO CONSOLIDADO
======================================================================
[INFO] balance-service foi interrompido de forma controlada para validar a resiliência.
[OK] transactions-service acumulou backlog pendente esperado: status=ok, backlog=<backlog-esperado>
[RESULTADO] Health com backlog pendente
{
  "service": "transactions-service",
  "status": "ok",
  "pending_backlog_entries": "<backlog-esperado>"
}
  -> Status retornado=ok; backlog atual=<backlog-esperado>.
  -> Comparação: backlog esperado=<backlog-esperado>.
  -> Interpretação: o serviço segue online com pendências enquanto o consolidado está offline.

======================================================================
4) RECUPERAÇÃO AUTOMÁTICA DO BACKLOG
======================================================================
[OK] saldo final recomposto corretamente: saldo=<saldo-final>, data=<data-configurada>
[RESULTADO] Saldo após recuperação
{
  "date": "<data-configurada>",
  "balance": "<saldo-final>",
  "updated_at": "<timestamp-dinamico>"
}
  -> Saldo retornado=<saldo-final> para a data <data-configurada>.
  -> Comparação: esperado=<saldo-final>; diferença=0.00.
[OK] extrato final contém todos os lançamentos esperados: quantidade=<quantidade-final>
[OK] lista final de saldos permanece consistente: quantidade=1
[OK] transactions-service terminou sem backlog: status=ok, backlog=0
[OK] balance-service terminou saudável: status=ok, backlog=0

======================================================================
5) TESTE DE CARGA NO CONSOLIDADO
======================================================================
[RESULTADO] Teste de carga do balance-service
  - total: <requests-configurados>
  - success: <requests-com-sucesso>
  - failed: <requests-com-falha>
  - loss_percent: <perda-observada>
  - rps: <valor-dinamico>
  -> Comparação: rps mínimo esperado=<min-rps>; rps observado=<valor-dinamico>; perda máxima esperada=<max-loss>%.
  -> Interpretação: a API sustentou a carga alvo quando os critérios acima forem satisfeitos.

======================================================================
RESUMO FINAL
======================================================================
[OK|FAIL] Inicialização dos serviços: status inicial=<status>; backlog inicial=<valor>.
[OK|FAIL] Consolidação inicial: esperado=<saldo-esperado>; retornado=<saldo-observado>; lançamentos=<quantidade>.
[OK|FAIL] Resiliência durante a falha: backlog esperado=<valor>; backlog observado=<valor>.
[OK|FAIL] Recuperação após a falha: saldo esperado=<valor>; saldo retornado=<valor>; lançamentos=<quantidade>; backlog final=<valor>.
[OK|FAIL] Teste de carga: rps mínimo=<valor>; rps observado=<valor>; perda máxima=<valor>; perda observada=<valor>.
```

Os campos `id`, `created_at`, `updated_at`, portas, `rps` e parte dos detalhes do resumo variam a cada execucao. O que permanece fixo e a logica de avaliacao: o script compara valores observados com os valores esperados calculados dinamicamente.

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
