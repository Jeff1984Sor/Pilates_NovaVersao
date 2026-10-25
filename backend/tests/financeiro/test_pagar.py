"""Contas a pagar: recorrência (R7), pagamento com comprovante, cancelamento com motivo, chips e exportação."""

import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.core import storage
from app.core.models import Auditoria
from app.modules.financeiro import consultas, servico
from app.modules.financeiro.models import ContaBancaria, ContaPagar, MovimentoConta, StatusPagar

PDF_OK = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    fixo = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(servico, "agora", lambda: fixo)
    monkeypatch.setattr(consultas, "agora", lambda: fixo)


def _corpo(cenario, **kw):
    base = {"fornecedor_id": cenario.forn.id, "categoria_id": cenario.cat_d.id, "subcategoria_id": cenario.sub_d.id,
            "vencimento": "2026-11-05", "valor": "1500.00", "descricao": "Aluguel"}
    return {**base, **kw}


def _criar(client, adm, cenario, **kw):
    r = client.post("/api/financeiro/pagar", json=_corpo(cenario, **kw), headers=adm)
    assert r.status_code == 201, r.text
    return r.json()["criadas"]


def test_criar_conta_simples(client, adm, db, cenario):
    c = _criar(client, adm, cenario)
    assert len(c) == 1 and c[0]["situacao"] == "AGENDADO" and c[0]["fornecedor_nome"] == "Imobiliária Centro"
    assert c[0]["categoria_nome"] == "Aluguel e contas" and c[0]["recorrencia"] is None
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "criar", Auditoria.entidade == "conta_pagar"))


def test_recorrencia_mensal_dia_limitado_a_28_e_sem_cascata(client, adm, db, cenario):
    contas = _criar(client, adm, cenario, vencimento="2026-01-31", recorrencia="MENSAL", recorrencia_quantidade=4)
    assert [c["vencimento"] for c in contas] == ["2026-01-31", "2026-02-28", "2026-03-28", "2026-04-28"]  # original mantém o dia
    assert contas[0]["recorrencia"] == "MENSAL" and contas[0]["recorrencia_quantidade"] == 4
    # cópias NÃO são recorrentes (sem regeneração em cascata) mas ficam ligadas pelo grupo
    assert all(c["recorrencia"] is None for c in contas[1:])
    assert len({c["recorrencia_grupo"] for c in contas}) == 1 and contas[0]["recorrencia_grupo"]
    assert db.query(ContaPagar).count() == 4
    # editar uma cópia ou a original não gera nada novo
    client.put(f"/api/financeiro/pagar/{contas[1]['id']}", json={"valor": "1600.00"}, headers=adm)
    client.put(f"/api/financeiro/pagar/{contas[0]['id']}", json={"descricao": "Aluguel (reajustado)"}, headers=adm)
    assert db.query(ContaPagar).count() == 4


def test_recorrencia_semanal_e_anual(client, adm, cenario):
    sem = _criar(client, adm, cenario, vencimento="2026-11-02", recorrencia="SEMANAL", recorrencia_quantidade=3)
    assert [c["vencimento"] for c in sem] == ["2026-11-02", "2026-11-09", "2026-11-16"]
    anu = _criar(client, adm, cenario, vencimento="2026-02-28", recorrencia="ANUAL", recorrencia_quantidade=3)
    assert [c["vencimento"] for c in anu] == ["2026-02-28", "2027-02-28", "2028-02-28"]
    # recorrência sem quantidade vale 1 lançamento
    um = _criar(client, adm, cenario, recorrencia="MENSAL")
    assert len(um) == 1 and um[0]["recorrencia_quantidade"] == 1 and um[0]["recorrencia_grupo"] is None


def test_validacao_de_vinculos(client, adm, cenario):
    r = client.post("/api/financeiro/pagar", json=_corpo(cenario, subcategoria_id=cenario.sub_r.id), headers=adm)
    assert r.status_code == 422 and "subcategoria" in r.json()["detail"].lower()
    assert client.post("/api/financeiro/pagar", json=_corpo(cenario, fornecedor_id=999), headers=adm).status_code == 422
    assert client.post("/api/financeiro/pagar", json=_corpo(cenario, recorrencia="DIARIA"), headers=adm).status_code == 422
    assert client.post("/api/financeiro/pagar", json=_corpo(cenario, valor="-5"), headers=adm).status_code == 422


