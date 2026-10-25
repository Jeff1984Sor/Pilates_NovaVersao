# Progresso - agente Fundação (branch feat/fundacao)

## Feito
1. **Limpeza e renomeação**: removidos certificados, CNPJ, hub de RPA, NFS-e, faturamento, comunicador, assistente e dashboards fiscais (backend e frontend). Projeto `pilates-api` / `pilates-web`. Marca padrão "Pilates"; o seed cria "Studio Mayris Pilates".
2. **Single-tenant**: sem `Tenant`/`tenant_id`. Tabelas do core com nomes fixos (`usuario`, `perfil_acesso`, `identidade`, `auditoria`, `config_email`, `config_ia`). `Usuario`: login único, e-mail único, `senha_hash` nullable, `acesso_sistema`, `perfil_acesso_id`, `ativo`, `token_version`, `ultima_atividade`, foto relativa, nome, telefone. Exportações de `core/db.py` intactas.
3. **Permissões**: catálogo por recurso.ação (alunos, agenda, aulas operar/evoluir/avaliar, contratos, planos, financeiro_receber/pagar/caixa/dre/bancos, receita_saude, comissoes, cadastros_*, whatsapp, comunicacao, integracoes, configuracoes, usuarios, perfis, auditoria). **Negar por padrão** (rota sem regra = 403). O teste enumera todas as rotas (inclusive routers incluídos de forma preguiçosa no FastAPI 0.162) e falha se faltar regra, login ou rate limit. Escopo "próprias aulas" (`core/escopo.py`) pronto e testado com stub.
4. **Perfis padrão (decisão do Jefferson, via coordenador)**: apenas **Full** (administrador, não excluível), **Professor** (só as próprias aulas) e **Secretária**. Outros perfis se criam pela matriz de permissões.
5. **Auth seguro**: login por e-mail ou usuário; access 30 min + refresh 14 dias com rotação (tabela `refresh_token`); reuso de refresh fora de 15 s derruba todas as sessões; `token_version` invalida tudo ao trocar/redefinir senha, desativar usuário ou mudar o perfil; bloqueio de 5 tentativas / 15 min com resposta genérica (não revela a conta); recuperação por e-mail (link de uso único, só o digest no banco) e por código no WhatsApp (6 dígitos, 10 min, 5 tentativas) via protocolo `Notificador` (falso `NotificadorMemoria` nos testes); troca de senha exige a atual; **hash PBKDF2 do Django aceito** e regravado em Argon2 (teste com hash gerado pelo Django 5.2 real).
6. **Rate limit** (`core/ratelimit.py`, janela deslizante em memória, opção `RATE_LIMIT_BACKEND=banco`); **cifra de segredos** (`core/segredos.py`, Fernet com suporte a rotação de MASTER_KEY); **storage** (`core/storage.py`: caminho relativo, anti path-traversal, extensão/tamanho/assinatura do arquivo, rota autenticada com permissão por categoria) e **link assinado com prazo** (`core/links.py`, HMAC + expiração).
7. **Config** (`core/config.py`): em hml/prod exige JWT_SECRET (>=32) e MASTER_KEY próprios e diferentes entre si, DEBUG=false, ALLOWED_HOSTS explícito, https, CORS sem localhost, rate limit ligado. `LEGACY_DJANGO_SECRET_KEY` opcional. `.env.example` (backend e frontend) só com nomes.
8. **Frontend**: login, esqueci senha (e-mail ou código WhatsApp), redefinir senha, painel placeholder, configurações (identidade, usuários, perfis com matriz e "somente as próprias aulas", e-mail, IA), auditoria, minha conta, menu com todas as áreas planejadas (não clicáveis). **BFF com cookies httpOnly** (`app/bff/[...path]/route.ts`), renovação automática de sessão (uma por vez), `proxy.ts` (Next 16) barra páginas privadas sem sessão. `npm run lint` e `npm run build` sem erro; fluxo validado ponta a ponta com a API real (login, páginas privadas, renovação paralela, troca de senha, logout).
9. **Deploy** (`deploy/`): `pilates-nova-{api,worker,web}@<hml|prod>`, pasta `/home/deploy/pilates-nova/<amb>`, bancos `pilates_nova_hml|prod`, portas 10041/10042 (hml) e 10051/10052 (prod), domínios placeholder, todos marcados "verificar no servidor". nginx com headers de segurança, rate limit e `/api` público só para integracao/aluno-app/webhooks/arquivos-publicos/health. Gate de testes e health check mantidos. `rollback.sh` marca o HEAD solto, avisa e tem `--retomar`; `deploy.sh` detecta HEAD solto. Backup inclui o storage (caminho do `.env`), confere os arquivos e não mistura a MASTER_KEY. **Nada foi executado no servidor.**
10. **Seed/CLI**: seed idempotente (identidade, e-mail e IA vazios, 3 perfis; admin de demonstração só em dev, senha por `SEED_ADMIN_SENHA` ou prompt); `criar_usuario`; `limpar_dados` com tabelas derivadas dos metadados. Seed e fluxo **não dependem de nenhum segredo de integração** (e-mail, WhatsApp, TotalPass e IA partem vazios; cadastro pela tela).
11. **Testes**: `cd backend && uv run python -m pytest -q` (120 testes).

