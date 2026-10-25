# Progresso — agente DOMÍNIO (`feat/dominio`)

Regras de negócio do sistema antigo (Django) extraídas para **funções puras** em `backend/app/domain/` (stdlib apenas:
sem banco, sem FastAPI, sem Django, sem `datetime.now()`), com **testes de caracterização "golden master"** cujos valores
foram gerados **rodando o código antigo de verdade** contra um SQLite temporário com dados sintéticos.

## Como rodar

```bash
cd backend
uv sync
uv run python -m pytest -q tests/domain                              # 2531 testes, ~3 s
uv run python -m pytest -q tests/domain --cov=app.domain --cov-report=term-missing   # cobertura do pacote: 99%
uv run python -m ruff check app/domain tests/domain
```

O Django (`django>=5.2,<5.3`) e `pytest-cov` entraram **somente no grupo `dev`** (o teste cruzado de tokens usa o
`django.core.signing` real; o domínio em si não importa Django).

## Como regenerar os valores de referência (golden)

Os arquivos `backend/tests/domain/golden/golden_*.py` são **gerados** (cada constante tem o comentário
"valor gerado pelo sistema antigo em 2026-10-25"). Para refazer:

```bash
# 1) Django antigo (precisa de um Python com as dependências do PilatesFinal; o banco é criado em %TEMP%)
set PILATES_ANTIGO_DIR=C:\Users\...\Projetos\Pilates\PilatesFinal
<python-do-venv-antigo> backend/tests/domain/golden_gen/gerar_golden.py [secao ...]
# 2) comissão (protótipo SQLAlchemy do antigo): roda com o venv do projeto novo
backend\.venv\Scripts\python.exe backend/tests/domain/golden_gen/gerar_golden_comissao.py
```

Seções: `precos parcelas telefone documentos capacidade reposicao status_aula agenda financeiro avulsa receita tokens
contratos whatsapp`. Nada toca produção; nenhuma mensagem é enviada (clientes substituídos por dublês); só dados sintéticos.

## Módulos prontos (15) e testes

| Módulo (`app/domain/`) | Regra | Fonte no antigo | Testes |
|---|---|---|---|
| `precos.py` | R1 (+R12 preço) | `views._contrato_precificacao`, `_aula_avulsa_precificacao` | 1118 |
| `parcelas.py` | R2 | `services.gerar_parcelas`, `views._add_months` | 123 |
| `capacidade.py` | R3 | `AulaSessao.capacidade_efetiva`, `Reserva.clean`, `aula_remarcar_api`, `_build_reserva_slots` | 18 |
| `reposicao.py` | R4 | `aula_status_api`, `api/main.aluno_app_desmarcar/confirmar` | 18 |
| `status_aula.py` | R5, R6 | `views._map_status`, `services.concluir_aulas_passadas` | 43 |
| `agenda.py` | slots, bloqueios, agenda do contrato/avulso | `_generate_slots_for_date`, `_is_slot_blocked`, `_load_funcionamento`, `_load_bloqueios`, `contrato_agenda`, `aluno_aula_avulsa_agenda` | 580 |
| `financeiro.py` | R7, R12 | `_build_fluxo_caixa_data_for_period`, `dre_relatorio`, `contas_pagar_list`, `create_view` | 73 |
| `receita_saude.py` | R8 | `core/receita_saude.py` (+ testes portados) | 50 |
| `documentos.py` / `telefone.py` | R16 | `validators.validar_cpf`, `clean_phone`, `_format_whatsapp_number`, `_telefone_canon` | 21 / 242 |
| `whatsapp_avisos.py` | R9 | `core/whatsapp_scheduler.py` | 121 |
| `comissao.py` | R17 | `app/modules/comissoes/service.py` (protótipo) | 25 |
| `contratos.py` | R13 (+vigência) | `delete_view` (Contrato), `contratos_gestao`, `dashboard` | 36 |
| `tokens_legados.py` | R10 | `services.gerar/validar_token_*` (`TimestampSigner`) | 63 |

Total: **2531 testes**, cobertura do pacote `app.domain`: **99%** (6 linhas de defesa não exercitadas).

Todo teste cita a regra (`test_r1_...`, `test_r9_...`). Cada módulo cita no docstring o arquivo/linha antigo.

## O que cada módulo entrega além da paridade

- **telefone**: UMA forma canônica `55DDD9XXXXXXXX` (`normalizar_telefone_br`), `tipo_telefone` (celular/fixo),
  `mesmo_telefone` (tolera DDI e nono dígito) e as 3 funções antigas portadas (`*_antigo`) só para caracterização/ETL.
- **contratos**: plano de exclusão **por FK** (modelo novo) e **inferido** (período/unidade/serviço, o que o antigo fazia),
  `comparar_planos` e `vincular_reservas_aos_contratos` para o ETL preencher a FK `reserva.contrato_id` (reporta ambíguas).
