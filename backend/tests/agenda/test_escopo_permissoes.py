"""Perfil Professor (R11/R4): só as próprias aulas; Full/Secretária/Professor nas rotas; login obrigatório."""

from datetime import time

from sqlalchemy import select

from app.core.models import Auditoria
from app.core.security import hash_senha
from app.modules.agenda import servico
from tests.agenda import fabrica
from tests.conftest import auth


def test_sem_login_401(client, cenario):
    assert client.get("/api/aulas/painel").status_code == 401
    assert client.get("/api/agenda/grade").status_code == 401
    assert client.post("/api/agenda/reservas", json={"aluno_id": 1, "sessao_id": 1}).status_code == 401


def test_professor_ve_so_as_proprias_aulas_no_painel_e_na_grade(client, db, cenario, outro_professor, professor):
    fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    p = client.get("/api/aulas/painel", params={"data": "2026-10-26"}, headers=auth(professor)).json()
    nomes = [c["aluno"]["nome"] for h in p["dias"][0]["horarios"] for g in h["profissionais"] for c in g["cartoes"]]
    assert nomes == ["Ana Paula"]
    # filtro por outro profissional não fura o escopo
    p = client.get("/api/aulas/painel", params={"data": "2026-10-26", "profissional_id": outro_professor.prof.id}, headers=auth(professor)).json()
    nomes = [c["aluno"]["nome"] for h in p["dias"][0]["horarios"] for g in h["profissionais"] for c in g["cartoes"]]
    assert nomes == ["Ana Paula"]
    g = client.get("/api/agenda/grade", params={"semana": "2026-10-26", "profissional_id": outro_professor.prof.id}, headers=auth(professor)).json()
    assert {b["aluno"] for b in g["dias"][0]["blocos"]} == {"Ana Paula"}
    s = client.get("/api/agenda/sessoes", params={"de": "2026-10-26", "ate": "2026-10-26"}, headers=auth(professor)).json()["itens"]
    assert [x["id"] for x in s] == [cenario.ses.id]


def test_professor_nao_acessa_reserva_aula_ou_aluno_alheios_por_id(client, db, cenario, outro_professor, professor):
    h = auth(professor)
    rid, aid, sid = outro_professor.reserva.id, outro_professor.aluna.id, outro_professor.ses.id
    assert client.get(f"/api/aulas/reservas/{rid}", headers=h).status_code == 404
    assert client.get(f"/api/aulas/reservas/{rid}/historico", headers=h).status_code == 404
    assert client.post(f"/api/aulas/reservas/{rid}/presenca", json={"acao": "chegou"}, headers=h).status_code == 404
    assert client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "x"}, headers=h).status_code == 404
    assert client.post(f"/api/aulas/reservas/{rid}/avaliacao", json={"texto": "x"}, headers=h).status_code == 404
    assert client.get(f"/api/aulas/reservas/{rid}/evolucao", headers=h).status_code == 404
    assert client.get(f"/api/agenda/sessoes/{sid}", headers=h).status_code == 404
    assert client.get(f"/api/agenda/alunos/{aid}/reservas", headers=h).status_code == 404
    assert client.get(f"/api/agenda/alunos/{aid}/evolucoes", headers=h).status_code == 404
    assert client.get(f"/api/agenda/alunos/{aid}/avaliacoes", headers=h).status_code == 404
    assert client.get(f"/api/agenda/alunos/{aid}/evolucoes/exportar", headers=h).status_code == 404
    assert client.get(f"/api/agenda/alunos/{aid}/avaliativas", headers=h).status_code == 404
    assert client.get(f"/api/agenda/reservas/{rid}/horarios", headers=h).status_code == 404


def test_professor_nao_edita_evolucao_alheia(client, db, cenario, outro_professor, professor):
    e = client.post(f"/api/aulas/reservas/{outro_professor.reserva.id}/evolucao", json={"texto": "da outra"}, headers=auth(outro_professor.token)).json()
    h = auth(professor)
    assert client.patch(f"/api/aulas/evolucoes/{e['id']}", json={"texto": "invadi"}, headers=h).status_code == 404
    assert client.delete(f"/api/aulas/evolucoes/{e['id']}", headers=h).status_code == 404


