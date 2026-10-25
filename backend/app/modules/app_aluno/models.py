"""Modelo ADITIVO do app do aluno: pedido de reposição.

O aluno só PEDE; quem decide é a gerência (perfil Full, permissão ``reposicoes``). Um pedido ativo (PENDENTE ou APROVADO)
por aula desmarcada (índice único parcial). ``data_origem``/``hora_origem`` são cópias da aula desmarcada: a remarcação
move a própria reserva e a aula antiga pode ser apagada quando fica vazia, então não dá para depender de FK para ela.
Migração: gerar com ``alembic revision --autogenerate`` (tabela nova ``reposicao_pedido``).
"""

import enum
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, ForeignKey, Index, Text, Time, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import coluna_enum


class StatusPedido(enum.StrEnum):
    PENDENTE = "PENDENTE"
    APROVADO = "APROVADO"
    RECUSADO = "RECUSADO"
    CANCELADO = "CANCELADO"  # substituído (a aula aprovada foi desmarcada de novo) ou retirado


class ReposicaoPedido(Base, Timestamped):
    __tablename__ = "reposicao_pedido"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id"), index=True)
    reserva_origem_id: Mapped[int] = mapped_column(ForeignKey("reserva.id", ondelete="CASCADE"), index=True)
    data_origem: Mapped[date] = mapped_column(Date)
    hora_origem: Mapped[time] = mapped_column(Time)
    preferencia: Mapped[str | None] = mapped_column(Text)  # texto livre do aluno (até 300 caracteres, já limpo)
    status: Mapped[StatusPedido] = mapped_column(coluna_enum(StatusPedido, 12), default=StatusPedido.PENDENTE, index=True)
    # aprovação: a própria reserva é remarcada, então reserva_nova_id == reserva_origem_id; data/hora ficam gravadas aqui
    reserva_nova_id: Mapped[int | None] = mapped_column(ForeignKey("reserva.id", ondelete="SET NULL"))
    aprovado_data: Mapped[date | None] = mapped_column(Date)
    aprovado_hora: Mapped[time | None] = mapped_column(Time)
    decidido_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    decidido_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    motivo_recusa: Mapped[str | None] = mapped_column(Text)
    ignorou_prazo: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_ignorar_prazo: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_reposicao_pedido_ativo",
            "reserva_origem_id",
            unique=True,
            sqlite_where=text("status IN ('PENDENTE', 'APROVADO')"),
            postgresql_where=text("status IN ('PENDENTE', 'APROVADO')"),
        ),
    )
