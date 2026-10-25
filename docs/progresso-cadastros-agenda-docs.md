# Progresso do agente CADASTROS-AGENDA-DOCS

Branch `feat/cadastros-agenda-docs` (saída de `develop`). Escopo: fornecedores, categorias/subcategorias, horários de funcionamento e do studio, bloqueios de agenda, termos de uso, modelos de contrato e modelos de evolução (API, testes e telas), mais o domínio novo `app/domain/modelos_documento.py`.

## Estado

- [x] Domínio `modelos_documento` (31 variáveis oficiais, `renderizar`, `variaveis_usadas`, `variaveis_desconhecidas`) com caracterização contra o `render_contrato_html` / `render_termo_html` do antigo (golden gerado com o Django real)
- [x] API de fornecedores, categorias + subcategorias, horários (funcionamento e studio legado, gerar em lote), bloqueios, termos e modelos (contrato e evolução)
- [x] HTML dos modelos sanitizado no servidor (`nh3`, allowlist), pré-visualização com dados de exemplo, duplicar modelo
- [x] Telas: fornecedores, categorias (abas categorias/subcategorias), horários (abas funcionamento/studio legado), bloqueios, termos (lista + editor), modelos (hub + contrato com editor + evolução)
- [x] Menu: as 6 entradas de Cadastros que são minhas estão `planejado: false`
- [x] Testes: 150 testes novos em `tests/cadastros_agenda_docs` + 39 em `tests/domain/test_modelos_documento.py`; `npm run lint` e `npm run build` limpos
- [ ] Conferir a tela no navegador com um usuário real (o editor `contenteditable` não foi exercitado em navegador nesta máquina; ver "Pontos de atenção")

## Arquivos

Backend (`backend/app/modules/cadastros/`): `fornecedores.py`, `categorias.py`, `horarios.py`, `bloqueios.py`, `termos.py`, `modelos_documentos.py`, `html_seguro.py` (sanitização), `util_docs.py` (paginação, busca, ordenação, auditoria), `routes_agenda_docs.py` (junta os routers e registra as exceções de permissão). Domínio: `backend/app/domain/modelos_documento.py`. Dependência nova: `nh3`.
Testes: `backend/tests/cadastros_agenda_docs/` (+ `gerar_golden_modelos.py` e `golden_modelos.py`) e `backend/tests/domain/test_modelos_documento.py`.
Frontend: `app/(app)/cadastros/{fornecedores,categorias,horarios,bloqueios,termos,modelos,modelos-contrato,modelos-evolucao}/`, `components/cadastros-docs/`, `lib/tipos-cadastros-docs.ts`.

## Rotas (prefixo `/api`)

| Rota | Permissão (mapa do core) |
|---|---|
| `/cadastros/fornecedores` (GET, POST, GET/PUT/DELETE `/{id}`) | `cadastros_fornecedores.*` |
| `/cadastros/categorias`, `/cadastros/categorias/subcategorias` (+ `/{id}`) | `cadastros_categorias.*` |
| `/cadastros/horarios` (+ `/gerar`, `/opcoes`, `PATCH /{id}/ativo`), `/cadastros/horarios/studio` (+ `/gerar`, `/{id}`) | `cadastros_horarios.*` |
| `/cadastros/bloqueios` (+ `/opcoes`, `/{id}/datas`, `PATCH /{id}/ativo`) | `cadastros_bloqueios.*` |
| `/cadastros/termos` (+ `/variaveis`, `/{id}/duplicar`) e `POST /cadastros/termos/previa` | `cadastros_termos.*`; a prévia só exige `cadastros_termos.ver` |
| `/cadastros/modelos/contrato` (+ `/{id}/duplicar`, `PATCH /{id}/ativo`), `/cadastros/modelos/evolucao`, `/cadastros/modelos/variaveis` e `POST /cadastros/modelos/contrato/previa` | `cadastros_modelos.*`; a prévia só exige `.ver` |
| `GET /cadastros/modelos/evolucao/ativos` | **`aulas.evoluir`** (a gaveta de evolução da agenda, inclusive do Professor, lista os modelos ativos) |

Todas as listas aceitam `q`, `pagina`, `por_pagina`, `ordenar`, `direcao` e devolvem `contagens` (chips de situação calculados só com a busca, sem o filtro do chip). Escritas auditadas (`fornecedor.criar`, `bloqueio_agenda.alterar`, `modelo_contrato.duplicar`, `horario_funcionamento.gerar`...); o HTML dos modelos entra na auditoria só com o tamanho.

## Decisões

