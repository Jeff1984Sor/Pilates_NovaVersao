"""Comissões (R17): percentual do cadastro sobre contas PAGAS na competência; idempotente; marcar como paga."""

import io
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.cadastros.models import Profissional
from app.modules.financeiro import comissoes as srv
from app.modules.financeiro import servico
from app.modules.financeiro.models import Comissao, ContaReceber, StatusReceber

D = Decimal


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    monkeypatch.setattr(servico, "agora", lambda: datetime(2026, 10, 25, 15, 0, tzinfo=UTC))


def _paga(db, aluno_id, valor, pag, **kw):
    c = ContaReceber(aluno_id=aluno_id, valor=D(str(valor)), vencimento=pag, status=StatusReceber.PAGO, pagamento=pag,
                     competencia=pag.strftime("%Y-%m"), **kw)
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def mundo(db, cenario):
    outro_prof = Profissional(nome="Bruno Pilates", comissao_percentual=D("12.5"))
    sem_perc = Profissional(nome="Carla Sem Comissao", comissao_percentual=D("0"))
    db.add_all([outro_prof, sem_perc])
    db.flush()
    # contrato da Maria é da Ana (10%): 300,00 -> 30,00
    c1 = _paga(db, cenario.aluno.id, "300.00", date(2026, 10, 12), contrato_id=cenario.contrato.id)
    # aula avulsa na sessão do Bruno (12,5%): 33,33 -> 4,17 (ROUND_HALF_UP)
    s = AulaSessao(unidade_id=cenario.unidade.id, tipo_servico_id=cenario.servico.id, profissional_id=outro_prof.id,
                   data=date(2026, 10, 14), hora_inicio=time(9), hora_fim=time(10))
    db.add(s)
    db.flush()
    r = Reserva(aluno_id=cenario.outro.id, aula_sessao_id=s.id)
    db.add(r)
    db.flush()
    c2 = _paga(db, cenario.outro.id, "33.33", date(2026, 10, 14), reserva_id=r.id)
    # sem profissional (avulso manual) e outra competência: não geram
    _paga(db, cenario.outro.id, "100", date(2026, 10, 20))
    _paga(db, cenario.aluno.id, "300", date(2026, 9, 12), contrato_id=cenario.contrato.id)
    # aberta não gera
    db.add(ContaReceber(aluno_id=cenario.aluno.id, valor=D("300"), vencimento=date(2026, 10, 28), status=StatusReceber.ABERTO,
                        contrato_id=cenario.contrato.id))
    db.commit()
    return c1, c2, outro_prof


def test_gerar_comissoes_calcula_e_e_idempotente(client, adm, db, cenario, mundo):
    c1, c2, outro_prof = mundo
    r = client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm)
    assert r.status_code == 200, r.text
    assert r.json()["geradas"] == 2 and D(r.json()["valor_total"]) == D("34.17")
    por_conta = {c.conta_receber_id: c for c in db.scalars(select(Comissao))}
    assert por_conta[c1.id].valor == D("30.00") and por_conta[c1.id].percentual == D("10.00") and por_conta[c1.id].profissional_id == cenario.prof.id
    assert por_conta[c2.id].valor == D("4.17") and por_conta[c2.id].valor_base == D("33.33") and por_conta[c2.id].profissional_id == outro_prof.id
    # rodar de novo não duplica
    assert client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm).json()["geradas"] == 0
    assert db.query(Comissao).count() == 2
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "gerar", Auditoria.entidade == "comissao"))


def test_competencia_estrita(client, adm):
    for ruim in ["2026-1", "26-10", "2026-13", "2026/10", "", "abc"]:
        assert client.post("/api/comissoes/gerar", json={"competencia": ruim}, headers=adm).status_code == 422, ruim
    with pytest.raises(servico.ErroDeNegocio):
        srv.validar_competencia("2026-1")


