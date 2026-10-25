# Progresso do agente CADASTROS-BASE

Branch `feat/cadastros-base` (saída de `develop`). Escopo: unidades, tipos de serviço, planos, profissionais (com vínculo de login) e profissões, em API + testes + telas.

## Estado

- [x] API: `unidades`, `servicos`, `planos`, `profissionais`, `profissoes` (CRUD, ativar/desativar, vínculos, auditoria, permissões)
- [x] Planos: valor por aula (R1, `app.domain.precos`), duplicar, opções do formulário
- [x] Profissionais: com ou sem login, convite pelo core, revogar acesso (`token_version`), sincronização usuário↔profissional, resolvedor do escopo do Professor, "Minha conta"
- [x] Testes: `backend/tests/cadastros_base/` (CRUD, permissões Full/Professor/Secretária, vínculos, duplicar, usuário↔profissional, escopo, auditoria, validações)
- [x] Telas: Unidades, Tipos de serviço, Planos, Profissionais, Profissões + card "Meus dados de profissional" em Minha conta
- [x] Menu (`nav.ts`): entradas marcadas `planejado: false`
- [ ] Verificação visual no navegador (feita só `npm run lint` e `npm run build`; ver "Pendências")

## Arquivos

Backend, em `backend/app/modules/cadastros/` (só os meus):

| Arquivo | Conteúdo |
|---|---|
| `comum.py` | `PaginaCad` (página + contagens por situação), busca com escape de curinga, ordenação por lista branca, vínculos por FK (varre o `metadata`), ativar/desativar genérico |
| `unidades.py`, `servicos.py`, `profissoes.py`, `planos.py`, `profissionais.py` | um `APIRouter` por entidade |
| `vinculo_usuario.py` | regras usuário↔profissional (conceder/revogar acesso, sincronizar) e o resolvedor do escopo do Professor |
| `routes_base.py` | `router` que inclui os cinco sub-routers + `adicionar_regras` + `registrar_escopo()` |

Frontend: `app/(app)/cadastros/{unidades,servicos,planos,profissionais,profissoes}/page.tsx`, `components/cadastros/{lista-cadastro,meu-profissional}.tsx`, `components/cadastros/mascaras.ts`, `lib/tipos-cadastros.ts`.

## API

Todas exigem login, regra de permissão e geram auditoria em criar/alterar/excluir/ativar/desativar. Listas: `?q=&situacao=ativos|inativos|todos&ordenar=&direcao=asc|desc&pagina=&por_pagina=` (máx. 200) e devolvem `contagens {ativos, inativos, todos}` (respeitam a busca e os filtros, não a situação escolhida).

| Rota | Permissão |
|---|---|
| `/api/cadastros/unidades` (+ `/{id}`, `/{id}/vinculos`, `/{id}/ativar`, `/{id}/desativar`) | `cadastros_unidades.*` |
| `/api/cadastros/servicos` (idem) | `cadastros_servicos.*` |
| `/api/cadastros/profissoes` (CRUD + `/{id}/vinculos`) | `cadastros_profissionais.*` (não há recurso próprio no catálogo) |
| `/api/planos` (idem + `/{id}/duplicar`, `/opcoes`) | `planos.*` |
| `/api/cadastros/profissionais` (idem + `/perfis-acesso`) | `cadastros_profissionais.*` |
| `POST/DELETE /api/cadastros/profissionais/{id}/acesso` (POST recebe `perfil_acesso_id` e `login`), `POST .../acesso/convite` | `cadastros_profissionais.editar` **e** `usuarios.editar` (checado na rota) |
| `GET/PATCH /api/cadastros/profissionais/meu` | livre para logados (só o próprio profissional) |

Observação: a rota dos planos é `/api/planos` (recurso `planos`), mas a tela fica em `/cadastros/planos` (decisão: a pasta é minha; o `nav.ts` foi ajustado).

## Decisões

