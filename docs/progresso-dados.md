# Progresso do agente DADOS (modelo de dados + ETL)

Branch `feat/dados-etl` (saída de `develop`). Escopo: `backend/app/modules/**/models.py`, `backend/app/etl/**`, `backend/alembic/versions/**`, `backend/tests/dados/**`, `backend/tests/fixtures/**`, este arquivo.

## Estado

- [x] Parte A: modelos de todas as entidades do Pilates (40 tabelas: negócio, M2M e contador de códigos)
- [x] Migração Alembic inicial **provisória** (o coordenador deve regenerá-la depois do merge com o core novo)
- [x] Parte B: ETL com conciliação (Markdown + JSON), idempotência, `--simular`, cópia de mídia com hash
- [x] Origem sintética (SQLite do Django antigo) versionada em `backend/tests/fixtures/` e 52 testes verdes (`uv run python -m pytest -q`)
- [ ] Ensaio contra uma cópia anonimizada de PostgreSQL (ver "Pendências")

## Modelos criados

| Módulo | Tabelas |
|---|---|
| `cadastros` | `unidade`, `tipo_servico`, `plano`, `profissao`, `profissional`, `fornecedor`, `categoria`, `subcategoria`, `horario_funcionamento` (+ M2M `horario_funcionamento_tipo_servico`), `horario_studio`, `bloqueio_agenda`, `termo_uso`, `modelo_contrato`, `modelo_evolucao`, `integracao_token`, `contador_codigo` |
| `alunos` | `aluno`, `aluno_endereco`, `aluno_telefone`, `aluno_documento`, `whatsapp_mensagem`, `app_codigo` |
| `agenda` | `aula_sessao`, `reserva`, `aula_avulsa`, `aula_avaliativa`, `evolucao`, `avaliacao`, `whatsapp_agendamento_log` |
| `contratos` | `contrato` |
| `financeiro` | `conta_receber`, `conta_pagar`, `conta_bancaria`, `movimento_conta`, `comissao`, `receita_saude_config` |
| `integracoes` | `whatsapp_config`, `totalpass_config`, `totalpass_evento` |

Registro dos modelos: `from app.modules import registrar_modelos; registrar_modelos()` (importa o core e todos os módulos no `Base.metadata`; usar em `alembic/env.py`, testes e ETL).
Helpers que moram junto dos modelos: `proximo_codigo` (cadastros) e `ocupar_vaga` / `liberar_vaga` (agenda).

## Decisões (todas obrigatórias do briefing, mais as que tomei)

