"""Esquemas da tela de integrações (tokens de API e TotalPass). Segredos: só escrita; a leitura mostra "definido" + final."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ------------------------------------------------------------------------------------------------ tokens de API
class TokenCriarIn(Base):
    nome: str = Field(min_length=2, max_length=120)


class TokenEditarIn(Base):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    ativo: bool | None = None


class TokenOut(Base):
    id: int
    nome: str
    token_final: str | None
    ativo: bool
    precisa_regenerar: bool
    ultimo_uso: datetime | None
    criado_em: datetime


class TokenComValorOut(TokenOut):
    """Resposta de criar/regenerar: o `valor` completo aparece UMA ÚNICA VEZ."""

    valor: str


# ------------------------------------------------------------------------------------------------ TotalPass
class SegredoOut(Base):
    definido: bool
    final: str | None = None


class TotalpassConfigOut(Base):
    unidade_id: int
    unidade_nome: str
    configurada: bool
    ativo: bool
    place_id: str | None
    criar_aluno_automatico: bool
    somente_dia: bool
    servico_padrao_id: int | None
    sync_ativo: bool
    sync_ultimo_em: datetime | None
    sync_ultimo_resumo: str | None
    partner_api_key: SegredoOut
    place_api_key: SegredoOut
    webhook_token: SegredoOut


class ServicoOpcao(Base):
    id: int
    nome: str


class TotalpassTelaOut(Base):
    webhook_caminho: str
    configuracoes: list[TotalpassConfigOut]
    servicos: list[ServicoOpcao]


class TotalpassConfigIn(Base):
    ativo: bool = True
    place_id: str | None = Field(default=None, max_length=120)
    criar_aluno_automatico: bool = True
    somente_dia: bool = True
    servico_padrao_id: int | None = None
    sync_ativo: bool = False
    # somente escrita: ausente/vazio = manter. Para apagar, liste o nome em `limpar`.
    partner_api_key: str | None = Field(default=None, max_length=200)
    place_api_key: str | None = Field(default=None, max_length=200)
    webhook_token: str | None = Field(default=None, min_length=16, max_length=200)
    limpar: list[Literal["partner_api_key", "place_api_key", "webhook_token"]] = Field(default_factory=list)


class WebhookTokenOut(Base):
    """Resposta de 'gerar token do webhook': o valor aparece UMA ÚNICA VEZ (cole no painel do TotalPass)."""

    valor: str
    final: str


class SincronizarIn(Base):
    dia: date | None = None  # padrão: hoje


class ResumoSyncOut(Base):
    resumo: str
    dia: date
    recebidos: int
    processados: int
    cancelados: int
    descartados: int
    duplicados: int
    erros: int


class EventoOut(Base):
    id: int
    recebido_em: datetime
    processado_em: datetime | None
    origem: str | None
    event_id: str | None
    slot_id: str | None
    documento_mascarado: str | None
    status: str | None
    titulo: str | None
    aula_em: str | None
    resultado: str  # processado | cancelado | descartado | erro | pendente
    erro: str | None
    reserva_id: int | None


class ListaEventosOut(Base):
    total: int
    pagina: int
    por_pagina: int
    itens: list[EventoOut]
