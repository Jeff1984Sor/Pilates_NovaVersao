"""Sessões de aula: criar/editar/excluir e geração sob demanda (nunca em GET)."""

from datetime import date, time

from sqlalchemy import func, select

from app.core.models import Auditoria
from app.modules.agenda import servico
from app.modules.agenda.models import AulaSessao
from tests.agenda import fabrica
from tests.conftest import auth


def corpo(cenario, **extra):
    base = {
        "unidade_id": cenario.un.id,
        "tipo_servico_id": cenario.srv.id,
        "profissional_id": cenario.prof.id,
        "data": "2026-10-27",
        "hora_inicio": "08:00",
    }
    return {**base, **extra}


def total(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(AulaSessao))


def test_criar_sessao_herda_capacidade_da_unidade(client, db, cenario, full):
    r = client.post("/api/agenda/sessoes", json=corpo(cenario), headers=auth(full))
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["hora_fim"] == "08:50" and s["capacidade"] is None and s["capacidade_efetiva"] == 2
    assert s["vagas_livres"] == 2 and s["reservas"] == []
    audit = db.scalars(select(Auditoria.acao)).all()
    assert "agenda.sessao.criar" in audit


def test_criar_sessao_com_capacidade_propria(client, cenario, full):
    s = client.post("/api/agenda/sessoes", json=corpo(cenario, capacidade=5, hora_fim="09:30"), headers=auth(full)).json()
    assert s["capacidade_efetiva"] == 5 and s["hora_fim"] == "09:30"


def test_unicidade_da_sessao(client, cenario, full):
    assert client.post("/api/agenda/sessoes", json=corpo(cenario), headers=auth(full)).status_code == 201
    r = client.post("/api/agenda/sessoes", json=corpo(cenario), headers=auth(full))
    assert r.status_code == 409 and "Já existe uma aula" in r.json()["detail"]


def test_sessao_sem_profissional_tambem_e_unica(client, cenario, full):
    """Aula TotalPass (sem profissional) participa da unicidade (coalesce no índice)."""
    c = corpo(cenario, profissional_id=None)
    assert client.post("/api/agenda/sessoes", json=c, headers=auth(full)).status_code == 201
    assert client.post("/api/agenda/sessoes", json=c, headers=auth(full)).status_code == 409


def test_validacoes_da_sessao(client, cenario, full):
    assert client.post("/api/agenda/sessoes", json=corpo(cenario, hora_fim="07:00"), headers=auth(full)).status_code == 422
    assert client.post("/api/agenda/sessoes", json=corpo(cenario, unidade_id=999), headers=auth(full)).status_code == 422
    assert client.post("/api/agenda/sessoes", json=corpo(cenario, capacidade=-1), headers=auth(full)).status_code == 422
    assert client.post("/api/agenda/sessoes", json=corpo(cenario, profissional_id=999), headers=auth(full)).status_code == 422


def test_editar_sessao_e_voltar_a_herdar_capacidade(client, db, cenario, full):
    sid = cenario.ses.id
    r = client.patch(f"/api/agenda/sessoes/{sid}", json={"capacidade": 4, "hora_inicio": "11:00", "hora_fim": "11:50"}, headers=auth(full))
    assert r.status_code == 200 and r.json()["capacidade_efetiva"] == 4 and r.json()["hora_inicio"] == "11:00"
    r = client.patch(f"/api/agenda/sessoes/{sid}", json={"capacidade": None}, headers=auth(full))
    assert r.json()["capacidade"] is None and r.json()["capacidade_efetiva"] == 2
    assert "agenda.sessao.alterar" in db.scalars(select(Auditoria.acao)).all()


def test_capacidade_nao_pode_ficar_abaixo_das_reservas(client, db, cenario, full):
    fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    fabrica.reserva_direta(db, cenario.a2, cenario.ses)
    db.commit()
    r = client.patch(f"/api/agenda/sessoes/{cenario.ses.id}", json={"capacidade": 1}, headers=auth(full))
    assert r.status_code == 409
    db.expire_all()
    assert db.get(AulaSessao, cenario.ses.id).capacidade is None  # nada mudou


def test_editar_para_horario_ja_ocupado_da_conflito(client, db, cenario, full):
    outra = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, inicio=time(10, 0))
    db.commit()
    r = client.patch(f"/api/agenda/sessoes/{outra.id}", json={"hora_inicio": "09:00", "hora_fim": "09:50"}, headers=auth(full))
    assert r.status_code == 409
    assert client.patch("/api/agenda/sessoes/9999", json={"capacidade": 1}, headers=auth(full)).status_code == 404


