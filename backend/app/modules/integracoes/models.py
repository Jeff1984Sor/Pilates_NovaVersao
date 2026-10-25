"""Configurações por unidade de WhatsApp e TotalPass, e eventos do webhook TotalPass.

Segredos ficam em colunas `*_cifrado` (Fernet com a MASTER_KEY; o ETL cifra na carga).
"""

import enum
from datetime import datetime, time
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import CodigoLegado, coluna_enum


class ProvedorWhatsapp(enum.StrEnum):
    wasender = "wasender"
    evolution = "evolution"


class WhatsappConfig(Base, Timestamped, CodigoLegado):
    """Uma por unidade. `instancia` preenchida = Evolution API; vazia = WasenderAPI (como no sistema antigo)."""

    __tablename__ = "whatsapp_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"), unique=True)
    provedor: Mapped[ProvedorWhatsapp] = mapped_column(coluna_enum(ProvedorWhatsapp, 10), default=ProvedorWhatsapp.wasender)
    url_api: Mapped[str | None] = mapped_column(String(300))
    usuario_api: Mapped[str | None] = mapped_column(String(150))
    credencial_cifrado: Mapped[str | None] = mapped_column(Text)  # token Wasender / senha Evolution
    instancia: Mapped[str | None] = mapped_column(String(150))

    acompanhar_envios: Mapped[bool] = mapped_column(Boolean, default=False)
    numero_acompanhamento: Mapped[str | None] = mapped_column(String(20))

    avisar_aluno: Mapped[bool] = mapped_column(Boolean, default=True)
    horario_aviso_aluno: Mapped[time] = mapped_column(Time, default=time(19, 0))
    template_aviso_aluno: Mapped[str | None] = mapped_column(Text)
    avisar_professor: Mapped[bool] = mapped_column(Boolean, default=True)
    horario_aviso_professor: Mapped[time] = mapped_column(Time, default=time(18, 0))
    template_aviso_professor: Mapped[str | None] = mapped_column(Text)
    enviar_link_contrato: Mapped[bool] = mapped_column(Boolean, default=True)
    template_link_contrato: Mapped[str | None] = mapped_column(Text)
    avisar_renovacao: Mapped[bool] = mapped_column(Boolean, default=True)
    horario_aviso_renovacao: Mapped[time] = mapped_column(Time, default=time(10, 0))
    template_aviso_renovacao: Mapped[str | None] = mapped_column(Text)
    avisar_aniversario: Mapped[bool] = mapped_column(Boolean, default=False)
    horario_aviso_aniversario: Mapped[time] = mapped_column(Time, default=time(9, 0))
    template_aniversario: Mapped[str | None] = mapped_column(Text)
    avisar_vencimento: Mapped[bool] = mapped_column(Boolean, default=False)
    horario_aviso_vencimento: Mapped[time] = mapped_column(Time, default=time(10, 0))
    template_vencimento_proximo: Mapped[str | None] = mapped_column(Text)
    avisar_atraso: Mapped[bool] = mapped_column(Boolean, default=False)
    horario_aviso_atraso: Mapped[time] = mapped_column(Time, default=time(10, 0))
    template_mensalidade_atraso: Mapped[str | None] = mapped_column(Text)
    avisar_tres_meses: Mapped[bool] = mapped_column(Boolean, default=False)
    horario_aviso_tres_meses: Mapped[time] = mapped_column(Time, default=time(10, 0))
    template_tres_meses: Mapped[str | None] = mapped_column(Text)
    avisar_fim_contrato: Mapped[bool] = mapped_column(Boolean, default=True)
    template_fim_contrato: Mapped[str | None] = mapped_column(Text)
    variaveis_template: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class TotalpassConfig(Base, Timestamped, CodigoLegado):
    __tablename__ = "totalpass_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id", ondelete="CASCADE"), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    partner_api_key_cifrado: Mapped[str | None] = mapped_column(Text)
    place_api_key_cifrado: Mapped[str | None] = mapped_column(Text)
    webhook_token_cifrado: Mapped[str | None] = mapped_column(Text)
    place_id: Mapped[str | None] = mapped_column(String(120))
    criar_aluno_automatico: Mapped[bool] = mapped_column(Boolean, default=True)
    somente_dia: Mapped[bool] = mapped_column(Boolean, default=True)


class TotalpassEvento(Base, CodigoLegado):
    """Auditoria de cada chamada do webhook TotalPass."""

    __tablename__ = "totalpass_evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String(100))
    slot_id: Mapped[str | None] = mapped_column(String(100))
    documento_usuario: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(30))
    payload: Mapped[Any] = mapped_column(JSON)
    recebido_em: Mapped[datetime] = mapped_column(UtcDateTime())
    processado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    erro: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_totalpass_evento_event_id", "event_id"),
        Index("ix_totalpass_evento_slot_id", "slot_id"),
        Index("ix_totalpass_evento_recebido_em", "recebido_em"),
    )
