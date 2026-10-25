"""Capacidade da aula e vagas (R3).

Origem no sistema antigo:
- ``core/models.py`` ``AulaSessao.capacidade_efetiva`` (linha 532) e ``Reserva.clean`` (562-571)
- ``core/views.py`` ``aula_remarcar_api`` (4741-4756): reimplementação à mão, com mensagem diferente
- ``core/views.py`` ``_build_reserva_slots`` (427-520): regra de listar slot e rótulo "N vaga(s)"
- ``_process_totalpass_payload`` (4392-4400) repete a checagem para o TotalPass.

No sistema novo a garantia contra estouro é transacional (``SELECT ... FOR UPDATE`` na sessão): estas funções
só dizem se, DADO o número de reservas ocupadas lido sob o bloqueio, cabe mais um aluno.

Só reservas ``RESERVADA`` ocupam vaga; PENDENTE, CONCLUIDA, FALTOU_* e CANCELADA não contam (``STATUS_OCUPAM_VAGA``).
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time

STATUS_OCUPAM_VAGA = frozenset({"RESERVADA"})


def capacidade_efetiva(capacidade_sessao: int | None, capacidade_unidade: int | None) -> int:
    """Capacidade da sessão, ou a da unidade se a da sessão for ``None`` (0 NÃO é "nulo": 0 vale 0)."""
    if capacidade_sessao is not None:
        return capacidade_sessao
    return capacidade_unidade or 0


def contar_ocupadas(status_das_reservas: Iterable[str]) -> int:
    """Quantas reservas ocupam vaga (somente ``RESERVADA``)."""
    return sum(1 for s in status_das_reservas if s in STATUS_OCUPAM_VAGA)


def vagas_livres(capacidade: int | None, ocupadas: int) -> int:
    """``max(capacidade - ocupadas, 0)`` (``None`` conta como 0)."""
    return max((capacidade or 0) - ocupadas, 0)


def pode_reservar(capacidade: int | None, ocupadas: int) -> bool:
    """Regra de ``Reserva.clean``: cabe mais um se ``ocupadas < capacidade``.

    Capacidade 0 (ou negativa/None) = sem vagas, como na listagem de slots. Vale para criar reserva
    RESERVADA, remarcar, contrato e TotalPass. ``ocupadas`` já deve EXCLUIR a própria reserva (ao remarcar).
    """
    return ocupadas < (capacidade or 0)


def pode_remarcar_comportamento_antigo(capacidade: int | None, ocupadas: int) -> bool:
    """# COMPORTAMENTO ANTIGO: ``aula_remarcar_api`` só recusava ``if capacidade and total >= capacidade``.

    Com capacidade 0 a remarcação PASSAVA (enquanto ``Reserva.clean`` recusa e a listagem de slots esconde).
    Mantida só para caracterização; no sistema novo use ``pode_reservar``.
    """
    return not (capacidade and ocupadas >= capacidade)


def slot_deve_ser_listado(capacidade: int | None, ocupadas: int, eh_aula_atual: bool) -> bool:
    """Regra de ``_build_reserva_slots``: o slot da própria reserva sempre aparece; os demais só se tiverem
    capacidade > 0 e vaga (``capacidade is None or capacidade <= 0 or ocupadas >= capacidade`` => escondido)."""
    if eh_aula_atual:
        return True
    return not (capacidade is None or capacidade <= 0 or ocupadas >= capacidade)


def rotulo_slot(hora_inicio: time, hora_fim: time, profissional: str | None, capacidade: int | None, ocupadas: int) -> str:
    """``"08:00 - 08:50 | Natalia (3 vaga(s))"``. O sufixo de vagas só aparece com capacidade > 0."""
    rotulo = f"{hora_inicio:%H:%M} - {hora_fim:%H:%M}"
    if profissional:
        rotulo = f"{rotulo} | {profissional}"
    if capacidade and capacidade > 0:
        rotulo = f"{rotulo} ({vagas_livres(capacidade, ocupadas)} vaga(s))"
    return rotulo


def mensagem_capacidade_excedida(data_aula: date, hora_inicio: time, ocupadas: int, capacidade: int) -> str:
    """Mensagem de ``Reserva.clean`` (criar reserva). Texto exatamente como no antigo (sem acentos)."""
    return (
        f"Capacidade excedida: a aula de {data_aula:%d/%m} as {hora_inicio:%H:%M} "
        f"ja tem {ocupadas} de {capacidade} vagas ocupadas. Escolha outro horario."
    )


def mensagem_sem_vaga_remarcacao(data_aula: date, hora_inicio: time, ocupadas: int, capacidade: int) -> str:
    """Mensagem de ``aula_remarcar_api`` (remarcar). Prefixo diferente da de ``Reserva.clean``."""
    return (
        f"Sem vaga neste horario: a aula de {data_aula:%d/%m} as {hora_inicio:%H:%M} "
        f"ja tem {ocupadas} de {capacidade} vagas ocupadas. Escolha outro horario."
    )


def validar_reserva(
    status: str,
    capacidade: int | None,
    ocupadas: int,
    data_aula: date,
    hora_inicio: time,
) -> str | None:
    """Equivalente a ``Reserva.clean``: devolve a mensagem de erro ou ``None`` se pode salvar.

    Só valida quando o status é ``RESERVADA`` (CANCELADA/PENDENTE/CONCLUIDA/FALTOU_* nunca estouram).
    """
    if status not in STATUS_OCUPAM_VAGA:
        return None
    if pode_reservar(capacidade, ocupadas):
        return None
    return mensagem_capacidade_excedida(data_aula, hora_inicio, ocupadas, capacidade or 0)
