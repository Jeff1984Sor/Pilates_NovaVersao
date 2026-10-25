"""Fluxo de caixa (por vencimento, sem CANCELADO) e DRE (por pagamento): números conferidos contra o domínio (R7)."""

import io
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.domain import financeiro as dom
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.financeiro import consultas, relatorios, servico
from app.modules.financeiro.models import (
    ContaBancaria,
    ContaPagar,
    ContaReceber,
    MovimentoConta,
    StatusPagar,
    StatusReceber,
    TipoMovimento,
)

D = Decimal


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    fixo = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(servico, "agora", lambda: fixo)
    monkeypatch.setattr(consultas, "agora", lambda: fixo)


def _rec(db, aluno_id, valor, venc, status=StatusReceber.ABERTO, pag=None, **kw):
    c = ContaReceber(aluno_id=aluno_id, valor=D(valor), vencimento=venc, status=status, pagamento=pag,
                     competencia=venc.strftime("%Y-%m"), **kw)
    db.add(c)
    db.flush()
    return c


def _pag(db, cen, valor, venc, status=StatusPagar.AGENDADO, pag=None):
    c = ContaPagar(fornecedor_id=cen.forn.id, categoria_id=cen.cat_d.id, subcategoria_id=cen.sub_d.id, valor=D(valor),
                   vencimento=venc, status=status, pagamento=pag)
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def mundo(db, cenario):
    """Outubro/2026. Receitas: contrato 300 (10/10, paga 12/10), contrato 300 (20/10, aberta), avulsa de aula 80 (15/10,
    paga 15/10), manual 50 (05/10, cancelada), manual 120 (25/10, paga 26/10... fora). Despesas: 1500 (05/10 paga 05/10),
    200 (22/10 aberta), 90 (08/10 cancelada). Bancos: conta inicial 1000; entrada 400 em 30/09; saída 100 em 12/10."""
    cen = cenario
    banco = ContaBancaria(banco="Banco X", agencia="1", conta="2", saldo_inicial=D("1000"))
    inativa = ContaBancaria(banco="Velho", agencia="9", conta="9", saldo_inicial=D("777"), ativo=False)
    db.add_all([banco, inativa])
    db.flush()
    db.add_all([
        MovimentoConta(conta_id=banco.id, tipo=TipoMovimento.ENTRADA, valor=D("400"), data=date(2026, 9, 30)),
        MovimentoConta(conta_id=banco.id, tipo=TipoMovimento.SAIDA, valor=D("100"), data=date(2026, 10, 12)),
        MovimentoConta(conta_id=inativa.id, tipo=TipoMovimento.ENTRADA, valor=D("50"), data=date(2026, 9, 1)),
    ])
    sess = AulaSessao(unidade_id=cen.unidade.id, tipo_servico_id=cen.servico.id, profissional_id=cen.prof.id,
                      data=date(2026, 10, 15), hora_inicio=time(9), hora_fim=time(10))
    db.add(sess)
    db.flush()
    reserva = Reserva(aluno_id=cen.outro.id, aula_sessao_id=sess.id)
    db.add(reserva)
    db.flush()
    _rec(db, cen.aluno.id, 300, date(2026, 10, 10), StatusReceber.PAGO, date(2026, 10, 12), contrato_id=cen.contrato.id)
    _rec(db, cen.aluno.id, 300, date(2026, 10, 20), contrato_id=cen.contrato.id)
    _rec(db, cen.outro.id, 80, date(2026, 10, 15), StatusReceber.PAGO, date(2026, 10, 15), reserva_id=reserva.id)
    _rec(db, cen.outro.id, 50, date(2026, 10, 5), StatusReceber.CANCELADO)
    _rec(db, cen.outro.id, 120, date(2026, 10, 25), StatusReceber.PAGO, date(2026, 11, 2), descricao="Avulso fora do período")
    _pag(db, cen, 1500, date(2026, 10, 5), StatusPagar.PAGO, date(2026, 10, 5))
    _pag(db, cen, 200, date(2026, 10, 22))
    _pag(db, cen, 90, date(2026, 10, 8), StatusPagar.CANCELADO)
    db.commit()
    return banco


INI, FIM = date(2026, 10, 1), date(2026, 10, 31)