def test_listagem_resumo_e_filtros(client, adm, mundo):
    client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm)
    j = client.get("/api/comissoes", params={"competencia": "2026-10"}, headers=adm).json()
    assert len(j["itens"]) == 2 and D(j["valor_total"]) == D("34.17") and D(j["valor_pendente"]) == D("34.17")
    assert {r["profissional_nome"]: D(r["valor_total"]) for r in j["resumo"]} == {"Ana Fisio": D("30.00"), "Bruno Pilates": D("4.17")}
    assert {i["aluno_nome"] for i in j["itens"]} == {"Maria Souza", "João Lima"}
    assert client.get("/api/comissoes", params={"competencia": "2026-09"}, headers=adm).json()["itens"] == []
    so_ana = client.get("/api/comissoes", params={"profissional_id": mundo[2].id}, headers=adm).json()
    assert len(so_ana["itens"]) == 1
    assert client.get("/api/comissoes", params={"competencia": "2026-1"}, headers=adm).status_code == 422


def test_marcar_como_paga_desfazer_e_excluir(client, adm, db, mundo):
    client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm)
    ids = [c.id for c in db.scalars(select(Comissao))]
    r = client.post("/api/comissoes/pagar", json={"comissao_ids": ids[:1], "data_pagamento": "2026-10-20"}, headers=adm)
    assert r.status_code == 200
    j = client.get("/api/comissoes", headers=adm).json()
    pagas = [i for i in j["itens"] if i["paga_em"]]
    assert len(pagas) == 1 and pagas[0]["paga_em"] == "2026-10-20" and D(j["valor_pendente"]) < D(j["valor_total"])
    assert len(client.get("/api/comissoes", params={"situacao": "PAGA"}, headers=adm).json()["itens"]) == 1
    assert len(client.get("/api/comissoes", params={"situacao": "PENDENTE"}, headers=adm).json()["itens"]) == 1
    assert client.post("/api/comissoes/pagar", json={"comissao_ids": ids[:1]}, headers=adm).status_code == 409  # já paga
    assert client.post("/api/comissoes/pagar", json={"comissao_ids": ids, "data_pagamento": "2026-12-01"}, headers=adm).status_code == 422
    assert client.post("/api/comissoes/pagar", json={"comissao_ids": [9999]}, headers=adm).status_code == 404
    assert client.delete(f"/api/comissoes/{pagas[0]['id']}", headers=adm).status_code == 409
    assert client.post(f"/api/comissoes/{pagas[0]['id']}/desfazer-pagamento", headers=adm).status_code == 200
    assert client.delete(f"/api/comissoes/{pagas[0]['id']}", headers=adm).status_code == 200
    assert db.query(Comissao).count() == 1
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "pagar", Auditoria.entidade == "comissao"))


def test_excluida_pode_ser_gerada_de_novo(client, adm, db, mundo):
    client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm)
    c = db.scalars(select(Comissao)).first()
    client.delete(f"/api/comissoes/{c.id}", headers=adm)
    assert client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm).json()["geradas"] == 1


def test_estornar_baixa_com_comissao_gerada_e_recusado(client, adm, db, mundo):
    c1 = mundo[0]
    client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm)
    r = client.delete(f"/api/financeiro/receber/{c1.id}/baixa", headers=adm)
    assert r.status_code == 409 and "comissão" in r.json()["detail"].lower()
    assert client.delete(f"/api/financeiro/receber/{c1.id}", headers=adm).status_code == 409


def test_exportar(client, adm, mundo):
    client.post("/api/comissoes/gerar", json={"competencia": "2026-10"}, headers=adm)
    x = client.get("/api/comissoes/exportar", params={"competencia": "2026-10", "formato": "xlsx"}, headers=adm)
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames == ["Por profissional", "Comissões"]
    linhas = list(wb["Comissões"].values)
    assert len(linhas) == 1 + 2 + 1 and linhas[-1][5] == 34.17
    assert client.get("/api/comissoes/exportar", params={"formato": "pdf"}, headers=adm).content.startswith(b"%PDF")