def test_pagar_com_comprovante_e_baixar_o_arquivo(client, adm, db, cenario):
    cid = _criar(client, adm, cenario)[0]["id"]
    r = client.post(f"/api/financeiro/pagar/{cid}/pagar", headers=adm, data={"data_pagamento": "2026-10-24"},
                    files={"comprovante": ("recibo.pdf", PDF_OK, "application/pdf")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["situacao"] == "PAGO" and j["pagamento"] == "2026-10-24" and j["tem_comprovante"] is True
    db.expire_all()
    caminho = db.get(ContaPagar, cid).comprovante_path
    assert caminho.startswith("comprovantes/contas_pagar/") and caminho.endswith(".pdf") and storage.existe(caminho)
    d = client.get(f"/api/financeiro/pagar/{cid}/comprovante", headers=adm)
    assert d.status_code == 200 and d.content == PDF_OK
    # também pelo endpoint genérico de arquivos (categoria "comprovantes" exige financeiro_pagar.ver)
    assert client.get(f"/api/arquivos/{caminho}", headers=adm).status_code == 200
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "pagar"))


def test_comprovante_invalido_e_recusado_sem_pagar(client, adm, db, cenario):
    cid = _criar(client, adm, cenario)[0]["id"]
    url = f"/api/financeiro/pagar/{cid}/pagar"
    r = client.post(url, headers=adm, files={"comprovante": ("virus.exe", b"MZ....", "application/octet-stream")})
    assert r.status_code == 422 and "Tipo de arquivo" in r.json()["detail"]
    r = client.post(url, headers=adm, files={"comprovante": ("falso.pdf", b"isto nao e pdf", "application/pdf")})
    assert r.status_code == 422
    db.expire_all()
    assert db.get(ContaPagar, cid).status == StatusPagar.AGENDADO


def test_pagar_com_conta_bancaria_gera_saida_e_reabrir_remove(client, adm, db, cenario):
    banco = ContaBancaria(banco="Banco X", agencia="1", conta="2", saldo_inicial=Decimal("5000"))
    db.add(banco)
    db.commit()
    cid = _criar(client, adm, cenario)[0]["id"]
    r = client.post(f"/api/financeiro/pagar/{cid}/pagar", headers=adm, data={"conta_bancaria_id": str(banco.id)},
                    files={"comprovante": ("c.pdf", PDF_OK, "application/pdf")})
    assert r.status_code == 200
    m = db.scalars(select(MovimentoConta)).one()
    assert m.tipo.value == "SAIDA" and m.valor == Decimal("1500.00") and m.conta_pagar_id == cid and m.comprovante_path
    assert Decimal(client.get("/api/financeiro/bancos/contas", headers=adm).json()[0]["saldo_atual"]) == Decimal("3500.00")
    r = client.post(f"/api/financeiro/pagar/{cid}/reabrir", headers=adm)
    assert r.json()["situacao"] == "AGENDADO" and r.json()["pagamento"] is None
    db.expire_all()
    assert db.scalars(select(MovimentoConta)).all() == []


def test_pagar_regras(client, adm, cenario):
    cid = _criar(client, adm, cenario)[0]["id"]
    url = f"/api/financeiro/pagar/{cid}/pagar"
    assert client.post(url, headers=adm, data={"data_pagamento": "2026-12-01"}).status_code == 422  # futura
    assert client.post(url, headers=adm).status_code == 200  # padrão: hoje (25/10, Brasília)
    assert client.get(f"/api/financeiro/pagar/{cid}", headers=adm).json()["pagamento"] == "2026-10-25"
    assert client.post(url, headers=adm).status_code == 409
    assert client.delete(f"/api/financeiro/pagar/{cid}", headers=adm).status_code == 409  # paga não exclui
    assert client.get(f"/api/financeiro/pagar/{cid}/comprovante", headers=adm).status_code == 404


