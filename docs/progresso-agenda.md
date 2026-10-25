# Progresso — agente AGENDA (`feat/agenda`)

Escopo: sessões de aula, reservas (capacidade transacional), grade semanal, painel operacional com gaveta, evolução e
avaliação, aula avulsa e avaliativa, job R6, serviço `agenda/servico.py` para os outros módulos e componentes da ficha do aluno.
Dono de: `backend/app/modules/agenda/`, `backend/tests/agenda/`, `frontend/app/(app)/agenda/`, `frontend/components/agenda/`,
`frontend/lib/tipos-agenda.ts` (e um arquivo novo de domínio, `backend/app/domain/painel.py`).

## Como rodar

```bash
cd backend && uv sync
uv run python -m pytest -q tests/agenda tests/test_cobertura_rotas.py     # 140 testes da agenda (~2 min, o login é lento)
uv run python -m pytest -q                                                # suíte inteira
uv run python -m ruff check app/modules/agenda app/domain/painel.py tests/agenda
cd ../frontend && npm install && npm run lint && npm run build
```
Telas: `/agenda/semana` (grade) e `/agenda/aulas` (painel operacional). Os componentes da ficha do aluno
(`aba-aluno-aulas.tsx`, `aba-aluno-evolucao.tsx`, `aba-aluno-avaliacao.tsx`, todos com `{ alunoId: number }`) esperam
ser ligados pelo coordenador. Dependências novas no `pyproject.toml`: `reportlab` e `openpyxl` (exportação PDF/Excel).

## Feito

| Item | Onde |
|---|---|
| Sessões: criar, editar, excluir, listar, detalhe; unicidade do índice `uq_aula_sessao_slot` (inclui aula sem profissional); capacidade vazia = herda da unidade | `routes.py`, `servico.py` |
| Geração de aulas **só por POST** (`/agenda/sessoes/gerar`), idempotente, pula bloqueios; nenhum GET cria ou altera dado (teste dedicado) | `servico.gerar_sessoes` |
| Reservas: criar (aula existente ou horário novo), remarcar (R3), desmarcar com reposição (R4), chegou/finalizar/faltou/faltou avisando, excluir, confirmar | `servico.py` |
| Capacidade transacional com `ocupar_vaga`/`liberar_vaga`, mensagem "N de M vagas ocupadas" do domínio; 3 testes com threads | `servico._trocar_status` |
| `servico`: `obter_ou_criar_sessao`, `criar_reserva`, `gerar_agenda_do_contrato`, `confirmar_reserva`, `desmarcar_reserva_do_aluno`, `calcular_slots`, `concluir_aulas_passadas` | `servico.py` |
| Grade semanal (API + tela): seg–sáb, blocos por status, ocupação n/m, colunas lado a lado, filtro por profissional, anterior/hoje/próxima; sáb/dom mostram a próxima semana | `consultas.montar_grade`, `grade-semanal.tsx` |
| Painel operacional (API + tela): Hoje/Amanhã/Semana, data alvo, unidade, profissional, status, busca (nome, CPF, telefone); agrupado por **horário > profissional > alunos**; cartões com plano, serviços, confirmado, preliminares, cobrança (só com permissão financeira) e ações rápidas | `consultas.montar_painel`, `painel-operacional.tsx` |
| Gaveta lateral: ações (chegou, finalizar, faltou, remarcar, desmarcar, excluir) e abas Evolução, Avaliações e Cobrança (só financeiro); rola por dentro | `gaveta-aluno.tsx` |
| Evolução e avaliação por reserva: CRUD, modelo de evolução como ponto de partida, salvar e finalizar aula, histórico por aluno, exportar PDF/Excel, ditado por voz, melhorar texto com IA | `evolucao.py`, `editor-registro.tsx` |
| Aula avulsa (com e sem cobrança, R12) e avaliativa (TotalPass/WellHub/avaliação, ficha, converter) | `avulsa.py` |
| Job R6 a cada 5 min (`agenda-concluir-aulas-passadas`), idempotente, com log e auditoria | `tarefas.py` |
| Permissões (`adicionar_regras`), login + auditoria em toda escrita, perfil Professor por `escopo` | `routes.py` |
| Menu: só as duas entradas da Agenda viraram `planejado: false` | `nav.ts` |

### Rotas (todas sob `/api`)

