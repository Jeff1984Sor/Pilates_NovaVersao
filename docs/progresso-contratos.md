# Progresso — agente CONTRATOS (`feat/contratos`)

Escopo: criar contrato (R1 + R2 + PDF, atômico), agenda do contrato, gestão (chips, filtros, editar, renovar, encerrar, recalcular),
exclusão segura (R13), PDF, envio (e-mail e ponto de extensão do WhatsApp), assinatura por link (R10) e local, termo de imagem por link,
componente da ficha do aluno.
Dono de: `backend/app/modules/contratos/`, `backend/tests/contratos/`, `frontend/app/(app)/contratos/`, `frontend/app/(publico)/`,
`frontend/components/contratos/`, `frontend/lib/tipos-contratos.ts`.

## Como rodar

```bash
cd backend && uv sync
uv run python -m pytest -q tests/contratos tests/test_cobertura_rotas.py     # 103 testes (~1 min)
uv run python -m ruff check app/modules/contratos tests/contratos
cd ../frontend && npm install && npm run lint && npm run build
```
Telas: `/contratos` (lista com chips), `/contratos/novo`, `/contratos/[id]`, `/contratos/[id]/agenda`; públicas (sem login):
`/assinar/contrato/[token]` e `/assinar/termo/[token]`. Verificado de ponta a ponta com uvicorn + `next start` (link → página →
assinatura pelo BFF → "já assinado"); sem dado real.

## Feito

| Item | Onde |
|---|---|
| Criar contrato: R1 (`domain.precos`) e R2 (`financeiro.servico.gerar_contas_do_contrato`) + PDF guardado como documento do aluno (`CONTRATO_PDF`), **tudo ou nada** (falha em parcelas, PDF, arquivo ou auditoria desfaz o banco e apaga o arquivo) | `servico.criar_contrato` |
| Precificação em tempo real (valor da aula, parcela, total e tabela de parcelas) sem gravar | `POST /contratos/precificar`, `form-contrato.tsx` |
| Agenda do contrato: opções (funcionamento − bloqueios − lotação, `agenda.servico.calcular_slots`), escolha exata de `aulas_por_semana`, um horário por dia, `contrato_id` (FK) em cada reserva; conflito listado sem desfazer o resto; idempotente | `servico.agenda_opcoes/gerar_agenda`, `agenda-contrato.tsx` |
| Gestão: chips Ativos / Vencendo em 30 dias / Vencidos / Não assinados / Todos com contagem (independente do chip, respeita os outros filtros), filtros aluno/plano/período, busca (nome, CPF, nº) — vigência **só** por `domain.contratos` | `servico.listar` |
| Editar sem sobrescrever valor em silêncio; renovar/duplicar; encerrar; **recalcular** com simulação | `servico.editar/renovar/encerrar/recalcular` |
| Exclusão segura (R13) com tela de confirmação do que será apagado e do que fica | `servico.plano_de_exclusao/excluir` (`domain.contratos.plano_exclusao_por_fk`) |
| PDF (reportlab): títulos, parágrafos, negrito/itálico/sublinhado/tachado, listas aninhadas, tabela com `colspan`, `hr`, quebra de página, assinatura embutida, logo e rodapé com a identidade do estúdio | `pdf.py` |
| Envio por e-mail (link + PDF anexo) e por WhatsApp (ponto de extensão `servico.definir_enviador_whatsapp`; sem enviador: 503 "WhatsApp ainda não configurado.") | `servico.enviar_*` |
| Assinatura por link (R10): tokens novos (7 dias) e **legados do Django** (`LEGACY_DJANGO_SECRET_KEY`, sal `contrato-assinatura`), rate limit, nada além do necessário, GET sem efeito colateral, assinatura única (UPDATE condicional), IP/data/CPF validado/PNG | `tokens.py`, `publico.py`, `routes.router_publico` |
| Assinatura local (recepção, usuário logado) → status `ASSINADO` | `servico.assinar_local` |
| Confirmação ao assinar (e-mail com a cópia + WhatsApp pelo ponto de extensão), sem nunca desfazer a assinatura se falhar | `servico.notificar_assinatura` |
| Termo de imagem: `termo_publico.gerar_link_assinatura_termo`, página pública (30 dias, novos + legados sal `termo-assinatura`), endpoints de link/envio | `termo_publico.py` |
| Componente da ficha: `components/contratos/aba-aluno-contratos.tsx` (`{ alunoId: number }`) | frontend |
| Menu: Contratos com `planejado: false` | `nav.ts` |

## Endpoints

