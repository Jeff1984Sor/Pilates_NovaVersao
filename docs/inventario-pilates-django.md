# Inventário do sistema Pilates (Django vs FastAPI/Next.js) — somente leitura

Raiz: `C:\Users\JeffersonFernandes\Projetos\Pilates\PilatesFinal`. Abreviações: `core/` = `backend/studiopilates/core/`, `views.py` = `core/views.py`.

**Não consegui verificar:**
- O Postgres de produção (só existe o `db.sqlite3` local, antigo).
- Os arquivos systemd/nginx (não estão no repositório).
- Os valores do `.env` (só li nomes).

---

## 0. RESUMO EXECUTIVO: o que é cada camada

Não são duas camadas e sim **três**, e só uma é o sistema de produção.

| Camada | Onde | Banco | Estado |
|---|---|---|---|
| **A. Django monolito** | `core/` (views.py 6941 linhas, models.py 899, 190 `path()` em urls.py) | Postgres em produção (o scheduler usa `pg_try_advisory_lock`); SQLite só em dev | **É o sistema de uso diário** |
| **B1. "API ponte" FastAPI sobre o ORM do Django** | `api/main.py` (524 linhas) + `api/schemas.py` | **O mesmo banco e as mesmas tabelas** (`core_*`), via `django.setup()` e `from studiopilates.core import models` (api/main.py:15-22) | **Em produção.** O `deploy/deploy.sh` reinicia o serviço `pilates-api` quando `api/`, `shared/` ou `backend/app/` mudam. O README sobe com `uvicorn api.main:app`. |
| **B2. FastAPI + SQLAlchemy "limpo"** | `backend/app/` (13 módulos, alembic 0001–0005) + `frontend/` Next.js | Schema **próprio e divergente** (tabelas `aluno`, `contrato`, `plano`, `contas_receber`, `usuario`...). As do Django se chamam `core_aluno` etc. | **Protótipo paralelo, aparentemente não implantado.** Veja as evidências abaixo. |

**Evidências de que B2 e o frontend não rodam em produção:**
- `requirements.txt` não tem `sqlalchemy`, `alembic`, `python-jose`, `passlib` nem `pydantic-settings`. Todos são importados por `backend/app/core/{deps,security,config,database}.py`. Com o requirements atual o `backend/app` nem sobe.
- O último commit que mexeu em `backend/app` ou `frontend` foi de 2026-06-19 (o commit "API de integração" 872fdff/b5d3a66, em que `backend/app` só ganhou o módulo `integracao`). O de comissões (10919e8) é de 2026-06-05. O resto é de fev/2026. Já `api/` recebeu commits até 2026-10-04.
- `frontend/Dockerfile` roda `next dev`. As páginas `contratos`, `dashboard`, `financeiro` e `planos` são stubs de 14 linhas. O dashboard em `frontend/app/page.tsx` tem números fixos (128 alunos, 24 aulas, R$ 6.540).
- O PWA do aluno usa `/api/fast/aluno-app` (`web/templates/app/index.html:84`), que é o B1.

**Único ponto de contato entre B2 e o banco do Django:** `backend/app/modules/integracao/router.py:20-45` lê `core_integracaotoken` por SQL cru. Ou seja, B2 só "conversa" com o Django por esse token. É também um duplicado de `/integracao/*` que já existe em `api/main.py:211-380`.

**O que B2 tem que o Django não tem:**
- **Comissão do profissional.** Há `Profissional.comissao_percentual`, a tabela `comissao` (única por `conta_receber_id`), `ComissaoService.gerar(competencia)` em `backend/app/modules/comissoes/service.py` e a tela `frontend/app/comissoes/page.tsx`. No Django **não existe comissão**: `grep -i comiss` em views, models e forms retorna zero.
- **Gerador de agenda por contrato** (`backend/app/modules/contratos/agenda_service.py` e `scheduler.py`). Usa `WORKING_HOURS` fixo (seg–qui 7–21h, sex 7–12h), `PREFERRED_WEEKDAYS` por nº de aulas/semana, slot de 50 min e idempotência por `idempotency_key`, com testes em `backend/tests/test_agendamento_contratos.py`. O Django faz isso de outro jeito: a atendente escolhe os horários na tela `contrato_agenda` (views.py:5893).
- Auth JWT próprio com refresh e papéis (`Usuario`, `PerfilAcesso.descricao`, `require_roles("admin")`).
- Eventos de agenda, participantes e recorrência (`AgendaEvento`, `AgendaParticipante`, `AgendaRecorrencia`), `Sala`, `TipoPlano`, `Recorrencia`.
- Endpoints `/aulas/amanha` e `/aulas/amanha-professores`, `/alunos/{id}/contexto-ia`, `/proximas-aulas`, `/contrato-ativo` e `/pagamentos/abertos` (integração com agente de IA/chatbot).
- Wrappers de TotalPass e Evolution (`integracoes/*`), que são stubs.

**O que o Django tem e B2 não tem (quase tudo):**
- Contratos com assinatura digital por token.
- Termo de imagem.
- Financeiro completo: conta bancária, movimentos, fluxo de caixa, DRE, exportações.
- Receita Saúde.
- WhatsApp scheduler, comunicado geral e avisos.
- PWA do aluno.
- TotalPass webhook e sync.
- Aula avaliativa e avulsa.
- Bloqueios e horários de funcionamento.
- Evolução e avaliação com IA.
- Perfil Professor (middleware).
- Wizard e e-mail SMTP.
- Fotos, documentos e assinaturas.

**Modelos duplicados e divergentes (Django ⇄ SQLAlchemy):**
- `Aluno`: Django tem `dsNome`, `dsCPF`, `foto`, termo de imagem, `cpf_pagador_recibo`, `sem_cpf`. B2 tem `nome`, `cpf`, `observacoes`.
- `Contrato`: Django tem `valor_aula`, `valor_parcela`, `valor_total`, `modo_pagamento`, assinatura e status de assinatura. B2 tem `status` ativo/pausado/encerrado, `agenda_gerada_em` e `idempotency_key`.
- `ContasReceber`: Django tem `contrato`, `reserva`, `aluno`, `competencia`, `recibo_saude_gerado_em` e status ABERTO/PAGO/ATRASADO/CANCELADO. B2 tem `origem`, `profissional_id`, `forma_pagamento` e status aberto/pago/vencido/cancelado.
- `Plano`: Django tem `valor`, `recorrencia` e `is_avulso`. B2 tem `preco`, `tipo_plano` e `ativo`.
- `Unidade`: Django tem `capacidade` e `duracao_aula_minutos`. B2 tem `ocupacao_max`.
- B2 tem `Aula/AulaAluno`, `AgendaEvento/AgendaParticipante`. O Django tem `AulaSessao/Reserva`.

**Consequência para a migração:** o "FastAPI de verdade" ainda não existe. B2 é um esboço com outro modelo de dados. Se for adotado como base, será preciso **migrar dados** do schema `core_*` para ele, ou reescrever B2 sobre o schema atual. Reaproveitar B2 sem cuidado perde dados. O caminho de menor risco é usar B1 (ORM do Django) como ponte durante a transição.

---

## 1. MODELOS (`core/models.py`, 39 models + 1 tabela M2M)

**Regra geral dos códigos `cd*`:**
- Quase toda entidade tem um `cdXxx = IntegerField(unique=True, db_index=True)` **manual**, ao lado do `id` automático.
- É gerado em Python pelo `max(cd)+1`: `_inject_cd_value` (views.py:1627) e `BaseAutoCdForm` (forms.py:7). Também em `signals._next_cd_profissional` e em vários trechos inline.
- **Há condição de corrida** (sem lock nem sequence).
- A migração deve manter `cd*` como coluna de negócio. Os integradores externos usam `cdAluno` (`/integracao/alunos/por-codigo`).

**Cadastros e acesso**
- `PerfilAcesso` (:12): `cdPerfilAcesso` e `dsPerfilAcesso`. **O perfil "professor" é detectado por substring no nome**, em minúsculas: `"professor" in nome` (middleware.py:~93, views.py:86-91, context_processors.py).
- `Profissao` (:20).
- `Profissional` (:28):
  - `cdProfissional` (unique), `profissional`, `email`, `celular`, `crefito`, `dtNascimento`.
  - FK `cdPerfilAcesso` (PROTECT).
  - **`user` OneToOne com `auth.User` (null, SET_NULL).**
  - Os signals mantêm User⇄Profissional em sincronia (signals.py:36-78). Criar User cria Profissional com perfil "Padrao" (cd=1). Criar Profissional sem user cria User com senha inutilizável.
  - O login é o e-mail do profissional (`_sync_user_for_profissional`, views.py:1596).
