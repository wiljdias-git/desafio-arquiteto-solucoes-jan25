# Arquitetura alvo

## Dominios funcionais e capacidades de negocio

| Dominio funcional | Capacidade de negocio | Responsabilidade |
| --- | --- | --- |
| Gestao de Caixa | Registrar lancamentos | Receber debitos e creditos do comerciante com rastreabilidade |
| Gestao de Caixa | Consultar extrato diario | Expor historico de lancamentos por dia |
| Consolidacao Financeira | Consolidar saldo diario | Transformar eventos de lancamento em saldo por data |
| Operacao da Plataforma | Monitorar saude e fila | Medir backlog, disponibilidade e comportamento operacional |
| Seguranca e Governanca | Proteger APIs | Validar entrada, reduzir perda de dados e preparar evolucao de autenticacao |

## Desenho de contexto

```mermaid
flowchart TB
    Merchant[Comerciante]
    Backoffice[Operacao / Suporte]
    TS[Transactions Service]
    BS[Balance Service]
    OBS[Observabilidade]

    Merchant -->|registra debitos e creditos| TS
    Merchant -->|consulta saldo diario| BS
    Backoffice -->|acompanha saude e backlog| OBS
    TS --> OBS
    BS --> OBS
```

## Arquitetura proposta

```mermaid
flowchart LR
    Merchant[Comerciante / Cliente] -->|POST /entries| TS[Transactions Service]
    Merchant -->|GET /balances/{data}| BS[Balance Service]
    TS -->|grava lancamento| DB[(SQLite / ledger_entries)]
    TS -->|persiste backlog| BL[(SQLite / consolidation_backlog)]
    BS -->|consome backlog| BL
    BS -->|atualiza saldo diario| BAL[(SQLite / daily_balances)]
    TS -->|health| OPS[Monitoramento]
    BS -->|health| OPS
```

## Desenho de componentes

```mermaid
flowchart LR
    subgraph Transactions Service
        API1[REST API]
        APP1[Validacao e regras]
        REPO1[Ledger repository]
    end

    subgraph Balance Service
        API2[REST API]
        WORKER[Backlog worker]
        REPO2[Balance repository]
    end

    subgraph Persistencia
        L[(ledger_entries)]
        B[(consolidation_backlog)]
        D[(daily_balances)]
    end

    API1 --> APP1 --> REPO1
    REPO1 --> L
    REPO1 --> B
    WORKER --> B
    WORKER --> REPO2 --> D
    API2 --> REPO2
```

## Fluxo de consolidacao

```mermaid
sequenceDiagram
    participant C as Cliente
    participant T as Transactions Service
    participant B as Backlog Persistido
    participant S as Balance Service
    participant D as Saldo Diario

    C->>T: POST /entries
    T->>T: Valida payload e persiste lancamento
    T->>B: Persiste evento pendente
    T-->>C: 201 Created
    loop Polling
        S->>B: Busca eventos pendentes
        S->>D: Soma ou subtrai valor do dia
        S->>B: Marca evento como processado
    end
    C->>S: GET /balances/{data}
    S-->>C: Saldo diario consolidado
```

## Justificativa de arquitetura e tecnologias

### Estilo arquitetural

- **Escolha para a prova de conceito**: servicos independentes dentro de um monorepo.
- **Motivacao**: manter separacao clara de responsabilidade sem elevar demais a complexidade operacional local.
- **Trade-off**: um monorepo simplifica onboarding, testes e demonstracao, mas a arquitetura alvo documentada admite evolucao para deploy separado por servico.

### Linguagem e framework

- **Python + FastAPI**
  - produtividade alta para prova tecnica
  - validacao forte com Pydantic
  - documentacao OpenAPI nativa
  - boa ergonomia para APIs e testes

### Persistencia

- **SQLite na prova de conceito**
  - setup local imediato
  - sem dependencia externa para avaliacao
  - suficiente para demonstrar regras de negocio, backlog e resiliencia
- **Evolucao recomendada**
  - PostgreSQL para dados transacionais
  - broker de eventos para desacoplamento do consolidado

## Como a solucao atende os requisitos nao funcionais

| Requisito | Mecanismo adotado |
| --- | --- |
| Lancamentos nao podem parar se o consolidado cair | O Transactions Service apenas grava lancamento e backlog persistido, sem depender de chamada sincrona ao Balance Service |
| 50 requisicoes por segundo no consolidado | Endpoint de leitura simples, acesso por chave de data e script de carga com 50 requisicoes concorrentes |
| Ate 5% de perda | Persistencia local, processamento idempotente por backlog e demonstracao por script de carga |
| Disponibilidade | Separacao entre APIs e health endpoints independentes |
| Resiliencia | Recuperacao por backlog persistido quando o consolidado volta |
| Observabilidade | Health endpoints e backlog exposto para monitoramento |

## Fronteiras de contexto

- **Transactions Service**
  - dono do cadastro de lancamentos
  - aceita entradas do dominio financeiro operacional
- **Balance Service**
  - dono da visao consolidada
  - materializa leitura otimizada por dia

## Desenho de deploy recomendado

```mermaid
flowchart LR
    Client[Cliente]
    APIM[Gateway / API Management]
    TS[Container App - Transactions]
    BS[Container App - Balance]
    PG[(PostgreSQL)]
    MQ[(Broker de mensagens)]
    MON[Monitoramento]

    Client --> APIM
    APIM --> TS
    APIM --> BS
    TS --> PG
    TS --> MQ
    BS --> MQ
    BS --> PG
    TS --> MON
    BS --> MON
```

## Riscos conhecidos e mitigacoes

| Risco | Mitigacao |
| --- | --- |
| Acoplamento por banco local na POC | Evoluir para banco por servico e mensageria dedicada |
| Crescimento de volume historico | Particionamento/log compaction na evolucao com PostgreSQL e broker |
| Reprocessamento concorrente | Lock local no Balance Service e backlog com status processado |
