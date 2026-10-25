"""Rota do painel inicial. Somente leitura (nenhuma escrita por GET).

Permissão: ``painel.ver`` para a rota; o CONTEÚDO de cada bloco depende da permissão do assunto (ver ``servico.py``).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from app.core.db import agora as agora_utc
from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.modules.painel import schemas as sc
from app.modules.painel import servico

router = APIRouter(prefix="/painel", tags=["painel"])

adicionar_regras([("GET", r"/painel(/|$)", "painel.ver")])


def _agora() -> datetime:
    return agora_utc()


@router.get("/resumo", response_model=sc.ResumoPainel)
def resumo(ctx: Ctx) -> sc.ResumoPainel:
    """Indicadores, gráficos, listas e alertas do painel em uma chamada, filtrados pelo perfil do usuário."""
    return servico.calcular_resumo(ctx, _agora())
