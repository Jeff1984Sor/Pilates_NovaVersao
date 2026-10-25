"""R9 - avisos automáticos de WhatsApp. Caracterização contra core/whatsapp_scheduler.py (rodado de verdade, com os
clientes de envio substituídos por dublês, em SQLite temporário com dados sintéticos)."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain import whatsapp_avisos as wa
from tests.domain.golden import golden_whatsapp as g

SP = ZoneInfo("America/Sao_Paulo")
VARIAVEIS = {"ESTUDIO_NOME": "Mayris", "PIX_TIPO": "CNPJ", "PIX_CHAVE": "50.732.875/0001-56"}
UNIDADE = g.DEFINICOES["principal"]


# ---------------------------------------------------------------- reconstrução do cenário ----------------------

def _dados() -> wa.DadosParaAvisos:
    d = g.DEFINICOES
    alunos = {
        a[0]: wa.AlunoAviso(id=a[0], nome=a[1], unidade_id=a[2], status=a[3], nascimento=a[4], telefones=a[5], codigo=a[0]) for a in d["alunos"]
    }
    profs = {p[0]: wa.ProfissionalAviso(p[0], p[1], p[2]) for p in d["profissionais"]}
    reservas = [
        wa.ReservaAviso(
            id=r[0], aluno=alunos[r[1]], status=r[2], data=r[3], hora_inicio=r[4], tipo_servico=r[5], unidade_id=r[6], unidade_nome=r[7],
            profissional=profs.get(r[8]),
        )
        for r in d["reservas"]
    ]
    contratos = {
        c[0]: wa.ContratoAviso(id=c[0], numero=c[1], aluno=alunos[c[2]], unidade_id=c[3], inicio=c[4], fim=c[5], status=c[6]) for c in d["contratos"]
    }
    contas = [wa.ContaAviso(id=c[0], contrato=contratos.get(c[1]), status=c[2], valor=c[3], vencimento=c[4]) for c in d["contas"]]
    return wa.DadosParaAvisos(reservas=reservas, alunos=list(alunos.values()), contratos=list(contratos.values()), contas=contas)


def _config(templates=None, ligados=None, variaveis=VARIAVEIS) -> wa.ConfigAvisos:
    campo = wa.CAMPO_TEMPLATE_DO_TIPO
    templates = g.PADROES if templates is None else templates
    ligados = ligados or {t: True for t in wa.TIPOS}
    avisos = {t: wa.ConfigAviso(ligados[t], wa.HORARIO_PADRAO[t], templates.get(campo[t], "")) for t in wa.TIPOS}
    return wa.ConfigAvisos(UNIDADE, g.DEFINICOES["unidades"][UNIDADE], avisos, variaveis)


def _chamadas(rodada: dict, nome: str) -> list[tuple]:
    return [(c[1], c[2], c[3], c[5]) for c in rodada[nome]["chamadas"]]   # (aluno/None, telefone, mensagem, contrato)


NUMERO_DO_CONTRATO = {c[0]: c[1] for c in g.DEFINICOES["contratos"]}   # id -> cdContrato (o antigo registra o numero)


def _avisos_enviar(avisos):
    return [(a.destinatario_nome, a.telefone, a.mensagem, NUMERO_DO_CONTRATO.get(a.contrato_id)) for a in avisos if a.situacao == "enviar"]


HOJE, AMANHA = g.HOJE, g.AMANHA
PRIMEIRA = g.EXECUCOES[0]
SEGUNDA = g.EXECUCOES[1]
# o antigo "enviou" para estes dois alunos, mas os telefones eram um fixo e o texto "123" (ver divergencias)
ALUNOS_COM_TELEFONE_INVALIDO = {"Gabi", "Hugo"}


# ---------------------------------------------------------------- lembrete de aula ---------------------------

def test_r9_lembrete_de_aula_identico_ao_antigo_exceto_telefone_invalido():
    avisos = wa.avisos_lembrete_aula(_config(), HOJE, _dados().reservas)
    esperado = [c for c in _chamadas(PRIMEIRA, "lembrete_aluno") if c[0] not in ALUNOS_COM_TELEFONE_INVALIDO]
    obtido = [(n, t, m, c) for n, t, m, c in _avisos_enviar(avisos)]
    assert obtido == esperado
    # mesmos grupos que o antigo ("eligible_students"), um por aluno, na mesma ordem
    assert len(avisos) == PRIMEIRA["lembrete_aluno"]["retorno"]["eligible_students"]
    assert [e[0] for e in PRIMEIRA["lembrete_aluno"]["entradas"]] == [a.destinatario_nome for a in avisos]


def test_r9_lembrete_exclui_cancelada_concluida_faltas_e_outra_unidade_e_inclui_pendente():
    nomes = {a.destinatario_nome for a in wa.avisos_lembrete_aula(_config(), HOJE, _dados().reservas)}
    assert nomes == {"Ana", "Bia", "Caio", "Dani", "Gabi", "Hugo"}          # Dani so tem reserva PENDENTE
    assert not nomes & {"Duda", "Edu", "Fabi"}                              # cancelada, faltas, outra unidade
    # Bia tem uma CONCLUIDA (10h) e uma RESERVADA (11h): so a das 11h entra
    bia = next(a for a in wa.avisos_lembrete_aula(_config(), HOJE, _dados().reservas) if a.destinatario_nome == "Bia")
    assert "às 11:00" in bia.mensagem


def test_r9_lembrete_aluno_sem_telefone_e_pulado_como_sem_telefone():
    caio = next(a for a in wa.avisos_lembrete_aula(_config(), HOJE, _dados().reservas) if a.destinatario_nome == "Caio")
    assert (caio.situacao, caio.telefone) == ("sem_telefone", None)
    assert next(e for e in PRIMEIRA["lembrete_aluno"]["entradas"] if e[0] == "Caio")[1] == "without_phone"


def test_r9_divergencia_telefone_fixo_e_invalido_nao_recebem_mais_mensagem():
    avisos = {a.destinatario_nome: a for a in wa.avisos_lembrete_aula(_config(), HOJE, _dados().reservas)}
    assert avisos["Gabi"].situacao == "sem_telefone" and avisos["Hugo"].situacao == "sem_telefone"
    # COMPORTAMENTO ANTIGO: ambos foram marcados como "sent" (para 551533334444 e para "123")
    antigo = {c[1]: c[2] for c in PRIMEIRA["lembrete_aluno"]["chamadas"]}
    assert antigo["Gabi"] == "551533334444" and antigo["Hugo"] == "123"


def test_r9_lembrete_chaves_de_dedupe_iguais_as_do_antigo():
    avisos = wa.avisos_lembrete_aula(_config(), HOJE, _dados().reservas)
    chaves = {a.dedupe_key for a in avisos if a.situacao == "enviar"}
    antigas = {k for k in g.CHAVES_LOG if k.startswith("student_reminder")}
    assert chaves == antigas - {"student_reminder:1:2026-10-27:8", "student_reminder:1:2026-10-27:9"}
    assert all(a.data_referencia == AMANHA for a in avisos)


def test_r9_lembrete_variaveis_aulas_e_horarios_como_a_tela_ao_vivo():
    cfg = _config(templates={"template_aviso_aluno": "Aluno {aluno} {aulas} | {horarios} | {unidade} {data} {tipo_servico} {horario}"})
    ana = next(a for a in wa.avisos_lembrete_aula(cfg, HOJE, _dados().reservas) if a.destinatario_nome == "Ana")
    assert ana.mensagem == g.MENSAGEM_UI


# ---------------------------------------------------------------- agenda do professor -----------------------------

def test_r9_agenda_do_professor_identica_ao_antigo():
    avisos = wa.avisos_agenda_professor(_config(), HOJE, _dados().reservas)
    assert len(avisos) == 1   # o professor sem celular so tem reserva PENDENTE: nao aparece
    esperado = [(None, c[0], c[1]) for c in [(x[2], x[3]) for x in PRIMEIRA["agenda_professor"]["chamadas"]]]
    a = avisos[0]
    assert (a.telefone, a.mensagem) == (esperado[0][1], esperado[0][2])
    assert a.dedupe_key == "professor_schedule:1:2026-10-27:1" and a.data_referencia == AMANHA
    assert a.situacao == "enviar"


def test_r9_agenda_do_professor_repete_a_lista_porque_o_texto_padrao_usa_horario_e_alunos():
    # COMPORTAMENTO ANTIGO: {horario} e {alunos} recebem o MESMO texto; o padrao "Resumo de amanha: {horario} – {alunos}" duplica
    a = wa.avisos_agenda_professor(_config(), HOJE, _dados().reservas)[0]
    corpo = a.mensagem.removeprefix("Resumo de amanhã: ")
    primeira, segunda = corpo.split(" – ")
    assert primeira == segunda


def test_r9_agenda_do_professor_so_reservada_com_professor():
    dados = _dados()
    nomes = [n for n in wa.avisos_agenda_professor(_config(), HOJE, dados.reservas)[0].mensagem.split("\n")]
    assert not any("Duda" in n or "Edu" in n for n in nomes)


# ---------------------------------------------------------------- renovação / aniversário / vencimento / atraso / 3 meses ---

def test_r9_renovacao_em_7_dias_so_contrato_assinado():
    avisos = wa.avisos_renovacao(_config(), HOJE, _dados().contratos)
    assert _avisos_enviar(avisos) == [(n, t, m, c) for n, t, m, c in _chamadas(PRIMEIRA, "renovacao")]
    assert [a.destinatario_nome for a in avisos] == ["Ana", "Caio"]          # Caio assinado digitalmente, sem telefone
    assert avisos[1].situacao == "sem_telefone"
    assert avisos[0].dedupe_key == "contract_renewal:1:2026-11-02:1"       # referencia = data do fim (hoje + 7)
    assert avisos[0].tipo_no_log == "contract_renewal"


def test_r9_aniversario_identico_ao_antigo():
    avisos = wa.avisos_aniversario(_config(), HOJE, _dados().alunos)
    assert _avisos_enviar(avisos) == _chamadas(PRIMEIRA, "aniversario")
    assert [a.destinatario_nome for a in avisos] == ["Ana"]                   # Bia inativa; Caio nasceu em 29/02; Duda e dia 27
    assert avisos[0].dedupe_key == "birthday:1:2026-10-26:1"


def test_r9_aniversario_29_de_fevereiro_so_em_ano_bissexto():
    caio = next(a for a in _dados().alunos if a.nome == "Caio")
    assert wa.avisos_aniversario(_config(), date(2028, 2, 29), [caio])[0].destinatario_nome == "Caio"
    assert wa.avisos_aniversario(_config(), date(2027, 2, 28), [caio]) == []
    assert wa.avisos_aniversario(_config(), date(2027, 3, 1), [caio]) == []


def test_r9_vencimento_amanha_so_status_aberto():
    avisos = wa.avisos_vencimento(_config(), HOJE, _dados().contas)
    assert _avisos_enviar(avisos) == _chamadas(PRIMEIRA, "vencimento")
    assert [a.dedupe_key for a in avisos] == ["payment_due:1:2026-10-27:1", "payment_due:1:2026-10-27:2"]
    assert all(a.data_referencia == AMANHA for a in avisos)


def test_r9_atraso_uma_mensagem_por_conta_com_referencia_na_segunda_feira():
    avisos = wa.avisos_atraso(_config(), HOJE, _dados().contas)
    assert _avisos_enviar(avisos) == _chamadas(PRIMEIRA, "atraso")
    assert [a.dedupe_key for a in avisos] == [
        "payment_overdue:1:2026-10-26:8", "payment_overdue:1:2026-10-26:9", "payment_overdue:1:2026-10-26:10",
    ]
    assert [a.destinatario_nome for a in avisos] == ["Ana", "Ana", "Bia"]    # Ana recebe 2 (uma por fatura)


def test_r9_atraso_dedupe_semanal():
    quinta = date(2026, 10, 29)
    assert wa.segunda_feira_da_semana(quinta) == date(2026, 10, 26)
    assert wa.segunda_feira_da_semana(date(2026, 11, 1)) == date(2026, 10, 26)      # domingo ainda e da semana de 26/10
    assert wa.chave_dedupe_atraso(1, quinta, 8) == "payment_overdue:1:2026-10-26:8"
    # a mesma chave durante toda a semana, outra na semana seguinte
    assert wa.chave_dedupe_atraso(1, date(2026, 10, 30), 8) == wa.chave_dedupe_atraso(1, quinta, 8)
    assert wa.chave_dedupe_atraso(1, date(2026, 11, 2), 8) == "payment_overdue:1:2026-11-02:8"


def test_r9_tres_meses_exatamente_90_dias():
    avisos = wa.avisos_tres_meses(_config(), HOJE, _dados().contratos)
    assert _avisos_enviar(avisos) == _chamadas(PRIMEIRA, "tres_meses")
    assert [a.destinatario_nome for a in avisos] == ["Dani"]       # 89 dias nao; contrato nao assinado nao
    assert avisos[0].dedupe_key == "three_months:1:2026-07-28:5"


# ---------------------------------------------------------------- deduplicação e orquestração ------------------

def test_r9_segunda_rodada_nao_reenvia_nada():
    config, dados = _config(), _dados()
    primeira = wa.avisos_devidos(datetime(2026, 10, 26, 23, 55, tzinfo=SP), config, dados)
    chaves = {a.dedupe_key for a in primeira if a.situacao == "enviar"}
    assert chaves
    segunda = wa.avisos_devidos(datetime(2026, 10, 26, 23, 55, tzinfo=SP), config, dados, ja_enviados=chaves)
    assert not [a for a in segunda if a.situacao == "enviar"]
    assert {a.situacao for a in segunda if a.dedupe_key in chaves} == {"ja_enviado"}
    # o antigo tambem: 2a rodada sem nenhuma chamada
    for nome in ("lembrete_aluno", "agenda_professor", "renovacao", "aniversario", "vencimento", "atraso", "tres_meses"):
        assert SEGUNDA[nome]["chamadas"] == []


def test_r9_chave_dedupe_formato():
    assert wa.chave_dedupe("birthday", 1, date(2026, 10, 26), 5) == "birthday:1:2026-10-26:5"
    assert wa.chave_dedupe("birthday", None, date(2026, 10, 26), None) == "birthday:0:2026-10-26:0"


@pytest.mark.parametrize("hhmm,tipos", list(g.QUANDO.items()))
def test_r9_quais_avisos_disparam_em_cada_horario(hhmm, tipos):
    hora, minuto = (int(x) for x in hhmm.split(":"))
    agora = datetime(2026, 10, 26, hora, minuto, tzinfo=SP)
    devidos = {wa.PREFIXO_DEDUPE[t] for t in wa.tipos_a_disparar(agora, _config())}
    assert devidos == set(tipos)


def test_r9_horario_em_brasilia_e_nao_em_utc():
    # 22:30 UTC = 19:30 em Brasilia: o lembrete das 19h ja esta devido
    utc = datetime(2026, 10, 26, 22, 30, tzinfo=ZoneInfo("UTC"))
    assert wa.LEMBRETE_ALUNO in wa.tipos_a_disparar(utc, _config())
    cedo_utc = datetime(2026, 10, 26, 21, 30, tzinfo=ZoneInfo("UTC"))   # 18:30 em Brasilia
    assert wa.LEMBRETE_ALUNO not in wa.tipos_a_disparar(cedo_utc, _config())
    assert wa.horario_atingido(datetime(2026, 10, 26, 19, 0), time(19, 0))


def test_r9_avisos_desligados_nao_disparam_e_padroes_de_liga_desliga():
    assert g.LIGADOS_PADRAO["avisar_aluno"] and not g.LIGADOS_PADRAO["avisar_atraso"]
    for tipo, campo in [(wa.LEMBRETE_ALUNO, "avisar_aluno"), (wa.AGENDA_PROFESSOR, "avisar_professor"), (wa.RENOVACAO, "avisar_renovacao"),
                        (wa.ANIVERSARIO, "avisar_aniversario"), (wa.VENCIMENTO, "avisar_vencimento"), (wa.ATRASO, "avisar_atraso"),
                        (wa.TRES_MESES, "avisar_tres_meses")]:
        assert wa.LIGADO_PADRAO[tipo] is g.LIGADOS_PADRAO[campo]
    for tipo, campo in [(wa.LEMBRETE_ALUNO, "horario_aviso_aluno"), (wa.AGENDA_PROFESSOR, "horario_aviso_professor"), (wa.RENOVACAO, "horario_aviso_renovacao"),
                        (wa.ANIVERSARIO, "horario_aviso_aniversario"), (wa.VENCIMENTO, "horario_aviso_vencimento"), (wa.ATRASO, "horario_aviso_atraso"),
                        (wa.TRES_MESES, "horario_aviso_tres_meses")]:
        assert wa.HORARIO_PADRAO[tipo] == g.HORARIOS_PADRAO[campo]
    desligados = {t: False for t in wa.TIPOS}
    assert wa.tipos_a_disparar(datetime(2026, 10, 26, 23, 0, tzinfo=SP), _config(ligados=desligados)) == []
    assert wa.avisos_devidos(datetime(2026, 10, 26, 23, 0, tzinfo=SP), _config(ligados=desligados), _dados()) == []


def test_r9_orquestrador_na_ordem_do_run_jobs():
    avisos = wa.avisos_devidos(datetime(2026, 10, 26, 23, 0, tzinfo=SP), _config(), _dados())
    ordem = []
    for a in avisos:
        if not ordem or ordem[-1] != a.tipo:
            ordem.append(a.tipo)
    assert ordem == [wa.LEMBRETE_ALUNO, wa.AGENDA_PROFESSOR, wa.RENOVACAO, wa.ANIVERSARIO, wa.VENCIMENTO, wa.ATRASO, wa.TRES_MESES]


def test_r9_outra_unidade_nao_recebe_dados_da_primeira():
    outra = wa.ConfigAvisos(2, "Outra", _config().avisos, VARIAVEIS)
    avisos = wa.avisos_devidos(datetime(2026, 10, 26, 23, 0, tzinfo=SP), outra, _dados())
    # so a Fabi (aluna da outra unidade) e a agenda da Natalia com a aula da Fabi; nenhum dado da unidade 1
    assert {a.destinatario_nome for a in avisos} <= {"Fabi", "Natalia"}
    assert all("Ana" not in a.mensagem for a in avisos)


# ---------------------------------------------------------------- templates em branco / fallbacks ----------------

def test_r9_template_em_branco_usa_fallback_so_para_lembrete_professor_e_renovacao():
    vazio = {c: "" for c in wa.CAMPO_TEMPLATE_DO_TIPO.values()}
    cfg = _config(templates=vazio)
    dados = _dados()
    assert _avisos_enviar(wa.avisos_lembrete_aula(cfg, HOJE, dados.reservas)) == [c for c in _chamadas(g.EM_BRANCO, "lembrete_aluno") if c[0] not in ALUNOS_COM_TELEFONE_INVALIDO]
    prof = wa.avisos_agenda_professor(cfg, HOJE, dados.reservas)
    assert [(a.telefone, a.mensagem) for a in prof] == [(c[1], c[2]) for c in _chamadas(g.EM_BRANCO, "agenda_professor")]
    assert _avisos_enviar(wa.avisos_renovacao(cfg, HOJE, dados.contratos)) == _chamadas(g.EM_BRANCO, "renovacao")
    # aniversario, vencimento, atraso e 3 meses: sem fallback => nada e enviado (retorno 0 no antigo)
    for nome, avisos in [
        ("aniversario", wa.avisos_aniversario(cfg, HOJE, dados.alunos)), ("vencimento", wa.avisos_vencimento(cfg, HOJE, dados.contas)),
        ("atraso", wa.avisos_atraso(cfg, HOJE, dados.contas)), ("tres_meses", wa.avisos_tres_meses(cfg, HOJE, dados.contratos)),
    ]:
        assert g.EM_BRANCO[nome]["chamadas"] == []
        assert avisos and all(a.situacao in ("sem_mensagem", "sem_telefone") for a in avisos) and not _avisos_enviar(avisos)


# ---------------------------------------------------------------- renderização --------------------------------

@pytest.mark.parametrize("modelo,esperado", g.RENDER_VIEWS)
def test_r9_renderizar_template_igual_a_funcao_das_views(modelo, esperado):
    assert wa.renderizar_template(modelo, **g.CONTEXTO) == esperado


@pytest.mark.parametrize("modelo,esperado", g.RENDER_SCHEDULER)
def test_r9_renderizar_template_igual_a_funcao_do_scheduler(modelo, esperado):
    assert wa.renderizar_template(modelo, **g.CONTEXTO) == esperado


def test_r9_as_duas_funcoes_antigas_eram_equivalentes():
    assert g.RENDER_VIEWS == g.RENDER_SCHEDULER


def test_r9_variavel_ausente_fica_como_esta_e_none_vira_vazio():
    assert wa.renderizar_template("Oi {aluno} {x}", aluno="Ana") == "Oi Ana {x}"
    assert wa.renderizar_template("Oi {aluno}{v}", aluno="Ana", v=None) == "Oi Ana"
    assert wa.renderizar_template("  ", aluno="Ana") == ""
    assert wa.renderizar_template(None) == ""
    assert wa.renderizar_template("{aluno", aluno="Ana") == "{aluno"    # sintaxe invalida: devolve o texto


# ---------------------------------------------------------------- textos padrão --------------------------------

def test_r9_sete_textos_padrao_mais_dois_identicos_ao_antigo_apos_trocar_as_variaveis_de_estudio():
    assert set(wa.TEXTOS_PADRAO) == set(g.PADROES)
    for campo, antigo in g.PADROES.items():
        assert wa.renderizar_template(wa.TEXTOS_PADRAO[campo], **VARIAVEIS) == antigo, campo


def test_r9_textos_padrao_nao_trazem_cnpj_nem_chave_pix_nem_nome_do_estudio_fixos():
    for campo, texto in wa.TEXTOS_PADRAO.items():
        assert "50.732.875" not in texto and "Mayris" not in texto, campo
    assert "{PIX_CHAVE}" in wa.TEXTOS_PADRAO["template_mensalidade_atraso"]
    assert "{ESTUDIO_NOME}" in wa.TEXTOS_PADRAO["template_tres_meses"]


def test_r9_atraso_sem_pix_configurado_remove_a_linha_do_pix():
    cfg = _config(templates=wa.TEXTOS_PADRAO, variaveis={"ESTUDIO_NOME": "Estudio X", "PIX_TIPO": "", "PIX_CHAVE": ""})
    msg = wa.avisos_atraso(cfg, HOJE, _dados().contas)[0].mensagem
    assert "Pix" not in msg and "{PIX_CHAVE}" not in msg and "R$ 300,00" in msg
    com_pix = _config(templates=wa.TEXTOS_PADRAO, variaveis={"ESTUDIO_NOME": "X", "PIX_TIPO": "CPF", "PIX_CHAVE": "123.456.789-09"})
    assert "Chave Pix (CPF): 123.456.789-09" in wa.avisos_atraso(com_pix, HOJE, _dados().contas)[0].mensagem


def test_r9_tres_meses_usa_o_nome_do_estudio_configurado():
    cfg = _config(templates=wa.TEXTOS_PADRAO, variaveis={"ESTUDIO_NOME": "Studio Lua", "PIX_TIPO": "", "PIX_CHAVE": ""})
    msg = wa.avisos_tres_meses(cfg, HOJE, _dados().contratos)[0].mensagem
    assert "confiar na Studio Lua para cuidar de você" in msg


def test_r9_fallbacks_embutidos():
    assert wa.template_efetivo(wa.LEMBRETE_ALUNO, "  ") == g.PADROES["template_aviso_aluno"]
    assert wa.template_efetivo(wa.AGENDA_PROFESSOR, None) == g.PADROES["template_aviso_professor"]
    assert wa.template_efetivo(wa.RENOVACAO, "") == g.PADROES["template_aviso_renovacao"]
    assert wa.template_efetivo(wa.ATRASO, "") == ""
    assert wa.template_efetivo(wa.ATRASO, "meu texto") == "meu texto"


# ---------------------------------------------------------------- execução em lote -----------------------------

@pytest.mark.parametrize("resposta,caiu", g.SESSAO_CAIU)
def test_r9_sessao_do_whatsapp_caiu_igual_ao_antigo(resposta, caiu):
    assert wa.sessao_do_whatsapp_caiu(resposta) is caiu


@pytest.mark.parametrize("resposta,pausas,final", g.RETRY)
def test_r9_pausa_entre_tentativas_igual_ao_antigo(resposta, pausas, final):
    assert wa.TENTATIVAS_POR_ENVIO == 3 and wa.INTERVALO_ENTRE_ENVIOS_SEGUNDOS == 5.0
    if wa.envio_deu_certo(resposta):
        assert pausas == []
        return
    # 3 tentativas => 2 pausas, cada uma recalculada a partir da anterior
    pausa = wa.INTERVALO_ENTRE_ENVIOS_SEGUNDOS
    esperadas = []
    for _ in range(wa.TENTATIVAS_POR_ENVIO - 1):
        pausa = wa.proxima_pausa_de_retry(resposta, pausa)
        esperadas.append(pausa)
    assert esperadas == pausas


def test_r9_formatar_valor():
    assert wa.formatar_valor(300) == "300,00"
    assert wa.formatar_valor("150.5") == "150,50"
    assert wa.formatar_valor(None) == ""
    assert wa.formatar_valor("abc") == ""


def test_r9_telefone_para_whatsapp_prefere_celular_e_ignora_fixo_e_lixo():
    assert wa.telefone_para_whatsapp(["(15) 3333-4444", "(15) 99776-2467"]) == "5515997762467"
    assert wa.telefone_para_whatsapp(["(15) 3333-4444"]) is None
    assert wa.telefone_para_whatsapp(["123", ""]) is None
    assert wa.telefone_para_whatsapp([]) is None
    assert wa.telefone_para_whatsapp(["1597762467"]) == "5515997762467"     # sem o nono digito: ganha o 9


def test_r9_linhas_sem_variavel_vazia():
    texto = "a\nPix {PIX_CHAVE}\nb"
    assert wa.linhas_sem_variavel_vazia(texto, {"PIX_CHAVE": ""}) == "a\nb"
    assert wa.linhas_sem_variavel_vazia(texto, {"PIX_CHAVE": "x"}) == texto
    assert wa.linhas_sem_variavel_vazia(texto, {}) == texto