- `Unidade` (:52): `capacidade` (default 0) e `duracao_aula_minutos` (50).
- `TermoUso` (:62): `dsTermoUso` em HTML com variáveis `{ALUNO_*}`.

**Aluno (:71)**
- `cdAluno` (unique) e `dsCPF` (**unique**, max 32).
- `sem_cpf=True` gera `dsCPF="SEM_CPF_<uuid16>"` no `save()` (:117).
- `clean()` valida o CPF (`validators.validar_cpf`) a menos que `sem_cpf`.
- **Formato do CPF inconsistente.** O TotalPass grava `xxx.xxx.xxx-xx` (views.py:4312-4366). O PWA compara só dígitos, varrendo **todos** os alunos em Python (api/main.py:262-268).
- Campos: `status` ATIVO/INATIVO, `estado_civil`, FKs `cdProfissao`, `cdUnidade` (PROTECT) e `cdTermoUso`, `cpf_pagador_recibo`, `autoriza_imagem`.
- **Arquivos:** `foto` (ImageField → `media/alunos/`) e `termo_assinatura_imagem` (ImageField → `media/assinaturas_termo/`).
- Campos de assinatura do termo: `termo_aceite_em`, `termo_assinatura_nome`, `termo_assinatura_documento`, `termo_assinatura_ip`, `termo_assinado_em`.
- `cdEndereco` é um OneToOne para `EnderecoAluno`, e `EnderecoAluno.cdAluno` é outro OneToOne para `Aluno`. **FK circular**, com cuidado na ordem de carga.
- `TelefoneAluno` (:150): FK CASCADE. Vários telefones por aluno.

**WhatsApp / documentos**
- `AlunoWhatsappMessage` (:170): histórico enviado/recebido, `response_payload` em texto.
- `AlunoDocumento` (:190): `arquivo` FileField → `media/alunos/documentos/`. Origem UPLOAD ou CONTRATO_PDF.
- `WhatsappAgendamentoLog` (:212): `dedupe_key` **unique** (220 chars). É o que impede o envio duplicado do scheduler.
- `WhatsappConfiguracao` (:760): OneToOne com `Unidade`. Credenciais Evolution/Wasender (`evolution_url`, `evolution_usuario`, `evolution_senha`, `evolution_instance`), toggles e horários por tipo de aviso, 7 templates de texto com valores padrão em português (inclui chave Pix/CNPJ fixo no `template_mensalidade_atraso`) e `variaveis_template` JSON.

**Agenda**
- `TipoServico` (:230).
- `HorarioStudio` (:238): grade antiga por dia da semana. `capacidade` pode ser null.
- `HorarioFuncionamento` (:262): `unique_together (unidade, tipoServico, diaSemana, horaInicio, horaFim)`, mais M2M `tipos_servico`. O campo `tipoServico` é legado; o M2M é o atual. Um horário sem serviço vale para todos.
- `BloqueioAgenda` (:322): pontual ou recorrente por dia da semana, por unidade/serviço/profissional. `clean()` exige horaFim > horaInicio.
- **`AulaSessao` (:522)**:
  - `capacidade` null significa "usar `unidade.capacidade`" (`capacidade_efetiva()`, :532).
  - `profissional` é null/SET_NULL (aula TotalPass vem sem profissional).
  - **Sem unique** em (unidade, serviço, profissional, data, hora). A deduplicação é por `.filter().first()` ou `get_or_create` no código, então podem existir duplicatas.
- **`Reserva` (:539)**:
  - `unique_together (aluno, aulaSessao)`.
  - Status: RESERVADA, CONCLUIDA, FALTOU_AVISOU, FALTOU_SEM_AVISAR, CANCELADA, PENDENTE.
  - FKs opcionais `pacote_avulso` (AulaAvulsa) e `aula_avaliativa`.
  - Campos `confirmada_em`, `desmarcada_em`, `reposicao_ate`.
  - **`clean()` (:562) valida a capacidade só quando status=RESERVADA**, contando as reservas RESERVADAS da sessão. **Não é imposta no banco**, só em `full_clean()`.
- `AulaAvulsa` (:392): pacote de aulas avulsas (`quantidade`, `valor_aula`, `valor_total`, `dtInicio/Fim`).
- `AulaAvaliativa` (:415): tipo AVALIATIVA/TOTALPASS/WELLHUB e status AGENDADA/REALIZADA/CANCELADA/CONVERTIDA. Tem ficha de avaliação em 4 campos de texto e FK opcional para `Contrato`.
- `EvolucaoAluno` (:600) e `AvaliacaoAluno` (:610): FK para `Reserva` (CASCADE) e `Profissional` (PROTECT). **Evoluções estão presas à reserva**, e apagar uma reserva apaga a evolução.
- `ModeloEvolucao` (:589).
- `AlunoAppCodigo` (:577): OTP de 6 dígitos do PWA, `expira_em` e `usado`.

**Plano / Contrato**
- `Plano` (:300): `valor` (mensal), `aulas_por_semana`, `duracao_meses`, `recorrencia`, `is_avulso`, FKs `cdTipoServico` (PROTECT), `categoria_receita`, `subcategoria_receita` e `modeloContrato` (SET_NULL).
- `ModeloContrato` (:734): `conteudo_html` com variáveis `{...}`.
- **`Contrato` (:351)**:
  - `cdContrato`, FKs PROTECT para aluno, plano, unidade e profissional.
  - `recorrencia`, `modo_pagamento`, `valor_aula` (null), `valor_parcela`, `valor_total`, `dtInicioContrato`, `dtFimContrato`.
  - `status` NAO_ASSINADO/ASSINADO/ASSINADO_DIGITALMENTE e campos `assinatura_*`.
  - **Arquivo:** `assinatura_imagem` (ImageField → `media/assinaturas/`).
  - **Não há estado "ativo/encerrado"**: vigência é só por datas (contratos_gestao, views.py:5809).

**Financeiro**
- `Fornecedor`, `Categoria` (RECEITA/DESPESA), `Subcategoria`.
- `ContasPagar` (:491): status AGENDADO/PAGO/ATRASADO/CANCELADO, recorrência MENSAL/SEMANAL/ANUAL com `recorrencia_quantidade`, `motivo_cancelamento`. **Arquivo:** `comprovante` → `media/comprovantes/contas_pagar/`.
- **`ContasReceber` (:671)**:
  - FKs opcionais `contrato` (PROTECT), `reserva` (SET_NULL) e `aluno` (PROTECT, só para lançamento avulso).
  - Campos: `competencia` ("YYYY-MM" ou "YYYY-WW"), `dtVencimento`, `dtPagamento`, `descricao`, `recibo_saude_gerado_em`.
  - O aluno é resolvido por `_conta_receber_aluno` (views.py:5379): contrato → reserva → aluno.
  - **`ATRASADO` é calculado na exibição**, não persistido (views.py:2528/3637/3681).
  - **Sem FK direta para Aluno nas contas de contrato**, só via contrato.
- `ContaBancaria` (:703) e `MovimentoConta` (:716): ENTRADA/SAÍDA. **Arquivo:** `comprovante` → `media/comprovantes/movimentos/`.

