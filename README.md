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

## Requisitos

- Python 3.12+
- `pip`

## Instalacao

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Executando os servicos

Em um terminal:

```bash
uvicorn services.transactions_service.main:app --host 0.0.0.0 --port 8000
```

Em outro terminal:

```bash
uvicorn services.balance_service.main:app --host 0.0.0.0 --port 8001
```

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
pytest
```

## Teste simples de carga

Com o servico de consolidado no ar:

```bash
python3 scripts/load_balance_service.py --url http://127.0.0.1:8001/balances/2026-01-25 --requests 100 --concurrency 50
```

O objetivo do script e demonstrar que a API atende uma rajada com **50 requisicoes concorrentes** e medir a taxa de perda observada.

## Documentacao arquitetural

- [Arquitetura alvo e decisoes](docs/architecture.md)
- [Requisitos refinados](docs/requirements.md)
- [Diferenciais, custos, seguranca e observabilidade](docs/differentials.md)

## Decisao de implementacao

Para facilitar a avaliacao e a execucao local, a prova de conceito usa SQLite e um backlog persistido na mesma base local. Na arquitetura alvo documentada, a evolucao recomendada e substituir o backlog local por um broker de mensageria e bancos independentes por servico.
