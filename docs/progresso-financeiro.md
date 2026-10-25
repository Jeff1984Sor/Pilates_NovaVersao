# Progresso — agente FINANCEIRO (`feat/financeiro`)

Escopo: contas a receber, contas a pagar, contas bancárias e movimentos, fluxo de caixa, DRE, Receita Saúde (por aluno e em lote)
e comissões, com API, testes e telas. Regras de negócio vêm de `app/domain` (R2, R7, R8, R12, R17); nada foi reimplementado.

## Como rodar

```bash
cd backend
uv sync
uv run python -m pytest -q tests/financeiro tests/test_cobertura_rotas.py     # 92 testes do financeiro + cobertura de rotas
uv run python -m ruff check app/modules/financeiro tests/financeiro
cd ../frontend && npm install && npm run lint && npm run build
```

## Pronto

| Item | API | Tela | Testes |
|---|---|---|---|
| Contas a receber: lista com chips (Todos/Aberto/Pago/Atrasado/Cancelado, contagem e valor), filtros (período, aluno, plano, competência, busca), baixa (data + forma + conta bancária), estorno, cancelar com motivo, reabrir, editar, excluir, valor avulso, recibo PDF (logo e nome do estúdio, dados do aluno), Excel/PDF por aluno e geral, cobrança por WhatsApp (ponto de extensão desabilitado) | `rotas_receber.py` | `financeiro/receber`, `components/financeiro/tabela-receber.tsx` | `test_receber.py` |
| Aba financeira da ficha do aluno | `GET /financeiro/receber?aluno_id=` + `/aluno/{id}/resumo` | `components/financeiro/aba-aluno-financeiro.tsx` (props `{alunoId: number}`) | `test_receber.py` |
| Contas a pagar: fornecedor, categoria/subcategoria, recorrência SEMANAL/MENSAL/ANUAL (N lançamentos, sem cascata), pagar com comprovante (`core.storage`), cancelar com motivo, reabrir, excluir, exportar | `rotas_pagar.py`, `pagar.py` | `financeiro/pagar` | `test_pagar.py` |
| Contas bancárias e movimentos: saldo sempre calculado, movimento com comprovante, transferência, extrato com saldo de abertura, baixa/pagamento gerando movimento (opcional, por requisição) | `rotas_bancos.py`, `bancos.py` | `financeiro/bancos` | `test_bancos.py` |
| Fluxo de caixa (por vencimento, sem cancelado, comparativo com o mês anterior) e DRE (por pagamento) com Excel/PDF e gráficos Recharts | `rotas_relatorios.py`, `relatorios.py` | `financeiro/caixa`, `financeiro/dre` | `test_relatorios.py` |
| Receita Saúde: configuração (CPF validado, CREFITO, ocupação, descrição), por aluno (`components/financeiro/recibos-saude-aluno.tsx`, dentro da aba do aluno), em lote por mês (problemas por linha antes de gerar, ZIP quando passa de 1000 linhas ou muda o ano), duplicidade e liberar, passo a passo do e-CAC | `rotas_receita_saude.py`, `recibos_saude.py` | `receita-saude` | `test_receita_saude.py` |
| Comissões: gerar por competência sobre contas PAGAS, listar, marcar como paga, desfazer, excluir (não paga), exportar | `rotas_comissoes.py`, `comissoes.py` | `comissoes` | `test_comissoes.py` |
| `servico.py` estável: `gerar_contas_do_contrato`, `criar_conta_aula_avulsa`, `resumo_financeiro_do_aluno`, `hoje_de_negocio_agora`, `definir_cobrador` | — | — | `test_servico.py` |
| Permissões por perfil, nenhuma escrita por GET, auditoria em toda escrita | — | — | `test_seguranca.py`, `test_opcoes.py` |

Menu: as 7 entradas de Financeiro estão com `planejado` removido em `nav.ts`.

## Decisões

