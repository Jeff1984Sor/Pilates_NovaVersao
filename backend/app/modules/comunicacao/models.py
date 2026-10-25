"""Tabelas NOVAS do módulo de comunicação (aditivas; o coordenador gera a migração).

- ``comunicacao_parametro``: chave/valor de ambiente (chave geral "envio automático ativo");
- ``comunicado`` / ``comunicado_destinatario``: fila do comunicado geral, com progresso, pausa e cancelamento.
As tabelas ``whatsapp_config``, ``whatsapp_mensagem`` e ``whatsapp_agendamento_log`` não foram alteradas.
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime


class ComunicacaoParametro(Base, Timestamped):
    __tablename__ = "comunicacao_parametro"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str | None] = mapped_column(Text)


class Comunicado(Base, Timestamped):
    """Comunicado geral. ``status``: enviando | pausado | cancelado | concluido."""

    __tablename__ = "comunicado"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    publico: Mapped[str] = mapped_column(String(10))  # ativos | inativos | todos
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidade.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(12), default="enviando", index=True)
    pausa_segundos: Mapped[int] = mapped_column(Integer, default=5)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    aviso: Mapped[str | None] = mapped_column(String(300))  # ex.: "Sessão do WhatsApp desconectada: envio pausado"
    ultimo_envio_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    finalizado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())


class ComunicadoDestinatario(Base):
    """``status``: pendente | enviando | enviado | falha | sem_telefone | cancelado."""

    __tablename__ = "comunicado_destinatario"

    id: Mapped[int] = mapped_column(primary_key=True)
    comunicado_id: Mapped[int] = mapped_column(ForeignKey("comunicado.id", ondelete="CASCADE"))
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(150))
    telefone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(15), default="pendente")
    erro: Mapped[str | None] = mapped_column(String(300))
    enviado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())

    __table_args__ = (
        UniqueConstraint("comunicado_id", "aluno_id", name="uq_comunicado_destinatario"),
        Index("ix_comunicado_destinatario_status", "comunicado_id", "status"),
    )