1. **Variáveis**: a lista oficial são as 31 do antigo (`CONTRACT_TEMPLATE_VARIABLES`), com acento nas descrições e um exemplo cada. O termo só conhece as 15 de aluno, endereço e data (era o que `render_termo_html` trocava); as de contrato aparecem como "não reconhecidas" no termo.
2. **Renderização** (divergências deliberadas do antigo, nenhuma muda um modelo legítimo): troca em uma passada; valores **escapados** como HTML por padrão (nome de aluno com `<script>` não vira marcação); variável desconhecida continua literal, mas é listada para quem edita (`variaveis_desconhecidas`) e o editor avisa. `escapar=False` reproduz o antigo byte a byte (é o que o teste de caracterização usa). A formatação de moeda mantém a do antigo (`R$ 1234,50`, sem separador de milhar).
3. **Sanitização**: allowlist em `html_seguro.py` (tags de texto/lista/tabela/link/imagem, `style` só com propriedades de alinhamento/ênfase/tabela, links `http/https/mailto/tel`). `<script>`, `<style>`, `<iframe>`, `<svg>`, formulários, `on*`, `javascript:` e `data:` saem. Limite de 300 mil caracteres. A pré-visualização é renderizada no servidor e exibida em `<iframe sandbox="">` (nenhum script roda).
4. **Bloqueio**: pontual **exige data final** (para um dia só, a mesma data nos dois campos). Registros migrados sem data final continuam valendo (a agenda não muda sem ação do usuário), aparecem com aviso e só podem ser salvos de novo com data final. Recorrente pode ficar sem data final, com aviso visível. Recorrente cria um registro por dia da semana marcado (como o antigo); editar mexe em um registro só. `GET /bloqueios/{id}/datas` lista as próximas datas afetadas usando `app.domain.agenda.slot_bloqueado`.
5. **Duplicidade de horário de funcionamento**: o modelo não tem `unique`; mantive a regra do antigo no serviço (igual unidade/dia/início/fim e, sem serviço, já existe janela geral; com serviços, já existe janela geral ou que atenda algum dos mesmos serviços). Vale também ao editar. O número de aulas por dia que a janela gera vem de `app.domain.agenda.gerar_slots_do_dia`.
6. **Gerar horários**: funcionamento = a mesma janela em vários dias (não divide em intervalos, como o antigo); studio = divide em horários consecutivos de N minutos (5 a 480), com teto de 2000 por geração. Ambos idempotentes (ignoram o que já existe) e devolvem criados/ignorados.
7. **Códigos**: `proximo_codigo(db, nome)` com os nomes que o ETL já inicializa (`fornecedor`, `categoria`, `subcategoria`, `modelo_contrato`, `modelo_evolucao`, `termo_uso`, `horario_studio`). Horário de funcionamento e bloqueio não tinham código no antigo e ficam sem `codigo_legado`.
8. **Exclusão com vínculos** (409 com a explicação na tela): fornecedor com contas a pagar; categoria com subcategorias, contas a pagar ou planos; subcategoria em uso por contas a pagar ou planos; modelo de contrato usado por plano; termo aceito por algum aluno (o aceite é evidência). Trocar o tipo de uma categoria em uso e mover uma subcategoria em uso também é recusado. Nomes duplicados (sem diferenciar maiúsculas) são recusados nos novos cadastros.
9. **Duplicar**: a cópia do modelo de contrato nasce **inativa** ("X (cópia)", "X (cópia 2)"...) para não passar a valer sem revisão; a do termo é só uma cópia (termo não tem `ativo`).
10. **Modelo de evolução** guarda texto simples (qualquer marcação é removida).
11. **Telas**: abas na URL (`?aba=`), chips com contagem, ordenação por coluna, paginação, estado vazio, confirmação de exclusão que mostra a recusa do servidor dentro do diálogo. Formulários simples em diálogo (RHF + zod); documentos longos em página própria (`/cadastros/termos/[id]`, `/cadastros/modelos-contrato/[id]`), com aviso de alterações não salvas. `/cadastros/modelos` é um hub com os dois tipos de modelo (o item "Modelos" do menu aponta para ele).
12. **Editor**: `contenteditable` + `document.execCommand` (negrito, itálico, sublinhado, título, subtítulo, listas, alinhamento, tabela 2x2, linha, limpar formatação, desfazer/refazer), aba "HTML" para editar o código, aba de pré-visualização, painel de variáveis agrupado e com busca que insere no cursor. Colar traz só texto puro.
13. **Perfis**: Professor nega tudo (testado em todas as rotas, exceto `modelos/evolucao/ativos`). Secretária só consulta (herda `cadastros_*.ver` do core; é a suposição já registrada em `docs/progresso-fundacao.md`).

