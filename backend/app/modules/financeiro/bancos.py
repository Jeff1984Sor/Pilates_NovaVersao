"""Contas bancárias e movimentos. O saldo é SEMPRE calculado (saldo inicial + entradas - saídas), nunca gravado."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domain.financeiro import saldo_bancario_base
from app.modules.financeiro.models import ContaBancaria, MovimentoConta, TipoMovimento
from app.modules.financeiro.servico import ErroDeNegocio, validar_conta_bancaria

ZERO = Decimal("0")


def _d(v) -> Decimal:
    """Soma vinda do banco -> Decimal com 2 casas (o SQLite devolve float em somas)."""
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def soma_movimentos(db: Session, conta_ids: list[int] | None, *, desde: date | None = None,
                    antes_de: date | None = None, ate: date | None = None) -> tuple[Decimal, Decimal]:
    """(entradas, saídas) das contas (None = todas as ATIVAS), com data < antes_de e/ou <= ate."""
    entra = func.coalesce(func.sum(case((MovimentoConta.tipo == TipoMovimento.ENTRADA, MovimentoConta.valor), else_=0)), 0)
    sai = func.coalesce(func.sum(case((MovimentoConta.tipo == TipoMovimento.SAIDA, MovimentoConta.valor), else_=0)), 0)
    stmt = select(entra, sai).select_from(MovimentoConta).join(ContaBancaria, ContaBancaria.id == MovimentoConta.conta_id)
    if conta_ids is None:
        stmt = stmt.where(ContaBancaria.ativo.is_(True))
    else:
        stmt = stmt.where(MovimentoConta.conta_id.in_(conta_ids))
    if desde:
        stmt = stmt.where(MovimentoConta.data >= desde)
    if antes_de:
        stmt = stmt.where(MovimentoConta.data < antes_de)
    if ate:
        stmt = stmt.where(MovimentoConta.data <= ate)
    e, s = db.execute(stmt).one()
    return _d(e), _d(s)


def saldo_conta(db: Session, conta: ContaBancaria, *, ate: date | None = None) -> Decimal:
    """Saldo da conta (até o fim do dia `ate`, ou hoje/total se None)."""
    e, s = soma_movimentos(db, [conta.id], ate=ate)
    return conta.saldo_inicial + e - s


def saldo_inicial_das_ativas(db: Session, conta_id: int | None) -> Decimal:
    stmt = select(func.coalesce(func.sum(ContaBancaria.saldo_inicial), 0))
    stmt = stmt.where(ContaBancaria.id == conta_id) if conta_id else stmt.where(ContaBancaria.ativo.is_(True))
    return _d(db.scalar(stmt))


def saldo_base_antes_de(db: Session, inicio: date, conta_id: int | None = None) -> Decimal:
    """Saldo bancário no começo de `inicio`: saldo inicial das contas ATIVAS (ou só da `conta_id`) + movimentos anteriores.

    Mesmo critério para fluxo de caixa e DRE (o antigo divergia: a DRE somava também contas inativas).
    """
    e, s = soma_movimentos(db, [conta_id] if conta_id else None, antes_de=inicio)
    return saldo_bancario_base(saldo_inicial_das_ativas(db, conta_id), e, s)


def contar_movimentos(db: Session, conta_id: int) -> int:
    return db.scalar(select(func.count()).select_from(MovimentoConta).where(MovimentoConta.conta_id == conta_id)) or 0


def conta_ativa(db: Session, conta_id: int) -> ContaBancaria:
    return validar_conta_bancaria(db, conta_id)


def criar_movimento(db: Session, *, conta_id: int, tipo: TipoMovimento, valor: Decimal, data: date,
                    descricao: str | None = None, comprovante_path: str | None = None,
                    conta_receber_id: int | None = None, conta_pagar_id: int | None = None,
                    transferencia_id: str | None = None) -> MovimentoConta:
    if valor < 0:
        raise ErroDeNegocio("O valor do movimento não pode ser negativo.", 422)
    conta_ativa(db, conta_id)
    m = MovimentoConta(conta_id=conta_id, tipo=tipo, valor=valor, data=data, descricao=descricao,
                       comprovante_path=comprovante_path, conta_receber_id=conta_receber_id,
                       conta_pagar_id=conta_pagar_id, transferencia_id=transferencia_id)
    db.add(m)
    db.flush()
    return m


def opcoes_contas_ativas(db: Session) -> list[dict]:
    """Contas ativas para os seletores (id + rótulo), sem expor saldos."""
    contas = db.scalars(select(ContaBancaria).where(ContaBancaria.ativo.is_(True)).order_by(ContaBancaria.banco, ContaBancaria.id))
    return [{"id": c.id, "nome": f"{c.banco} ag. {c.agencia} c/c {c.conta}"} for c in contas]