- **tokens_legados**: verifica links antigos de contrato (7 d) e termo (30 d) **sem Django**, byte a byte igual ao
  `TimestampSigner` (teste cruzado com o Django real: assina de um lado e verifica do outro, 300 casos aleatórios +
  expirado/adulterado/salt errado). Também `emitir_token`/`verificar_token` no formato novo (`v1.<payload>.<hmac>`, com
  finalidade e expiração) e `verificar_token_aceitando_legado` para a janela pós-cutover (`LEGACY_DJANGO_SECRET_KEY`).
- **whatsapp_avisos**: `avisos_devidos(agora, config, dados, ja_enviados)` devolve QUAIS avisos estão devidos, a mensagem
  pronta, o telefone e o `dedupe_key`; textos padrão com `{ESTUDIO_NOME}`, `{PIX_TIPO}`, `{PIX_CHAVE}` no lugar de
  "Mayris" e do CNPJ/Pix fixos (renderizando com os valores antigos reproduz os textos antigos exatamente).
- **financeiro**: `esta_atrasada`, `hoje_de_negocio` (data de Brasília), fluxo de caixa, DRE, comparativo, recorrência de
  contas a pagar (sem regeneração em cascata) e `conta_da_aula_avulsa`.

## Divergências e comportamentos estranhos do sistema antigo (decisão do Jefferson)

Todos estão reproduzidos fielmente e marcados no código com `# COMPORTAMENTO ANTIGO` quando o domínio novo difere ou
tem um parâmetro/flag. "Gravado" = coberto por teste que fixa o valor antigo.

| Regra | Comportamento antigo | Sugestão |
|---|---|---|
| R1 aula avulsa | `valor_total = valor_base`: **não multiplica pela quantidade** (pacote de 4 aulas de R$ 80 mostra R$ 80). A cobrança real é por aula, então o total é só informativo. | Confirmar a intenção. Flag `multiplicar_quantidade=True` já existe em `precificar_aula_avulsa`. |
| R1 contrato | Duração negativa não é limitada (`int(-2) or 1` = -2 → total negativo). `Decimal("NaN")` era aceito como valor da aula avulsa. | Validar na API (duração ≥ 1). NaN/Infinity já tratados como inválidos no domínio novo. |
| R2 `add_months` | O dia é limitado a 28 **também no 1º vencimento** (início 31/01 → 1ª parcela 28/01; início 29–31 muda o dia). | Manter 1ª parcela na data de início e fixar um "dia de vencimento ≤ 28" explícito no contrato. |
| R2 aula avulsa MENSAL | Usa o mesmo `add_months` desde `idx=0`: a 1ª aula cai em dia ≤ 28, **fora do dia da semana escolhido** (golden `mensal_dia_31`: sábado 31/01 vira quarta 28/01 e a reserva é criada nessa data). | Usar `primeira_data + idx meses` sem clamp em `idx=0`, ou mensal = a cada 4 semanas. |
| R3 | `aula_remarcar_api` só recusa `if capacidade and total >= capacidade`: com capacidade 0 a remarcação passa; `Reserva.clean` e a listagem de slots tratam 0 como "sem vagas". Três cópias da regra. | Regra única `pode_reservar` (já no domínio). |
| R3 | Só `RESERVADA` ocupa vaga e a ação "chegou/iniciar" muda para RESERVADA com `save(update_fields)` **sem checar capacidade** → pode estourar a lotação; sem constraint no banco. | Checar no `UPDATE` de status e travar a sessão (`FOR UPDATE`). |
| R4 | O prazo de 6 horas da cláusula 5 do contrato **não é validado**; a equipe pode desmarcar aula passada ou já cancelada (reescreve `desmarcada_em`/`reposicao_ate`); a reposição nunca é consumida. | `aviso_minimo_cumprido(..., ativo=False)` está pronto; ligar se for regra do negócio. Definir a tela de reposição. |
| R6 | A conclusão automática roda ao abrir telas (efeito de leitura). | Job agendado (`reservas_a_concluir`). |
| R7 hoje | `contas a pagar`, fluxo de caixa e DRE usam `timezone.now().date()` = **data em UTC**: depois das 21h de Brasília uma conta que vence hoje aparece como ATRASADA (golden `ATRASO`). Painel/WhatsApp usam a data local. | `hoje_de_negocio(agora)` (Brasília) em tudo. |
| R7 ATRASADO | Opção do campo existe mas nada grava; a lista de contas a receber mostra o status gravado. | Derivar sempre (`status_exibido_receber`). |
| R7 DRE × fluxo | O saldo anterior da DRE soma movimentos de contas bancárias **inativas**; o fluxo só das ativas. DRE agrupa por **nome** do plano/categoria (dois planos com o mesmo nome viram uma linha); empates de ordem indefinidos. | Padronizar o critério e agrupar por id. |
| R7 recorrência | As contas geradas nascem com a mesma `recorrencia`/`quantidade` da original e sem vínculo de grupo; a 1ª conta mantém o dia digitado e as demais limitam a 28 (ANUAL de 29/02 → 28/02). | Gravar as cópias com `grupo_id` e sem recorrência; nunca regerar. |
| R8 | `formatar_valor` usa arredondamento bancário (`0,005 → 0,00`), diferente do resto do sistema (ROUND_HALF_UP). Irrelevante com `Numeric(15,2)`. | Manter; coluna já tem 2 casas. |
| R9 telefone | O envio usava o primeiro número "limpo" mesmo sendo **fixo** (`551533334444`) ou lixo (`"123"`), e marcava como enviado. | `telefone_para_whatsapp` (só celular válido) — já aplicado no domínio novo (testado). |
| R9 professor | Texto padrão `"Resumo de amanhã: {horario} – {alunos}"` com `horario` e `alunos` iguais → lista **duplicada** na mensagem. | Trocar o texto padrão para usar só `{alunos}`. |
| R9 atraso | Uma mensagem **por fatura** por semana, **sem limite** (fatura de 2 anos atrás continua gerando aviso toda segunda). | Uma mensagem por aluno por semana com o total e um teto de dias/avisos. |
| R9 dedupe | A chave usa a PK do banco antigo (`student_reminder:1:2026-10-27:7`). `force=True` com chave já existente quebra o log (UNIQUE) depois de enviar. | O ETL traz o log recente; no dia do cutover o novo pode reenviar o que o antigo já enviou (evitar cutover entre 19h e 23h59). Tratar `force` com upsert. |
| R9 padrão | Aniversário, vencimento, atraso e 3 meses nascem **desligados** (`avisar_*=False`); lembrete, professor e renovação nascem ligados. Aniversário só alunos ATIVOS (os demais avisos não olham o status do aluno). Nascidos em 29/02 só no bissexto. | Confirmar quais devem ligar por padrão no novo. |
| R9 textos | Texto padrão trazia CNPJ/Pix e "Mayris" fixos. | Variáveis `{ESTUDIO_NOME}`, `{PIX_TIPO}`, `{PIX_CHAVE}` (white-label); sem Pix configurado a linha some. |
| R12 | Horário de funcionamento que atende **2 serviços** faz a aula avulsa criar uma reserva **e uma cobrança por serviço** (golden `dois_servicos_no_horario`: pacote de 2 aulas, 4 cobranças de R$ 80). O contrato já foi corrigido para o serviço do plano. | Uma reserva/cobrança por aula, do serviço do plano. |
| R13 | Excluir contrato apaga **contas já PAGAS**, **aulas avulsas** do aluno no período, reservas concluídas/faltas e, por CASCADE, **evoluções e avaliações** dessas reservas; com contratos sobrepostos do mesmo aluno/unidade/serviço apaga também as reservas do outro contrato. | FK `reserva.contrato_id`; recusar exclusão com conta paga/evolução (cancelar/encerrar em vez de apagar). `plano_exclusao_por_fk` já separa. |
| Agenda | `bloqueio` **pontual sem data final vale para todos os dias seguintes** (não só para o dia). Janela que começa em 08:30 só gera slots a partir das 09:00. Validação da agenda do contrato tem **efeitos parciais**: o 1º horário já criou reservas quando o 2º é recusado (golden `ERROS_A`). | Pontual sem fim = só aquele dia; validar tudo antes de gravar (já é assim no domínio). |
| Inventário | O inventário diz que `contrato_agenda` sobrescreve o profissional da sessão compartilhada: **não ocorre** (a busca já filtra pelo mesmo profissional). | Corrigir o inventário. |
| R16 | Login do app compara `so_digitos(dsCPF)`; um marcador `SEM_CPF_*` cujos dígitos formem 11 números casaria com um CPF digitado. Três normalizações de telefone diferentes. | `mesmo_cpf` nunca casa `SEM_CPF_*`; telefone canônico único. |
| R17 | Só existe no protótipo; `parse_competencia` aceita `"2026-1"` e `"26-10"` (ano 26 d.C.). Comissão nunca recalcula conta já gerada. | Validar `YYYY-MM` na API. |

