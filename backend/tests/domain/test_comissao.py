"""R17 - comissão do profissional. Caracterização contra backend/app/modules/comissoes/service.py do protótipo antigo."""
from datetime import date
from decimal import Decimal

import pytest

from app.domain import comissao as cm
from tests.domain.golden import golden_comissao as g


def _contas():
    """Reconstrói as contas do cenário; o profissional do contrato 1 é P1 e o do contrato 2 é P2."""
    prof_do_contrato = {1: 1, 2: 2, None: None}
    return [
        cm.ContaRecebida(id=cid, valor=valor, status=status, recebido_em=recebido, profissional_id=prof,
                         contrato_id=contrato, contrato_profissional_id=prof_do_contrato[contrato])
        for cid, contrato, prof, status, recebido, valor in g.CONTAS
    ]


def test_r17_geracao_identica_ao_prototipo_antigo():
    r = cm.gerar_comissoes("2026-10", _contas(), g.PERCENTUAIS, contas_ja_geradas=[g.CONTA_JA_GERADA])
    assert r.geradas == g.PRIMEIRA["geradas"]
    assert float(r.valor_total) == g.PRIMEIRA["valor_total"]
    # o golden inclui a comissao pre-existente da conta 3: as novas sao todas as outras
    esperado = [x for x in g.GERADAS if x[0] != g.CONTA_JA_GERADA]
    obtido = [(c.conta_receber_id, c.profissional_id, c.contrato_id, c.competencia, c.valor_base, c.percentual, c.valor, c.status)
              for c in r.comissoes]
    assert sorted(obtido) == sorted(esperado)


def test_r17_idempotente_nao_gera_duas_vezes_a_mesma_conta():
    primeira = cm.gerar_comissoes("2026-10", _contas(), g.PERCENTUAIS, [g.CONTA_JA_GERADA])
    ja = [g.CONTA_JA_GERADA, *[c.conta_receber_id for c in primeira.comissoes]]
    segunda = cm.gerar_comissoes("2026-10", _contas(), g.PERCENTUAIS, ja)
    assert (segunda.geradas, float(segunda.valor_total)) == (g.SEGUNDA["geradas"], g.SEGUNDA["valor_total"])


def test_r17_outro_mes_so_pega_pagamentos_daquele_mes():
    r = cm.gerar_comissoes("2026-11", _contas(), g.PERCENTUAIS, [g.CONTA_JA_GERADA])
    assert (r.geradas, float(r.valor_total)) == (g.OUTRO_MES["geradas"], g.OUTRO_MES["valor_total"])
    assert r.comissoes[0].competencia == date(2026, 11, 1)


def test_r17_mesma_conta_repetida_na_entrada_gera_uma_vez():
    conta = cm.ContaRecebida(1, "100", "pago", date(2026, 10, 5), profissional_id=1)
    r = cm.gerar_comissoes("2026-10", [conta, conta], {1: Decimal("10")})
    assert r.geradas == 1


def test_r17_regras_de_selecao():
    perc = {1: Decimal("10"), 3: None, 4: Decimal("0")}
    base = dict(valor="100", recebido_em=date(2026, 10, 15), profissional_id=1)
    casos = [
        (dict(id=1, status="pago"), 1),
        (dict(id=2, status="PAGO"), 1),                    # no sistema novo o status e maiusculo
        (dict(id=3, status="aberto", recebido_em=None), 0),
        (dict(id=4, status="pago", recebido_em=None), 0),
        (dict(id=5, status="pago", recebido_em=date(2026, 9, 30)), 0),
        (dict(id=6, status="pago", recebido_em=date(2026, 11, 1)), 0),   # fim exclusivo
        (dict(id=7, status="pago", recebido_em=date(2026, 10, 1)), 1),   # inicio inclusivo
        (dict(id=8, status="pago", profissional_id=3), 0),   # percentual None
        (dict(id=9, status="pago", profissional_id=4), 0),   # percentual 0
        (dict(id=10, status="pago", profissional_id=None), 0),
        (dict(id=11, status="pago", profissional_id=99), 0),  # sem percentual cadastrado
    ]
    for extra, esperado in casos:
        dados = {**base, **extra}
        conta = cm.ContaRecebida(dados["id"], dados["valor"], dados["status"], dados["recebido_em"], profissional_id=dados["profissional_id"])
        assert cm.gerar_comissoes("2026-10", [conta], perc).geradas == esperado, extra


def test_r17_profissional_da_conta_vence_o_do_contrato():
    conta = cm.ContaRecebida(1, "200", "pago", date(2026, 10, 11), profissional_id=1, contrato_id=2, contrato_profissional_id=2)
    r = cm.gerar_comissoes("2026-10", [conta], {1: Decimal("10"), 2: Decimal("12.5")})
    assert (r.comissoes[0].profissional_id, r.comissoes[0].valor) == (1, Decimal("20.00"))
    sem_prof_na_conta = cm.ContaRecebida(2, "200", "pago", date(2026, 10, 11), contrato_id=2, contrato_profissional_id=2)
    r2 = cm.gerar_comissoes("2026-10", [sem_prof_na_conta], {1: Decimal("10"), 2: Decimal("12.5")})
    assert (r2.comissoes[0].profissional_id, r2.comissoes[0].valor) == (2, Decimal("25.00"))


@pytest.mark.parametrize("base,perc,esperado", [
    ("33.33", "12.5", "4.17"),     # 4,16625 -> meio para cima
    ("0.05", "10", "0.01"),        # 0,005 -> 0,01 (nao 0,00 como o arredondamento bancario)
    ("300.00", "10", "30.00"),
    ("100.10", "10", "10.01"),
    ("250", "12.50", "31.25"),
    (33.33, 12.5, "4.17"),         # floats entram via str, como no antigo
])
def test_r17_calculo_round_half_up(base, perc, esperado):
    assert cm.calcular_valor_comissao(base, perc) == Decimal(esperado)


@pytest.mark.parametrize("texto,inicio,fim,erro", g.COMPETENCIAS)
def test_r17_parse_competencia_identico_ao_antigo(texto, inicio, fim, erro):
    if erro:
        with pytest.raises(cm.CompetenciaInvalida) as exc:
            cm.parse_competencia(texto)
        assert str(exc.value) == erro[1]
    else:
        assert cm.parse_competencia(texto) == (inicio, fim)


def test_r17_competencia_invalida_em_gerar():
    with pytest.raises(cm.CompetenciaInvalida):
        cm.gerar_comissoes("2026-13", [], {})
