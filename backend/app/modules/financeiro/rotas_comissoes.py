"""Comissões dos profissionais (R17)."""

from __future__ import annotations

from typing import Literal

from fastapi import Query

from app.core.deps import Ctx
from app.core.schemas import Mensagem
from app.modules.financeiro import comissoes as srv
from app.modules.financeiro import planilhas
from app.modules.financeiro.exportacao import gerar_pdf, gerar_xlsx, identidade_do_estudio
from app.modules.financeiro.models import Comissao
from app.modules.financeiro.rotas_base import PDF, XLSX, anexo, novo_router
from app.modules.financeiro.schemas import ComissoesOut, GerarComissaoIn, GerarComissaoOut, PagarComissaoIn
from app.modules.financeiro.servico import ErroDeNegocio, hoje_de_negocio_agora

router = novo_router(prefix="/comissoes", tags=["financeiro: comissões"])


@router.get("", response_model=ComissoesOut)
def listar(ctx: Ctx, competencia: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), profissional_id: int | None = None,
           situacao: Literal["PAGA", "PENDENTE"] | None = None):
    return srv.listar(ctx.db, competencia, profissional_id, situacao)


@router.get("/exportar")
def exportar(ctx: Ctx, formato: Literal["xlsx", "pdf"] = "xlsx",
             competencia: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
             profissional_id: int | None = None, situacao: Literal["PAGA", "PENDENTE"] | None = None):
    dados = srv.listar(ctx.db, competencia, profissional_id, situacao)
    ctx.auditar("exportar", "comissao", None, f"Exportou comissões ({competencia or 'todas'}) em {formato.upper()}")
    ctx.db.commit()
    tabelas = planilhas.comissoes(dados)
    if formato == "xlsx":
        return anexo(gerar_xlsx(tabelas), "comissoes.xlsx", XLSX)
    return anexo(gerar_pdf(identidade_do_estudio(ctx.db), "Comissões dos profissionais", tabelas,
                           subtitulo=f"Competência {competencia}" if competencia else None), "comissoes.pdf", PDF)


@router.post("/gerar", response_model=GerarComissaoOut)
def gerar(dados: GerarComissaoIn, ctx: Ctx):
    """Gera as comissões da competência sobre contas PAGAS no mês (idempotente: nunca duplica uma conta)."""
    r = srv.gerar(ctx.db, dados.competencia)
    ctx.auditar("gerar", "comissao", None,
                f"Gerou {r.geradas} comissão(ões) da competência {dados.competencia} (R$ {r.valor_total})")
    ctx.db.commit()
    return GerarComissaoOut(competencia=dados.competencia, geradas=r.geradas, valor_total=r.valor_total)


@router.post("/pagar", response_model=Mensagem)
def marcar_pagas(dados: PagarComissaoIn, ctx: Ctx):
    hoje = hoje_de_negocio_agora()
    quando = dados.data_pagamento or hoje
    if quando > hoje:
        raise ErroDeNegocio("A data do pagamento não pode ser futura.", 422)
    cs = srv.marcar_pagas(ctx.db, dados.comissao_ids, quando)
    ctx.auditar("pagar", "comissao", None, f"Marcou {len(cs)} comissão(ões) como paga(s) em {quando:%d/%m/%Y}",
                depois={"comissao_ids": [c.id for c in cs]})
    ctx.db.commit()
    return Mensagem(mensagem=f"{len(cs)} comissão(ões) marcada(s) como paga(s).")


@router.post("/{comissao_id:int}/desfazer-pagamento", response_model=Mensagem)
def desfazer_pagamento(comissao_id: int, ctx: Ctx):
    c = ctx.db.get(Comissao, comissao_id)
    if not c:
        raise ErroDeNegocio("Comissão não encontrada.", 404)
    srv.desfazer_pagamento(ctx.db, c)
    ctx.auditar("desfazer_pagamento", "comissao", c.id, "Desfez o pagamento da comissão")
    ctx.db.commit()
    return Mensagem(mensagem="Pagamento desfeito.")


@router.delete("/{comissao_id:int}", response_model=Mensagem)
def excluir(comissao_id: int, ctx: Ctx):
    c = ctx.db.get(Comissao, comissao_id)
    if not c:
        raise ErroDeNegocio("Comissão não encontrada.", 404)
    valor = c.valor
    srv.excluir(ctx.db, c)
    ctx.auditar("excluir", "comissao", comissao_id, f"Excluiu comissão de R$ {valor}")
    ctx.db.commit()
    return Mensagem(mensagem="Comissão excluída.")