## Decisões
- Ids de recurso sem ponto: `financeiro_receber` representa "financeiro.receber".
- Sessão do navegador via BFF + cookies httpOnly (SameSite=Lax, `X-Requested-With` e conferência de Origin nas escritas). `/auth/refresh` não é exposto ao navegador. Em hml/prod o Next chama a API por `127.0.0.1`, por isso `ALLOWED_HOSTS` inclui `127.0.0.1`.
- O nginx deixa a internet alcançar apenas `/api/{integracao,aluno-app,webhooks,arquivos-publicos,health}`; o restante da API só pelo BFF.
- Removi do pyproject: lxml, openpyxl, pypdf, reportlab, signxml, sse-starlette. Quem precisar de PDF/Excel reinclui.
- Telefone para WhatsApp: normalização mínima só em `auth_service.telefone_whatsapp`; a normalização completa (R16) é do domínio.

## Falta / pendências para outros agentes e para o coordenador
- `backend/alembic/env.py` (DADOS) ainda importa módulos que não existem mais (`app.comunicador`, `app.modules.faturamento` etc.). Não toquei. A migração inicial do DADOS deve incluir as tabelas do core, inclusive `refresh_token`, `recuperacao_senha`, `rate_limit_evento` e a coluna `perfil_acesso.somente_proprias_aulas`.
- Ligar `escopo.registrar_resolvedor_profissional` ao vínculo usuário-profissional quando o modelo existir.
- Implementação real do `Notificador` (WasenderAPI) vem do módulo de comunicação (`notificador.definir_notificador`).
- Verificação dos links de contrato/termo do Django (`LEGACY_DJANGO_SECRET_KEY`) é do módulo de contratos.
- Triggers de banco (Postgres) para reforçar a imutabilidade da auditoria: hoje a barreira é no ORM e no cursor SQL da aplicação.

## Dúvidas para o Jefferson
1. **Escopo da Secretária (suposição a confirmar)**: agenda e aulas de todos (operar, evoluir, avaliar), alunos (ver/editar), contratos (ver/editar/enviar), planos (ver), contas a receber (ver/baixar), WhatsApp e comunicação (ver/enviar), cadastros só para consulta. Sem contas a pagar, bancos, caixa, DRE, comissões, Receita Saúde, configurações, usuários, perfis, integrações e auditoria. Pode excluir alunos/contratos? Hoje não.
2. O Professor precisa abrir a ficha do aluno (dados cadastrais) além de evolução/avaliação? Hoje não tem `alunos.ver`.
3. Domínios definitivos de hml/prod e confirmação das portas 10041/10042/10051/10052 no servidor.
4. Bucket de backup (placeholder `CONFIGURAR-BUCKET`).

## Como rodar
```
cd backend && uv sync && uv run python -m pytest -q
uv run python -m app.seed --sem-migrar      # dev, depois de criar as tabelas; senha por SEED_ADMIN_SENHA
uv run python -m uvicorn app.main:app --port 8000
cd ../frontend && npm install && INTERNAL_API_URL=http://localhost:8000/api npm run dev
```
Obs.: nesta máquina as portas 8000 e 3100 estavam ocupadas por outro projeto; use `--port` diferente se precisar.