def test_professor_ve_o_aluno_das_proprias_aulas_e_so_as_aulas_dele(client, db, cenario, outro_professor, professor):
    # a aluna "alheia" também faz uma aula com a Natalia: passa a ser aluna dela, mas a aula da outra continua escondida
    ses = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, inicio=time(14, 0))
    db.commit()
    fabrica.reserva_direta(db, outro_professor.aluna, ses)
    db.commit()
    r = client.get(f"/api/agenda/alunos/{outro_professor.aluna.id}/reservas", headers=auth(professor))
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["itens"]] != [] and all(i["profissional"]["id"] == cenario.prof.id for i in r.json()["itens"])


def test_professor_nao_desmarca_nao_remarca_nao_exclui(client, db, cenario, professor):
    r = fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    h = auth(professor)
    assert client.post(f"/api/aulas/reservas/{r.id}/desmarcar", headers=h).status_code == 403
    assert client.post(f"/api/aulas/reservas/{r.id}/remarcar", json={"data": "2026-10-28", "hora_inicio": "09:00"}, headers=h).status_code == 403
    assert client.delete(f"/api/aulas/reservas/{r.id}", headers=h).status_code == 403
    assert client.post("/api/agenda/reservas", json={"aluno_id": cenario.a2.id, "sessao_id": cenario.ses.id}, headers=h).status_code == 403
    assert client.get(f"/api/aulas/reservas/{r.id}/cobranca", headers=h).status_code == 403
    assert client.post("/api/agenda/sessoes", json={"unidade_id": 1, "tipo_servico_id": 1, "data": "2026-10-27", "hora_inicio": "08:00"}, headers=h).status_code == 403
    db.expire_all()
    assert db.get(servico.Reserva, r.id).status == "RESERVADA"


def test_professor_com_operar_continua_sem_desmarcar(client, db, cenario, professor):
    """Mesmo que o perfil ganhe aulas.operar, R4 vale: professor não desmarca nem remarca (checado pelo escopo)."""
    from app.core.models import PerfilAcesso

    p = db.scalar(select(PerfilAcesso).where(PerfilAcesso.nome == "Professor"))
    p.permissoes = [*p.permissoes, "aulas.operar"]
    db.commit()
    r = fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    h = auth(professor)
    assert client.post(f"/api/aulas/reservas/{r.id}/desmarcar", headers=h).status_code == 403
    assert client.post(f"/api/aulas/reservas/{r.id}/remarcar", json={"data": "2026-10-28", "hora_inicio": "09:00"}, headers=h).status_code == 403
    assert client.delete(f"/api/aulas/reservas/{r.id}", headers=h).status_code == 403


def test_professor_faz_presenca_evolucao_e_avaliacao_das_proprias_aulas(client, db, cenario, professor):
    r = fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    h = auth(professor)
    assert client.post(f"/api/aulas/reservas/{r.id}/presenca", json={"acao": "chegou"}, headers=h).status_code == 200
    e = client.post(f"/api/aulas/reservas/{r.id}/evolucao", json={"texto": "Bom ritmo", "finalizar": True}, headers=h)
    assert e.status_code == 201 and e.json()["status_reserva"] == "CONCLUIDA" and e.json()["profissional_id"] == cenario.prof.id
    assert client.post(f"/api/aulas/reservas/{r.id}/avaliacao", json={"texto": "Postura ok"}, headers=h).status_code == 201


def test_professor_registra_sempre_como_ele_mesmo(client, db, cenario, outro_professor, professor):
    r = fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    e = client.post(
        f"/api/aulas/reservas/{r.id}/evolucao", json={"texto": "x", "profissional_id": outro_professor.prof.id}, headers=auth(professor)
    ).json()
    assert e["profissional_id"] == cenario.prof.id


def test_professor_sem_vinculo_nao_ve_nada(client, db, cenario, full):
    from tests.conftest import criar_usuario, entrar

    criar_usuario(db, "Professor", email="solto@exemplo.com")
    t = entrar(client, "solto@exemplo.com").json()["access_token"]
    fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    db.commit()
    p = client.get("/api/aulas/painel", params={"data": "2026-10-26"}, headers=auth(t)).json()
    assert p["total"] == 0
    assert client.get("/api/agenda/opcoes", headers=auth(t)).json()["profissionais"] == []


def test_opcoes_do_professor_so_trazem_ele(client, cenario, outro_professor, professor, full):
    nomes = [p["nome"] for p in client.get("/api/agenda/opcoes", headers=auth(professor)).json()["profissionais"]]
    assert nomes == ["Natalia Souza"]
    todos = [p["nome"] for p in client.get("/api/agenda/opcoes", headers=auth(full)).json()["profissionais"]]
    assert set(todos) == {"Natalia Souza", "Outra Professora"}


