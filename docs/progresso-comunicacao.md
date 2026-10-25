# Progresso - agente Comunicação (branch feat/comunicacao)

## Feito
1. **Provedores** (`modules/comunicacao/provedores.py`): WasenderAPI (Bearer; `/api/send-message` para texto e documento por URL via `documentUrl`+`fileName`; status em `/api/status`) e Evolution API (`apikey`; `/message/sendText|sendMedia/{instancia}`; status em `/instance/connectionState/{instancia}`). Interface comum (`enviar_texto`, `enviar_documento`, `status_sessao`), timeouts (15/30/10 s), `enviar_com_retry` (3 tentativas, pausa de 2 s ou `Retry-After`), número normalizado por `domain.telefone`. **Sessão desconectada** (HTTP 200 `success=false`, "not connected", "Connection Closed"...) e **credencial recusada** (401/403) não são repetidas e abortam o lote. O token só vai no cabeçalho; qualquer eco dele na resposta é apagado, e as mensagens de erro de rede não trazem URL.
2. **Tela Configurações > Integrações > WhatsApp** (`/configuracoes/integracoes/whatsapp`) + **hub** (`/configuracoes/integracoes`): credencial somente escrita (mostra "configurado" + 4 últimos), **Testar conexão**, pausa entre envios, resumo ao gestor, Pix (tipo/chave), 7 avisos (liga/desliga + horário) e os 9 textos editáveis com chips de variáveis e "restaurar padrão". **Todos os avisos nascem desligados** e há a **chave geral "Envio automático ativo"** do ambiente (nasce desligada, só o Full liga, pede confirmação e é documentada na tela).
3. **Serviço de envio** (`servico.py`): texto/documento a aluno (grava `whatsapp_mensagem`, sem segredo), "Enviar agora" do painel (`POST /whatsapp/reservas/{id}/enviar-agora`), **cobrança** (`financeiro.servico.definir_cobrador`; vencida usa o texto de atraso, a vencer o de vencimento), **enviador de contrato/termo** (`registrar_enviador()` -> `EnviadorWhatsapp`) e **`core.notificador` real** (`NotificadorWhatsapp`, registrado ao importar `routes.py`).
4. **Scheduler R9** (`automatico.py` + `tarefas.py`, a cada 5 min): decide tudo por `domain.whatsapp_avisos`; grava a linha de `whatsapp_agendamento_log` (`dedupe_key` UNIQUE) **antes** de enviar; pausa entre envios (config, padrão 5 s); 3 tentativas; sessão caída/credencial recusada apaga a reserva do aviso (volta a ficar devido), aborta o lote da unidade, grava alerta (1x/dia) e manda e-mail aos administradores; telefone ausente/fixo/inválido é pulado e registrado (`sem_telefone`); resumo ao gestor por WhatsApp. Máximo de 60 envios por rodada (o resto sai na próxima).
5. **Comunicado geral** (`comunicados.py`): público ativos/inativos/todos (+ unidade), `{aluno}`/`{unidade}`, prévia (primeiro aluno com celular + contagem), fila no banco processada pelo worker a cada 5 s (uma mensagem por passada por comunicado, respeitando a pausa), progresso por polling (3 s), pausar/retomar/cancelar, relatório por destinatário. Sessão caída **pausa** o comunicado sem perder ninguém. **Aviso ao aluno** (prévia + envio). **Histórico** com filtros (busca, tipo, situação, período) e **acompanhamento dos envios automáticos**. Telas: `/comunicacao/whatsapp` (abas Histórico, Aviso ao aluno, Envios automáticos), `/comunicacao/comunicados`. Componente da ficha: `components/comunicacao/aba-aluno-whatsapp.tsx` (`{alunoId: number}`).
6. **Testes** (`backend/tests/comunicacao`, ~100 testes): provedores com `httpx.MockTransport` (sucesso, 401, sessão caída, timeout, retry, eco do token); segredos nunca em resposta/auditoria/log/histórico; permissões Full/Secretária/Professor/leitor; dedupe e idempotência do scheduler com `agora` injetado e provedor falso (duas rodadas, horário, corrida de worker, sessão caída, 3 falhas, pausa, limite por rodada, telefones inválidos, chave geral desligada); textos padrão batendo com `domain.whatsapp_avisos`; comunicado (pausar, cancelar, falhas, sessão caída); notificador real (recuperação de senha por código usa o WhatsApp). Uma trava global (`rede_bloqueada`) faz qualquer chamada HTTP real falhar.

