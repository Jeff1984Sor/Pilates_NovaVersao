"""Agenda: sessões de aula, reservas, aulas avulsas/avaliativas, evoluções e log de avisos por WhatsApp.

Capacidade (decisão): cada `aula_sessao` mantém o contador `reservas_ativas` (reservas em RESERVADA).
`ocupar_vaga` faz um UPDATE condicional atômico (`reservas_ativas < capacidade efetiva`), então duas
transações simultâneas não estouram a lotação. Funciona igual em PostgreSQL e SQLite (que não tem
`SELECT ... FOR UPDATE`). Quem muda o status de uma reserva de/para RESERVADA chama `ocupar_vaga`/`liberar_vaga`.
"""

import enum
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import CodigoLegado, coluna_enum
from app.modules.cadastros.models import Recorrencia, Unidade


class StatusReserva(enum.StrEnum):
    RESERVADA = "RESERVADA"
    CONCLUIDA = "CONCLUIDA"
    FALTOU_AVISOU = "FALTOU_AVISOU"
    FALTOU_SEM_AVISAR = "FALTOU_SEM_AVISAR"
    CANCELADA = "CANCELADA"
    PENDENTE = "PENDENTE"


class TipoAvaliativa(enum.StrEnum):
    AVALIATIVA = "AVALIATIVA"
    TOTALPASS = "TOTALPASS"
    WELLHUB = "WELLHUB"


class StatusAvaliativa(enum.StrEnum):
    AGENDADA = "AGENDADA"
    REALIZADA = "REALIZADA"
    CANCELADA = "CANCELADA"
    CONVERTIDA = "CONVERTIDA"


class AulaSessao(Base, Timestamped, CodigoLegado):
    """Uma aula (horário + serviço + profissional). Única por (unidade, serviço, profissional, data, início)."""

    __tablename__ = "aula_sessao"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"))
    tipo_servico_id: Mapped[int] = mapped_column(ForeignKey("tipo_servico.id"))
    profissional_id: Mapped[int | None] = mapped_column(ForeignKey("profissional.id", ondelete="SET NULL"))
    data: Mapped[date] = mapped_column(Date)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    capacidade: Mapped[int | None] = mapped_column(Integer)  # nulo = herda da unidade
    reservas_ativas: Mapped[int] = mapped_column(Integer, default=0)  # reservas em RESERVADA (ver docstring do módulo)

    __table_args__ = (
        # profissional nulo (aula TotalPass) conta como "0" para a unicidade, senão o NULL escaparia da regra
        Index(
            "uq_aula_sessao_slot",
            "unidade_id",
            "tipo_servico_id",
            func.coalesce(profissional_id, 0),
            "data",
            "hora_inicio",
            unique=True,
        ),
        Index("ix_aula_sessao_data_unidade", "data", "unidade_id"),
        Index("ix_aula_sessao_profissional_data", "profissional_id", "data"),
        CheckConstraint("reservas_ativas >= 0", name="reservas_ativas_nao_negativo"),
        CheckConstraint("capacidade IS NULL OR capacidade >= 0", name="capacidade_nao_negativa"),
        CheckConstraint("hora_fim > hora_inicio", name="hora_fim_maior"),
    )


def ocupar_vaga(db: Session, aula_sessao_id: int) -> bool:
    """Reserva uma vaga de forma atômica. Devolve False se a aula estiver lotada (ou não existir)."""
    t = AulaSessao.__table__
    capacidade_unidade = select(Unidade.capacidade).where(Unidade.id == t.c.unidade_id).scalar_subquery()
    r = db.execute(
        update(t)
        .where(t.c.id == aula_sessao_id, t.c.reservas_ativas < func.coalesce(t.c.capacidade, capacidade_unidade))
        .values(reservas_ativas=t.c.reservas_ativas + 1)
    )
    return r.rowcount == 1


def liberar_vaga(db: Session, aula_sessao_id: int) -> None:
    t = AulaSessao.__table__
    db.execute(
        update(t)
        .where(t.c.id == aula_sessao_id, t.c.reservas_ativas > 0)
        .values(reservas_ativas=t.c.reservas_ativas - 1)
    )


