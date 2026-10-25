# Progresso — agente APP-ALUNO-IA (`feat/app-aluno-ia`)

Escopo: app do aluno (PWA em `/app/`, R15) e IA de cadastro (assistente "Preencher com IA" da ficha do aluno).
Dono de: `backend/app/modules/app_aluno/`, `backend/app/modules/ia_cadastro/`, `backend/tests/app_aluno/`, `backend/tests/ia_cadastro/`,
`frontend/app/(aluno)/`, `frontend/components/app-aluno/`, `frontend/public/app/`, `frontend/components/alunos/assistente-ia.tsx`,
`frontend/lib/tipos-app-aluno.ts`.

## Como rodar

```bash
cd backend && uv sync
uv run python -m pytest -q tests/app_aluno tests/ia_cadastro tests/agenda/test_prazo_6h.py tests/test_cobertura_rotas.py
uv run python -m ruff check app/modules/app_aluno app/modules/ia_cadastro tests/app_aluno tests/ia_cadastro
cd ../frontend && npm install && npm run lint && npm run build
```
Telas do aluno: `/app/entrar` (CPF -> código), `/app` (próximas aulas), `/app/reposicoes`. Variáveis opcionais do BFF do aluno:
`INTERNAL_API_URL` (a mesma do BFF da equipe), `ALUNO_ACCESS_HORAS` (12) e `ALUNO_REFRESH_DIAS` (7), só para o tempo do cookie;
quem manda na validade real é a API.

Verificação manual feita (backend e `next start` em portas livres, dados sintéticos, WhatsApp falso): manifest com nome/cor do banco, ícones
PNG 192/512/maskable, `sw.js`, `offline.html`, e o fluxo inteiro pelo BFF (pedir código, entrar, `me`, aulas, confirmar, desmarcar,
reposições, opções, sair; sem sessão = 401; chamada sem `X-Requested-With` = 403; caminho fora da lista = 404).

## Feito

| Item | Onde |
|---|---|
| Login por CPF + código de 6 dígitos (10 min) via `core.notificador`; CPF com ou sem máscara | `app_aluno/servico.py`, `routes.py` |
| Limites: 3 pedidos/15 min por CPF, 10 por IP; 15 verificações por CPF e 20 por IP; 5 erros queimam o código | `routes.py` (constantes no topo), `servico.MAX_TENTATIVAS` |
| Resposta idêntica exista ou não o CPF (inativo, sem telefone, telefone inválido, falha de envio) | teste `test_resposta_igual_exista_ou_nao_o_cpf` |
| Código de uso único (UPDATE condicional), anterior invalidado, hash em tempo constante (`hmac.compare_digest`) | `servico.verificar_codigo` |
| JWT do aluno: access 12 h, refresh 7 dias, `typ` `aluno_access`/`aluno_refresh` e `aud` próprios; não abre rota da equipe e vice-versa | `servico.emitir_tokens/decodificar` |
| `me`, `aulas`, `confirmar` (R15, `agenda.confirmar_reserva`), `desmarcar` (R4, `agenda.desmarcar_reserva_do_aluno`), isolamento (id alheio = 404) | `routes.py` |
| Reposição por **pedido** (decisão do Jefferson, 25/10/2026): o aluno só pede (preferência em texto livre, até 300 caracteres); a gerência (Full, permissão `reposicoes`) aprova escolhendo aula com vaga real ou recusa com motivo; WhatsApp ao aluno na decisão | `app_aluno/reposicoes.py`, `models.py` (`reposicao_pedido`), `routes.py` |
| **Regra das 6 horas LIGADA** ao desmarcar (aluno e equipe); exceção só do Full, com motivo (na reserva e na auditoria) | `agenda/servico.py`, `agenda/routes.py`, gaveta do painel |
| Tela da gerência `/reposicoes` (chips Pendentes/Aprovados/Recusados, preferência, aulas sugeridas, aprovar/recusar) | `app/(app)/reposicoes/page.tsx`, `components/reposicoes/` |
| Auditoria das ações do aluno (`aluno_app.login/confirmar/desmarcar/reposicao`) | `routes._auditar` |
| IA de cadastro: documento e comprovante, rascunho com campos incertos marcados, CPF validado, nada gravado | `ia_cadastro/` |
| Frontend PWA: login em 2 passos, aulas (confirmar um toque, desmarcar com aviso da data limite), reposições (escolher horário), sair, instalar, offline | `components/app-aluno/`, `app/(aluno)/` |
| BFF do aluno com cookies httpOnly próprios (`path=/app`), lista fechada de rotas, CSRF (Origin + `X-Requested-With`), renovação automática | `app/(aluno)/app/api/[...path]/route.ts` |
| Manifest dinâmico com a marca do banco, ícones PNG gerados (cor + iniciais ou logo), service worker, página offline | `app/(aluno)/app/manifest.json`, `app/icone/[tamanho]`, `public/app/` |
| Componente `AssistenteIA` (modal) pronto para o cadastro de aluno | `components/alunos/assistente-ia.tsx` |

