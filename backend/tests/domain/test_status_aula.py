"""R5 e R6 - status exibido e conclusão automática. Caracterização contra views._map_status e services.concluir_aulas_passadas."""
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain import status_aula as sa
from tests.domain.golden import golden_status_aula as g

SP = ZoneInfo("America/Sao_Paulo")
INICIO = datetime(2026, 10, 26, 9, 0, tzinfo=SP)
FIM = datetime(2026, 10, 26, 9, 50, tzinfo=SP)
MOMENTOS = [
    datetime(2026, 10, 26, 8, 59, 59, tzinfo=SP), INICIO, datetime(2026, 10, 26, 9, 25, tzinfo=SP), FIM,
    datetime(2026, 10, 26, 9, 50, 1, tzinfo=SP),
]


@pytest.mark.parametrize("status,indice_momento,esperado", g.MAPA_STATUS)
def test_r5_status_exibido_identico_ao_antigo(status, indice_momento, esperado):
    assert sa.status_exibido(status, INICIO, FIM, MOMENTOS[indice_momento]) == esperado


def test_r5_tabela_completa():
    assert sa.MAPA_STATUS_EXIBIDO == {
        "RESERVADA": "aguardando_chegar", "PENDENTE": "aguardando_chegar", "CONCLUIDA": "finalizada",
        "FALTOU_AVISOU": "faltou", "FALTOU_SEM_AVISAR": "faltou", "CANCELADA": "remarcada",
    }


def test_r5_em_aula_so_para_reservada_e_pendente_dentro_do_horario_inclusive():
    assert sa.status_exibido("RESERVADA", INICIO, FIM, INICIO) == "em_aula"
    assert sa.status_exibido("RESERVADA", INICIO, FIM, FIM) == "em_aula"
    assert sa.status_exibido("CONCLUIDA", INICIO, FIM, INICIO) == "finalizada"
    assert sa.status_exibido("CANCELADA", INICIO, FIM, INICIO) == "remarcada"


def test_r5_fusos_diferentes_sao_comparados_em_instante_absoluto():
    utc = datetime(2026, 10, 26, 12, 30, tzinfo=UTC)  # 09:30 em Brasília
    assert sa.status_exibido("RESERVADA", INICIO, FIM, utc) == "em_aula"


def test_r5_datetime_sem_fuso_e_horario_de_brasilia():
    assert sa.status_exibido("RESERVADA", INICIO, FIM, datetime(2026, 10, 26, 9, 30)) == "em_aula"
    assert sa.momento_da_sessao(date(2026, 10, 26), time(9, 0)) == INICIO


def _reservas_do_golden():
    return [
        sa.ReservaSimples(i, st, d, hf) for i, (st, d, hf, _rot, _final) in enumerate(g.CONCLUIR)
    ]


def test_r6_reservas_a_concluir_identico_ao_antigo():
    reservas = _reservas_do_golden()
    escolhidas = {r.id for r in sa.reservas_a_concluir(g.AGORA_CONCLUIR, reservas)}
    esperadas = {i for i, (_st, _d, _hf, _rot, final) in enumerate(g.CONCLUIR) if final == "CONCLUIDA" and _st != "CONCLUIDA"}
    assert escolhidas == esperadas
    assert len(escolhidas) == g.CONCLUIDAS_TOTAL


def test_r6_so_reservada_e_pendente_viram_concluida():
    agora = datetime(2026, 10, 26, 10, 0, tzinfo=SP)
    for status in ("CONCLUIDA", "CANCELADA", "FALTOU_AVISOU", "FALTOU_SEM_AVISAR"):
        assert not sa.deve_concluir(status, date(2026, 10, 20), time(9, 0), agora)
    for status in ("RESERVADA", "PENDENTE"):
        assert sa.deve_concluir(status, date(2026, 10, 20), time(9, 0), agora)


def test_r6_hoje_so_depois_do_fim_da_aula_inclusive():
    agora = datetime(2026, 10, 26, 10, 0, tzinfo=SP)
    assert sa.deve_concluir("RESERVADA", date(2026, 10, 26), time(10, 0), agora)
    assert not sa.deve_concluir("RESERVADA", date(2026, 10, 26), time(10, 1), agora)
    assert not sa.deve_concluir("RESERVADA", date(2026, 10, 27), time(8, 0), agora)


def test_r6_virada_do_dia_usa_fuso_de_brasilia_nao_utc():
    # 27/10 01:30 UTC ainda é 26/10 22:30 em Brasília: a aula de 26/10 22:00-22:50 já terminou e a de 23:30 não.
    agora_utc = datetime(2026, 10, 27, 1, 30, tzinfo=UTC)
    assert sa.deve_concluir("RESERVADA", date(2026, 10, 26), time(22, 20), agora_utc)
    assert not sa.deve_concluir("RESERVADA", date(2026, 10, 26), time(23, 30), agora_utc)
