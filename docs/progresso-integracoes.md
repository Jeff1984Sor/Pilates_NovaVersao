# Progresso - agente Integrações (branch feat/integracoes)

Escopo: tokens de API dos integradores, API de integração externa (mesmos caminhos/formatos do antigo), TotalPass (tela, teste de
conexão, webhook, sincronização) e telas. Perfil **Full** configura; Secretária e Professor não veem nada daqui.

## Feito
1. **Tokens de API** (`modules/integracoes/tokens.py`, tela `Configurações > Integrações > Tokens`): valor `pilates_` + 32 bytes URL-safe,
   aparece **uma única vez** (criar/regenerar), banco guarda só SHA-256 + últimos 4 caracteres. Ativar/desativar, renomear, regenerar
   (o valor antigo morre na hora), excluir, "último uso" (regravado no máximo a cada 30 s por token). Tokens migrados do ETL
   (`precisa_regenerar`, sem hash) vêm destacados em amarelo com a orientação de regenerar e repassar; não ativam sem regenerar.
2. **API de integração externa** (`api_externa.py`), prefixo `/api/integracao/*`. Autenticação `X-API-Key` ou `Authorization: Bearer`
   (a chave vence, como no antigo), só token ATIVO; rate limit **por token** (120/min) e **de falhas por IP** (20 em 5 min).
3. **TotalPass** (`totalpass.py`, `servico.py`, `routes.py`, `tarefas.py`): tela por unidade (chaves cifradas somente escrita, place id, token do
   webhook, só o dia, criar aluno, serviço padrão, sync agendado), **Testar conexão**, **Gerar token do webhook**, **Sincronizar agora**,
   lista dos últimos eventos (resultado, motivo, CPF mascarado), webhook `POST /api/webhooks/totalpass` e sync diário (`registrar_tarefa`, 15 min,
   **desligado por padrão**).
4. **Testes** (`backend/tests/integracoes`, 155 testes): golden do antigo (52 chamadas), tokens, webhook (cada ramo), tela/teste de conexão/sync/tarefa,
   eventos, permissões, auditoria e vazamento de segredos. Cliente HTTP do TotalPass **sempre falso** (`httpx.MockTransport`; um autouse troca a fábrica por
   uma que explode se algo tentar a internet).

## Rotas

### Públicas com autenticação própria (`router_publico`)
Todas exigem `X-API-Key: <token>` ou `Authorization: Bearer <token>`. Erros: `401 {"detail": "API key ausente"}` / `{"detail": "API key invalida"}`
(inclui token desativado ou migrado sem valor), `429` com `Retry-After`. Respostas só levam os campos abaixo.

| Rota | Resposta |
|---|---|
| `GET /api/integracao/alunos?nome=&status=&limit=50` (1..200) | lista `{id, cdAluno, dsNome, dsCPF, dsEmail, dsTelefone, status}`; `nome` = contém, sem diferenciar maiúsculas; `status` ATIVO/INATIVO; ordem por nome |
| `GET /api/integracao/alunos/por-codigo/{cdAluno}` | um aluno (mesmo formato); 404 `Aluno nao encontrado`. `cdAluno` = `aluno.codigo_legado` |
| `GET /api/integracao/alunos/por-telefone?telefone=` | um aluno; compara pela chave `(DDD, 8 dígitos finais)` de `domain.telefone` (tolera máscara, DDI 55 e nono dígito); 400 `Telefone invalido` se não houver dígitos; 404 se não achar. `dsTelefone` = o número que casou |
| `GET /api/integracao/faturas?cdAluno=&status=` | faturas das parcelas de contrato do aluno `{id, cdAluno, contrato_id, descricao ("Mensalidade Outubro/2026"), competencia, valor (float), vencimento, dt_pagamento, status (minúsculo)}`; `status`: aberto/pago/atrasado/cancelado; ordem por vencimento. **Pagamentos em aberto** = `status=aberto` (+ `atrasado`) |
| `GET /api/integracao/contratos?cdAluno=` | `{id, cdContrato, cdAluno, plano, profissional, unidade, dt_inicio, dt_fim, status (assinatura), valor_parcela, valor_total}`; mais recente primeiro |
| `GET /api/integracao/aulas?cdAluno=&apenas_proximas=false&limit=50` | reservas `{reserva_id, cdAluno, data, hora_inicio, hora_fim, tipo_servico, profissional, unidade, status}`; mais recentes primeiro; `apenas_proximas` = data de negócio >= hoje (**próximas aulas**) |
| `POST /api/integracao/whatsapp-mensagens` `{cdAluno, direcao="recebida"/"enviada", texto, telefone?, data_iso?, contrato_id?}` | grava no histórico do aluno; devolve `{id, cdAluno, direcao, enviado_em}`; 404 aluno, 400 direção. Auditado como "Robô" (sem o texto) |
| `GET /api/integracao/contratos/ativo?cdAluno=` | **NOVA**: contrato vigente hoje (formato de contrato); 404 `Contrato ativo nao encontrado` |
| `GET /api/integracao/aulas/amanha` | **NOVA**: reservas RESERVADA de amanhã `{...aula, dsNome, dsTelefone}` (lembretes do chatbot) |
| `POST /api/webhooks/totalpass` | webhook do TotalPass, ver abaixo |