1. **`codigo_legado`** (Integer, único, anulável) em todo registro que tinha `cdXxx`. Nas tabelas que não tinham código (reserva, sessão, conta a receber, mensagens...) guarda o `id` antigo; é a chave de idempotência do ETL. `cdAluno` dos integradores = `aluno.codigo_legado`. **Novos registros** pegam o código de `proximo_codigo(db, "aluno")`: `UPDATE contador_codigo ... RETURNING` dentro da transação (sem `max+1`; a linha do contador serializa os concorrentes). O ETL inicializa os contadores com o maior código migrado (aluno, contrato, plano, profissional, unidade...).
2. **CPF**: `aluno.cpf` único, só dígitos, NULL quando `sem_cpf` (CHECK `cpf_coerente_com_sem_cpf`: `sem_cpf` ⇔ `cpf` nulo). O ETL normaliza os formatos mistos (máscara, espaços), troca `SEM_CPF_<uuid>` por NULL e relata colisões. Coluna extra `cpf_legado_bruto` guarda o valor original quando o CPF não pôde ser preservado (colisão ou lixo).
3. **`reserva.contrato_id`** FK anulável (novo). `unique(aluno_id, aula_sessao_id)`. Vínculo também explícito com `aula_avulsa_id` e `aula_avaliativa_id`.
4. **`aula_sessao`**: índice único `uq_aula_sessao_slot (unidade_id, tipo_servico_id, coalesce(profissional_id,0), data, hora_inicio)`. O `coalesce` faz o NULL (aula TotalPass sem profissional) participar da unicidade (PostgreSQL e SQLite aceitam índice por expressão). **Capacidade**: nula = herda da unidade. Imposta por contador `reservas_ativas` na própria sessão + `ocupar_vaga()`, um `UPDATE ... WHERE reservas_ativas < coalesce(capacidade, capacidade_da_unidade)` atômico (rowcount 1 = vaga obtida). Escolhi isso em vez de `SELECT ... FOR UPDATE` porque funciona igual em PostgreSQL e em SQLite (dev/testes, que não tem `FOR UPDATE`), não precisa segurar lock durante a request e é testável. Quem muda uma reserva de/para `RESERVADA` chama `ocupar_vaga`/`liberar_vaga` na mesma transação (a regra de negócio fica em `app/domain` + serviço; o contador é só a trava transacional). Só `RESERVADA` conta (regra R3).
5. **`profissional`**: `usuario_id` FK anulável e única para `usuario` (profissional sem login permitido), `perfil_acesso_id` FK anulável, `comissao_percentual` Numeric(5,2) 0–100, `crefito`.
6. **`conta_receber`**: `aluno_id` **sempre** preenchido (contrato → reserva → aluno, como o antigo), `contrato_id` e `reserva_id` opcionais, `status` ∈ {ABERTO, PAGO, CANCELADO} (**ATRASADO não é gravado**: é derivado por vencimento), `recibo_saude_gerado_em`. O mesmo vale para `conta_pagar` (AGENDADO, PAGO, CANCELADO).
7. **Segredos de integração cifrados** (Fernet, `MASTER_KEY`): `whatsapp_config.credencial_cifrado`, `totalpass_config.partner_api_key_cifrado / place_api_key_cifrado / webhook_token_cifrado`, e a senha SMTP (`config_email`, tabela do core). O ETL recebe a chave e cifra na carga. **Token de integração**: guarda-se o SHA-256 (`token_hash`) + 4 últimos caracteres; o integrador continua mandando o mesmo valor, o sistema compara o hash (o valor em claro não fica no banco).
8. **Arquivos**: só caminhos relativos ao storage. Mapa antigo → novo: `alunos/x.jpg` → `alunos/foto/x.jpg`; `assinaturas_termo/x` → `assinaturas/termo/x`; `assinaturas/x` → `assinaturas/contrato/x`; `alunos/documentos/x` → `documentos/x`; `comprovantes/contas_pagar/x` e `comprovantes/movimentos/x` ficam como estão.
9. **Endereço sem FK circular**: `aluno_endereco.aluno_id` único (1:1); `aluno` não aponta para o endereço. O antigo `cdEndereco` do aluno é ignorado (vale o `cdAluno` do endereço; divergência é relatada).
10. **Telefones**: `aluno_telefone(aluno_id, ordem, numero, numero_original)` com `unique(aluno_id, numero)`; `numero` normalizado (DDI 55, nono dígito). Sem código legado: o antigo apagava e recriava a cada salvamento, então o `cdTelefone` é instável; o ETL reconstrói a ordem 1..n por aluno (ordem de `cdTelefone` dentro do aluno) e descarta repetidos.
11. **Horário de funcionamento**: o campo legado `tipoServico` entra no M2M atual (`horario_funcionamento_tipo_servico`); sem serviço = vale para todos.
12. **Tipos**: ids inteiros autoincrementais; dinheiro `Numeric(15,2)`; datas `Date`; instantes `UtcDateTime` (UTC); enums como texto (`Enum(native_enum=False)`); `Timestamped` na maioria (criado_em/atualizado_em recebem a data de cadastro antiga).
13. **Índices**: reservas por sessão/aluno/contrato; sessões por (data, unidade) e (profissional, data); contas a receber por (aluno, vencimento), (vencimento, status), contrato, pagamento; contas a pagar por (vencimento, status); mensagens por (aluno, enviado_em); `dedupe_key` único; eventos TotalPass por event_id/slot_id/recebido_em.
14. **`app_codigo`** (OTP do app): guarda só hash do código, `tentativas` e expiração (o antigo guardava 6 dígitos em claro, sem limite). O ETL **não migra** os códigos antigos (efêmeros).
15. **Comissão** (`comissao`, `profissional.comissao_percentual`): funcionalidade nova; o ETL não preenche (percentual entra 0).

## Migração Alembic provisória

