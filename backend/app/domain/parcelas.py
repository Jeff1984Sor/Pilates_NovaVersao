"""Geração de parcelas e aritmética de meses (R2).

Origem no sistema antigo:
- ``core/services.py`` ``gerar_parcelas`` e seu ``_add_months`` interno (linhas 10-33)
- ``core/views.py`` ``_add_months`` (linha 1686, idêntico) e ``_competencia_avulsa`` (223)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

DIA_MAXIMO_VENCIMENTO = 28


def add_months(base: date, meses: int) -> date:
    """``base + meses`` com o dia LIMITADO a 28 (``min(dia, 28)``), mesmo se o mês tiver 31 dias.

    Ex.: 31/01 + 1 -> 28/02; 15/11 + 3 -> 15/02 do ano seguinte.

    # COMPORTAMENTO ANTIGO: o dia é limitado a 28 também com ``meses=0`` (31/01 + 0 -> 28/01).
    Evita a aritmética de fim de mês, mas muda o dia de vencimento de quem começa nos dias 29-31.
    """
    total = (base.month - 1) + meses
    ano = base.year + total // 12
    mes = total % 12 + 1
    return date(ano, mes, min(base.day, DIA_MAXIMO_VENCIMENTO))


def competencia_mensal(vencimento: date) -> str:
    return vencimento.strftime("%Y-%m")


def competencia_semanal(vencimento: date) -> str:
    """``ISOANO-SS`` (ano ISO, não o do calendário: 31/12/2024 é 2025-01)."""
    ano_iso, semana, _ = vencimento.isocalendar()
    return f"{ano_iso}-{semana:02d}"


def competencia_avulsa(data_aula: date, recorrencia: str) -> str:
    """``views._competencia_avulsa``: MENSAL -> YYYY-MM, senão ISOANO-SEMANA."""
    return competencia_mensal(data_aula) if recorrencia == "MENSAL" else competencia_semanal(data_aula)


@dataclass(frozen=True)
class Parcela:
    valor: Decimal
    vencimento: date
    competencia: str


def gerar_parcelas(
    valor: Decimal,
    inicio: date,
    fim: date,
    meses: int | None,
    recorrencia: str = "MENSAL",
) -> list[Parcela]:
    """Parcelas de um contrato/pacote.

    - ``SEMANAL``: uma a cada 7 dias de ``inicio`` até ``fim`` (inclusive); competência ISOANO-SEMANA.
    - qualquer outro valor (inclusive ``MENSAL``): ``max(int(meses or 1), 1)`` parcelas, vencimento
      ``add_months(inicio, idx)`` (dia <= 28); competência YYYY-MM. ``fim`` é ignorado.
    """
    parcelas: list[Parcela] = []
    if recorrencia == "SEMANAL":
        vencimento = inicio
        while vencimento <= fim:
            parcelas.append(Parcela(valor, vencimento, competencia_semanal(vencimento)))
            vencimento += timedelta(days=7)
        return parcelas
    total = max(int(meses or 1), 1)
    for idx in range(total):
        vencimento = add_months(inicio, idx)
        parcelas.append(Parcela(valor, vencimento, competencia_mensal(vencimento)))
    return parcelas