`GET /agenda/opcoes` · `GET /agenda/grade` · `GET|POST /agenda/sessoes` · `GET|PATCH|DELETE /agenda/sessoes/{id}` ·
`POST /agenda/sessoes/gerar` · `POST /agenda/reservas` · `GET /agenda/reservas/{id}/horarios` ·
`GET /agenda/alunos/{id}/{reservas|evolucoes|avaliacoes|avulsas|avaliativas}` ·
`GET /agenda/alunos/{id}/{evolucoes|avaliacoes}/exportar?formato=pdf|xlsx` · `GET /agenda/avulsas/slots` · `POST /agenda/avulsas` ·
`POST /agenda/avaliativas` · `PUT /agenda/avaliativas/{id}/ficha` · `POST /agenda/avaliativas/{id}/converter` ·
`GET /aulas/painel` · `GET /aulas/reservas/{id}[/historico|/cobranca]` · `POST /aulas/reservas/{id}/{presenca|confirmar|desmarcar|remarcar}` ·
`DELETE /aulas/reservas/{id}` · `GET|POST /aulas/reservas/{id}/{evolucao|avaliacao}` ·
`PATCH|DELETE /aulas/{evolucoes|avaliacoes}/{id}` · `POST /aulas/evolucoes/melhorar`.

Permissões: sessões e reservas novas = `agenda.*`; painel = `aulas.ver`; remarcar/desmarcar/excluir/confirmar = `aulas.operar`
**e** não ser Professor; chegou/finalizar/faltou = `aulas.operar` **ou** `aulas.evoluir`; evolução = `aulas.evoluir`;
avaliação e ficha avaliativa = `aulas.avaliar`; cobrança = `financeiro_receber.ver` (nunca Professor).

## Decisões (e o que mudou em relação ao sistema antigo)

1. **Nada é criado ou concluído em GET.** O antigo criava aulas ao listar horários de remarcação e concluía aulas ao abrir telas
   (`# COMPORTAMENTO ANTIGO` removido). Remarcação lista opções sem criar; a aula nasce ao confirmar. Geração é `POST /agenda/sessoes/gerar`.
2. **Capacidade (R3)**: toda mudança de/para RESERVADA passa por `_trocar_status`. "Chegou" numa aula lotada (aluno que tinha faltado e
   perdeu a vaga) é recusado com "N de M". `# COMPORTAMENTO ANTIGO` corrigido: o antigo deixava estourar a lotação por "chegou" e deixava
   remarcar para capacidade 0.
3. **Atomicidade**: os serviços não fazem `commit`; a rota desfaz tudo em erro. Datas/aulas que podem falhar sozinhas usam SAVEPOINT.
   No SQLite (dev/testes) um `UPDATE` vazio força o `BEGIN` antes do SAVEPOINT (senão o RELEASE gravaria tudo); no PostgreSQL não faz nada.
   Leituras que usam `reservas_ativas` ignoram o cache da sessão (`populate_existing`), porque o contador muda por UPDATE direto.
4. **Desmarcar (R4)**: `reposicao_ate = data + 30 dias`, `desmarcada_em = agora`, `confirmada_em = None`. Não replicado: desmarcar de novo uma aula já
   desmarcada (o antigo reescrevia o prazo e estendia a reposição) agora responde 409. A regra das 6 horas **continua desligada** (`aviso_minimo_cumprido(ativo=False)`).
5. **Reposição consumida (novo)**: remarcar uma aula desmarcada só vale até `reposicao_ate` (a equipe pode ignorar o prazo com `ignorar_prazo_reposicao`);
   ao remarcar, `reposicao_ate` zera. Remarcar também zera `confirmada_em` (valia para o horário antigo).
6. **"Chegou"** (`# COMPORTAMENTO ANTIGO`): só grava RESERVADA (em aula é derivado do horário); a única adição é gravar `confirmada_em` se vazio.
   No painel, "Confirmado" passou a significar `confirmada_em` preenchido (o antigo mostrava "Confirmado" para qualquer reserva que não fosse PENDENTE).
7. **Excluir reserva**: libera a vaga e apaga a aula só se ficar vazia (a reserva é o único vínculo da aula no modelo). Recusa (409) se há evolução,
   avaliação ou cobrança **paga** (o antigo apagava tudo em cascata, R13); cobranças **abertas** da reserva são canceladas.
8. **Aula avulsa**: 1 reserva e 1 cobrança por aula, sempre no serviço do plano (**corrigido** o horário com 2 serviços que cobrava 2x — teste dedicado).
   Valor 0 (TotalPass/WellHub/cortesia) não cobra. `valor_total = valor_aula x quantidade` (flag `MULTIPLICAR_TOTAL_DO_PACOTE`; o antigo gravava só o valor de uma aula).
   O horário é validado contra os slots oferecidos (antes de gravar); bloqueio/lotação de uma data viram avisos e as outras aulas ficam; se nenhuma aula entra, nada é gravado.