`backend/alembic/versions/0001_pilates_esquema_inicial_provisorio.py` (regenerar: `uv run python -m tests.dados.gerar_migracao_provisoria`). Gerada por autogenerate contra SQLite vazio via API do Alembic (o `alembic/env.py` do esqueleto ainda importa módulos do MayaJus que não existem, então não usei o CLI). Contém também as tabelas do core do esqueleto atual para fechar as FKs. O índice por expressão `uq_aula_sessao_slot` é adicionado à mão (o autogenerate não reflete expressões). Teste (`tests/dados/test_migracao.py`): `upgrade()` em SQLite produz o mesmo esquema do `create_all`, `downgrade()` limpa tudo e o render offline para PostgreSQL contém os nomes de constraint do naming convention, `TIMESTAMP WITH TIME ZONE`, `NUMERIC(15, 2)` e o índice `coalesce`.

## O que o ETL cobre

`uv run python -m app.etl --origem <url|arquivo> --destino <url|arquivo> [--simular] [--midia-origem <pasta> --midia-destino <pasta>] --relatorio saida.md [--criar-esquema] [--master-key ...]` (a chave também pode vir de `MASTER_KEY`). Escreve `saida.md` e `saida.json`. Código de saída 0 = conciliação OK; 1 = divergência sem justificativa ou erro.

- **Origem somente leitura**: SQLite abre com `mode=ro`; PostgreSQL abre a sessão com `default_transaction_read_only=on`. Reflexão das tabelas `core_*` e `auth_user`.
- **Ordem** (cada etapa em transação própria): perfis e usuários → cadastros → profissionais → horários/bloqueios/tokens → alunos/endereços/telefones → contratos/documentos → sessões/avulsas/avaliativas/reservas/evoluções/avaliações → financeiro → integrações/comunicação → contadores → verificação.
- **Idempotente** por `codigo_legado` (insere só o que falta; rodar 2× não duplica). `--simular` roda tudo numa única transação desfeita no fim (exercita as constraints e a conciliação sem gravar nem copiar mídia).
- **Usuários**: `auth_user` → `usuario`; hash `pbkdf2_sha256$...` copiado como está em `senha_hash`; senha inutilizável (`!...`) vira NULL + convite pendente; e-mail vazio gerado a partir do login (relatado); e-mail repetido recebe `+id`.
- **Perfis**: por nome (substring "professor" → Professor; admin → Administrador; financ → Financeiro; padrão/recepção/gestão → Recepção/Gestão; leitura → Somente leitura). Desconhecidos viram Recepção/Gestão e vão para o relatório. Superusuário → Administrador. Perfil ausente no destino é criado vazio (e relatado como pendência para o core semear).
- **Sessões duplicadas**: detecta pela chave do índice único, funde na de menor id (capacidade = maior explícita), reaponta reservas; se o mesmo aluno ficou duas vezes na sessão fundida, mantém a reserva com mais dependências (evolução/avaliação/conta) e melhor status, e reaponta os dependentes. Hora final ≤ inicial é corrigida pela duração da unidade (relatado).
- **Contrato da reserva**: inferido por (aluno, unidade, serviço do plano, data dentro da vigência) só quando há exatamente um candidato; avulsas/avaliativas ficam sem contrato; o resto vai para o relatório (sem profissional/TotalPass, ambígua, nenhum contrato cobre).
- **Contas a receber**: `aluno_id` resolvido por contrato → reserva → aluno; `ATRASADO` gravado vira ABERTO; vínculo órfão (FK inexistente) é zerado e relatado; sem aluno resolvível é descartado com motivo.
- **Mídia**: copia com verificação de SHA-256 (e grava o hash em `aluno_documento.sha256`); ausentes na origem são listados; divergência de hash após a cópia é erro.
- **Segredos**: WhatsApp (credencial), TotalPass (3 chaves) e e-mail cifrados com a MASTER_KEY.
- **Contadores** de código inicializados a partir do maior `codigo_legado`.
- **Relatório**: contagem origem × esperado × destino por tabela com descartados/fundidos/adiados/ajustados e motivos; somas (planos, contratos, avulsas, contas a receber/pagar por status, movimentos por tipo, saldo inicial); alunos sem CPF; CPFs duplicados; sessões fundidas; reservas sem contrato; sessões acima da capacidade; mídia ausente; FKs órfãs na origem e no destino; checagem de `reservas_ativas` contra as reservas; amostra aleatória de 20 registros (distribuída entre tabelas, semente fixa) comparados campo a campo.

