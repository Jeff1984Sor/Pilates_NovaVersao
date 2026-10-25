"""Contas bancárias e movimentos: saldo sempre calculado, comprovante, transferência."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select

from app.core import storage
from app.core.models import Auditoria
from app.modules.financeiro import servico
from app.modules.financeiro.models import ContaBancaria, MovimentoConta

PDF_OK = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF"


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    monkeypatch.setattr(servico, "agora", lambda: datetime(2026, 10, 25, 15, 0, tzinfo=UTC))


def _conta(client, adm, banco="Banco A", saldo="1000.00"):
    r = client.post("/api/financeiro/bancos/contas", json={"banco": banco, "agencia": "0001", "conta": "123-4", "saldo_inicial": saldo},
                    headers=adm)
    assert r.status_code == 201, r.text
    return r.json()


def _mov(client, adm, conta_id, tipo, valor, data="2026-10-10", **kw):
    r = client.post("/api/financeiro/bancos/movimentos", headers=adm,
                    data={"conta_id": str(conta_id), "tipo": tipo, "valor": valor, "data": data, "descricao": "teste"}, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def test_saldo_e_sempre_calculado_e_nao_existe_coluna_de_saldo(client, adm, db):
    assert "saldo_atual" not in {c.key for c in inspect(ContaBancaria).column_attrs}
    c = _conta(client, adm)
    assert Decimal(c["saldo_atual"]) == Decimal("1000.00")
    _mov(client, adm, c["id"], "ENTRADA", "250.50")
    _mov(client, adm, c["id"], "SAIDA", "100.25")
    lista = client.get("/api/financeiro/bancos/contas", headers=adm).json()
    assert Decimal(lista[0]["saldo_atual"]) == Decimal("1150.25") and lista[0]["total_movimentos"] == 2
    # mudar o saldo inicial recalcula (nada gravado)
    client.put(f"/api/financeiro/bancos/contas/{c['id']}", headers=adm,
               json={"banco": "Banco A", "agencia": "0001", "conta": "123-4", "saldo_inicial": "0", "ativo": True})
    assert Decimal(client.get("/api/financeiro/bancos/contas", headers=adm).json()[0]["saldo_atual"]) == Decimal("150.25")


def test_movimento_com_comprovante(client, adm, db):
    c = _conta(client, adm)
    m = _mov(client, adm, c["id"], "SAIDA", "80", files={"comprovante": ("nota.pdf", PDF_OK, "application/pdf")})
    assert m["tem_comprovante"] is True
    d = client.get(f"/api/financeiro/bancos/movimentos/{m['id']}/comprovante", headers=adm)
    assert d.status_code == 200 and d.content == PDF_OK
    caminho = db.get(MovimentoConta, m["id"]).comprovante_path
    assert caminho.startswith("comprovantes/movimentos/")
    assert client.delete(f"/api/financeiro/bancos/movimentos/{m['id']}", headers=adm).status_code == 200
    assert not storage.existe(caminho)
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "excluir_movimento"))


def test_movimento_invalido(client, adm):
    c = _conta(client, adm)
    base = {"conta_id": str(c["id"]), "tipo": "ENTRADA", "valor": "10", "data": "2026-10-10"}
    assert client.post("/api/financeiro/bancos/movimentos", headers=adm, data={**base, "tipo": "TROCA"}).status_code == 422
    assert client.post("/api/financeiro/bancos/movimentos", headers=adm, data={**base, "valor": "-1"}).status_code == 422
    assert client.post("/api/financeiro/bancos/movimentos", headers=adm, data={**base, "conta_id": "999"}).status_code == 404
    r = client.post("/api/financeiro/bancos/movimentos", headers=adm, data=base,
                    files={"comprovante": ("a.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 422


def test_extrato_por_periodo_com_saldo_de_abertura(client, adm):
    c = _conta(client, adm, saldo="1000")
    _mov(client, adm, c["id"], "ENTRADA", "500", "2026-09-20")  # antes do período
    _mov(client, adm, c["id"], "ENTRADA", "200", "2026-10-05")
    _mov(client, adm, c["id"], "SAIDA", "50", "2026-10-06")
    e = client.get("/api/financeiro/bancos/extrato", params={"conta_id": c["id"], "de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).json()
    assert Decimal(e["saldo_inicial_periodo"]) == Decimal("1500") and Decimal(e["total_entradas"]) == 200
    assert Decimal(e["total_saidas"]) == 50 and Decimal(e["saldo_final"]) == Decimal("1650")
    assert [m["tipo"] for m in e["movimentos"]] == ["SAIDA", "ENTRADA"]  # mais recente primeiro
    so_ent = client.get("/api/financeiro/bancos/extrato", params={"conta_id": c["id"], "tipo": "ENTRADA", "de": "2026-10-01",
                                                                  "ate": "2026-10-31"}, headers=adm).json()
    assert len(so_ent["movimentos"]) == 1 and Decimal(so_ent["saldo_final"]) == Decimal("1650")
    x = client.get("/api/financeiro/bancos/extrato/exportar", params={"conta_id": c["id"], "formato": "pdf"}, headers=adm)
    assert x.content.startswith(b"%PDF")


def test_transferencia_entre_contas(client, adm, db):
    a, b = _conta(client, adm, "A", "1000"), _conta(client, adm, "B", "0")
    r = client.post("/api/financeiro/bancos/transferencias", headers=adm,
                    json={"conta_origem_id": a["id"], "conta_destino_id": b["id"], "valor": "300", "data": "2026-10-10"})
    assert r.status_code == 201
    saida, entrada = r.json()
    assert saida["tipo"] == "SAIDA" and entrada["tipo"] == "ENTRADA" and saida["transferencia_id"] == entrada["transferencia_id"]
    saldos = {c["banco"]: Decimal(c["saldo_atual"]) for c in client.get("/api/financeiro/bancos/contas", headers=adm).json()}
    assert saldos == {"A": Decimal("700"), "B": Decimal("300")}
    # um lado sozinho não pode ser apagado; a transferência inteira, sim
    assert client.delete(f"/api/financeiro/bancos/movimentos/{saida['id']}", headers=adm).status_code == 409
    assert client.delete(f"/api/financeiro/bancos/transferencias/{saida['transferencia_id']}", headers=adm).status_code == 200
    saldos = {c["banco"]: Decimal(c["saldo_atual"]) for c in client.get("/api/financeiro/bancos/contas", headers=adm).json()}
    assert saldos == {"A": Decimal("1000"), "B": Decimal("0")}
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "transferir"))


def test_transferencia_invalida(client, adm):
    a = _conta(client, adm)
    corpo = {"conta_origem_id": a["id"], "conta_destino_id": a["id"], "valor": "10", "data": "2026-10-10"}
    assert client.post("/api/financeiro/bancos/transferencias", json=corpo, headers=adm).status_code == 422
    assert client.post("/api/financeiro/bancos/transferencias", json={**corpo, "conta_destino_id": 999}, headers=adm).status_code == 404
    assert client.post("/api/financeiro/bancos/transferencias", json={**corpo, "conta_destino_id": a["id"] + 1, "valor": "0"},
                       headers=adm).status_code == 422


def test_conta_com_movimentos_nao_exclui_so_inativa(client, adm):
    c = _conta(client, adm)
    _mov(client, adm, c["id"], "ENTRADA", "10")
    assert client.delete(f"/api/financeiro/bancos/contas/{c['id']}", headers=adm).status_code == 409
    vazia = _conta(client, adm, "Vazia")
    assert client.delete(f"/api/financeiro/bancos/contas/{vazia['id']}", headers=adm).status_code == 200
    # conta inativa não recebe movimento
    client.put(f"/api/financeiro/bancos/contas/{c['id']}", headers=adm,
               json={"banco": "Banco A", "agencia": "0001", "conta": "123-4", "saldo_inicial": "1000", "ativo": False})
    r = client.post("/api/financeiro/bancos/movimentos", headers=adm,
                    data={"conta_id": str(c["id"]), "tipo": "ENTRADA", "valor": "1", "data": "2026-10-10"})
    assert r.status_code == 422
    assert [x["banco"] for x in client.get("/api/financeiro/bancos/contas", params={"somente_ativas": "true"}, headers=adm).json()] == []