### Segurança (achado)

`PilatesFinal/backend/studiopilates/settings.py` traz um **token da WasenderAPI como valor padrão no código**
(`WASENDER_API_TOKEN`). Está no repositório antigo e no histórico: **rotacionar o token** no painel da WasenderAPI. Nada
disso foi copiado para este repositório (os testes zeram a variável).

## Dúvidas abertas para o Jefferson

1. R1 avulsa: o total do pacote deve multiplicar pela quantidade?
2. R2: manter o clamp em 28 no 1º vencimento ou usar "dia de vencimento" explícito?
3. R4: ligar a regra das 6 horas? Qual a regra de consumo da reposição (30 dias)?
4. R9: quais avisos ligam por padrão; aviso de atraso por aluno (e com teto) em vez de por fatura?
5. R13: proibir exclusão de contrato com conta paga/evolução?
6. Bloqueio pontual sem data final: dia único ou indefinido?

## Fora do escopo recebido (não feito aqui)

R11 (permissão do professor — `middleware.py`), R14 (TotalPass `_process_totalpass_payload`) e R15 (OTP do app do aluno:
6 dígitos, 10 min) não estavam na lista de módulos desta tarefa. R15 tem regras puras claras (geração/validação de código,
expiração, limite de tentativas) e é boa candidata a `otp.py`; R14 também (`somente_dia`, status cancelado, capacidade).
