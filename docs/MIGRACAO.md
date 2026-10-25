# Migração Pilates (Django → FastAPI + Next.js)

Fonte da verdade do sistema antigo: [`inventario-pilates-django.md`](inventario-pilates-django.md) (leia as seções 1, 2, 5 e 9). Código antigo (somente leitura): `C:\Users\JeffersonFernandes\Projetos\Pilates\PilatesFinal`, principalmente `backend/studiopilates/core/{models,views,services,forms,whatsapp_scheduler,whatsapp_service,totalpass_service,receita_saude,middleware,signals}.py`, `api/main.py` e `web/templates/`.

## Estratégia

- Banco **novo** com esquema limpo (SQLAlchemy + Alembic). Os dados antigos entram por **ETL único no final** (`backend/app/etl/`), com relatório de conciliação (contagem por tabela, somas de valores, amostras). Enquanto isso o sistema antigo segue em produção, intocado.
- Entregas por área, cada uma com: modelo, API, regras em `app/domain`, testes, telas, e a linha correspondente da lista de paridade marcada.
- O ETL é desenvolvido e testado com **dados sintéticos** gerados pelos models do Django antigo (SQLite temporário). Dados reais só no cutover, com autorização.

## Regras que não podem se perder (com o caso de teste do sistema antigo)

| # | Regra | Onde está no antigo | Teste de caracterização |
|---|---|---|---|
| R1 | `valor_aula = round_half_up(valor_mensal / (aulas_por_semana × 4), 2)`; `None` se aulas_por_semana = 0. `valor_parcela = valor_mensal`; `valor_total = valor_mensal × max(duracao_meses,1)`. Contrato é sempre MENSAL | `views._contrato_precificacao` (176) | plano 300,00 · 2×/sem · 3 meses → aula 37,50; parcela 300,00; total 900,00 |
| R2 | Parcelas MENSAL: `max(duracao_meses,1)`; vencimento = início + n meses com **dia limitado a 28**; competência `YYYY-MM`. SEMANAL: a cada 7 dias até o fim; competência `ISOANO-SEMANA` | `services.gerar_parcelas` (10) | início 31/01 → vencimentos 28/01? **conferir**: dia = min(dia,28) → 28/01, 28/02, 28/03 |
| R3 | Capacidade efetiva da aula = `capacidade` da sessão, ou a da unidade se nula. Reserva conta só RESERVADA. Unicidade (aluno, sessão). Aviso de erro diz data, hora e `N de M` vagas | `models.AulaSessao.capacidade_efetiva`, `Reserva.clean` | sessão cap 1 com 1 reserva → 2ª recusada |
| R4 | Desmarcar: status CANCELADA, `confirmada_em=None`, `desmarcada_em=agora`, **`reposicao_ate = data da aula + 30 dias`**. Professor não desmarca nem remarca | `views.aula_status_api`, `api/main.aluno_app_desmarcar` | aula 10/10 → reposição até 09/11 |
| R5 | Status exibido: RESERVADA/PENDENTE → aguardando (ou em_aula entre início e fim), CONCLUIDA → finalizada, FALTOU_* → faltou, CANCELADA → remarcada | `views._map_status` (3988) | tabela completa |
| R6 | Aulas passadas viram CONCLUIDA automaticamente (RESERVADA/PENDENTE com fim < agora). **Vira job agendado**, não efeito de abrir tela | `services.concluir_aulas_passadas` (329) | |
| R7 | Contas a receber: `ATRASADO` é derivado (vencida e não paga), não gravado. Fluxo de caixa por vencimento (exclui cancelado); DRE por data de pagamento | `views` fluxo (2644) e DRE (3178) | |
| R8 | Receita Saúde: CSV `;`, CRLF, sem cabeçalho, 16 colunas, ≤1000 linhas, mesmo ano, tudo-ou-nada, `recibo_saude_gerado_em` evita duplicar | `core/receita_saude.py` (+14 testes no antigo) | portar os testes `test_receita_saude.py` |
| R9 | WhatsApp automático a cada 5 min: lembrete de aula (amanhã, 19:00), agenda do professor (18:00), renovação (7 dias antes do fim), aniversário, vencimento (amanhã), atraso (1×/semana), 3 meses (90 dias). Dedupe por `tipo:unidade:data:destinatario` (UNIQUE). Pausa 5 s entre envios, 3 tentativas, aborta se a sessão cair | `core/whatsapp_scheduler.py` | |
| R10 | Link de assinatura de contrato (7 dias) e de termo de imagem (30 dias), assinado; PNG da assinatura + nome + documento + IP; contrato assinado não assina de novo. **Links já enviados devem continuar válidos** (ver Compatibilidade) | `services.gerar_token_*`, views 6809/949 | |
| R11 | Perfil Professor: só agenda/painel, evolução e avaliação **dos alunos das próprias aulas**; sem financeiro, contratos, cadastros, configurações | `core/middleware.py` (11 testes no antigo) | portar `test_acesso_professor.py` |
| R12 | Aula avulsa: cria reserva e, se `valor_aula > 0`, uma conta a receber ligada à reserva. TotalPass/WellHub valor 0 não geram cobrança. Aula avaliativa não cobra | `views` 1083–1513 | |
| R13 | Excluir contrato apaga as contas a receber dele e as reservas do aluno **no período do contrato, na unidade e no serviço do plano**, e sessões que ficarem vazias; exige confirmação explícita. (No novo sistema: vincular reserva ao contrato por FK para não depender de datas) | `views.delete_view` (5101) | |
| R14 | TotalPass: webhook cria/acha aluno por CPF, sessão sem profissional com capacidade da unidade, cancela se status cancelado, respeita capacidade e `somente_dia` | `views._process_totalpass_payload` (4305) | |
| R15 | App do aluno: login por CPF + OTP de 6 dígitos (10 min); lista aulas futuras; confirmar (`confirmada_em`); desmarcar (R4) | `api/main.py` 289–395 | |
| R16 | CPF único; aluno `sem_cpf` permitido; normalização de telefone (DDI 55, nono dígito) em **um** lugar só | `models.Aluno`, `whatsapp_service.clean_phone`, `api/main._telefone_canon` | |
| R17 | Comissão do profissional (existia só no protótipo): percentual por profissional sobre contas **pagas** do mês, `ROUND_HALF_UP`, única por conta | `backend/app/modules/comissoes/service.py` do antigo | |

