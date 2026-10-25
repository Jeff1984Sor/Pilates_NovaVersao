"""Termos de uso (termo de imagem): HTML com variáveis do aluno, sanitizado, com pré-visualização e duplicação."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select

from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.domain import modelos_documento as md
from app.modules.alunos.models import Aluno
from app.modules.cadastros import html_seguro
from app.modules.cadastros.modelos_documentos import (
    PreviaIn,
    PreviaOut,
    VariavelOut,
    nome_da_copia,
    previa,
    sanear_ou_422,
    variaveis_out,
)
from app.modules.cadastros.models import TermoUso, proximo_codigo
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

router = APIRouter(prefix="/cadastros/termos", tags=["cadastros: termos"])

ESCOPO = md.ESCOPO_TERMO


class TermoIn(Schema):
    nome: Texto = Field(min_length=2, max_length=80)
    conteudo_html: str = Field(min_length=1)
    ativo: bool = True


class TermoLista(Schema):
    id: int
    codigo: int | None
    nome: str
    ativo: bool
    previa: str
    alunos_com_aceite: int
    atualizado_em: datetime | None = None


class TermoOut(TermoLista):
    conteudo_html: str
    variaveis_usadas: list[str]
    variaveis_desconhecidas: list[str]


def _alunos():
    return select(func.count(Aluno.id)).where(Aluno.termo_uso_id == TermoUso.id).correlate(TermoUso).scalar_subquery()


def _lista(t: TermoUso, alunos: int) -> TermoLista:
    return TermoLista(
        id=t.id, codigo=t.codigo_legado, nome=t.nome, ativo=t.ativo, previa=html_seguro.texto_puro(t.conteudo_html),
        alunos_com_aceite=alunos, atualizado_em=t.atualizado_em,
    )


def _detalhe(ctx, t: TermoUso) -> TermoOut:
    alunos = ctx.db.scalar(select(func.count(Aluno.id)).where(Aluno.termo_uso_id == t.id)) or 0
    return TermoOut(
        **_lista(t, alunos).model_dump(), conteudo_html=t.conteudo_html,
        variaveis_usadas=md.variaveis_usadas(t.conteudo_html),
        variaveis_desconhecidas=md.variaveis_desconhecidas(t.conteudo_html, ESCOPO),
    )


def _termo(ctx, tid: int) -> TermoUso:
    t = ctx.db.get(TermoUso, tid)
    if not t:
        raise nao_encontrado("Termo")
    return t


def _checar_nome(ctx, nome: str, exceto: int | None = None) -> None:
    q = select(TermoUso.id).where(func.lower(TermoUso.nome) == nome.lower(), TermoUso.id != (exceto or 0))
    if ctx.db.scalar(q):
        raise HTTPException(409, "Já existe um termo com este nome.")


@router.get("/variaveis", response_model=list[VariavelOut])
def variaveis(ctx: Ctx):
    """Só as variáveis que o termo conhece (aluno, endereço e data); as de contrato ficam de fora."""
    return variaveis_out(ESCOPO)


@router.post("/previa", response_model=PreviaOut)
def previa_termo(dados: PreviaIn, ctx: Ctx):
    return previa(dados.conteudo_html, ESCOPO)


@router.get("", response_model=PaginaContagens[TermoLista])
def listar(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    situacao: SITUACAO = "todos",
    somente_ativos: Annotated[bool, Query()] = False,
):
    base = select(TermoUso, _alunos().label("alunos"))
    if pedido.q:
        base = base.where(contem(TermoUso.nome, pedido.q))
    contagens = {"todos": 0, "ativos": 0, "inativos": 0}
    for termo, _a in ctx.db.execute(base).all():
        contagens["todos"] += 1
        contagens["ativos" if termo.ativo else "inativos"] += 1
    base = filtrar_situacao(base, TermoUso.ativo, situacao, somente_ativos)
    colunas = {
        "nome": func.lower(TermoUso.nome), "codigo": TermoUso.codigo_legado, "atualizado": TermoUso.atualizado_em,
        "alunos": _alunos(),
    }
    stmt = base.order_by(ordem(pedido, colunas, "nome"), TermoUso.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=[_lista(t, a) for t, a in linhas], total=total, pagina=pedido.pagina, por_pagina=pedido.por_pagina,
        contagens=contagens,
    )


@router.get("/{tid}", response_model=TermoOut)
def ler(tid: int, ctx: Ctx):
    return _detalhe(ctx, _termo(ctx, tid))


@router.post("", response_model=TermoOut, status_code=201)
def criar(dados: TermoIn, ctx: Ctx):
    _checar_nome(ctx, dados.nome)
    t = TermoUso(
        nome=dados.nome, conteudo_html=sanear_ou_422(dados.conteudo_html), ativo=dados.ativo, codigo_legado=proximo_codigo(ctx.db, "termo_uso")
    )
    ctx.db.add(t)
    ctx.db.flush()
    ctx.auditar("termo.criar", "termo_uso", t.id, descricao=t.nome, depois=foto(t, ("conteudo_html",)))
    ctx.db.commit()
    return _detalhe(ctx, t)


@router.put("/{tid}", response_model=TermoOut)
def alterar(tid: int, dados: TermoIn, ctx: Ctx):
    t = _termo(ctx, tid)
    _checar_nome(ctx, dados.nome, exceto=tid)
    novo = sanear_ou_422(dados.conteudo_html)
    antes = foto(t, ("conteudo_html",))
    t.nome, t.conteudo_html, t.ativo = dados.nome, novo, dados.ativo
    ctx.db.flush()
    ctx.auditar("termo.alterar", "termo_uso", t.id, descricao=t.nome, antes=antes, depois=foto(t, ("conteudo_html",)))
    ctx.db.commit()
    return _detalhe(ctx, t)


@router.post("/{tid}/duplicar", response_model=TermoOut, status_code=201)
def duplicar(tid: int, ctx: Ctx):
    o = _termo(ctx, tid)
    nomes = set(ctx.db.scalars(select(TermoUso.nome)))
    c = TermoUso(nome=nome_da_copia(nomes, o.nome, 80), conteudo_html=o.conteudo_html, codigo_legado=proximo_codigo(ctx.db, "termo_uso"))
    ctx.db.add(c)
    ctx.db.flush()
    ctx.auditar("termo.duplicar", "termo_uso", c.id, descricao=f"{o.nome} -> {c.nome}", depois=foto(c, ("conteudo_html",)))
    ctx.db.commit()
    return _detalhe(ctx, c)


@router.patch("/{tid}/ativo", response_model=TermoOut)
def ativar(tid: int, ctx: Ctx, ativo: Annotated[bool, Query()]):
    t = _termo(ctx, tid)
    if t.ativo != ativo:
        t.ativo = ativo
        ctx.auditar("termo.reativar" if ativo else "termo.inativar", "termo_uso", t.id, descricao=t.nome)
        ctx.db.commit()
    return _detalhe(ctx, t)


@router.delete("/{tid}", response_model=Mensagem)
def excluir(tid: int, ctx: Ctx):
    t = _termo(ctx, tid)
    alunos = ctx.db.scalar(select(func.count(Aluno.id)).where(Aluno.termo_uso_id == tid)) or 0
    if alunos:
        raise HTTPException(
            409,
            f"Não é possível excluir: {plural(alunos, 'aluno aceitou', 'alunos aceitaram')} o termo {t.nome}. "
            "O registro do aceite deve ser preservado: inative este termo e crie um novo para usar daqui para frente.",
        )
    antes = foto(t, ("conteudo_html",))
    ctx.db.delete(t)
    ctx.auditar("termo.excluir", "termo_uso", tid, descricao=t.nome, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Termo excluído.")