## Como rodar
```
cd backend && uv run python -m pytest -q tests/comunicacao tests/test_cobertura_rotas.py
cd frontend && npm install && npm run lint && npm run build
```

## Decisões
- **Chave geral por ambiente** guardada na tabela nova `comunicacao_parametro` (`envio_automatico_ativo`, padrão desligado). Ela só trava o que é AUTOMÁTICO; envio manual, comunicado, cobrança, contrato/termo e o código de senha/OTP continuam funcionando.
- **Configuração por unidade** reaproveita `whatsapp_config` sem mudar o esquema: o provedor vem da coluna `provedor`; **pausa entre envios, `PIX_TIPO` e `PIX_CHAVE` ficam em `variaveis_template` (JSON)**. A credencial é cifrada (Fernet) em `credencial_cifrado` (texto). Linhas novas nascem com todos os `avisar_*` falsos e os textos padrão do domínio; texto `NULL` = usa o padrão do domínio. `ESTUDIO_NOME` vem da identidade.
- **Status gravados no log do scheduler**: `pendente` (reservado, ainda enviando), `sent`, `failed` (3 tentativas, não insiste), `sem_telefone`, e alertas `sessao_caida`/`credencial_recusada`/`resumo` (tipo `alerta`/`resumo`). Um `pendente` que ficar para trás (worker morreu no meio) **não é reenviado** (prefere perder a duplicar).
- `whatsapp_mensagem.tipo` das mensagens novas usa os tipos do domínio (`lembrete_aluno`, `aniversario`, `atraso`...) além de `manual`, `comunicado`, `cobranca`, `contract_link`, `contract_pdf`, `image_term_link`. O histórico mapeia também os tipos antigos (`automated_reminder`...).
- O notificador do core não conhece a unidade: usa a configuração da **primeira unidade (menor id) com credencial**.
- Mídia no Wasender: usei o mesmo endpoint de envio com `documentUrl`/`fileName` (conforme o pedido "endpoint único, mídia por URL"). **Não pude validar contra a API real** (proibido chamar a internet): confirmar no primeiro teste real.
- Rotas novas: `/whatsapp/...` (config, mensagens, enviar, enviar-agora, automaticos, status) e `/comunicacao/...` (comunicados, aviso-aluno). Regra extra: `/whatsapp/configuracao/*` exige `whatsapp.configurar` (inclusive GET); o resto segue o padrão do core (GET ver, POST enviar).

## Mudanças de esquema (ADITIVAS) - o coordenador gera a migração
Tabelas **novas** em `backend/app/modules/comunicacao/models.py`:
- `comunicacao_parametro` (`chave` PK, `valor`, timestamps);
- `comunicado` (texto, publico, unidade_id, status, pausa_segundos, criado_por_id, aviso, ultimo_envio_em, finalizado_em, timestamps);
- `comunicado_destinatario` (comunicado_id, aluno_id, nome, telefone, status, erro, enviado_em; UNIQUE comunicado+aluno).
Nenhuma coluna foi adicionada às tabelas existentes (`whatsapp_config`, `whatsapp_mensagem`, `whatsapp_agendamento_log`).