def test_cancelar_com_motivo_e_reabrir(client, adm, db, cenario):
    cid = _criar(client, adm, cenario)[0]["id"]
    url = f"/api/financeiro/pagar/{cid}"
    assert client.post(f"{url}/cancelar", json={}, headers=adm).status_code == 422
    r = client.post(f"{url}/cancelar", json={"motivo": "Contrato rescindido"}, headers=adm)
    assert r.json()["situacao"] == "CANCELADO" and r.json()["motivo_cancelamento"] == "Contrato rescindido"
    assert client.post(f"{url}/pagar", headers=adm).status_code == 409
    assert client.put(url, json={"valor": "1"}, headers=adm).status_code == 409
    assert client.post(f"{url}/reabrir", headers=adm).json()["situacao"] == "AGENDADO"
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "cancelar", Auditoria.entidade == "conta_pagar"))


def test_excluir_remove_comprovante_do_disco(client, adm, db, cenario):
    cid = _criar(client, adm, cenario)[0]["id"]
    client.post(f"/api/financeiro/pagar/{cid}/comprovante", headers=adm, files={"comprovante": ("c.pdf", PDF_OK, "application/pdf")})
    db.expire_all()
    caminho = db.get(ContaPagar, cid).comprovante_path
    assert storage.existe(caminho)
    assert client.delete(f"/api/financeiro/pagar/{cid}", headers=adm).status_code == 200
    assert not storage.existe(caminho)


def test_lista_com_chips_atrasado_derivado_e_filtros(client, adm, db, cenario):
    for venc, valor, status in [("2026-10-01", "100", StatusPagar.AGENDADO), ("2026-10-25", "50", StatusPagar.AGENDADO),
                                ("2026-11-10", "70", StatusPagar.AGENDADO), ("2026-10-02", "30", StatusPagar.PAGO),
                                ("2026-10-03", "20", StatusPagar.CANCELADO)]:
        db.add(ContaPagar(fornecedor_id=cenario.forn.id, categoria_id=cenario.cat_d.id, subcategoria_id=cenario.sub_d.id,
                          vencimento=date.fromisoformat(venc), valor=Decimal(valor), status=status,
                          pagamento=date(2026, 10, 2) if status == StatusPagar.PAGO else None))
    db.commit()
    r = client.get("/api/financeiro/pagar", headers=adm).json()
    ch = {c["situacao"]: (c["quantidade"], Decimal(c["valor"])) for c in r["chips"]}
    assert ch == {"TODOS": (5, Decimal("270")), "AGENDADO": (2, Decimal("120")), "ATRASADO": (1, Decimal("100")),
                  "PAGO": (1, Decimal("30")), "CANCELADO": (1, Decimal("20"))}
    a = client.get("/api/financeiro/pagar", params={"situacao": "ATRASADO"}, headers=adm).json()
    assert a["total"] == 1 and a["itens"][0]["status"] == "AGENDADO" and a["itens"][0]["dias_atraso"] == 24
    assert client.get("/api/financeiro/pagar", params={"de": "2026-11-01", "ate": "2026-11-30"}, headers=adm).json()["total"] == 1
    assert client.get("/api/financeiro/pagar", params={"q": "imobili"}, headers=adm).json()["total"] == 5
    assert client.get("/api/financeiro/pagar", params={"fornecedor_id": 999}, headers=adm).json()["total"] == 0


def test_exportar_excel_e_pdf(client, adm, db, cenario):
    _criar(client, adm, cenario, recorrencia="MENSAL", recorrencia_quantidade=2)
    r = client.get("/api/financeiro/pagar/exportar", params={"formato": "xlsx"}, headers=adm)
    linhas = list(load_workbook(io.BytesIO(r.content)).active.values)
    assert len(linhas) == 1 + 2 + 1 and linhas[-1][-1] == 3000.0 and linhas[1][0] == "Imobiliária Centro"
    p = client.get("/api/financeiro/pagar/exportar", params={"formato": "pdf"}, headers=adm)
    assert p.content.startswith(b"%PDF")
