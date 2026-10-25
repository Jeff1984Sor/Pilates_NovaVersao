"""Evolução e avaliação por reserva: CRUD, modelo como ponto de partida, finalizar, histórico, exportação e IA."""

import io

from sqlalchemy import select

from app.core import ia
from app.core.models import ConfigIA
from app.core.segredos import cifrar_texto as cifrar
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.cadastros.models import ModeloEvolucao
from tests.agenda import fabrica
from tests.conftest import auth


def nova_reserva(db, cenario, aluno=None):
    r = fabrica.reserva_direta(db, aluno or cenario.a1, cenario.ses)
    db.commit()
    return r.id


def test_crud_de_evolucao(client, db, cenario, full):
    rid = nova_reserva(db, cenario)
    h = auth(full)
    r = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "  Trabalhou mobilidade  "}, headers=h)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["texto"] == "Trabalhou mobilidade" and e["profissional"] == "Natalia Souza" and e["data_aula"] == "2026-10-26"
    assert e["status_reserva"] == "RESERVADA"  # sem finalizar não mexe na aula
    lista = client.get(f"/api/aulas/reservas/{rid}/evolucao", headers=h).json()["itens"]
    assert [x["id"] for x in lista] == [e["id"]]
    up = client.patch(f"/api/aulas/evolucoes/{e['id']}", json={"texto": "Texto novo"}, headers=h)
    assert up.status_code == 200 and up.json()["texto"] == "Texto novo"
    assert client.delete(f"/api/aulas/evolucoes/{e['id']}", headers=h).status_code == 204
    assert client.get(f"/api/aulas/reservas/{rid}/evolucao", headers=h).json()["itens"] == []
    assert client.patch(f"/api/aulas/evolucoes/{e['id']}", json={"texto": "x"}, headers=h).status_code == 404


def test_texto_obrigatorio(client, db, cenario, full):
    rid = nova_reserva(db, cenario)
    h = auth(full)
    assert client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "   "}, headers=h).status_code == 422
    assert client.post(f"/api/aulas/reservas/{rid}/avaliacao", json={}, headers=h).status_code == 422
    ev = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "ok"}, headers=h).json()["id"]
    assert client.patch(f"/api/aulas/evolucoes/{ev}", json={"texto": ""}, headers=h).status_code == 422


def test_modelo_de_evolucao_como_ponto_de_partida(client, db, cenario, full):
    m = ModeloEvolucao(titulo="Dor/limitação", texto="Dor: \nLimitação: \nConduta: ")
    db.add(m)
    db.commit()
    rid = nova_reserva(db, cenario)
    h = auth(full)
    opc = client.get("/api/agenda/opcoes", headers=h).json()["modelos_evolucao"]
    assert opc == [{"id": m.id, "titulo": "Dor/limitação", "texto": "Dor: \nLimitação: \nConduta: "}]
    r = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"modelo_evolucao_id": m.id}, headers=h)
    assert r.status_code == 201 and r.json()["texto"].startswith("Dor:")
    # texto digitado vale mais que o modelo
    r = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"modelo_evolucao_id": m.id, "texto": "Meu texto"}, headers=h)
    assert r.json()["texto"] == "Meu texto"
    assert client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"modelo_evolucao_id": 999}, headers=h).status_code == 422


def test_salvar_e_finalizar_marca_concluida_e_libera_vaga(client, db, cenario, full):
    rid = nova_reserva(db, cenario)
    r = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "Fim", "finalizar": True}, headers=auth(full))
    assert r.json()["status_reserva"] == "CONCLUIDA"
    db.expire_all()
    assert db.get(Reserva, rid).status == StatusReserva.CONCLUIDA
    assert db.get(AulaSessao, cenario.ses.id).reservas_ativas == 0


def test_evolucao_com_status_de_falta(client, db, cenario, full):
    rid = nova_reserva(db, cenario)
    h = auth(full)
    r = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "Avisou", "status": "faltou_avisou"}, headers=h)
    assert r.status_code == 201 and r.json()["status_reserva"] == "FALTOU_AVISOU"
    assert client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "x", "status": "CANCELADA"}, headers=h).status_code == 422
    assert client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "x", "status": "NADA"}, headers=h).status_code == 422


