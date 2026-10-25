"""Tipos de serviço (`/api/cadastros/servicos`): Pilates, Fisioterapia, etc."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.modules.cadastros import comum
from app.modules.cadastros.comum import PaginaCad, Situacao, VinculosOut
from app.modules.cadastros.models import TipoServico, proximo_codigo

router = APIRouter(prefix="/cadastros/servicos", tags=["cadastros: tipos de serviço"])

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class ServicoIn(BaseModel):
    nome: Nome
    ativo: bool = True


class ServicoOut(Schema):
    id: int
    codigo: int | None
    nome: str
    ativo: bool


def _out(db, s: TipoServico) -> ServicoOut:
    return ServicoOut(id=s.id, codigo=s.codigo_legado, nome=s.nome, ativo=s.ativo)


def _obter(ctx, servico_id: int) -> TipoServico:
    s = ctx.db.get(TipoServico, servico_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tipo de serviço não encontrado.")
    return s


_ORDEM = {"nome": TipoServico.nome, "codigo": TipoServico.codigo_legado}


@router.get("", response_model=PaginaCad[ServicoOut])
def listar(
    ctx: Ctx,
    q: str | None = None,
    situacao: Situacao = "todos",
    ordenar: str | None = None,
    direcao: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
):
    filtros = [TipoServico.nome.ilike(comum.like(q), escape="\\")] if q and q.strip() else []
    contagens = comum.contar_situacoes(ctx.db, TipoServico.id, TipoServico.ativo, filtros)
    sit = comum.filtro_situacao(TipoServico.ativo, situacao)
    onde = filtros + ([sit] if sit is not None else [])
    total = ctx.db.scalar(select(func.count()).select_from(TipoServico).where(*onde)) or 0
    itens = ctx.db.scalars(
        select(TipoServico).where(*onde).order_by(comum.ordenar_por(_ORDEM, ordenar, direcao, "nome"), TipoServico.id)
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    )
    return PaginaCad[ServicoOut](itens=[_out(ctx.db, s) for s in itens], total=total, pagina=pagina, por_pagina=por_pagina,
                                 contagens=contagens)


@router.get("/{servico_id}", response_model=ServicoOut)
def ler(servico_id: int, ctx: Ctx):
    return _out(ctx.db, _obter(ctx, servico_id))


@router.post("", response_model=ServicoOut, status_code=201)
def criar(dados: ServicoIn, ctx: Ctx):
    if comum.duplicado(ctx.db, TipoServico, TipoServico.nome, dados.nome):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um tipo de serviço com este nome.")
    s = TipoServico(**dados.model_dump(), codigo_legado=proximo_codigo(ctx.db, "tipo_servico"))
    ctx.db.add(s)
    ctx.db.flush()
    ctx.auditar("servico.criar", "tipo_servico", s.id, descricao=s.nome, depois=audit.snapshot(s))
    ctx.db.commit()
    return _out(ctx.db, s)


@router.put("/{servico_id}", response_model=ServicoOut)
def alterar(servico_id: int, dados: ServicoIn, ctx: Ctx):
    s = _obter(ctx, servico_id)
    if comum.duplicado(ctx.db, TipoServico, TipoServico.nome, dados.nome, exceto_id=s.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um tipo de serviço com este nome.")
    antes = audit.snapshot(s)
    for k, v in dados.model_dump().items():
        setattr(s, k, v)
    ctx.db.flush()
    a, d = audit.diff(antes, audit.snapshot(s))
    ctx.auditar("servico.alterar", "tipo_servico", s.id, descricao=s.nome, antes=a, depois=d)
    ctx.db.commit()
    return _out(ctx.db, s)


@router.get("/{servico_id}/vinculos", response_model=VinculosOut)
def ver_vinculos(servico_id: int, ctx: Ctx):
    _obter(ctx, servico_id)
    return comum.vinculos_out(ctx.db, TipoServico, servico_id)


@router.delete("/{servico_id}", response_model=Mensagem)
def excluir(servico_id: int, ctx: Ctx):
    s = _obter(ctx, servico_id)
    comum.bloquear_se_vinculado(ctx.db, TipoServico, s.id, "o tipo de serviço")
    snap, nome = audit.snapshot(s), s.nome
    try:
        ctx.db.delete(s)
        ctx.auditar("servico.excluir", "tipo_servico", servico_id, descricao=nome, antes=snap)
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível excluir o tipo de serviço: ele está em uso. Desative-o em vez de excluir.") from None
    return Mensagem(mensagem=f"Tipo de serviço {nome} excluído.")


comum.registrar_ativacao(router, modelo=TipoServico, entidade="servico", rotulo="tipo de serviço", saida=_out, modelo_saida=ServicoOut)