def test_secretaria_opera_mas_nao_exclui_aula_nem_sessao(client, db, cenario, secretaria):
    h = auth(secretaria)
    r = client.post("/api/agenda/reservas", json={"aluno_id": cenario.a1.id, "sessao_id": cenario.ses.id}, headers=h)
    assert r.status_code == 201
    rid = r.json()["id"]
    assert client.post(f"/api/aulas/reservas/{rid}/desmarcar", headers=h).status_code == 200
    assert client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-29", "hora_inicio": "10:00"}, headers=h).status_code == 200
    assert client.get("/api/aulas/painel", params={"data": "2026-10-29"}, headers=h).json()["total"] == 1
    assert client.post("/api/agenda/sessoes", json={"unidade_id": cenario.un.id, "tipo_servico_id": cenario.srv.id, "data": "2026-10-30", "hora_inicio": "08:00"}, headers=h).status_code == 201
    assert client.delete(f"/api/agenda/sessoes/{cenario.ses.id}", headers=h).status_code == 403  # sem agenda.excluir
    assert client.delete(f"/api/aulas/reservas/{rid}", headers=h).status_code == 200  # reserva: aulas.operar


def test_sem_permissao_de_aulas_nao_entra(client, db, cenario):
    """Perfil sem nenhuma permissão da agenda: tudo 403."""
    from app.core.models import PerfilAcesso
    from tests.conftest import criar_usuario, entrar

    db.add(PerfilAcesso(nome="Vazio", permissoes=[]))
    db.commit()
    from app.core.models import Usuario

    u = Usuario(nome="Sem nada", email="vazio@exemplo.com", login="vazio", perfil_acesso_id=db.scalar(select(PerfilAcesso.id).where(PerfilAcesso.nome == "Vazio")),
                senha_hash=hash_senha("Senha@Forte1"))
    db.add(u)
    db.commit()
    t = entrar(client, "vazio@exemplo.com").json()["access_token"]
    h = auth(t)
    for metodo, url in [
        ("get", "/api/aulas/painel"),
        ("get", "/api/agenda/grade"),
        ("get", "/api/agenda/opcoes"),
        ("post", "/api/aulas/reservas/1/presenca"),
        ("post", "/api/aulas/evolucoes/melhorar"),
        ("post", "/api/agenda/reservas"),
        ("get", "/api/agenda/alunos/1/evolucoes"),
    ]:
        assert getattr(client, metodo)(url, headers=h).status_code == 403, url
    assert criar_usuario and True


def test_toda_acao_de_escrita_gera_auditoria(client, db, cenario, full):
    h = auth(full)
    rid = client.post("/api/agenda/reservas", json={"aluno_id": cenario.a1.id, "sessao_id": cenario.ses.id}, headers=h).json()["id"]
    client.post(f"/api/aulas/reservas/{rid}/presenca", json={"acao": "chegou"}, headers=h)
    client.post(f"/api/aulas/reservas/{rid}/confirmar", headers=h)
    client.post(f"/api/aulas/reservas/{rid}/remarcar", json={"data": "2026-10-28", "hora_inicio": "09:00"}, headers=h)
    ev = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "ok"}, headers=h).json()["id"]
    client.patch(f"/api/aulas/evolucoes/{ev}", json={"texto": "ok2"}, headers=h)
    av = client.post(f"/api/aulas/reservas/{rid}/avaliacao", json={"texto": "ok"}, headers=h).json()["id"]
    client.patch(f"/api/aulas/avaliacoes/{av}", json={"texto": "ok2"}, headers=h)
    client.delete(f"/api/aulas/avaliacoes/{av}", headers=h)
    client.delete(f"/api/aulas/evolucoes/{ev}", headers=h)
    client.post(f"/api/aulas/reservas/{rid}/desmarcar", headers=h)
    client.delete(f"/api/aulas/reservas/{rid}", headers=h)
    acoes = set(db.scalars(select(Auditoria.acao)).all())
    assert {
        "agenda.reserva.criar", "aula.chegou", "aula.confirmar", "aula.remarcar", "evolucao.criar", "evolucao.alterar",
        "avaliacao.criar", "avaliacao.alterar", "avaliacao.excluir", "evolucao.excluir", "aula.desmarcar", "aula.excluir",
    } <= acoes
    um = db.scalar(select(Auditoria).where(Auditoria.acao == "aula.remarcar"))
    assert um.entidade == "reserva" and um.usuario_nome and "Ana Paula" in um.descricao and um.antes_json