## Pedidos ao coordenador
1. **Migração**: incluir as 3 tabelas acima e adicionar `comunicacao` em `app/modules/__init__.py::registrar_modelos()` (hoje os modelos só carregam porque `routes.py` os importa).
2. **Contratos/termo**: ligar `servico.registrar_enviador()` aos pontos de extensão de contratos e de `alunos.servico.gerar_link_assinatura_termo`. Métodos: `enviar_link_contrato(db, aluno, link, contrato_id=)`, `enviar_link_termo(db, aluno, link)`, `enviar_documento_por_url(db, aluno, url, nome_arquivo, legenda, tipo=, contrato_id=)` (levantam `ErroDeNegocio` se não enviar; fazem `flush`, sem `commit`). O link/URL deve ser assinado com prazo (`core.links`); a URL não é gravada no histórico.
3. **Aba da ficha**: ligar `components/comunicacao/aba-aluno-whatsapp.tsx` em `components/alunos/abas.ts` (permissão `whatsapp.ver`).
4. **"Enviar agora" do painel**: o painel da agenda mostra o botão desabilitado; ligar a `POST /whatsapp/reservas/{reserva_id}/enviar-agora` (`GET .../previa` devolve o texto). Exige `whatsapp.enviar`.
5. **Hub de integrações**: `app/(app)/configuracoes/integracoes/page.tsx` marca TotalPass e Tokens de API como "Em breve" (constante `DISPONIVEL` no topo). Trocar para `true` quando as telas `.../integracoes/totalpass` e `.../integracoes/tokens` existirem. No `nav.ts` mexi só em 3 linhas de Comunicação: WhatsApp e Comunicados `planejado: false`, e **Integrações agora aponta para `/configuracoes/integracoes`** (era `/comunicacao/integracoes`). Se quiser, acrescente também uma aba "Integrações" no layout de Configurações (`configuracoes/layout.tsx`, que não é meu).
6. **ETL / virada**: as chaves `dedupe_key` do log antigo usam ids antigos (unidade/aluno). Como o novo sistema gera chaves com os ids novos, na virada deixe o sistema antigo desligar os avisos ANTES de ligar a chave geral aqui (ou o ETL regrave as chaves). É exatamente para isso que a chave geral existe.
7. **Worker**: já registra `whatsapp-avisos-automaticos` (300 s) e `comunicados-envio` (5 s) ao descobrir `tarefas.py`. Como o worker é de um laço só, um lote de avisos longo atrasa o comunicado (limitei a 60 envios por rodada).

## Dúvidas para o Jefferson
1. **Wasender, mídia**: o envio de PDF usa `documentUrl`/`fileName` no `/api/send-message`. O sistema antigo usava `/api/send-media` com `mediaUrl`. Qual a documentação vigente da sua conta?
2. **Mensagem de aniversário, vencimento, atraso e 3 meses** continuam de uso opcional (desligados). Quer que o **atraso** tenha um limite (ex.: no máximo 4 semanas ou 60 dias)? Hoje, como no antigo, repete toda semana sem fim (já documentado em `progresso-dominio.md`).
3. Mensagem de **fim de contrato** (`template_fim_contrato`, proposta de renovação com valor reajustado) só existe como texto sob demanda; o aviso automático de renovação (7 dias) usa `template_aviso_renovacao`. Está certo?
4. O resumo ao gestor é enviado a cada rodada que enviar alguma coisa (pode ser vários por dia). Prefere um único resumo diário?

## Pendências conhecidas
- Sem **SSE**: o progresso do comunicado usa polling de 3 s (suficiente e mais simples de operar atrás do nginx).
- Mensagens **recebidas** (direção `recebida`) não são capturadas (não havia webhook de entrada no escopo).
- Teste visual no navegador com a API não foi executado (somente lint/build do frontend e testes da API).

## Suíte completa
`pytest -q` (sem `tests/dados` e `tests/domain`) verde, **exceto 1 teste de outro módulo** que precisa de ajuste do coordenador: `tests/financeiro/test_receber.py::test_cobranca_whatsapp_desabilitada_ate_a_onda_de_comunicacao` afirma que o cobrador NÃO está registrado (503). Agora a comunicação registra o cobrador ao importar `routes.py`, então esse teste deve ser trocado por um que apenas confirme o cobrador registrado (o equivalente já existe em `tests/comunicacao/test_servico_rotas.py::test_cobranca_por_whatsapp_pelo_financeiro`) ou restaurar `servico._cobrador = None` na fixture.
