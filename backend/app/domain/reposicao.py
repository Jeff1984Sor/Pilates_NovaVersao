"""Desmarcar aula e reposição (R4).

Origem no sistema antigo:
- ``core/views.py`` ``aula_status_api``, ação ``desmarcar`` (4666-4688): equipe/recepção
- ``api/main.py`` ``aluno_app_desmarcar`` (505-525): app do aluno (mesma regra + 2 validações extras)
- ``api/main.py`` ``aluno_app_confirmar`` (491-502)
- cláusula 5 do contrato padrão (``set_modelo_contrato``): aviso de 6 horas. O sistema antigo NÃO valida isso.

Nada daqui lê o relógio: quem chama passa ``agora``/``hoje``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

DIAS_REPOSICAO = 30
HORAS_AVISO_CONTRATO = 6
STATUS_CANCELADA = "CANCELADA"


class SemPermissao(Exception):
    """Perfil não pode fazer a ação (professor não desmarca nem remarca)."""


class AcaoInvalida(Exception):
    """A reserva não está num estado que permita a ação (mensagem pronta para o usuário)."""


@dataclass(frozen=True)
class ResultadoDesmarcar:
    status: str
    confirmada_em: datetime | None
    desmarcada_em: datetime
    reposicao_ate: date | None


def reposicao_ate(data_aula: date | None) -> date | None:
    """``data da aula + 30 dias`` (``None`` se a reserva não tem sessão)."""
    return data_aula + timedelta(days=DIAS_REPOSICAO) if data_aula else None


def desmarcar(data_aula: date | None, agora: datetime, *, eh_professor: bool = False) -> ResultadoDesmarcar:
    """Campos gravados ao desmarcar (equipe): CANCELADA, ``confirmada_em=None``, ``desmarcada_em=agora``,
    ``reposicao_ate = data da aula + 30 dias``.

    Sem validar passado nem status (a equipe pode desmarcar qualquer aula, inclusive uma já cancelada ou
    passada; reproduz ``aula_status_api``). Professor levanta ``SemPermissao``.
    """
    if eh_professor:
        raise SemPermissao("Sem permissao para desmarcar.")
    return ResultadoDesmarcar(STATUS_CANCELADA, None, agora, reposicao_ate(data_aula))


def mensagem_reposicao(data_limite: date) -> str:
    """Texto devolvido ao aluno no app."""
    return f"Aula desmarcada. Voce pode repor ate {data_limite:%d/%m/%Y} (30 dias)."


def desmarcar_pelo_aluno(status: str, data_aula: date, hoje: date, agora: datetime) -> ResultadoDesmarcar:
    """Desmarcar pelo app do aluno: além da regra comum, recusa aula já CANCELADA e aula passada.

    ``hoje`` é a data local (America/Sao_Paulo). Aula de hoje ainda pode ser desmarcada (``data < hoje`` recusa).
    O app não valida as 6 horas de aviso (ver ``aviso_minimo_cumprido``).
    """
    if status == STATUS_CANCELADA:
        raise AcaoInvalida("Aula ja desmarcada")
    if data_aula < hoje:
        raise AcaoInvalida("Nao e possivel desmarcar uma aula que ja passou")
    return desmarcar(data_aula, agora)


def confirmar_pelo_aluno(status: str, data_aula: date, hoje: date, agora: datetime) -> datetime:
    """Confirmar presença no app: devolve o valor de ``confirmada_em``. Recusa CANCELADA e aula passada."""
    if status == STATUS_CANCELADA:
        raise AcaoInvalida("Aula cancelada")
    if data_aula < hoje:
        raise AcaoInvalida("Aula ja passou")
    return agora


def aviso_minimo_cumprido(
    inicio_aula: datetime,
    agora: datetime,
    horas_minimas: int = HORAS_AVISO_CONTRATO,
    *,
    ativo: bool = False,
) -> bool:
    """Regra OPCIONAL das 6 horas de aviso (cláusula 5 do contrato). DESLIGADA por padrão.

    # COMPORTAMENTO ANTIGO: o sistema nunca validou o prazo; ``ativo=False`` devolve sempre ``True``.
    Ligada, devolve ``True`` se faltam pelo menos ``horas_minimas`` horas para ``inicio_aula``.
    Os dois datetimes precisam ter o mesmo "tipo" (ambos com fuso ou ambos sem).
    """
    if not ativo:
        return True
    return inicio_aula - agora >= timedelta(hours=horas_minimas)


def acoes_permitidas_status(acao: str, *, eh_professor: bool) -> str:
    """Status resultante das ações de ``aula_status_api`` (exceto ``desmarcar``).

    chegou/iniciar -> RESERVADA, finalizar -> CONCLUIDA, faltou -> FALTOU_SEM_AVISAR, remarcar -> CANCELADA
    (professor não remarca). Ação desconhecida levanta ``AcaoInvalida("Acao invalida.")``.
    """
    mapa = {
        "chegou": "RESERVADA",
        "iniciar": "RESERVADA",
        "finalizar": "CONCLUIDA",
        "faltou": "FALTOU_SEM_AVISAR",
        "remarcar": "CANCELADA",
    }
    if acao not in mapa:
        raise AcaoInvalida("Acao invalida.")
    if acao == "remarcar" and eh_professor:
        raise SemPermissao("Sem permissao para remarcar.")
    return mapa[acao]
