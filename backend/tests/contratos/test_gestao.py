"""Gestão: chips com contagem (vigência pelo domínio), filtros, busca, editar sem sobrescrever valor, renovar, encerrar, recalcular."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.models import Auditoria
from app.domain import contratos as dom
from app.modules.cadastros.models import Plano
from app.modules.contratos.models import Contrato, StatusAssinatura
from app.modules.financeiro.models import ContaReceber, StatusReceber
from tests.contratos.conftest import HOJE, cabecalho, png_data_url


def _criar_varios(db, cen):
    """Contratos com fins variados em relação a HOJE (25/10/2026)."""
    casos = {
        "futuro": (HOJE + timedelta(days=10), HOJE + timedelta(days=100)),
        "ativo_longe": (HOJE - timedelta(days=30), HOJE + timedelta(days=200)),
        "vence_7": (HOJE - timedelta(days=60), HOJE + timedelta(days=7)),
        "vence_30": (HOJE - timedelta(days=60), HOJE + timedelta(days=30)),
        "vence_31": (HOJE - timedelta(days=60), HOJE + timedelta(days=31)),
        "vence_hoje": (HOJE - timedelta(days=60), HOJE),
        "vencido": (HOJE - timedelta(days=60), HOJE - timedelta(days=1)),
    }
    ids = {}
    for nome, (ini, fim) in casos.items():
        c = Contrato(aluno_id=cen.aluno.id, plano_id=cen.plano.id, unidade_id=cen.un.id, profissional_id=cen.p1.id,
                     data_inicio=ini, data_fim=fim, valor_parcela=Decimal("300"), valor_total=Decimal("900"), valor_aula=Decimal("37.50"))
        db.add(c)
        db.flush()
        ids[nome] = c.id
    db.commit()
    return casos, ids


def test_chips_e_contagens_seguem_o_dominio(client, full, db, cen):
    casos, ids = _criar_varios(db, cen)
    h = cabecalho(full)
    periodos = list(casos.values())
    esperado = dom.resumo_gestao(periodos, HOJE)
    j = client.get("/api/contratos", params={"chip": "ativos"}, headers=h).json()
    assert j["contagens"] == {"ativos": esperado["ativos"], "vencendo": esperado["vencendo"], "vencidos": esperado["vencidos"],
                              "nao_assinados": 6, "total": 7}
    for chip in ("ativos", "vencendo", "vencidos", "todos"):
        r = client.get("/api/contratos", params={"chip": chip}, headers=h).json()
        esp = {i for n, i in ids.items() if dom.passa_no_filtro(chip, *casos[n], HOJE)}
        assert {x["id"] for x in r["itens"]} == esp, chip
        assert r["total"] == len(esp)
    vencendo = {x["id"] for x in client.get("/api/contratos", params={"chip": "vencendo"}, headers=h).json()["itens"]}
    assert ids["vence_30"] in vencendo and ids["vence_31"] not in vencendo and ids["vence_hoje"] in vencendo
    assert ids["futuro"] not in {x["id"] for x in client.get("/api/contratos", params={"chip": "ativos"}, headers=h).json()["itens"]}


def test_situacao_do_contrato_vem_do_dominio(client, full, db, cen):
    _casos, ids = _criar_varios(db, cen)
    itens = {x["id"]: x for x in client.get("/api/contratos", params={"chip": "todos", "por_pagina": 50}, headers=cabecalho(full)).json()["itens"]}
    assert itens[ids["vencido"]]["situacao"] == {"rotulo": "Vencido", "badge": "danger", "dias_restantes": -1}
    assert itens[ids["vence_7"]]["situacao"]["rotulo"] == "Vence esta semana"
    assert itens[ids["vence_30"]]["situacao"]["rotulo"] == "Vence em breve"
    assert itens[ids["ativo_longe"]]["situacao"]["rotulo"] == "Vigente"


def test_chip_nao_assinados_ignora_vencidos_e_assinados(client, full, db, cen):
    _casos, ids = _criar_varios(db, cen)
    db.get(Contrato, ids["ativo_longe"]).status_assinatura = StatusAssinatura.ASSINADO
    db.commit()
    j = client.get("/api/contratos", params={"chip": "nao_assinados"}, headers=cabecalho(full)).json()
    got = {x["id"] for x in j["itens"]}
    assert ids["vencido"] not in got and ids["ativo_longe"] not in got and ids["futuro"] in got
    assert j["total"] == len(got) == j["contagens"]["nao_assinados"] == 5


def test_filtros_aluno_plano_periodo_e_busca(client, full, db, cen):
    _criar_varios(db, cen)
    outro = Contrato(aluno_id=cen.outro.id, plano_id=cen.avulso.id, unidade_id=cen.un.id, profissional_id=cen.p2.id,
                     data_inicio=date(2025, 1, 1), data_fim=date(2025, 3, 31), valor_parcela=Decimal("80"), valor_total=Decimal("80"))
    db.add(outro)
    db.commit()
    h = cabecalho(full)
    por_aluno = client.get("/api/contratos", params={"chip": "todos", "aluno_id": cen.outro.id}, headers=h).json()
    assert [x["id"] for x in por_aluno["itens"]] == [outro.id]
    por_plano = client.get("/api/contratos", params={"chip": "todos", "plano_id": cen.avulso.id}, headers=h).json()
    assert por_plano["total"] == 1
    periodo = client.get("/api/contratos", params={"chip": "todos", "de": "2025-02-01", "ate": "2025-02-28"}, headers=h).json()
    assert [x["id"] for x in periodo["itens"]] == [outro.id]
    assert client.get("/api/contratos", params={"chip": "todos", "q": "joão"}, headers=h).json()["total"] == 1
    assert client.get("/api/contratos", params={"chip": "todos", "q": cen.outro.cpf}, headers=h).json()["total"] == 1
    # as contagens respeitam os filtros (menos o chip)
    assert client.get("/api/contratos", params={"aluno_id": cen.outro.id}, headers=h).json()["contagens"]["total"] == 1


def test_detalhe_traz_parcelas_assinatura_e_telefone(client, full, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    d = client.get(f"/api/contratos/{cid}", headers=cabecalho(full)).json()
    assert len(d["parcelas"]) == 3 and d["parcelas"][0]["situacao"] == "ABERTO"
    assert d["aluno_email"] == "maria@exemplo.com.br" and d["aluno_telefone"]
    assert d["valores_divergem_do_plano"] is False and d["assinatura"]["nome"] is None
    assert client.get("/api/contratos/99999", headers=cabecalho(full)).status_code == 404


# ------------------------------------------------------------------------------------------------------ editar
def test_editar_nao_sobrescreve_valor_sem_confirmar_e_avisa(client, full, db, cen, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    h = cabecalho(full)
    # valor digitado à mão
    r = client.put(f"/api/contratos/{cid}", json={"valor_parcela": "250.00", "valor_total": "750.00"}, headers=h)
    assert r.status_code == 200 and Decimal(r.json()["valor_parcela"]) == Decimal("250.00")
    assert r.json()["valores_divergem_do_plano"] is True and any("diferem do plano" in a for a in r.json()["avisos"])
    # o plano muda de preço; editar só as datas NÃO mexe nos valores manuais
    cen.plano.valor = Decimal("400.00")
    db.commit()
    r = client.put(f"/api/contratos/{cid}", json={"data_fim": "2027-03-31"}, headers=h)
    assert Decimal(r.json()["valor_parcela"]) == Decimal("250.00") and r.json()["data_fim"] == "2027-03-31"
    assert any("parcelas já geradas não foram alteradas" in a for a in r.json()["avisos"])
    # confirmando, recalcula pela regra R1 com o plano atual (400,00 · 2x · 3 meses)
    r = client.put(f"/api/contratos/{cid}", json={"recalcular_valores": True}, headers=h)
    d = r.json()
    assert (Decimal(d["valor_aula"]), Decimal(d["valor_parcela"]), Decimal(d["valor_total"])) == (Decimal("50.00"), Decimal("400.00"), Decimal("1200.00"))
    assert d["valores_divergem_do_plano"] is False
    # as parcelas já geradas continuam como estavam
    assert {x["valor"] for x in d["parcelas"]} == {"300.00"}
    acoes = [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id))]
    assert acoes.count("contrato.editar") == 3


def test_recalcular_e_valor_manual_juntos_sao_recusados(client, full, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    r = client.put(f"/api/contratos/{cid}", json={"recalcular_valores": True, "valor_parcela": "100"}, headers=cabecalho(full))
    assert r.status_code == 422


def test_editar_contrato_assinado_exige_confirmacao_para_mudar_o_contratual(client, full, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    h = cabecalho(full)
    assert client.post(f"/api/contratos/{cid}/assinatura-local", headers=h, json={
        "nome": "Maria da Silva Souza", "documento": "529.982.247-25", "assinatura": png_data_url()}).status_code == 200
    r = client.put(f"/api/contratos/{cid}", json={"data_fim": "2027-06-30"}, headers=h)
    assert r.status_code == 409 and "já foi assinado" in r.json()["detail"]
    assert client.put(f"/api/contratos/{cid}", json={"forma_pagamento": "DINHEIRO"}, headers=h).status_code == 200
    assert client.put(f"/api/contratos/{cid}", json={"data_fim": "2027-06-30", "confirmar_alterar_assinado": True}, headers=h).status_code == 200


def test_editar_valida_datas_e_referencias(client, full, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    h = cabecalho(full)
    assert client.put(f"/api/contratos/{cid}", json={"data_fim": "2020-01-01"}, headers=h).status_code == 422
    assert client.put(f"/api/contratos/{cid}", json={"unidade_id": 9999}, headers=h).status_code == 422
    assert client.put(f"/api/contratos/{cid}", json={"profissional_id": 9999}, headers=h).status_code == 422


# ----------------------------------------------------------------------------------------- renovar / encerrar
def test_renovar_cria_novo_contrato_no_dia_seguinte(client, full, db, novo_contrato):
    antigo = novo_contrato()["contrato"]
    r = client.post(f"/api/contratos/{antigo['id']}/renovar", json={}, headers=cabecalho(full))
    assert r.status_code == 201, r.text
    novo = r.json()["contrato"]
    assert novo["id"] != antigo["id"] and novo["data_inicio"] == "2027-02-02" and novo["data_fim"] == "2027-05-01"
    assert novo["forma_pagamento"] == "PIX" and len(novo["parcelas"]) == 3
    assert any(a.acao == "contrato.renovar" for a in db.scalars(select(Auditoria)))


def test_encerrar_cancela_futuras_e_nao_toca_o_pago(client, full, db, novo_contrato):
    j = novo_contrato(data_inicio="2026-09-01", data_fim="2026-12-31")
    cid = j["contrato"]["id"]
    contas = db.scalars(select(ContaReceber).where(ContaReceber.contrato_id == cid).order_by(ContaReceber.vencimento)).all()
    assert [c.vencimento for c in contas] == [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    contas[0].status = StatusReceber.PAGO
    contas[0].pagamento = date(2026, 9, 1)
    db.commit()
    r = client.post(f"/api/contratos/{cid}/encerrar", json={"motivo": "Mudou de cidade"}, headers=cabecalho(full))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["parcelas_canceladas"] == 1 and out["contrato"]["data_fim"] == "2026-10-24"
    assert out["contrato"]["situacao"]["rotulo"] == "Vencido"
    db.expire_all()
    status = [c.status for c in db.scalars(select(ContaReceber).where(ContaReceber.contrato_id == cid).order_by(ContaReceber.vencimento))]
    assert status == [StatusReceber.PAGO, StatusReceber.ABERTO, StatusReceber.CANCELADO]  # a de 01/10 já venceu: segue em aberto
    assert client.post(f"/api/contratos/{cid}/encerrar", json={}, headers=cabecalho(full)).status_code == 409


# -------------------------------------------------------------------------------------------------- recalcular
def test_recalcular_simula_e_aplica(client, full, db, cen):
    c = Contrato(aluno_id=cen.aluno.id, plano_id=cen.plano.id, unidade_id=cen.un.id, profissional_id=cen.p1.id,
                 data_inicio=HOJE, data_fim=HOJE + timedelta(days=90), valor_parcela=Decimal("111.11"), valor_total=Decimal("1"), valor_aula=None)
    ok = Contrato(aluno_id=cen.aluno.id, plano_id=cen.plano.id, unidade_id=cen.un.id, profissional_id=cen.p1.id,
                  data_inicio=HOJE, data_fim=HOJE + timedelta(days=90), valor_parcela=Decimal("300.00"), valor_total=Decimal("900.00"),
                  valor_aula=Decimal("37.50"))
    db.add_all([c, ok])
    db.commit()
    h = cabecalho(full)
    r = client.post("/api/contratos/recalcular", json={}, headers=h)
    assert r.status_code == 200
    j = r.json()
    assert j["simulacao"] is True and j["verificados"] == 2 and j["alterados"] == 1
    assert j["itens"][0]["contrato_id"] == c.id and Decimal(j["itens"][0]["depois"]["valor_aula"]) == Decimal("37.50")
    db.expire_all()
    assert db.get(Contrato, c.id).valor_parcela == Decimal("111.11")  # simulação não grava
    j = client.post("/api/contratos/recalcular", json={"simular": False}, headers=h).json()
    assert j["alterados"] == 1
    db.expire_all()
    c = db.get(Contrato, c.id)
    assert (c.valor_aula, c.valor_parcela, c.valor_total) == (Decimal("37.50"), Decimal("300.00"), Decimal("900.00"))
    assert client.post("/api/contratos/recalcular", json={"simular": False}, headers=h).json()["alterados"] == 0
    assert any(a.acao == "contrato.recalcular" for a in db.scalars(select(Auditoria)))


def test_recalcular_filtra_por_id_e_vigencia(client, full, db, cen):
    velho = Contrato(aluno_id=cen.aluno.id, plano_id=cen.plano.id, unidade_id=cen.un.id, profissional_id=cen.p1.id,
                     data_inicio=date(2024, 1, 1), data_fim=date(2024, 3, 31), valor_parcela=Decimal("1"), valor_total=Decimal("1"))
    db.add(velho)
    db.commit()
    h = cabecalho(full)
    assert client.post("/api/contratos/recalcular", json={"somente_vigentes": True}, headers=h).json()["verificados"] == 0
    assert client.post("/api/contratos/recalcular", json={"contrato_ids": [velho.id]}, headers=h).json()["alterados"] == 1
    plano = db.get(Plano, cen.plano.id)
    plano.valor = Decimal("0")
    db.commit()
    j = client.post("/api/contratos/recalcular", json={"contrato_ids": [velho.id]}, headers=h).json()
    assert Decimal(j["itens"][0]["depois"]["valor_aula"]) == Decimal("0.00")
