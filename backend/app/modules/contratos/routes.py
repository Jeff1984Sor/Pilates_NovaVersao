"""Rotas de contratos: gestão (protegidas, `contratos.*`) e assinatura por link (públicas, `router_publico`)."""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from app.core import permissoes
from app.core.deps import DB, Ctx, ip_cliente
from app.core.permissoes import adicionar_regras
from app.core.ratelimit import limitar
from app.modules.agenda.servico import ErroAgenda
from app.modules.contratos import publico, servico, termo_publico
from app.modules.contratos import schemas as sc
from app.modules.financeiro.servico import ErroDeNegocio

router = APIRouter(prefix="/contratos", tags=["contratos"])
router_publico = APIRouter(prefix="/assinar", tags=["assinatura-publica"])

# O padrão `contratos.*` (GET=ver, DELETE=excluir, demais=editar) cobre quase tudo; abaixo só as exceções.
adicionar_regras([
    ("POST", r"/contratos/\d+/(link|enviar-email|enviar-whatsapp)$", "contratos.enviar"),
    ("POST", r"/contratos/termo/\d+/(link|enviar)$", "alunos.editar"),
    ("POST", r"/contratos/(precificar|recalcular)$", "contratos.editar"),
    ("*", r"/contratos", "contratos.*"),
])

# Rotas públicas de assinatura: autenticação PRÓPRIA (o token do link) + rate limit. O core só conhece os prefixos do
# app do aluno/integração/webhook; registramos o nosso aqui (pedido ao coordenador: mover para `core/permissoes.py`).
_PREFIXO_PUBLICO = r"/api/assinar/"
if _PREFIXO_PUBLICO not in permissoes.PUBLICAS_AUTENTICACAO_PROPRIA:
    permissoes.PUBLICAS_AUTENTICACAO_PROPRIA.append(_PREFIXO_PUBLICO)
    permissoes._PROPRIA_C.append(re.compile(_PREFIXO_PUBLICO))


@contextmanager
def traduzir():
    """Erros de regra viram HTTP com a mensagem em português."""
    try:
        yield
    except servico.ErroContrato as e:
        raise HTTPException(e.status, e.mensagem) from e
    except ErroAgenda as e:
        raise HTTPException(e.status, e.mensagem) from e
    except ErroDeNegocio as e:
        raise HTTPException(e.status, e.mensagem) from e


# ------------------------------------------------------------------------------------------------ lista e opções
@router.get("", response_model=sc.ListaContratos)
def listar(
    ctx: Ctx,
    chip: sc.Chip = "ativos",
    aluno_id: int | None = None,
    plano_id: int | None = None,
    de: date | None = None,
    ate: date | None = None,
    q: str = Query("", max_length=100),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
):
    return servico.listar(ctx.db, chip=chip, aluno_id=aluno_id, plano_id=plano_id, de=de, ate=ate, q=q, pagina=pagina,
                          por_pagina=por_pagina)


@router.get("/opcoes", response_model=sc.OpcoesOut)
def opcoes(ctx: Ctx):
    return servico.opcoes(ctx.db)


@router.post("/precificar", response_model=sc.PrecificacaoOut)
def precificar(dados: sc.PrecificarIn, ctx: Ctx):
    """Valores (R1) e parcelas (R2) em tempo real, sem gravar nada."""
    with traduzir():
        return servico.precificar(ctx.db, dados.plano_id, dados.data_inicio, dados.data_fim)


@router.post("/recalcular", response_model=sc.RecalculoOut)
def recalcular(dados: sc.RecalcularIn, ctx: Ctx):
    """Equivalente ao `recalcular_contratos` do sistema antigo. Simula por padrão; aplicar exige `contratos.excluir`
    (alteração em massa: só quem pode excluir contratos, o perfil Full por padrão)."""
    if not dados.simular:
        ctx.exigir("contratos.excluir")
    with traduzir():
        return servico.recalcular(ctx, dados)


@router.post("/termo/{aluno_id}/link", response_model=sc.LinkOut)
def termo_link(aluno_id: int, ctx: Ctx):
    with traduzir():
        return termo_publico.criar_link(ctx, aluno_id)


class EnviarTermoIn(BaseModel):
    canal: Literal["email", "whatsapp"]


@router.post("/termo/{aluno_id}/enviar", response_model=sc.EnvioOut)
def termo_enviar(aluno_id: int, dados: EnviarTermoIn, ctx: Ctx):
    with traduzir():
        return termo_publico.enviar(ctx, aluno_id, dados.canal)


# -------------------------------------------------------------------------------------------------------- CRUD
@router.post("", response_model=sc.ContratoCriado, status_code=status.HTTP_201_CREATED)
def criar(dados: sc.ContratoIn, ctx: Ctx):
    with traduzir():
        return servico.criar_contrato(ctx, dados)


@router.get("/{contrato_id}", response_model=sc.ContratoDetalhe)
def ler(contrato_id: int, ctx: Ctx):
    with traduzir():
        return servico.detalhe(ctx.db, servico.obter(ctx.db, contrato_id))


@router.put("/{contrato_id}", response_model=sc.ContratoDetalhe)
def editar(contrato_id: int, dados: sc.EditarIn, ctx: Ctx):
    with traduzir():
        return servico.editar(ctx, contrato_id, dados)


