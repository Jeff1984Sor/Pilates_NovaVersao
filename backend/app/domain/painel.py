"""Painel operacional e grade semanal: períodos, semana de exibição e agrupamento.

Origem no sistema antigo (``core/views.py``):
- ``_build_period_range`` (3974-3985): períodos Hoje / Amanhã / Semana do painel operacional
- ``aulas_semana`` (3731-3750): semana de seg a sáb; sem semana escolhida e hoje sábado/domingo mostra a próxima
- ``_cor_status_reserva`` (3717-3728): cor e rótulo de cada reserva na grade
- sobreposição de blocos em colunas lado a lado (3786-3820)

Tudo puro: ``hoje`` vem de quem chama (data de Brasília).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

PERIODOS = ("hoje", "amanha", "semana")


def periodo_do_painel(alvo: date | None, periodo: str | None, hoje: date) -> tuple[date, date]:
    """Intervalo ``(início, fim)`` do painel. ``alvo`` = data escolhida (ou ``hoje``).

    - ``amanha``: o dia seguinte ao alvo.
    - ``semana``: segunda a domingo da semana do alvo; # COMPORTAMENTO ANTIGO: se o alvo é sábado ou domingo,
      mostra a PRÓXIMA semana.
    - qualquer outro valor (inclusive ``hoje``): o próprio dia.
    """
    base = alvo or hoje
    if periodo == "amanha":
        d = base + timedelta(days=1)
        return d, d
    if periodo == "semana":
        inicio = base - timedelta(days=base.weekday())
        if base.weekday() >= 5:
            inicio += timedelta(days=7)
        return inicio, inicio + timedelta(days=6)
    return base, base


def semana_da_grade(referencia: date | None, hoje: date) -> tuple[date, date]:
    """Segunda e sábado da semana mostrada na grade. Sem ``referencia`` (nenhuma semana escolhida) e hoje sendo
    sábado/domingo, mostra a próxima semana (``# COMPORTAMENTO ANTIGO`` mantido por decisão do Jefferson)."""
    ref = referencia
    if ref is None:
        ref = hoje + timedelta(days=7) if hoje.weekday() >= 5 else hoje
    inicio = ref - timedelta(days=ref.weekday())
    return inicio, inicio + timedelta(days=5)


# Cor e rótulo por situação da reserva na grade (hex iguais aos do antigo).
COR_CONFIRMADA = ("#3b9ad9", "Confirmada")
COR_A_CONFIRMAR = ("#f59e0b", "A confirmar")
COR_SEM_ALUNOS = ("#cbd5e1", "Sem alunos")
_CORES_POR_STATUS = {
    "CONCLUIDA": ("#16a34a", "Concluída"),
    "FALTOU_AVISOU": ("#eab308", "Falta avisada"),
    "FALTOU_SEM_AVISAR": ("#ef4444", "Falta"),
    "CANCELADA": ("#9ca3af", "Cancelada"),
    "PENDENTE": ("#a78bfa", "Pendente"),
}


def cor_da_reserva(status: str, confirmada: bool) -> tuple[str, str]:
    """``(cor, rótulo)`` da reserva na grade. RESERVADA confirmada = azul; sem confirmar = laranja."""
    if status == "RESERVADA":
        return COR_CONFIRMADA if confirmada else COR_A_CONFIRMAR
    return _CORES_POR_STATUS.get(status, ("#94a3b8", status))


@dataclass
class BlocoMinutos:
    """Bloco de grade em minutos desde 00:00; ``coluna``/``colunas`` são preenchidos por ``distribuir_colunas``."""

    inicio: int
    fim: int
    coluna: int = 0
    colunas: int = 1
    dados: object = None  # carga livre de quem chama (o bloco da grade)


def distribuir_colunas[T: BlocoMinutos](blocos: Sequence[T]) -> list[T]:
    """Blocos que se sobrepõem no horário viram colunas lado a lado (mesmo algoritmo do antigo): agrupa em
    "clusters" de blocos encadeados e dá a cada bloco a primeira coluna livre. Devolve a lista ordenada por
    (início, fim) com ``coluna`` e ``colunas`` preenchidos."""
    ordenados = sorted(blocos, key=lambda b: (b.inicio, b.fim))
    clusters: list[list[T]] = []
    atual: list[T] = []
    fim_atual = -1
    for b in ordenados:
        if atual and b.inicio >= fim_atual:
            clusters.append(atual)
            atual, fim_atual = [], -1
        atual.append(b)
        fim_atual = max(fim_atual, b.fim)
    if atual:
        clusters.append(atual)
    for cluster in clusters:
        fins: list[int] = []
        for b in cluster:
            for i, fim in enumerate(fins):
                if b.inicio >= fim:
                    fins[i] = b.fim
                    b.coluna = i
                    break
            else:
                b.coluna = len(fins)
                fins.append(b.fim)
        for b in cluster:
            b.colunas = len(fins)
    return ordenados


def iniciais(nome: str | None) -> str:
    """Duas primeiras iniciais em maiúsculas (``"Ana Paula Souza"`` -> ``"AP"``)."""
    partes = [p for p in (nome or "").split() if p]
    return "".join(p[0] for p in partes[:2]).upper()