**Configurações de integração**
- `EmailConfiguracao` (:745): host/porta/usuário/**senha em texto puro**.
- `ReceitaSaudeConfig` (:623): registro único (usa `.order_by("-id").first()`).
- `TotalpassConfiguracao` (:652): OneToOne com `Unidade`; `partner_api_key`, `place_api_key` e `webhook_token` em texto puro.
- `TotalpassWebhookEvent` (:635): payload JSON de auditoria.
- `IntegracaoToken` (:878): token `pilates_<urlsafe32>` gerado no `save()`. **É lido por SQL cru pelo B2.**

**Arquivos no disco (resumo, caminhos sob `MEDIA_ROOT = PilatesFinal/media`):**

| Campo | Pasta |
|---|---|
| `Aluno.foto` | `media/alunos/` |
| `Aluno.termo_assinatura_imagem` | `media/assinaturas_termo/` |
| `AlunoDocumento.arquivo` | `media/alunos/documentos/` |
| `Contrato.assinatura_imagem` | `media/assinaturas/` |
| `ContasPagar.comprovante` | `media/comprovantes/contas_pagar/` |
| `MovimentoConta.comprovante` | `media/comprovantes/movimentos/` |

Copiar `media/` junto com o banco é obrigatório. O arquivo `media/alunos/foto-aluno.jpg` está **versionado no git**, apesar de `media/` constar no `.gitignore`.

---

## 2. FUNCIONALIDADES POR ÁREA

Mapa geral de `core/urls.py`:
- Cerca de 60 rotas de CRUD genérico passam por 4 funções reutilizadas: `list_view` (views.py:2134), `create_view` (:4859), `edit_view` (:4978) e `delete_view` (:5101). Elas são ligadas por `lambda` em urls.py.
- Essas funções têm `if model is models.X` espalhados com a lógica de negócio de cada cadastro.

**2.1 Alunos e ficha**
- **Rotas:** `cadastros/alunos/` (lista, criar, editar, excluir), `cadastros/alunos/<pk>/ficha/` (`aluno_detail`, views.py:650-817), `autoriza-imagem`, `documentos/*`, `whatsapp`, `evolucoes/*`, `avaliacoes/*`.
- **Ficha:** uma única página de **2958 linhas** (`web/templates/alunos/detail.html`) com abas contratos, agenda, financeiro, documentos, WhatsApp, evoluções e termo.
- **Regras:**
  - A ficha chama `services.concluir_aulas_passadas()` a cada abertura.
  - `_build_reserva_slots` (views.py:427) **cria `AulaSessao` durante um GET** para oferecer horários de remarcação (próximos 60 dias).
  - `_sync_aluno_address` (:1638) e `_sync_aluno_phones` (:1660) fazem **delete-and-recreate** dos telefones a cada salvamento. Os `cdTelefone` mudam.
  - O professor só vê ficha de aluno que tenha reserva em aula dele (middleware `POR_ALUNO`).
- **Risco:** `aluno_detail` (:650) **não tem `@login_required`**. Veja a seção 9.

**2.2 Agenda (grade e operacional)**
- **Rotas:** `agenda/semana/` (`aulas_semana`, views.py:3731), `agenda/aulas/` (`aulas_list`, :3845), `agenda/aulas/operacao/` (`aulas_operacao_api`, :4061; JSON do painel operacional) e `agenda/aulas/reservas/<id>/{evolucoes,avaliacoes,cobranca,historico,status,remarcar,excluir,whatsapp}`.
- **Cadastros da agenda:** horários do studio (`gerar_horarios_studio`, :1704), horários de funcionamento (:1784, :1846) e bloqueios (:1925, :2020).
- **Regras:**
  - Status exibido (`_map_status`, :3988): RESERVADA/PENDENTE→aguardando_chegar (ou `em_aula` se agora está entre início e fim), CONCLUIDA→finalizada, FALTOU_*→faltou, CANCELADA→remarcada.
  - `aula_remarcar_api` (:4714) faz `get_or_create` de `AulaSessao` e checa a capacidade manualmente. **Apaga a sessão antiga se ficar sem reservas.**
  - `aula_reserva_excluir` (:4699) apaga a sessão se ficar vazia.
  - `AULA_INTERVALO_MINUTOS = 10` (views.py:309) define o intervalo entre slots.
  - `_generate_slots_for_date` (:415) gera os slots de uma data a partir das janelas.
  - `_is_slot_blocked` (:396) aplica os bloqueios.

**2.3 Aulas / Reservas**
- Edição da aula do aluno em `reservas/<id>/editar-aula/` (`aluno_reserva_editar`, :1363, permite trocar o professor).
- Exclusão em lote em `cadastros/alunos/<id>/reservas/excluir/` (:5151).
- **Aula avulsa** (:1083-1362): cria um `AulaAvulsa` e depois agenda os slots. Para cada aula cria `Reserva` e, **se `valor_aula > 0`, uma `ContasReceber` com `reserva=`** (views.py:1297). TotalPass/WellHub têm valor 0 e não geram cobrança.
- **Aula avaliativa** (:1404-1513): cria `AulaAvaliativa`, `AulaSessao` e `Reserva` sem cobrança. A "ficha" é salva em :1485. "Converter" só muda o status para CONVERTIDA e **não cria contrato**.

**2.4 Contratos e assinatura digital**
- **Rotas:** `contratos/`, `contratos/gestao/` (:5809), `contratos/<pk>/agenda/` (:5893), `contratos/modelos/*` (editor HTML), `contratos/<pk>/{enviar-email,whatsapp,assinar-local,documento,assinatura}`.
- **Criação** (`create_view`, views.py:4880-4915), na ordem:
  1. Calcula preços (`_contrato_precificacao`).
  2. `services.criar_contrato_e_contas` (parcelas).
  3. Gera o PDF e salva como `AlunoDocumento`.
  4. Envia por e-mail (`enviar_contrato_para_assinatura`).
  5. Envia por WhatsApp (link e PDF).
  6. Redireciona para a escolha de agenda.
- **Assinatura pública:** link `contratos/assinar/<token>/` (view `contrato_assinar`, :6809). Detalhes na seção 2.15.
- **Exclusão de contrato** (`delete_view`, :5101-5146): apaga as `ContasReceber` do contrato. Apaga as reservas do aluno **no período do contrato, na unidade e no serviço do plano**. Apaga as sessões que ficarem sem reserva. Exige `confirm_delete=1`. **É uma exclusão destrutiva por período, não por vínculo.** Reservas não têm FK para contrato, então o vínculo é inferido por datas.
- Renderização de variáveis do contrato: `services.render_contrato_html` (services.py:100+). PDF: `render_contrato_pdf` usa **WeasyPrint se existir, senão ReportLab**. `weasyprint` **não está em requirements.txt**, então produção provavelmente usa o fallback ReportLab (texto sem formatação).

**2.5 Planos**
- Rotas `cadastros/planos/*`, incluindo `duplicar` (`duplicar_view`, :5066).
- Os planos avulsos têm `is_avulso=True`. Existe um plano de valor 0 "Aula Avulsa Total Pass / WellHub" (commit 0c2e050).

**2.6 Financeiro**
- **Contas a receber:**
  - Lista (CRUD genérico). `baixar` (:5175), `excluir` (:5210), `cobrar-whatsapp` (:5234), `recibo` PDF (:5533), `lancar avulsa` (:5402) e exportar PDF/Excel por aluno (:5421/:5469).
  - **`baixar` e `excluir` aceitam GET**, ou seja, uma ação que altera dados por link (sem proteção CSRF).
- **Contas a pagar:** lista e filtros (:2489, :2575), `pagar` com comprovante (:5281), `cancelar` com motivo (:5304), recorrência que cria N lançamentos (views.py:4905-4925) e exportar Excel/PDF (:3622/:3662).
- **Conta bancária:** `conta_bancaria_view` (:2840), criar conta (:3149), movimento com comprovante (:3164).
- **Fluxo de caixa:** `_build_fluxo_caixa_data_for_period` (:2644), mais exportações Excel (:2948) e PDF (:3018). Considera receitas e despesas **por vencimento**, excluindo CANCELADO.
- **DRE:** `dre_view` (:3178) e `dre_relatorio` (:3224), com exportações Excel (:3361) e PDF (:3458). Usa **receitas pagas por `dtPagamento`**, `deducoes=0`, `custo_direto=0`. Agrupa por plano, categoria e subcategoria via `contrato__cdPlano__*`. **Lançamentos avulsos e de reserva (sem contrato) ficam sem plano/categoria na DRE.**
- Bloqueado para professor via `_professor_block`.
- Há um bloco duplicado (`despesas_por_subcategoria` repetido 3 vezes em :3224-3300), que é inofensivo.

**2.7 Receita Saúde (arquivo CSV)**
- Módulo `core/receita_saude.py`:
  - CSV com `;`, CRLF, sem cabeçalho, até 1000 linhas.
  - Código de rendimento `R01.001.001`, 16 colunas.
  - Valida CPF do aluno e do pagador, status PAGO, data e valor > 0, e todos os pagamentos no mesmo ano.
  - **Se qualquer linha tiver erro, não gera nada.** Descrição sem acento e sem `;`.
- Views: configuração em views.py:6165, geração do arquivo em :6192 (marca `recibo_saude_gerado_em`; para refazer é preciso "liberar") e `cpf_pagador` em :6245.
- Tem 14 testes.

**2.8 Evoluções e avaliações (IA)**
- CRUD de evolução/avaliação na ficha e na gaveta da operação (views.py:1514-1594 e :4423-4600). Exportação em PDF/Excel (:5587/:5620).
- **A IA é a OpenAI** (commit 754c100, "IA: troca Gemini por OpenAI"). views.py:31 importa `shared.ai.openai_client`. O `shared/ai/gemini_client.py` ficou como código morto, mas o `google-generativeai` continua no requirements.
- `improve_evolution_text` é chamada em `_enriquecer_evolucao_response` (:4495). A chamada de IA é **síncrona dentro da requisição**.

**2.9 WhatsApp**
- **Provedor:**
  - `core/whatsapp_service.py`. `EvolutionClient` fala com **WasenderAPI** (Bearer, endpoint único `send-message`) ou **Evolution API** (header `apikey` e `/message/sendText/{instancia}`).
  - O modo Evolution só é escolhido quando `WhatsappConfiguracao.evolution_instance` está preenchido.
  - `send_document` usa uma URL pública de mídia: o PDF do contrato é servido por `contratos/pdf/<token>/`.
  - Toda mensagem enviada grava `AlunoWhatsappMessage`.
- **Tela de configuração por unidade** (views.py:6317-6513): botões "enviar agora" para aluno, professor, renovação, aniversário, vencimento, atraso e 3 meses. Histórico em :6514. Aviso ao aluno com preview e envio unitário em :6587-6694. **Comunicado geral** (:6695-6770): seleção de alunos e envio um a um via AJAX.
- **Mensagens específicas:** contrato (link e PDF), termo de imagem (documento e link de assinatura), documento do aluno, cobrança de fatura, código OTP do app, confirmação de contrato/termo assinados.

**2.10 E-mail SMTP**
- Duas fontes: `EmailConfiguracao` no banco (`enviar_contrato_para_assinatura`, services.py: usa a mais recente ativa) e as variáveis `EMAIL_*` do settings (fallback do Django).
- **Só o e-mail de assinatura de contrato** usa e-mail, com `fail_silently=True`.
- Tela de configuração: views.py:6139.

**2.11 TotalPass**
- **Webhook** `integrations/totalpass/webhook/` (`totalpass_webhook`, views.py:4837), `@csrf_exempt`, POST.
- **Comando** `sync_totalpass [--date]`: autentica em `booking-api.totalpass.com` (`/partner/auth`) e lê `/partner/slot`.
- **Processamento** (`_process_totalpass_payload`, views.py:4305):
  - Grava `TotalpassWebhookEvent`.
  - Respeita `somente_dia` (descarta se não for hoje).
  - Resolve o serviço por título (`iexact`, depois `icontains`).
  - Acha o aluno pelo CPF, **criando-o automaticamente** se `criar_aluno_automatico`.
  - Faz `get_or_create` da `AulaSessao` **sem profissional** e com capacidade da unidade.
  - Status canceled/cancelled/inactive → CANCELADA.
  - Verifica a capacidade antes de reservar.
- Configuração por unidade na tela `configuracoes/totalpass/` (views.py:6774), **sem `@login_required`**.

**2.12 App do aluno (PWA)**
- **Páginas Django (públicas):** `/app/`, `/app/manifest.json`, `/app/sw.js` e `/app/icon.svg` (views.py:6262-6302). O service worker é um stub sem cache.
- **API (FastAPI B1, `api/main.py:289-395`)**, prefixo `/aluno-app` exposto como `/api/fast/aluno-app`:
  - `POST login/solicitar`: CPF → gera OTP de 6 dígitos (`secrets.randbelow`), válido por 10 minutos, enviado por WhatsApp.
  - `POST login/confirmar`: CPF + OTP → JWT HS256 assinado com `DJANGO_SECRET_KEY`.
  - `GET me`, `GET aulas` (futuras, exceto CANCELADA), `POST aulas/{id}/confirmar` (grava `confirmada_em`), `POST aulas/{id}/desmarcar` (cancela e grava `reposicao_ate = data da aula + 30 dias`).
- **Riscos:**
  - **O JWT do aluno não tem `exp`** e nunca expira.
  - O OTP não tem limite de tentativas nem de pedidos.
  - A resposta de `solicitar` distingue "CPF não encontrado" (enumeração de CPFs).
  - O JWT do staff (`/api/auth/token`) também não expira.
  - `reposicao_ate` é gravado, mas **nenhuma tela reagenda a reposição**. O app só desmarca e não repõe.

**2.13 Termo de imagem / assinatura do aluno**
- **Rotas:** `termo-imagem/{registrar,documento,whatsapp,assinar-local,enviar-assinatura}` por aluno (views.py:855-947) e a página pública **`termos/assinar/<token>/`** (`termo_assinar`, :949).
- A assinatura é um canvas em PNG base64 (data URL). Grava imagem, nome, documento, IP (`REMOTE_ADDR`), `autoriza_imagem=True` e `termo_assinado_em`, e confirma por WhatsApp.
- Token: `TimestampSigner(salt="termo-assinatura")`, validade de **30 dias** (`services.validar_token_termo`).
- Comando `set_termo_imagem` carrega o texto padrão do termo da Mayris no banco.

**2.14 Cadastros auxiliares**
- Perfis de acesso, profissões, unidades, tipos de serviço, fornecedores, categorias, subcategorias, tokens de integração, modelos de contrato, modelos de evolução, termos de uso.
- Editores HTML em `termos_*` (views.py:2392-2438) e `modelos_contrato_*` (:2345-2391).

**2.15 Wizard**
- `wizard/step1..5` (views.py:5668-5808): extração de documento e comprovante de endereço por **IA (OpenAI)**, criação de aluno, endereço, termo e contrato. Guarda estado em `request.session`.
- Tem lógica duplicada com `create_view`.
- O step 1 compara `dsCPF` literal sem normalizar.

**2.16 Configurações, perfil, senha**
- `perfil/` reaproveita `edit_view` para o `Profissional` do usuário (views.py:543).
- `conta/trocar-senha/` usa as views prontas do Django.
- Django Admin em `/admin/` com 20 models registrados (admin.py). Verifique se está exposto em produção.

**2.17 Acesso do professor (`core/middleware.py`)**
- `ProfessorAccessMiddleware` (settings.py MIDDLEWARE). Para usuário não-superuser cujo Profissional tem perfil contendo "professor": **nega por padrão** toda rota não listada.
- `ROTAS_LIVRES`: dashboard (redireciona para agenda), aulas_list, aulas_semana, aulas_operacao_api, evolucao_enriquecer_api, perfil, senha, login/logout e rotas públicas.
- `POR_RESERVA`, `POR_ALUNO`, `POR_EVOLUCAO` e `POR_AVALIACAO` checam se a reserva/aluno/evolução é de uma aula do próprio professor.
- Resposta de negação: 403 JSON para APIs, ou redirect com mensagem.
- Complementado por `_professor_block` e `_admin_only_models` dentro das views, e por `_aplica_filtro_professor` na agenda.
- Tem 11 testes (`test_acesso_professor.py`). **Rota nova nasce bloqueada.**

### ROTAS PÚBLICAS / SEM LOGIN (as mais arriscadas de migrar)

| Rota | View | Autenticação hoje | Observações |
|---|---|---|---|
| `contratos/assinar/<token>/` | views.py:6809 | `TimestampSigner(salt="contrato-assinatura")`, **7 dias** | Aceita o POST com nome, documento e PNG base64. Grava `assinatura_*` (IP, imagem), muda o status para ASSINADO_DIGITALMENTE e manda WhatsApp. **O token depende da `SECRET_KEY` do Django.** Mudar a chave invalida os links em circulação. |
| `contratos/pdf/<token>/` | views.py:6878 | mesmo token | O GET **regrava o `AlunoDocumento`** (efeito colateral). É a URL que o provedor de WhatsApp baixa. |
| `termos/assinar/<token>/` | views.py:949 | `TimestampSigner(salt="termo-assinatura")`, 30 dias | Pode ser assinado de novo? Não: bloqueia se `termo_assinado_em`. |
| `integrations/totalpass/webhook/` | views.py:4837 | Header `X-Totalpass-Token`, **opcional**: se nem a config nem `TOTALPASS_WEBHOOK_TOKEN` tiverem token, **aceita qualquer POST**. | `@csrf_exempt`. Cria alunos, sessões e reservas. |
| `app/`, `app/manifest.json`, `app/sw.js`, `app/icon.svg` | views.py:6262-6302 | nenhuma (estáticos) | |
| `/api/fast/aluno-app/*` (B1) | api/main.py:289-395 | CPF+OTP→JWT sem expiração | |
| `/api/fast/integracao/*` (B1) | api/main.py:211-380 | `X-API-Key` ou Bearer = `IntegracaoToken` ativo | Atualiza `ultimo_uso`. Inclui `POST whatsapp-mensagens` (**escreve** no banco). |
| `/api/auth/token` (B1) | api/main.py | usuário/senha do Django | JWT sem `exp`. |
| `/login/`, `/logout/` | views.py:525/538 | | |

**Sem `@login_required` por esquecimento (verificar; potencialmente grave):**
- `core/urls.py` liga o CRUD genérico por `lambda`, sem decorator, e `list_view`, `create_view`, `edit_view` e `delete_view` não checam `is_authenticated`. Isso cobre `cadastros/*` (alunos, profissionais, planos, unidades, perfis, tokens de integração, fornecedores), `financeiro/contas-receber/*`, `contas-pagar/criar|editar|excluir`, `contratos/`, `contratos/criar|editar|excluir`, `reservas/<pk>/editar|excluir`, `agenda/aulas/criar|editar|excluir`, entre outros.
- Também sem decorator: `aluno_detail` (views.py:650), `aulas_list` (:3845) e `totalpass_config_view` (:6774, mostra e grava as chaves do TotalPass).
- O middleware só restringe quem **está logado como professor**. Não exige login. Não há `LoginRequiredMiddleware` no settings.
- Não executei o servidor, mas pela leitura **um visitante anônimo parece conseguir listar, criar, editar e apagar cadastros, inclusive `tokens-integracao` e `profissionais`**. **Confirmar em produção antes da migração e corrigir.** O novo sistema não deve herdar esse comportamento.

---

## 3. INTEGRAÇÕES EXTERNAS E SEGREDOS

| Integração | Onde fica a credencial | Código |
|---|---|---|
| **WasenderAPI** (WhatsApp) | `.env` (`WASENDER_API_TOKEN`, `WASENDER_API_URL`, `WASENDER_MEDIA_URL`) **e** `WhatsappConfiguracao.evolution_url/evolution_senha` por unidade (banco, texto puro) | `core/whatsapp_service.py` |
| **Evolution API** | `.env` (`EVOLUTION_BASE_URL`, `EVOLUTION_TOKEN`, `EVOLUTION_INSTANCE`) e o banco (`evolution_*`) | idem |
| **TotalPass** | banco (`TotalpassConfiguracao.partner_api_key`, `place_api_key`, `webhook_token`, texto puro) com fallback `.env` (`TOTALPASS_WEBHOOK_TOKEN`, `TOTALPASS_UNIDADE_ID`, `TOTALPASS_BOOKING_BASE_URL`) | `core/totalpass_service.py`, views.py:4188-4420 |
| **SMTP** | banco (`EmailConfiguracao.senha`, texto puro) com fallback `.env` (`EMAIL_BACKEND/HOST/PORT/HOST_USER/HOST_PASSWORD/USE_TLS`, `DEFAULT_FROM_EMAIL`) | services.py |
| **OpenAI** (IA: wizard e evolução) | `.env` (`OPENAI_API_KEY`, `OPENAI_MODEL`) | `shared/ai/openai_client.py`, `shared/config.py` |
| **Gemini** (legado, sem uso nas views) | `.env` (`GEMINI_API_KEY`, `GEMINI_MODEL`) | `shared/ai/gemini_client.py` |
| **Receita Federal** | Nenhuma API: só gera CSV para importação manual no e-CAC | `core/receita_saude.py` |
| **Integradores externos** (chatbot/agente) chamando a API | banco (`IntegracaoToken`, tela "Tokens de Integração") e `INTEGRACAO_API_KEYS` (só no B2) | api/main.py:211+ |

**Variáveis de ambiente, só os nomes:**
- **Django/geral:** `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `SITE_BASE_URL`.
- **E-mail:** `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`.
- **WhatsApp:** `EVOLUTION_BASE_URL`, `EVOLUTION_TOKEN`, `EVOLUTION_INSTANCE`, `WASENDER_API_URL`, `WASENDER_API_TOKEN`, `WASENDER_MEDIA_URL`, `WHATSAPP_SCHEDULER_ENABLED`, `WHATSAPP_BATCH_PAUSE_SECONDS`.
- **TotalPass:** `TOTALPASS_WEBHOOK_TOKEN`, `TOTALPASS_UNIDADE_ID`, `TOTALPASS_BOOKING_BASE_URL`.
- **IA:** `OPENAI_API_KEY`, `OPENAI_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`.
- **Só no B2 (`backend/app/core/config.py`):** `ENV`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `ALGORITHM`, `CORS_ORIGINS`, `TOTALPASS_BASE_URL`, `TOTALPASS_API_KEY`, `ROOT_PATH`, `STORAGE_DIR`, `RATE_LIMIT_PER_MINUTE`, `INTEGRACAO_API_KEYS`.
- **Frontend:** `NEXT_PUBLIC_API_URL`.

**Problemas de segurança observados (sem reproduzir valores):**
1. `settings.py:106-109` tem um **valor padrão fixo para `WASENDER_API_TOKEN`** (um token real no código-fonte, versionado). Esse token deve ser considerado vazado e rotacionado.
2. `.env` está **versionado no git** (`git ls-files` retorna `.env`), apesar de constar no `.gitignore`. Também estão versionados `db.sqlite3` e `media/alunos/foto-aluno.jpg`. O `.env` local não contém `DJANGO_SECRET_KEY` (usa `SECRET_KEY`, nome que só o B2 lê). Como o código Django cai no valor padrão `"unsafe-dev-secret"` quando a variável falta, **confirme que o servidor define `DJANGO_SECRET_KEY`**. Os tokens de contrato/termo e os JWTs derivam dela.
3. `DEBUG` tem padrão `True` e `ALLOWED_HOSTS` tem padrão `*`.
4. Credenciais de SMTP, Wasender/Evolution e TotalPass ficam **em texto puro no banco**. Ao migrar, ou se mantém o mesmo esquema ou se criptografa de uma vez.
5. Há dados do negócio fixos no código: CNPJ e chave Pix nos templates padrão de WhatsApp (models.py, `template_mensalidade_atraso`); texto do contrato e do termo nos comandos `set_modelo_contrato` e `set_termo_imagem`; nome "Mayris" no manifest, mensagens e deploy.

---

## 4. TAREFAS AGENDADAS / BACKGROUND

1. **Scheduler de WhatsApp** (`core/whatsapp_scheduler.py`):
   - **APScheduler `BackgroundScheduler`** (thread dentro do processo web), disparado em `CoreConfig.ready()` (apps.py:10-12 → `start_scheduler()`, whatsapp_scheduler.py:657).
   - Job `whatsapp_sistema_mensagens` com **CronTrigger a cada 5 minutos** (`minute="*/5"`), fuso America/Sao_Paulo, `coalesce=True`, `max_instances=1`, `misfire_grace_time=300`.
   - Liga-se por `WHATSAPP_SCHEDULER_ENABLED` (padrão True) e **não inicia** em `migrate`, `collectstatic`, `check`, `shell`, `test` e similares (`_SKIP_COMMANDS`, :21).
   - **Lock entre workers:** `pg_try_advisory_lock(91437251)` no início de `_run_jobs` (:604-609). **É específico de Postgres; em SQLite o job falha.** Com N workers do gunicorn, cada um tem um scheduler, mas só um executa por vez.
   - Para cada `WhatsappConfiguracao` (uma por unidade), se `now.time() >= horario_aviso_*`, envia (todos com dedupe por `WhatsappAgendamentoLog.dedupe_key = tipo:unidade:data:destinatário`):
     - Lembrete de aula para amanhã (aluno), agrupado por aluno (:198) — padrão 19:00.
     - Agenda do professor (:359) — 18:00.
     - Renovação de contrato: contratos ASSINADOS cujo `dtFimContrato` é daqui a 7 dias (:416) — 10:00.
     - Aniversário (:526), vencimento amanhã (:540), atraso (:562, deduplicado **por semana**, usando a segunda-feira como referência) e 3 meses (:587, contrato iniciado há exatos 90 dias).
   - Pausa de `WHATSAPP_BATCH_PAUSE_SECONDS` (padrão 5 s) entre envios, até 3 tentativas por envio, e **aborta o lote se a sessão do WhatsApp cair** (`_is_session_down`, :72). Opcionalmente envia ao gestor um resumo do lote (`acompanhar_envios`).
   - Os envios são **sequenciais e síncronos**, com `sleep`. Um lote grande segura a thread por minutos.
   - Se `now.time()` já passou do horário, a próxima rodada de 5 minutos envia o que faltou. Por isso a deduplicação é essencial.