## O que o ETL NÃO cobre (ou cobre parcialmente)

- **`config_email`** (tabela do core, ainda em reescrita): o ETL já sabe carregar (procura colunas `host/smtp_host`, `porta`, `usuario`, `senha_cifrado`..., `usar_tls`, `remetente`, `ativo`), mas se a tabela não existir no destino a carga fica **adiada** e registrada como pendência (reexecutar depois do core; o ETL é idempotente). Testado com uma tabela de teste.
- Tabelas do Django sem uso no novo sistema: `django_session`, `auth_group/permission`, `django_admin_log`, migrations.
- Variáveis de ambiente do antigo (`WASENDER_API_TOKEN`, `EVOLUTION_*`, `EMAIL_*`, `TOTALPASS_*`, `OPENAI_*`): não estão no banco; precisam ir para o `.env`/configuração do novo (o token Wasender estava fixo em `settings.py` do antigo e deve ser rotacionado).
- Links assinados em circulação (contrato/termo): dependem da `SECRET_KEY` do Django; é trabalho do módulo de contratos (`LEGACY_DJANGO_SECRET_KEY`), não do ETL.
- `concluir_aulas_passadas` (R6): não roda no ETL; as reservas passadas ficam como estavam.
- Não grava na `auditoria` do core que o ETL rodou (nome de colunas ainda em definição).
- Origem PostgreSQL e destino PostgreSQL **não foram exercitados** (a máquina não tem PostgreSQL; tudo foi testado em SQLite). A leitura somente leitura, `timestamptz`, `jsonb` e `Numeric` exato estão tratados no código, mas o ensaio real fica para a cópia anonimizada.

## Ensaio completo (origem sintética) — resumo da conciliação

Rodado com `uv run python -m app.etl --origem tests/fixtures/origem_sintetica.sqlite --destino <novo.sqlite> --criar-esquema --midia-origem tests/fixtures/midia_origem --midia-destino <storage> --relatorio rel.md`: **resultado OK, código de saída 0, 2ª execução idêntica sem inserir nada**.

| Tabela | Origem | Descartados | Fundidos | Destino | Motivo |
|---|---:|---:|---:|---:|---|
| usuario | 8 | 0 | 0 | 8 | 1 sem e-mail gerado do login |
| profissional | 9 | 0 | 0 | 9 | 2 sem login |
| aluno | 62 | 0 | 0 | 62 | 6 sem CPF (4 marcados, 1 CPF lixo, 1 colisão após normalizar) |
| aluno_telefone | 107 | 1 | 0 | 106 | repetido no mesmo aluno |
| contrato | 25 | 0 | 0 | 25 | |
| aula_sessao | 772 | 0 | 25 | 747 | duplicatas fundidas; 1 com hora invertida corrigida |
| reserva | 549 | 0 | 4 | 545 | conflito aluno×sessão após fusão |
| evolucao / avaliacao | 160 / 20 | 0 | 0 | 160 / 20 | |
| conta_receber | 95 | 1 | 0 | 94 | sem aluno resolvível (R$ 12,00); 1 contrato órfão zerado; 2 ATRASADO→ABERTO |
| conta_pagar | 30 | 0 | 0 | 30 | 9 ATRASADO→AGENDADO |
| whatsapp_mensagem | 161 | 1 | 0 | 160 | aluno inexistente |
| app_codigo | 10 | 10 | 0 | 0 | OTP efêmero |
| config_email | 1 | 0 | 0 (1 adiado) | 0 | core sem `config_email` |

Somas: planos 1.340,00; contratos (total 26.760,00 / parcela 7.760,00); contas a receber 27.787,50 (descartado 12,00 → 27.775,50 no destino; PAGO 20.360,00); contas a pagar 45.570,21; movimentos ENTRADA 10.231,14 / SAÍDA 7.346,11: todas as somas conferem. Mídia: 72 referenciados, 66 copiados, 6 ausentes (relatados). Amostra de 20 registros: 0 diferenças.

## Pendências e dúvidas para o Jefferson

