# Progresso - agente ALUNOS (branch feat/alunos)

## Feito

**Backend** (`backend/app/modules/alunos/`: `routes.py`, `schemas.py`, `servico.py`; testes em `backend/tests/alunos/`, 56 testes)

- Lista `GET /alunos`: busca (nome, CPF, RG, telefone, código), ordenação (`nome`, `codigo`, `cadastro`, `status`, com `-` para decrescer), paginação, `situacao=ativos|inativos|todos` e **contagem dos chips** (`contagens.ativos/inativos/todos`, respeitando o escopo do Professor). A lista devolve CPF **mascarado**.
- Busca da barra do topo `GET /alunos/busca?q=` (aluno, CPF ou telefone; mínimo 2 caracteres, até 8 resultados, ativos primeiro).
- `GET /alunos/opcoes`: unidades, profissões, termos e estados civis para os selects do cadastro (não depende das rotas de Cadastros).
- `GET /alunos/cep/{cep}`: ViaCEP com timeout de 4 s, cache de 10 min (achado) e 60 s (não achado), erro amigável (404 "CEP não encontrado", 502 "Não foi possível consultar o CEP agora. Preencha o endereço manualmente."). Os testes substituem `servico.consultar_viacep`; nada vai à internet.
- CRUD: `POST /alunos`, `GET/PUT /alunos/{id}`, `POST /alunos/{id}/inativar|reativar`, `DELETE /alunos/{id}`, `GET /alunos/{id}/vinculos`.
  - CPF: validação do domínio, único (409 com o nome de quem já tem), `sem_cpf` grava `NULL` (nunca o marcador `SEM_CPF_...`). CPF de quem paga validado. Código do aluno novo vem do contador `aluno` (`proximo_codigo`).
  - **Telefones atualizados por id** (corrige o delete-and-recreate do antigo): existentes mudam no lugar, novos entram, ausentes saem, a ordem da lista define a ordem e o marcado como principal vira ordem 1; normalização canônica `domain.telefone` (número inválido ou repetido = 422); troca de números entre dois registros não bate no índice único.
  - Endereço 1:1 (cria, atualiza e remove quando enviado todo vazio). PUT é parcial: só muda o que foi enviado (`telefones`/`endereco` ausentes = intactos).
  - **Excluir só sem vínculos** (contratos, reservas, aulas avulsas/avaliativas, cobranças); com vínculos devolve 409 orientando a inativar. Excluir apaga também foto, documentos e assinatura do disco.
- Foto: `POST/DELETE/GET /alunos/{id}/foto` (categoria `alunos`, subpasta `foto`, 4 MB, assinatura do arquivo conferida).
- Documentos: `GET/POST /alunos/{id}/documentos`, `GET .../{doc}/arquivo` (download autenticado, auditado), `DELETE .../{doc}` (categoria `documentos`, 10 MB). Documento de origem `CONTRATO_PDF` não é excluível por aqui.
- Termo de imagem: `GET /alunos/{id}/termo` (estado + texto com variáveis `{ALUNO_*}` substituídas e **escapadas**), `POST .../termo/registrar` (aceite sem imagem), `POST .../termo/assinatura-local` (canvas em data URL PNG; grava nome, documento, IP, imagem em `alunos/termo/`; marca `autoriza_imagem`), `GET .../termo/assinatura`.
- **Professor**: aluno visível só com reserva em aula dele (`escopo.filtrar_proprias` sobre `AulaSessao.profissional_id`); fora do escopo = 404 (não revela que existe). `GET /alunos/{id}/resumo` (nome, foto, status, unidade; sem CPF/telefone) e `GET /alunos/{id}/foto` aceitam `alunos.ver` **ou** `aulas.ver`. Perfil restrito nunca grava (403 em criar/editar/excluir/upload) mesmo se alguém lhe der `alunos.editar`.
- Permissões em `adicionar_regras` no `routes.py`; auditoria em toda escrita e no download de documento (`aluno.criar|alterar|inativar|reativar|excluir|foto|documento.enviar|baixar|excluir|termo.registrar|termo.assinar`). A alteração registra só o que mudou (antes/depois).

**Frontend** (`frontend/app/(app)/alunos/`, `frontend/components/alunos/`, `frontend/lib/tipos-alunos.ts`)

- `/alunos`: busca com `/` (usa o `data-busca` do `SearchInput`, já ligado à paleta), chips Ativos/Inativos/Todos com contagem, ordenação clicável, paginação, estados vazios, botão "Preencher com IA" desabilitado com tooltip.
- `/alunos/novo` e edição (diálogo na aba Dados) com o mesmo `FormAluno`: seções, máscara de CPF/telefone/CEP, "sem CPF", vários telefones com WhatsApp principal, busca de CEP via backend (`use-cep-aluno.ts`), CPF de quem paga, termo, autoriza imagem, ativo/inativo, foto com recorte e zoom.
- `/alunos/[id]`: cabeçalho (foto, nome, CPF mascarado, status, WhatsApp e e-mail), **atalhos** (Aulas, Contratos, Financeiro, WhatsApp, Evolução) e abas com **`?aba=`** na URL.
- Abas prontas: **Dados** (resumo, editar, trocar foto, inativar/reativar, excluir com confirmação digitando o nome, ou explicação do vínculo), **Documentos** (upload com arraste, lista, baixar, excluir), **Uso da imagem** (estado, registrar aceite, assinar com canvas, texto do termo em iframe isolado, botão de link por WhatsApp desabilitado = ponto de extensão).
- **Registro de abas** em `components/alunos/abas.ts` (id, rótulo, ícone, componente, permissão, `visivelProfessor`, atalho). Esqueletos "Em construção" em `components/alunos/abas-esqueleto.tsx` (Aulas, Contratos, Financeiro, WhatsApp, Evolução, Avaliações), todos com props `{ alunoId: number }`. Professor só vê Evolução e Avaliações.
- `nav.ts`: apenas a entrada de Alunos virou `planejado: false`.

