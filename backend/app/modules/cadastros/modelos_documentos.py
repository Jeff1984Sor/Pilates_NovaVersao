"""Modelos de contrato e modelos de evolução (texto-base da gaveta de evolução da agenda).

O HTML do contrato passa pela allowlist de `html_seguro` antes de ir ao banco; as variáveis `{ALUNO_NOME}` etc. e a
renderização vêm de `app.domain.modelos_documento` (lista oficial, `renderizar`, `variaveis_desconhecidas`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select

from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.domain import modelos_documento as md
from app.modules.cadastros import html_seguro
from app.modules.cadastros.models import ModeloContrato, ModeloEvolucao, Plano, proximo_codigo
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

router = APIRouter(prefix="/cadastros/modelos", tags=["cadastros: modelos"])


# ------------------------------------------------------------------------------------------------ comum (HTML)
class VariavelOut(Schema):
    chave: str
    marcador: str
    descricao: str
    exemplo: str


class PreviaIn(Schema):
    conteudo_html: str = Field(max_length=html_seguro.TAMANHO_MAXIMO * 2)


class PreviaOut(Schema):
    html: str
    usadas: list[str]
    desconhecidas: list[str]


def variaveis_out(escopo: str) -> list[VariavelOut]:
    return [
        VariavelOut(chave=v.chave, marcador=v.marcador, descricao=v.descricao, exemplo=v.exemplo)
        for v in md.variaveis_do_escopo(escopo)
    ]


def sanear_ou_422(texto: str) -> str:
    """HTML sanitizado e obrigatoriamente com algum conteúdo."""
    try:
        limpo = html_seguro.sanitizar(texto)
    except html_seguro.HtmlGrandeDemais as e:
        raise HTTPException(422, str(e)) from e
    if not html_seguro.texto_puro(limpo, 5) and "<img" not in limpo and "<hr" not in limpo:
        raise HTTPException(422, "Escreva o texto do modelo.")
    return limpo


def previa(texto: str, escopo: str) -> PreviaOut:
    """Pré-visualização com dados de exemplo (nada é gravado)."""
    try:
        limpo = html_seguro.sanitizar(texto)
    except html_seguro.HtmlGrandeDemais as e:
        raise HTTPException(422, str(e)) from e
    return PreviaOut(
        html=md.renderizar(limpo, md.contexto_exemplo(escopo), escopo=escopo),
        usadas=md.variaveis_usadas(limpo),
        desconhecidas=md.variaveis_desconhecidas(limpo, escopo),
    )


def nome_da_copia(existentes: set[str], nome: str, limite: int) -> str:
    """"X (cópia)", "X (cópia 2)"... sem repetir um nome existente e sem passar do limite da coluna."""
    existentes_min = {e.lower() for e in existentes}
    for n in range(1, 1000):
        sufixo = " (cópia)" if n == 1 else f" (cópia {n})"
        candidato = nome[: limite - len(sufixo)].rstrip() + sufixo
        if candidato.lower() not in existentes_min:
            return candidato
    raise HTTPException(409, "Há cópias demais deste modelo; renomeie algumas.")


@router.get("/variaveis", response_model=list[VariavelOut])
def variaveis(ctx: Ctx, escopo: Annotated[str, Query(pattern="^(contrato|termo)$")] = "contrato"):
    return variaveis_out(escopo)


# ------------------------------------------------------------------------------------------------ contrato
class ModeloContratoIn(Schema):
    nome: Texto = Field(min_length=2, max_length=120)
    conteudo_html: str = Field(min_length=1)
    ativo: bool = True


class ModeloContratoLista(Schema):
    id: int
    codigo: int | None
    nome: str
    ativo: bool
    previa: str
    planos: int
    atualizado_em: datetime | None = None


class ModeloContratoOut(ModeloContratoLista):
    conteudo_html: str
    variaveis_usadas: list[str]
    variaveis_desconhecidas: list[str]


def _planos_do_modelo():
    return (
        select(func.count(Plano.id)).where(Plano.modelo_contrato_id == ModeloContrato.id).correlate(ModeloContrato).scalar_subquery()
    )


def _lista(m: ModeloContrato, planos: int) -> ModeloContratoLista:
    return ModeloContratoLista(
        id=m.id, codigo=m.codigo_legado, nome=m.nome, ativo=m.ativo, previa=html_seguro.texto_puro(m.conteudo_html),
        planos=planos, atualizado_em=m.atualizado_em,
    )


def _detalhe(ctx, m: ModeloContrato) -> ModeloContratoOut:
    planos = ctx.db.scalar(select(func.count(Plano.id)).where(Plano.modelo_contrato_id == m.id)) or 0
    base = _lista(m, planos)
    return ModeloContratoOut(
        **base.model_dump(), conteudo_html=m.conteudo_html, variaveis_usadas=md.variaveis_usadas(m.conteudo_html),
        variaveis_desconhecidas=md.variaveis_desconhecidas(m.conteudo_html),
    )


def _modelo(ctx, mid: int) -> ModeloContrato:
    m = ctx.db.get(ModeloContrato, mid)
    if not m:
        raise nao_encontrado("Modelo de contrato")
    return m


def _checar_nome_contrato(ctx, nome: str, exceto: int | None = None) -> None:
    q = select(ModeloContrato.id).where(func.lower(ModeloContrato.nome) == nome.lower(), ModeloContrato.id != (exceto or 0))
    if ctx.db.scalar(q):
        raise HTTPException(409, "Já existe um modelo de contrato com este nome.")


@router.get("/contrato", response_model=PaginaContagens[ModeloContratoLista])
def listar_contratos(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    situacao: Annotated[str, Query(pattern="^(todos|ativos|inativos)$")] = "todos",
):
    base = select(ModeloContrato, _planos_do_modelo().label("planos"))
    if pedido.q:
        base = base.where(contem(ModeloContrato.nome, pedido.q))
    contagens = {"todos": 0, "ativos": 0, "inativos": 0}
    for m, _p in ctx.db.execute(base).all():
        contagens["todos"] += 1
        contagens["ativos" if m.ativo else "inativos"] += 1
    stmt = base
    if situacao != "todos":
        stmt = stmt.where(ModeloContrato.ativo.is_(situacao == "ativos"))
    colunas = {
        "nome": func.lower(ModeloContrato.nome), "codigo": ModeloContrato.codigo_legado,
        "atualizado": ModeloContrato.atualizado_em, "planos": _planos_do_modelo(),
    }
    stmt = stmt.order_by(ordem(pedido, colunas, "nome"), ModeloContrato.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=[_lista(m, p) for m, p in linhas], total=total, pagina=pedido.pagina, por_pagina=pedido.por_pagina,
        contagens=contagens,
    )


@router.post("/contrato/previa", response_model=PreviaOut)
def previa_contrato(dados: PreviaIn, ctx: Ctx):
    return previa(dados.conteudo_html, md.ESCOPO_CONTRATO)


@router.get("/contrato/{mid}", response_model=ModeloContratoOut)
def ler_contrato(mid: int, ctx: Ctx):
    return _detalhe(ctx, _modelo(ctx, mid))


@router.post("/contrato", response_model=ModeloContratoOut, status_code=201)
def criar_contrato(dados: ModeloContratoIn, ctx: Ctx):
    _checar_nome_contrato(ctx, dados.nome)
    m = ModeloContrato(
        nome=dados.nome, conteudo_html=sanear_ou_422(dados.conteudo_html), ativo=dados.ativo,
        codigo_legado=proximo_codigo(ctx.db, "modelo_contrato"),
    )
    ctx.db.add(m)
    ctx.db.flush()
    ctx.auditar("modelo_contrato.criar", "modelo_contrato", m.id, descricao=m.nome, depois=foto(m, ("conteudo_html",)))
    ctx.db.commit()
    return _detalhe(ctx, m)


@router.put("/contrato/{mid}", response_model=ModeloContratoOut)
def alterar_contrato(mid: int, dados: ModeloContratoIn, ctx: Ctx):
    m = _modelo(ctx, mid)
    _checar_nome_contrato(ctx, dados.nome, exceto=mid)
    novo_html = sanear_ou_422(dados.conteudo_html)
    antes = foto(m, ("conteudo_html",))
    m.nome, m.conteudo_html, m.ativo = dados.nome, novo_html, dados.ativo
    ctx.db.flush()
    ctx.auditar("modelo_contrato.alterar", "modelo_contrato", m.id, descricao=m.nome, antes=antes, depois=foto(m, ("conteudo_html",)))
    ctx.db.commit()
    return _detalhe(ctx, m)


@router.patch("/contrato/{mid}/ativo", response_model=ModeloContratoOut)
def ativar_contrato(mid: int, ctx: Ctx, ativo: Annotated[bool, Query()]):
    m = _modelo(ctx, mid)
    if m.ativo != ativo:
        m.ativo = ativo
        ctx.auditar("modelo_contrato.ativar" if ativo else "modelo_contrato.inativar", "modelo_contrato", m.id, descricao=m.nome)
        ctx.db.commit()
    return _detalhe(ctx, m)


@router.post("/contrato/{mid}/duplicar", response_model=ModeloContratoOut, status_code=201)
def duplicar_contrato(mid: int, ctx: Ctx):
    """Cópia INATIVA ("X (cópia)"): não passa a valer sem alguém revisar e ativar."""
    o = _modelo(ctx, mid)
    nomes = set(ctx.db.scalars(select(ModeloContrato.nome)))
    c = ModeloContrato(
        nome=nome_da_copia(nomes, o.nome, 120), conteudo_html=o.conteudo_html, ativo=False,
        codigo_legado=proximo_codigo(ctx.db, "modelo_contrato"),
    )
    ctx.db.add(c)
    ctx.db.flush()
    ctx.auditar("modelo_contrato.duplicar", "modelo_contrato", c.id, descricao=f"{o.nome} -> {c.nome}", depois=foto(c, ("conteudo_html",)))
    ctx.db.commit()
    return _detalhe(ctx, c)


@router.delete("/contrato/{mid}", response_model=Mensagem)
def excluir_contrato(mid: int, ctx: Ctx):
    m = _modelo(ctx, mid)
    planos = ctx.db.scalar(select(func.count(Plano.id)).where(Plano.modelo_contrato_id == mid)) or 0
    if planos:
        raise HTTPException(
            409,
            f"Não é possível excluir: o modelo {m.nome} é usado por {plural(planos, 'plano', 'planos')}. "
            "Troque o modelo desses planos ou apenas inative este modelo.",
        )
    antes = foto(m, ("conteudo_html",))
    ctx.db.delete(m)
    ctx.auditar("modelo_contrato.excluir", "modelo_contrato", mid, descricao=m.nome, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Modelo excluído.")


# ------------------------------------------------------------------------------------------------ evolução
class ModeloEvolucaoIn(Schema):
    titulo: Texto = Field(min_length=2, max_length=120)
    texto: str = Field(min_length=1, max_length=20_000)
    ativo: bool = True


class ModeloEvolucaoOut(Schema):
    id: int
    codigo: int | None
    titulo: str
    texto: str
    ativo: bool
    atualizado_em: datetime | None = None


class ModeloEvolucaoAtivo(Schema):
    id: int
    titulo: str
    texto: str


def _evo_out(m: ModeloEvolucao) -> ModeloEvolucaoOut:
    return ModeloEvolucaoOut(
        id=m.id, codigo=m.codigo_legado, titulo=m.titulo, texto=m.texto, ativo=m.ativo, atualizado_em=m.atualizado_em
    )


def _evo(ctx, mid: int) -> ModeloEvolucao:
    m = ctx.db.get(ModeloEvolucao, mid)
    if not m:
        raise nao_encontrado("Modelo de evolução")
    return m


def _texto_evolucao(texto: str) -> str:
    """Texto simples: sem marcação (a evolução é digitada na gaveta como texto)."""
    limpo = html_seguro.texto_puro(texto, 20_000) if "<" in texto else texto.strip()
    if not limpo:
        raise HTTPException(422, "Escreva o texto-base da evolução.")
    return limpo


def _checar_titulo(ctx, titulo: str, exceto: int | None = None) -> None:
    q = select(ModeloEvolucao.id).where(func.lower(ModeloEvolucao.titulo) == titulo.lower(), ModeloEvolucao.id != (exceto or 0))
    if ctx.db.scalar(q):
        raise HTTPException(409, "Já existe um modelo de evolução com este título.")


@router.get("/evolucao/ativos", response_model=list[ModeloEvolucaoAtivo])
def evolucao_ativos(ctx: Ctx):
    """Modelos ativos para a gaveta de evolução da agenda (permissão da própria evolução: `aulas.evoluir`)."""
    return list(ctx.db.scalars(select(ModeloEvolucao).where(ModeloEvolucao.ativo.is_(True)).order_by(func.lower(ModeloEvolucao.titulo))))


@router.get("/evolucao", response_model=PaginaContagens[ModeloEvolucaoOut])
def listar_evolucao(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    situacao: Annotated[str, Query(pattern="^(todos|ativos|inativos)$")] = "todos",
):
    base = select(ModeloEvolucao)
    if pedido.q:
        base = base.where(contem(ModeloEvolucao.titulo, pedido.q) | contem(ModeloEvolucao.texto, pedido.q))
    contagens = {"todos": 0, "ativos": 0, "inativos": 0}
    for m in ctx.db.scalars(base):
        contagens["todos"] += 1
        contagens["ativos" if m.ativo else "inativos"] += 1
    stmt = base
    if situacao != "todos":
        stmt = stmt.where(ModeloEvolucao.ativo.is_(situacao == "ativos"))
    colunas = {
        "titulo": func.lower(ModeloEvolucao.titulo), "codigo": ModeloEvolucao.codigo_legado,
        "atualizado": ModeloEvolucao.atualizado_em,
    }
    stmt = stmt.order_by(ordem(pedido, colunas, "titulo"), ModeloEvolucao.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=[_evo_out(m) for (m,) in linhas], total=total, pagina=pedido.pagina, por_pagina=pedido.por_pagina,
        contagens=contagens,
    )


@router.get("/evolucao/{mid}", response_model=ModeloEvolucaoOut)
def ler_evolucao(mid: int, ctx: Ctx):
    return _evo_out(_evo(ctx, mid))


@router.post("/evolucao", response_model=ModeloEvolucaoOut, status_code=201)
def criar_evolucao(dados: ModeloEvolucaoIn, ctx: Ctx):
    _checar_titulo(ctx, dados.titulo)
    m = ModeloEvolucao(
        titulo=dados.titulo, texto=_texto_evolucao(dados.texto), ativo=dados.ativo,
        codigo_legado=proximo_codigo(ctx.db, "modelo_evolucao"),
    )
    ctx.db.add(m)
    ctx.db.flush()
    ctx.auditar("modelo_evolucao.criar", "modelo_evolucao", m.id, descricao=m.titulo, depois=foto(m, ("texto",)))
    ctx.db.commit()
    return _evo_out(m)


@router.put("/evolucao/{mid}", response_model=ModeloEvolucaoOut)
def alterar_evolucao(mid: int, dados: ModeloEvolucaoIn, ctx: Ctx):
    m = _evo(ctx, mid)
    _checar_titulo(ctx, dados.titulo, exceto=mid)
    novo = _texto_evolucao(dados.texto)
    antes = foto(m, ("texto",))
    m.titulo, m.texto, m.ativo = dados.titulo, novo, dados.ativo
    ctx.db.flush()
    ctx.auditar("modelo_evolucao.alterar", "modelo_evolucao", m.id, descricao=m.titulo, antes=antes, depois=foto(m, ("texto",)))
    ctx.db.commit()
    return _evo_out(m)


@router.patch("/evolucao/{mid}/ativo", response_model=ModeloEvolucaoOut)
def ativar_evolucao(mid: int, ctx: Ctx, ativo: Annotated[bool, Query()]):
    m = _evo(ctx, mid)
    if m.ativo != ativo:
        m.ativo = ativo
        ctx.auditar("modelo_evolucao.ativar" if ativo else "modelo_evolucao.inativar", "modelo_evolucao", m.id, descricao=m.titulo)
        ctx.db.commit()
    return _evo_out(m)


@router.delete("/evolucao/{mid}", response_model=Mensagem)
def excluir_evolucao(mid: int, ctx: Ctx):
    """O texto já usado numa evolução foi copiado para ela (não há vínculo), então a exclusão é livre."""
    m = _evo(ctx, mid)
    antes = foto(m, ("texto",))
    ctx.db.delete(m)
    ctx.auditar("modelo_evolucao.excluir", "modelo_evolucao", mid, descricao=m.titulo, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Modelo excluído.")