2. **`concluir_aulas_passadas`** (`services.py:329`): marca como CONCLUIDA toda reserva RESERVADA/PENDENTE cuja aula já terminou (data < hoje, ou hoje com `horaFim <= agora`).
   - **Não é agendada.** É chamada **dentro de 4 views de leitura** (views.py:651 ficha, :3733 semana, :3846 lista, :4063 operação), então um GET altera dados. Existe também o comando `manage.py concluir_aulas_passadas`, mas nada o agenda, até onde se vê no repositório.
   - Ao migrar, vira um job real (cron/APScheduler) que não pode depender de alguém abrir a tela. Reservas passadas não tratadas viram "realizada" automaticamente (commit 6e92ce8).
3. **`sync_totalpass [--date]`** (management command): puxa os slots do dia e processa. **Nada o agenda no repositório.** A sincronização efetiva é pelo webhook; confirme no servidor se há cron.
4. **Outros comandos:**
   - `recalcular_contratos [--apply] [--id]`: recalcula `valor_aula/parcela/total` com a regra atual (dry-run por padrão).
   - `set_acesso_professor <nomes> [--simular]`: atribui o perfil "Professor".
   - `set_modelo_contrato` e `set_termo_imagem`: carregam os textos padrão.
   - `backend/scripts/seed_admin.py` (B2).