### Webhook TotalPass
- Cabeçalho `X-Totalpass-Token` **obrigatório**, comparado em tempo constante (`hmac.compare_digest`, sem curto-circuito entre unidades).
  Nenhum token configurado no sistema: **403**; cabeçalho ausente: **401**; errado: **403** (falhas limitadas a 20/5 min por IP; 120 chamadas/min por IP; corpo até 256 KB).
- Escolha da unidade: o `place` do payload casa com o `place_id` das configurações cujo token confere; se só uma confere, é ela.
- Respostas: `200 {"ok":true,"reserva_id","resultado"}`, `200 {"ok":true,"duplicado":true,...}` (já processado), `202 {"ok":true,"descartado":"Fora do dia atual."}`,
  `202 {"warning":"Integracao desativada."}`, `400 {"detail","error"}` (erro de regra, registrado no evento).
- Processamento: grava `totalpass_evento` (payload, origem, resultado) -> serviço por título (exato, depois "contém", depois o serviço padrão) -> aluno por
  CPF (só dígitos; cria se permitido e o CPF for válido, com telefone normalizado) -> `agenda.obter_ou_criar_sessao` **sem profissional** (herda a capacidade da
  unidade) -> `agenda.criar_reserva` (vaga atômica; capacidade excedida vira erro "Capacidade excedida: ... N de M vagas ocupadas" no evento) ->
  status `canceled/cancelled/inactive` cancela a reserva (libera a vaga; **não** cria aluno nem aula) -> `somente_dia` descarta outro dia.
  Tudo da unidade de trabalho roda em SAVEPOINT: erro não deixa aluno/aula pela metade.
- **Idempotência**: chave `(event.id, slot.id, status, documento)`; já processado = devolve `duplicado`. Evento com erro/descartado pode ser reenviado e reaproveita a linha.
  (O `event.id` do TotalPass identifica a aula e se repete entre alunos; por isso a chave inclui slot e documento.)

### Protegidas (só `integracoes.ver/editar` = Full)
`GET/POST /api/integracoes/tokens`, `PATCH/DELETE /api/integracoes/tokens/{id}`, `POST .../{id}/regenerar`;
`GET /api/integracoes/totalpass`, `PUT /api/integracoes/totalpass/{unidade_id}`, `POST .../{unidade_id}/token-webhook|testar|sincronizar`,
`GET /api/integracoes/totalpass/eventos`. Nenhum GET tem efeito colateral. Auditoria: criar/regenerar/ativar/desativar/excluir token, configurar TotalPass (diz
**qual** segredo mudou, nunca o valor), gerar token do webhook, testar conexão, sincronizar, e (como "Robô") aluno/reserva criados ou cancelados pelo TotalPass.

## Divergências do sistema antigo (POR SEGURANÇA ou coerência com o modelo novo)
1. **Webhook sem token recusa** (antigo: aceitava qualquer POST se nenhum token estivesse configurado). Token comparado em tempo constante.
2. **Tokens de API não são guardados em claro**: hash SHA-256. Os do antigo vêm sem valor (`precisa_regenerar`): **cada integrador precisa receber um novo valor**.
   Desativado/inexistente/sem valor = mesmo 401 "API key invalida".
3. **Busca por telefone**: o antigo procurava os 8 dígitos num campo guardado COM máscara e nunca achava (`(15) 99776-2467` -> 404; só achava telefone gravado só com dígitos).
   O novo compara o número normalizado e acha. Registrado no golden (`DIVERGENCIAS`).
4. **ATRASADO é derivado**: `status=aberto` não traz vencidas; `status=atrasado` traz abertas vencidas (o antigo dependia do status gravado).
5. Mensagem WhatsApp: `contrato_id` só vale se for contrato do próprio aluno; `texto` 1..4000 caracteres; data sem fuso = horário de São Paulo; telefone cortado em 20.
6. 422 de validação sai no formato do app novo (`{"detail": "campo: mensagem", "erros": [...]}`), não na lista do FastAPI (o status é o mesmo).
7. `dsCPF`: devolvido com máscara (`xxx.xxx.xxx-xx`), `null` para aluno sem CPF (o antigo devolvia o texto `SEM_CPF_...`); `dsEmail` vazio = `""`.
8. TotalPass: CPF inválido não cria aluno (antigo criava com lixo); cancelamento não cria aluno/aula; descartado responde 202 (antigo 400); serviço padrão novo;
   aula nasce com capacidade herdada da unidade (antigo copiava o número); cancelar não dá direito a reposição (igual ao antigo, que só trocava o status).
