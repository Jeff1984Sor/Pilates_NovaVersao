"""Fluxos de reserva pela API: criar, remarcar, desmarcar, presença, excluir, confirmar, com auditoria e rollback."""

from datetime import date

from sqlalchemy import func, select

from app.core.models import Auditoria
from app.modules.agenda.models import AulaSessao, Avaliacao, Evolucao, Reserva, StatusReserva
from tests.agenda import fabrica
from tests.conftest import auth


def acoes_auditadas(db):
    db.expire_all()
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id))]


def vagas(db, ses_id):
    db.expire_all()
    return db.get(AulaSessao, ses_id).reservas_ativas


def criar(client, token, aluno_id, sessao_id):
    return client.post("/api/agenda/reservas", json={"aluno_id": aluno_id, "sessao_id": sessao_id}, headers=auth(token))


def test_criar_reserva_na_aula_mostra_ocupacao_e_audita(client, db, cenario, full):
    r = criar(client, full, cenario.a1.id, cenario.ses.id)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["status"] == "RESERVADA" and corpo["ocupacao"] == "1/2" and corpo["data"] == "2026-10-26"
    assert "agenda.reserva.criar" in acoes_auditadas(db)


def test_criar_reserva_lotada_devolve_409_com_mensagem_e_nao_grava(client, db, cenario, full):
    criar(client, full, cenario.a1.id, cenario.ses.id)
    criar(client, full, cenario.a2.id, cenario.ses.id)
    a3 = fabrica.aluno(db, cenario.un, "Carla")
    db.commit()
    r = criar(client, full, a3.id, cenario.ses.id)
    assert r.status_code == 409
    assert "2 de 2 vagas ocupadas" in r.json()["detail"]
    assert vagas(db, cenario.ses.id) == 2
    assert db.scalar(select(func.count()).select_from(Reserva)) == 2


def test_criar_reserva_pelo_horario_cria_a_aula_se_nao_existir(client, db, cenario, full):
    corpo = {
        "aluno_id": cenario.a1.id,
        "unidade_id": cenario.un.id,
        "tipo_servico_id": cenario.srv.id,
        "profissional_id": cenario.prof.id,
        "data": "2026-10-27",
        "hora_inicio": "14:00",
    }
    r = client.post("/api/agenda/reservas", json=corpo, headers=auth(full))
    assert r.status_code == 201, r.text
    assert r.json()["hora_fim"] == "14:50"  # duração da unidade
    # segunda reserva no mesmo horário reaproveita a aula
    corpo["aluno_id"] = cenario.a2.id
    r2 = client.post("/api/agenda/reservas", json=corpo, headers=auth(full))
    assert r2.json()["sessao_id"] == r.json()["sessao_id"] and r2.json()["ocupacao"] == "2/2"


def test_criar_reserva_sem_informar_a_aula(client, cenario, full):
    r = client.post("/api/agenda/reservas", json={"aluno_id": cenario.a1.id}, headers=auth(full))
    assert r.status_code == 422


def test_desmarcar_com_reposicao_r4(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    r = client.post(f"/api/aulas/reservas/{rid}/desmarcar", headers=auth(full))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["status"] == "CANCELADA" and c["confirmada_em"] is None
    assert c["reposicao_ate"] == "2026-11-25"  # aula 26/10 + 30 dias
    assert c["desmarcada_em"].startswith("2026-10-25T18:00")
    assert vagas(db, cenario.ses.id) == 0
    assert "aula.desmarcar" in acoes_auditadas(db)
    # de novo: recusa
    assert client.post(f"/api/aulas/reservas/{rid}/desmarcar", headers=auth(full)).status_code == 409


def test_remarcar_libera_vaga_antiga_e_apaga_aula_vazia(client, db, cenario, full):
    ses_id = cenario.ses.id
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    r = client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-28", "hora_inicio": "10:00"}, headers=auth(full))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["data"] == "2026-10-28" and c["hora_inicio"] == "10:00" and c["hora_fim"] == "10:50"
    assert c["profissional_id"] == cenario.prof.id and c["ocupacao"] == "1/2"
    db.expire_all()
    assert db.get(AulaSessao, ses_id) is None  # ficou vazia e sem outros vínculos: apagada
    assert "aula.remarcar" in acoes_auditadas(db)


def test_remarcar_mantem_aula_antiga_se_ainda_tem_gente(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    criar(client, full, cenario.a2.id, cenario.ses.id)
    client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-28", "hora_inicio": "10:00"}, headers=auth(full))
    assert vagas(db, cenario.ses.id) == 1


def test_remarcar_para_aula_lotada_recusa_e_desfaz_tudo(client, db, cenario, full):
    a3 = fabrica.aluno(db, cenario.un, "Carla")
    lotada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 28), capacidade=1)
    db.commit()
    criar(client, full, a3.id, lotada.id)
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    r = client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-28", "hora_inicio": "09:00"}, headers=auth(full))
    assert r.status_code == 409 and "1 de 1 vagas ocupadas" in r.json()["detail"]
    db.expire_all()
    assert db.get(Reserva, rid).aula_sessao_id == cenario.ses.id and vagas(db, cenario.ses.id) == 1


