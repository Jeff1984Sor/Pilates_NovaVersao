"""Categorias (RECEITA/DESPESA) e subcategorias. Exclusão bloqueada, com explicação, quando há vínculos."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select

from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.modules.cadastros.models import Categoria, Plano, Subcategoria, TipoCategoria, proximo_codigo
from app.modules.cadastros.util_docs import (
    SITUACAO,
    PaginaContagens,
    Pedido,
    Texto,
    contem,
    filtrar_situacao,
    foto,
    nao_encontrado,
    ordem,
    pagina_de,
    parametros_lista,
    plural,
)
from app.modules.financeiro.models import ContaPagar

router = APIRouter(prefix="/cadastros/categorias", tags=["cadastros: categorias"])


# ------------------------------------------------------------------------------------------------ esquemas
class CategoriaIn(Schema):
    nome: Texto = Field(min_length=2, max_length=120)
    tipo: TipoCategoria


class CategoriaOut(Schema):
    id: int
    codigo: int | None
    nome: str
    tipo: TipoCategoria
    ativo: bool
    subcategorias: int
    contas_a_pagar: int
    planos: int
    criado_em: datetime | None = None


class SubcategoriaIn(Schema):
    categoria_id: int
    nome: Texto = Field(min_length=2, max_length=120)


class SubcategoriaOut(Schema):
    id: int
    codigo: int | None
    categoria_id: int
    categoria_nome: str
    categoria_tipo: TipoCategoria
    nome: str
    ativo: bool
    contas_a_pagar: int
    planos: int


# ------------------------------------------------------------------------------------------------ contagens
def _n_subs():
    return select(func.count(Subcategoria.id)).where(Subcategoria.categoria_id == Categoria.id).correlate(Categoria).scalar_subquery()


def _n_contas_cat():
    return select(func.count(ContaPagar.id)).where(ContaPagar.categoria_id == Categoria.id).correlate(Categoria).scalar_subquery()


def _n_planos_cat():
    return (
        select(func.count(Plano.id)).where(Plano.categoria_receita_id == Categoria.id).correlate(Categoria).scalar_subquery()
    )


def _n_contas_sub():
    return (
        select(func.count(ContaPagar.id)).where(ContaPagar.subcategoria_id == Subcategoria.id).correlate(Subcategoria).scalar_subquery()
    )


def _n_planos_sub():
    return (
        select(func.count(Plano.id)).where(Plano.subcategoria_receita_id == Subcategoria.id).correlate(Subcategoria).scalar_subquery()
    )


def _cat_out(c: Categoria, subs: int, contas: int, planos: int) -> CategoriaOut:
    return CategoriaOut(
        id=c.id, codigo=c.codigo_legado, nome=c.nome, tipo=c.tipo, ativo=c.ativo, subcategorias=subs, contas_a_pagar=contas,
        planos=planos, criado_em=c.criado_em,
    )


def _sub_out(s: Subcategoria, c: Categoria, contas: int, planos: int) -> SubcategoriaOut:
    return SubcategoriaOut(
        id=s.id, codigo=s.codigo_legado, categoria_id=c.id, categoria_nome=c.nome, categoria_tipo=c.tipo,
        nome=s.nome, ativo=s.ativo, contas_a_pagar=contas, planos=planos,
    )


def _categoria_out(ctx, c: Categoria) -> CategoriaOut:
    subs, contas, planos = ctx.db.execute(select(_n_subs(), _n_contas_cat(), _n_planos_cat()).where(Categoria.id == c.id)).one()
    return _cat_out(c, subs, contas, planos)


def _subcategoria_out(ctx, s: Subcategoria) -> SubcategoriaOut:
    c = ctx.db.get(Categoria, s.categoria_id)
    contas, planos = ctx.db.execute(select(_n_contas_sub(), _n_planos_sub()).where(Subcategoria.id == s.id)).one()
    return _sub_out(s, c, contas, planos)


# ------------------------------------------------------------------------------------------------ subcategorias
# (declaradas antes das rotas /{cid}, senão "subcategorias" seria lido como id)
@router.get("/subcategorias", response_model=PaginaContagens[SubcategoriaOut])
def listar_subcategorias(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    categoria_id: Annotated[int | None, Query()] = None,
    tipo: Annotated[TipoCategoria | None, Query()] = None,
    situacao: SITUACAO = "todos",
    somente_ativos: Annotated[bool, Query()] = False,
):
    """Chips por tipo e situação da categoria (contagens só com a busca/categoria, sem o filtro de tipo)."""
    base = select(Subcategoria, Categoria, _n_contas_sub().label("contas"), _n_planos_sub().label("planos")).join(
        Categoria, Subcategoria.categoria_id == Categoria.id
    )
    if pedido.q:
        base = base.where(contem(Subcategoria.nome, pedido.q) | contem(Categoria.nome, pedido.q))
    if categoria_id:
        base = base.where(Subcategoria.categoria_id == categoria_id)
    contagens = {"todos": 0, "RECEITA": 0, "DESPESA": 0, "ativos": 0, "inativos": 0}
    for s, c, _a, _b in ctx.db.execute(base).all():
        contagens["todos"] += 1
        contagens[c.tipo.value] += 1
        contagens["ativos" if s.ativo else "inativos"] += 1
    stmt = base.where(Categoria.tipo == tipo) if tipo else base
    stmt = filtrar_situacao(stmt, Subcategoria.ativo, situacao, somente_ativos)
    if somente_ativos:  # seletor: subcategoria de categoria inativa também não é oferecida
        stmt = stmt.where(Categoria.ativo.is_(True))
    colunas = {
        "nome": func.lower(Subcategoria.nome), "categoria": func.lower(Categoria.nome), "codigo": Subcategoria.codigo_legado,
    }
    stmt = stmt.order_by(ordem(pedido, colunas, "categoria"), func.lower(Subcategoria.nome), Subcategoria.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=[_sub_out(s, c, a, b) for s, c, a, b in linhas], total=total, pagina=pedido.pagina,
        por_pagina=pedido.por_pagina, contagens=contagens,
    )


def _buscar_sub(ctx, sid: int) -> Subcategoria:
    s = ctx.db.get(Subcategoria, sid)
    if not s:
        raise nao_encontrado("Subcategoria")
    return s


def _categoria_existente(ctx, cid: int) -> Categoria:
    c = ctx.db.get(Categoria, cid)
    if not c:
        raise HTTPException(422, "Escolha uma categoria existente.")
    return c


def _checar_nome_sub(ctx, categoria_id: int, nome: str, exceto: int | None = None) -> None:
    q = select(Subcategoria.id).where(
        Subcategoria.categoria_id == categoria_id, func.lower(Subcategoria.nome) == nome.lower(), Subcategoria.id != (exceto or 0)
    )
    if ctx.db.scalar(q):
        raise HTTPException(409, "Já existe uma subcategoria com este nome nesta categoria.")


@router.post("/subcategorias", response_model=SubcategoriaOut, status_code=201)
def criar_subcategoria(dados: SubcategoriaIn, ctx: Ctx):
    cat = _categoria_existente(ctx, dados.categoria_id)
    if not cat.ativo:
        raise HTTPException(409, "Esta categoria está inativa. Reative-a antes de criar subcategorias nela.")
    _checar_nome_sub(ctx, cat.id, dados.nome)
    s = Subcategoria(categoria_id=cat.id, nome=dados.nome, codigo_legado=proximo_codigo(ctx.db, "subcategoria"))
    ctx.db.add(s)
    ctx.db.flush()
    ctx.auditar("subcategoria.criar", "subcategoria", s.id, descricao=f"{cat.nome} > {s.nome}", depois=foto(s))
    ctx.db.commit()
    return _subcategoria_out(ctx, s)


@router.put("/subcategorias/{sid}", response_model=SubcategoriaOut)
def alterar_subcategoria(sid: int, dados: SubcategoriaIn, ctx: Ctx):
    s = _buscar_sub(ctx, sid)
    cat = _categoria_existente(ctx, dados.categoria_id)
    _checar_nome_sub(ctx, cat.id, dados.nome, exceto=sid)
    uso = _subcategoria_out(ctx, s)
    if cat.id != s.categoria_id and (uso.contas_a_pagar or uso.planos):
        raise HTTPException(
            409,
            "Esta subcategoria já está em uso (contas a pagar ou planos); não dá para mudá-la de categoria. "
            "Crie outra subcategoria na categoria desejada.",
        )
    antes = foto(s)
    s.categoria_id, s.nome = cat.id, dados.nome
    ctx.db.flush()
    ctx.auditar("subcategoria.alterar", "subcategoria", s.id, descricao=f"{cat.nome} > {s.nome}", antes=antes, depois=foto(s))
    ctx.db.commit()
    return _subcategoria_out(ctx, s)


@router.patch("/subcategorias/{sid}/ativo", response_model=SubcategoriaOut)
def ativar_subcategoria(sid: int, ctx: Ctx, ativo: Annotated[bool, Query()]):
    s = _buscar_sub(ctx, sid)
    if s.ativo != ativo:
        s.ativo = ativo
        ctx.auditar("subcategoria.reativar" if ativo else "subcategoria.inativar", "subcategoria", s.id, descricao=s.nome)
        ctx.db.commit()
    return _subcategoria_out(ctx, s)


@router.delete("/subcategorias/{sid}", response_model=Mensagem)
def excluir_subcategoria(sid: int, ctx: Ctx):
    s = _buscar_sub(ctx, sid)
    uso = _subcategoria_out(ctx, s)
    if uso.contas_a_pagar or uso.planos:
        partes = []
        if uso.contas_a_pagar:
            partes.append(plural(uso.contas_a_pagar, "conta a pagar", "contas a pagar"))
        if uso.planos:
            partes.append(plural(uso.planos, "plano", "planos"))
        raise HTTPException(
            409, f"Não é possível excluir: a subcategoria {s.nome} está em uso por {' e '.join(partes)}. Inative-a para não usá-la mais."
        )
    antes = foto(s)
    ctx.db.delete(s)
    ctx.auditar("subcategoria.excluir", "subcategoria", sid, descricao=s.nome, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Subcategoria excluída.")


# ------------------------------------------------------------------------------------------------ categorias
def _buscar(ctx, cid: int) -> Categoria:
    c = ctx.db.get(Categoria, cid)
    if not c:
        raise nao_encontrado("Categoria")
    return c


def _checar_nome(ctx, nome: str, tipo: TipoCategoria, exceto: int | None = None) -> None:
    q = select(Categoria.id).where(
        func.lower(Categoria.nome) == nome.lower(), Categoria.tipo == tipo, Categoria.id != (exceto or 0)
    )
    if ctx.db.scalar(q):
        raise HTTPException(409, f"Já existe uma categoria de {tipo.value.lower()} com este nome.")


@router.get("", response_model=PaginaContagens[CategoriaOut])
def listar(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    tipo: Annotated[TipoCategoria | None, Query()] = None,
    situacao: SITUACAO = "todos",
    somente_ativos: Annotated[bool, Query()] = False,
):
    base = select(Categoria, _n_subs().label("subs"), _n_contas_cat().label("contas"), _n_planos_cat().label("planos"))
    if pedido.q:
        base = base.where(contem(Categoria.nome, pedido.q))
    contagens = {"todos": 0, "RECEITA": 0, "DESPESA": 0, "ativos": 0, "inativos": 0}
    for c, *_ in ctx.db.execute(base).all():
        contagens["todos"] += 1
        contagens[c.tipo.value] += 1
        contagens["ativos" if c.ativo else "inativos"] += 1
    stmt = base.where(Categoria.tipo == tipo) if tipo else base
    stmt = filtrar_situacao(stmt, Categoria.ativo, situacao, somente_ativos)
    colunas = {"nome": func.lower(Categoria.nome), "tipo": Categoria.tipo, "codigo": Categoria.codigo_legado}
    stmt = stmt.order_by(ordem(pedido, colunas, "nome"), Categoria.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=[_cat_out(c, a, b, d) for c, a, b, d in linhas], total=total, pagina=pedido.pagina,
        por_pagina=pedido.por_pagina, contagens=contagens,
    )


@router.get("/{cid}", response_model=CategoriaOut)
def ler(cid: int, ctx: Ctx):
    return _categoria_out(ctx, _buscar(ctx, cid))


@router.post("", response_model=CategoriaOut, status_code=201)
def criar(dados: CategoriaIn, ctx: Ctx):
    _checar_nome(ctx, dados.nome, dados.tipo)
    c = Categoria(nome=dados.nome, tipo=dados.tipo, codigo_legado=proximo_codigo(ctx.db, "categoria"))
    ctx.db.add(c)
    ctx.db.flush()
    ctx.auditar("categoria.criar", "categoria", c.id, descricao=f"{c.nome} ({c.tipo.value})", depois=foto(c))
    ctx.db.commit()
    return _categoria_out(ctx, c)


@router.put("/{cid}", response_model=CategoriaOut)
def alterar(cid: int, dados: CategoriaIn, ctx: Ctx):
    c = _buscar(ctx, cid)
    _checar_nome(ctx, dados.nome, dados.tipo, exceto=cid)
    uso = _categoria_out(ctx, c)
    if dados.tipo != c.tipo and (uso.contas_a_pagar or uso.planos):
        raise HTTPException(
            409,
            "Não dá para trocar o tipo desta categoria: ela já está em uso por "
            f"{plural(uso.contas_a_pagar, 'conta a pagar', 'contas a pagar')} e {plural(uso.planos, 'plano', 'planos')}. "
            "Crie outra categoria com o tipo desejado.",
        )
    antes = foto(c)
    c.nome, c.tipo = dados.nome, dados.tipo
    ctx.db.flush()
    ctx.auditar("categoria.alterar", "categoria", c.id, descricao=c.nome, antes=antes, depois=foto(c))
    ctx.db.commit()
    return _categoria_out(ctx, c)


@router.patch("/{cid}/ativo", response_model=CategoriaOut)
def ativar(cid: int, ctx: Ctx, ativo: Annotated[bool, Query()]):
    """Inativar a categoria não mexe nas subcategorias: elas só deixam de ser oferecidas enquanto ela estiver inativa."""
    c = _buscar(ctx, cid)
    if c.ativo != ativo:
        c.ativo = ativo
        ctx.auditar("categoria.reativar" if ativo else "categoria.inativar", "categoria", c.id, descricao=c.nome)
        ctx.db.commit()
    return _categoria_out(ctx, c)


@router.delete("/{cid}", response_model=Mensagem)
def excluir(cid: int, ctx: Ctx):
    c = _buscar(ctx, cid)
    uso = _categoria_out(ctx, c)
    partes = []
    if uso.subcategorias:
        partes.append(plural(uso.subcategorias, "subcategoria", "subcategorias"))
    if uso.contas_a_pagar:
        partes.append(plural(uso.contas_a_pagar, "conta a pagar", "contas a pagar"))
    if uso.planos:
        partes.append(plural(uso.planos, "plano", "planos"))
    if partes:
        raise HTTPException(
            409,
            f"Não é possível excluir: a categoria {c.nome} tem {', '.join(partes)}. "
            "Exclua ou mova os vínculos antes, ou apenas inative a categoria.",
        )
    antes = foto(c)
    ctx.db.delete(c)
    ctx.auditar("categoria.excluir", "categoria", cid, descricao=c.nome, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Categoria excluída.")
