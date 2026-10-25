"""Financeiro: contas a receber/pagar, conta bancária, movimentos, comissão e configuração do Receita Saúde.

`ATRASADO` não é status gravado: é derivado (vencida e não paga) na consulta.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import CodigoLegado, coluna_enum
from app.modules.cadastros.models import Recorrencia  # noqa: F401  (reexporta para quem importa daqui)


class StatusReceber(enum.StrEnum):
    ABERTO = "ABERTO"
    PAGO = "PAGO"
    CANCELADO = "CANCELADO"


class StatusPagar(enum.StrEnum):
    AGENDADO = "AGENDADO"
    PAGO = "PAGO"
    CANCELADO = "CANCELADO"


class RecorrenciaPagar(enum.StrEnum):
    MENSAL = "MENSAL"
    SEMANAL = "SEMANAL"
    ANUAL = "ANUAL"


class TipoMovimento(enum.StrEnum):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"


class ContaReceber(Base, Timestamped, CodigoLegado):
    """Cobrança. `aluno_id` é sempre preenchido (contrato -> reserva -> aluno); contrato e reserva são opcionais."""

    __tablename__ = "conta_receber"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id"))
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato.id"))
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reserva.id", ondelete="SET NULL"))
    descricao: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[StatusReceber] = mapped_column(coluna_enum(StatusReceber, 10), default=StatusReceber.ABERTO)
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    vencimento: Mapped[date] = mapped_column(Date)
    competencia: Mapped[str | None] = mapped_column(String(7))  # "YYYY-MM" (mensal) ou "YYYY-WW" (semanal)
    pagamento: Mapped[date | None] = mapped_column(Date)
    recibo_saude_gerado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())

    __table_args__ = (
        CheckConstraint("valor >= 0", name="valor_nao_negativo"),
        Index("ix_conta_receber_aluno_vencimento", "aluno_id", "vencimento"),
        Index("ix_conta_receber_vencimento_status", "vencimento", "status"),
        Index("ix_conta_receber_contrato", "contrato_id"),
        Index("ix_conta_receber_pagamento", "pagamento"),
    )


class ContaPagar(Base, Timestamped, CodigoLegado):
    __tablename__ = "conta_pagar"

    id: Mapped[int] = mapped_column(primary_key=True)
    fornecedor_id: Mapped[int] = mapped_column(ForeignKey("fornecedor.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    subcategoria_id: Mapped[int] = mapped_column(ForeignKey("subcategoria.id"))
    vencimento: Mapped[date] = mapped_column(Date)
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    recorrencia: Mapped[RecorrenciaPagar | None] = mapped_column(coluna_enum(RecorrenciaPagar, 10))
    recorrencia_quantidade: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[StatusPagar] = mapped_column(coluna_enum(StatusPagar, 10), default=StatusPagar.AGENDADO)
    pagamento: Mapped[date | None] = mapped_column(Date)
    comprovante_path: Mapped[str | None] = mapped_column(String(500))  # comprovantes/contas_pagar/...
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("valor >= 0", name="valor_nao_negativo"),
        Index("ix_conta_pagar_vencimento_status", "vencimento", "status"),
    )


class ContaBancaria(Base, Timestamped, CodigoLegado):
    __tablename__ = "conta_bancaria"

    id: Mapped[int] = mapped_column(primary_key=True)
    banco: Mapped[str] = mapped_column(String(120))
    agencia: Mapped[str] = mapped_column(String(20))
    conta: Mapped[str] = mapped_column(String(20))
    saldo_inicial: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class MovimentoConta(Base, Timestamped, CodigoLegado):
    __tablename__ = "movimento_conta"

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta_bancaria.id"), index=True)
    tipo: Mapped[TipoMovimento] = mapped_column(coluna_enum(TipoMovimento, 10))
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    data: Mapped[date] = mapped_column(Date, index=True)
    descricao: Mapped[str | None] = mapped_column(String(200))
    comprovante_path: Mapped[str | None] = mapped_column(String(500))  # comprovantes/movimentos/...

    __table_args__ = (CheckConstraint("valor >= 0", name="valor_nao_negativo"),)


class Comissao(Base, Timestamped):
    """Comissão do profissional sobre uma conta paga (única por conta). Funcionalidade nova: o ETL não preenche."""

    __tablename__ = "comissao"

    id: Mapped[int] = mapped_column(primary_key=True)
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissional.id"), index=True)
    conta_receber_id: Mapped[int] = mapped_column(ForeignKey("conta_receber.id"), unique=True)
    competencia: Mapped[str] = mapped_column(String(7), index=True)
    valor_base: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    percentual: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2))


class ReceitaSaudeConfig(Base, Timestamped):
    """Dados do profissional que emite os recibos no Receita Saúde (registro único)."""

    __tablename__ = "receita_saude_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    cpf_profissional: Mapped[str] = mapped_column(String(11))
    registro_profissional: Mapped[str | None] = mapped_column(String(15))
    codigo_ocupacao: Mapped[str] = mapped_column(String(3), default="231")
    descricao_padrao: Mapped[str] = mapped_column(String(200), default="Aulas de Pilates")