5. **B2:** `contratos/scheduler.py` não é job, é só cálculo de slots.
6. **Deploy:** `deploy/deploy.sh` roda `git pull`, `manage.py check`, `migrate --noinput`, `collectstatic` e `systemctl restart pilates-web` (e `pilates-api` se `api/`, `shared/` ou `backend/app/` mudaram). O site é `https://mayris.mayacorp.com.br`, na VPS via ssh alias `flicsales`. **Os arquivos de unit do systemd e o nginx não estão no repositório.** Precisam ser inventariados no servidor (quantos workers, quem serve `/media/`, como `/api/fast/` chega ao uvicorn).

---

## 5. REGRAS DE NEGÓCIO CRÍTICAS (funções exatas)

**Preço e contrato**
- `_contrato_precificacao(plano, valor_aula)` (views.py:176):
  - `valor_plano` é o **valor MENSAL**.
  - `valor_parcela = valor_plano` e `valor_total = valor_plano × duracao_meses` (mínimo 1 mês).
  - **`valor_aula = round_half_up(valor_plano / (aulas_por_semana × 4), 2)`**, ou `None` se `aulas_por_semana == 0`. O valor por aula é só informativo.
  - Contrato é **sempre MENSAL** (`recorrencia = "MENSAL"` fixo). O argumento `valor_aula` recebido é ignorado.
  - O `edit_view` recalcula tudo ao salvar (views.py:5004-5030), sobrescrevendo edições manuais de valores. O comando `recalcular_contratos` replica a regra.
