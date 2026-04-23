# Desafio de Arquiteto de Solucoes - Fluxo de Caixa Diario

Este repositorio entrega uma solucao completa para o desafio descrito em `init.md`, com **dois servicos independentes**, **testes automatizados**, **documentacao arquitetural** e **instrucoes de execucao local**.

## Resumo da solucao

- **Transactions Service**: registra debitos e creditos.
- **Balance Service**: consolida o saldo diario a partir de um backlog persistido.
- **Persistencia**: SQLite com tabelas separadas para lancamentos, backlog de consolidacao e saldo diario.
- **Resiliencia**: o servico de lancamentos nao depende do consolidado para aceitar requisicoes. Se o consolidado cair, o backlog fica persistido e e processado quando o servico voltar.

## Estrutura do repositorio

- `services/transactions_service/`: API de lancamentos
- `services/balance_service/`: API de saldo diario
- `services/common/`: configuracao, banco e repositorios compartilhados
- `tests/`: testes automatizados
- `docs/`: documentacao arquitetural e complementar
- `scripts/load_balance_service.py`: script simples de carga para o servico de consolidado
- `scripts/demo_real.py`: implementacao cross-platform da demonstracao ponta a ponta
- `scripts/demo_real.sh`: wrapper para Linux/macOS
- `scripts/demo_real.bat`: wrapper para Windows

## Requisitos

- Python 3.12+
- `pip`

## Instalacao

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
python -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Executando os servicos

Em um terminal:

```bash
python -m uvicorn services.transactions_service.main:app --host 0.0.0.0 --port 8000
```

Em outro terminal:

```bash
python -m uvicorn services.balance_service.main:app --host 0.0.0.0 --port 8001
```

## APIs implementadas

### Transactions Service

| Metodo | Endpoint | Finalidade |
| --- | --- | --- |
| `GET` | `/health` | estado do servico e quantidade de backlog pendente |
| `POST` | `/entries` | registra um lancamento de debito ou credito |
| `GET` | `/entries` | lista lancamentos; aceita `entry_date=YYYY-MM-DD` |

### Balance Service

| Metodo | Endpoint | Finalidade |
| --- | --- | --- |
| `GET` | `/health` | estado do servico e quantidade de backlog pendente |
| `GET` | `/balances/{entry_date}` | consulta o saldo consolidado de uma data |
| `GET` | `/balances` | lista saldos consolidados; aceita `start_date` e `end_date` |
| `POST` | `/internal/process-backlog` | endpoint interno para forcar processamento do backlog |

## Fluxo de demonstracao

### 1. Registrar lancamentos

```bash
curl --request POST 'http://127.0.0.1:8000/entries' \
  --header 'Content-Type: application/json' \
  --data '{
    "type": "credit",
    "amount": "100.00",
    "date": "2026-01-25",
    "description": "Venda no caixa"
  }'
```

```bash
curl --request POST 'http://127.0.0.1:8000/entries' \
  --header 'Content-Type: application/json' \
  --data '{
    "type": "debit",
    "amount": "25.50",
    "date": "2026-01-25",
    "description": "Pagamento de fornecedor"
  }'
```

### 2. Consultar o saldo consolidado

```bash
curl 'http://127.0.0.1:8001/balances/2026-01-25'
```

### 3. Simular indisponibilidade do consolidado

1. Pare o servico da porta `8001`.
2. Continue enviando lancamentos para a porta `8000`.
3. Suba novamente o servico de consolidado.
4. Consulte `/health` e `/balances/{data}` para confirmar o reprocessamento do backlog.

## Testes

```bash
python -m pytest
```

Ou, para uma leitura mais enxuta:

```bash
python -m pytest -q
```

O comando `pytest -q` agora entrega um **resumo humano por cenario**, com:

- total de cenarios validados
- quantidade de aprovacoes, falhas e itens pulados
- uma linha `[PASS]`, `[FAIL]` ou `[SKIP]` explicando o comportamento validado em cada teste

### Testes incluidos

- **unitarios e de API** com `TestClient`
- **E2E live** com `uvicorn` em subprocessos e chamadas HTTP reais

## Teste simples de carga

Com o servico de consolidado no ar:

```bash
python scripts/load_balance_service.py --url http://127.0.0.1:8001/balances/2026-01-25 --requests 100 --concurrency 50
```

O objetivo do script e demonstrar que a API atende uma rajada com **50 requisicoes concorrentes** e medir a taxa de perda observada.

## Demonstracao real automatizada

Comando canonico cross-platform:

```bash
python scripts/demo_real.py
```

Atalhos por sistema operacional:

```bash
./scripts/demo_real.sh
```

```bat
scripts\demo_real.bat
```

A implementacao compartilhada em `scripts/demo_real.py`:

1. sobe os dois servicos com `uvicorn`
2. registra lancamentos reais por HTTP
3. derruba o consolidado
4. continua aceitando lancamentos no servico transacional
5. sobe novamente o consolidado e comprova o reprocessamento do backlog
6. executa carga com 100 requisicoes e concorrencia 50

O output foi desenhado para leitura humana e agora mostra:

- blocos visuais por etapa
- validacoes `[OK]` de cada checkpoint
- payloads JSON formatados
- explicacao dinamica do que cada resposta significa
- resumo final com os cenarios aprovados
- comparacao entre valor esperado e valor realmente retornado pela API
- portas livres escolhidas em tempo de execucao para evitar conflito local
- resumo final com status calculado dinamicamente a partir dos resultados observados
- secao explicita de falha com a etapa atual e o erro real quando a execucao quebra

O comportamento esperado e:

- se os resultados reais coincidirem com os esperados, o resumo final mostra linhas com `[OK]`
- se algum valor nao bater, o resumo final mostra `[FAIL]`
- se a execucao quebrar antes do resumo, o script imprime `FALHA NA DEMONSTRACAO` com diagnostico da etapa atual

