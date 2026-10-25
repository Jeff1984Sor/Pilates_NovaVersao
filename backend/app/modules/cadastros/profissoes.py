"""Profissões dos alunos (`/api/cadastros/profissoes`). CRUD simples; a permissão é a de `cadastros_profissionais`."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core.deps import Ctx
from app.core.schemas import Mensagem, Pagina, Schema
from app.modules.cadastros import comum
from app.modules.cadastros.comum import VinculosOut
from app.modules.cadastros.models import Profissao, proximo_codigo

router = APIRouter(prefix="/cadastros/profissoes", tags=["cadastros: profissões"])

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


class ProfissaoIn(BaseModel):
    nome: Nome


class ProfissaoOut(Schema):
    id: int
    codigo: int | None
    nome: str


def _out(p: Profissao) -> ProfissaoOut:
    return ProfissaoOut(id=p.id, codigo=p.codigo_legado, nome=p.nome)


def _obter(ctx, profissao_id: int) -> Profissao:
    p = ctx.db.get(Profissao, profissao_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profissão não encontrada.")
    return p


_ORDEM = {"nome": Profissao.nome, "codigo": Profissao.codigo_legado}


@router.get("", response_model=Pagina[ProfissaoOut])
def listar(
    ctx: Ctx,
    q: str | None = None,
    ordenar: str | None = None,
    direcao: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
):
    onde = [Profissao.nome.ilike(comum.like(q), escape="\\")] if q and q.strip() else []
    total = ctx.db.scalar(select(func.count()).select_from(Profissao).where(*onde)) or 0
    itens = ctx.db.scalars(
        select(Profissao).where(*onde).order_by(comum.ordenar_por(_ORDEM, ordenar, direcao, "nome"), Profissao.id)
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    )
    return Pagina[ProfissaoOut](itens=[_out(p) for p in itens], total=total, pagina=pagina, por_pagina=por_pagina)


@router.get("/{profissao_id}", response_model=ProfissaoOut)
def ler(profissao_id: int, ctx: Ctx):
    return _out(_obter(ctx, profissao_id))


@router.post("", response_model=ProfissaoOut, status_code=201)
def criar(dados: ProfissaoIn, ctx: Ctx):
    if comum.duplicado(ctx.db, Profissao, Profissao.nome, dados.nome):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma profissão com este nome.")
    p = Profissao(nome=dados.nome, codigo_legado=proximo_codigo(ctx.db, "profissao"))
    ctx.db.add(p)
    ctx.db.flush()
    ctx.auditar("profissao.criar", "profissao", p.id, descricao=p.nome, depois=audit.snapshot(p))
    ctx.db.commit()
    return _out(p)


@router.put("/{profissao_id}", response_model=ProfissaoOut)
def alterar(profissao_id: int, dados: ProfissaoIn, ctx: Ctx):
    p = _obter(ctx, profissao_id)
    if comum.duplicado(ctx.db, Profissao, Profissao.nome, dados.nome, exceto_id=p.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma profissão com este nome.")
    antes = audit.snapshot(p)
    p.nome = dados.nome
    ctx.db.flush()
    a, d = audit.diff(antes, audit.snapshot(p))
    ctx.auditar("profissao.alterar", "profissao", p.id, descricao=p.nome, antes=a, depois=d)
    ctx.db.commit()
    return _out(p)


@router.get("/{profissao_id}/vinculos", response_model=VinculosOut)
def ver_vinculos(profissao_id: int, ctx: Ctx):
    _obter(ctx, profissao_id)
    return comum.vinculos_out(ctx.db, Profissao, profissao_id, tem_ativo=False)


@router.delete("/{profissao_id}", response_model=Mensagem)
def excluir(profissao_id: int, ctx: Ctx):
    p = _obter(ctx, profissao_id)
    comum.bloquear_se_vinculado(ctx.db, Profissao, p.id, "a profissão", tem_ativo=False)
    snap, nome = audit.snapshot(p), p.nome
    try:
        ctx.db.delete(p)
        ctx.auditar("profissao.excluir", "profissao", profissao_id, descricao=nome, antes=snap)
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível excluir a profissão: ela está em uso.") from None
    return Mensagem(mensagem=f"Profissão {nome} excluída.")
