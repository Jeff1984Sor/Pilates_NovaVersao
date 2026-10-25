"""R2 - parcelas e add_months (dia limitado a 28). Caracterização contra services.gerar_parcelas."""
from datetime import date
from decimal import Decimal

import pytest

from app.domain import parcelas
from tests.domain.golden.golden_parcelas import ADD_MONTHS, COMPETENCIAS_AVULSA, MENSAIS, SEMANAIS


@pytest.mark.parametrize("base,n,esperado", ADD_MONTHS)
def test_r2_add_months_identico_ao_antigo(base, n, esperado):
    assert parcelas.add_months(base, n) == esperado


def test_r2_dia_31_vira_28_e_virada_de_ano():
    assert parcelas.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert parcelas.add_months(date(2026, 1, 31), 2) == date(2026, 3, 28)
    assert parcelas.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert parcelas.add_months(date(2026, 12, 31), 1) == date(2027, 1, 28)


def test_r2_fevereiro_bissexto_nao_aparece_29():
    assert parcelas.add_months(date(2024, 2, 29), 0) == date(2024, 2, 28)
    assert parcelas.add_months(date(2024, 1, 29), 1) == date(2024, 2, 28)


def test_r2_dia_limitado_a_28_ate_com_zero_meses():
    # COMPORTAMENTO ANTIGO: 31/01 + 0 meses -> 28/01
    assert parcelas.add_months(date(2026, 1, 31), 0) == date(2026, 1, 28)


@pytest.mark.parametrize("inicio,meses,esperado", MENSAIS)
def test_r2_parcelas_mensais_identicas_ao_antigo(inicio, meses, esperado):
    lista = parcelas.gerar_parcelas(Decimal("300.00"), inicio, date(2099, 1, 1), meses, "MENSAL")
    assert [(p.vencimento, p.competencia) for p in lista] == esperado
    assert all(p.valor == Decimal("300.00") for p in lista)


def test_r2_caso_oficial_inicio_31_01_tres_parcelas():
    lista = parcelas.gerar_parcelas(Decimal("300"), date(2026, 1, 31), date(2026, 3, 31), 3)
    assert [(p.vencimento, p.competencia) for p in lista] == [
        (date(2026, 1, 28), "2026-01"), (date(2026, 2, 28), "2026-02"), (date(2026, 3, 28), "2026-03"),
    ]


@pytest.mark.parametrize("inicio,fim,esperado", SEMANAIS)
def test_r2_parcelas_semanais_identicas_ao_antigo(inicio, fim, esperado):
    lista = parcelas.gerar_parcelas(Decimal("50"), inicio, fim, 1, "SEMANAL")
    assert [(p.vencimento, p.competencia) for p in lista] == esperado


def test_r2_semanal_competencia_usa_ano_iso():
    lista = parcelas.gerar_parcelas(Decimal("50"), date(2024, 12, 30), date(2025, 1, 6), None, "SEMANAL")
    assert [p.competencia for p in lista] == ["2025-01", "2025-02"]


@pytest.mark.parametrize("dia,rec,esperado", COMPETENCIAS_AVULSA)
def test_r2_competencia_avulsa(dia, rec, esperado):
    assert parcelas.competencia_avulsa(dia, rec) == esperado


def test_r2_meses_invalido_vira_uma_parcela():
    assert len(parcelas.gerar_parcelas(Decimal("1"), date(2026, 1, 1), date(2026, 1, 1), 0)) == 1
    assert len(parcelas.gerar_parcelas(Decimal("1"), date(2026, 1, 1), date(2026, 1, 1), -4)) == 1