1. **ATRASADO derivado** pela data de negócio (`hoje_de_negocio`, America/Sao_Paulo) em tudo: lista, chips, resumo, fluxo e exportações. Vencer hoje não é atraso.
2. **Nenhuma escrita por GET.** Baixar = `POST /financeiro/receber/{id}/baixa`; estornar = `DELETE` no mesmo caminho; excluir = `DELETE /{id}`. Teste varre as rotas e confere que toda rota não-GET chama `ctx.auditar`.
3. **Baixa**: a data não pode ser futura (422); só conta ABERTA pode ser baixada; a forma de pagamento (Pix, dinheiro, crédito, débito) é gravada. Com `conta_bancaria_id` gera um `MovimentoConta` ENTRADA ligado à conta (`conta_receber_id`); o estorno apaga esse movimento. "Configurável" = escolhido a cada baixa/pagamento (sem chave global).
4. **Estorno** é recusado quando o arquivo do Receita Saúde daquele pagamento já foi gerado (libere antes) ou quando há comissão gerada (exclua a comissão antes). Conta paga não pode ser excluída nem cancelada; conta paga só aceita editar a descrição.
5. **Recorrência de contas a pagar** (`domain.planejar_recorrencia_pagar`): a original guarda `recorrencia` e `recorrencia_quantidade`; as cópias nascem **sem recorrência** e ligadas por `recorrencia_grupo`. Editar nunca regenera (resolve o risco de cascata do antigo).
6. **DRE e fluxo usam o mesmo critério de saldo bancário**: saldo inicial + movimentos só das contas **ativas** (o antigo somava contas inativas na DRE). Receitas por plano/categoria/subcategoria vêm só do plano do **contrato**; aula avulsa por reserva e lançamento avulso caem em "Sem plano" (como no antigo e como pediu a regra R7).
7. **Receita Saúde em lote** aceita um período de pagamento (a tela usa o mês). Gera só o que está pronto (sem problema e ainda não gerado); se o usuário marcar linha com problema, **nada** é gerado (tudo ou nada, vale para todos os arquivos do lote). Vários arquivos saem num ZIP. Por aluno, anos diferentes continuam sendo erro (regra do domínio). O CPF do pagador é gravado em `aluno.cpf_pagador_recibo` (coluna que já existia no módulo de alunos).
8. **Comissão**: profissional = o do contrato; para aula avulsa, o da sessão da reserva. Competência estrita `AAAA-MM` na API (o antigo aceitava `2026-1`).
9. **Comprovantes**: categoria de storage `comprovantes` (PDF/PNG/JPG/WEBP, 8 MB) com permissão `financeiro_pagar.ver` para ler por `/api/arquivos/...`; também há rotas próprias (`/financeiro/pagar/{id}/comprovante`, `/financeiro/bancos/movimentos/{id}/comprovante`). Os caminhos do ETL (`comprovantes/contas_pagar/...`, `comprovantes/movimentos/...`) continuam válidos.
10. **Opções dos formulários** (`/financeiro/receber/opcoes`, `/financeiro/pagar/opcoes`): planos, fornecedores, categorias com subcategorias e contas bancárias ativas, lidos direto do banco. Assim as telas não dependem das rotas dos módulos de cadastros (que ainda não existem) e a Secretária consegue escolher a conta na baixa sem ter `financeiro_bancos.ver`.
11. **Recibo PDF** só para conta paga (o antigo imprimia "Recibo de Pagamento" até para conta aberta).
12. PDF/Excel: `reportlab` e `openpyxl` voltaram ao `pyproject.toml`.

## Alteração de modelo (aditiva) — o coordenador precisa gerar a migração

`backend/app/modules/financeiro/models.py` (nenhuma coluna removida ou alterada; a `0001` não foi tocada):