## Compatibilidade (links e integrações em circulação)

- Links de contrato/termo já enviados usam `django.core.signing.TimestampSigner` com a `SECRET_KEY` do Django e sais `contrato-assinatura` / `termo-assinatura`. O novo sistema deve **aceitar esses tokens** (implementar a verificação no formato do Django com a chave antiga via variável `LEGACY_DJANGO_SECRET_KEY`) por pelo menos 30 dias após o cutover, e emitir tokens novos no formato próprio.
- Integradores externos usam `X-API-Key`/Bearer = `IntegracaoToken` (tabela de tokens) e `cdAluno`. A API `/integracao/*` deve manter os **mesmos caminhos e formatos de resposta** (ver `api/main.py` 211–380) e aceitar os tokens existentes (migrados no ETL).
- O app do aluno (`/app/`) deve continuar no mesmo endereço.

## Lista de paridade (marque ao concluir; cada item = tela + API + teste)

**Acesso e base:** [x] login e-mail/usuário · [x] perfis e permissões (catálogo) · [x] perfil Professor (R11) · [x] profissional sem login · [~] troca/recuperação de senha (e-mail e WhatsApp) — e-mail e código prontos; envio real pelo WhatsApp na onda 3 · [x] identidade white-label · [x] auditoria · [x] perfil do usuário
**Cadastros:** [x] unidades (capacidade, duração) · [x] tipos de serviço · [x] planos (+duplicar, avulso, modelo de contrato) · [x] profissionais (+comissão, CREFITO) · [x] profissões · [x] fornecedores · [x] categorias/subcategorias · [x] horários de funcionamento (+gerar) · [x] horários do studio · [x] bloqueios · [x] termos de uso · [x] modelos de contrato (editor HTML) · [x] modelos de evolução · [ ] tokens de integração
**Alunos:** [x] lista com chips (ativos/inativos/todos) · [x] cadastro (endereço, vários telefones, CEP) · [~] ficha com abas (Contratos, Aulas, Financeiro, WhatsApp, Documentos, Evolução, Avaliações, Uso da imagem) — prontas Dados, Aulas, Financeiro, Evolução, Avaliações, Documentos e Uso da imagem; faltam Contratos e WhatsApp · [x] foto · [x] documentos (upload) · [x] CPF do pagador · [ ] wizard de cadastro com IA
**Agenda:** [x] grade semanal (ocupação n/m, cores por status) · [x] painel operacional (agrupado por horário > profissional, gaveta de evolução) · [x] criar/editar/excluir aula · [x] remarcar/desmarcar/faltou/chegou/finalizar · [x] aula avulsa · [x] aula avaliativa · [x] reposição (consumir `reposicao_ate`: novo) · [x] capacidade transacional (R3)
**Contratos:** [ ] criar com precificação (R1) e parcelas (R2) · [ ] agenda do contrato (1 horário por dia da semana) · [ ] gestão (ativos/vencendo/vencidos) · [ ] PDF · [ ] envio por e-mail e WhatsApp · [ ] assinatura por link (R10) e local · [ ] exclusão segura (R13) · [ ] recalcular
**Financeiro:** [x] contas a receber (baixar, cobrar por WhatsApp, recibo PDF, lançar avulso, exportar PDF/Excel) · [x] contas a pagar (recorrência, pagar, cancelar, comprovante, exportar) · [x] conta bancária e movimentos · [x] fluxo de caixa (R7) · [x] DRE (R7) · [x] Receita Saúde (R8) · [x] comissões (R17)
**Evolução:** [x] evolução e avaliação por reserva · [~] melhoria de texto com IA — pronta; depende da chave cadastrada em Configurações > Integrações (onda 3) · [x] exportar PDF/Excel
**Comunicação:** [ ] WhatsApp Wasender/Evolution por unidade · [ ] scheduler (R9) · [ ] comunicado geral · [ ] aviso ao aluno · [ ] histórico de mensagens · [ ] e-mail SMTP configurável
**Integrações:** [ ] TotalPass webhook + sync (R14) · [ ] API de integração externa · [ ] App do aluno PWA (R15) · [ ] CEP (ViaCEP)
**Dados:** [x] ETL completo com conciliação · [x] cópia da mídia (fotos, assinaturas, documentos, comprovantes) · [x] senhas: usuários antigos entram com hash PBKDF2 do Django aceito no login (ou redefinição obrigatória)

