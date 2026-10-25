"""Cadastros de apoio: unidades, serviços, planos, profissionais, financeiro básico, agenda base e modelos de texto."""

import enum
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    Time,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.db import Base, Timestamped, UtcDateTime
from app.modules.base import CodigoLegado, coluna_enum


class Recorrencia(enum.StrEnum):
    SEMANAL = "SEMANAL"
    MENSAL = "MENSAL"


class TipoCategoria(enum.StrEnum):
    RECEITA = "RECEITA"
    DESPESA = "DESPESA"


class ContadorCodigo(Base):
    """Contador transacional dos códigos de negócio (substitui o `max(cd)+1` do sistema antigo)."""

    __tablename__ = "contador_codigo"

    nome: Mapped[str] = mapped_column(String(60), primary_key=True)
    ultimo: Mapped[int] = mapped_column(Integer, default=0)


def proximo_codigo(db: Session, nome: str) -> int:
    """Próximo código da série `nome` (ex.: "aluno"), atômico: `UPDATE ... RETURNING` na transação.

    Duas transações simultâneas nunca recebem o mesmo número (a linha fica bloqueada até o commit).
    """
    t = ContadorCodigo.__table__
    for _ in range(2):
        novo = db.execute(
            update(t).where(t.c.nome == nome).values(ultimo=t.c.ultimo + 1).returning(t.c.ultimo)
        ).scalar()
        if novo is not None:
            return novo
        # primeira vez da série: cria a linha (corrida entre duas transações é resolvida pelo ON CONFLICT)
        if db.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as ins
        else:
            from sqlalchemy.dialects.sqlite import insert as ins
        db.execute(ins(t).values(nome=nome, ultimo=0).on_conflict_do_nothing())
    raise RuntimeError(f"não foi possível obter o próximo código de {nome!r}")


class Unidade(Base, Timestamped, CodigoLegado):
    __tablename__ = "unidade"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    capacidade: Mapped[int] = mapped_column(Integer, default=0)  # vagas por aula quando a sessão não define a sua
    duracao_aula_minutos: Mapped[int] = mapped_column(Integer, default=50)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (CheckConstraint("capacidade >= 0", name="capacidade_nao_negativa"),)


class TipoServico(Base, Timestamped, CodigoLegado):
    __tablename__ = "tipo_servico"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Profissao(Base, Timestamped, CodigoLegado):
    __tablename__ = "profissao"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))


class Categoria(Base, Timestamped, CodigoLegado):
    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[TipoCategoria] = mapped_column(coluna_enum(TipoCategoria, 10), default=TipoCategoria.DESPESA)


class Subcategoria(Base, Timestamped, CodigoLegado):
    __tablename__ = "subcategoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))


class Fornecedor(Base, Timestamped, CodigoLegado):
    __tablename__ = "fornecedor"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))


class ModeloContrato(Base, Timestamped, CodigoLegado):
    """Texto HTML do contrato com variáveis `{...}`."""

    __tablename__ = "modelo_contrato"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    conteudo_html: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class ModeloEvolucao(Base, Timestamped, CodigoLegado):
    __tablename__ = "modelo_evolucao"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(120))
    texto: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class TermoUso(Base, Timestamped, CodigoLegado):
    """Termo de uso de imagem (HTML com variáveis `{ALUNO_*}`)."""

    __tablename__ = "termo_uso"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    conteudo_html: Mapped[str] = mapped_column(Text)


class Plano(Base, Timestamped, CodigoLegado):
    __tablename__ = "plano"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    tipo_servico_id: Mapped[int] = mapped_column(ForeignKey("tipo_servico.id"), index=True)
    categoria_receita_id: Mapped[int | None] = mapped_column(ForeignKey("categoria.id"))
    subcategoria_receita_id: Mapped[int | None] = mapped_column(ForeignKey("subcategoria.id"))
    modelo_contrato_id: Mapped[int | None] = mapped_column(ForeignKey("modelo_contrato.id"))
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)  # valor MENSAL
    aulas_por_semana: Mapped[int] = mapped_column(Integer, default=1)
    duracao_meses: Mapped[int] = mapped_column(Integer, default=1)
    recorrencia: Mapped[Recorrencia] = mapped_column(coluna_enum(Recorrencia, 10), default=Recorrencia.MENSAL)
    avulso: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("valor >= 0", name="valor_nao_negativo"),
        CheckConstraint("aulas_por_semana >= 0", name="aulas_semana_nao_negativo"),
    )


