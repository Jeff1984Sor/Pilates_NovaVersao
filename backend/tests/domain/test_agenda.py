"""Agenda: slots, bloqueios, funcionamento, agenda do contrato e do pacote avulso.

Caracterização contra views._generate_slots_for_date, _is_slot_blocked, _load_funcionamento, _load_bloqueios e
contrato_agenda (rodados de verdade no sistema antigo, ver golden_gen/gerar_golden.py).
"""
from datetime import date, time

import pytest

from app.domain import agenda as ag
from tests.domain.golden import golden_agenda as g

P, A = 1, 2  # ids sintéticos de tipo de serviço (Pilates, Alongamento)


# ---------------------------------------------------------------- slots ---------------------------------------

@pytest.mark.parametrize("janelas,duracao,esperado", g.SLOTS)
def test_slots_do_dia_identicos_ao_antigo(janelas, duracao, esperado):
    assert ag.gerar_slots_do_dia(date(2026, 11, 2), janelas, duracao) == esperado


def test_slots_exemplo_8_as_12_com_50_minutos_e_intervalo_de_10():
    slots = ag.gerar_slots_do_dia(date(2026, 11, 2), [(time(8, 0), time(12, 0))], 50)
    assert slots == [(time(8, 0), time(8, 50)), (time(9, 0), time(9, 50)), (time(10, 0), time(10, 50)), (time(11, 0), time(11, 50))]
    assert ag.AULA_INTERVALO_MINUTOS == 10


def test_slots_inicio_quebrado_sobe_para_a_proxima_hora():
    # COMPORTAMENTO ANTIGO: janela 08:30-12:00 comeca as 09:00
    slots = ag.gerar_slots_do_dia(date(2026, 11, 2), [ag.Janela(0, time(8, 30), time(12, 0))], 50)
    assert slots[0] == (time(9, 0), time(9, 50))


def test_duracao_da_unidade_padrao_50():
    assert ag.duracao_da_unidade(None) == 50
    assert ag.duracao_da_unidade(0) == 50
    assert ag.duracao_da_unidade(60) == 60


# ---------------------------------------------------------------- bloqueios -------------------------------------

def _bloq(d: dict) -> ag.Bloqueio:
    return ag.Bloqueio(
        hora_inicio=d["horaInicio"], hora_fim=d["horaFim"], data_inicio=d["dataInicio"], data_fim=d["dataFim"],
        recorrente=d["recorrente"], dia_semana=d["diaSemana"],
    )


@pytest.mark.parametrize("nome,dia,ini,fim,esperado", g.BLOQUEADOS)
def test_slot_bloqueado_identico_ao_antigo(nome, dia, ini, fim, esperado):
    assert ag.slot_bloqueado([_bloq(g.BLOQUEIOS_DEF[nome])], dia, ini, fim) is esperado


@pytest.mark.parametrize("dia,ini,fim,esperado", g.BLOQUEADOS_JUNTOS)
def test_slot_bloqueado_varios_bloqueios(dia, ini, fim, esperado):
    todos = [_bloq(d) for d in g.BLOQUEIOS_DEF.values()]
    assert ag.slot_bloqueado(todos, dia, ini, fim) is esperado


def test_bloqueio_encostar_na_borda_nao_bloqueia():
    b = ag.Bloqueio(time(9, 0), time(10, 0), date(2026, 11, 2))
    assert not ag.slot_bloqueado([b], date(2026, 11, 2), time(8, 10), time(9, 0))
    assert not ag.slot_bloqueado([b], date(2026, 11, 2), time(10, 0), time(10, 50))
    assert ag.slot_bloqueado([b], date(2026, 11, 2), time(9, 50), time(10, 40))


def test_bloqueio_recorrente_sem_dia_da_semana_nunca_bloqueia():
    # COMPORTAMENTO ANTIGO: recorrente com diaSemana None e ignorado
    b = ag.Bloqueio(time(0, 0), time(23, 59), date(2026, 1, 1), recorrente=True, dia_semana=None)
    assert not ag.slot_bloqueado([b], date(2026, 11, 2), time(8, 0), time(8, 50))


# ---------------------------------------------------------------- funcionamento -------------------------------

def _janelas_do_golden() -> list[ag.Janela]:
    ids = {"P": P, "A": A}
    lista = []
    for dia, ini, fim, ativo, fk, m2m in g.HORARIOS_DEF:
        servicos = frozenset(ids[c] for c in (fk + m2m))
        lista.append(ag.Janela(dia, ini, fim, ativo, servicos))
    return lista


