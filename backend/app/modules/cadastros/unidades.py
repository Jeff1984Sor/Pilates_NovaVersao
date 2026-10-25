"""Unidades do estúdio (`/api/cadastros/unidades`).

Regra R3 (capacidade): `capacidade` é o número de vagas por aula DA UNIDADE. Uma sessão de aula cuja capacidade
própria é nula HERDA este valor (`app.domain.capacidade.capacidade_efetiva`); capacidade 0 na sessão vale 0 (sem
vagas) e capacidade 0 na unidade significa "sem vagas por padrão". `duracao_aula_minutos` é a duração padrão
usada para sugerir o horário final e corrigir horários invertidos.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.modules.cadastros import comum
from app.modules.cadastros.comum import PaginaCad, Situacao, VinculosOut
from app.modules.cadastros.models import Unidade, proximo_codigo

router = APIRouter(prefix="/cadastros/unidades", tags=["cadastros: unidades"])

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


class UnidadeIn(BaseModel):
    nome: Nome
    capacidade: int = Field(default=1, ge=0, le=500, description="Vagas por aula quando a aula não define a sua (0 = sem vagas)")
    duracao_aula_minutos: int = Field(default=50, ge=10, le=240)
    ativo: bool = True


class UnidadeOut(Schema):
    id: int
    codigo: int | None
    nome: str
    capacidade: int
    duracao_aula_minutos: int
    ativo: bool


def _out(db, u: Unidade) -> UnidadeOut:
    return UnidadeOut(id=u.id, codigo=u.codigo_legado, nome=u.nome, capacidade=u.capacidade,
                      duracao_aula_minutos=u.duracao_aula_minutos, ativo=u.ativo)


def _obter(ctx, unidade_id: int) -> Unidade:
    u = ctx.db.get(Unidade, unidade_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unidade não encontrada.")
    return u


_ORDEM = {"nome": Unidade.nome, "capacidade": Unidade.capacidade, "duracao": Unidade.duracao_aula_minutos,
          "codigo": Unidade.codigo_legado}


@router.get("", response_model=PaginaCad[UnidadeOut])
def listar(
    ctx: Ctx,
    q: str | None = None,
    situacao: Situacao = "todos",
    ordenar: str | None = None,
    direcao: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
):
    filtros = [Unidade.nome.ilike(comum.like(q), escape="\\")] if q and q.strip() else []
    contagens = comum.contar_situacoes(ctx.db, Unidade.id, Unidade.ativo, filtros)
    sit = comum.filtro_situacao(Unidade.ativo, situacao)
    onde = filtros + ([sit] if sit is not None else [])
    total = ctx.db.scalar(select(func.count()).select_from(Unidade).where(*onde)) or 0
    itens = ctx.db.scalars(
        select(Unidade).where(*onde).order_by(comum.ordenar_por(_ORDEM, ordenar, direcao, "nome"), Unidade.id)
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    )
    return PaginaCad[UnidadeOut](itens=[_out(ctx.db, u) for u in itens], total=total, pagina=pagina, por_pagina=por_pagina,
                                 contagens=contagens)


@router.get("/{unidade_id}", response_model=UnidadeOut)
def ler(unidade_id: int, ctx: Ctx):
    return _out(ctx.db, _obter(ctx, unidade_id))


@router.post("", response_model=UnidadeOut, status_code=201)
def criar(dados: UnidadeIn, ctx: Ctx):
    if comum.duplicado(ctx.db, Unidade, Unidade.nome, dados.nome):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma unidade com este nome.")
    u = Unidade(**dados.model_dump(), codigo_legado=proximo_codigo(ctx.db, "unidade"))
    ctx.db.add(u)
    ctx.db.flush()
    ctx.auditar("unidade.criar", "unidade", u.id, descricao=u.nome, depois=audit.snapshot(u))
    ctx.db.commit()
    return _out(ctx.db, u)


@router.put("/{unidade_id}", response_model=UnidadeOut)
def alterar(unidade_id: int, dados: UnidadeIn, ctx: Ctx):
    u = _obter(ctx, unidade_id)
    if comum.duplicado(ctx.db, Unidade, Unidade.nome, dados.nome, exceto_id=u.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma unidade com este nome.")
    antes = audit.snapshot(u)
    for k, v in dados.model_dump().items():
        setattr(u, k, v)
    ctx.db.flush()
    a, d = audit.diff(antes, audit.snapshot(u))
    ctx.auditar("unidade.alterar", "unidade", u.id, descricao=u.nome, antes=a, depois=d)
    ctx.db.commit()
    return _out(ctx.db, u)


@router.get("/{unidade_id}/vinculos", response_model=VinculosOut)
def ver_vinculos(unidade_id: int, ctx: Ctx):
    _obter(ctx, unidade_id)
    return comum.vinculos_out(ctx.db, Unidade, unidade_id)


@router.delete("/{unidade_id}", response_model=Mensagem)
def excluir(unidade_id: int, ctx: Ctx):
    u = _obter(ctx, unidade_id)
    comum.bloquear_se_vinculado(ctx.db, Unidade, u.id, "a unidade")
    snap = audit.snapshot(u)
    nome = u.nome
    try:
        ctx.db.delete(u)
        ctx.auditar("unidade.excluir", "unidade", unidade_id, descricao=nome, antes=snap)
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível excluir a unidade: ela está em uso. Desative-a em vez de excluir.") from None
    return Mensagem(mensagem=f"Unidade {nome} excluída.")


comum.registrar_ativacao(router, modelo=Unidade, entidade="unidade", rotulo="unidade", saida=_out, modelo_saida=UnidadeOut)
