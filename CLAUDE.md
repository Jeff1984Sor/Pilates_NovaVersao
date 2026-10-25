# CLAUDE.md — Pilates Nova Versão

> **Leia primeiro.** Reescrita do sistema do **Studio Mayris Pilates** (hoje em Django, em produção) para a stack do MayaJus.
> **Regra de ouro: não perder nenhuma funcionalidade nem nenhum dado do sistema antigo.**
> Contrato e lista de paridade: [`docs/MIGRACAO.md`](docs/MIGRACAO.md). Inventário completo do sistema antigo: [`docs/inventario-pilates-django.md`](docs/inventario-pilates-django.md).

## Origem e destino

| | Sistema antigo (NÃO MEXER) | Este projeto |
|---|---|---|
| Código | `C:\Users\JeffersonFernandes\Projetos\Pilates\PilatesFinal` (Django + `api/` FastAPI) | `C:\Users\JeffersonFernandes\Projetos\Pilates_NovaVersao` |
| Produção | `https://mayris.mayacorp.com.br` (VPS `ssh flicsales`, pasta `~/pilates`, serviços `pilates-web`/`pilates-api`) | ainda não existe; terá hml e prod próprios |
| Banco | PostgreSQL `pilates` (tabelas `core_*`, ~17 mil linhas) | **banco novo**, esquema limpo; os dados antigos entram por ETL **só no final** |

**Proibido nesta fase:** alterar o sistema antigo, conectar na produção antiga, ou baixar dados reais de alunos para a máquina de desenvolvimento. Testes usam dados sintéticos. A carga real do banco antigo é uma etapa final, com autorização explícita do Jefferson.

## Stack (igual à do MayaJus, `C:\Users\JeffersonFernandes\Projetos\MayacorpAutomacoes_CFME`)

- `backend/`: FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic, Python 3.12, gerenciado com `uv`. Rode com `uv run python -m ...` (os `.exe` do venv são bloqueados no Windows desta máquina; `uv run pytest` falha e `uv run python -m pytest` funciona).
- `frontend/`: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query + Zod.
- Banco: PostgreSQL (hml/prod), SQLite só em dev/testes. Fila e tarefas periódicas no worker (`app.worker`).
- Deploy: `deploy/` (systemd templated + nginx), hml antes de prod, tag `vN` em prod.

## Decisões já tomadas

1. **Um estúdio por instalação** (sem `tenant_id`). Identidade (nome, logo, cor) vem do banco (white-label), nunca fixa no código.
2. **Segurança por padrão**: toda rota exige login; rota pública precisa estar numa lista explícita. JWT com expiração e refresh, OTP com limite de tentativas, segredos de integração **cifrados** no banco (Fernet com `MASTER_KEY`), webhooks exigem token, arquivos só por rota autenticada ou por link assinado com prazo.
3. **Perfis de acesso por catálogo de permissões** (como no MayaJus), com perfis padrão: Administrador, Recepção/Gestão, Financeiro, **Professor** (só as próprias aulas, nada de financeiro) e Somente leitura. Profissional **sem login** é permitido.
4. **Regras de negócio ficam em `app/domain/` como funções puras com testes** (preço, parcelas, capacidade, reposição, status...). Rota só orquestra. Nada de regra escondida em CRUD genérico.
5. Dinheiro sempre `Decimal`/`Numeric(15,2)`. Datas de negócio em `Date`; instantes em `UtcDateTime`. Fuso de negócio: `America/Sao_Paulo`.
6. Códigos de negócio antigos (`cdAluno`, `cdContrato`...) são **preservados** em colunas `codigo_legado` (integradores externos usam `cdAluno`).
7. Capacidade da aula é garantida com transação + bloqueio (não só validação em Python).

## Como trabalhar (agentes e humanos)

- Branch `develop` = integração (vai para hml); `main` = produção. Trabalho em branch `feat/<assunto>`; PR/merge em `develop`. **Nunca** force-push em `main`/`develop`.
- Commits pequenos, mensagem em português dizendo o que muda e por quê. Terminar mensagem com a linha `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Todo trecho de regra portada do Django precisa de **teste de caracterização** com o caso numérico do sistema antigo (ver `docs/MIGRACAO.md`, seção Regras).
- Antes de dar algo como pronto: `cd backend && uv run python -m pytest -q` verde; no frontend, `npm run build` sem erro.
- Não commitar `.env`, `*.pfx`, bancos, `storage/`, `node_modules`. Segredo nunca em código.
- Registre o andamento em `docs/PROGRESSO.md` (o que foi feito, o que falta, decisões e dúvidas para o Jefferson).

## Comandos

```bash
cd backend
uv sync
uv run python -m pytest -q
uv run python -m alembic revision --autogenerate -m "..."
uv run python -m alembic upgrade head
uv run python -m uvicorn app.main:app --reload --port 8000
cd ../frontend && npm install && npm run dev
```