@pytest.mark.parametrize("rotulo,tipo", [("todos", None), ("P", P), ("A", A)])
def test_janelas_por_dia_identico_ao_load_funcionamento_antigo(rotulo, tipo):
    resultado = ag.janelas_por_dia(_janelas_do_golden(), tipo)
    como_tuplas = {dia: [(j.hora_inicio, j.hora_fim) for j in itens] for dia, itens in sorted(resultado.items())}
    assert como_tuplas == g.FUNCIONAMENTO[rotulo]


def test_janela_especifica_do_servico_substitui_a_generica_do_mesmo_dia():
    janelas = [ag.Janela(0, time(8, 0), time(12, 0)), ag.Janela(0, time(14, 0), time(18, 0), servicos=frozenset({P}))]
    assert [j.hora_inicio for j in ag.janelas_por_dia(janelas, P)[0]] == [time(14, 0)]
    assert [j.hora_inicio for j in ag.janelas_por_dia(janelas, A)[0]] == [time(8, 0)]


# ---------------------------------------------------------------- bloqueios aplicaveis (banco) ---------------

def test_bloqueios_aplicaveis_identico_ao_load_bloqueios_antigo():
    tipo_ids = {"nenhum": None, "P": P, "A": A}
    prof_ids = {"sem": None, "1": 1, "2": 2}
    objetos = []
    for rec, dia, ini, fim, hi, hf, ativo, tipo, prof in g.BLOQ_DB_DEF:
        objetos.append(ag.Bloqueio(
            hora_inicio=hi, hora_fim=hf, data_inicio=ini, data_fim=fim, recorrente=rec, dia_semana=dia, ativo=ativo,
            tipo_servico_id={"P": P, "A": A}.get(tipo), profissional_id=int(prof) if prof else None,
        ))
    for tipo_rot, prof_rot, ini, fim, indices in g.BLOQ_DB_CARREGADOS:
        achados = ag.bloqueios_aplicaveis(objetos, tipo_ids[tipo_rot], prof_ids[prof_rot], ini, fim)
        assert sorted(next(i for i, o in enumerate(objetos) if o is b) for b in achados) == indices, (tipo_rot, prof_rot, ini, fim)


# ---------------------------------------------------------------- agenda do contrato --------------------------

def test_contrato_semanal_limita_a_4_semanas_e_1_aula():
    assert ag.aulas_por_semana_do_contrato("SEMANAL", 3) == 1
    assert ag.aulas_por_semana_do_contrato("MENSAL", 3) == 3
    assert ag.aulas_por_semana_do_contrato("MENSAL", 0) == 1
    assert ag.aulas_por_semana_do_contrato("MENSAL", None) == 1
    assert ag.fim_da_agenda_do_contrato("SEMANAL", date(2026, 11, 2), date(2027, 2, 2)) == date(2026, 11, 29)
    assert ag.fim_da_agenda_do_contrato("SEMANAL", date(2026, 11, 2), date(2026, 11, 10)) == date(2026, 11, 10)
    assert ag.fim_da_agenda_do_contrato("MENSAL", date(2026, 11, 2), date(2027, 2, 2)) == date(2027, 2, 2)


def test_datas_por_dia_da_semana():
    datas = ag.datas_por_dia_da_semana(date(2026, 11, 2), date(2026, 11, 15))
    assert datas[0] == [date(2026, 11, 2), date(2026, 11, 9)]
    assert datas[6] == [date(2026, 11, 8), date(2026, 11, 15)]
    assert sum(len(v) for v in datas.values()) == 14


def _selecao(valor, prof, dia_informado=None):
    dia, ini, fim = ag.interpretar_valor_slot(valor)
    return ag.SelecaoHorario(dia, ini, fim, prof, dia_informado)


def _cenario_a():
    ids = g.IDS_A
    janelas = {0: [ag.Janela(0, time(8, 0), time(11, 0))], 2: [ag.Janela(2, time(9, 0), time(10, 0))]}
    inicio, fim = date(2026, 11, 2), date(2026, 11, 30)
    datas = ag.datas_por_dia_da_semana(inicio, fim)
    bloq_p1 = ag.Bloqueio(time(8, 0), time(12, 0), date(2026, 11, 16))
    bloqueios = {ids["admin"]: [], ids["p1"]: [bloq_p1], ids["p2"]: []}
    sessoes = {ids["p2"]: {(date(2026, 11, 23), time(8, 0), time(8, 50)): ag.SessaoExistente(ocupadas=2)}}
    slots = ag.slots_permitidos_do_contrato(janelas, datas, 50, list(ids.values()), bloqueios, sessoes, 2)
    return ids, inicio, fim, bloqueios, sessoes, slots