def test_excluir_sessao_vazia_ok_e_com_reserva_recusa(client, db, cenario, full):
    fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    vazia = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, inicio=time(15, 0))
    db.commit()
    assert client.delete(f"/api/agenda/sessoes/{cenario.ses.id}", headers=auth(full)).status_code == 409
    assert client.delete(f"/api/agenda/sessoes/{vazia.id}", headers=auth(full)).status_code == 204
    assert "agenda.sessao.excluir" in db.scalars(select(Auditoria.acao)).all()


def test_listar_e_ver_sessao(client, db, cenario, full):
    fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    itens = client.get("/api/agenda/sessoes", params={"de": "2026-10-26", "ate": "2026-10-26"}, headers=auth(full)).json()["itens"]
    assert len(itens) == 1 and itens[0]["total_reservas"] == 1 and itens[0]["vagas_livres"] == 1
    d = client.get(f"/api/agenda/sessoes/{cenario.ses.id}", headers=auth(full)).json()
    assert d["reservas"][0]["aluno"] == "Ana Paula"


# ----------------------------------------------------------------------------------- geração sob demanda
def gerar(client, cenario, token, **extra):
    c = {
        "unidade_id": cenario.un.id,
        "tipo_servico_id": cenario.srv.id,
        "profissional_id": cenario.prof.id,
        "data_inicio": "2026-11-02",  # segunda
        "data_fim": "2026-11-03",
    }
    return client.post("/api/agenda/sessoes/gerar", json={**c, **extra}, headers=auth(token))


def test_get_nunca_cria_aula(client, db, cenario, full):
    fabrica.funcionamento(db, cenario.un)
    fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    antes = total(db)
    rid = db.scalar(select(func.min(servico.Reserva.id)))
    client.get("/api/agenda/grade", headers=auth(full))
    client.get("/api/agenda/sessoes", params={"de": "2026-10-01", "ate": "2026-12-31"}, headers=auth(full))
    client.get(f"/api/agenda/reservas/{rid}/horarios", headers=auth(full))
    client.get("/api/aulas/painel", headers=auth(full))
    client.get("/api/agenda/avulsas/slots", params={"unidade_id": cenario.un.id, "plano_id": fabrica.plano_avulso(db, cenario.srv).id, "data_inicio": "2026-11-02"}, headers=auth(full))
    assert total(db) == antes


def test_gerar_sessoes_pelos_horarios_de_funcionamento(client, db, cenario, full):
    fabrica.funcionamento(db, cenario.un, dias=(0, 1), inicio=time(8, 0), fim=time(12, 0))
    db.commit()
    antes = total(db)
    r = gerar(client, cenario, full)
    assert r.status_code == 200, r.text
    # janela 08-12 com aulas de 50 min + 10 de intervalo: 08:00, 09:00, 10:00, 11:00 -> 4 por dia x 2 dias
    assert r.json() == {"criadas": 8, "ja_existiam": 0, "bloqueadas": 0}
    assert total(db) == antes + 8
    horas = sorted({s.hora_inicio for s in db.scalars(select(AulaSessao).where(AulaSessao.data == date(2026, 11, 2)))})
    assert horas == [time(8), time(9), time(10), time(11)]
    # idempotente
    r2 = gerar(client, cenario, full)
    assert r2.json() == {"criadas": 0, "ja_existiam": 8, "bloqueadas": 0}
    assert "agenda.sessao.gerar" in db.scalars(select(Auditoria.acao)).all()


def test_gerar_pula_bloqueios(client, db, cenario, full):
    fabrica.funcionamento(db, cenario.un, dias=(0,), inicio=time(8, 0), fim=time(12, 0))
    fabrica.bloqueio(db, cenario.un, date(2026, 11, 2), inicio=time(9, 0), fim=time(10, 0))
    db.commit()
    r = gerar(client, cenario, full, data_fim="2026-11-02").json()
    assert r["criadas"] == 3 and r["bloqueadas"] == 1  # 09:00 bloqueado (10:00 encosta na borda e não bloqueia)


def test_gerar_respeita_o_servico_da_janela(client, db, cenario, full):
    outro = fabrica.servico(db, "Fisioterapia")
    fabrica.funcionamento(db, cenario.un, dias=(0,), servicos=[outro])
    db.commit()
    assert gerar(client, cenario, full, data_fim="2026-11-02").json()["criadas"] == 0


def test_gerar_valida_periodo(client, db, cenario, full):
    assert gerar(client, cenario, full, data_fim="2026-10-01").status_code == 422
    assert gerar(client, cenario, full, data_fim="2027-06-01").status_code == 422
