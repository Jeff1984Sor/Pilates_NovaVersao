"""Aulas do aluno: listar, confirmar (R15), desmarcar (R4), isolamento entre alunos e reposição."""

from datetime import date, time

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from tests.agenda import fabrica
from tests.app_aluno.conftest import cab, entrar_aluno

B = "/api/aluno-app"


def _tokens_bruna(client, zap, cenario):
    return cab(entrar_aluno(client, zap, cenario.bruna))


def test_lista_so_as_proprias_aulas_futuras_sem_canceladas(client, db, cenario, ana_logada):
    passada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 20))
    fabrica.reserva_direta(db, cenario.ana, passada)
    cancelada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 27))
    rc = fabrica.reserva_direta(db, cenario.ana, cancelada)
    agenda.desmarcar_reserva(db, rc.id)
    db.commit()
    aulas = client.get(f"{B}/aulas", headers=ana_logada).json()
    assert [a["id"] for a in aulas] == [cenario.r_ana.id]
    a = aulas[0]
    assert (a["data"], a["hora_inicio"], a["profissional"], a["servico"]) == ("2026-10-26", "09:00:00", "Natalia Souza", "Pilates")
    assert a["status"] == "aguardando_chegar" and a["pode_confirmar"] and a["pode_desmarcar"] and not a["confirmada"]


def test_aluna_nao_ve_a_aula_de_outra(client, cenario, ana_logada):
    ids = {a["id"] for a in client.get(f"{B}/aulas", headers=ana_logada).json()}
    assert cenario.r_bruna.id not in ids


def test_confirmar_grava_confirmada_em(client, db, cenario, ana_logada):
    r = client.post(f"{B}/aulas/{cenario.r_ana.id}/confirmar", headers=ana_logada)
    assert r.status_code == 200
    j = r.json()
    assert j["confirmada"] is True and j["pode_confirmar"] is False
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).confirmada_em is not None
    aud = db.scalars(select(Auditoria).where(Auditoria.acao == "aluno_app.confirmar")).one()
    assert aud.entidade_id == str(cenario.r_ana.id) and "Ana" in aud.usuario_nome


def test_desmarcar_aplica_r4_e_libera_a_vaga(client, db, cenario, ana_logada):
    r = client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    assert r.status_code == 200
    # aula de 26/10 -> reposição até 25/11 (30 dias)
    assert r.json()["reposicao_ate"] == "2026-11-25" and "25/11/2026" in r.json()["mensagem"]
    db.expire_all()
    res = db.get(Reserva, cenario.r_ana.id)
    assert res.status == StatusReserva.CANCELADA and res.reposicao_ate == date(2026, 11, 25)
    assert res.desmarcada_em is not None and res.confirmada_em is None
    assert db.get(AulaSessao, cenario.s9.id).reservas_ativas == 0
    assert client.get(f"{B}/aulas", headers=ana_logada).json() == []


def test_desmarcar_de_novo_409_e_nao_estende_o_prazo(client, db, cenario, ana_logada):
    client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    r = client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    assert r.status_code == 409
    assert client.post(f"{B}/aulas/{cenario.r_ana.id}/confirmar", headers=ana_logada).status_code == 409


def test_aula_concluida_ou_passada_nao_confirma_nem_desmarca(client, db, cenario, ana_logada):
    velha = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 20))
    rv = fabrica.reserva_direta(db, cenario.ana, velha)
    db.commit()
    assert client.post(f"{B}/aulas/{rv.id}/confirmar", headers=ana_logada).status_code == 409
    assert client.post(f"{B}/aulas/{rv.id}/desmarcar", headers=ana_logada).status_code == 409
    futura = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 28))
    rf = fabrica.reserva_direta(db, cenario.ana, futura, status=StatusReserva.CONCLUIDA)
    db.commit()
    assert client.post(f"{B}/aulas/{rf.id}/desmarcar", headers=ana_logada).status_code == 409


def test_isolamento_id_alheio_e_404_em_todas_as_acoes(client, db, zap, cenario, ana_logada):
    alheio = cenario.r_bruna.id
    for acao in ("confirmar", "desmarcar"):
        assert client.post(f"{B}/aulas/{alheio}/{acao}", headers=ana_logada).status_code == 404
    assert client.get(f"{B}/reposicoes/{alheio}/opcoes", headers=ana_logada).status_code == 404
    assert client.post(f"{B}/reposicoes/{alheio}/remarcar", json={"aula_id": cenario.s9.id}, headers=ana_logada).status_code == 404
    assert client.post(f"{B}/aulas/999999/confirmar", headers=ana_logada).status_code == 404  # inexistente = igual
    db.expire_all()
    assert db.get(Reserva, alheio).status == StatusReserva.RESERVADA and db.get(Reserva, alheio).confirmada_em is None


def test_reposicoes_lista_a_desmarcada_com_prazo(client, cenario, ana_logada):
    assert client.get(f"{B}/reposicoes", headers=ana_logada).json() == []
    client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    lista = client.get(f"{B}/reposicoes", headers=ana_logada).json()
    assert len(lista) == 1
    assert lista[0]["reposicao_ate"] == "2026-11-25" and lista[0]["dias_restantes"] == 31 and lista[0]["dentro_do_prazo"]


