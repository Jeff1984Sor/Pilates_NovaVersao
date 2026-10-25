"""Alunos, endereço, telefones, documentos, histórico de WhatsApp e códigos de acesso do app."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import CodigoLegado, coluna_enum


class StatusAluno(enum.StrEnum):
    ATIVO = "ATIVO"
    INATIVO = "INATIVO"


class EstadoCivil(enum.StrEnum):
    SOLTEIRO = "SOLTEIRO"
    CASADO = "CASADO"
    DIVORCIADO = "DIVORCIADO"
    VIUVO = "VIUVO"
    SEPARADO = "SEPARADO"
    UNIAO_ESTAVEL = "UNIAO_ESTAVEL"
    OUTRO = "OUTRO"


class OrigemDocumento(enum.StrEnum):
    UPLOAD = "UPLOAD"
    CONTRATO_PDF = "CONTRATO_PDF"


class DirecaoMensagem(enum.StrEnum):
    enviada = "enviada"
    recebida = "recebida"


class Aluno(Base, Timestamped, CodigoLegado):
    """Aluno do estúdio.

    `cpf` guarda só dígitos e é NULL quando `sem_cpf` (nada de `SEM_CPF_<uuid>`). `codigo_legado` é o
    `cdAluno` usado pelos integradores externos; alunos novos recebem o código do contador "aluno".
    """

    __tablename__ = "aluno"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), index=True)
    cpf: Mapped[str | None] = mapped_column(String(11), unique=True)
    sem_cpf: Mapped[bool] = mapped_column(Boolean, default=False)
    cpf_legado_bruto: Mapped[str | None] = mapped_column(String(32))  # valor antigo quando a normalização o alterou
    rg: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(200))
    foto_path: Mapped[str | None] = mapped_column(String(500))
    autoriza_imagem: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[StatusAluno] = mapped_column(coluna_enum(StatusAluno, 10), default=StatusAluno.ATIVO, index=True)
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    estado_civil: Mapped[EstadoCivil | None] = mapped_column(coluna_enum(EstadoCivil, 20))
    profissao_id: Mapped[int | None] = mapped_column(ForeignKey("profissao.id", ondelete="SET NULL"))
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"), index=True)
    cpf_pagador_recibo: Mapped[str | None] = mapped_column(String(11))  # quem paga, quando não é o aluno
    # termo de uso de imagem
    termo_uso_id: Mapped[int | None] = mapped_column(ForeignKey("termo_uso.id", ondelete="SET NULL"))
    termo_aceite_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    termo_assinatura_nome: Mapped[str | None] = mapped_column(String(150))
    termo_assinatura_documento: Mapped[str | None] = mapped_column(String(30))
    termo_assinatura_ip: Mapped[str | None] = mapped_column(String(45))
    termo_assinatura_path: Mapped[str | None] = mapped_column(String(500))
    termo_assinado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())

    __table_args__ = (
        CheckConstraint(
            "(sem_cpf AND cpf IS NULL) OR (NOT sem_cpf AND cpf IS NOT NULL)", name="cpf_coerente_com_sem_cpf"
        ),
    )


class AlunoEndereco(Base, Timestamped, CodigoLegado):
    """Endereço 1:1 com o aluno (a FK fica aqui; o aluno não aponta de volta, sem ciclo)."""

    __tablename__ = "aluno_endereco"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), unique=True)
    logradouro: Mapped[str] = mapped_column(String(150))
    numero: Mapped[str] = mapped_column(String(20))
    cep: Mapped[str | None] = mapped_column(String(8))  # só dígitos
    cidade: Mapped[str] = mapped_column(String(80))
    bairro: Mapped[str] = mapped_column(String(80))


class AlunoTelefone(Base, Timestamped):
    """Telefones do aluno em ordem (`ordem` 1 = principal). Sem código legado: o antigo recriava a cada salvamento."""

    __tablename__ = "aluno_telefone"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), index=True)
    ordem: Mapped[int] = mapped_column(Integer, default=1)
    numero: Mapped[str] = mapped_column(String(20))  # normalizado (dígitos, DDI 55 quando for o caso)
    numero_original: Mapped[str | None] = mapped_column(String(30))

    __table_args__ = (UniqueConstraint("aluno_id", "numero", name="uq_aluno_telefone_aluno_numero"),)


class AlunoDocumento(Base, Timestamped, CodigoLegado):
    __tablename__ = "aluno_documento"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), index=True)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato.id", ondelete="SET NULL"))
    titulo: Mapped[str] = mapped_column(String(150))
    arquivo_path: Mapped[str] = mapped_column(String(500))  # relativo ao storage: documentos/...
    sha256: Mapped[str | None] = mapped_column(String(64))
    descricao: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[OrigemDocumento] = mapped_column(coluna_enum(OrigemDocumento, 20), default=OrigemDocumento.UPLOAD)


class WhatsappMensagem(Base, CodigoLegado):
    """Histórico de mensagens enviadas e recebidas de um aluno."""

    __tablename__ = "whatsapp_mensagem"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"))
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato.id", ondelete="SET NULL"))
    tipo: Mapped[str] = mapped_column(String(30), default="manual")
    direcao: Mapped[DirecaoMensagem] = mapped_column(coluna_enum(DirecaoMensagem, 10), default=DirecaoMensagem.enviada)
    telefone: Mapped[str | None] = mapped_column(String(20))
    mensagem: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    resposta_payload: Mapped[str | None] = mapped_column(Text)
    enviado_em: Mapped[datetime] = mapped_column(UtcDateTime())

    __table_args__ = (Index("ix_whatsapp_mensagem_aluno_enviado", "aluno_id", "enviado_em"),)


class AppCodigo(Base):
    """Código de uso único (OTP) enviado por WhatsApp para o login do aluno no app. Guarda só o hash."""

    __tablename__ = "app_codigo"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id", ondelete="CASCADE"), index=True)
    codigo_hash: Mapped[str] = mapped_column(String(128))
    expira_em: Mapped[datetime] = mapped_column(UtcDateTime())
    usado: Mapped[bool] = mapped_column(Boolean, default=False)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(UtcDateTime())
