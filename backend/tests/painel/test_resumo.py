"""Números do painel (cenário `mundo`, hoje = domingo 25/10/2026) e estado vazio."""

from datetime import UTC, date, datetime
from decimal import Decimal

from tests.painel.conftest import fixar_agora, mk_aluno

URL = "/api/painel/resumo"


def _alerta(r, chave):
    return next((a for a in r["alertas"]["itens"] if a["chave"] == chave), None)


def test_sem_login_401(client):
    assert client.get(URL).status_code == 401


def test_kpis(client, mundo, full):
    r = client.get(URL, headers=full).json()
    assert r["hoje"] == "2026-10-25"
    k = r["kpis"]
    assert k["alunos_ativos"] == {"visivel": True, "valor": 5, "href": "/alunos?status=ATIVO"}
    # hoje: 08:00 (Caio), 14:00 (Ana + Bia pendente), 16:00 (Dani) = 4; amanhã: Ana (a cancelada não conta) = 1
    assert (k["aulas"]["hoje"], k["aulas"]["amanha"]) == (4, 1)
    # contratos que terminam em até 30 dias (24/11 inclusive): 10/11 e 24/11
    assert k["contratos_vencendo"]["valor"] == 2
    # em aberto e não vencido: 100 + 50,50 + 70 (vence hoje) em 3 contas
    assert Decimal(k["a_receber"]["valor"]) == Decimal("220.50") and k["a_receber"]["quantidade"] == 3
    # atrasado: 200 + 30 em 2 contas (a cancelada não entra)
    assert Decimal(k["atrasado"]["valor"]) == Decimal("230.00") and k["atrasado"]["quantidade"] == 2
    assert k["atrasado"]["href"] == "/financeiro/receber?status=ATRASADO"


def test_recebido_no_mes_e_comparacao(client, mundo, full):
    rm = client.get(URL, headers=full).json()["recebido_mes"]
    assert rm["mes"] == "2026-10"
    assert Decimal(rm["valor"]) == Decimal("340.00")                       # 300 + 40
    assert Decimal(rm["mes_anterior"]) == Decimal("350.00")                # 250 + 100 (mês cheio)
    assert Decimal(rm["anterior_ate_mesmo_dia"]) == Decimal("250.00")      # até 25/09
    assert rm["variacao_pct"] == 36.0                                      # (340 - 250) / 250


def test_comparacao_sem_base_nao_inventa_percentual(client, db, full):
    from app.modules.financeiro.models import StatusReceber
    from tests.agenda import fabrica
    from tests.painel.conftest import mk_conta

    un = fabrica.unidade(db)
    a = mk_aluno(db, un, "Ana", 1)
    mk_conta(db, a, "80.00", date(2026, 10, 3), StatusReceber.PAGO, date(2026, 10, 3))
    db.commit()
    rm = client.get(URL, headers=full).json()["recebido_mes"]
    assert Decimal(rm["valor"]) == Decimal("80.00") and rm["variacao_pct"] is None


def test_aulas_por_mes_ultimos_seis(client, mundo, full):
    a = client.get(URL, headers=full).json()["aulas_por_mes"]
    assert [m["mes"] for m in a["meses"]] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert [m["rotulo"] for m in a["meses"]][0] == "mai/26"
    # out: 4 hoje + 1 amanhã + 2 em 10/10 = 7; set: 3; mai: 1; a de 30/04 fica de fora
    assert [m["total"] for m in a["meses"]] == [1, 0, 0, 0, 3, 7]
    assert a["total"] == 11


def test_ranking_de_professores_no_mes(client, mundo, full):
    r = client.get(URL, headers=full).json()["ranking_professores"]
    assert r["mes"] == "2026-10"
    assert [(i["nome"], i["total"]) for i in r["itens"]] == [("Natalia", 4), ("Carla", 3)]


def test_proximas_aulas_de_hoje_a_partir_de_agora(client, mundo, full):
    p = client.get(URL, headers=full).json()["proximas_aulas"]
    # 08:00 já terminou; 14:00 (Ana reservada, Bia pendente) e 16:00 (Dani)
    assert [(i["hora"], i["aluno"], i["professor"], i["status"]) for i in p["itens"]] == [
        ("14:00", "Ana", "Natalia", "RESERVADA"),
        ("14:00", "Bia", "Natalia", "PENDENTE"),
        ("16:00", "Dani", "Carla", "RESERVADA"),
    ]
    assert p["restantes"] == 0


def test_proximas_aulas_limita_em_oito(client, db, mundo, full):
    from datetime import time

    from app.modules.agenda import servico as agenda
    from tests.agenda import fabrica

    s = fabrica.sessao(db, mundo.un, mundo.srv, mundo.p1, date(2026, 10, 25), time(20, 0), capacidade=20)
    for n in range(10):
        agenda.criar_reserva(db, mk_aluno(db, mundo.un, f"Extra {n:02d}", 100 + n).id, s.id)
    db.commit()
    p = client.get(URL, headers=full).json()["proximas_aulas"]
    assert len(p["itens"]) == 8
    assert p["restantes"] == 5  # 3 já existentes + 10 novas = 13