def _desmarcada(client, cenario, ana_logada):
    client.post(f"{B}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)


def test_opcoes_so_com_vaga_real_e_sem_criar_aula(client, db, cenario, ana_logada):
    _desmarcada(client, cenario, ana_logada)
    cheia = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 27))
    fabrica.reserva_direta(db, cenario.bruna, cheia)
    c2 = fabrica.aluno(db, cenario.un, "Carla Dias")
    fabrica.reserva_direta(db, c2, cheia)  # capacidade 2: lotada
    boa = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 28), inicio=time(8, 0))
    longe = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 12, 15))  # depois do prazo
    outro_srv = fabrica.servico(db, "Fisioterapia")
    fabrica.sessao(db, cenario.un, outro_srv, cenario.prof, dia=date(2026, 10, 29))  # outro serviço
    fabrica.bloqueio(db, cenario.un, date(2026, 10, 30))
    bloqueada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 30))
    db.commit()
    n_antes = len(db.scalars(select(AulaSessao)).all())
    ops = client.get(f"{B}/reposicoes/{cenario.r_ana.id}/opcoes", headers=ana_logada).json()
    ids = {o["aula_id"] for o in ops}
    assert boa.id in ids and cenario.s10.id in ids  # a de seg 10:00 tem 1 vaga (Bruna)
    assert cheia.id not in ids and longe.id not in ids and bloqueada.id not in ids
    assert cenario.s9.id not in ids  # a própria aula original: o aluno já tem reserva nela
    assert all(o["vagas"] >= 1 for o in ops)
    assert len(db.scalars(select(AulaSessao)).all()) == n_antes  # GET nunca cria


def test_remarcar_reposicao_consome_o_prazo_e_ocupa_a_vaga(client, db, cenario, ana_logada):
    _desmarcada(client, cenario, ana_logada)
    boa = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 28), inicio=time(8, 0))
    db.commit()
    r = client.post(f"{B}/reposicoes/{cenario.r_ana.id}/remarcar", json={"aula_id": boa.id}, headers=ana_logada)
    assert r.status_code == 200 and r.json()["data"] == "2026-10-28" and r.json()["hora_inicio"] == "08:00:00"
    db.expire_all()
    res = db.get(Reserva, cenario.r_ana.id)
    assert res.status == StatusReserva.RESERVADA and res.aula_sessao_id == boa.id and res.reposicao_ate is None
    assert db.get(AulaSessao, boa.id).reservas_ativas == 1
    assert client.get(f"{B}/reposicoes", headers=ana_logada).json() == []
    aud = db.scalars(select(Auditoria).where(Auditoria.acao == "aluno_app.reposicao")).one()
    assert aud.entidade_id == str(cenario.r_ana.id)


def test_remarcar_para_aula_lotada_ou_fora_das_opcoes_409(client, db, cenario, ana_logada):
    _desmarcada(client, cenario, ana_logada)
    cheia = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 27))
    fabrica.reserva_direta(db, cenario.bruna, cheia)
    fabrica.reserva_direta(db, fabrica.aluno(db, cenario.un, "Carla Dias"), cheia)
    longe = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 12, 15))
    db.commit()
    for aula in (cheia.id, longe.id, 999999):
        r = client.post(f"{B}/reposicoes/{cenario.r_ana.id}/remarcar", json={"aula_id": aula}, headers=ana_logada)
        assert r.status_code == 409
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).status == StatusReserva.CANCELADA  # nada mudou


def test_prazo_vencido_nao_remarca(client, db, cenario, ana_logada, monkeypatch):
    from datetime import timedelta

    from app.modules.app_aluno import routes
    from tests.app_aluno.conftest import AGORA_FIXO

    _desmarcada(client, cenario, ana_logada)
    boa = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 11, 26))
    db.commit()
    monkeypatch.setattr(routes, "_agora", lambda: AGORA_FIXO + timedelta(days=32))  # 26/11: um dia depois do prazo
    assert client.get(f"{B}/reposicoes/{cenario.r_ana.id}/opcoes", headers=ana_logada).status_code == 409
    assert client.post(f"{B}/reposicoes/{cenario.r_ana.id}/remarcar", json={"aula_id": boa.id}, headers=ana_logada).status_code == 409
    lista = client.get(f"{B}/reposicoes", headers=ana_logada).json()
    assert lista[0]["dentro_do_prazo"] is False and lista[0]["dias_restantes"] == 0


def test_aula_ativa_nao_e_reposicao(client, cenario, ana_logada):
    assert client.get(f"{B}/reposicoes/{cenario.r_ana.id}/opcoes", headers=ana_logada).status_code == 409
    assert client.post(f"{B}/reposicoes/{cenario.r_ana.id}/remarcar", json={"aula_id": cenario.s10.id}, headers=ana_logada).status_code == 409


def test_duas_alunas_disputando_a_ultima_vaga_so_uma_entra(client, db, zap, cenario, ana_logada):
    """Bruna também desmarca; só há uma vaga na aula de destino: a segunda a pedir recebe 409."""
    bruna = _tokens_bruna(client, zap, cenario)
    client.post(f"{B}/aulas/{cenario.r_bruna.id}/desmarcar", headers=bruna)
    _desmarcada(client, cenario, ana_logada)
    destino = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 28), inicio=time(8, 0), capacidade=1)
    db.commit()
    a = client.post(f"{B}/reposicoes/{cenario.r_ana.id}/remarcar", json={"aula_id": destino.id}, headers=ana_logada)
    b = client.post(f"{B}/reposicoes/{cenario.r_bruna.id}/remarcar", json={"aula_id": destino.id}, headers=bruna)
    assert (a.status_code, b.status_code) == (200, 409)
    db.expire_all()
    assert db.get(AulaSessao, destino.id).reservas_ativas == 1
