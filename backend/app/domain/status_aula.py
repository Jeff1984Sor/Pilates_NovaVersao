"""Status exibido da aula e conclusão automática (R5 e R6).

Origem no sistema antigo:
- ``core/views.py`` ``_map_status`` (3988-4003): R5
- ``core/services.py`` ``concluir_aulas_passadas`` (329-345): R6. No antigo é chamada ao abrir telas;
  no novo vira job agendado (``reservas_a_concluir`` só diz QUAIS reservas mudam).

Fuso de negócio: America/Sao_Paulo. ``agora`` deve vir com fuso; sem fuso é interpretado como horário de Brasília.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

FUSO_NEGOCIO = ZoneInfo("America/Sao_Paulo")

STATUS_PENDENTES_DE_CONCLUSAO = ("RESERVADA", "PENDENTE")

#: Mapa de ``_map_status``: status gravado -> status mostrado na grade.
MAPA_STATUS_EXIBIDO = {
    "RESERVADA": "aguardando_chegar",
    "PENDENTE": "aguardando_chegar",
    "CONCLUIDA": "finalizada",
    "FALTOU_AVISOU": "faltou",
    "FALTOU_SEM_AVISAR": "faltou",
    "CANCELADA": "remarcada",
}


def para_fuso_negocio(momento: datetime) -> datetime:
    """Converte para Brasília; datetime sem fuso é tratado como já estando em Brasília."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=FUSO_NEGOCIO)
    return momento.astimezone(FUSO_NEGOCIO)


def momento_da_sessao(dia: date, hora: time) -> datetime:
    """``timezone.make_aware(datetime.combine(dia, hora))`` com o fuso de negócio."""
    return datetime.combine(dia, hora).replace(tzinfo=FUSO_NEGOCIO)


def status_exibido(status_reserva: str, inicio: datetime, fim: datetime, agora: datetime) -> str:
    """Status da grade. RESERVADA/PENDENTE (e qualquer status desconhecido) = ``aguardando_chegar``,
    que vira ``em_aula`` quando ``inicio <= agora <= fim`` (limites INCLUSIVOS nos dois lados)."""
    mapeado = MAPA_STATUS_EXIBIDO.get(status_reserva, "aguardando_chegar")
    if mapeado == "aguardando_chegar":
        if para_fuso_negocio(inicio) <= para_fuso_negocio(agora) <= para_fuso_negocio(fim):
            return "em_aula"
    return mapeado


class _ReservaConclusivel(Protocol):
    status: str
    data: date
    hora_fim: time


def deve_concluir(status: str, data_aula: date, hora_fim: time, agora: datetime) -> bool:
    """RESERVADA/PENDENTE cuja aula já terminou: dia anterior, ou hoje com ``hora_fim <= hora atual``.

    Faltas, canceladas e concluídas nunca são tocadas.
    """
    if status not in STATUS_PENDENTES_DE_CONCLUSAO:
        return False
    local = para_fuso_negocio(agora)
    hoje = local.date()
    return data_aula < hoje or (data_aula == hoje and hora_fim <= local.time())


def reservas_a_concluir[T: _ReservaConclusivel](agora: datetime, reservas: Iterable[T]) -> list[T]:
    """Subconjunto de ``reservas`` (objetos com ``status``, ``data`` e ``hora_fim``) que viram CONCLUIDA."""
    return [r for r in reservas if deve_concluir(r.status, r.data, r.hora_fim, agora)]


@dataclass(frozen=True)
class ReservaSimples:
    """Conveniência para testes e jobs: o mínimo que ``reservas_a_concluir`` precisa."""

    id: int
    status: str
    data: date
    hora_fim: time
