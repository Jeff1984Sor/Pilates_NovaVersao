"""Rotas do módulo financeiro (descobertas pelo main.py). Cada grupo está em seu arquivo `rotas_*.py`."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.permissoes import adicionar_regras
from app.modules.financeiro import (
    rotas_bancos,
    rotas_comissoes,
    rotas_pagar,
    rotas_receber,
    rotas_receita_saude,
    rotas_relatorios,
)

router = APIRouter()
for _r in (rotas_receber.router, rotas_pagar.router, rotas_bancos.router, rotas_relatorios.router,
           rotas_receita_saude.router, rotas_comissoes.router):
    router.include_router(_r)

# Regras de permissão. Os prefixos padrão (/financeiro/receber|pagar|caixa|dre|bancos, /receita-saude, /comissoes)
# já estão no mapa do core; aqui só o que foge do padrão.
adicionar_regras([
    # ponto de extensão da cobrança por WhatsApp: exige poder enviar WhatsApp (a rota só funciona na onda de comunicação)
    ("POST", r"/financeiro/receber/\d+/cobrar-whatsapp", "whatsapp.enviar"),
])