class Profissional(Base, Timestamped, CodigoLegado):
    """Pessoa que dá aula. Pode existir sem login (`usuario_id` nulo)."""

    __tablename__ = "profissional"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(200))
    celular: Mapped[str | None] = mapped_column(String(20))
    crefito: Mapped[str | None] = mapped_column(String(50))
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), unique=True)
    perfil_acesso_id: Mapped[int | None] = mapped_column(ForeignKey("perfil_acesso.id"))
    comissao_percentual: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("comissao_percentual >= 0 AND comissao_percentual <= 100", name="comissao_faixa"),
    )


horario_funcionamento_tipo_servico = Table(
    "horario_funcionamento_tipo_servico",
    Base.metadata,
    Column("horario_funcionamento_id", ForeignKey("horario_funcionamento.id", ondelete="CASCADE"), primary_key=True),
    Column("tipo_servico_id", ForeignKey("tipo_servico.id"), primary_key=True),
)


class HorarioFuncionamento(Base, Timestamped, CodigoLegado):
    """Janela de funcionamento da unidade num dia da semana (0=segunda ... 6=domingo).

    Sem nenhum serviço associado vale para todos os serviços.
    """

    __tablename__ = "horario_funcionamento"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"), index=True)
    dia_semana: Mapped[int] = mapped_column(Integer)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    tipos_servico: Mapped[list[TipoServico]] = relationship(secondary=horario_funcionamento_tipo_servico)

    __table_args__ = (
        CheckConstraint("dia_semana BETWEEN 0 AND 6", name="dia_semana_valido"),
        CheckConstraint("hora_fim > hora_inicio", name="hora_fim_maior"),
    )


class HorarioStudio(Base, Timestamped, CodigoLegado):
    """Grade fixa antiga por dia da semana (usada para gerar horários)."""

    __tablename__ = "horario_studio"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"), index=True)
    tipo_servico_id: Mapped[int] = mapped_column(ForeignKey("tipo_servico.id"))
    profissional_id: Mapped[int | None] = mapped_column(ForeignKey("profissional.id"))
    dia_semana: Mapped[int] = mapped_column(Integer)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    capacidade: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (CheckConstraint("dia_semana BETWEEN 0 AND 6", name="dia_semana_valido"),)


class BloqueioAgenda(Base, Timestamped, CodigoLegado):
    __tablename__ = "bloqueio_agenda"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade.id"), index=True)
    tipo_servico_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_servico.id"))
    profissional_id: Mapped[int | None] = mapped_column(ForeignKey("profissional.id"))
    recorrente: Mapped[bool] = mapped_column(Boolean, default=False)
    dia_semana: Mapped[int | None] = mapped_column(Integer)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    motivo: Mapped[str | None] = mapped_column(String(200))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("hora_fim > hora_inicio", name="hora_fim_maior"),
        CheckConstraint("NOT recorrente OR dia_semana IS NOT NULL", name="recorrente_exige_dia"),
        Index("ix_bloqueio_agenda_data_inicio", "data_inicio"),
    )


class IntegracaoToken(Base, Timestamped, CodigoLegado):
    """Chave de API de uma empresa integradora.

    O valor do token NÃO fica em claro: guarda-se o SHA-256 (`token_hash`) e os 4 últimos caracteres.
    Tokens migrados do antigo vêm sem valor (`token_hash` nulo, `precisa_regenerar`): o valor é gerado de novo na tela.
    O integrador continua enviando o mesmo valor; o sistema compara o hash.
    """

    __tablename__ = "integracao_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_final: Mapped[str | None] = mapped_column(String(4))
    precisa_regenerar: Mapped[bool] = mapped_column(Boolean, default=False)  # migrado sem o valor: gerar um novo
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_uso: Mapped[datetime | None] = mapped_column(UtcDateTime())