9. Faturas só de parcelas de **contrato** (como no antigo); cobranças de aula avulsa (sem contrato) não aparecem.
10. Sync (manual ou agendado) **ignora** `somente_dia` (o dia é pedido explicitamente); o webhook respeita.

## Alterações de modelo (ADITIVAS) - o coordenador precisa regenerar a migração `0001`
`backend/app/modules/integracoes/models.py` (nenhuma coluna removida/alterada; a `0001` não foi tocada):
- `totalpass_config`: `servico_padrao_id` (FK `tipo_servico`, SET NULL), `sync_ativo` (bool, padrão falso), `sync_ultimo_em`, `sync_ultimo_resumo` (varchar 300).
- `totalpass_evento`: `resultado` (varchar 20), `reserva_id` (FK `reserva`, SET NULL), `origem` (varchar 10).
`tests/dados/test_migracao.py` compara a `0001` com `create_all` e falha até a migração ser regenerada (mesma situação registrada pelo financeiro). Os testes de integrações usam `create_all`.

## Pedidos ao coordenador
- **Migração**: regenerar a `0001` (ou nova revisão) com as colunas acima.
- **nginx / base da API externa**: os integradores hoje chamam `/api/fast/integracao/*` (antigo). O novo serviço responde em `/api/integracao/*`. Duas saídas: avisar
  os integradores da nova base, ou `rewrite ^/api/fast/(integracao/.*)$ /api/$1 break;` no nginx. Também liberar `/api/webhooks/` (já está) e **`client_max_body_size`**
  coerente (o webhook corta em 256 KB).
- **`nav.ts`**: o item "Integrações" (Comunicação) aponta para `/comunicacao/integracoes` (`planejado`). Minhas páginas estão em `/configuracoes/integracoes/tokens` e
  `/configuracoes/integracoes/totalpass`; o hub (`/configuracoes/integracoes/page.tsx`) é do agente Comunicação e deve linkar para as duas. Sugestão: no grupo
  "Configurações" um item "Integrações" -> `/configuracoes/integracoes` (`integracoes.ver`) e remover/redirecionar o de Comunicação. Sem item de menu, a página abre
  pela URL e a API devolve 403 para Secretária/Professor (a tela mostraria erro); com `itemDaRota` mapeando o caminho, o shell mostra "Sem acesso".
- **Agenda (`agenda/servico.py`)**: uso `_trocar_status` (privada) para cancelar reserva do TotalPass sem reposição. Pedir um `cancelar_reserva(db, reserva_id)` público.
- **Alunos**: `criar_aluno` exige `Contexto`; o webhook cria o `Aluno` direto (`proximo_codigo` + telefone normalizado). Um `criar_aluno_sistema(db, ...)` sem ctx evitaria duplicar regra.
- **Worker**: `tarefas.py` registra `totalpass-sincronizar` (15 min); nada roda se nenhuma unidade ligar a sincronização.
- Variável opcional `TOTALPASS_BOOKING_BASE_URL` (padrão `https://booking-api.totalpass.com`); não é segredo.

## Dúvidas para o Jefferson
1. A API externa devolve CPF e e-mail completos do aluno (compatível com o antigo). Quer **mascarar o CPF** (ou remover) para os integradores?
2. Cada integrador precisará de um **token novo** (os antigos não migram o valor). Quer manter o valor antigo? Só seria possível trazendo o valor do banco antigo no ETL (contra a decisão de não migrar segredos).
3. A URL da API externa muda de `/api/fast/integracao` para `/api/integracao`. Prefere avisar os integradores ou que o nginx reescreva?
4. Evento TotalPass de outro dia (`somente_dia`) responde 202 "descartado"; o antigo respondia 400. OK?
5. Quando o aluno cancela no TotalPass, a reserva fica **CANCELADA** (sem reposição). Correto?

## Como rodar
```
cd backend
uv run python -m pytest -q tests/integracoes tests/test_cobertura_rotas.py     # ~90 s (hash de senha dos usuários de teste)
cd ../frontend && npm install && npm run lint && npm run build
```
Regenerar o golden do antigo (somente leitura no antigo; banco SQLite temporário fora do repo):
```
cd C:\Users\JeffersonFernandes\Projetos\Pilates\PilatesFinal\backend
$env:PYTHONDONTWRITEBYTECODE="1"
<venv antigo>\Scripts\python.exe <repo novo>\backend\tests\integracoes\golden\gerar_golden_antigo.py --saida <repo novo>\backend\tests\integracoes\golden\api_antiga.json
```