def test_agenda_contrato_slots_oferecidos_identicos_a_tela_antiga():
    _, _, _, _, _, slots = _cenario_a()
    como_texto = sorted((ag.valor_do_slot(*chave), profs) for chave, profs in slots.items())
    assert como_texto == sorted(g.OPCOES_A)


CASOS_ERRO = {
    "uma_so": lambda i: [_selecao("0|09:00|09:50", i["p2"])],
    "repetido": lambda i: [_selecao("0|09:00|09:50", i["p2"]), _selecao("0|09:00|09:50", i["p2"])],
    "mesmo_dia": lambda i: [_selecao("0|09:00|09:50", i["p2"]), _selecao("0|10:00|10:50", i["p2"])],
    "slot_inexistente": lambda i: [_selecao("0|08:30|09:20", i["p2"]), _selecao("2|09:00|09:50", i["p2"])],
    "prof_nao_permitido": lambda i: [_selecao("0|09:00|09:50", i["p1"]), _selecao("2|09:00|09:50", i["p1"])],
    "sem_prof": lambda i: [_selecao("0|09:00|09:50", None), _selecao("2|09:00|09:50", i["p2"])],
    "dia_nao_confere": lambda i: [_selecao("0|09:00|09:50", i["p2"], dia_informado=2), _selecao("2|09:00|09:50", i["p2"])],
    "parcial_depois_invalido": lambda i: [_selecao("0|09:00|09:50", i["p2"]), _selecao("2|09:30|10:20", i["p2"])],
}


@pytest.mark.parametrize("nome,_http,mensagens,_reservas_parciais", [e for e in g.ERROS_A if e[0] in CASOS_ERRO])
def test_agenda_contrato_validacao_com_a_mesma_mensagem_do_antigo(nome, _http, mensagens, _reservas_parciais):
    ids, _, _, _, _, slots = _cenario_a()
    selecoes = CASOS_ERRO[nome](ids)
    erro = ag.validar_selecao(selecoes, 2) or ag.validar_selecao_nos_slots(selecoes, slots)
    assert [erro] == mensagens


def test_agenda_contrato_formato_de_slot_invalido():
    erro = next(e for e in g.ERROS_A if e[0] == "formato_ruim")
    with pytest.raises(ValueError) as exc:
        ag.interpretar_valor_slot("lixo")
    assert [str(exc.value)] == erro[2]
    assert ag.interpretar_valor_slot("2|09:00|09:50") == (2, time(9, 0), time(9, 50))
    assert ag.valor_do_slot(2, time(9, 0), time(9, 50)) == "2|09:00|09:50"


def test_agenda_contrato_validacao_antigo_aplicava_efeitos_parciais():
    """COMPORTAMENTO ANTIGO: uma escolha valida ja criava as reservas antes de a seguinte ser recusada
    (casos 'repetido', 'mesmo_dia', 'parcial_depois_invalido'). O dominio novo valida TUDO antes de planejar."""
    for nome in ("repetido", "mesmo_dia", "parcial_depois_invalido", "sem_prof"):
        entrada = next(e for e in g.ERROS_A if e[0] == nome)
        assert entrada[3], nome  # o antigo deixou reservas criadas apesar do erro
    ids = g.IDS_A
    selecoes = CASOS_ERRO["repetido"](ids)
    assert ag.validar_selecao(selecoes, 2) == "Nao repita o mesmo horario."


def test_agenda_contrato_caminho_feliz_cria_as_mesmas_reservas():
    ids, inicio, fim, bloqueios, sessoes, _ = _cenario_a()
    selecoes = [_selecao("0|09:00|09:50", ids["p2"]), _selecao("2|09:00|09:50", ids["admin"])]
    assert ag.validar_selecao(selecoes, 2) is None
    plano = ag.planejar_agenda_contrato(selecoes, inicio, fim, bloqueios, sessoes, 2)
    assert plano.conflitos == []
    criadas = sorted((r.data, r.inicio, r.fim, r.profissional_id, "RESERVADA") for r in plano.reservas)
    assert criadas == sorted(g.OK_A[2])


