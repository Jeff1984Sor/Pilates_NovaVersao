"""R3 - capacidade, vagas e mensagens. Caracterização contra Reserva.clean e aula_remarcar_api."""
from datetime import date, time

import pytest

from app.domain import capacidade as cap
from tests.domain.golden import golden_capacidade as g


def test_r3_capacidade_efetiva_sessao_ou_unidade():
    # EFETIVAS = (capacidade da sessão, capacidade da unidade, resultado do antigo)
    for sessao, unidade, esperado in g.EFETIVAS:
        assert cap.capacidade_efetiva(sessao, unidade) == esperado


def test_r3_zero_na_sessao_nao_cai_para_a_unidade():
    assert cap.capacidade_efetiva(0, 9) == 0
    assert cap.capacidade_efetiva(None, 9) == 9
    assert cap.capacidade_efetiva(None, None) == 0


def test_r3_so_reservada_ocupa_vaga():
    assert cap.contar_ocupadas(["RESERVADA", "PENDENTE", "CONCLUIDA", "CANCELADA", "FALTOU_AVISOU", "RESERVADA"]) == 2


def test_r3_sessao_cap_1_com_1_reserva_recusa_a_segunda():
    assert cap.pode_reservar(1, 0) is True
    assert cap.pode_reservar(1, 1) is False
    assert cap.pode_reservar(2, 1) is True
    assert cap.pode_reservar(2, 2) is False


def test_r3_capacidade_zero_ou_nula_nao_tem_vaga_como_no_clean_antigo():
    assert g.ZERO_RECUSA is True  # Reserva.clean antigo recusa com capacidade 0
    assert cap.pode_reservar(0, 0) is False
    assert cap.pode_reservar(None, 0) is False


def test_r3_mensagem_de_erro_identica_ao_clean_antigo():
    esperado = g.MSG_CLEAN[0]  # aula 12/10 08:00, 2 de 2
    assert cap.mensagem_capacidade_excedida(date(2026, 10, 12), time(8, 0), 2, 2) == esperado
    assert cap.validar_reserva("RESERVADA", 2, 2, date(2026, 10, 12), time(8, 0)) == esperado
    assert cap.validar_reserva("RESERVADA", 0, 0, date(2026, 10, 14), time(8, 0)) == g.MSG_ZERO[0]


def test_r3_validar_reserva_so_vale_para_reservada():
    for status, passou in g.OK_POR_STATUS.items():
        assert passou is True
        assert cap.validar_reserva(status, 2, 2, date(2026, 10, 12), time(8, 0)) is None
    assert cap.validar_reserva("RESERVADA", 2, 1, date(2026, 10, 12), time(8, 0)) is None


def test_r3_mensagem_de_remarcacao_identica_a_api_antiga():
    status, corpo = g.REMARCAR_CHEIA
    assert status == 400
    assert cap.mensagem_sem_vaga_remarcacao(date(2026, 10, 12), time(8, 0), 2, 2) == corpo["error"]


def test_r3_remarcar_com_capacidade_zero_passava_no_antigo():
    # COMPORTAMENTO ANTIGO: aula_remarcar_api so recusava "if capacidade and total >= capacidade"
    status, ok = g.REMARCAR_CAP_ZERO
    assert (status, ok) == (200, True)
    assert cap.pode_remarcar_comportamento_antigo(0, 0) is True
    assert cap.pode_remarcar_comportamento_antigo(2, 2) is False
    assert cap.pode_remarcar_comportamento_antigo(2, 1) is True
    # e a regra unificada nova recusa:
    assert cap.pode_reservar(0, 0) is False


@pytest.mark.parametrize(
    "capacidade,ocupadas,atual,listado",
    [
        (3, 0, False, True),
        (3, 2, False, True),
        (3, 3, False, False),   # lotado
        (0, 0, False, False),   # capacidade <= 0 = sem vagas
        (-1, 0, False, False),
        (None, 0, False, False),
        (3, 3, True, True),     # o slot da própria reserva sempre aparece
        (0, 0, True, True),
    ],
)
def test_r3_slot_deve_ser_listado(capacidade, ocupadas, atual, listado):
    assert cap.slot_deve_ser_listado(capacidade, ocupadas, atual) is listado


def test_r3_vagas_livres_e_rotulo():
    assert cap.vagas_livres(3, 1) == 2
    assert cap.vagas_livres(3, 5) == 0
    assert cap.vagas_livres(None, 0) == 0
    assert cap.rotulo_slot(time(8, 0), time(8, 50), "Natalia", 3, 1) == "08:00 - 08:50 | Natalia (2 vaga(s))"
    assert cap.rotulo_slot(time(8, 0), time(8, 50), None, 3, 3) == "08:00 - 08:50 (0 vaga(s))"
    assert cap.rotulo_slot(time(8, 0), time(8, 50), None, 0, 0) == "08:00 - 08:50"