1. **R3 (capacidade)**: `unidade.capacidade` é o padrão de vagas por aula. Sessão com capacidade NULA herda a da unidade (`capacidade_efetiva` em `app.domain.capacidade`); 0 na sessão vale 0. **Decisão do Jefferson: capacidade da unidade 0 é PROIBIDA**: capacidade 1–500 e duração 1–240 min; a API responde 422 "A capacidade da unidade precisa ser de pelo menos 1 vaga por aula." (idem duração) e o formulário valida igual.
2. **Código de negócio**: todo registro novo usa `proximo_codigo(db, "unidade"|"tipo_servico"|"plano"|"profissional"|"profissao")` (mesmos nomes de série que o ETL inicializa), gravado em `codigo_legado`; a API expõe como `codigo`. Teste garante que continua do contador do ETL.
3. **Exclusão**: `comum.vinculos()` percorre todas as FKs do `metadata` que apontam para o cadastro (menos `ON DELETE CASCADE`) e conta os registros por tabela. Com vínculos: `DELETE` responde 409 com texto como "Não é possível excluir a unidade: ela está em uso por 12 aulas, 3 contratos. Desative-a em vez de excluir." A tela consulta `/{id}/vinculos` antes e oferece "Desativar" no lugar de "Excluir". Funciona sem mudar quando novas tabelas passarem a apontar para o cadastro. Profissão não tem ativo/inativo: só bloqueia. **Unidade (decisão do Jefferson)**: horários de funcionamento, horários da grade e bloqueios saem JUNTO (exclusão em cascata na mesma transação, registrada na auditoria); aulas, contratos, alunos e demais vínculos continuam bloqueando com 409 e sugerindo desativar. `GET /{id}/vinculos` devolve `itens`/`total`/`pode_excluir` (o que bloqueia) separados de `junto`/`total_junto` (o que será removido junto), e a confirmação da tela mostra "Serão removidos junto: …".
4. **Nome único (sem diferenciar maiúsculas)** em unidade, serviço, plano e profissão (409). Não há constraint no banco; a checagem é na rota.
5. **Plano**: `valor` é MENSAL; `valor_aula` e `valor_total` vêm de `precificar_contrato` (R1). Validações: valor 0–9.999.999,99 (plano avulso TotalPass de valor 0 é permitido), aulas/semana 0–14, duração 1–120 meses. Categoria e subcategoria têm de ser de RECEITA e coerentes (subcategoria sem categoria preenche a categoria). Duplicar: "Nome (cópia)", "(cópia 2)"..., novo código, mantém todos os campos e a situação.
6. **Profissional ↔ usuário** (substitui os signals do Django):
   - **Login (decisão do Jefferson)**: todos entram com um LOGIN próprio (ex.: `ana`), nunca com e-mail. Ao dar acesso o campo `login` é obrigatório (3 a 30 caracteres: minúsculas, números, ponto, hífen e sublinhado; sem `@` nem espaço; guardado em minúsculas; único sem diferenciar maiúsculas, 409 se repetido). O e-mail continua obrigatório só como contato, recuperação de senha e convite. Editar permite trocar o login (valida unicidade e derruba as sessões via `token_version`; exige `usuarios.editar`). A lista mostra e busca o login; Minha conta já mostra o login. Os testes de login usam o campo `login` (`tests/cadastros_base/test_login_profissional.py`). O core passará a aceitar somente login (coordenador).
   - Profissional sem login: `usuario_id` nulo. Dar acesso: cria `usuario` com `login` escolhido e `email` do profissional, perfil escolhido, `convite_pendente`, sem senha, e envia o link de definição de senha com `auth_service.enviar_link_email(convite=True)`. Se o e-mail não sair (SMTP não configurado), o cadastro é mantido e a resposta traz `convite_enviado: false` (a tela avisa; há "Reenviar convite").
   - Revogar acesso: `acesso_sistema=False`, `convite_pendente=False`, `invalidar_sessoes` (sobe `token_version`, derruba access/refresh). O usuário é mantido e o vínculo também (histórico/auditoria). Dar acesso de novo reaproveita o mesmo usuário, zera a senha e manda novo convite.
   - Editar sincroniza nome, e-mail (contato), login, celular (→ `usuario.telefone`), situação e perfil. Desativar o profissional desativa o usuário; reativar reativa. Mudança de perfil derruba as sessões.
   - Proteções iguais às do core: não tirar o próprio acesso, manter pelo menos um Administrador ativo, e-mail único (409 com mensagem), e-mail obrigatório para quem tem acesso.
   - Excluir profissional (sem aulas etc.) desativa o usuário vinculado.
   - Dar/tirar acesso e trocar o perfil exigem também `usuarios.editar` (uma "gestora de cadastros" sem esse recurso não consegue elevar privilégio).
   - Celular normalizado pela R16 (`normalizar_telefone_br`, `55`+DDD+número); inválido dá 422.
