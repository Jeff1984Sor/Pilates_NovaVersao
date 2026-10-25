# Progresso — agente PAINEL (`feat/painel`)

Escopo: tela inicial `/dashboard` (substitui o espaço reservado) e `GET /api/painel/resumo`. Origem: `dashboard` do Django (`core/views.py`
~555–700) e `dashboard.html`. Não há tabela nova, nem migração, nem alteração de modelo ou do core.

## Como rodar

```bash
cd backend
uv run python -m pytest -q tests/painel tests/test_cobertura_rotas.py      # 27 testes do painel + cobertura de rotas
uv run python -m ruff check app/modules/painel tests/painel
cd ../frontend && npm install && npm run lint && npm run build
```

## Pronto

| Item | Onde |
|---|---|
| API `GET /api/painel/resumo` (uma chamada, 15 consultas agregadas no banco para o perfil Full) | `backend/app/modules/painel/` (`routes.py`, `schemas.py`, `servico.py`) |
| KPIs clicáveis (com `href`): alunos ativos, aulas hoje/amanhã, contratos vencendo em 30 dias, a receber em aberto, atrasado | idem |
| Recebido no mês + comparação com o mês anterior (`deslocar_mes_limitado`/`ultimo_dia_do_mes_anterior` de `domain.financeiro`) | idem |
| Aulas por mês (6 meses), ranking de professores do mês (top 6), próximas aulas de hoje (até 8), aniversariantes (hoje + 7 dias, virada de ano e 29/02) | idem |
| Alertas: contas atrasadas, aulas passadas sem evolução, contratos não assinados, reposições pendentes, WhatsApp (sessão caída / avisos automáticos desligados), TotalPass com erro | idem |
| Tela: saudação + data, KPI cards, gráfico Recharts, listas com estado vazio, esqueleto, atualização a cada 60 s, botão Atualizar, "Primeiros passos" | `frontend/app/(app)/dashboard/page.tsx`, `frontend/components/painel/`, `frontend/lib/tipos-painel.ts` |
| Testes (27): números, recebido/comparação, aulas por mês, ranking, aniversariantes (virada de ano, 29/02), alertas, banco vazio, data de negócio (23h e 00:30 em Brasília, virada de mês), perfis, desempenho (conta consultas) | `backend/tests/painel/` |

## Decisões

1. **Permissão**: a rota exige `painel.ver` (regra registrada com `adicionar_regras`). **O conteúdo respeita o perfil**: cada bloco traz `visivel` e, sem a permissão do assunto, nem é calculado (valores `null`). Assuntos: `alunos.ver` (alunos ativos, aniversariantes, nome do aluno nas próximas aulas), `aulas.ver` (aulas, gráfico, ranking, próximas, "sem evolução"), `contratos.ver` (contratos vencendo e não assinados), `financeiro_receber.ver` (a receber, atrasado, recebido no mês, alerta de atraso), `reposicoes.ver`, `whatsapp.configurar` (só Full) e `integracoes.ver` (só Full) para os alertas de integração, `cadastros_unidades.editar` (Full) para "Primeiros passos".
2. **Professor**: a API responde **200 com só as próprias aulas** (não 403) e **nunca** entrega financeiro, contratos, alunos, aniversariantes, reposições ou alertas de integração, **mesmo que o perfil receba essas permissões** (`ASSUNTOS_DO_RESTRITO` = painel, aulas, agenda). Nas próximas aulas o nome do aluno vem `null`. O frontend redireciona o Professor para `/agenda/aulas` (como no antigo). Sem profissional vinculado, ele não vê nada.
3. **Data de negócio**: "hoje" = `hoje_de_negocio(agora)` (America/Sao_Paulo). Às 23h30 de Brasília ainda é o mesmo dia; conta que vence hoje não é atraso. O "agora" é `routes._agora()` (trocável nos testes).
4. **Definições**: aula = reserva não cancelada (como o antigo); "próximas aulas" = reservas RESERVADA/PENDENTE de hoje cuja aula ainda não terminou; "a receber" = ABERTO com vencimento de hoje em diante; "atrasado" = ABERTO vencido antes de hoje; recebido no mês = PAGO com `pagamento` no mês; **variação** compara o recebido do mês com o do mês anterior **até o mesmo dia** (comparação justa); o mês anterior inteiro vem em `mes_anterior`; sem base (zero) não inventa percentual. Contrato vencendo = `data_fim` entre hoje e hoje+30 (inclusive). Contratos não assinados = vigentes (`data_fim >= hoje`) com status NAO_ASSINADO. Aulas sem evolução = reservas CONCLUIDA dos últimos 30 dias sem registro em `evolucao`. Aniversariantes = só alunos ATIVOS; 29/02 comemora em 28/02 nos anos sem bissexto.
5. **Alertas de integração**: WhatsApp "sessão caída" lê o log de alertas já gravado pelo envio automático (`whatsapp_agendamento_log`, tipo `alerta`, status `sessao_caida`/`credencial_recusada`, hoje ou ontem). O painel **não chama a internet**. "Avisos desligados" só aparece se há credencial configurada. TotalPass: eventos com `resultado = 'erro'` nos últimos 3 dias.
6. **Primeiros passos** (unidade, serviço, plano, profissional, aluno; WhatsApp aparece como sugestão que não segura o bloco) só para quem pode cadastrar unidades; some quando os 5 primeiros estão feitos. `vazio=true` quando não há aluno.
7. **Desempenho**: o Full faz 15 consultas (inclui autenticação); o número **não cresce com o volume** (teste cria 50 alunos/reservas/contas e confere que continua igual). O limite do teste é 18.

## Pedidos ao coordenador

- **Filtros nos `href` dos KPIs**: apontam para `/alunos?status=ATIVO`, `/agenda/aulas`, `/contratos?vencendo=30`, `/contratos?assinatura=NAO_ASSINADO`, `/financeiro/receber?status=ABERTO|ATRASADO|PAGO`. As telas de lista de alunos, contratos e contas a receber **ainda não leem a query string** (só abrem a lista). Pedir aos donos desses módulos para aceitarem esses parâmetros (o painel não edita telas de outros módulos).
- `nav.ts`: nada a mudar (o item "Painel" já aponta para `/dashboard` com `painel.ver`).
- Catálogo de permissões: nada novo foi necessário.

## Dúvidas para o Jefferson

1. Aniversariantes: só alunos ativos (o antigo listava todos do mês). Pode?
2. "Aulas passadas sem evolução" olha só os últimos 30 dias para não virar um alerta eterno. Prazo adequado?
3. Contratos vencendo: o antigo avisava em 7 dias; aqui são 30, como pedido. Quer os dois?