### Rotas (todas sob `/api`)

App do aluno (autenticação própria, `router_publico`): `POST /aluno-app/auth/{codigo|verificar|refresh}` · `GET /aluno-app/{me|aulas|reposicoes}` ·
`POST /aluno-app/aulas/{id}/{confirmar|desmarcar}` · `POST /aluno-app/reposicoes/{reserva_id}/pedir` (corpo `{preferencia}`).
Equipe (login + permissão `reposicoes`: GET = ver, POST = editar; só o Full tem): `GET /reposicoes?status=&q=` (devolve `contagens` + `itens`) · `GET /reposicoes/{pedido}/opcoes?ignorar_prazo=` · `POST /reposicoes/{pedido}/aprovar` (`{aula_id, ignorar_prazo, motivo}`) · `POST /reposicoes/{pedido}/recusar` (`{motivo}`).
Agenda: `POST /aulas/reservas/{id}/desmarcar` aceita corpo opcional `{excecao_prazo, motivo}`.
IA (login + `ia.usar`): `GET /ia/cadastro/status` · `POST /ia/cadastro/documento` · `POST /ia/cadastro/comprovante` (multipart, campo `arquivo`).

## Decisões

1. **Sem enumeração e sem diferença de tempo**: o envio do WhatsApp roda em `BackgroundTasks` (depois da resposta), então o caminho "CPF existe" não demora mais que o "não existe". CPF malformado também recebe 200 e a mesma mensagem.
2. **Limite por CPF vale para CPF inexistente também** (senão o 429 revelaria quem é aluno). Efeito colateral aceito: quem digita o CPF de outra pessoa 4 vezes em 15 min impede o pedido dela por alguns minutos. A chave do limite é um hash do CPF (o CPF não vai para a tabela de rate limit).
3. **Código**: o hash inclui o id do aluno (`hash_token("app-aluno:<id>:<código>")`); 5 erros marcam o código como usado (é preciso pedir outro). Só o último código aberto vale.
4. **Refresh stateless** (não há tabela de sessões do aluno, para não mexer em modelo): renovar devolve um par novo, mas o refresh antigo continua válido até vencer. Compensação: access e refresh conferem se o aluno ainda está **ATIVO** a cada uso (inativar o aluno derruba o acesso na hora). "Sair" apaga os cookies; não há revogação central do token. Se o Jefferson quiser revogação (ex.: "sair de todos os aparelhos"), é uma tabela aditiva `app_sessao`.
5. **Aluno só mexe em aula aberta**: confirmar/desmarcar só para RESERVADA/PENDENTE de hoje em diante (concluída, falta e aula passada = 409).
6. **Regra das 6 horas LIGADA** (resposta do Jefferson): `domain.reposicao.aviso_minimo_cumprido(ativo=True)`; vale `antecedência >= 6 h` (o limite exato passa; 1 segundo depois = 409 com o horário limite, ex.: "o prazo desta aula terminou em 26/10/2026 às 03:00"). Vale para o aluno (sem exceção; a lista de aulas traz `pode_desmarcar=false` e `desmarcar_ate`) e para a equipe (`agenda.servico.desmarcar_reserva`). **Exceção**: só o perfil Full (administrador), enviando `excecao_prazo=true` + `motivo` (mín. 3 caracteres, 422 sem ele); a Secretária recebe 403. O motivo vai para `reserva.motivo_excecao_prazo` e para a auditoria (`aula.desmarcar_excecao`). Aula já desmarcada continua 409; "falta avisada" continua sem gerar reposição. O detalhe da reserva traz `aviso_prazo_desmarcar` e `permite.desmarcar_excecao`; a gaveta mostra o aviso e, para o Full, "Desmarcar mesmo assim" com campo de motivo.
7. **Reposição é PEDIDO, não remarcação imediata** (resposta do Jefferson): removidas as opções com vaga e a remarcação do app do aluno. O aluno vê as aulas desmarcadas com prazo, o botão "Pedir reposição" e a situação (Aguardando a gerência / Aprovada para data e hora / Recusada: motivo). Um pedido ativo por aula (índice único parcial em `reposicao_pedido` para PENDENTE/APROVADO); pedir de novo enquanto PENDENTE só atualiza a preferência (idempotente); pedido RECUSADO bloqueia novo pedido da mesma desmarcação; se a aula aprovada for desmarcada de novo, o pedido antigo vira CANCELADO e vale um novo. Preferência: até 300 caracteres (422 acima), sem caracteres de controle nem `<` `>`.
   - **Aprovar** (`reposicoes/aprovar`): a gerência escolhe uma aula entre as sugeridas (mesmo serviço/unidade, vaga real, fora de bloqueio, onde o aluno não está, hoje em diante, até `reposicao_ate`); a remarcação usa `agenda.servico.remarcar_reserva` (capacidade transacional, consome o prazo). Aula depois do prazo ou reposição vencida: 409, a menos que `ignorar_prazo=true` **com motivo** (422 sem; gravado em `ignorou_prazo`/`motivo_ignorar_prazo` e na auditoria). Aula lotada/inexistente: 409 e o pedido continua PENDENTE. Pedido já decidido: 409.
   - **Recusar**: motivo obrigatório (o aluno lê). Aprovar e recusar auditam (`reposicao.aprovar`/`reposicao.recusar`) e avisam o aluno por WhatsApp via `core.notificador` (falha no aviso nunca desfaz a decisão).
   - Como a remarcação move a própria reserva, `reserva_nova_id == reserva_origem_id`; `aprovado_data/aprovado_hora` e `data_origem/hora_origem` guardam as datas (a aula antiga pode ser apagada ao ficar vazia, então não há FK para ela).