1. **Nome da coluna**: usei `codigo_legado` também para o código de negócio dos registros novos (aluno novo recebe o próximo do contador no mesmo campo). Prefere uma coluna `codigo` separada e `codigo_legado` só para o histórico? (É trocar o nome do atributo do aluno/contrato e do contador.)
2. **Token de integração só como hash**: a tela "Tokens de Integração" do antigo mostra o valor para copiar. No novo, só dá para mostrar na criação. Se precisar continuar vendo, trocamos para texto cifrado reversível (`token_cifrado`). Qual prefere?
3. **Perfis**: no antigo só o perfil "professor" tinha restrição; todos os outros (e usuários sem profissional) tinham acesso total. O ETL mapeia "Padrão", recepção e perfis desconhecidos (ex.: "Coordenação") para **Recepção/Gestão** e lista cada caso. Confirme o mapeamento antes do cutover (e liste os nomes reais dos perfis de produção).
4. **CPF repetido** (mesmo CPF em formatos diferentes, comum com alunos criados pelo TotalPass): o ETL **não funde alunos**; mantém o CPF no aluno com mais contratos e deixa os outros sem CPF (`sem_cpf`, original em `cpf_legado_bruto`). Decidir quem unifica (manual) depois da carga.
5. **Reservas sem contrato inferível** (TotalPass, reposições soltas, períodos sem contrato): ficam com `contrato_id` nulo; o relatório lista as categorias. Se alguma regra de negócio exigir contrato, é decisão sua caso a caso.
6. **Sessões acima da capacidade** no antigo (mais RESERVADA que vagas): migram como estão e são relatadas; o `ocupar_vaga` impede novas reservas nelas.
7. **core**: o ETL assume no core as tabelas `usuario` (`senha_hash`, `email`, `login` se existir, `perfil_acesso_id`, `ativo`...), `perfil_acesso` (`nome`) e `config_email`. Colunas NOT NULL desconhecidas recebem um padrão e são listadas no relatório (hoje aparece `tenant`, pois o esqueleto ainda tem multi-tenant). Quando a FUNDAÇÃO fechar o core, rodar o ensaio de novo e conferir "Colunas do core preenchidas automaticamente" e "Pendências" no relatório.
8. **Ensaio com PostgreSQL**: pedir uma cópia anonimizada (ou rodar o ETL em `--simular` contra um dump restaurado em máquina local) antes do cutover. O gerador sintético não substitui a variedade de sujeira dos dados reais; o relatório existe justamente para expô-la.
9. **Dados pessoais no relatório**: o relatório lista alunos só por `cdAluno` (nunca nome/CPF completo), mas guarde-o como material interno.

## Como rodar

```bash
cd backend && uv sync
uv run python -m pytest tests/dados -q                      # modelos, migração e ETL (usa o fixture sintético)

# regenerar o fixture (usa o Python do ambiente ANTIGO, de dentro de PilatesFinal/backend, caminhos FORA do repo antigo)
$env:PYTHONDONTWRITEBYTECODE="1"
<venv antigo>\python.exe <novo>\backend\tests\dados\gerar_origem_sintetica.py --saida <novo>\backend\tests\fixtures\origem_sintetica.sqlite --midia <novo>\backend\tests\fixtures\midia_origem

# ensaio manual
uv run python -m app.etl --origem tests/fixtures/origem_sintetica.sqlite --destino ../saida/novo.sqlite --criar-esquema \
  --midia-origem tests/fixtures/midia_origem --midia-destino ../saida/storage --relatorio ../saida/relatorio.md

# produção (só com autorização do Jefferson): --origem postgresql://... (somente leitura) --destino postgresql://... ; sem --criar-esquema (o esquema vem do Alembic)
```

## Mudanças de interface que afetam outros agentes

- `app.modules.registrar_modelos()` precisa estar no `alembic/env.py` (o env do esqueleto importa `app.comunicador`, `app.modules.faturamento` etc. que não existem; a FUNDAÇÃO/coordenador deve ajustar).
- Tabelas do core referenciadas por FK: `usuario(id)` (de `profissional.usuario_id`) e `perfil_acesso(id)` (de `profissional.perfil_acesso_id`).
- Quem criar aluno/contrato/etc. deve usar `proximo_codigo(db, "aluno")`; quem alterar reservas deve usar `ocupar_vaga` / `liberar_vaga`.