- `_aula_avulsa_precificacao` (:197): `valor_base = valor_aula informado ou valor do plano`; `valor_total = valor_base` (**não multiplica pela quantidade**; confirme a intenção). Recorrência padrão SEMANAL.
- `dtFim` da aula avulsa (views.py:1105-1108): `+quantidade meses` (MENSAL) ou `+7×quantidade dias`.

**Parcelas**
- `services.gerar_parcelas(valor, inicio, fim, meses, recorrencia)` (services.py:10):
  - **MENSAL:** `max(duracao_meses, 1)` parcelas; o vencimento de cada uma é `inicio + idx meses` com **o dia limitado a 28** (`min(dia, 28)`); competência `YYYY-MM`.
  - **SEMANAL:** uma parcela a cada 7 dias entre início e fim; competência `ISOANO-SEMANA`.
  - Em `create_view` o contrato é sempre MENSAL, então a ramificação semanal é praticamente código morto para contratos (vale para aula avulsa por reserva).
- `services.criar_contrato_e_contas` (:36): transação atômica: `Contrato` + `ContasReceber` de todas as parcelas.
- Há uma cópia de `_add_months` em views.py:1686 (também limita o dia a 28).

**Geração da agenda do contrato**
- `contrato_agenda` (views.py:5893):
  - Exige **exatamente `aulas_por_semana` horários distintos, um por dia da semana**.
  - Valida o horário contra os slots calculados de `HorarioFuncionamento` ativo menos bloqueios e lotação.
  - Para cada data entre início e fim naquele dia da semana: pula bloqueios, faz `get_or_create` de `AulaSessao` do **serviço do plano** e cria a `Reserva` via `services.create_reserva` (que roda `full_clean`, logo checa a capacidade).
  - Falha de vaga vira "conflito" informativo; **não desfaz** as demais.
  - Contrato `SEMANAL` limita a agenda a 4 semanas (`+27 dias`) e 1 aula/semana (:5894-5898).
  - Ao reutilizar uma sessão existente, **sobrescreve o profissional dela** (`aula.profissional_id = prof_id`), o que afeta outros alunos da mesma sessão.
- `services.reservar_aulas_automaticas` (services.py:52) **não é chamada em lugar nenhum** (código morto).
- B2 tem outro algoritmo de distribuição (agenda_service.py). Não é equivalente.

**Capacidade**
- `AulaSessao.capacidade_efetiva()` (models.py:532): `capacidade` se não for None, senão `unidade.capacidade`.
- `Reserva.clean()` (:562): conta só `RESERVADA` e **ignora PENDENTE e CONCLUIDA**.
- Reimplementada à mão em `aula_remarcar_api` (:4741-4756), `_process_totalpass_payload` (:4392-4400) e `_build_reserva_slots` (:427, com a regra "capacidade ≤ 0 = sem vagas" para listar slots). **Não há constraint no banco**, então concorrência pode estourar a lotação.

**Reposição (30 dias)**
- `aula_status_api`, ação `desmarcar` (views.py:4666-4688) e `aluno_app_desmarcar` (api/main.py): status→CANCELADA, `confirmada_em=None`, `desmarcada_em=now`, **`reposicao_ate = data da aula + 30 dias`**. O professor não pode desmarcar. A mesma regra está duplicada em dois lugares.
- A cláusula 5 do contrato padrão (`set_modelo_contrato`) fala em aviso de 6 horas e reposição em 30 dias, mas **o sistema não valida as 6 horas**.
- Não há tela nem regra para consumir a reposição.

**Status da reserva**
- Mapa de ações (views.py:4661-4667): chegou/iniciar→RESERVADA, finalizar→CONCLUIDA, faltou→FALTOU_SEM_AVISAR, remarcar→CANCELADA (professor não remarca).
- `evoluir_reserva` (:5320) e `aula_evolucao_api` com `finalizar` (:4447) marcam CONCLUIDA ao salvar a evolução.
- O lembrete de WhatsApp exclui CANCELADA, CONCLUIDA e as faltas.

**Contrato / assinatura**
- `services.gerar_token_contrato` e `validar_token_contrato` (`TimestampSigner`, salt `"contrato-assinatura"`, 7 dias); termo com salt `"termo-assinatura"` e 30 dias.
- Assinar muda `status` para ASSINADO_DIGITALMENTE. Contrato já assinado não é assinado de novo. O scheduler só considera contratos `ASSINADO` e `ASSINADO_DIGITALMENTE` para renovação e 3 meses.

**Comissão**
- **Não existe no Django.** No B2: `ComissaoService.gerar(competencia)` (comissoes/service.py), `ROUND_HALF_UP` a 2 casas, só contas PAGAS no mês, profissional = o da conta ou o do contrato, `valor_base × percentual`, único por `conta_receber_id`. Se a regra de comissão for requisito, é **uma funcionalidade nova para o Django/produção**, não uma migração.

**Financeiro**
- Contas a pagar recorrentes: `quantidade` lançamentos; `SEMANAL +7d`, `ANUAL +12 meses`, `MENSAL +idx meses` (dia limitado a 28). Os novos lançamentos nascem sem `recorrencia` própria? Não: copiam `recorrencia` e `quantidade`. Atenção para não regerar em cascata.
- Status ATRASADO é derivado na exibição. O scheduler trata `ABERTO` e `ATRASADO`.
- DRE por `dtPagamento` (regime de caixa); fluxo de caixa por `dtVencimento`.

**Receita Saúde:** regras na seção 2.7. Não pode gerar duas vezes o mesmo pagamento (`recibo_saude_gerado_em`).

**Telefone:** `WhatsappService.clean_phone` (whatsapp_service.py:189) e `get_aluno_phone` (:201). Três normalizações diferentes: `_format_whatsapp_number` (views.py:299), `_telefone_canon` (api/main.py, tolera DDI 55 e o nono dígito) e `_normalize_phone` (B2).