| Tabela | Coluna nova | Para quê |
|---|---|---|
| `conta_receber` | `forma_pagamento` String(20) nulo | forma usada na baixa (Pix, dinheiro...) |
| `conta_receber` | `motivo_cancelamento` Text nulo | cancelamento com motivo |
| `conta_pagar` | `descricao` String(200) nulo | descrição livre |
| `conta_pagar` | `recorrencia_grupo` String(36) nulo, índice | vincula os lançamentos de uma recorrência |
| `movimento_conta` | `conta_receber_id` FK nulo (`SET NULL`), índice | movimento gerado pela baixa |
| `movimento_conta` | `conta_pagar_id` FK nulo (`SET NULL`), índice | movimento gerado pelo pagamento |
| `movimento_conta` | `transferencia_id` String(36) nulo, índice | par de uma transferência entre contas |
| `comissao` | `paga_em` Date nulo | comissão repassada ao profissional |

Atenção: `tests/dados/test_migracao.py` compara a migração `0001` com `create_all`; ele falha até a migração dessas colunas existir
(`uv run python -m alembic revision --autogenerate -m "financeiro: colunas aditivas"`). Os testes do financeiro usam `create_all`.

## Pedidos ao coordenador

- **Migração** das colunas acima (e conferir `test_migracao`).
- **Catálogo/permissões**: nada novo foi preciso. Usei `financeiro_receber/pagar/caixa/dre/bancos`, `receita_saude`, `comissoes` e `whatsapp.enviar` (só para a cobrança por WhatsApp, regra registrada em `routes.py`). Sugestão: `receita_saude.configurar` separado de `gerar` (hoje salvar a configuração exige `receita_saude.gerar`).
- **Ficha do aluno** (módulo de alunos): montar `<AbaAlunoFinanceiro alunoId={aluno.id} />` de `components/financeiro/aba-aluno-financeiro.tsx` na aba Financeiro. O componente já respeita as permissões (sem `financeiro_receber.ver` só mostra o bloco do Receita Saúde, e sem `receita_saude.ver` esconde o bloco).
- **Contratos**: chamar `servico.gerar_contas_do_contrato(db, contrato)` ao criar o contrato (não faz commit; recusa se o contrato já tem contas). **Agenda**: `servico.criar_conta_aula_avulsa(...)` ao reservar aula avulsa (idempotente por reserva; valor 0 não cobra).
- **Comunicação**: registrar o envio da cobrança com `servico.definir_cobrador(fn)`, `fn(db, conta, aluno) -> mensagem`. Enquanto não houver cobrador, o botão da tela fica desabilitado ("em breve") e a rota responde 503.
- Excluir contrato (R13) ainda precisa decidir o que fazer com contas pagas; o financeiro recusa excluir conta paga e conta com comissão.

## Dúvidas para o Jefferson

1. A data do pagamento na baixa pode ser retroativa, mas **não futura** (o antigo aceitava qualquer data). Pode?
2. Recibo PDF só para conta paga está certo, ou a recepção imprime recibo de conta em aberto?
3. A Secretária hoje pode estornar a baixa (a permissão `financeiro_receber.baixar` cobre baixar e estornar). Quer separar?
4. Comissão: confirmar se sai sobre o valor pago da conta (como no protótipo) e se aula avulsa deve usar o profissional da aula.
5. O arquivo do Receita Saúde em lote por mês é por **data de pagamento**. Confirma (a Receita exige o mês do pagamento)?
6. Cobrança por WhatsApp: o texto atual do antigo ("Identificamos uma fatura em aberto...") será mantido pela onda de comunicação?

## Não verificado

- As telas foram compiladas (`npm run lint`, `npm run build`) mas **não foram exercitadas no navegador** com a API real; a API tem 92 testes automatizados do financeiro.
- O ETL traz `forma_pagamento`/`descricao`/`paga_em` vazios (campos novos).

## Suíte completa (25/10/2026)

`uv run python -m pytest -q` em `backend`: 2794 passaram e 1 falhou: `tests/dados/test_migracao.py::test_upgrade_igual_ao_create_all_e_downgrade_limpa`,
esperado até o coordenador gerar a migração das colunas aditivas acima. `npm run lint` e `npm run build` sem erro.