## Pedidos para o coordenador

1. **Unir as rotas**: no `routes.py` do módulo `cadastros`, `from app.modules.cadastros.routes_agenda_docs import router as router_agenda_docs` e `router.include_router(router_agenda_docs)` (ou equivalente). Enquanto isso não existe, o `conftest.py` de `tests/cadastros_agenda_docs` inclui o router no app por conta própria (e não duplica se o coordenador já o tiver incluído). `tests/test_cobertura_rotas.py` só passa a enxergar as minhas rotas depois dessa união; um teste meu (`test_minhas_rotas_existem_tem_login_e_regra_de_permissao`) já faz a mesma checagem.
2. **Modelo (aditivo, migração nova)**: `fornecedor`, `categoria` e `subcategoria` não têm `ativo`; o briefing pedia "ativo" nessas listas e o termo de uso também não tem. Não mexi no modelo. Se o Jefferson quiser inativar em vez de excluir, é uma coluna `ativo Boolean default true` nessas tabelas (e em `termo_uso`); a API e as telas já estão prontas para acrescentar o chip.
3. **Catálogo de permissões**: nada novo. Sugestão opcional: separar `cadastros_modelos` em `cadastros_modelos_contrato` e `cadastros_modelos_evolucao` se um dia alguém precisar editar um e não o outro. O mapa do core já cobre `/cadastros/{fornecedores,categorias,horarios,bloqueios,termos,modelos}`; só acrescentei, via `adicionar_regras`, as exceções das prévias e de `evolucao/ativos`.
4. **Agente da agenda**: a gaveta de evolução pode listar os modelos em `GET /api/cadastros/modelos/evolucao/ativos` (permissão `aulas.evoluir`), ou ler `ModeloEvolucao` direto. Para horários e bloqueios, usar `app.domain.agenda` com `HorarioFuncionamento`/`BloqueioAgenda` (`bloqueios.py` mostra como montar `dom.Bloqueio` a partir do modelo).
5. **Agente de contratos**: usar `app.domain.modelos_documento.renderizar(html, contexto)` (contexto = dicionário `CHAVE -> valor` já formatado; datas como `date` saem em `dd/mm/aaaa`) e `MODELO_CONTRATO_PADRAO` quando o plano não tem modelo. O termo usa `escopo="termo"`.
6. **Auditoria do core**: `audit.snapshot` não serializa `time` (quebrava com horários). Contornei em `util_docs.foto`; seria melhor tratar `time` em `core/audit._jsonable` (arquivo do core, não toquei).

## Dúvidas para o Jefferson

1. **Fornecedores, categorias e termos precisam de "ativo"?** (ver pedido 2 acima.) Hoje só dá para excluir, e a exclusão é recusada se houver vínculo.
2. **Bloqueio recorrente sem data final** continua permitido (ex.: "toda terça das 12h às 13h, sempre"), com aviso. Prefere exigir data final também nele?
3. **Valores com HTML nos documentos**: escapamos por padrão (mais seguro que o antigo). Se algum modelo antigo contava com HTML dentro de um valor (improvável), seria preciso desligar para aquela variável.
4. **Secretária** pode criar/editar cadastros de agenda (horários, bloqueios, modelos) ou só consultar? Hoje só consulta (decisão herdada do perfil padrão).
5. **Formatação de moeda** nos contratos: mantive `R$ 1234,50` (sem ponto de milhar) para ficar idêntico ao antigo; trocar para `R$ 1.234,50` é uma linha.

## Pontos de atenção

- O editor usa `document.execCommand` (obsoleto, mas suportado em todos os navegadores e sem dependência). Os testes cobrem o servidor (sanitização, variáveis, prévia); o comportamento do `contenteditable` precisa de uma passada manual em navegador (inserir variável no cursor, colar texto, tabela, voltar da aba HTML).
- A busca/ordenação por texto usa `lower()` do banco: em SQLite (dev/testes) letras acentuadas maiúsculas não são normalizadas; em PostgreSQL com collation pt_BR funciona normalmente.
- Os testes fazem login por teste (hash Argon2), então a pasta leva ~2 min; os 39 testes do domínio rodam em segundos.

## Como rodar

```bash
cd backend && uv sync
uv run python -m pytest -q tests/cadastros_agenda_docs tests/domain/test_modelos_documento.py tests/test_cobertura_rotas.py
# regenerar o golden do antigo (Python do ambiente ANTIGO; banco temporário fora do repo)
<venv antigo>/python.exe backend/tests/cadastros_agenda_docs/gerar_golden_modelos.py
cd ../frontend && npm install && npm run lint && npm run build
```