## Segurança exigida (o antigo falhava nisto)

Login obrigatório global · JWT com `exp` · OTP com limite de pedidos/tentativas e resposta que não revela se o CPF existe · segredos cifrados no banco · webhook TotalPass **exige** token · arquivos (assinaturas, documentos, comprovantes) servidos só autenticados ou por link assinado · `DEBUG=false` e hosts explícitos em hml/prod · sem token ou chave no código · rate limit nos endpoints públicos · auditoria das ações sensíveis.

## Ondas de trabalho

1. **Fundação** (core single-tenant, permissões, auth segura, frontend shell, deploy) · **Domínio puro** (`app/domain` + testes R1–R17) · **Modelo de dados + ETL** (models de todas as entidades, migração inicial, ETL com conciliação).
2. Módulos de API + telas: cadastros → alunos → agenda/reservas → contratos → financeiro/Receita Saúde.
3. Comunicação (WhatsApp, scheduler), TotalPass, app do aluno, API de integração, IA.
4. Hardening, hml, ensaio do ETL com cópia anonimizada, teste de paridade lado a lado, cutover.

## Ondas — andamento

- **Onda 1 (concluída e integrada em `develop`):** fundação do core, domínio puro (R1–R17, 2.531 testes golden master), modelo de dados (40+ tabelas) e ETL com conciliação. Ensaio ponta a ponta com dados sintéticos OK.
- **Onda 2a (concluída e integrada em `develop`):** cadastros, alunos, agenda/reservas, financeiro/Receita Saúde.
- **Onda 2b:** contratos (depende de agenda e financeiro).
- **Onda 3:** WhatsApp (envio, scheduler R9, comunicado, aviso), TotalPass (R14, token pela tela), app do aluno (R15), API de integração, IA, telas de Configurações > Integrações.
- **Onda 4:** hardening, hml, ensaio da carga em PostgreSQL com cópia anonimizada, conferência lado a lado, cutover.

## Divergências do sistema antigo a decidir (ver `docs/progresso-dominio.md`)

Valor da aula avulsa não multiplica pela quantidade (R1) · dia ≤ 28 já na 1ª parcela (R2) · remarcação com capacidade 0 passa (R3) · data em UTC no atraso/DRE (R7) · WhatsApp envia a telefone fixo/lixo e atraso sem limite (R9) · aula avulsa em horário com 2 serviços cobra 2× (R12) · excluir contrato apaga contas pagas e evoluções (R13) · bloqueio pontual sem data final vale para sempre.