Protegidos (`/api/contratos...`, regra `contratos.*`: GET=ver, DELETE=excluir, demais=editar; exceções abaixo):
`GET ""` (lista) · `GET /opcoes` · `POST /precificar` · `POST ""` (criar) · `GET/PUT /{id}` · `POST /{id}/renovar|encerrar` ·
`GET /{id}/exclusao` · `DELETE /{id}?confirmar=true` · `GET /{id}/agenda/opcoes` · `POST /{id}/agenda` · `GET /{id}/pdf` ·
`POST /{id}/link|enviar-email|enviar-whatsapp` (`contratos.enviar`) · `POST /{id}/assinatura-local` · `POST /recalcular`
(simular: `contratos.editar`; aplicar: exige `contratos.excluir`) · `POST /termo/{aluno_id}/link|enviar` (`alunos.editar`).
Todas auditadas (`contrato.criar|editar|renovar|encerrar|excluir|agenda|link|enviar_email|enviar_whatsapp|assinar_local|recalcular`,
`aluno.termo.link|enviar`); o público grava `contrato.assinar_link` e `aluno.termo.assinar_link` (sem usuário, com IP).
Públicos (`/api/assinar/...`, autenticação própria = token + rate limit): `GET|POST /contrato/{token}`, `GET /contrato/{token}/pdf`,
`GET|POST /termo/{token}`. Rate limit por IP: leitura 60/min, PDF 30/min, assinar 10/min.

## Decisões (as de negócio estão marcadas com DÚVIDA e vão para o Jefferson)

1. **Sem mudança de modelo.** Nenhuma coluna nova; `Reserva.contrato_id` e `AlunoDocumento.contrato_id` já existiam. Nada de migração.
2. **Número do contrato** = `codigo_legado` (contador `proximo_codigo("contrato")`, continua a série do Django); `{CONTRATO_NUMERO}` usa isso.
3. **Contrato novo é sempre MENSAL** (R1). Data final vazia = início + duração do plano − 1 dia (calendário real; sugestão, editável).
   As parcelas seguem R2 (dia ≤ 28), por isso o último vencimento pode ser anterior ao fim.
4. **Plano avulso** cria contrato e parcelas, mas **sem agenda automática** (igual ao antigo). `GET /agenda/opcoes` responde 409.
5. **Agenda**: começa em `max(início do contrato, hoje)` (não reserva o passado). O domínio só oferece o horário se houver vaga e não houver
   bloqueio em **todas** as datas; conflito só aparece quando a lotação muda entre listar e reservar.
6. **Editar**: mudar plano/datas nunca mexe nos valores. Valor só muda com `recalcular_valores=true` (R1) ou digitado (`valor_*`);
   os dois juntos dão 422. Contrato já assinado: mudar plano, datas ou valores exige `confirmar_alterar_assinado` (409 com
   `exige_confirmacao`). As **parcelas já geradas não são alteradas** (a resposta avisa; ajustar em Contas a receber).
7. **Encerrar** (o que o antigo não tinha): `data_fim = ontem`, cancela parcelas em aberto que vencem de hoje em diante, tira da agenda as
   aulas RESERVADA/PENDENTE de hoje em diante (opcionais). Não apaga nada pago, passado, evolução ou comissão.
8. **Excluir (R13)** — DIVERGE do antigo de propósito (que apagava contas pagas, evoluções e avaliações):
   - **recusa (409)** se houver parcela **paga** ou **comissão** (o financeiro também recusa conta paga) e oferece "Encerrar";
   - apaga as parcelas abertas/canceladas e as **reservas futuras** vinculadas por FK (`RESERVADA/PENDENTE`, data ≥ hoje, sem evolução/avaliação,
     sem cobrança paga) e as aulas que ficarem vazias (`domain.contratos.plano_exclusao_por_fk`); aulas avulsas nunca entram;
   - aulas passadas / concluídas / com evolução ou avaliação **ficam** (só perdem o vínculo `contrato_id`); evoluções e avaliações nunca são apagadas;
   - o PDF do contrato é apagado só se **não** estava assinado; contrato assinado mantém o PDF assinado no prontuário (desvinculado);
   - exige `?confirmar=true` (sem isso: 409 "Confirme a exclusao do contrato."); a tela mostra o plano (`GET /{id}/exclusao`) e pede o aceite.
   - **DÚVIDA (Jefferson):** concorda em manter as aulas passadas (sem vínculo) em vez de apagá-las junto, como o antigo fazia?
9. **Recalcular**: igual ao comando antigo (só `valor_aula/parcela/total` do contrato; **não** mexe nas parcelas). Simular por padrão.
   Aplicar exige `contratos.excluir` (alteração em massa; só Full por padrão). Opção `somente_vigentes`.
10. **Assinatura**: CPF validado (`domain.documentos`) e guardado formatado; não exige que seja o CPF do aluno (pode ser responsável).
    Link por e-mail/WhatsApp vale 7 dias; **gerar um link novo não invalida os anteriores** (sem tabela de revogação).
    Assinatura local grava `ASSINADO`; por link, `ASSINADO_DIGITALMENTE`. A imagem fica em `assinaturas/contrato/contrato_<id>.png`
    (mesmo caminho do ETL), servida só autenticada (`contratos.ver`).
11. **Segurança do link**: token inválido/adulterado/de outra finalidade/contrato inexistente → mesma resposta (404); expirado → 410;
    contrato assinado não devolve o texto; o PDF público é gerado na hora (não regrava o documento, ao contrário do antigo); páginas com
    `noindex` e `no-referrer`; HTML mostrado é re-sanitizado e os valores do aluno são escapados.
