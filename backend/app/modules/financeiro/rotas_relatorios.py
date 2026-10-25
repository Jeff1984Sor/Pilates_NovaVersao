"""Fluxo de caixa e DRE (somente leitura) com exportação Excel/PDF."""

from __future__ import annotations

from datetime import date
from typing import Literal

from app.core.deps import Ctx
from app.modules.financeiro import planilhas, relatorios
from app.modules.financeiro.exportacao import gerar_pdf, gerar_xlsx, identidade_do_estudio
from app.modules.financeiro.rotas_base import PDF, XLSX, anexo, novo_router
from app.modules.financeiro.schemas import DreOut, FluxoCaixaOut

router = novo_router(prefix="/financeiro", tags=["financeiro: relatórios"])


@router.get("/caixa", response_model=FluxoCaixaOut)
def fluxo_de_caixa(ctx: Ctx, de: date | None = None, ate: date | None = None, conta_id: int | None = None):
    """Fluxo de caixa projetado POR VENCIMENTO (exclui CANCELADO). `conta_id` afeta só o saldo bancário inicial."""
    inicio, fim = relatorios.periodo_padrao(de, ate)
    return relatorios.fluxo_de_caixa_out(ctx.db, inicio, fim, conta_id)


@router.get("/caixa/exportar")
def exportar_fluxo(ctx: Ctx, formato: Literal["xlsx", "pdf"] = "xlsx", de: date | None = None, ate: date | None = None,
                   conta_id: int | None = None):
    inicio, fim = relatorios.periodo_padrao(de, ate)
    f = relatorios.fluxo_de_caixa_out(ctx.db, inicio, fim, conta_id)
    ctx.auditar("exportar", "fluxo_caixa", None,
                f"Exportou o fluxo de caixa de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} em {formato.upper()}")
    ctx.db.commit()
    tabelas = planilhas.fluxo(f)
    if formato == "xlsx":
        return anexo(gerar_xlsx(tabelas), "fluxo-de-caixa.xlsx", XLSX)
    return anexo(gerar_pdf(identidade_do_estudio(ctx.db), "Fluxo de caixa", tabelas,
                           subtitulo=f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y} (por vencimento)"), "fluxo-de-caixa.pdf", PDF)


@router.get("/dre", response_model=DreOut)
def dre(ctx: Ctx, de: date | None = None, ate: date | None = None):
    """DRE por data de PAGAMENTO (regime de caixa). Lançamentos avulsos ficam em "Sem plano"."""
    inicio, fim = relatorios.periodo_padrao(de, ate)
    return relatorios.dre_out(ctx.db, inicio, fim)


@router.get("/dre/exportar")
def exportar_dre(ctx: Ctx, formato: Literal["xlsx", "pdf"] = "xlsx", de: date | None = None, ate: date | None = None):
    inicio, fim = relatorios.periodo_padrao(de, ate)
    d = relatorios.dre_out(ctx.db, inicio, fim)
    ctx.auditar("exportar", "dre", None, f"Exportou a DRE de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} em {formato.upper()}")
    ctx.db.commit()
    tabelas = planilhas.dre(d)
    if formato == "xlsx":
        return anexo(gerar_xlsx(tabelas), "dre.xlsx", XLSX)
    return anexo(gerar_pdf(identidade_do_estudio(ctx.db), "DRE - Demonstração do Resultado", tabelas,
                           subtitulo=f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y} (por data de pagamento)", paisagem=False),
                 "dre.pdf", PDF)