8. **Mensagem do desmarcar** foi reescrita com acento no serviço ("Você pode repor até 25/11/2026 (30 dias).") porque o texto do domínio (`mensagem_reposicao`) é sem acento. Domínio não foi tocado.
9. **IA de cadastro**: cliente HTTP próprio (`ia_cadastro/cliente.py`), em vez de `core.ia.gerar_json`, porque o core não manda PDF para a OpenAI. OpenAI recebe imagem como `image_url` e PDF como `file` (data URL base64); Gemini recebe `inline_data`. Usa `core.ia.provedor_ativo` (chave cifrada, somente escrita) e as mensagens de erro do core. Trocável por `definir_cliente(...)` (testes usam cliente falso e `httpx.MockTransport`; nenhum teste fala com a internet).
10. **Arquivo só na memória**: PNG/JPG/WEBP/PDF, máx. 8 MB, tipo conferido pela extensão **e** pelos primeiros bytes; nada é salvo em disco pela IA (o temporário do upload do Starlette é fechado/apagado na rota). Auditoria registra tipo, tamanho e quantidade de campos incertos, nunca o conteúdo nem os valores.
11. **A IA sugere, o sistema decide**: CPF pelo dígito verificador (`domain.documentos`); data de nascimento entre 1900 e hoje; CEP com 8 dígitos; nome em MAIÚSCULAS vira "Nome Próprio"; chaves extras, caracteres de controle e textos longos da resposta são descartados (prompt injection); o prompt manda tratar o texto do arquivo como dado. Campo inválido, ausente ou duvidoso vai com `incerto=true` + aviso. **Nunca grava aluno/endereço**: o usuário confere e a tela chama `onAplicar(dados)`.
12. **Erros da IA**: sem chave/desligada = 409 apontando para Configurações > Inteligência Artificial; recusa do provedor, cota, timeout ou resposta fora do formato = 502 com texto claro. Rate limit de 30 leituras por hora por usuário.
13. **Fora do shell da equipe**: grupo `(aluno)` com URL `/app/...`. O cookie do aluno tem `path=/app` e nome próprio; o BFF do aluno só repassa para `aluno-app/*` (lista fechada).

## Alterações fora da minha pasta (mínimas, 1 linha cada; o coordenador confere no merge)

Sem elas o PWA em `/app` era redirecionado para `/login` pela sessão da equipe. Em todas só entrou `app` na lista de rotas "sem sessão da equipe":
- `frontend/proxy.ts`: `PUBLICAS` ganhou `app`.
- `frontend/lib/api.ts`: `irParaLogin` não redireciona em `/app`.
- `frontend/lib/auth.tsx`: não consulta `/auth/me` em `/app`.
- `frontend/lib/brand.tsx`: título da aba em `/app` sem o sufixo "· Gestão".