class AulaAvulsa(Base, Timestamped, CodigoLegado):
    """Pacote de aulas avulsas (sem contrato)."""

    __tablename__ = "aula_avulsa"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id"), index=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("plano.id"))
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissional.id"))
    recorrencia: Mapped[Recorrencia] = mapped_column(coluna_enum(Recorrencia, 10), default=Recorrencia.SEMANAL)
    quantidade: Mapped[int] = mapped_column(Integer, default=1)
    valor_aula: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)


class AulaAvaliativa(Base, Timestamped, CodigoLegado):
    """Aula experimental (ou TotalPass/WellHub avulsa) com ficha de avaliação."""

    __tablename__ = "aula_avaliativa"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoAvaliativa] = mapped_column(coluna_enum(TipoAvaliativa, 20), default=TipoAvaliativa.AVALIATIVA)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id"), index=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissional.id"))
    tipo_servico_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_servico.id"))
    data: Mapped[date] = mapped_column(Date)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    status: Mapped[StatusAvaliativa] = mapped_column(
        coluna_enum(StatusAvaliativa, 20), default=StatusAvaliativa.AGENDADA
    )
    queixa_principal: Mapped[str | None] = mapped_column(Text)
    objetivos: Mapped[str | None] = mapped_column(Text)
    historico_saude: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato.id", ondelete="SET NULL"))


class Reserva(Base, Timestamped, CodigoLegado):
    """Vaga de um aluno numa aula. `contrato_id` é o vínculo explícito (no antigo era inferido por datas)."""

    __tablename__ = "reserva"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id"), index=True)
    aula_sessao_id: Mapped[int] = mapped_column(ForeignKey("aula_sessao.id"), index=True)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato.id"), index=True)
    aula_avulsa_id: Mapped[int | None] = mapped_column(ForeignKey("aula_avulsa.id", ondelete="SET NULL"))
    aula_avaliativa_id: Mapped[int | None] = mapped_column(ForeignKey("aula_avaliativa.id", ondelete="SET NULL"))
    status: Mapped[StatusReserva] = mapped_column(coluna_enum(StatusReserva, 20), default=StatusReserva.RESERVADA)
    confirmada_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    desmarcada_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    reposicao_ate: Mapped[date | None] = mapped_column(Date)
    # motivo da EXCEÇÃO ao prazo de 6 h para desmarcar (só o perfil Full abre; também vai para a auditoria)
    motivo_excecao_prazo: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("aluno_id", "aula_sessao_id", name="uq_reserva_aluno_aula_sessao"),)


class Evolucao(Base, Timestamped, CodigoLegado):
    """Evolução do aluno numa aula (presa à reserva; `criado_em` = data da evolução)."""

    __tablename__ = "evolucao"

    id: Mapped[int] = mapped_column(primary_key=True)
    reserva_id: Mapped[int] = mapped_column(ForeignKey("reserva.id", ondelete="CASCADE"), index=True)
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissional.id"), index=True)
    texto: Mapped[str] = mapped_column(Text)


class Avaliacao(Base, Timestamped, CodigoLegado):
    __tablename__ = "avaliacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    reserva_id: Mapped[int] = mapped_column(ForeignKey("reserva.id", ondelete="CASCADE"), index=True)
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissional.id"), index=True)
    texto: Mapped[str] = mapped_column(Text)


class WhatsappAgendamentoLog(Base, CodigoLegado):
    """Registro de cada aviso automático enviado. `dedupe_key` único impede o envio em duplicidade."""

    __tablename__ = "whatsapp_agendamento_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(220), unique=True)
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"))
    aluno_id: Mapped[int | None] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), index=True)
    profissional_id: Mapped[int | None] = mapped_column(ForeignKey("profissional.id", ondelete="CASCADE"))
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato.id", ondelete="CASCADE"))
    data_referencia: Mapped[date] = mapped_column(Date)
    telefone: Mapped[str | None] = mapped_column(String(20))
    mensagem: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    resposta_payload: Mapped[str | None] = mapped_column(Text)
    enviado_em: Mapped[datetime] = mapped_column(UtcDateTime())

    __table_args__ = (Index("ix_whatsapp_agendamento_log_data_tipo", "data_referencia", "tipo"),)