def test_remarcar_aula_com_capacidade_zero_e_bloqueado(client, db, cenario, full):
    """# COMPORTAMENTO ANTIGO corrigido: no antigo a remarcação para capacidade 0 passava."""
    zero = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 28), capacidade=0)
    db.commit()
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    r = client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-28", "hora_inicio": "09:00"}, headers=auth(full))
    assert r.status_code == 409 and "0 de 0" in r.json()["detail"]
    assert zero.id


def test_remarcar_reposicao_respeita_prazo_e_consome(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    client.post(f"/api/aulas/reservas/{rid}/desmarcar", headers=auth(full))  # reposição até 25/11
    longe = client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-11-26", "hora_inicio": "09:00"}, headers=auth(full))
    assert longe.status_code == 409 and "25/11/2026" in longe.json()["detail"]
    ok = client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-11-20", "hora_inicio": "09:00"}, headers=auth(full))
    assert ok.status_code == 200
    assert ok.json()["status"] == "RESERVADA" and ok.json()["reposicao_ate"] is None  # consumida


def test_remarcar_reposicao_com_prazo_ignorado_pela_equipe(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    client.post(f"/api/aulas/reservas/{rid}/desmarcar", headers=auth(full))
    r = client.post(
        f"/api/aulas/reservas/{rid}/remarcar",
        json={"data": "2026-12-20", "hora_inicio": "09:00", "ignorar_prazo_reposicao": True},
        headers=auth(full),
    )
    assert r.status_code == 200


def test_remarcar_para_o_mesmo_horario_recusa(client, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    r = client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-26", "hora_inicio": "09:00"}, headers=auth(full))
    assert r.status_code == 409


def test_presenca_chegou_finalizar_faltou(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    for acao, esperado, ocup in [("faltou", "FALTOU_SEM_AVISAR", 0), ("chegou", "RESERVADA", 1), ("finalizar", "CONCLUIDA", 0), ("faltou_avisou", "FALTOU_AVISOU", 0)]:
        r = client.post(f"/api/aulas/reservas/{rid}/presenca", json={"acao": acao}, headers=auth(full))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == esperado
        assert vagas(db, cenario.ses.id) == ocup
    assert client.post(f"/api/aulas/reservas/{rid}/presenca", json={"acao": "voar"}, headers=auth(full)).status_code == 422
    assert {"aula.faltou", "aula.chegou", "aula.finalizar", "aula.faltou_avisou"} <= set(acoes_auditadas(db))


def test_excluir_reserva_libera_vaga_e_apaga_aula_vazia(client, db, cenario, full):
    ses_id = cenario.ses.id
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    r = client.delete(f"/api/aulas/reservas/{rid}", headers=auth(full))
    assert r.status_code == 200 and r.json()["sessao_apagada"] is True
    db.expire_all()
    assert db.get(AulaSessao, ses_id) is None and db.get(Reserva, rid) is None
    assert "aula.excluir" in acoes_auditadas(db)


def test_excluir_reserva_mantem_aula_com_outros_alunos(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    criar(client, full, cenario.a2.id, cenario.ses.id)
    r = client.delete(f"/api/aulas/reservas/{rid}", headers=auth(full))
    assert r.json()["sessao_apagada"] is False and vagas(db, cenario.ses.id) == 1


def test_excluir_reserva_com_evolucao_e_recusado(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "Boa aula"}, headers=auth(full))
    r = client.delete(f"/api/aulas/reservas/{rid}", headers=auth(full))
    assert r.status_code == 409 and "evolução" in r.json()["detail"]
    assert db.scalar(select(func.count()).select_from(Evolucao)) == 1
    assert db.scalar(select(func.count()).select_from(Avaliacao)) == 0


def test_confirmar_grava_confirmada_em_e_recusa_aula_passada(client, db, cenario, full):
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    r = client.post(f"/api/aulas/reservas/{rid}/confirmar", headers=auth(full))
    assert r.status_code == 200 and r.json()["confirmada_em"].startswith("2026-10-25T18:00")
    passada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 10, 20))
    db.commit()
    rid2 = criar(client, full, cenario.a2.id, passada.id).json()["id"]
    assert client.post(f"/api/aulas/reservas/{rid2}/confirmar", headers=auth(full)).status_code == 409


def test_reserva_inexistente_404(client, full):
    assert client.post("/api/aulas/reservas/999/desmarcar", headers=auth(full)).status_code == 404
    assert client.delete("/api/aulas/reservas/999", headers=auth(full)).status_code == 404


def test_atomicidade_erro_no_meio_nao_deixa_nada(client, db, cenario, full):
    """A aula nova é criada no caminho da remarcação; se a vaga falha, o rollback tem de desfazer essa criação também."""
    rid = criar(client, full, cenario.a1.id, cenario.ses.id).json()["id"]
    cenario.ses.capacidade = 0  # a aula nova herda capacidade 0 e nunca terá vaga
    db.commit()
    antes = db.scalar(select(func.count()).select_from(AulaSessao))
    r = client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-30", "hora_inicio": "10:00"}, headers=auth(full))
    assert r.status_code == 409
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AulaSessao)) == antes  # a aula criada no caminho foi desfeita
    assert db.get(Reserva, rid).aula_sessao_id == cenario.ses.id and db.get(Reserva, rid).status == StatusReserva.RESERVADA
