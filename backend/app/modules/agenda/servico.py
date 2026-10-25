"""Serviço da agenda: sessões de aula, reservas e agenda do contrato.

CONTRATO para os outros módulos (assinaturas estáveis e testadas em ``tests/agenda``):

- ``obter_ou_criar_sessao(db, *, unidade_id, tipo_servico_id, profissional_id, data, hora_inicio, hora_fim=None, capacidade=None)``
- ``criar_reserva(db, aluno_id, sessao_id, *, status=..., contrato_id=None, ...)``
- ``gerar_agenda_do_contrato(db, *, aluno_id, contrato_id, unidade_id, tipo_servico_id, data_inicio, data_fim, selecoes, ...)``
- ``confirmar_reserva`` / ``desmarcar_reserva_do_aluno`` (usadas pelo app do aluno, R15)

Regras:
- NADA aqui faz ``commit``: quem chama (a rota, o job, outro módulo) controla a transação. Em erro, quem chama faz
  ``rollback`` e nada fica gravado. Os pedaços que podem falhar sozinhos (uma data da agenda, uma aula do pacote) usam
  SAVEPOINT, então um conflito não derruba o resto.
- Capacidade (R3): a garantia é transacional, pelo ``UPDATE`` condicional de ``ocupar_vaga`` (contador
  ``aula_sessao.reservas_ativas``). Toda mudança de status de/para RESERVADA passa por ``_trocar_status``.
- Nunca cria sessão em consulta (GET): a geração é pedida explicitamente (``gerar_sessoes``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import agora as agora_utc
from app.domain import agenda as dom_agenda
from app.domain import capacidade as cap
from app.domain import reposicao as repos
from app.domain import status_aula
from app.domain.financeiro import hoje_de_negocio
from app.modules.agenda.models import (
    AulaSessao,
    Reserva,
    StatusReserva,
    liberar_vaga,
    ocupar_vaga,
)
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import (
    BloqueioAgenda,
    HorarioFuncionamento,
    Profissional,
    TipoServico,
    Unidade,
)

log = logging.getLogger(__name__)

#: máximo de dias que ``gerar_sessoes`` aceita de uma vez
MAX_DIAS_GERACAO = 92


# ----------------------------------------------------------------------------------------------------------- erros
class ErroAgenda(Exception):
    """Erro de regra com mensagem pronta para o usuário. ``status`` é o código HTTP sugerido."""

    status = 400

    def __init__(self, mensagem: str, *, dados: dict | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.dados = dados or {}


class NaoEncontrado(ErroAgenda):
    status = 404


class SemPermissao(ErroAgenda):
    status = 403


class Conflito(ErroAgenda):
    status = 409


class Invalido(ErroAgenda):
    status = 422


# ------------------------------------------------------------------------------------------------------- utilidades
def _agora(agora: datetime | None) -> datetime:
    return agora or agora_utc()


def _garantir_transacao(db: Session) -> None:
    """SQLite (dev/testes) só abre a transação no primeiro INSERT/UPDATE/DELETE; um SAVEPOINT antes disso viraria a
    transação externa e o RELEASE gravaria tudo. Um UPDATE que não acha linha força o BEGIN. No PostgreSQL não faz nada."""
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(AulaSessao.__table__).where(AulaSessao.__table__.c.id == -1).values(reservas_ativas=0))


@contextmanager
def savepoint(db: Session) -> Iterator[None]:
    """Bloco que desfaz só a si mesmo em caso de exceção (a transação externa continua)."""
    db.flush()
    _garantir_transacao(db)
    with db.begin_nested():
        yield


def _somar_minutos(dia: date, inicio: time, minutos: int) -> time:
    fim = datetime.combine(dia, inicio) + timedelta(minutes=minutos)
    if fim.date() != dia:
        raise Invalido("A aula não pode terminar depois da meia-noite.")
    return fim.time()


def _unidade(db: Session, unidade_id: int) -> Unidade:
    u = db.get(Unidade, unidade_id)
    if u is None:
        raise Invalido("Unidade inválida.")
    return u


def _sessao(db: Session, sessao_id: int) -> AulaSessao:
    s = db.get(AulaSessao, sessao_id)
    if s is None:
        raise NaoEncontrado("Aula não encontrada.")
    return s


def _reserva(db: Session, reserva_id: int) -> Reserva:
    r = db.get(Reserva, reserva_id)
    if r is None:
        raise NaoEncontrado("Reserva não encontrada.")
    return r


def capacidade_da_sessao(db: Session, sessao: AulaSessao) -> int:
    """Capacidade efetiva (R3): a da sessão ou, se nula, a da unidade."""
    unidade = db.get(Unidade, sessao.unidade_id)
    return cap.capacidade_efetiva(sessao.capacidade, unidade.capacidade if unidade else 0)


def _ocupar_vaga_ou_erro(db: Session, sessao: AulaSessao, *, remarcando: bool = False) -> None:
    """Pega uma vaga de forma atômica ou levanta ``Conflito`` com "N de M vagas ocupadas" (texto do domínio)."""
    if ocupar_vaga(db, sessao.id):
        return
    db.refresh(sessao)
    capacidade = capacidade_da_sessao(db, sessao)
    montar = cap.mensagem_sem_vaga_remarcacao if remarcando else cap.mensagem_capacidade_excedida
    raise Conflito(
        montar(sessao.data, sessao.hora_inicio, sessao.reservas_ativas, capacidade),
        dados={"ocupadas": sessao.reservas_ativas, "capacidade": capacidade},
    )


def _trocar_status(db: Session, reserva: Reserva, novo: StatusReserva) -> None:
    """Única porta para mudar o status: sincroniza o contador de vagas (só RESERVADA ocupa)."""
    antigo = StatusReserva(reserva.status)
    novo = StatusReserva(novo)
    if antigo == novo:
        return
    if novo.value in cap.STATUS_OCUPAM_VAGA and antigo.value not in cap.STATUS_OCUPAM_VAGA:
        _ocupar_vaga_ou_erro(db, _sessao(db, reserva.aula_sessao_id))
    elif antigo.value in cap.STATUS_OCUPAM_VAGA and novo.value not in cap.STATUS_OCUPAM_VAGA:
        liberar_vaga(db, reserva.aula_sessao_id)
    reserva.status = novo


# ------------------------------------------------------------------------------------------------------- sessões
def _buscar_sessao(
    db: Session, unidade_id: int, tipo_servico_id: int, profissional_id: int | None, data: date, hora_inicio: time
) -> AulaSessao | None:
    return db.scalars(
        select(AulaSessao).where(
            AulaSessao.unidade_id == unidade_id,
            AulaSessao.tipo_servico_id == tipo_servico_id,
            func.coalesce(AulaSessao.profissional_id, 0) == (profissional_id or 0),
            AulaSessao.data == data,
            AulaSessao.hora_inicio == hora_inicio,
        )
    ).first()


def _validar_sessao_refs(db: Session, unidade_id: int, tipo_servico_id: int, profissional_id: int | None) -> Unidade:
    unidade = _unidade(db, unidade_id)
    if db.get(TipoServico, tipo_servico_id) is None:
        raise Invalido("Tipo de serviço inválido.")
    if profissional_id is not None and db.get(Profissional, profissional_id) is None:
        raise Invalido("Profissional inválido.")
    return unidade


def obter_ou_criar_sessao(
    db: Session,
    *,
    unidade_id: int,
    tipo_servico_id: int,
    profissional_id: int | None,
    data: date,
    hora_inicio: time,
    hora_fim: time | None = None,
    capacidade: int | None = None,
) -> tuple[AulaSessao, bool]:
    """Acha a aula do (unidade, serviço, profissional, data, início) ou cria. Devolve ``(sessao, criada)``.

    A chave é a do índice único do banco (``hora_fim`` não entra): se já existe, devolve a existente SEM mexer em
    profissional, fim nem capacidade (não sobrescreve nada de quem já está na aula). Sem ``hora_fim``, usa a duração
    da unidade. Seguro contra corrida: se outra transação cria a mesma aula no meio, devolve a dela.
    """
    existente = _buscar_sessao(db, unidade_id, tipo_servico_id, profissional_id, data, hora_inicio)
    if existente:
        return existente, False
    unidade = _validar_sessao_refs(db, unidade_id, tipo_servico_id, profissional_id)
    if hora_fim is None:
        hora_fim = _somar_minutos(data, hora_inicio, dom_agenda.duracao_da_unidade(unidade.duracao_aula_minutos))
    if hora_fim <= hora_inicio:
        raise Invalido("A hora final precisa ser depois da inicial.")
    if capacidade is not None and capacidade < 0:
        raise Invalido("A capacidade não pode ser negativa.")
    try:
        with savepoint(db):
            sessao = AulaSessao(
                unidade_id=unidade_id,
                tipo_servico_id=tipo_servico_id,
                profissional_id=profissional_id,
                data=data,
                hora_inicio=hora_inicio,
                hora_fim=hora_fim,
                capacidade=capacidade,
                reservas_ativas=0,
            )
            db.add(sessao)
            db.flush()
    except IntegrityError:
        existente = _buscar_sessao(db, unidade_id, tipo_servico_id, profissional_id, data, hora_inicio)
        if existente is None:
            raise
        return existente, False
    return sessao, True


def criar_sessao(
    db: Session,
    *,
    unidade_id: int,
    tipo_servico_id: int,
    profissional_id: int | None,
    data: date,
    hora_inicio: time,
    hora_fim: time | None = None,
    capacidade: int | None = None,
) -> AulaSessao:
    """Criação explícita (tela "Nova aula"): se já existe aula igual, avisa em vez de reaproveitar."""
    sessao, criada = obter_ou_criar_sessao(
        db,
        unidade_id=unidade_id,
        tipo_servico_id=tipo_servico_id,
        profissional_id=profissional_id,
        data=data,
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
        capacidade=capacidade,
    )
    if not criada:
        raise Conflito("Já existe uma aula com este serviço, profissional, data e horário.")
    return sessao


def editar_sessao(db: Session, sessao_id: int, campos: dict) -> AulaSessao:
    """Altera serviço, profissional, data, horário e/ou capacidade (``capacidade=None`` volta a herdar da unidade).

    ``campos`` só leva as chaves a alterar. Recusa capacidade menor que as reservas ativas.
    """
    sessao = _sessao(db, sessao_id)
    for chave in ("unidade_id", "tipo_servico_id", "profissional_id", "data", "hora_inicio", "hora_fim", "capacidade"):
        if chave in campos:
            setattr(sessao, chave, campos[chave])
    _validar_sessao_refs(db, sessao.unidade_id, sessao.tipo_servico_id, sessao.profissional_id)
    if sessao.hora_fim <= sessao.hora_inicio:
        raise Invalido("A hora final precisa ser depois da inicial.")
    db.flush()
    db.refresh(sessao)
    capacidade = capacidade_da_sessao(db, sessao)
    if capacidade < sessao.reservas_ativas:
        raise Conflito(
            f"A aula já tem {sessao.reservas_ativas} reserva(s) ativa(s); a capacidade não pode ser {capacidade}."
        )
    return sessao


def editar_sessao_segura(db: Session, sessao_id: int, campos: dict) -> AulaSessao:
    """``editar_sessao`` que traduz violação do índice único em ``Conflito`` (a transação é desfeita pela rota)."""
    try:
        with savepoint(db):
            return editar_sessao(db, sessao_id, campos)
    except IntegrityError as exc:
        raise Conflito("Já existe uma aula com este serviço, profissional, data e horário.") from exc


def excluir_sessao(db: Session, sessao_id: int) -> None:
    sessao = _sessao(db, sessao_id)
    total = db.scalar(select(func.count()).select_from(Reserva).where(Reserva.aula_sessao_id == sessao.id)) or 0
    if total:
        raise Conflito(
            f"A aula tem {total} reserva(s). Remarque ou exclua as reservas antes de excluir a aula.",
            dados={"reservas": total},
        )
    db.delete(sessao)
    db.flush()


def apagar_sessao_se_vazia(db: Session, sessao_id: int) -> bool:
    """Apaga a aula só se ficou sem nenhuma reserva (qualquer status) — única ligação que ela tem no modelo."""
    db.flush()
    if db.scalar(select(func.count()).select_from(Reserva).where(Reserva.aula_sessao_id == sessao_id)):
        return False
    sessao = db.get(AulaSessao, sessao_id)
    if sessao is None:
        return False
    db.delete(sessao)
    db.flush()
    return True


# ------------------------------------------------------------------------------------------- janelas e bloqueios
def carregar_janelas(db: Session, unidade_id: int) -> list[dom_agenda.Janela]:
    horarios = db.scalars(
        select(HorarioFuncionamento).where(HorarioFuncionamento.unidade_id == unidade_id, HorarioFuncionamento.ativo)
    ).all()
    return [
        dom_agenda.Janela(
            dia_semana=h.dia_semana,
            hora_inicio=h.hora_inicio,
            hora_fim=h.hora_fim,
            ativo=h.ativo,
            servicos=frozenset(t.id for t in h.tipos_servico),
        )
        for h in horarios
    ]


def carregar_bloqueios(db: Session, unidade_id: int) -> list[dom_agenda.Bloqueio]:
    return [
        dom_agenda.Bloqueio(
            hora_inicio=b.hora_inicio,
            hora_fim=b.hora_fim,
            data_inicio=b.data_inicio,
            data_fim=b.data_fim,
            recorrente=b.recorrente,
            dia_semana=b.dia_semana,
            ativo=b.ativo,
            tipo_servico_id=b.tipo_servico_id,
            profissional_id=b.profissional_id,
        )
        for b in db.scalars(
            select(BloqueioAgenda).where(BloqueioAgenda.unidade_id == unidade_id, BloqueioAgenda.ativo)
        )
    ]


def gerar_sessoes(
    db: Session,
    *,
    unidade_id: int,
    tipo_servico_id: int,
    profissional_id: int | None,
    data_inicio: date,
    data_fim: date,
    capacidade: int | None = None,
) -> dict:
    """Cria, por pedido EXPLÍCITO, as aulas vazias do período a partir dos horários de funcionamento da unidade
    (janelas do serviço, slots de duração+10 min), pulando horários bloqueados e os que já existem.

    No antigo isso acontecia dentro de GETs; aqui só roda quando alguém pede (POST). Idempotente.
    """
    if data_fim < data_inicio:
        raise Invalido("A data final precisa ser depois da inicial.")
    if (data_fim - data_inicio).days + 1 > MAX_DIAS_GERACAO:
        raise Invalido(f"Gere no máximo {MAX_DIAS_GERACAO} dias de uma vez.")
    unidade = _validar_sessao_refs(db, unidade_id, tipo_servico_id, profissional_id)
    duracao = dom_agenda.duracao_da_unidade(unidade.duracao_aula_minutos)
    janelas = dom_agenda.janelas_por_dia(carregar_janelas(db, unidade_id), tipo_servico_id)
    bloqueios = dom_agenda.bloqueios_aplicaveis(
        carregar_bloqueios(db, unidade_id), tipo_servico_id, profissional_id, data_inicio, data_fim
    )
    criadas: list[int] = []
    existentes = bloqueadas = 0
    dia = data_inicio
    while dia <= data_fim:
        for inicio, fim in dom_agenda.gerar_slots_do_dia(dia, janelas.get(dia.weekday(), ()), duracao):
            if dom_agenda.slot_bloqueado(bloqueios, dia, inicio, fim):
                bloqueadas += 1
                continue
            sessao, criada = obter_ou_criar_sessao(
                db,
                unidade_id=unidade_id,
                tipo_servico_id=tipo_servico_id,
                profissional_id=profissional_id,
                data=dia,
                hora_inicio=inicio,
                hora_fim=fim,
                capacidade=capacidade,
            )
            if criada:
                criadas.append(sessao.id)
            else:
                existentes += 1
        dia += timedelta(days=1)
    return {"criadas": len(criadas), "ids": criadas, "ja_existiam": existentes, "bloqueadas": bloqueadas}


# ------------------------------------------------------------------------------------------------------- reservas
def criar_reserva(
    db: Session,
    aluno_id: int,
    sessao_id: int,
    *,
    status: StatusReserva | str = StatusReserva.RESERVADA,
    contrato_id: int | None = None,
    aula_avulsa_id: int | None = None,
    aula_avaliativa_id: int | None = None,
    confirmada_em: datetime | None = None,
) -> Reserva:
    """Reserva o aluno na aula. Atômico: pega a vaga (``ocupar_vaga``) e grava a reserva na mesma transação; se
    qualquer passo falhar, a vaga não fica ocupada. Erros: ``NaoEncontrado`` (aluno/aula), ``Conflito`` (aluno já está
    na aula; aula lotada, com "N de M vagas ocupadas")."""
    status = StatusReserva(status)
    if db.get(Aluno, aluno_id) is None:
        raise NaoEncontrado("Aluno não encontrado.")
    sessao = _sessao(db, sessao_id)
    if db.scalar(select(Reserva.id).where(Reserva.aluno_id == aluno_id, Reserva.aula_sessao_id == sessao_id)):
        raise Conflito("O aluno já tem reserva nesta aula.")
    try:
        with savepoint(db):
            if status.value in cap.STATUS_OCUPAM_VAGA:
                _ocupar_vaga_ou_erro(db, sessao)
            reserva = Reserva(
                aluno_id=aluno_id,
                aula_sessao_id=sessao_id,
                contrato_id=contrato_id,
                aula_avulsa_id=aula_avulsa_id,
                aula_avaliativa_id=aula_avaliativa_id,
                status=status,
                confirmada_em=confirmada_em,
            )
            db.add(reserva)
            db.flush()
    except IntegrityError as exc:
        raise Conflito("O aluno já tem reserva nesta aula.") from exc
    return reserva


def inicio_da_sessao(sessao: AulaSessao) -> datetime:
    return status_aula.momento_da_sessao(sessao.data, sessao.hora_inicio)


def limite_para_desmarcar(sessao: AulaSessao) -> datetime:
    """Último instante em que dá para desmarcar: ``HORAS_AVISO_CONTRATO`` horas antes do início da aula (fuso de Brasília)."""
    return status_aula.para_fuso_negocio(inicio_da_sessao(sessao) - timedelta(hours=repos.HORAS_AVISO_CONTRATO))


def prazo_de_desmarcar_cumprido(sessao: AulaSessao, momento: datetime) -> bool:
    """Regra das 6 horas LIGADA (decisão do Jefferson, 25/10/2026): vale ``antecedência >= 6 h`` (limite exato passa)."""
    return repos.aviso_minimo_cumprido(inicio_da_sessao(sessao), momento, ativo=True)


def mensagem_prazo_desmarcar(sessao: AulaSessao) -> str:
    lim = limite_para_desmarcar(sessao)
    return (
        f"Só é possível desmarcar com pelo menos {repos.HORAS_AVISO_CONTRATO} horas de antecedência "
        f"(o prazo desta aula terminou em {lim:%d/%m/%Y} às {lim:%H:%M}). Fale com a recepção."
    )


def desmarcar_reserva(
    db: Session,
    reserva_id: int,
    *,
    agora: datetime | None = None,
    eh_professor: bool = False,
    excecao_prazo: bool = False,
    motivo: str | None = None,
) -> Reserva:
    """Desmarcar com reposição (R4): CANCELADA, ``confirmada_em=None``, ``desmarcada_em=agora`` e
    ``reposicao_ate = data da aula + 30 dias``. Professor não desmarca. Libera a vaga se a reserva ocupava uma.

    Regra das 6 horas: só com 6 h ou mais de antecedência (``Conflito`` 409 com o horário limite). ``excecao_prazo=True``
    (quem chama garante que é o perfil Full) dispensa o prazo e EXIGE ``motivo`` (``Invalido`` 422 sem ele); o motivo fica em
    ``reserva.motivo_excecao_prazo``."""
    reserva = _reserva(db, reserva_id)
    sessao = _sessao(db, reserva.aula_sessao_id)
    if StatusReserva(reserva.status) == StatusReserva.CANCELADA:
        # COMPORTAMENTO ANTIGO (não replicado): a equipe podia "desmarcar" uma aula já desmarcada e o sistema
        # reescrevia desmarcada_em/reposicao_ate, estendendo a reposição. Aqui recusamos.
        raise Conflito("Esta aula já está desmarcada.")
    momento = _agora(agora)
    fora_do_prazo = not prazo_de_desmarcar_cumprido(sessao, momento)
    motivo_limpo = (motivo or "").strip()
    if fora_do_prazo and not eh_professor:
        if not excecao_prazo:
            raise Conflito(mensagem_prazo_desmarcar(sessao), dados={"prazo_6h": True})
        if len(motivo_limpo) < 3:
            raise Invalido("Informe o motivo da exceção ao prazo de desmarcar.")
    try:
        r = repos.desmarcar(sessao.data, momento, eh_professor=eh_professor)
    except repos.SemPermissao as exc:
        raise SemPermissao(str(exc)) from exc
    _trocar_status(db, reserva, StatusReserva.CANCELADA)
    reserva.confirmada_em = r.confirmada_em
    reserva.desmarcada_em = r.desmarcada_em
    reserva.reposicao_ate = r.reposicao_ate
    reserva.motivo_excecao_prazo = motivo_limpo[:300] if (fora_do_prazo and excecao_prazo) else None
    db.flush()
    return reserva


def desmarcar_reserva_do_aluno(db: Session, aluno_id: int, reserva_id: int, *, agora: datetime | None = None) -> Reserva:
    """Desmarcar pelo app do aluno (R15/R4): só a própria reserva, recusa aula já desmarcada, aula que já passou e
    desmarcação com menos de 6 horas de antecedência (sem exceção para o aluno)."""
    reserva = _reserva(db, reserva_id)
    if reserva.aluno_id != aluno_id:
        raise NaoEncontrado("Reserva não encontrada.")
    sessao = _sessao(db, reserva.aula_sessao_id)
    momento = _agora(agora)
    try:
        r = repos.desmarcar_pelo_aluno(StatusReserva(reserva.status).value, sessao.data, hoje_de_negocio(momento), momento)
    except repos.AcaoInvalida as exc:
        raise Conflito(str(exc)) from exc
    if not prazo_de_desmarcar_cumprido(sessao, momento):
        raise Conflito(mensagem_prazo_desmarcar(sessao), dados={"prazo_6h": True})
    _trocar_status(db, reserva, StatusReserva.CANCELADA)
    reserva.confirmada_em = r.confirmada_em
    reserva.desmarcada_em = r.desmarcada_em
    reserva.reposicao_ate = r.reposicao_ate
    reserva.motivo_excecao_prazo = None
    db.flush()
    return reserva


def confirmar_reserva(db: Session, reserva_id: int, *, aluno_id: int | None = None, agora: datetime | None = None) -> Reserva:
    """Grava ``confirmada_em`` (R15). Com ``aluno_id`` (app do aluno) confere que a reserva é dele. Recusa aula
    cancelada ou que já passou (regra do domínio)."""
    reserva = _reserva(db, reserva_id)
    if aluno_id is not None and reserva.aluno_id != aluno_id:
        raise NaoEncontrado("Reserva não encontrada.")
    sessao = _sessao(db, reserva.aula_sessao_id)
    momento = _agora(agora)
    try:
        reserva.confirmada_em = repos.confirmar_pelo_aluno(
            StatusReserva(reserva.status).value, sessao.data, hoje_de_negocio(momento), momento
        )
    except repos.AcaoInvalida as exc:
        raise Conflito(str(exc)) from exc
    db.flush()
    return reserva


ACOES_PRESENCA = {
    "chegou": StatusReserva.RESERVADA,
    "iniciar": StatusReserva.RESERVADA,
    "finalizar": StatusReserva.CONCLUIDA,
    "faltou": StatusReserva.FALTOU_SEM_AVISAR,
    "faltou_avisou": StatusReserva.FALTOU_AVISOU,
}


def aplicar_acao_presenca(db: Session, reserva_id: int, acao: str, *, agora: datetime | None = None) -> Reserva:
    """chegou/iniciar -> RESERVADA, finalizar -> CONCLUIDA, faltou -> FALTOU_SEM_AVISAR, faltou_avisou ->
    FALTOU_AVISOU. Mudar para RESERVADA pode falhar por lotação (``Conflito``).

    # COMPORTAMENTO ANTIGO: "chegou" só gravava RESERVADA (não anotava a chegada; "em aula" é derivado do horário).
    Mantido; a única adição é gravar ``confirmada_em`` quando vazio (chegar prova a presença).
    """
    acao = (acao or "").strip().lower()
    if acao not in ACOES_PRESENCA:
        raise Invalido("Ação inválida.")
    reserva = _reserva(db, reserva_id)
    _trocar_status(db, reserva, ACOES_PRESENCA[acao])
    if acao in ("chegou", "iniciar") and reserva.confirmada_em is None:
        reserva.confirmada_em = _agora(agora)
    db.flush()
    return reserva


def remarcar_reserva(
    db: Session,
    reserva_id: int,
    *,
    data: date,
    hora_inicio: time,
    profissional_id: int | None = None,
    ignorar_prazo_reposicao: bool = False,
    agora: datetime | None = None,
) -> Reserva:
    """Remarcar (R3): leva a reserva para outra data/hora (e profissional), mantendo unidade, serviço e duração.

    - a aula nova é achada ou criada; a capacidade é conferida de forma atômica (capacidade 0 também recusa;
      # COMPORTAMENTO ANTIGO: no sistema antigo a remarcação com capacidade 0 passava);
    - a reserva volta a RESERVADA e a vaga antiga é liberada; a aula antiga é apagada se ficar vazia;
    - reposição (novo): uma reserva desmarcada (CANCELADA) só pode ser remarcada até ``reposicao_ate``, a menos que
      ``ignorar_prazo_reposicao``; ao remarcar, a reposição é consumida (``reposicao_ate`` zera);
    - a confirmação do aluno (``confirmada_em``) é zerada, pois vale para o horário antigo.
    """
    reserva = _reserva(db, reserva_id)
    antiga = _sessao(db, reserva.aula_sessao_id)
    status_antigo = StatusReserva(reserva.status)
    if profissional_id is not None and db.get(Profissional, profissional_id) is None:
        raise Invalido("Profissional inválido.")
    novo_prof = antiga.profissional_id if profissional_id is None else profissional_id
    if (
        status_antigo == StatusReserva.CANCELADA
        and reserva.reposicao_ate
        and data > reserva.reposicao_ate
        and not ignorar_prazo_reposicao
    ):
        raise Conflito(
            f"A reposição desta aula vale até {reserva.reposicao_ate:%d/%m/%Y}. Escolha uma data até lá.",
            dados={"reposicao_ate": reserva.reposicao_ate.isoformat()},
        )
    unidade = _unidade(db, antiga.unidade_id)
    duracao = int((datetime.combine(date.min, antiga.hora_fim) - datetime.combine(date.min, antiga.hora_inicio)).total_seconds() // 60)
    duracao = duracao if duracao > 0 else dom_agenda.duracao_da_unidade(unidade.duracao_aula_minutos)
    nova, _ = obter_ou_criar_sessao(
        db,
        unidade_id=antiga.unidade_id,
        tipo_servico_id=antiga.tipo_servico_id,
        profissional_id=novo_prof,
        data=data,
        hora_inicio=hora_inicio,
        hora_fim=_somar_minutos(data, hora_inicio, duracao),
        capacidade=antiga.capacidade,
    )
    if nova.id == antiga.id:
        raise Conflito("A aula já está neste horário.")
    if db.scalar(select(Reserva.id).where(Reserva.aluno_id == reserva.aluno_id, Reserva.aula_sessao_id == nova.id)):
        raise Conflito("O aluno já tem reserva nesse horário.")
    _ocupar_vaga_ou_erro(db, nova, remarcando=True)
    if status_antigo == StatusReserva.RESERVADA:
        liberar_vaga(db, antiga.id)
    reserva.aula_sessao_id = nova.id
    reserva.status = StatusReserva.RESERVADA
    reserva.confirmada_em = None
    if status_antigo == StatusReserva.CANCELADA:
        reserva.reposicao_ate = None
    db.flush()
    apagar_sessao_se_vazia(db, antiga.id)
    return reserva


def excluir_reserva(db: Session, reserva_id: int) -> dict:
    """Exclui a reserva: libera a vaga, cancela cobranças ABERTAS ligadas a ela e apaga a aula se ficar vazia.

    Recusa (``Conflito``) quando há evolução, avaliação ou cobrança PAGA ligadas à reserva: isso é histórico clínico
    e financeiro (# COMPORTAMENTO ANTIGO: o antigo apagava tudo em cascata, inclusive evoluções; ver R13).
    """
    from app.modules.agenda.models import Avaliacao, Evolucao
    from app.modules.financeiro.models import ContaReceber, StatusReceber

    reserva = _reserva(db, reserva_id)
    if db.scalar(select(func.count()).select_from(Evolucao).where(Evolucao.reserva_id == reserva.id)) or db.scalar(
        select(func.count()).select_from(Avaliacao).where(Avaliacao.reserva_id == reserva.id)
    ):
        raise Conflito("Esta aula tem evolução ou avaliação registrada e não pode ser excluída. Desmarque a aula em vez disso.")
    contas = db.scalars(select(ContaReceber).where(ContaReceber.reserva_id == reserva.id)).all()
    if any(StatusReceber(c.status) == StatusReceber.PAGO for c in contas):
        raise Conflito("Esta aula tem cobrança já paga e não pode ser excluída. Desmarque a aula em vez disso.")
    for conta in contas:
        if StatusReceber(conta.status) == StatusReceber.ABERTO:
            conta.status = StatusReceber.CANCELADO
        conta.reserva_id = None
    sessao_id = reserva.aula_sessao_id
    if StatusReserva(reserva.status).value in cap.STATUS_OCUPAM_VAGA:
        liberar_vaga(db, sessao_id)
    db.flush()
    db.delete(reserva)
    db.flush()
    sessao_apagada = apagar_sessao_se_vazia(db, sessao_id)
    return {"sessao_id": sessao_id, "sessao_apagada": sessao_apagada, "contas_canceladas": len(contas)}


# ------------------------------------------------------------------------------------------------- agenda do contrato
@dataclass
class ResultadoAgenda:
    """Retorno de ``gerar_agenda_do_contrato`` e do pacote avulso."""

    reservas_criadas: list[int] = field(default_factory=list)
    sessoes_criadas: int = 0
    ja_existentes: int = 0
    conflitos: list[str] = field(default_factory=list)

    @property
    def mensagem_conflitos(self) -> str | None:
        return dom_agenda.mensagem_conflitos(self.conflitos) if self.conflitos else None


def _profissionais_ativos_ids(db: Session) -> list[int]:
    return list(db.scalars(select(Profissional.id).where(Profissional.ativo).order_by(Profissional.id)))


def calcular_slots(
    db: Session,
    *,
    unidade_id: int,
    tipo_servico_id: int,
    inicio: date,
    fim: date,
    profissionais_ids: Sequence[int] | None = None,
) -> dict[tuple[int, time, time], list[int]]:
    """Slots oferecidos para agendar do ``inicio`` ao ``fim``: ``(dia_semana, início, fim) -> profissionais``.

    Usa os horários de funcionamento do serviço, menos bloqueios e lotação (``slots_permitidos_do_contrato``). Sem
    nenhum horário de funcionamento configurado, cai para as aulas já existentes no período com vaga (plano B do antigo).
    Só LÊ: nunca cria aula.
    """
    unidade = _unidade(db, unidade_id)
    duracao = dom_agenda.duracao_da_unidade(unidade.duracao_aula_minutos)
    janelas_unidade = carregar_janelas(db, unidade_id)
    janelas = dom_agenda.janelas_por_dia(janelas_unidade, tipo_servico_id)
    datas = dom_agenda.datas_por_dia_da_semana(inicio, fim)
    profs = list(profissionais_ids) if profissionais_ids is not None else _profissionais_ativos_ids(db)
    bloqueios_todos = carregar_bloqueios(db, unidade_id)
    bloqueios = {
        p: dom_agenda.bloqueios_aplicaveis(bloqueios_todos, None, p, inicio, fim) for p in profs
    }
    sessoes = db.scalars(
        select(AulaSessao).where(
            AulaSessao.unidade_id == unidade_id,
            AulaSessao.tipo_servico_id == tipo_servico_id,
            AulaSessao.data.between(inicio, fim),
        ).execution_options(populate_existing=True)  # reservas_ativas é mexido por UPDATE direto: nunca ler do cache da sessão
    ).all()
    por_prof: dict[int, dict[dom_agenda.ChaveSessao, dom_agenda.SessaoExistente]] = {}
    for s in sessoes:
        if s.profissional_id is None:
            continue
        por_prof.setdefault(s.profissional_id, {})[(s.data, s.hora_inicio, s.hora_fim)] = dom_agenda.SessaoExistente(
            ocupadas=s.reservas_ativas, capacidade=s.capacidade
        )
    slots = dom_agenda.slots_permitidos_do_contrato(
        janelas, datas, duracao, profs, bloqueios, por_prof, unidade.capacidade
    )
    if not slots and not janelas_unidade:
        todas = db.scalars(
            select(AulaSessao).where(AulaSessao.unidade_id == unidade_id, AulaSessao.data.between(inicio, fim)).execution_options(populate_existing=True)
        ).all()
        slots = dom_agenda.slots_por_sessoes_existentes(
            (s.data, s.hora_inicio, s.hora_fim, s.reservas_ativas, capacidade_da_sessao(db, s)) for s in todas
        )
    return slots


def _reservar_datas(
    db: Session,
    resultado: ResultadoAgenda,
    *,
    aluno_id: int,
    unidade_id: int,
    tipo_servico_id: int,
    profissional_id: int,
    datas: Sequence[date],
    inicio: time,
    fim: time,
    bloqueios: Sequence[dom_agenda.Bloqueio],
    contrato_id: int | None = None,
    aula_avulsa_id: int | None = None,
    ao_criar=None,
) -> None:
    """Para cada data: pula bloqueio, é idempotente (aluno já na aula), cria a aula e a reserva em SAVEPOINT (falha de
    vaga vira conflito e não desfaz as demais). ``ao_criar(reserva, data)`` roda dentro do mesmo SAVEPOINT."""
    for dia in datas:
        rotulo = f"{dia} {inicio:%H:%M}"
        if dom_agenda.slot_bloqueado(bloqueios, dia, inicio, fim):
            resultado.conflitos.append(f"Bloqueio em {rotulo}")
            continue
        try:
            with savepoint(db):
                sessao, criada = obter_ou_criar_sessao(
                    db,
                    unidade_id=unidade_id,
                    tipo_servico_id=tipo_servico_id,
                    profissional_id=profissional_id,
                    data=dia,
                    hora_inicio=inicio,
                    hora_fim=fim,
                )
                if db.scalar(select(Reserva.id).where(Reserva.aluno_id == aluno_id, Reserva.aula_sessao_id == sessao.id)):
                    resultado.ja_existentes += 1
                    continue
                reserva = criar_reserva(
                    db, aluno_id, sessao.id, contrato_id=contrato_id, aula_avulsa_id=aula_avulsa_id
                )
                if ao_criar:
                    ao_criar(reserva, dia)
        except Conflito:
            resultado.conflitos.append(f"Sem vaga em {rotulo}")
            continue
        resultado.reservas_criadas.append(reserva.id)
        if criada:
            resultado.sessoes_criadas += 1


def gerar_agenda_do_contrato(
    db: Session,
    *,
    aluno_id: int,
    contrato_id: int | None,
    unidade_id: int,
    tipo_servico_id: int,
    data_inicio: date,
    data_fim: date,
    selecoes: Sequence[dom_agenda.SelecaoHorario],
    aulas_por_semana: int,
    recorrencia_contrato: str = "MENSAL",
) -> ResultadoAgenda:
    """Cria as reservas do contrato: um horário por dia da semana, de ``data_inicio`` a ``data_fim``.

    - A escolha é VALIDADA ANTES de gravar qualquer coisa (``ErroAgenda`` 422): quantidade de horários, repetição, dia,
      professor em todos e conferência com os slots oferecidos. Se a validação recusa, nada é criado (o antigo criava
      as reservas do 1º horário antes de recusar o 2º).
    - Só o SERVIÇO do plano (``tipo_servico_id``) ganha reserva.
    - Aula já existente é reaproveitada SEM trocar o profissional dela (não sobrescreve nada).
    - Bloqueio e falta de vaga viram ``conflitos`` informativos e NÃO desfazem as demais datas
      (# COMPORTAMENTO ANTIGO: sucesso parcial). Reexecutar é idempotente.
    - Contrato SEMANAL agenda no máximo 4 semanas e 1 aula por semana.
    - Sem commit: a transação é de quem chama.
    """
    fim_agenda = dom_agenda.fim_da_agenda_do_contrato(recorrencia_contrato, data_inicio, data_fim)
    por_semana = 1 if recorrencia_contrato == "SEMANAL" else (aulas_por_semana or 1)
    erro = dom_agenda.validar_selecao(selecoes, por_semana)
    if erro:
        raise Invalido(erro)
    slots = calcular_slots(
        db, unidade_id=unidade_id, tipo_servico_id=tipo_servico_id, inicio=data_inicio, fim=fim_agenda
    )
    erro = dom_agenda.validar_selecao_nos_slots(selecoes, slots)
    if erro:
        raise Invalido(erro)
    for s in selecoes:
        if s.profissional_id and db.get(Profissional, s.profissional_id) is None:
            raise Invalido("Profissional inválido.")
    if db.get(Aluno, aluno_id) is None:
        raise NaoEncontrado("Aluno não encontrado.")
    _unidade(db, unidade_id)
    bloqueios_todos = carregar_bloqueios(db, unidade_id)
    resultado = ResultadoAgenda()
    datas = dom_agenda.datas_por_dia_da_semana(data_inicio, fim_agenda)
    for s in selecoes:
        bloqueios = dom_agenda.bloqueios_aplicaveis(bloqueios_todos, None, s.profissional_id, data_inicio, fim_agenda)
        _reservar_datas(
            db,
            resultado,
            aluno_id=aluno_id,
            unidade_id=unidade_id,
            tipo_servico_id=tipo_servico_id,
            profissional_id=s.profissional_id,
            datas=datas[s.dia_semana],
            inicio=s.inicio,
            fim=s.fim,
            bloqueios=bloqueios,
            contrato_id=contrato_id,
        )
    return resultado


# ---------------------------------------------------------------------------------------------------- job R6
def concluir_aulas_passadas(db: Session, agora: datetime | None = None) -> int:
    """R6: RESERVADA/PENDENTE cuja aula já terminou viram CONCLUIDA (``domain.status_aula.reservas_a_concluir``).

    Idempotente (o que já está CONCLUIDA/faltou/cancelada não é tocado) e chamado SÓ pelo job — nenhuma tela dispara
    isso. As RESERVADA que concluem liberam a vaga. Devolve quantas reservas mudaram. Sem commit.
    """
    momento = _agora(agora)
    hoje = hoje_de_negocio(momento)
    candidatas = db.execute(
        select(Reserva, AulaSessao.data, AulaSessao.hora_fim)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .where(
            Reserva.status.in_([StatusReserva.RESERVADA, StatusReserva.PENDENTE]),
            AulaSessao.data <= hoje,
        )
    ).all()
    itens = [
        status_aula.ReservaSimples(id=r.id, status=StatusReserva(r.status).value, data=d, hora_fim=hf)
        for r, d, hf in candidatas
    ]
    por_id = {r.id: r for r, _, _ in candidatas}
    a_concluir = status_aula.reservas_a_concluir(momento, itens)
    for item in a_concluir:
        _trocar_status(db, por_id[item.id], StatusReserva.CONCLUIDA)
    db.flush()
    return len(a_concluir)
