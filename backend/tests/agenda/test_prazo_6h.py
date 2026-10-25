"""Regra das 6 horas para desmarcar (decisão do Jefferson, 25/10/2026): equipe, exceção do Full e auditoria."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.agenda import routes, servico
from app.modules.agenda.models import Reserva, StatusReserva
from tests.conftest import auth

# a aula do cenário é 26/10/2026 09:00 em Brasília = 12:00 UTC; o prazo termina às 03:00 de Brasília = 06:00 UTC
LIMITE = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)


@pytest.fixture
def reserva(db, cenario):
    r = servico.criar_reserva(db, cenario.a1.id, cenario.ses.id)
    db.commit()
    return r


def relogio(monkeypatch, momento):
    monkeypatch.setattr(routes, "_agora", lambda: momento)


def desmarcar(client, token, rid, **corpo):
    return client.post(f"/api/aulas/reservas/{rid}/desmarcar", json=corpo or None, headers=auth(token))


def test_limite_exato_de_6_horas_ainda_desmarca(client, monkeypatch, secretaria, reserva):
    relogio(monkeypatch, LIMITE)
    assert desmarcar(client, secretaria, reserva.id).status_code == 200


def test_um_segundo_depois_do_limite_409_com_o_horario_limite(client, monkeypatch, secretaria, reserva, db):
    relogio(monkeypatch, datetime(2026, 10, 26, 6, 0, 1, tzinfo=UTC))
    r = desmarcar(client, secretaria, reserva.id)
    assert r.status_code == 409
    assert "6 horas" in r.json()["detail"] and "26/10/2026" in r.json()["detail"] and "03:00" in r.json()["detail"]
    db.expire_all()
    assert db.get(Reserva, reserva.id).status == StatusReserva.RESERVADA


def test_secretaria_nao_abre_excecao(client, monkeypatch, secretaria, reserva):
    relogio(monkeypatch, datetime(2026, 10, 26, 10, 0, tzinfo=UTC))
    assert desmarcar(client, secretaria, reserva.id, excecao_prazo=True, motivo="Aluna avisou por telefone").status_code == 403


def test_full_precisa_de_motivo_para_a_excecao(client, monkeypatch, full, reserva):
    relogio(monkeypatch, datetime(2026, 10, 26, 10, 0, tzinfo=UTC))
    assert desmarcar(client, full, reserva.id).status_code == 409
    assert desmarcar(client, full, reserva.id, excecao_prazo=True).status_code == 422
    assert desmarcar(client, full, reserva.id, excecao_prazo=True, motivo="  ").status_code == 422


def test_full_com_excecao_desmarca_grava_motivo_na_reserva_e_na_auditoria(client, monkeypatch, full, reserva, db):
    relogio(monkeypatch, datetime(2026, 10, 26, 10, 0, tzinfo=UTC))
    r = desmarcar(client, full, reserva.id, excecao_prazo=True, motivo="Aluna internada")
    assert r.status_code == 200
    db.expire_all()
    res = db.get(Reserva, reserva.id)
    assert res.status == StatusReserva.CANCELADA and res.motivo_excecao_prazo == "Aluna internada"
    aud = db.scalars(select(Auditoria).where(Auditoria.acao == "aula.desmarcar_excecao")).one()
    assert "Aluna internada" in aud.descricao and aud.entidade_id == str(reserva.id)


def test_excecao_dentro_do_prazo_nao_grava_motivo(client, monkeypatch, full, reserva, db):
    relogio(monkeypatch, datetime(2026, 10, 25, 18, 0, tzinfo=UTC))
    assert desmarcar(client, full, reserva.id, excecao_prazo=True, motivo="não precisava").status_code == 200
    db.expire_all()
    assert db.get(Reserva, reserva.id).motivo_excecao_prazo is None
    assert db.scalars(select(Auditoria).where(Auditoria.acao == "aula.desmarcar")).one()


def test_aula_ja_desmarcada_continua_409(client, monkeypatch, full, reserva):
    relogio(monkeypatch, datetime(2026, 10, 25, 18, 0, tzinfo=UTC))
    assert desmarcar(client, full, reserva.id).status_code == 200
    assert desmarcar(client, full, reserva.id, excecao_prazo=True, motivo="de novo").status_code == 409


def test_detalhe_traz_aviso_e_permissao_de_excecao(client, monkeypatch, full, secretaria, reserva):
    relogio(monkeypatch, datetime(2026, 10, 26, 10, 0, tzinfo=UTC))
    d = client.get(f"/api/aulas/reservas/{reserva.id}", headers=auth(full)).json()
    assert "6 horas" in d["aviso_prazo_desmarcar"] and d["permite"]["desmarcar_excecao"] is True
    s = client.get(f"/api/aulas/reservas/{reserva.id}", headers=auth(secretaria)).json()
    assert s["aviso_prazo_desmarcar"] and s["permite"]["desmarcar_excecao"] is False
    relogio(monkeypatch, datetime(2026, 10, 25, 18, 0, tzinfo=UTC))
    assert client.get(f"/api/aulas/reservas/{reserva.id}", headers=auth(full)).json()["aviso_prazo_desmarcar"] is None


def test_servico_do_aluno_tambem_respeita_as_6_horas(db, cenario, reserva):
    from app.modules.agenda.servico import Conflito

    with pytest.raises(Conflito, match="6 horas"):
        servico.desmarcar_reserva_do_aluno(db, cenario.a1.id, reserva.id, agora=datetime(2026, 10, 26, 8, 0, tzinfo=UTC))
    servico.desmarcar_reserva_do_aluno(db, cenario.a1.id, reserva.id, agora=LIMITE)
