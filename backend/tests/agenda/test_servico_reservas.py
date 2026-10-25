from datetime import UTC, date, datetime

import pytest

from app.modules.agenda import servico
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from tests.agenda import fabrica

AGORA = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


def vagas(db, ses):
    db.expire_all()
    return db.get(AulaSessao, ses.id).reservas_ativas


def test_criar_reserva_ocupa_vaga(db, cenario):
    r = servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    db.commit()
    assert r.status == StatusReserva.RESERVADA
    assert vagas(db, cenario.ses) == 1


def test_r3_capacidade_mensagem_clara(db, cenario):
    servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    servico.criar_reserva(db, cenario.a2.id, cenario.ses.id)
    a3 = fabrica.aluno(db, cenario.un, "Carla")
    with pytest.raises(servico.Conflito) as e:
        servico.criar_reserva(db, a3.id, cenario.ses.id)
    assert "2 de 2 vagas ocupadas" in e.value.mensagem
    assert "26/10" in e.value.mensagem and "09:00" in e.value.mensagem
    db.rollback()


def test_reserva_duplicada_recusada(db, cenario):
    servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    with pytest.raises(servico.Conflito):
        servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)


def test_reserva_nao_ocupa_vaga_se_nao_for_reservada(db, cenario):
    servico.criar_reserva(db, cenario.a1.id, cenario.ses.id, status=StatusReserva.PENDENTE)
    assert vagas(db, cenario.ses) == 0


def test_aluno_ou_aula_inexistente(db, cenario):
    with pytest.raises(servico.NaoEncontrado):
        servico.criar_reserva(db, 9999, cenario.ses.id)
    with pytest.raises(servico.NaoEncontrado):
        servico.criar_reserva(db, cenario.a1.id, 9999)


def test_falha_nao_deixa_vaga_ocupada(db, cenario):
    servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    servico.criar_reserva(db, cenario.a2.id, cenario.ses.id)
    a3 = fabrica.aluno(db, cenario.un, "Carla")
    with pytest.raises(servico.Conflito):
        servico.criar_reserva(db, a3.id, cenario.ses.id)
    assert vagas(db, cenario.ses) == 2


def test_desmarcar_r4(db, cenario):
    r = servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    r.confirmada_em = AGORA
    servico.desmarcar_reserva(db, r.id, agora=AGORA)
    db.commit()
    db.expire_all()
    r = db.get(Reserva, r.id)
    assert r.status == StatusReserva.CANCELADA
    assert r.confirmada_em is None
    assert r.desmarcada_em == AGORA
    assert r.reposicao_ate == date(2026, 11, 25)  # 26/10 + 30 dias
    assert vagas(db, cenario.ses) == 0


def test_professor_nao_desmarca(db, cenario):
    r = servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    with pytest.raises(servico.SemPermissao):
        servico.desmarcar_reserva(db, r.id, agora=AGORA, eh_professor=True)


def test_desmarcar_duas_vezes_recusa(db, cenario):
    r = servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    servico.desmarcar_reserva(db, r.id, agora=AGORA)
    with pytest.raises(servico.Conflito):
        servico.desmarcar_reserva(db, r.id, agora=AGORA)


def test_acoes_de_presenca_mexem_na_vaga(db, cenario):
    r = servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    servico.aplicar_acao_presenca(db, r.id, "faltou")
    assert r.status == StatusReserva.FALTOU_SEM_AVISAR and vagas(db, cenario.ses) == 0
    servico.aplicar_acao_presenca(db, r.id, "chegou", agora=AGORA)
    assert r.status == StatusReserva.RESERVADA and vagas(db, cenario.ses) == 1
    assert r.confirmada_em == AGORA
    servico.aplicar_acao_presenca(db, r.id, "finalizar")
    assert r.status == StatusReserva.CONCLUIDA and vagas(db, cenario.ses) == 0
    servico.aplicar_acao_presenca(db, r.id, "faltou_avisou")
    assert r.status == StatusReserva.FALTOU_AVISOU
    with pytest.raises(servico.Invalido):
        servico.aplicar_acao_presenca(db, r.id, "dancar")


def test_chegou_em_aula_lotada_recusa(db, cenario):
    r1 = servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    servico.criar_reserva(db, cenario.a2.id, cenario.ses.id)
    servico.aplicar_acao_presenca(db, r1.id, "faltou")
    a3 = fabrica.aluno(db, cenario.un, "Carla")
    servico.criar_reserva(db, a3.id, cenario.ses.id)  # ocupa a vaga liberada
    with pytest.raises(servico.Conflito, match="2 de 2"):
        servico.aplicar_acao_presenca(db, r1.id, "chegou")
    assert r1.status == StatusReserva.FALTOU_SEM_AVISAR
