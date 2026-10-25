"""Fornecedores: CRUD com busca, ordenação, paginação e exclusão bloqueada quando há contas a pagar."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select

from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.modules.cadastros.models import Fornecedor, proximo_codigo
from app.modules.cadastros.util_docs import (
    PaginaContagens,
    Pedido,
    Texto,
    contem,
    foto,
    nao_encontrado,
    ordem,
    pagina_de,
    parametros_lista,
    plural,
)
from app.modules.financeiro.models import ContaPagar

router = APIRouter(prefix="/cadastros/fornecedores", tags=["cadastros: fornecedores"])


class FornecedorIn(Schema):
    nome: Texto = Field(min_length=2, max_length=120)


class FornecedorOut(Schema):
    id: int
    codigo: int | None
    nome: str
    contas_a_pagar: int
    criado_em: datetime | None = None


def _contas_a_pagar():
    return (
        select(func.count(ContaPagar.id))
        .where(ContaPagar.fornecedor_id == Fornecedor.id)
        .correlate(Fornecedor)
        .scalar_subquery()
    )


def _out(f: Fornecedor, contas: int) -> FornecedorOut:
    return FornecedorOut(id=f.id, codigo=f.codigo_legado, nome=f.nome, contas_a_pagar=contas, criado_em=f.criado_em)


def _buscar(ctx, fid: int) -> Fornecedor:
    f = ctx.db.get(Fornecedor, fid)
    if not f:
        raise nao_encontrado("Fornecedor")
    return f


def _contas_de(ctx, fid: int) -> int:
    return ctx.db.scalar(select(func.count(ContaPagar.id)).where(ContaPagar.fornecedor_id == fid)) or 0


def _checar_nome(ctx, nome: str, exceto: int | None = None) -> None:
    q = select(Fornecedor.id).where(func.lower(Fornecedor.nome) == nome.lower(), Fornecedor.id != (exceto or 0))
    if ctx.db.scalar(q):
        raise HTTPException(409, "Já existe um fornecedor com este nome.")


@router.get("", response_model=PaginaContagens[FornecedorOut])
def listar(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    uso: Annotated[str, Query(pattern="^(todos|em_uso|sem_uso)$")] = "todos",
):
    """`uso`: em_uso = tem contas a pagar; sem_uso = nenhuma (pode ser excluído)."""
    n = _contas_a_pagar()
    base = select(Fornecedor, n.label("contas"))
    if pedido.q:
        base = base.where(contem(Fornecedor.nome, pedido.q))
    # contagens dos chips: só com a busca
    contagens = {"todos": 0, "em_uso": 0, "sem_uso": 0}
    for _f, contas in ctx.db.execute(base).all():
        contagens["todos"] += 1
        contagens["em_uso" if contas else "sem_uso"] += 1
    stmt = base
    if uso == "em_uso":
        stmt = stmt.where(n > 0)
    elif uso == "sem_uso":
        stmt = stmt.where(n == 0)
    colunas = {"nome": func.lower(Fornecedor.nome), "codigo": Fornecedor.codigo_legado, "contas": n}
    stmt = stmt.order_by(ordem(pedido, colunas, "nome"), Fornecedor.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=[_out(f, c) for f, c in linhas], total=total, pagina=pedido.pagina, por_pagina=pedido.por_pagina,
        contagens=contagens,
    )


@router.get("/{fid}", response_model=FornecedorOut)
def ler(fid: int, ctx: Ctx):
    f = _buscar(ctx, fid)
    return _out(f, _contas_de(ctx, fid))


@router.post("", response_model=FornecedorOut, status_code=201)
def criar(dados: FornecedorIn, ctx: Ctx):
    _checar_nome(ctx, dados.nome)
    f = Fornecedor(nome=dados.nome, codigo_legado=proximo_codigo(ctx.db, "fornecedor"))
    ctx.db.add(f)
    ctx.db.flush()
    ctx.auditar("fornecedor.criar", "fornecedor", f.id, descricao=f.nome, depois=foto(f))
    ctx.db.commit()
    return _out(f, 0)


@router.put("/{fid}", response_model=FornecedorOut)
def alterar(fid: int, dados: FornecedorIn, ctx: Ctx):
    f = _buscar(ctx, fid)
    _checar_nome(ctx, dados.nome, exceto=fid)
    antes = foto(f)
    f.nome = dados.nome
    ctx.db.flush()
    ctx.auditar("fornecedor.alterar", "fornecedor", f.id, descricao=f.nome, antes=antes, depois=foto(f))
    ctx.db.commit()
    return _out(f, _contas_de(ctx, fid))


@router.delete("/{fid}", response_model=Mensagem)
def excluir(fid: int, ctx: Ctx):
    f = _buscar(ctx, fid)
    contas = _contas_de(ctx, fid)
    if contas:
        raise HTTPException(
            409,
            f"Não é possível excluir: {f.nome} tem {plural(contas, 'conta a pagar', 'contas a pagar')} lançada(s). "
            "Mantenha o fornecedor para preservar o histórico financeiro.",
        )
    antes = foto(f)
    ctx.db.delete(f)
    ctx.auditar("fornecedor.excluir", "fornecedor", fid, descricao=f.nome, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Fornecedor excluído.")
