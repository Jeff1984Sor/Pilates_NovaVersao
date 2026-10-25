"""Comissão do profissional (R17).

Origem: protótipo FastAPI do sistema antigo, ``backend/app/modules/comissoes/service.py`` (``ComissaoService.gerar``,
``parse_competencia``, ``_q2``). NÃO existe no Django em produção: é regra de requisito novo, mas o protótipo é a
referência numérica.

Regras (reproduzidas):
- só contas a receber PAGAS cuja data de recebimento cai na competência (``inicio <= recebido_em < primeiro dia do mês seguinte``);
- profissional = o da CONTA; se ela não tiver, o do CONTRATO;
- sem profissional, ou profissional com percentual nulo/zero/negativo: não gera;
- ``valor_base = round_half_up(valor, 2)``; ``valor = round_half_up(valor_base * percentual / 100, 2)``;
- UMA comissão por conta (``contas_ja_geradas`` impede repetir, inclusive na mesma execução);
- ``valor_total`` do resultado é a soma dos valores já arredondados.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_CENTAVOS = Decimal("0.01")
_CEM = Decimal("100")


class CompetenciaInvalida(ValueError):
    """O antigo respondia HTTP 422 ``competencia invalida (use YYYY-MM)``."""

    def __init__(self) -> None:
        super().__init__("competencia invalida (use YYYY-MM)")


def parse_competencia(competencia: str | None) -> tuple[date, date]:
    """``"2026-10"`` -> ``(2026-10-01, 2026-11-01)`` (primeiro dia do mês e do mês seguinte, o fim é EXCLUSIVO).

    # COMPORTAMENTO ANTIGO: aceita ``"2026-1"`` (janeiro) e ``"26-10"`` (ano 26 d.C.); recusa o resto. Reproduzido.
    """
    try:
        ano_txt, mes_txt = competencia.split("-")  # type: ignore[union-attr]
        ano, mes = int(ano_txt), int(mes_txt)
        inicio = date(ano, mes, 1)
    except (ValueError, AttributeError) as exc:
        raise CompetenciaInvalida() from exc
    fim = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return inicio, fim


def arredondar_centavos(valor: object) -> Decimal:
    """``Decimal(str(valor))`` com 2 casas, meio para cima (``_q2``)."""
    return Decimal(str(valor)).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def calcular_valor_comissao(valor_base: object, percentual: object) -> Decimal:
    """``round_half_up(round_half_up(base) * percentual / 100)``. Ex.: 33,33 x 12,5% = 4,17."""
    base = arredondar_centavos(valor_base)
    return arredondar_centavos(base * Decimal(str(percentual)) / _CEM)


@dataclass(frozen=True)
class ContaRecebida:
    """O que a comissão precisa saber de uma conta a receber."""

    id: int
    valor: object
    status: str
    recebido_em: date | None
    profissional_id: int | None = None
    contrato_id: int | None = None
    #: profissional do contrato (usado só se a conta não tiver o seu)
    contrato_profissional_id: int | None = None


@dataclass(frozen=True)
class ComissaoCalculada:
    conta_receber_id: int
    profissional_id: int
    contrato_id: int | None
    competencia: date
    valor_base: Decimal
    percentual: Decimal
    valor: Decimal
    status: str = "pendente"


@dataclass
class ResultadoGeracao:
    competencia: str
    comissoes: list[ComissaoCalculada] = field(default_factory=list)

    @property
    def geradas(self) -> int:
        return len(self.comissoes)

    @property
    def valor_total(self) -> Decimal:
        return sum((c.valor for c in self.comissoes), Decimal("0.00"))


def gerar_comissoes(
    competencia: str,
    contas: Iterable[ContaRecebida],
    percentual_por_profissional: Mapping[int, object],
    contas_ja_geradas: Iterable[int] = (),
) -> ResultadoGeracao:
    """Comissões a criar para a competência (``"YYYY-MM"``). Pura: quem chama grava o resultado.

    A ordem do resultado segue a ordem das ``contas`` recebidas. Reexecutar com ``contas_ja_geradas`` atualizado
    não gera nada de novo (idempotente).
    """
    inicio, fim = parse_competencia(competencia)
    ja = set(contas_ja_geradas)
    resultado = ResultadoGeracao(competencia)
    for conta in contas:
        if str(conta.status).lower() != "pago":
            continue
        if conta.recebido_em is None or not (inicio <= conta.recebido_em < fim):
            continue
        profissional_id = conta.profissional_id or conta.contrato_profissional_id
        if conta.id in ja or not profissional_id:
            continue
        percentual = percentual_por_profissional.get(profissional_id)
        if not percentual or Decimal(str(percentual)) <= 0:
            continue
        perc = Decimal(str(percentual))
        valor_base = arredondar_centavos(conta.valor)
        resultado.comissoes.append(
            ComissaoCalculada(
                conta_receber_id=conta.id,
                profissional_id=profissional_id,
                contrato_id=conta.contrato_id,
                competencia=inicio,
                valor_base=valor_base,
                percentual=perc,
                valor=arredondar_centavos(valor_base * perc / _CEM),
            )
        )
        ja.add(conta.id)
    return resultado