12. **Confirmações são cortesia**: falha no e-mail/WhatsApp depois da assinatura é só registrada em log; a assinatura vale.
13. **PDF**: quebra de página por `page-break-before/after: always` ou por um parágrafo só com `{QUEBRA_DE_PAGINA}` (o sanitizador do editor
    remove o `style` de quebra; use o marcador). Fonte Helvetica (acentos do português ok). Valores de moeda no formato `R$ 1.234,50`.
14. **Alunos inativos** não ganham contrato (409 "reative o cadastro"); plano/unidade/profissional inativos também são recusados.
    Contrato sobreposto (mesmo aluno e serviço) só **avisa**, não bloqueia.

## Pedidos ao coordenador

1. **Ligar a aba na ficha** (`components/alunos/abas.ts`): trocar `AbaContratos` por `AbaAlunoContratos` (de `@/components/contratos/aba-aluno-contratos`).
2. **Ligar o termo**: chamar uma vez na subida `termo_publico.registrar_no_modulo_alunos()` (substitui `alunos.servico.gerar_link_assinatura_termo`,
   que hoje levanta `NotImplementedError`). Para a aba "Uso da imagem" usar os endpoints `POST /contratos/termo/{aluno_id}/link` e `/enviar`.
3. **Edições mínimas que fiz fora do meu escopo** (4 linhas, necessárias para a página pública existir; revisar no merge):
   `frontend/proxy.ts` (`PUBLICAS` ganhou `assinar`), `frontend/app/bff/[...path]/route.ts` (`ROTAS_PUBLICAS` ganhou `assinar/(contrato|termo)/...`),
   `frontend/lib/auth.tsx` e `frontend/lib/api.ts` (o `/auth/me` e o redirecionamento ao login não rodam em `/assinar`).
   Sem elas o visitante sem login seria mandado para `/login`.
4. **Rotas públicas no core**: o prefixo `/api/assinar/` entra em `PUBLICAS_AUTENTICACAO_PROPRIA` por código em `contratos/routes.py`
   (`permissoes._PROPRIA_C`). Se preferirem, movam para `core/permissoes.py` e apaguem as 3 linhas do módulo.
5. **WhatsApp (agente COMUNICAÇÃO)**: registrar `servico.definir_enviador_whatsapp(fn)` com `fn(db, mensagem: MensagemWhatsapp) -> None`
   (campos: `tipo` = `contrato_assinatura|contrato_assinado|termo_assinatura|termo_assinado`, `aluno_id`, `telefone` canônico, `texto`,
   `contrato_id`, `link`, `pdf_url` público por token, `pdf_nome`). Levantar exceção se não enviar; o módulo traduz para 502 sem vazar detalhe.
6. **Produção**: definir `LEGACY_DJANGO_SECRET_KEY` (a `SECRET_KEY` do Django antigo) por pelo menos 30 dias depois do cutover; depois remover.
   `FRONTEND_URL` (https) é usado nos links. Atrás do nginx, o IP gravado na assinatura vem de `X-Forwarded-For` (o BFF repassa).
7. **Paridade** (`docs/MIGRACAO.md`): marcar Contratos como feito (criar, agenda, gestão, PDF, envio e-mail/WhatsApp-extensão, assinatura, exclusão, recalcular)
   e a aba "Contratos" da ficha quando ligada. O WhatsApp só fecha quando o agente COMUNICAÇÃO registrar o enviador.
8. `pyproject.toml`: nenhuma dependência nova.

## Dúvidas para o Jefferson

1. Excluir contrato: manter as **aulas passadas** (sem vínculo) e recusar quando houver parcela paga/comissão — é isso mesmo? (item 8)
2. **Encerrar** deve também **inativar o aluno** ou ficar só no contrato? (hoje só o contrato)
3. O CPF de quem assina precisa ser o do aluno (ou do pagador)? Hoje basta um CPF válido, para permitir responsável legal.
4. Link de assinatura novo deve **invalidar** o anterior? (hoje não)
5. Secretária pode **aplicar o recálculo em massa**? (hoje só Full, por exigir `contratos.excluir`; simular qualquer um com `contratos.editar`)
6. Contrato de plano **semanal/avulso**: manter "sem agenda automática" para avulso, como no antigo?

## Testes (`backend/tests/contratos`, 103 com `test_cobertura_rotas`)

`test_criar` (R1/R2 contra o domínio, PDF guardado, atomicidade em 4 pontos de falha, validações, permissões) ·
`test_gestao` (chips × `domain.contratos`, filtros, busca, editar sem sobrescrever, renovar, encerrar, recalcular) ·
`test_agenda_e_exclusao` (FK, conflito sem desfazer, escolha inválida, exclusão: confirmação, sessões vazias, aula avulsa/colega/evolução preservados,
conta paga e comissão bloqueiam, falha desfaz) · `test_pdf` · `test_assinatura` (tokens novo/legado/expirado/adulterado/sal errado, GET sem efeito colateral,
assinatura dupla e simultânea, rate limit, local, e-mail com anexo, WhatsApp 503/extensão/falha, confirmações) · `test_termo` ·
`test_permissoes_auditoria` (Full/Secretária/Professor em todas as rotas, rotas públicas com rate limit, auditoria sem segredo).
