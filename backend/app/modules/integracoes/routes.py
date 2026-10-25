"""Rotas de integrações.

- `router` (protegido, só quem tem `integracoes.*`: perfil Full): tokens de API, configuração e eventos do TotalPass.
- `router_publico` (autenticação própria): API de integração externa (`/api/integracao/*`, chave de API) e o
  webhook do TotalPass (`/api/webhooks/totalpass`, token no cabeçalho `X-Totalpass-Token`).
"""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import get_db
from app.core.deps import Ctx
from app.core.schemas import Mensagem
from app.modules.integracoes import api_externa, servico, totalpass
from app.modules.integracoes import schemas as sc
from app.modules.integracoes.models import TotalpassConfig

router = APIRouter(prefix="/integracoes", tags=["integracoes"])
router_publico = APIRouter()
router_publico.include_router(api_externa.router)

# --------------------------------------------------------------------------------------------- tokens de API


@router.get("/tokens", response_model=list[sc.TokenOut])
def listar_tokens(ctx: Ctx):
    return servico.tokens_listar(ctx)


@router.post("/tokens", response_model=sc.TokenComValorOut, status_code=201)
def criar_token(dados: sc.TokenCriarIn, ctx: Ctx):
    """O valor completo vem SÓ nesta resposta. Guarde-o: depois só existe o hash."""
    return servico.tokens_criar(ctx, dados.nome)


@router.patch("/tokens/{token_id:int}", response_model=sc.TokenOut)
def editar_token(token_id: int, dados: sc.TokenEditarIn, ctx: Ctx):
    return servico.tokens_editar(ctx, token_id, dados)


@router.post("/tokens/{token_id:int}/regenerar", response_model=sc.TokenComValorOut)
def regenerar_token(token_id: int, ctx: Ctx):
    return servico.tokens_regenerar(ctx, token_id)


@router.delete("/tokens/{token_id:int}", response_model=Mensagem)
def excluir_token(token_id: int, ctx: Ctx):
    servico.tokens_excluir(ctx, token_id)
    return Mensagem(mensagem="Token excluído.")


# --------------------------------------------------------------------------------------------- TotalPass (tela)


@router.get("/totalpass", response_model=sc.TotalpassTelaOut)
def totalpass_tela(ctx: Ctx):
    return servico.totalpass_tela(ctx)


@router.put("/totalpass/{unidade_id:int}", response_model=sc.TotalpassConfigOut)
def totalpass_salvar(unidade_id: int, dados: sc.TotalpassConfigIn, ctx: Ctx):
    return servico.totalpass_salvar(ctx, unidade_id, dados)


@router.post("/totalpass/{unidade_id:int}/token-webhook", response_model=sc.WebhookTokenOut)
def totalpass_token_webhook(unidade_id: int, ctx: Ctx):
    """Gera um token novo para o webhook (o antigo deixa de valer). O valor aparece só nesta resposta."""
    return servico.totalpass_gerar_token_webhook(ctx, unidade_id)


@router.post("/totalpass/{unidade_id:int}/testar", response_model=Mensagem)
def totalpass_testar(unidade_id: int, ctx: Ctx):
    return Mensagem(mensagem=servico.totalpass_testar(ctx, unidade_id))


@router.post("/totalpass/{unidade_id:int}/sincronizar", response_model=sc.ResumoSyncOut)
def totalpass_sincronizar(unidade_id: int, dados: sc.SincronizarIn, ctx: Ctx):
    return servico.totalpass_sincronizar(ctx, unidade_id, dados)


@router.get("/totalpass/eventos", response_model=sc.ListaEventosOut)
def totalpass_eventos(ctx: Ctx, resultado: str | None = Query(None, pattern="^(processado|cancelado|descartado|erro|pendente)$"),
                      pagina: int = Query(1, ge=1), por_pagina: int = Query(25, ge=1, le=100)):
    return servico.totalpass_eventos(ctx, resultado=resultado, pagina=pagina, por_pagina=por_pagina)


# --------------------------------------------------------------------------------------------- webhook do TotalPass
LIMITE_WEBHOOK_POR_IP = 120  # por minuto
LIMITE_FALHAS_WEBHOOK_POR_IP = 20  # por 5 minutos
TAMANHO_MAXIMO_WEBHOOK = 256 * 1024


def autenticar_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_totalpass_token: Annotated[str | None, Header(alias="X-Totalpass-Token")] = None,
) -> list[int]:
    """Token OBRIGATÓRIO (comparado em tempo constante). Devolve os ids das configurações cujo token confere.

    Sem nenhum token configurado no sistema a rota RECUSA (o antigo aceitava qualquer POST nesse caso)."""
    ratelimit.verificar(request, "webhook-totalpass", LIMITE_WEBHOOK_POR_IP, 60, db=db)
    tamanho = request.headers.get("content-length")
    if tamanho and tamanho.isdigit() and int(tamanho) > TAMANHO_MAXIMO_WEBHOOK:
        raise HTTPException(413, "Payload grande demais.")
    configurados = [(c.id, totalpass.decifrar(c.webhook_token_cifrado)) for c in db.scalars(
        select(TotalpassConfig).where(TotalpassConfig.webhook_token_cifrado.is_not(None)))]
    configurados = [(i, t) for i, t in configurados if t]
    if not configurados:
        raise HTTPException(403, "Webhook do TotalPass não configurado: cadastre o token em Configurações > Integrações.")
    if not x_totalpass_token:
        ratelimit.verificar(request, "webhook-totalpass-falha", LIMITE_FALHAS_WEBHOOK_POR_IP, 300, db=db)
        raise HTTPException(401, "Token ausente.")
    recebido = x_totalpass_token.encode()
    # percorre TODOS (sem curto-circuito) e compara em tempo constante
    conferem = [i for i, t in configurados if hmac.compare_digest(t.encode(), recebido)]
    if not conferem:
        ratelimit.verificar(request, "webhook-totalpass-falha", LIMITE_FALHAS_WEBHOOK_POR_IP, 300, db=db)
        raise HTTPException(403, "Token invalido.")
    return conferem


@router_publico.post("/webhooks/totalpass", tags=["integracoes (webhook)"])
def webhook_totalpass(
    db: Annotated[Session, Depends(get_db)],
    config_ids: Annotated[list[int], Depends(autenticar_webhook)],
    payload: Annotated[dict[str, Any], Body()],
):
    configs = list(db.scalars(select(TotalpassConfig).where(TotalpassConfig.id.in_(config_ids)).order_by(TotalpassConfig.id)))
    place = totalpass.place_do_payload(payload)
    cfg = next((c for c in configs if place and c.place_id == place), None)
    if cfg is None and len(configs) == 1:
        cfg = configs[0]
    if cfg is None:
        return JSONResponse({"detail": "Não foi possível identificar a unidade (place) do evento.",
                             "error": "Não foi possível identificar a unidade (place) do evento."}, status_code=400)
    if not cfg.ativo:
        return JSONResponse({"ok": True, "warning": "Integracao desativada."}, status_code=202)
    r = totalpass.processar_payload(db, cfg, payload, origem="webhook")
    if r.resultado == "duplicado":
        return {"ok": True, "duplicado": True, "reserva_id": r.reserva_id}
    if r.resultado == "descartado":
        return JSONResponse({"ok": True, "descartado": r.mensagem}, status_code=202)
    if r.resultado == "erro":
        return JSONResponse({"detail": r.mensagem, "error": r.mensagem}, status_code=400)
    return {"ok": True, "reserva_id": r.reserva_id, "resultado": r.resultado}