9. **Aula avaliativa**: atômica (`# COMPORTAMENTO ANTIGO` corrigido: sem vaga o antigo deixava a ficha solta). "Converter" só marca CONVERTIDA e **não cria contrato** (mantido e documentado na API e na tela).
10. **Agenda do contrato** (`gerar_agenda_do_contrato`): valida TUDO antes de gravar (o antigo deixava as reservas do 1º horário quando o 2º era recusado);
    não sobrescreve profissional de aula existente; devolve `conflitos` sem desfazer o resto (`# COMPORTAMENTO ANTIGO`: sucesso parcial); idempotente; grava `reserva.contrato_id`;
    contrato SEMANAL = 4 semanas e 1 aula por semana. O horário só é oferecido se **todas** as datas daquele dia têm vaga e não estão bloqueadas (regra do antigo, vinda do domínio).
11. **Evolução**: Professor registra sempre como ele mesmo e só em reserva de aula dele (id alheio = 404, não revela). `# COMPORTAMENTO ANTIGO` mantido: ao abrir um aluno das próprias
    aulas, o Professor vê as evoluções de **todos** os professores daquele aluno. Exportação neutraliza fórmulas do Excel. Sem IA configurada (ou falha do provedor) o texto volta intacto com `aviso`.
12. **Painel**: status exibido (`aguardando_chegar`, `em_aula`, `finalizada`, `faltou`, `remarcada`) vem de `domain.status_aula` (R5). Não existe "ATRASADO" no domínio de aulas; o "ATRASADO" que aparece é o da **cobrança**, derivado por `domain.financeiro`.
    WhatsApp e "Enviar agora" são botões **desabilitados** (ponto de extensão da onda de comunicação). Texto dos cartões é sempre texto (React escapa).
13. **Job R6**: conclui RESERVADA/PENDENTE cuja aula acabou (fim <= agora, inclusive), libera a vaga das RESERVADA e grava uma linha de auditoria ("Robô") por execução com resultado.
14. **Auditoria**: `audit.snapshot` do core não serializa `time` (hora da aula); a rota converte antes de gravar (pedido ao coordenador abaixo).
15. **Dia de hoje** é o de Brasília (`hoje_de_negocio`), em grade, painel e prazos.

## Pedidos ao coordenador

- **Resolvedor de profissional**: `escopo.registrar_resolvedor_profissional` (CADASTROS-BASE). Meus testes registram um de teste (`Profissional.usuario_id`).
- **Perfil Professor**: manter **sem** `aulas.operar` (o teste do core exige). Chegou/finalizar/faltou funcionam por `aulas.evoluir`. Se algum dia o perfil ganhar `aulas.operar`, R4 continua valendo (a rota barra Professor).
- **Ficha do aluno**: ligar `AbaAlunoAulas`, `AbaAlunoEvolucao`, `AbaAlunoAvaliacao` (`{ alunoId: number }`). A gaveta tem um link para `/alunos/{id}` (aparece só com `alunos.ver`).
- **`core/audit._jsonable`**: aceitar `datetime.time` (hoje contorno na rota).
- **Contratos**: usar `agenda.servico.gerar_agenda_do_contrato(...)` (e `criar_reserva` com `contrato_id`). R13 pode apagar por `reserva.contrato_id`.
- **App do aluno / TotalPass**: usar `servico.confirmar_reserva(db, reserva_id, aluno_id=...)`, `servico.desmarcar_reserva_do_aluno(...)`, `obter_ou_criar_sessao(profissional_id=None)` + `criar_reserva`.
- **Modelo**: nenhuma mudança (sem migração nova). Nenhum recurso novo no catálogo de permissões.
- **Dependências**: `reportlab` e `openpyxl` no `pyproject.toml`/`uv.lock`.
- **Cadastros**: a tela de horários de funcionamento precisa existir para a grade/avulsa/contrato oferecerem horários (sem horários, vale o plano B do antigo: aulas já existentes).

## Dúvidas para o Jefferson

1. O **total do pacote avulso** deve ser valor x quantidade (como está) ou só o valor de uma aula (antigo)?
2. Ligar a **regra das 6 horas** de aviso para desmarcar? E **falta avisada** deve gerar reposição como o desmarcar (hoje não)?
3. Pode **excluir** uma aula que já tem evolução ou cobrança paga? Hoje recusa e manda desmarcar.
4. O Professor deve ver evoluções de **outros professores** do mesmo aluno (como no antigo)?
5. "Confirmado" no painel = o aluno confirmou pelo app (ou a equipe confirmou). Está certo, ou "Chegou" também deve contar?
6. Aula avulsa: manter o professor do pacote único (como o antigo) ou permitir um por aula?

## Pendências / limites conhecidos

- A UI foi validada por `npm run lint` e `npm run build` e pelos contratos da API (testes), **não** num navegador real nesta máquina.
- Tela de **criar contrato/agenda do contrato** é do módulo de contratos (aqui só o serviço).
- Edição de aula pela ficha (`aluno_reserva_editar`) está coberta por remarcar (data, hora e professor); trocar só o status manualmente fica nas ações da gaveta.
- Sem consumo automático de reposição fora do prazo; a tela dedicada de reposição não foi pedida.
