---
description: "Use quando estiver desenhando, implementando ou documentando a solucao do desafio de arquiteto de solucoes para controle de fluxo de caixa diario e consolidado diario. Cobre dominio, capacidades de negocio, requisitos nao funcionais, testes, README e justificativas arquiteturais."
name: "Desafio Arquiteto de Solucoes"
---
# Diretrizes do desafio

## Contexto do problema

- A solucao atende um comerciante que precisa controlar o fluxo de caixa diario.
- O sistema deve registrar lancamentos de debito e credito.
- O sistema tambem deve disponibilizar o saldo diario consolidado.
- Considere pelo menos dois servicos centrais:
  - controle de lancamentos
  - consolidado diario

## O que deve orientar a solucao

- Mapear dominios funcionais e capacidades de negocio antes de detalhar implementacao.
- Refinar requisitos funcionais e nao funcionais, deixando premissas e limites explicitos.
- Produzir um desenho completo da Arquitetura Alvo.
- Justificar as escolhas de arquitetura, ferramentas, tecnologias e padroes adotados.
- Priorizar solucoes escalaveis, reutilizaveis, flexiveis e alinhadas ao valor de negocio.
- Explicitar integracoes, responsabilidades, fronteiras de contexto e comunicacao entre componentes.

## Requisitos obrigatorios

- Servico para controle de lancamentos.
- Servico para consolidado diario.
- Mapeamento de dominios funcionais e capacidades de negocio.
- Refinamento do levantamento de requisitos funcionais e nao funcionais.
- Desenho completo da solucao.
- Justificativa das decisoes arquiteturais e tecnologicas.
- Testes.
- README com instrucoes claras para entendimento e execucao local.
- Toda a documentacao do projeto deve permanecer no repositorio.

## Requisitos nao funcionais criticos

- O servico de controle de lancamentos nao pode ficar indisponivel se o consolidado diario cair.
- Em picos, o servico de consolidado diario deve suportar 50 requisicoes por segundo.
- A perda maxima aceitavel em pico e de 5% das requisicoes.
- Considere resiliencia, observabilidade, seguranca, disponibilidade e desempenho como partes do desenho, nao como extras.

## Como avaliar trade-offs

- Compare estilos arquiteturais com clareza, como monolito modular, microsservicos, SOA ou serverless.
- Justifique mecanismos de integracao, protocolos, formatos de mensagem, fila/eventos e sincronismo vs assincronismo.
- Defina como a arquitetura lida com falhas, crescimento de carga, protecao de dados e operacao continua.
- Registre decisoes, fluxos, diagramas e racional tecnico sempre que houver escolha relevante.

## Entrega esperada

- O codigo nao precisa demonstrar sozinho todas as premissas; a documentacao arquitetural faz parte essencial da entrega.
- Valorize explicacoes objetivas sobre contexto, capacidades, decomposicao de dominios, componentes e boas praticas.
- Se algo ficar fora do escopo da implementacao, documente como evolucao futura ou melhoria desejada.
- Considere como diferenciais: arquitetura de transicao, estimativa de custos, monitoramento e criterios de seguranca para integracoes.