Variaveis de ambiente aceitas para customizar a demonstracao:

- `TRANSACTIONS_PORT`
- `BALANCE_PORT`
- `DEMO_DATE`
- `INITIAL_CREDIT_AMOUNT`
- `INITIAL_DEBIT_AMOUNT`
- `OFFLINE_CREDIT_AMOUNT`
- `OFFLINE_DEBIT_AMOUNT`
- `LOAD_REQUESTS`
- `LOAD_CONCURRENCY`
- `LOAD_MIN_RPS`
- `LOAD_MAX_LOSS_PERCENTAGE`
- `BALANCE_WORKER_POLL_INTERVAL_SECONDS`
- `DEMO_DB_PATH`
- `TRANSACTIONS_LOG`
- `BALANCE_LOG`

## Como rodar durante a avaliacao

### Opcao 1 - prova rapida

Linux/macOS:

```bash
./scripts/demo_real.sh
python -m pytest tests/test_e2e_live.py -q
```

Windows:

```bat
scripts\demo_real.bat
python -m pytest tests\test_e2e_live.py -q
```

Essa e a forma mais objetiva de mostrar:

- chamadas HTTP reais
- validacao automatica dos resultados esperados
- consulta do extrato e da lista de saldos
- queda e recuperacao do servico de consolidado
- reprocessamento do backlog
- verificacao de health antes, durante e depois da falha
- validacao do requisito de carga com minimo de 50 rps e ate 5% de perda
- teste automatizado com os servicos reais no ar

### Opcao 2 - execucao manual

Em um terminal:

```bash
python -m uvicorn services.transactions_service.main:app --host 0.0.0.0 --port 8000
```

Em outro terminal:

```bash
python -m uvicorn services.balance_service.main:app --host 0.0.0.0 --port 8001
```

Depois execute:

```bash
curl --request POST 'http://127.0.0.1:8000/entries' \
  --header 'Content-Type: application/json' \
  --data '{"type":"credit","amount":"100.00","date":"2026-01-25","description":"Venda no caixa"}'
```

```bash
curl --request POST 'http://127.0.0.1:8000/entries' \
  --header 'Content-Type: application/json' \
  --data '{"type":"debit","amount":"25.50","date":"2026-01-25","description":"Pagamento de fornecedor"}'
```

```bash
curl 'http://127.0.0.1:8001/balances/2026-01-25'
```

O saldo esperado e `74.50`.

## Como explicar a solucao para o avaliador

Use a explicacao abaixo de forma objetiva:

> A solucao foi separada em dois servicos. O `transactions-service` recebe e persiste os lancamentos de debito e credito. O `balance-service` materializa a leitura do saldo diario. O desacoplamento entre eles foi feito com um backlog persistido. Assim, se o consolidado cair, o servico transacional continua operando normalmente e o saldo e reprocessado quando o consolidado volta.

## Como demonstrar resiliencia ao vivo

1. pare o `balance-service`
2. continue enviando lancamentos para `http://127.0.0.1:8000/entries`
3. consulte `http://127.0.0.1:8000/health`
4. mostre que `pending_backlog_entries` aumentou
5. suba novamente o `balance-service`
6. consulte `http://127.0.0.1:8001/balances/2026-01-25`
7. consulte de novo `http://127.0.0.1:8000/health`

O comportamento esperado e:

- o servico transacional nao para
- o backlog cresce enquanto o consolidado esta offline
- o backlog volta para `0` quando o consolidado retorna
- o saldo diario e recomposto corretamente

## Cobertura dos requisitos do desafio

| Item pedido em `init.md` | Onde foi atendido |
| --- | --- |
| Servico que faca o controle de lancamentos | `services/transactions_service/main.py` |
| Servico do consolidado diario | `services/balance_service/main.py` |
| Mapeamento de dominios funcionais e capacidades de negocio | `docs/architecture.md` |
| Refinamento de requisitos funcionais e nao funcionais | `docs/requirements.md` |
| Desenho completo da Arquitetura Alvo | `docs/architecture.md` |
| Justificativa de ferramentas, tecnologias e arquitetura | `docs/architecture.md` |
| Testes | `tests/` |
| README com execucao local clara | `README.md` |
| Documentacoes no repositorio | `docs/` e `README.md` |
| Arquitetura de transicao | `docs/transition-architecture.md` |
| Estimativa de custos | `docs/differentials.md` |
| Monitoramento e observabilidade | `docs/differentials.md` e endpoints `/health` |
| Criterios de seguranca para integracao | `docs/differentials.md` |

## Documentacao arquitetural

- [Arquitetura alvo e decisoes](docs/architecture.md)
- [Arquitetura de transicao](docs/transition-architecture.md)
- [Requisitos refinados](docs/requirements.md)
- [Diferenciais, custos, seguranca e observabilidade](docs/differentials.md)
- [Evidencias de execucao](docs/evidence.md)

## Decisao de implementacao

Para facilitar a avaliacao e a execucao local, a prova de conceito usa SQLite e um backlog persistido na mesma base local. Na arquitetura alvo documentada, a evolucao recomendada e substituir o backlog local por um broker de mensageria e bancos independentes por servico.

## Publicacao em GitHub

O projeto **ja esta publicado** no GitHub publico e sincronizado com o remoto:

```text
https://github.com/wiljdias-git/desafio-arquiteto-solucoes-jan25
```

Estado atual do repositorio local:

- branch: `main`
- remoto: `origin`
- sincronizado com `origin/main`

Para enviar novas alteracoes apos futuras mudancas:

```bash
git add .
git commit -m "sua mensagem"
git push origin main
```