7. **Escopo do Professor**: `vinculo_usuario.resolver_profissional_id(db, usuario)` = id do profissional com `usuario_id == usuario.id` (mesmo com acesso revogado) ou `None`. Registrado por `routes_base` na importação (`escopo.registrar_resolvedor_profissional`). Sem vínculo o perfil restrito não enxerga nada.
8. **Minha conta**: `GET/PATCH /cadastros/profissionais/meu` edita só nome, celular, nascimento e CREFITO do próprio profissional (e sincroniza `usuario.nome/telefone`). E-mail, comissão, perfil e situação ficam de fora. A tela de Minha conta ganhou o card `MeuProfissionalCard` (uma linha de import e uma de uso em `app/(app)/minha-conta/page.tsx`; o card não aparece para quem não é profissional).
9. **Professor**: nenhum recurso `cadastros_*` nem `planos.*` no perfil Professor, então negado por padrão (testado em todas as rotas). A Secretária só consulta (herda `*.ver` do perfil padrão), inclusive `GET /planos/opcoes`.

## Pedidos ao coordenador

1. **`routes.py` do pacote** `app/modules/cadastros/routes.py` deve incluir `routes_base.router` (e o da outra frente). Não declarei `router` em `routes.py` para não conflitar. Exemplo: `from app.modules.cadastros.routes_base import router as router_base; router = APIRouter(); router.include_router(router_base)`.
2. **Teste do core a ajustar quando o `routes.py` existir**: `tests/test_permissoes.py::test_escopo_sem_resolvedor_registrado_nega` assume que nenhum resolvedor está registrado; com `routes_base` importado pelo `main`, o resolvedor real fica registrado e esse teste passa a falhar. Sugestão: o teste chamar `escopo.registrar_resolvedor_profissional(escopo._sem_resolvedor)` antes. Hoje, no meu `conftest`, o resolvedor é ligado e desligado a cada teste para a suíte inteira continuar verde sem o `routes.py`.
3. **Catálogo de permissões**: não existe recurso para Profissões; mapeei para `cadastros_profissionais`. Se preferir recurso próprio (`cadastros_profissoes`), é só acrescentar ao `CATALOGO` e trocar a regra em `routes_base.py`.
4. **Migração**: nenhuma mudança de modelo foi necessária (usei só as colunas existentes). Sugestões opcionais, NÃO feitas: índice único funcional `lower(nome)` em unidade/tipo_servico/plano/profissao (hoje a unicidade é só na rota) e índice em `lower(email)` de profissional.
5. **`nav.ts`**: marquei `planejado: false` em Unidades, Tipos de serviço, Profissionais e Planos; o href de Planos mudou de `/planos` para `/cadastros/planos` (a pasta da tela está no meu escopo); **acrescentei** a entrada "Profissões" (`/cadastros/profissoes`, permissão `cadastros_profissionais.ver`, ícone Briefcase) logo depois de Profissionais, porque não existia no menu. Pode dar conflito de merge trivial na área "Cadastros" com a outra frente.
6. Outros módulos que precisem listar unidades/serviços/profissionais/planos para selects podem chamar as mesmas listas (`por_pagina=200&situacao=ativos`) se o perfil tiver `*.ver`; para planos, `GET /api/planos/opcoes` traz serviços, categorias de receita, subcategorias e modelos de contrato (ler direto dos modelos da outra frente).

## Dúvidas para o Jefferson

Respondidas (2025-10-25) e aplicadas: login próprio (item de decisão 6), comissão (continua um percentual por profissional, igual para todos os planos e serviços), capacidade mínima 1, Secretária só consulta (testes mantidos), exclusão de unidade com cascata de horários/bloqueios.

1. **Profissional inativo com aulas futuras**: desativar não cancela nada. O agente de Agenda deve decidir o que fazer (avisar?).

## Pendências

- Verificação visual: `npm run lint` e `npm run build` passam, mas as telas não foram abertas num navegador nesta sessão (sem API real + Next rodando juntos). Os fluxos de API estão cobertos por testes.
- Exclusão de tipo de serviço: continua 409 por qualquer vínculo (inclusive horários de funcionamento); só a unidade leva horários/bloqueios junto.
- Foto do profissional: pode ser trocada em Configurações › Usuários (rota do core); não repliquei na tela de profissionais.

## Como rodar

```bash
cd backend && uv sync
uv run python -m pytest -q tests/cadastros_base tests/test_cobertura_rotas.py   # 100+ testes dos cadastros-base
uv run python -m pytest -q                                                       # suíte inteira (lenta)
cd ../frontend && npm install && npm run lint && npm run build
```

Para ver as telas hoje (sem o `routes.py` do pacote): montar `routes_base.router` no app, por exemplo num `routes.py` temporário com `from app.modules.cadastros.routes_base import router` e subir `uvicorn app.main:app --port 8001` + `INTERNAL_API_URL=http://localhost:8001/api npm run dev`.