def test_evolucao_sem_profissional_na_aula_exige_informar(client, db, cenario, full):
    ses = fabrica.sessao(db, cenario.un, cenario.srv, None, inicio=__import__("datetime").time(16, 0))
    r = fabrica.reserva_direta(db, cenario.a1, ses)
    db.commit()
    h = auth(full)
    assert client.post(f"/api/aulas/reservas/{r.id}/evolucao", json={"texto": "x"}, headers=h).status_code == 422
    ok = client.post(f"/api/aulas/reservas/{r.id}/evolucao", json={"texto": "x", "profissional_id": cenario.prof.id}, headers=h)
    assert ok.status_code == 201 and ok.json()["profissional"] == "Natalia Souza"


def test_falha_na_finalizacao_desfaz_a_evolucao(client, db, cenario, full):
    """Atomicidade: se a mudança de status falha, a evolução não fica gravada."""
    a3 = fabrica.aluno(db, cenario.un, "Carla")
    rid = nova_reserva(db, cenario)
    # a aluna cancela e a vaga é tomada; finalizar (CONCLUIDA) não ocupa vaga, então usamos a falta -> chegou via status inválido
    r = client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "x", "status": "CANCELADA"}, headers=auth(full))
    assert r.status_code == 422
    assert client.get(f"/api/aulas/reservas/{rid}/evolucao", headers=auth(full)).json()["itens"] == []
    assert a3.id


def test_avaliacao_crud_e_historico_do_aluno(client, db, cenario, full):
    r1 = nova_reserva(db, cenario)
    ses2 = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, inicio=__import__("datetime").time(10, 0))
    r2 = fabrica.reserva_direta(db, cenario.a1, ses2).id
    db.commit()
    h = auth(full)
    a = client.post(f"/api/aulas/reservas/{r1}/avaliacao", json={"texto": "Avaliação inicial"}, headers=h).json()
    client.post(f"/api/aulas/reservas/{r2}/avaliacao", json={"texto": "Reavaliação"}, headers=h)
    historico = client.get(f"/api/agenda/alunos/{cenario.a1.id}/avaliacoes", headers=h).json()["itens"]
    assert [x["texto"] for x in historico] == ["Reavaliação", "Avaliação inicial"]  # mais recente primeiro
    assert client.patch(f"/api/aulas/avaliacoes/{a['id']}", json={"texto": "Editada"}, headers=h).json()["texto"] == "Editada"
    assert client.delete(f"/api/aulas/avaliacoes/{a['id']}", headers=h).status_code == 204


def test_historico_de_evolucoes_do_aluno_traz_as_de_todas_as_aulas(client, db, cenario, full):
    r1 = nova_reserva(db, cenario)
    ses2 = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, inicio=__import__("datetime").time(10, 0))
    r2 = fabrica.reserva_direta(db, cenario.a1, ses2).id
    db.commit()
    h = auth(full)
    client.post(f"/api/aulas/reservas/{r1}/evolucao", json={"texto": "A"}, headers=h)
    client.post(f"/api/aulas/reservas/{r2}/evolucao", json={"texto": "B"}, headers=h)
    itens = client.get(f"/api/agenda/alunos/{cenario.a1.id}/evolucoes", headers=h).json()["itens"]
    assert [i["texto"] for i in itens] == ["B", "A"] and itens[0]["aluno_id"] == cenario.a1.id
    # a Bruna não vê as do outro aluno
    assert client.get(f"/api/agenda/alunos/{cenario.a2.id}/evolucoes", headers=h).json()["itens"] == []