@router.post("/{contrato_id}/renovar", response_model=sc.ContratoCriado, status_code=status.HTTP_201_CREATED)
def renovar(contrato_id: int, dados: sc.RenovarIn, ctx: Ctx):
    with traduzir():
        return servico.renovar(ctx, contrato_id, dados)


@router.post("/{contrato_id}/encerrar", response_model=sc.EncerramentoOut)
def encerrar(contrato_id: int, dados: sc.EncerrarIn, ctx: Ctx):
    with traduzir():
        return servico.encerrar(ctx, contrato_id, dados)


@router.get("/{contrato_id}/exclusao", response_model=sc.PlanoExclusaoOut)
def plano_exclusao(contrato_id: int, ctx: Ctx):
    """Tela de confirmação: o que a exclusão apagaria e o que ela preserva. Só LÊ."""
    with traduzir():
        return servico.plano_de_exclusao(ctx.db, contrato_id)


@router.delete("/{contrato_id}", response_model=sc.ExclusaoOut)
def excluir(contrato_id: int, ctx: Ctx, confirmar: bool = False):
    with traduzir():
        return servico.excluir(ctx, contrato_id, confirmar=confirmar)


# ------------------------------------------------------------------------------------------------------ agenda
@router.get("/{contrato_id}/agenda/opcoes", response_model=sc.AgendaOpcoes)
def agenda_opcoes(contrato_id: int, ctx: Ctx):
    with traduzir():
        return servico.agenda_opcoes(ctx.db, contrato_id)


@router.post("/{contrato_id}/agenda", response_model=sc.AgendaOut)
def agenda_gerar(contrato_id: int, dados: sc.AgendaIn, ctx: Ctx):
    with traduzir():
        return servico.gerar_agenda(ctx, contrato_id, dados)


# ----------------------------------------------------------------------------------------- PDF, envio, assinatura
@router.get("/{contrato_id}/pdf")
def pdf(contrato_id: int, ctx: Ctx):
    """PDF atual do contrato (com a assinatura quando assinado). Gerado na hora; não grava nada."""
    with traduzir():
        c = servico.obter(ctx.db, contrato_id)
        conteudo = servico.gerar_pdf_do_contrato(ctx.db, c)
    return Response(conteudo, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="contrato-{servico.numero_do_contrato(c)}.pdf"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.post("/{contrato_id}/link", response_model=sc.LinkOut)
def link(contrato_id: int, ctx: Ctx):
    with traduzir():
        return servico.link_assinatura(ctx, contrato_id)


@router.post("/{contrato_id}/enviar-email", response_model=sc.EnvioOut)
def enviar_email(contrato_id: int, ctx: Ctx):
    with traduzir():
        return servico.enviar_email(ctx, contrato_id)


@router.post("/{contrato_id}/enviar-whatsapp", response_model=sc.EnvioOut)
def enviar_whatsapp(contrato_id: int, ctx: Ctx):
    with traduzir():
        return servico.enviar_whatsapp(ctx, contrato_id)


@router.post("/{contrato_id}/assinatura-local", response_model=sc.ContratoDetalhe)
def assinatura_local(contrato_id: int, dados: sc.AssinaturaLocalIn, ctx: Ctx):
    with traduzir():
        return servico.assinar_local(ctx, contrato_id, dados)


# ============================================================================================ PÚBLICAS (sem login)
_ver = Depends(limitar("assinar-ver", 60, 60))
_pdf = Depends(limitar("assinar-pdf", 30, 60))
_assinar = Depends(limitar("assinar-enviar", 10, 60))


@router_publico.get("/contrato/{token}", response_model=sc.ContratoPublico, dependencies=[_ver])
def publico_contrato(token: str, db: DB):
    with traduzir():
        return publico.visualizar(db, token)


@router_publico.get("/contrato/{token}/pdf", dependencies=[_pdf])
def publico_contrato_pdf(token: str, db: DB):
    """PDF para o aluno e para o provedor de WhatsApp baixar. GET puro: não grava nada."""
    with traduzir():
        conteudo, nome = publico.pdf(db, token)
    return Response(conteudo, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{nome}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router_publico.post("/contrato/{token}", response_model=sc.AssinadoOut, dependencies=[_assinar])
def publico_contrato_assinar(token: str, dados: sc.AssinarPublicoIn, request: Request, db: DB):
    with traduzir():
        return publico.assinar(db, token, dados, ip_cliente(request))


@router_publico.get("/termo/{token}", response_model=sc.TermoPublico, dependencies=[_ver])
def publico_termo(token: str, db: DB):
    with traduzir():
        return termo_publico.visualizar(db, token)


@router_publico.post("/termo/{token}", response_model=sc.AssinadoOut, dependencies=[_assinar])
def publico_termo_assinar(token: str, dados: sc.AssinarPublicoIn, request: Request, db: DB):
    with traduzir():
        return termo_publico.assinar(db, token, dados, ip_cliente(request))


# Liga o link real de assinatura do termo de imagem no módulo de alunos (idempotente; roda quando o módulo é carregado).
termo_publico.registrar_no_modulo_alunos()
