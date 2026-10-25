"""Peças comuns das rotas do financeiro: roteador que traduz `ErroDeNegocio` em HTTP e helpers de resposta."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.financeiro.servico import ErroDeNegocio

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"


class RotaFinanceiro(APIRoute):
    """Converte `ErroDeNegocio` (regra violada, não encontrado...) na resposta HTTP `{"detail": mensagem}`."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ErroDeNegocio as e:
                corpo = {"detail": e.mensagem}
                if getattr(e, "erros", None):
                    corpo["erros"] = e.erros
                return JSONResponse(corpo, status_code=e.status)

        return handler


def novo_router(**kw) -> APIRouter:
    return APIRouter(route_class=RotaFinanceiro, **kw)


def anexo(conteudo: bytes, nome: str, media_type: str) -> Response:
    return Response(conteudo, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{nome}"'})
