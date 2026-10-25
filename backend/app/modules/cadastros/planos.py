"""Planos (`/api/planos`): valor MENSAL, aulas por semana, duração e receita; duplicar, ativar/desativar.

O valor por aula mostrado na tela vem de `app.domain.precos.precificar_contrato` (regra R1):
`valor_aula = valor_mensal / (aulas_por_semana x 4)` arredondado meio para cima; `None` sem aulas por semana.
O prefixo da rota é `/planos` (recurso de permissão `planos`), não `/cadastros/planos`.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.domain.precos import precificar_contrato
from app.modules.cadastros import comum
from app.modules.cadastros.comum import PaginaCad, Situacao, VinculosOut
from app.modules.cadastros.models import (
    Categoria,
    ModeloContrato,
    Plano,
    Recorrencia,
    Subcategoria,
    TipoCategoria,
    TipoServico,
    proximo_codigo,
)

router = APIRouter(prefix="/planos", tags=["planos"])

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


class PlanoIn(BaseModel):
    nome: Nome
    tipo_servico_id: int
    valor: Decimal = Field(ge=0, le=Decimal("9999999.99"), decimal_places=2, description="Valor MENSAL")
    aulas_por_semana: int = Field(default=1, ge=0, le=14)
    duracao_meses: int = Field(default=1, ge=1, le=120)
    recorrencia: Recorrencia = Recorrencia.MENSAL
    is_avulso: bool = False
    categoria_receita_id: int | None = None
    subcategoria_receita_id: int | None = None
    modelo_contrato_id: int | None = None
    ativo: bool = True


class PlanoOut(Schema):
    id: int
    codigo: int | None
    nome: str
    tipo_servico_id: int
    tipo_servico_nome: str | None
    valor: Decimal
    aulas_por_semana: int
    duracao_meses: int
    recorrencia: Recorrencia
    is_avulso: bool
    categoria_receita_id: int | None
    categoria_receita_nome: str | None
    subcategoria_receita_id: int | None
    subcategoria_receita_nome: str | None
    modelo_contrato_id: int | None
    modelo_contrato_nome: str | None
    ativo: bool
    valor_aula: Decimal | None  # R1
    valor_total: Decimal  # valor mensal x max(duração, 1)


def _out(db, p: Plano) -> PlanoOut:
    preco = precificar_contrato(p.valor, p.aulas_por_semana, p.duracao_meses)
    tipo = db.get(TipoServico, p.tipo_servico_id)
    cat = db.get(Categoria, p.categoria_receita_id) if p.categoria_receita_id else None
    sub = db.get(Subcategoria, p.subcategoria_receita_id) if p.subcategoria_receita_id else None
    mod = db.get(ModeloContrato, p.modelo_contrato_id) if p.modelo_contrato_id else None
    return PlanoOut(
        id=p.id, codigo=p.codigo_legado, nome=p.nome, tipo_servico_id=p.tipo_servico_id,
        tipo_servico_nome=tipo.nome if tipo else None, valor=p.valor, aulas_por_semana=p.aulas_por_semana,
        duracao_meses=p.duracao_meses, recorrencia=p.recorrencia, is_avulso=p.avulso,
        categoria_receita_id=p.categoria_receita_id, categoria_receita_nome=cat.nome if cat else None,
        subcategoria_receita_id=p.subcategoria_receita_id, subcategoria_receita_nome=sub.nome if sub else None,
        modelo_contrato_id=p.modelo_contrato_id, modelo_contrato_nome=mod.nome if mod else None, ativo=p.ativo,
        valor_aula=preco.valor_aula, valor_total=preco.valor_total)


def _obter(ctx, plano_id: int) -> Plano:
    p = ctx.db.get(Plano, plano_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano não encontrado.")
    return p


def _validar_referencias(ctx, dados: PlanoIn) -> None:
    """Existência do serviço/categoria/modelo e coerência categoria x subcategoria (só receita)."""
    db = ctx.db
    if not db.get(TipoServico, dados.tipo_servico_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escolha um tipo de serviço válido.")
    if dados.categoria_receita_id:
        cat = db.get(Categoria, dados.categoria_receita_id)
        if not cat or cat.tipo != TipoCategoria.RECEITA:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A categoria de receita informada não existe ou não é de receita.")
    if dados.subcategoria_receita_id:
        sub = db.get(Subcategoria, dados.subcategoria_receita_id)
        pai = db.get(Categoria, sub.categoria_id) if sub else None
        if not sub or not pai or pai.tipo != TipoCategoria.RECEITA:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A subcategoria de receita informada não existe ou não é de receita.")
        if dados.categoria_receita_id and sub.categoria_id != dados.categoria_receita_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A subcategoria não pertence à categoria escolhida.")
    if dados.modelo_contrato_id and not db.get(ModeloContrato, dados.modelo_contrato_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "O modelo de contrato informado não existe.")


def _valores(dados: PlanoIn, db) -> dict:
    v = dados.model_dump()
    v["avulso"] = v.pop("is_avulso")
    if v["subcategoria_receita_id"] and not v["categoria_receita_id"]:
        v["categoria_receita_id"] = db.get(Subcategoria, v["subcategoria_receita_id"]).categoria_id
    return v


_ORDEM = {"nome": Plano.nome, "valor": Plano.valor, "aulas": Plano.aulas_por_semana, "duracao": Plano.duracao_meses,
          "codigo": Plano.codigo_legado}


@router.get("/opcoes")
def opcoes(ctx: Ctx):
    """Listas para o formulário do plano: serviços ativos, categorias/subcategorias de receita e modelos de contrato ativos."""
    db = ctx.db
    categorias = db.scalars(select(Categoria).where(Categoria.tipo == TipoCategoria.RECEITA).order_by(Categoria.nome)).all()
    subs = db.scalars(select(Subcategoria).where(Subcategoria.categoria_id.in_([c.id for c in categorias] or [0])).order_by(Subcategoria.nome)).all()
    return {
        "tipos_servico": [{"id": s.id, "nome": s.nome, "ativo": s.ativo}
                          for s in db.scalars(select(TipoServico).order_by(TipoServico.nome))],
        "categorias_receita": [{"id": c.id, "nome": c.nome} for c in categorias],
        "subcategorias_receita": [{"id": s.id, "nome": s.nome, "categoria_id": s.categoria_id} for s in subs],
        "modelos_contrato": [{"id": m.id, "nome": m.nome, "ativo": m.ativo}
                             for m in db.scalars(select(ModeloContrato).order_by(ModeloContrato.nome))],
    }


@router.get("", response_model=PaginaCad[PlanoOut])
def listar(
    ctx: Ctx,
    q: str | None = None,
    situacao: Situacao = "todos",
    tipo: Annotated[str, Query(pattern="^(todos|avulso|mensal)$", description="avulso = aulas avulsas; mensal = planos de contrato")] = "todos",
    tipo_servico_id: int | None = None,
    ordenar: str | None = None,
    direcao: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
):
    filtros = []
    if q and q.strip():
        like = comum.like(q)
        filtros.append(or_(Plano.nome.ilike(like, escape="\\")))
    if tipo == "avulso":
        filtros.append(Plano.avulso.is_(True))
    elif tipo == "mensal":
        filtros.append(Plano.avulso.is_(False))
    if tipo_servico_id:
        filtros.append(Plano.tipo_servico_id == tipo_servico_id)
    contagens = comum.contar_situacoes(ctx.db, Plano.id, Plano.ativo, filtros)
    sit = comum.filtro_situacao(Plano.ativo, situacao)
    onde = filtros + ([sit] if sit is not None else [])
    total = ctx.db.scalar(select(func.count()).select_from(Plano).where(*onde)) or 0
    itens = ctx.db.scalars(
        select(Plano).where(*onde).order_by(comum.ordenar_por(_ORDEM, ordenar, direcao, "nome"), Plano.id)
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    )
    return PaginaCad[PlanoOut](itens=[_out(ctx.db, p) for p in itens], total=total, pagina=pagina, por_pagina=por_pagina,
                               contagens=contagens)


@router.get("/{plano_id}", response_model=PlanoOut)
def ler(plano_id: int, ctx: Ctx):
    return _out(ctx.db, _obter(ctx, plano_id))


@router.post("", response_model=PlanoOut, status_code=201)
def criar(dados: PlanoIn, ctx: Ctx):
    if comum.duplicado(ctx.db, Plano, Plano.nome, dados.nome):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um plano com este nome.")
    _validar_referencias(ctx, dados)
    p = Plano(**_valores(dados, ctx.db), codigo_legado=proximo_codigo(ctx.db, "plano"))
    ctx.db.add(p)
    ctx.db.flush()
    ctx.auditar("plano.criar", "plano", p.id, descricao=p.nome, depois=audit.snapshot(p))
    ctx.db.commit()
    return _out(ctx.db, p)


@router.put("/{plano_id}", response_model=PlanoOut)
def alterar(plano_id: int, dados: PlanoIn, ctx: Ctx):
    p = _obter(ctx, plano_id)
    if comum.duplicado(ctx.db, Plano, Plano.nome, dados.nome, exceto_id=p.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um plano com este nome.")
    _validar_referencias(ctx, dados)
    antes = audit.snapshot(p)
    for k, v in _valores(dados, ctx.db).items():
        setattr(p, k, v)
    ctx.db.flush()
    a, d = audit.diff(antes, audit.snapshot(p))
    ctx.auditar("plano.alterar", "plano", p.id, descricao=p.nome, antes=a, depois=d)
    ctx.db.commit()
    return _out(ctx.db, p)


@router.post("/{plano_id}/duplicar", response_model=PlanoOut, status_code=201)
def duplicar(plano_id: int, ctx: Ctx):
    """Cópia do plano com o nome "<nome> (cópia)" ("(cópia 2)"... se já existir) e um novo código de negócio."""
    base = _obter(ctx, plano_id)
    limite = 120
    sufixo, n = " (cópia)", 2
    nome = f"{base.nome[: limite - len(sufixo)]}{sufixo}"
    while comum.duplicado(ctx.db, Plano, Plano.nome, nome):
        sufixo = f" (cópia {n})"
        nome, n = f"{base.nome[: limite - len(sufixo)]}{sufixo}", n + 1
    nova = Plano(
        nome=nome, tipo_servico_id=base.tipo_servico_id, categoria_receita_id=base.categoria_receita_id,
        subcategoria_receita_id=base.subcategoria_receita_id, modelo_contrato_id=base.modelo_contrato_id,
        valor=base.valor, aulas_por_semana=base.aulas_por_semana, duracao_meses=base.duracao_meses,
        recorrencia=base.recorrencia, avulso=base.avulso, ativo=base.ativo, codigo_legado=proximo_codigo(ctx.db, "plano"))
    ctx.db.add(nova)
    ctx.db.flush()
    ctx.auditar("plano.duplicar", "plano", nova.id, descricao=f"{nova.nome} (a partir de {base.nome})", depois=audit.snapshot(nova))
    ctx.db.commit()
    return _out(ctx.db, nova)


@router.get("/{plano_id}/vinculos", response_model=VinculosOut)
def ver_vinculos(plano_id: int, ctx: Ctx):
    _obter(ctx, plano_id)
    return comum.vinculos_out(ctx.db, Plano, plano_id)


@router.delete("/{plano_id}", response_model=Mensagem)
def excluir(plano_id: int, ctx: Ctx):
    p = _obter(ctx, plano_id)
    comum.bloquear_se_vinculado(ctx.db, Plano, p.id, "o plano")
    snap, nome = audit.snapshot(p), p.nome
    try:
        ctx.db.delete(p)
        ctx.auditar("plano.excluir", "plano", plano_id, descricao=nome, antes=snap)
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível excluir o plano: ele está em uso. Desative-o em vez de excluir.") from None
    return Mensagem(mensagem=f"Plano {nome} excluído.")


comum.registrar_ativacao(router, modelo=Plano, entidade="plano", rotulo="plano", saida=_out, modelo_saida=PlanoOut)