**Detecção de professor:** substring "professor" no nome do perfil (ver seção 1).

---

## 6. ARQUIVOS / MÍDIA

- **Gravado em disco (ver tabela da seção 1):** fotos de aluno, imagem de assinatura do contrato, imagem de assinatura do termo, documentos do aluno (inclusive **PDFs de contrato gerados pelo sistema**, regravados a cada criação, envio ou acesso ao PDF), comprovantes de contas a pagar e de movimentos bancários.
- **Como é servido:**
  - `MEDIA_URL=/media/`, `MEDIA_ROOT=PilatesFinal/media`.
  - O Django só serve `/media/` com `DEBUG=True` (`studiopilates/urls.py:15`). Em produção **tem que ser o nginx** servindo essa pasta. Isso não está no repositório e precisa ser verificado.
  - **Os arquivos de mídia são servidos sem autenticação** se o nginx expõe `/media/` direto. Assinaturas, documentos de saúde/contrato e comprovantes ficam acessíveis por URL.
  - O `.gitignore` ignora `media/`, então o backup depende do servidor.
  - O WhatsApp envia o PDF por URL pública (`/contratos/pdf/<token>/`), o provedor baixa de lá.
- **PDFs/Excel gerados em memória (não gravados):**
  - ReportLab e OpenPyXL, em `exportar_*` (contas a pagar, contas a receber, fluxo de caixa, DRE, evoluções) e recibo de conta a receber (:5533).
  - PDF de contrato: WeasyPrint (não instalado) → ReportLab.
- B2: `STORAGE_DIR=./storage` e `AlunoAnexo.arquivo_path` (arquivos num esquema próprio, sem relação com o `media/` do Django).
- Na máquina local há só 1 foto e 1 PDF de teste. **O volume real está no servidor.**

---

## 7. TESTES

**Existentes (cerca de 62 funções `def test_*`, pytest + pytest-django, `pytest.ini` aponta `studiopilates.settings`):**
- `core/tests/test_acesso_professor.py` (11): bloqueios e liberações do professor, ficha só do próprio aluno, e comando `set_acesso_professor`. Boa cobertura do middleware.
- `core/tests/test_aulas_operacao.py` (7): parcelas (mensal e semanal), listagem da operação por data, evolução com finalizar, avaliação, cobrança, status.
- `core/tests/test_receita_saude.py` (14): layout do CSV coluna a coluna, validações e telas.
- `core/tests/test_ux_listas.py` (8): chips de lista, duplicar plano, mensagem de capacidade excedida, agenda semanal.
- `core/tests/test_whatsapp_scheduler.py` (1, com monkeypatch).
- `tests/` na raiz: 4 testes (CPF válido/inválido, geração de contas a receber, capacidade da reserva).
- `backend/tests/` (6 + 3 + 1 + 2): só do B2 (distribuição de agenda por nº de aulas, idempotência, limites de capacidade, health, módulos).

**Lacunas:**
- Nenhum teste de: **assinatura por token** (nem expiração), **webhook TotalPass**, **API de integração/PWA** (OTP, JWT, confirmar/desmarcar), `contrato_agenda`, `aula_remarcar_api`, `delete_view` de contrato (exclusão em cascata por período), `baixar_conta_receber`, fluxo de caixa/DRE (valores), exportações PDF/Excel, `_build_reserva_slots`, aula avulsa/avaliativa, e-mail, `sync_totalpass`, `concluir_aulas_passadas` e `recalcular_contratos`.
- Nenhum teste de autenticação anônima nas rotas genéricas.
- Os testes do scheduler cobrem 1 caso; não cobrem dedupe, horário nem advisory lock.
- O scheduler usa advisory lock do Postgres, e os testes rodam em SQLite.
- Nenhum teste de contrato de API (golden files) para guiar uma reescrita. **Antes de migrar, vale escrever testes de caracterização dessas regras sobre um dump anonimizado de produção.**

---

## 8. DADOS EM PRODUÇÃO

- **Banco:** `DATABASE_URL` via `dj_database_url` (padrão SQLite em dev). Produção é **PostgreSQL** (psycopg2-binary; `docker-compose.yml` sobe postgres:15; `pg_try_advisory_lock` no scheduler). Não consegui ler o servidor.
- **Tabelas:** 39 models do app `core` + 1 M2M (`core_horariofuncionamento_tipos_servico`) = 40 tabelas `core_*`, mais `auth_*`, `django_*` e `sessions` (cerca de 10). Total estimado de ~50 tabelas. O `db.sqlite3` local tem só 37 (48 migrations aplicadas de 61; é uma cópia antiga com 1 aluno, 9 aulas e 9 reservas, **não representa a produção**). Há 61 migrations numeradas (0001-0061; a pasta tem 64 arquivos contando `__init__` e `__pycache__`). O brief dizia 63.
- **Tabelas que provavelmente mais crescem** (estimativa por estrutura, sem contagem real):
  1. **`core_aulasessao`** (~12 mil, informado por você). Cresce por contrato ativo × aulas/semana × semanas. Também **cria sessões em GET** (`_build_reserva_slots`).
  2. **`core_reserva`** (>= nº de sessões com aluno; tende a mais que as sessões porque várias alunas dividem uma sessão).
  3. **`core_contasreceber`** (uma por mês por contrato, mais avulsas).
  4. **`core_alunowhatsappmessage`** e **`core_whatsappagendamentolog`** (crescem diariamente com lembretes, aniversários, cobranças; guardam o `response_payload` inteiro).
  5. `django_session`, `core_evolucaoaluno`, `core_totalpasswebhookevent` (payload JSON por evento), `core_alunoappcodigo` (nunca é limpo).
  6. As demais são pequenas (cadastros).
- **Atenção na carga de dados:** a ordem de carga por causa das FKs PROTECT e da FK circular `Aluno ⇄ EnderecoAluno`; `Profissional.user` ligado a `auth_user` (e as **senhas em hash do Django**, formato PBKDF2, que o FastAPI precisa saber verificar ou forçar redefinição); os `cd*` e a sequência dos `id`; e o `dsCPF` com formatos mistos (`SEM_CPF_*`, só dígitos, com máscara).

---

## 9. DÍVIDA TÉCNICA E RISCOS PARA A MIGRAÇÃO

1. **`views.py` monolítico (6941 linhas)**, sem separação em módulos; cálculo de negócio, consulta, geração de PDF/Excel e HTTP misturados. Constantes e helpers duplicados (`_add_months` em 2 lugares, `_shift_month`, `_shift_month_clamped`, `_format_whatsapp_number`, `_render_whatsapp_template` ≈ `scheduler._render_template`).
2. **CRUD genérico com `if model is X`** (`create_view`/`edit_view`/`delete_view`): regras de negócio escondidas por modelo (contrato cria parcelas/PDF/e-mail/WhatsApp; profissional cria usuário; aluno sincroniza telefone/endereço; contas a pagar replica recorrência). **É onde o risco de perder regra é maior**, porque não aparece como "função" nomeada.
3. **GET com efeito colateral:** `concluir_aulas_passadas` em 4 views, `_build_reserva_slots` criando `AulaSessao`, `contrato_pdf` regravando `AlunoDocumento`, `baixar/excluir_conta_receber` aceitando GET.
4. **Segurança:** rotas sem login (seção 2), JWTs sem expiração, OTP sem limite, token Wasender no código, `.env` no git, tokens e senhas em texto puro no banco, `/media/` provavelmente público, `DEBUG=True` por padrão, webhook TotalPass aberto sem token configurado, admin do Django exposto.
5. **Estado fora do banco:** `ProfessorAccessMiddleware` e o `context_processor` fazem 1-2 consultas por requisição; perfil por substring do nome; sessão do Django (`request.session` no wizard).
6. **Lógica em templates e JS inline:**
   - `alunos/detail.html` tem 2958 linhas; `generic/list.html` 1154; `static/js/app.js` 2139; `static/css/app.css` 2439. 12 templates têm `<script>` inline (detail, aulas_list, dre_relatorio, fluxo_caixa, comunicado_geral, aviso_aluno etc.).
   - As telas dependem de **HTML renderizado no servidor** com contextos enormes. Para o Next.js é preciso redesenhar as telas, não "converter" templates.
   - `app.js` usa `fetch` com CSRF cookie do Django (`X-CSRFToken`, app.js:1585-1620), então todo o JS precisa de nova autenticação.