- `backend/app/modules/agenda/{models,servico,routes,schemas}.py` e `tests/agenda`: **só** para a regra das 6 horas (coluna aditiva `reserva.motivo_excecao_prazo`, parâmetros novos opcionais `excecao_prazo`/`motivo` em `desmarcar_reserva`, `DesmarcarIn`, `permite.desmarcar_excecao`, `aviso_prazo_desmarcar`). Retrocompatível; `test_api_painel_grade` ganhou a chave nova esperada. `tests/agenda/test_prazo_6h.py` é novo.
- `frontend/components/agenda/gaveta-aluno.tsx`, `frontend/lib/tipos-agenda.ts`: aviso e "desmarcar mesmo assim" (Full).
- `frontend/components/mayacorp/nav.ts`: entrada "Reposições" (`/reposicoes`, `reposicoes.ver`) no grupo Agenda.

## Pedidos ao coordenador (migração)

0. **Gerar a migração** (`alembic revision --autogenerate`): tabela nova `reposicao_pedido` (modelo em `app_aluno/models.py`, com índice único parcial `uq_reposicao_pedido_ativo`) e coluna nova `reserva.motivo_excecao_prazo` (Text, nula). Acrescentar `app_aluno` ao `registrar_modelos()` em `app/modules/__init__.py` (importar `app.modules.app_aluno.models`) para o Alembic/ETL enxergarem a tabela. Os testes usam `Base.metadata.create_all`.

1. **Ligar o assistente no cadastro do aluno** (botão "Preencher com IA" hoje desabilitado em `alunos/novo/page.tsx` e `alunos/page.tsx`): `<AssistenteIA open onOpenChange onAplicar />` de `components/alunos/assistente-ia.tsx`. `onAplicar(dados: DadosAssistenteIA)` recebe só os campos preenchidos: `nome`, `cpf` (11 dígitos), `rg`, `data_nascimento` (AAAA-MM-DD), `logradouro`, `numero`, `bairro`, `cidade`, `cep` (8 dígitos). O botão só deve aparecer com `pode("ia.usar")`. O `FormAluno` precisa expor uma forma de receber esses valores (hoje o estado é interno).
2. **Notificador real**: o login do aluno chama `core.notificador.get_notificador().enviar_texto(telefone, texto)` (telefone normalizado `55DDDNÚMERO`). Falta o módulo de comunicação registrar o WasenderAPI com `definir_notificador`; sem isso o código **não chega** (padrão atual só registra no log, sem o texto). Em produção o envio deve ir para o histórico de mensagens do aluno (tipo "codigo_app") sem gravar o código.
3. **Rate limit em produção**: com mais de um processo usar `RATE_LIMIT_BACKEND=banco`; com a memória (padrão) o limite é por processo.
4. **Nginx**: servir `/app/` no Next (não na API) e manter `/api/` na API; o nginx deve SOBRESCREVER `X-Forwarded-For` (os limites por IP dependem disso). `/app/sw.js` deve ser servido sem cache longo.
5. **Cutover R15**: o antigo serve o app em `/app/` + `/app/manifest.json`, `/app/sw.js`, `/app/icon.svg`. Os mesmos caminhos existem aqui (`icon.svg` estático; os ícones PNG ficam em `/app/icone/...`). Alunos que já instalaram o app antigo precisarão entrar de novo (sessão nova).
6. `core.ia.gerar_json` poderia aprender a mandar PDF para a OpenAI (formato `file`) e usar o mesmo cliente; hoje só a IA de cadastro faz isso.

## Respostas do Jefferson (25/10/2026) já aplicadas

Reposição é pedido decidido pela gerência (Full) · regra das 6 horas ligada (exceção só do Full, com motivo) · texto do WhatsApp do código aprovado como está.

## Dúvidas ainda abertas

1. Código de acesso: 10 min e 5 tentativas estão bons? Manter o aluno logado por 7 dias sem pedir código novo?
2. Quer **revogar sessões** do aluno (sair de todos os aparelhos / aparelho perdido)? Exige tabela nova.
3. Pedido de reposição **recusado** bloqueia novo pedido da mesma aula desmarcada (o aluno fala com a recepção). Prefere permitir pedir de novo?
4. A Secretária hoje não vê a tela de Reposições (só o Full tem a permissão `reposicoes`); está certo mesmo ela não podendo nem ver a lista?

## Pendências / limites conhecidos

- A UI foi validada por `npm run lint`, `npm run build` e o fluxo manual pelo BFF (curl); **não** foi aberta num navegador/celular real nem passou por Lighthouse.
- Push notification (lembrete de aula) não faz parte do escopo.
- A gerência só enxerga como sugestão aulas **já geradas** (a geração é por `POST /agenda/sessoes/gerar`); aprovar não cria aula nova.
- Leitura de PDF pela OpenAI depende de o modelo escolhido aceitar arquivos (modelos com visão atuais aceitam); caso contrário a tela mostra o erro do provedor e o usuário envia uma foto.
