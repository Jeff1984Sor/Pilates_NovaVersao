"""Contratos de aluno (sempre mensais; as parcelas ficam em `financeiro.conta_receber`)."""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import CodigoLegado, coluna_enum
from app.modules.cadastros.models import Recorrencia


class StatusAssinatura(enum.StrEnum):
    NAO_ASSINADO = "NAO_ASSINADO"
    ASSINADO = "ASSINADO"
    ASSINADO_DIGITALMENTE = "ASSINADO_DIGITALMENTE"


class FormaPagamento(enum.StrEnum):
    DINHEIRO = "DINHEIRO"
    PIX = "PIX"
    CREDITO = "CREDITO"
    DEBITO = "DEBITO"


class Contrato(Base, Timestamped, CodigoLegado):
    __tablename__ = "contrato"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id"), index=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("plano.id"), index=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissional.id"))
    recorrencia: Mapped[Recorrencia] = mapped_column(coluna_enum(Recorrencia, 10), default=Recorrencia.MENSAL)
    forma_pagamento: Mapped[FormaPagamento | None] = mapped_column(coluna_enum(FormaPagamento, 20))
    valor_aula: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2)
    )  # informativo: valor mensal / (aulas por semana x 4)
    valor_parcela: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)
    status_assinatura: Mapped[StatusAssinatura] = mapped_column(
        coluna_enum(StatusAssinatura, 30), default=StatusAssinatura.NAO_ASSINADO
    )
    assinado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    assinatura_nome: Mapped[str | None] = mapped_column(String(150))
    assinatura_documento: Mapped[str | None] = mapped_column(String(30))
    assinatura_ip: Mapped[str | None] = mapped_column(String(45))
    assinatura_path: Mapped[str | None] = mapped_column(String(500))  # assinaturas/contrato/...

    __table_args__ = (
        CheckConstraint("valor_parcela >= 0 AND valor_total >= 0", name="valores_nao_negativos"),
        Index("ix_contrato_vigencia", "data_inicio", "data_fim"),
    )