7. **Dois mundos de autenticação:** sessão + CSRF do Django (UI), JWT HS256 com a `DJANGO_SECRET_KEY` (B1), JWT com `SECRET_KEY` e tabela `usuario` própria (B2), API key (integração), token assinado (contrato/termo), webhook com header. Unificar sem quebrar links e integradores é parte do trabalho.
8. **Concorrência:** códigos `cd*` e `max+1`; capacidade sem constraint; scheduler em thread dentro do web com lock Postgres; envios em lote bloqueantes com `sleep`.
9. **Acoplamento Django ⇄ FastAPI B1:** `api/main.py` importa `django.setup()` e o ORM. Se o Django sair, o PWA e toda a API de integração caem junto. Se o FastAPI novo usar SQLAlchemy sobre as tabelas `core_*`, será preciso mapear os nomes `cdAluno`, `dsNome` etc. (camelCase misto), os `db_table` implícitos (`core_*`) e as colunas `*_id`.
10. **Schema B2 divergente** (seção 0) e dependências ausentes no requirements. Adotar B2 sem plano = risco de perda de dados e de campos (assinatura, foto, `valor_aula`, `cpf_pagador_recibo`, `recibo_saude_gerado_em`, configurações de WhatsApp...).
11. **Lacunas de regra já visíveis:** `reposicao_ate` nunca consumido; "6 horas de aviso" do contrato não validado; `valor_total` da aula avulsa não multiplica pela quantidade; `Converter` avaliativa não cria contrato; `ATRASADO` nunca persistido; `reservar_aulas_automaticas` morta; `gemini_client` morto; `weasyprint` fora do requirements; DRE sem plano para lançamentos avulsos; comissão só no B2.
12. **Observabilidade:** logging só em console (settings.py:120+), sem Sentry; nenhum teste de carga.
13. **O que é mais difícil de migrar** (ver tabela): o conjunto CRUD genérico+contrato (regra espalhada), a agenda (grade, bloqueios, capacidade e criação sob demanda), as rotas públicas por token (preservar `SECRET_KEY`/salts/prazos), o scheduler/dedupe do WhatsApp, a ficha do aluno (2958 linhas) e o login/permissão do professor.
14. **Estratégia sugerida para "não perder nada":** manter o banco e as tabelas `core_*` como verdade; fazer o novo FastAPI **ler/escrever as mesmas tabelas** (SQLAlchemy reflexivo ou modelos espelho) para um "strangler fig" por área; manter o Django rodando as rotas públicas e o scheduler até o final; congelar e testar as regras da seção 5 antes de portar; copiar `media/` íntegro; manter a mesma `DJANGO_SECRET_KEY`/salts enquanto os links assinados estiverem em circulação; trocar a autenticação por fim.

---

## TABELA FINAL

| Área | Telas/rotas | Regra crítica | Dificuldade de migrar |
|---|---|---|---|
| Alunos + ficha | `cadastros/alunos/*`, `…/<pk>/ficha/` (detail.html 2958 linhas), documentos, evoluções | CPF único (`SEM_CPF_*`, formatos mistos), endereço OneToOne circular, telefones recriados no save, foto/ficha com 7 abas | **Alta** |
| Agenda grade/operacional | `agenda/semana/`, `agenda/aulas/`, `agenda/aulas/operacao/`, horários, funcionamento, bloqueios | `AulaSessao.capacidade` null=unidade, slots (50 min + 10 min), bloqueios, sessões criadas em GET, `_map_status` | **Alta** |
| Aulas / reservas | `reservas/*`, `agenda/aulas/reservas/<id>/*`, avulsa, avaliativa | `unique(aluno, aulaSessao)`, `Reserva.clean` conta só RESERVADA, remarcar apaga sessão vazia, avulsa gera cobrança se valor > 0 | **Alta** |
| Contratos + agenda do contrato | `contratos/*`, `contratos/<pk>/agenda/`, gestão, modelos | `valor_aula = valor/(aulas_semana×4)`, 1 parcela/mês (dia ≤ 28), 1 horário/dia da semana, exclusão em cascata por período | **Alta** |
| Assinatura digital (token) | `contratos/assinar/<token>/`, `contratos/pdf/<token>/`, `termos/assinar/<token>/` | `TimestampSigner` com `SECRET_KEY` (7 e 30 dias), PNG base64, IP, status ASSINADO_DIGITALMENTE, PDF ReportLab/Weasy | **Alta** (rota pública) |
| Planos | `cadastros/planos/*` | `is_avulso`, `duracao_meses`, `modeloContrato`, duplicar com `(copia)` | **Baixa** |
| Financeiro receber/pagar | `financeiro/contas-*`, baixar, recibo PDF, avulso | ATRASADO só calculado, `competencia`, recorrência de pagar, comprovante | **Média** |
| Conta bancária / fluxo / DRE | `financeiro/conta-bancaria`, `fluxo-caixa`, `dre`, exportações PDF/Excel | Fluxo por vencimento, DRE por pagamento, saldo inicial + movimentos | **Média** |
| Receita Saúde | `configuracoes/receita-saude/`, `…/<pk>/receita-saude/arquivo|pagador/` | CSV de 16 colunas, tudo-ou-nada, mesmo ano, até 1000 linhas, `recibo_saude_gerado_em` | **Baixa** (módulo isolado, bem testado) |
| Evolução / avaliação (IA) | gaveta da operação, `evolucoes/*`, enriquecer | Evolução ligada à reserva; OpenAI síncrona; marca CONCLUIDA | **Média** |
| WhatsApp (envio, scheduler, comunicado, aviso) | `configuracoes/whatsapp*`, `avisos/aluno*`, `comunicado-geral*` | Wasender × Evolution por unidade, dedupe por `dedupe_key`, throttle 5 s, advisory lock, 8 tipos de aviso | **Alta** |
| E-mail SMTP | `configuracoes/email/`, envio de contrato | Config no banco com fallback `.env`, `fail_silently` | **Baixa** |
| TotalPass | `integrations/totalpass/webhook/`, `configuracoes/totalpass/`, `sync_totalpass` | Token opcional, cria aluno por CPF, sessão sem profissional, `somente_dia` | **Média/Alta** (rota pública) |
| App do aluno (PWA) | `/app/*`, `/api/fast/aluno-app/*` | CPF + OTP 6 dígitos (10 min), JWT sem exp, desmarcar = `reposicao_ate` +30 dias | **Média** |
| API de integração externa | `/api/fast/integracao/*` (+ duplicata em B2) | `IntegracaoToken` ativo, atualiza `ultimo_uso`, normalização de telefone | **Média** |
| Termo de imagem | `…/termo-imagem/*`, `termos/assinar/<token>/` | Assinatura canvas, `autoriza_imagem=True`, WhatsApp de confirmação | **Média** |
| Cadastros auxiliares | `cadastros/*` (perfis, profissões, unidades, fornecedores, categorias...) | `cd*` manual `max+1`; unidade com capacidade/duração | **Baixa** |
| Wizard | `wizard/step1..5` | IA extrai documento/endereço; estado em sessão | **Média** |
| Configurações / perfil / senha | `perfil/`, `conta/trocar-senha/`, `configuracoes/*` | Perfil edita Profissional; sincronia User⇄Profissional | **Média** |
| Acesso do professor | `core/middleware.py`, `context_processors.py` | Perfil por substring "professor", negar por padrão, dono por reserva/aluno | **Média** (bem testado) |
| Usuário⇄Profissional (signals) | `core/signals.py`, `_sync_user_for_profissional` | OneToOne bidirecional, username = e-mail | **Média** |
| Background (`concluir_aulas_passadas`, scheduler) | Em 4 views + management command + APScheduler | Job que hoje roda como efeito colateral de GET | **Média/Alta** |
| Comissão | só `backend/app` e `frontend/app/comissoes` | Percentual por profissional sobre contas pagas do mês | **Baixa** (nova) |
| Mídia/arquivos | `media/*` | 6 pastas, servidas por nginx (não versionado) | **Média** |

**Arquivos principais citados:**
- `backend/studiopilates/core/{views.py, models.py, urls.py, services.py, middleware.py, signals.py, whatsapp_scheduler.py, whatsapp_service.py, receita_saude.py, totalpass_service.py, forms.py}`
- `backend/studiopilates/settings.py`
- `api/main.py`
- `backend/app/modules/{integracao,comissoes,contratos}/…`
- `shared/ai/openai_client.py`
- `deploy/deploy.sh`
- `web/templates/alunos/detail.html`
- `static/js/app.js`