def test_agenda_contrato_fallback_sem_horarios_configurados_com_bloqueio_e_sessao_cheia():
    p1 = g.OK_B[3]["p1"]
    sessoes_db = [
        (date(2026, 11, 2), time(8, 0), time(8, 50), 0, 2),
        (date(2026, 11, 23), time(8, 0), time(8, 50), 2, 2),
    ]
    slots = ag.slots_por_sessoes_existentes(sessoes_db)
    assert [(ag.valor_do_slot(*k), v) for k, v in slots.items()] == g.OPCOES_B

    bloqueios = {p1: [ag.Bloqueio(time(8, 0), time(12, 0), date(2026, 11, 16), date(2026, 11, 16))]}
    sessoes = {p1: {(date(2026, 11, 2), time(8, 0), time(8, 50)): ag.SessaoExistente(0),
                    (date(2026, 11, 23), time(8, 0), time(8, 50)): ag.SessaoExistente(2)}}
    selecoes = [_selecao("0|08:00|08:50", p1)]
    plano = ag.planejar_agenda_contrato(selecoes, date(2026, 11, 2), date(2026, 11, 30), bloqueios, sessoes, 2)
    assert sorted((r.data, r.inicio, r.fim, r.profissional_id, "RESERVADA") for r in plano.reservas) == g.OK_B[2]
    assert [ag.mensagem_conflitos(plano.conflitos)] == g.OK_B[1]
    # sessao que ja existe so precisa da reserva; a de 09/11 precisa ser criada
    existe = {r.data: r.sessao_existe for r in plano.reservas}
    assert existe == {date(2026, 11, 2): True, date(2026, 11, 9): False, date(2026, 11, 30): False}


def test_agenda_contrato_semanal_quatro_semanas_uma_aula():
    aulas = ag.aulas_por_semana_do_contrato("SEMANAL", 3)
    assert (aulas, ag.SEMANAS_AGENDA_CONTRATO_SEMANAL) == g.SEMANAL_INFO[:2]
    fim_agenda = ag.fim_da_agenda_do_contrato("SEMANAL", date(2026, 11, 2), date(2027, 2, 2))
    selecoes = [_selecao("0|09:00|09:50", 10)]
    plano = ag.planejar_agenda_contrato(selecoes, date(2026, 11, 2), fim_agenda, {}, {}, 2)
    assert sorted((r.data, r.inicio, r.fim, r.profissional_id, "RESERVADA") for r in plano.reservas) == g.OK_C[2]
    assert ag.validar_selecao(selecoes, aulas) is None


def test_agenda_contrato_reserva_ja_existente_e_idempotente():
    sessoes = {1: {(date(2026, 11, 2), time(9, 0), time(9, 50)): ag.SessaoExistente(1, aluno_ja_reservado=True)}}
    plano = ag.planejar_agenda_contrato([_selecao("0|09:00|09:50", 1)], date(2026, 11, 2), date(2026, 11, 2), {}, sessoes, 2)
    assert plano.reservas == [] and plano.conflitos == []


def test_agenda_contrato_selecao_sem_professor_e_ignorada_no_plano():
    plano = ag.planejar_agenda_contrato([_selecao("0|09:00|09:50", None)], date(2026, 11, 2), date(2026, 11, 30), {}, {}, 2)
    assert plano.reservas == [] and plano.conflitos == []


def test_slots_do_contrato_ignora_dia_sem_datas_no_periodo():
    janelas = {3: [ag.Janela(3, time(8, 0), time(10, 0))]}
    datas = ag.datas_por_dia_da_semana(date(2026, 11, 2), date(2026, 11, 3))  # seg e ter
    assert ag.slots_permitidos_do_contrato(janelas, datas, 50, [1], {}, {}, 2) == {}


# ---------------------------------------------------------------- aula avulsa ---------------------------------

@pytest.mark.parametrize("base,dia,esperado", g.ALINHAR)
def test_alinhar_ao_dia_da_semana_identico_ao_antigo(base, dia, esperado):
    assert ag.alinhar_ao_dia_da_semana(base, dia) == esperado


@pytest.mark.parametrize("base,rec,idx,esperado", g.AVANCAR)
def test_avancar_recorrencia_identico_ao_antigo(base, rec, idx, esperado):
    assert ag.avancar_recorrencia(base, rec, idx) == esperado


def test_datas_do_pacote_avulso_marcam_fora_do_periodo():
    # pacote semanal de 4 aulas na quarta, de 26/10 a 23/11 (inicio + 28 dias)
    datas = ag.datas_aula_avulsa(date(2026, 10, 26), 2, "SEMANAL", 4, date(2026, 11, 23))
    assert [(d.data, d.fora_do_periodo) for d in datas] == [
        (date(2026, 10, 28), False), (date(2026, 11, 4), False), (date(2026, 11, 11), False), (date(2026, 11, 18), False),
    ]
    curto = ag.datas_aula_avulsa(date(2026, 10, 26), 2, "SEMANAL", 4, date(2026, 11, 8))
    assert [d.fora_do_periodo for d in curto] == [False, False, True, True]
    assert len(ag.datas_aula_avulsa(date(2026, 10, 26), 2, "MENSAL", 0, date(2026, 12, 1))) == 1