## Decisões

1. **Storage**: categoria `alunos` (fotos em `alunos/foto/`, assinaturas novas em `alunos/termo/`) e `documentos` (`documentos/<aluno_id>/...`), ambas com leitura pela permissão `alunos.ver`. São os mesmos prefixos que o ETL já usa (`alunos/foto/`, `documentos/`); as assinaturas migradas ficam em `assinaturas/termo/` e são lidas pela rota do aluno (que usa o caminho do banco).
2. **Cabeçalho do Professor** pela rota `/resumo` (permissão `aulas.ver`), porque o perfil padrão Professor **não** tem `alunos.ver` (pergunta aberta da Fundação, ver dúvidas).
3. CPF completo só na ficha (`GET /alunos/{id}`); lista, busca e cabeçalho usam máscara `***.***.247-25`.
4. Excluir exige confirmação digitando o nome do aluno; com vínculos o diálogo troca para "inativar em vez de excluir".
5. Documento de contrato (`CONTRATO_PDF`) é somente leitura/baixar.
6. Inativar **não** cancela reservas futuras nem contratos (só tira o aluno das listas de ativos). A regra de cancelamento em cascata, se existir, fica para o módulo de Contratos/Agenda.
7. Sem mudança de modelo (nenhuma coluna nova; a migração não precisa de nada para este módulo).

## Pedidos ao coordenador

1. **Ligar as abas**: em `frontend/components/alunos/abas.ts` trocar `AbaAulas`, `AbaContratos`, `AbaFinanceiro`, `AbaWhatsapp`, `AbaEvolucao`, `AbaAvaliacoes` (de `abas-esqueleto.tsx`) pelos componentes `components/agenda/aba-aluno-*.tsx`, `components/financeiro/aba-aluno-financeiro.tsx` etc. (props `{alunoId: number}`).
2. **Busca da barra do topo**: o `command-palette.tsx` (core) tem `ativo = false` para busca de registros. Para ligar: chamar `GET /alunos/busca?q=` (devolve `id, nome, cpf_mascarado, telefone, status, foto_url`) e navegar para `/alunos/{id}`. O atalho `/` já foca o `input[data-busca]`.
3. **Perfil Professor**: se o Jefferson quiser que o Professor abra a ficha completa (dados cadastrais), acrescentar `alunos.ver` ao perfil padrão (o escopo por reserva já funciona). Sem isso ele vê só o cabeçalho mínimo e as abas Evolução/Avaliações.
4. **Cadastro de Profissões**: o select de profissão do aluno lê `GET /alunos/opcoes`, mas não existe CRUD de profissões no menu nem no catálogo de permissões. Pedir ao agente CADASTROS-BASE (ou criar `cadastros_profissoes`), senão o select fica vazio no sistema novo (o ETL migra as existentes).
5. **Resolvedor usuário -> profissional** (CADASTROS-BASE): o escopo do Professor depende dele; nos testes uso um resolvedor de teste.
6. **Ligar a assinatura por link** (onda de comunicação): ponto de extensão `servico.gerar_link_assinatura_termo(aluno)` (backend) e o botão desabilitado "Enviar link de assinatura" na aba Uso da imagem. Usar `core.links` (link assinado com prazo; o antigo era 30 dias) e a página pública de assinatura.
7. `hooks/use-cep.ts` (compartilhado) consulta o ViaCEP direto do navegador; o módulo usa o seu próprio `components/alunos/use-cep-aluno.ts`, que passa pelo backend. Se quiserem, o hook compartilhado pode migrar para o endpoint.
8. Ao ligar o módulo Contratos: `servico.quantidade_vinculos` já conta `Contrato`, `Reserva`, `AulaAvulsa`, `AulaAvaliativa` e `ContaReceber` para impedir exclusão.

## Dúvidas para o Jefferson

1. O Professor deve ver os **dados cadastrais** do aluno (CPF, telefone, endereço) ou só o cabeçalho e as abas de evolução e avaliação, como está agora?
2. **Inativar um aluno** deve cancelar as reservas futuras e encerrar contratos, ou só esconder o aluno das listas (como está)?
3. O texto do termo de imagem usa as variáveis do antigo (`{ALUNO_NOME}`, `{ALUNO_CPF}`, `{ENDERECO_CEP}`...). Mantemos exatamente essas?
4. A Secretária pode **excluir** aluno sem vínculos? Hoje só o Full (a Secretária pode editar e inativar).

## Como rodar

```
cd backend
uv sync
uv run python -m pytest -q tests/alunos tests/test_cobertura_rotas.py
cd ../frontend
npm install
npm run lint
npm run build
```
