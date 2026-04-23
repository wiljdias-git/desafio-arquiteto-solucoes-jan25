# Requisitos refinados

## Requisitos funcionais

1. O sistema deve registrar lancamentos de debito e credito.
2. Cada lancamento deve possuir tipo, valor, data e descricao opcional.
3. O sistema deve permitir listar lancamentos por data.
4. O sistema deve consolidar o saldo diario a partir dos lancamentos recebidos.
5. O sistema deve permitir consultar o saldo consolidado por data.
6. O sistema deve expor saude operacional basica dos dois servicos.

## Requisitos nao funcionais refinados

1. O servico de lancamentos deve continuar respondendo mesmo com indisponibilidade do servico de consolidado.
2. O consolidado deve conseguir recuperar backlog pendente apos retorno do servico.
3. O endpoint de consulta de saldo deve suportar pico de 50 requisicoes por segundo com perda observada menor ou igual a 5% na demonstracao local.
4. As APIs devem usar contratos simples, validacao de payload e codigos HTTP coerentes.
5. A execucao local deve ser simples, sem dependencia obrigatoria de infraestrutura externa.

## Assuncoes adotadas

- O saldo diario e calculado por data informada no lancamento.
- O endpoint `GET /balances/{data}` retorna `0.00` quando nao houver movimentos para o dia.
- O valor monetario e tratado em centavos para evitar erro de ponto flutuante na persistencia.
- O timezone de referencia da prova de conceito e a data enviada pelo cliente.
- Nao ha autenticacao implementada na POC local, mas o desenho de seguranca esta documentado.

## Criterios de aceite da implementacao

- Criar lancamentos de credito e debito com persistencia.
- Consultar extrato simples de lancamentos.
- Consolidar saldo diario corretamente.
- Demonstrar backlog pendente quando o consolidado estiver parado.
- Demonstrar processamento do backlog quando o consolidado voltar.
- Executar testes automatizados com sucesso.
