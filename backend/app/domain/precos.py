"""Precificação de contrato e de aula avulsa (R1).

Origem no sistema antigo: ``core/views.py``
- ``_contrato_precificacao`` (linhas 176-194)
- ``_aula_avulsa_precificacao`` (197-209)
- data fim da aula avulsa em ``aluno_aula_avulsa_create`` (1103-1106)

Dinheiro sempre ``Decimal``; arredondamento ``ROUND_HALF_UP`` em 2 casas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.domain.parcelas import add_months

CENTAVOS = Decimal("0.01")


def arredondar_dinheiro(valor: Decimal) -> Decimal:
    """2 casas, meio para cima (3,125 -> 3,13), como ``quantize(..., ROUND_HALF_UP)`` do antigo."""
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _como_decimal(valor: object) -> Decimal:
    """``Decimal(str(valor or 0))`` do antigo."""
    return Decimal(str(valor or 0))


@dataclass(frozen=True)
class PrecificacaoContrato:
    recorrencia: str
    valor_aula: Decimal | None
    valor_parcela: Decimal
    valor_total: Decimal


def precificar_contrato(valor_plano: object, aulas_por_semana: object, duracao_meses: object) -> PrecificacaoContrato:
    """Contrato é sempre MENSAL; ``valor_plano`` é o valor MENSAL (parcela).

    - ``valor_aula = round_half_up(valor_plano / (aulas_por_semana * 4), 2)``; ``None`` se aulas_por_semana <= 0.
      É só informativo.
    - ``valor_parcela = valor_plano``.
    - ``valor_total = valor_plano * max(duracao_meses, 1)`` (duração 0/None vira 1 mês).

    # COMPORTAMENTO ANTIGO: duração negativa NÃO é limitada (``int(-2) or 1`` = -2) e gera total negativo;
    aulas_por_semana negativo dá ``valor_aula=None``. Reproduzido; o formulário antigo não permitia isso.
    """
    plano = _como_decimal(valor_plano)
    aulas = int(aulas_por_semana or 0)
    meses = int(duracao_meses or 0) or 1
    aulas_no_mes = aulas * 4
    valor_aula = arredondar_dinheiro(plano / Decimal(aulas_no_mes)) if aulas_no_mes > 0 else None
    return PrecificacaoContrato("MENSAL", valor_aula, plano, plano * meses)


@dataclass(frozen=True)
class PrecificacaoAulaAvulsa:
    recorrencia: str
    valor_base: Decimal
    valor_total: Decimal
    quantidade: int


def precificar_aula_avulsa(
    valor_plano: object,
    quantidade: object = 1,
    valor_aula_informado: object = None,
    recorrencia_plano: str | None = "SEMANAL",
    *,
    multiplicar_quantidade: bool = False,
) -> PrecificacaoAulaAvulsa:
    """Pacote de aulas avulsas.

    - ``quantidade = max(int(quantidade or 1), 1)``; valor inválido (texto, None) vira 1.
    - ``valor_base`` = valor informado (se não vazio e numérico) senão o valor do plano.
    - recorrência: a do plano, ou ``SEMANAL`` se vazia.
    - ``valor_total``: no antigo é IGUAL a ``valor_base`` (NÃO multiplica pela quantidade).

    # DÚVIDA PARA O JEFFERSON (R1): ``valor_total = valor_base`` parece bug: um pacote de 4 aulas de R$ 80
    mostra total R$ 80,00. Na prática a cobrança real é por aula (uma ``ContasReceber`` de ``valor_aula``
    por reserva, ``views.py:1297``), então o total do pacote é só informativo. Com
    ``multiplicar_quantidade=True`` o total vira ``valor_base * quantidade``. Padrão = comportamento antigo.

    # COMPORTAMENTO ANTIGO (endurecido): ``Decimal("NaN")``/``Infinity`` eram aceitos como valor informado;
    aqui valores não finitos são tratados como inválidos (usa o valor do plano).
    """
    recorrencia = recorrencia_plano or "SEMANAL"
    plano = _como_decimal(valor_plano)
    try:
        qtd = max(int(quantidade or 1), 1)
    except (TypeError, ValueError):
        qtd = 1
    valor_base = plano
    if valor_aula_informado not in (None, ""):
        try:
            candidato = Decimal(str(valor_aula_informado))
            if candidato.is_finite():
                valor_base = candidato
        except (InvalidOperation, ValueError):
            valor_base = plano
    valor_total = valor_base * qtd if multiplicar_quantidade else valor_base
    return PrecificacaoAulaAvulsa(recorrencia, valor_base, valor_total, qtd)


def data_fim_aula_avulsa(inicio: date, recorrencia: str, quantidade: int) -> date:
    """MENSAL: ``inicio + quantidade meses`` (dia limitado a 28). Senão: ``inicio + 7*quantidade`` dias."""
    if recorrencia == "MENSAL":
        return add_months(inicio, quantidade)
    return inicio + timedelta(days=7 * quantidade)
