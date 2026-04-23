# Diferenciais e evolucoes

## Arquitetura de transicao

Caso a origem seja um legado monolitico, a transicao recomendada e:

1. Extrair primeiro o **Transactions Service**, mantendo o monolito ainda responsavel pelo consolidado.
2. Publicar eventos de lancamento via outbox no legado.
3. Introduzir o **Balance Service** como consumidor assíncrono.
4. Migrar a leitura consolidada para o novo servico.
5. Desativar a funcionalidade equivalente no legado.

## Monitoramento e observabilidade

- Health checks independentes por servico.
- Medicao de backlog pendente.
- Recomendacao de evolucao:
  - logs estruturados
  - metricas Prometheus
  - traces OpenTelemetry
  - alertas para backlog crescente e falhas de consolidacao

## Seguranca para consumo de servicos

### POC atual

- validacao de payload com FastAPI/Pydantic
- separacao de responsabilidades entre escrita e leitura

### Evolucao recomendada

- autenticacao via OAuth2/OIDC ou JWT
- autorizacao por escopo para leitura e escrita
- rate limiting por cliente
- TLS fim a fim
- audit trail imutavel
- mascaramento de dados sensiveis em logs

## Estimativa simplificada de custos

### Ambiente minimo em nuvem

| Componente | Opcao sugerida | Objetivo |
| --- | --- | --- |
| API de lancamentos | Container App / App Service pequeno | escrita transacional |
| API de consolidado | Container App / App Service pequeno | leitura consolidada |
| Banco transacional | PostgreSQL gerenciado | persistencia primaria |
| Broker | Service Bus / RabbitMQ gerenciado | desacoplamento |
| Observabilidade | Application Insights / Grafana | saude e diagnostico |

Para um ambiente inicial de baixo volume, o custo pode ser mantido enxuto com instancias pequenas e escalonamento horizontal apenas no consolidado.

## Evolucoes futuras

- consolidado near real-time por streaming
- reprocessamento historico sob demanda
- multiempresa e multiusuario
- fechamento diario com trilha de auditoria
- dashboard operacional e financeiro