def test_aniversariantes_hoje_e_proximos_sete_dias(client, mundo, full):
    a = client.get(URL, headers=full).json()["aniversariantes"]["itens"]
    assert [(x["nome"], x["dia"], x["idade"], x["hoje"]) for x in a] == [
        ("Ana", "2026-10-25", 36, True),
        ("Dani", "2026-10-26", 34, False),
        ("Bia", "2026-10-30", 41, False),
    ]  # Caio (02/11) fica a 8 dias; a aluna inativa não aparece


def test_aniversariantes_na_virada_do_ano(client, db, monkeypatch, full):
    from tests.agenda import fabrica

    un = fabrica.unidade(db)
    mk_aluno(db, un, "Fim de ano", 1, date(1990, 12, 30))
    mk_aluno(db, un, "Ano novo", 2, date(2000, 1, 2))
    mk_aluno(db, un, "Fora", 3, date(2000, 1, 6))
    db.commit()
    fixar_agora(monkeypatch, datetime(2026, 12, 29, 15, 0, tzinfo=UTC))
    a = client.get(URL, headers=full).json()["aniversariantes"]["itens"]
    assert [(x["nome"], x["dia"], x["idade"]) for x in a] == [("Fim de ano", "2026-12-30", 36), ("Ano novo", "2027-01-02", 27)]


def test_aniversario_de_29_de_fevereiro_em_ano_nao_bissexto(client, db, monkeypatch, full):
    from tests.agenda import fabrica

    un = fabrica.unidade(db)
    mk_aluno(db, un, "Bissexta", 1, date(2000, 2, 29))
    db.commit()
    fixar_agora(monkeypatch, datetime(2027, 2, 25, 15, 0, tzinfo=UTC))
    a = client.get(URL, headers=full).json()["aniversariantes"]["itens"]
    assert [(x["nome"], x["dia"]) for x in a] == [("Bissexta", "2027-02-28")]


def test_alertas(client, mundo, full):
    r = client.get(URL, headers=full).json()
    assert r["alertas"]["visivel"] is True
    atras = _alerta(r, "contas_atrasadas")
    assert atras["quantidade"] == 2 and Decimal(atras["valor"]) == Decimal("230.00") and atras["gravidade"] == "critico"
    assert _alerta(r, "aulas_sem_evolucao")["quantidade"] == 1  # só 10/10 (Ana); 15/09 está fora dos 30 dias, a de Bia tem evolução
    assert _alerta(r, "contratos_nao_assinados")["quantidade"] == 1  # o encerrado em 01/10 não conta
    assert _alerta(r, "reposicoes_pendentes")["quantidade"] == 1  # a APROVADA não conta
    assert _alerta(r, "whatsapp_sessao")["quantidade"] == 1
    assert _alerta(r, "whatsapp_automatico_desligado") is not None
    assert _alerta(r, "totalpass_erro")["quantidade"] == 1  # o evento antigo e o processado não contam
    graves = [a["gravidade"] for a in r["alertas"]["itens"]]
    assert graves == sorted(graves, key=["critico", "aviso", "info"].index)  # críticos primeiro


def test_estado_vazio_banco_novo(client, db, full):
    r = client.get(URL, headers=full).json()
    assert r["vazio"] is True
    k = r["kpis"]
    assert k["alunos_ativos"]["valor"] == 0 and k["aulas"]["hoje"] == 0 and k["contratos_vencendo"]["valor"] == 0
    assert Decimal(k["a_receber"]["valor"]) == 0 and Decimal(k["atrasado"]["valor"]) == 0
    assert Decimal(r["recebido_mes"]["valor"]) == 0 and r["recebido_mes"]["variacao_pct"] is None
    assert [m["total"] for m in r["aulas_por_mes"]["meses"]] == [0] * 6
    assert r["ranking_professores"]["itens"] == [] and r["proximas_aulas"]["itens"] == []
    assert r["aniversariantes"]["itens"] == [] and r["alertas"]["itens"] == []
    pp = r["primeiros_passos"]
    assert pp["visivel"] and not pp["completo"]
    assert [(p["chave"], p["feito"]) for p in pp["passos"]] == [
        ("unidade", False), ("servico", False), ("plano", False), ("profissional", False), ("aluno", False), ("whatsapp", False)
    ]


def test_primeiros_passos_somem_quando_ha_dados(client, mundo, full):
    pp = client.get(URL, headers=full).json()["primeiros_passos"]
    assert pp["completo"] is True
    assert {p["chave"]: p["feito"] for p in pp["passos"]} == {
        "unidade": True, "servico": True, "plano": True, "profissional": True, "aluno": True, "whatsapp": True
    }