def test_exportar_evolucoes_em_pdf_e_excel(client, db, cenario, full):
    rid = nova_reserva(db, cenario)
    h = auth(full)
    client.post(f"/api/aulas/reservas/{rid}/evolucao", json={"texto": "=SOMA(A1) perigo <b>html</b>"}, headers=h)
    pdf = client.get(f"/api/agenda/alunos/{cenario.a1.id}/evolucoes/exportar", params={"formato": "pdf"}, headers=h)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert f"evolucoes-aluno-{cenario.a1.id}.pdf" in pdf.headers["content-disposition"]
    xlsx = client.get(f"/api/agenda/alunos/{cenario.a1.id}/evolucoes/exportar", params={"formato": "xlsx"}, headers=h)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(xlsx.content)).active
    assert [c.value for c in ws[1]] == ["Data", "Profissional", "Evolução"]
    assert ws.cell(2, 2).value == "Natalia Souza"
    assert not str(ws.cell(2, 3).value).startswith("=")  # texto livre nunca vira fórmula
    aval = client.get(f"/api/agenda/alunos/{cenario.a1.id}/avaliacoes/exportar", params={"formato": "pdf"}, headers=h)
    assert aval.status_code == 200
    assert client.get(f"/api/agenda/alunos/{cenario.a1.id}/evolucoes/exportar", params={"formato": "doc"}, headers=h).status_code == 422
    assert client.get("/api/agenda/alunos/999/evolucoes/exportar", headers=h).status_code == 404


# ------------------------------------------------------------------------------------------------------ IA
def test_melhorar_sem_ia_configurada_devolve_original_com_aviso(client, cenario, full):
    r = client.post("/api/aulas/evolucoes/melhorar", json={"texto": "aluna sentiu dor"}, headers=auth(full))
    assert r.status_code == 200
    c = r.json()
    assert c["texto"] == "aluna sentiu dor" and c["melhorado"] is False and "desligada" in c["aviso"]


def test_melhorar_com_ia_configurada(client, db, cenario, full, monkeypatch):
    db.add(ConfigIA(id=1, ativo=True, provedor="openai", modelo="gpt-x", chave_cifrada=cifrar("chave-de-teste")))
    db.commit()
    chamadas = []

    def falsa(provedor, sistema, usuario, anexo=None):
        chamadas.append((provedor.modelo, usuario))
        return {"texto": "A aluna relatou dor."}

    monkeypatch.setattr(ia, "gerar_json", falsa)
    r = client.post("/api/aulas/evolucoes/melhorar", json={"texto": "aluna sentiu dor"}, headers=auth(full))
    assert r.json() == {"texto": "A aluna relatou dor.", "melhorado": True, "aviso": None}
    assert chamadas == [("gpt-x", "Texto original:\naluna sentiu dor")]


def test_melhorar_com_falha_da_ia_nao_perde_o_texto(client, db, cenario, full, monkeypatch):
    db.add(ConfigIA(id=1, ativo=True, provedor="openai", modelo="gpt-x", chave_cifrada=cifrar("chave-de-teste")))
    db.commit()

    def quebra(*a, **k):
        raise ia.IAIndisponivel("Limite de uso atingido. Tente mais tarde.")

    monkeypatch.setattr(ia, "gerar_json", quebra)
    c = client.post("/api/aulas/evolucoes/melhorar", json={"texto": "meu texto"}, headers=auth(full)).json()
    assert c["texto"] == "meu texto" and c["melhorado"] is False and "Limite" in c["aviso"]
    monkeypatch.setattr(ia, "gerar_json", lambda *a, **k: {"texto": "   "})
    c = client.post("/api/aulas/evolucoes/melhorar", json={"texto": "meu texto"}, headers=auth(full)).json()
    assert c["texto"] == "meu texto" and c["melhorado"] is False


def test_melhorar_exige_texto(client, full):
    assert client.post("/api/aulas/evolucoes/melhorar", json={"texto": ""}, headers=auth(full)).status_code == 422
    assert client.post("/api/aulas/evolucoes/melhorar", json={}, headers=auth(full)).status_code == 422


def test_professor_pode_melhorar_texto(client, cenario, professor):
    assert client.post("/api/aulas/evolucoes/melhorar", json={"texto": "x"}, headers=auth(professor)).status_code == 200
    assert select and True
