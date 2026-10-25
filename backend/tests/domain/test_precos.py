"""R1 - precificação de contrato e aula avulsa. Caracterização contra o sistema antigo (views._contrato_precificacao)."""
from datetime import date
from decimal import Decimal

import pytest

from app.domain import precos
from tests.domain.golden.golden_precos import AVULSAS, CONTRATOS, FINS_AVULSA


def test_r1_caso_do_contrato_plano_300_2x_3_meses():
    """Caso oficial do docs/MIGRACAO.md: 300,00 · 2x/sem · 3 meses -> aula 37,50; parcela 300,00; total 900,00."""
    p = precos.precificar_contrato(Decimal("300.00"), 2, 3)
    assert p.recorrencia == "MENSAL"
    assert p.valor_aula == Decimal("37.50")
    assert p.valor_parcela == Decimal("300.00")
    assert p.valor_total == Decimal("900.00")


@pytest.mark.parametrize("valor,aulas,meses,rec,v_aula,v_parcela,v_total", CONTRATOS)
def test_r1_contrato_identico_ao_antigo_em_grade(valor, aulas, meses, rec, v_aula, v_parcela, v_total):
    p = precos.precificar_contrato(Decimal(valor), aulas, meses)
    assert (p.recorrencia, p.valor_aula, p.valor_parcela, p.valor_total) == (rec, v_aula, v_parcela, v_total)


def test_r1_sem_aulas_por_semana_valor_aula_e_none():
    assert precos.precificar_contrato(Decimal("200"), 0, 1).valor_aula is None
    assert precos.precificar_contrato(Decimal("200"), None, 1).valor_aula is None


def test_r1_arredonda_meio_para_cima():
    # 100,50 / 8 = 12,5625 -> 12,56 ; 3,125 -> 3,13 (ROUND_HALF_UP, nao o arredondamento bancario do float)
    assert precos.precificar_contrato(Decimal("100.50"), 2, 1).valor_aula == Decimal("12.56")
    assert precos.arredondar_dinheiro(Decimal("3.125")) == Decimal("3.13")
    assert precos.arredondar_dinheiro(Decimal("2.675")) == Decimal("2.68")


def test_r1_duracao_zero_ou_nula_vira_um_mes_e_negativa_nao_e_limitada():
    assert precos.precificar_contrato(Decimal("300"), 2, 0).valor_total == Decimal("300")
    assert precos.precificar_contrato(Decimal("300"), 2, None).valor_total == Decimal("300")
    # COMPORTAMENTO ANTIGO: negativo passa direto (total negativo)
    assert precos.precificar_contrato(Decimal("300"), 2, -2).valor_total == Decimal("-600")


@pytest.mark.parametrize("rec_plano,valor,qtd,informado,rec,base,total,q", AVULSAS)
def test_r1_aula_avulsa_identica_ao_antigo_em_grade(rec_plano, valor, qtd, informado, rec, base, total, q):
    r = precos.precificar_aula_avulsa(Decimal(valor), qtd, informado, rec_plano)
    assert (r.recorrencia, r.valor_base, r.valor_total, r.quantidade) == (rec, base, total, q)


def test_r1_aula_avulsa_total_nao_multiplica_pela_quantidade_por_padrao():
    # COMPORTAMENTO ANTIGO / DUVIDA: pacote de 4 aulas de 80 -> total 80
    r = precos.precificar_aula_avulsa(Decimal("80"), 4)
    assert r.valor_base == Decimal("80") and r.valor_total == Decimal("80") and r.quantidade == 4


def test_r1_aula_avulsa_flag_multiplicar_quantidade():
    r = precos.precificar_aula_avulsa(Decimal("80"), 4, multiplicar_quantidade=True)
    assert r.valor_total == Decimal("320")


def test_r1_aula_avulsa_valor_nao_finito_usa_valor_do_plano():
    for ruim in ("NaN", "Infinity", "-Infinity"):
        assert precos.precificar_aula_avulsa(Decimal("80"), 1, ruim).valor_base == Decimal("80")


@pytest.mark.parametrize("inicio,rec,q,esperado", FINS_AVULSA)
def test_r1_data_fim_aula_avulsa(inicio, rec, q, esperado):
    assert precos.data_fim_aula_avulsa(inicio, rec, q) == esperado


def test_r1_data_fim_mensal_limita_dia_a_28():
    assert precos.data_fim_aula_avulsa(date(2026, 1, 31), "MENSAL", 1) == date(2026, 2, 28)
