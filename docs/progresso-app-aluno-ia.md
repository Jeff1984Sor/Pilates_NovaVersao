# Progresso — agente APP-ALUNO-IA (`feat/app-aluno-ia`)

Escopo: app do aluno (PWA em `/app/`, R15) e IA de cadastro (assistente "Preencher com IA" da ficha do aluno).
Dono de: `backend/app/modules/app_aluno/`, `backend/app/modules/ia_cadastro/`, `backend/tests/app_aluno/`, `backend/tests/ia_cadastro/`,
`frontend/app/(aluno)/`, `frontend/components/app-aluno/`, `frontend/public/app/`, `frontend/components/alunos/assistente-ia.tsx`,
`frontend/lib/tipos-app-aluno.ts`.

## Como rodar

```bash
cd backend && uv sync
uv run python -m pytest -q tests/app_aluno tests/ia_cadastro tests/test_cobertura_rotas.py     # 81 testes, ~30 s
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
| Reposições: lista, opções com vaga real (aulas existentes) e remarcação imediata via `agenda.remarcar_reserva` | `servico.listar_reposicoes/opcoes_reposicao/remarcar_reposicao` |
| Auditoria das ações do aluno (`aluno_app.login/confirmar/desmarcar/reposicao`) | `routes._auditar` |
| IA de cadastro: documento e comprovante, rascunho com campos incertos marcados, CPF validado, nada gravado | `ia_cadastro/` |
| Frontend PWA: login em 2 passos, aulas (confirmar um toque, desmarcar com aviso da data limite), reposições (escolher horário), sair, instalar, offline | `components/app-aluno/`, `app/(aluno)/` |
| BFF do aluno com cookies httpOnly próprios (`path=/app`), lista fechada de rotas, CSRF (Origin + `X-Requested-With`), renovação automática | `app/(aluno)/app/api/[...path]/route.ts` |
| Manifest dinâmico com a marca do banco, ícones PNG gerados (cor + iniciais ou logo), service worker, página offline | `app/(aluno)/app/manifest.json`, `app/icone/[tamanho]`, `public/app/` |
| Componente `AssistenteIA` (modal) pronto para o cadastro de aluno | `components/alunos/assistente-ia.tsx` |

### Rotas (todas sob `/api`)

App do aluno (autenticação própria, `router_publico`): `POST /aluno-app/auth/{codigo|verificar|refresh}` · `GET /aluno-app/{me|aulas|reposicoes}` ·
`POST /aluno-app/aulas/{id}/{confirmar|desmarcar}` · `GET /aluno-app/reposicoes/{id}/opcoes` · `POST /aluno-app/reposicoes/{id}/remarcar`.
IA (login + `ia.usar`): `GET /ia/cadastro/status` · `POST /ia/cadastro/documento` · `POST /ia/cadastro/comprovante` (multipart, campo `arquivo`).

## Decisões

1. **Sem enumeração e sem diferença de tempo**: o envio do WhatsApp roda em `BackgroundTasks` (depois da resposta), então o caminho "CPF existe" não demora mais que o "não existe". CPF malformado também recebe 200 e a mesma mensagem.
2. **Limite por CPF vale para CPF inexistente também** (senão o 429 revelaria quem é aluno). Efeito colateral aceito: quem digita o CPF de outra pessoa 4 vezes em 15 min impede o pedido dela por alguns minutos. A chave do limite é um hash do CPF (o CPF não vai para a tabela de rate limit).
3. **Código**: o hash inclui o id do aluno (`hash_token("app-aluno:<id>:<código>")`); 5 erros marcam o código como usado (é preciso pedir outro). Só o último código aberto vale.
4. **Refresh stateless** (não há tabela de sessões do aluno, para não mexer em modelo): renovar devolve um par novo, mas o refresh antigo continua válido até vencer. Compensação: access e refresh conferem se o aluno ainda está **ATIVO** a cada uso (inativar o aluno derruba o acesso na hora). "Sair" apaga os cookies; não há revogação central do token. Se o Jefferson quiser revogação (ex.: "sair de todos os aparelhos"), é uma tabela aditiva `app_sessao`.
5. **Aluno só mexe em aula aberta**: confirmar/desmarcar só para RESERVADA/PENDENTE de hoje em diante (concluída, falta e aula passada = 409). A regra das 6 horas continua **desligada** (decisão da agenda).
6. **Reposição pelo aluno é imediata, não "solicitação"**: como `agenda.servico` oferece `remarcar_reserva` (com prazo e capacidade transacional), o aluno vê só **aulas já existentes** do mesmo serviço e unidade, até `reposicao_ate`, hoje em diante, com vaga real, fora de bloqueio e onde ele ainda não tem reserva, e a remarcação é feita na hora (vaga garantida pela transação da agenda). Não criei tabela de solicitação. Se não houver aula gerada com vaga, a tela manda falar com a recepção. A reposição consome o prazo (`reposicao_ate` zera) e a aula volta a RESERVADA.
7. **Aula sem profissional** (TotalPass) só é oferecida se a aula original também não tinha profissional (`remarcar_reserva` mantém o profissional quando não se informa outro).
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

## Pedidos ao coordenador

1. **Ligar o assistente no cadastro do aluno** (botão "Preencher com IA" hoje desabilitado em `alunos/novo/page.tsx` e `alunos/page.tsx`): `<AssistenteIA open onOpenChange onAplicar />` de `components/alunos/assistente-ia.tsx`. `onAplicar(dados: DadosAssistenteIA)` recebe só os campos preenchidos: `nome`, `cpf` (11 dígitos), `rg`, `data_nascimento` (AAAA-MM-DD), `logradouro`, `numero`, `bairro`, `cidade`, `cep` (8 dígitos). O botão só deve aparecer com `pode("ia.usar")`. O `FormAluno` precisa expor uma forma de receber esses valores (hoje o estado é interno).
2. **Notificador real**: o login do aluno chama `core.notificador.get_notificador().enviar_texto(telefone, texto)` (telefone normalizado `55DDDNÚMERO`). Falta o módulo de comunicação registrar o WasenderAPI com `definir_notificador`; sem isso o código **não chega** (padrão atual só registra no log, sem o texto). Em produção o envio deve ir para o histórico de mensagens do aluno (tipo "codigo_app") sem gravar o código.
3. **Rate limit em produção**: com mais de um processo usar `RATE_LIMIT_BACKEND=banco`; com a memória (padrão) o limite é por processo.
4. **Nginx**: servir `/app/` no Next (não na API) e manter `/api/` na API; o nginx deve SOBRESCREVER `X-Forwarded-For` (os limites por IP dependem disso). `/app/sw.js` deve ser servido sem cache longo.
5. **Cutover R15**: o antigo serve o app em `/app/` + `/app/manifest.json`, `/app/sw.js`, `/app/icon.svg`. Os mesmos caminhos existem aqui (`icon.svg` estático; os ícones PNG ficam em `/app/icone/...`). Alunos que já instalaram o app antigo precisarão entrar de novo (sessão nova).
6. `core.ia.gerar_json` poderia aprender a mandar PDF para a OpenAI (formato `file`) e usar o mesmo cliente; hoje só a IA de cadastro faz isso.

## Dúvidas para o Jefferson

1. O aluno pode **repor sozinho** (como está: escolhe um horário com vaga e já fica marcado) ou prefere que o pedido vá para a **recepção aprovar**?
2. O aluno pode repor em qualquer dia/hora com vaga, ou só em horários de dias diferentes do plano dele?
3. Ligar a regra das **6 horas de aviso** para desmarcar pelo app (hoje desligada, como no antigo)?
4. Código de acesso: 10 min e 5 tentativas estão bons? E manter o aluno logado por 7 dias sem pedir código novo?
5. Quer **revogar sessões** (sair de todos os aparelhos / bloquear um aparelho perdido)? Exige uma tabela nova.
6. Texto da mensagem do WhatsApp com o código: "Olá, Ana! Seu código de acesso ao app é 123456. Vale por 10 minutos. Não compartilhe com ninguém." Alguma mudança?

## Pendências / limites conhecidos

- A UI foi validada por `npm run lint`, `npm run build` e o fluxo manual pelo BFF (curl); **não** foi aberta num navegador/celular real nem passou por Lighthouse.
- Push notification (lembrete de aula) não faz parte do escopo.
- Reposição só oferece aulas **já geradas** (a geração é por `POST /agenda/sessoes/gerar`); aluno não cria aula nova.
- Leitura de PDF pela OpenAI depende de o modelo escolhido aceitar arquivos (modelos com visão atuais aceitam); caso contrário a tela mostra o erro do provedor e o usuário envia uma foto.