def test_fluxo_de_caixa_totais_e_saldos_batem_com_o_dominio(client, adm, mundo):
    r = client.get("/api/financeiro/caixa", params={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm)
    assert r.status_code == 200, r.text
    j = r.json()
    # saldo base: só contas ATIVAS (1000 + 400 antes de outubro) = 1400; a conta inativa (777 + 50) fica de fora
    assert D(j["saldo_bancario_base"]) == D("1400")
    # receitas por vencimento, sem CANCELADO: 300 + 300 + 80 + 120 (vence 25/10) = 800; despesas: 1500 + 200 = 1700
    assert D(j["total_receitas"]) == D("800") and D(j["total_despesas"]) == D("1700")
    assert D(j["saldo_projetado_final"]) == D("1400") + 800 - 1700
    esperado = dom.fluxo_de_caixa([], [], INI, FIM, D("1400"))
    assert len(j["saldo_diario"]) == len(esperado.saldo_diario) == 31
    assert len(j["saldo_semanal"]) == len(esperado.saldo_semanal) == 5
    dias = {d["data"]: d for d in j["saldo_diario"]}
    assert D(dias["2026-10-05"]["despesas"]) == 1500 and D(dias["2026-10-05"]["saldo"]) == D("1400") - 1500
    assert D(dias["2026-10-31"]["saldo"]) == D(j["saldo_projetado_final"])
    # lançamentos ordenados (data, receita antes de despesa) e sem os cancelados
    ordem = [(x["data"], x["tipo"]) for x in j["lancamentos"]]
    assert ordem == sorted(ordem, key=lambda t: (t[0], 0 if t[1] == "Receita" else 1))
    assert all(x["status"] != "CANCELADO" for x in j["lancamentos"]) and len(j["lancamentos"]) == 6
    # semanas: 7 dias a partir do início
    assert j["saldo_semanal"][0]["inicio"] == "2026-10-01" and j["saldo_semanal"][0]["fim"] == "2026-10-07"
    assert j["saldo_semanal"][-1]["fim"] == "2026-10-31"
    assert D(j["saldo_semanal"][-1]["saldo"]) == D(j["saldo_projetado_final"])


def test_fluxo_descricoes_de_contrato_aula_avulsa_e_manual(client, adm, mundo):
    j = client.get("/api/financeiro/caixa", params={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).json()
    por = {(x["data"], x["tipo"]): x for x in j["lancamentos"]}
    c = por[("2026-10-10", "Receita")]
    assert c["descricao"].startswith("Contrato #") and c["descricao"].endswith("Maria Souza") and c["detalhe"] == "Plano 2x"
    av = por[("2026-10-15", "Receita")]
    assert av["descricao"] == "Aula avulsa - João Lima (09:00)" and av["detalhe"] == "Pilates"
    assert por[("2026-10-25", "Receita")]["descricao"].startswith("Receita #") and por[("2026-10-25", "Receita")]["detalhe"] == "Lancamento manual"
    d = por[("2026-10-05", "Despesa")]
    assert d["descricao"] == "Imobiliária Centro" and d["detalhe"] == "Aluguel e contas / Aluguel"
    assert por[("2026-10-10", "Receita")]["status"] == "PAGO" and por[("2026-10-20", "Receita")]["status"] == "ATRASADO"


def test_fluxo_filtra_por_conta_bancaria_so_no_saldo_base(client, adm, mundo):
    j = client.get("/api/financeiro/caixa", params={"de": "2026-10-01", "ate": "2026-10-31", "conta_id": mundo.id}, headers=adm).json()
    assert D(j["saldo_bancario_base"]) == D("1400") and j["conta_id"] == mundo.id
    assert client.get("/api/financeiro/caixa", params={"conta_id": 999}, headers=adm).status_code == 404


def test_fluxo_comparativo_com_o_mes_anterior(client, adm, db, cenario, mundo):
    _rec(db, cenario.aluno.id, 500, date(2026, 9, 10))
    _pag(db, cenario, 100, date(2026, 9, 12))
    db.commit()
    j = client.get("/api/financeiro/caixa", params={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).json()
    c = j["comparativo_mes_anterior"]
    assert c["periodo"] == "01/09/2026 a 30/09/2026"
    assert D(c["receitas"]) == 500 and D(c["despesas"]) == 100
    assert D(c["delta_receitas"]) == D("800") - 500 and D(c["delta_despesas"]) == D("1700") - 100


def test_fluxo_periodo_padrao_e_limites(client, adm, mundo):
    j = client.get("/api/financeiro/caixa", headers=adm).json()
    assert j["inicio"] == "2026-10-01" and j["fim"] == "2026-10-31"  # mês corrente de São Paulo
    assert client.get("/api/financeiro/caixa", params={"de": "2026-10-10", "ate": "2026-10-01"}, headers=adm).status_code == 422
    assert client.get("/api/financeiro/caixa", params={"de": "2024-01-01", "ate": "2026-12-31"}, headers=adm).status_code == 422


def test_dre_por_data_de_pagamento_e_agrupamentos(client, adm, mundo):
    j = client.get("/api/financeiro/dre", params={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).json()
    # só PAGAS com pagamento em outubro: 300 (contrato) + 80 (aula avulsa); a de 120 foi paga em novembro e a aberta não conta
    assert D(j["receita_bruta"]) == D("380") and D(j["receita_liquida"]) == D("380")
    assert D(j["deducoes"]) == 0 and D(j["custo_direto"]) == 0 and D(j["lucro_bruto"]) == D("380")
    assert D(j["despesas_operacionais"]) == D("1500")
    assert D(j["resultado_final"]) == D("380") - 1500 and j["resultado_label"] == "Prejuizo"
    # saldo bancário anterior: ativas (1000 + 400 antes de 01/10); final = anterior + receitas - despesas (R7)
    assert D(j["saldo_bancario_anterior"]) == D("1400") and D(j["saldo_bancario_final"]) == D("1400") + 380 - 1500
    por_plano = {i["nome"]: D(i["total"]) for i in j["receitas_por_plano"]}
    assert por_plano == {"Plano 2x": D("300"), "Sem plano": D("80")}  # avulsa de aula cai em "Sem plano" (como no antigo)
    assert {i["nome"]: D(i["total"]) for i in j["receitas_por_categoria"]} == {"Mensalidades": D("300"), "Sem categoria": D("80")}
    assert {i["nome"]: D(i["total"]) for i in j["receitas_por_subcategoria"]} == {"Pilates mensal": D("300"), "Sem subcategoria": D("80")}
    assert [(i["nome"], D(i["total"])) for i in j["despesas_por_categoria"]] == [("Aluguel e contas", D("1500"))]
    assert [(i["nome"], D(i["total"])) for i in j["despesas_por_subcategoria"]] == [("Aluguel", D("1500"))]
    # a ordem é a do domínio: maior total primeiro
    assert [i["nome"] for i in j["receitas_por_plano"]] == ["Plano 2x", "Sem plano"]


def test_dre_confere_com_o_dominio_diretamente(db, mundo):
    d = relatorios.calcular_dre(db, INI, FIM)
    esperado = dom.dre(
        [dom.ReceitaRecebida(D("300"), date(2026, 10, 12), plano="Plano 2x", categoria="Mensalidades", subcategoria="Pilates mensal"),
         dom.ReceitaRecebida(D("80"), date(2026, 10, 15))],
        [dom.DespesaPaga(D("1500"), date(2026, 10, 5), categoria="Aluguel e contas", subcategoria="Aluguel")],
        INI, FIM, D("1400"))
    assert d == esperado


def test_dre_lancamento_avulso_entra_em_sem_plano(client, adm, db, cenario):
    _rec(db, cenario.aluno.id, 99, date(2026, 10, 3), StatusReceber.PAGO, date(2026, 10, 3), descricao="Taxa")
    db.commit()
    j = client.get("/api/financeiro/dre", params={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).json()
    assert [(i["nome"], D(i["total"])) for i in j["receitas_por_plano"]] == [("Sem plano", D("99"))]
    assert j["resultado_label"] == "Lucro"


def test_exportar_fluxo_e_dre_excel_e_pdf(client, adm, mundo):
    p = {"de": "2026-10-01", "ate": "2026-10-31"}
    x = client.get("/api/financeiro/caixa/exportar", params={**p, "formato": "xlsx"}, headers=adm)
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames == ["Resumo", "Saldo semanal", "Saldo diário", "Lançamentos"]
    resumo = {r[0]: r[1] for r in list(wb["Resumo"].values)[1:]}
    assert resumo["Saldo projetado no fim"] == 500.0 and resumo["Total de despesas previstas"] == 1700.0
    assert len(list(wb["Saldo diário"].values)) == 32
    assert client.get("/api/financeiro/caixa/exportar", params={**p, "formato": "pdf"}, headers=adm).content.startswith(b"%PDF")
    d = client.get("/api/financeiro/dre/exportar", params={**p, "formato": "xlsx"}, headers=adm)
    wb = load_workbook(io.BytesIO(d.content))
    assert wb.sheetnames[0] == "DRE" and "Receitas por plano" in wb.sheetnames
    linhas = {r[0]: r[1] for r in list(wb["DRE"].values)[1:]}
    assert linhas["Receita bruta"] == 380.0 and linhas["Saldo bancário final"] == 280.0
    assert client.get("/api/financeiro/dre/exportar", params={**p, "formato": "pdf"}, headers=adm).content.startswith(b"%PDF")
