"""Rotas de contas a pagar (pagar/cancelar/reabrir/excluir: nunca por GET)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from app.core import audit, storage
from app.core.deps import Ctx
from app.core.schemas import Mensagem
from app.modules.financeiro import consultas, pagar as srv, planilhas
from app.modules.financeiro.consultas import FiltrosPagar
from app.modules.financeiro.exportacao import gerar_pdf, gerar_xlsx, identidade_do_estudio
from app.modules.financeiro.rotas_base import PDF, XLSX, anexo, novo_router
from app.modules.financeiro.schemas import (
    CancelarPagarIn,
    ContaPagarEditarIn,
    ContaPagarIn,
    ContaPagarOut,
    CriarPagarOut,
    PaginaPagar,
    SituacaoPagar,
)
from app.modules.financeiro.servico import ErroDeNegocio

router = novo_router(prefix="/financeiro/pagar", tags=["financeiro: contas a pagar"])
MAX_BYTES = 9 * 1024 * 1024


def _filtros(situacao, de, ate, fornecedor_id, categoria_id, subcategoria_id, q) -> FiltrosPagar:
    return FiltrosPagar(situacao=situacao, de=de, ate=ate, fornecedor_id=fornecedor_id, categoria_id=categoria_id,
                        subcategoria_id=subcategoria_id, q=q)


def _arquivo(up: UploadFile | None) -> tuple[str, bytes] | None:
    if up is None or not up.filename:
        return None
    return up.filename, up.file.read(MAX_BYTES + 1)


@router.get("", response_model=PaginaPagar)
def listar(
    ctx: Ctx,
    situacao: SituacaoPagar | None = None,
    de: date | None = None,
    ate: date | None = None,
    fornecedor_id: int | None = None,
    categoria_id: int | None = None,
    subcategoria_id: int | None = None,
    q: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=200),
):
    f = _filtros(situacao, de, ate, fornecedor_id, categoria_id, subcategoria_id, q)
    itens, total, chips, hoje = consultas.listar_pagar(ctx.db, f, pagina, por_pagina)
    return PaginaPagar(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina, chips=chips, hoje=hoje)


@router.get("/exportar")
def exportar(
    ctx: Ctx,
    formato: Literal["xlsx", "pdf"] = "xlsx",
    situacao: SituacaoPagar | None = None,
    de: date | None = None,
    ate: date | None = None,
    fornecedor_id: int | None = None,
    categoria_id: int | None = None,
    subcategoria_id: int | None = None,
    q: str | None = None,
):
    itens = consultas.todas_pagar(ctx.db, _filtros(situacao, de, ate, fornecedor_id, categoria_id, subcategoria_id, q))
    ctx.auditar("exportar", "conta_pagar", None, f"Exportou {len(itens)} conta(s) a pagar em {formato.upper()}")
    ctx.db.commit()
    tabelas = planilhas.pagar(itens)
    if formato == "xlsx":
        return anexo(gerar_xlsx(tabelas), "contas-a-pagar.xlsx", XLSX)
    return anexo(gerar_pdf(identidade_do_estudio(ctx.db), "Contas a pagar", tabelas), "contas-a-pagar.pdf", PDF)


@router.post("", response_model=CriarPagarOut, status_code=201)
def criar(dados: ContaPagarIn, ctx: Ctx):
    """Cria a conta e, se recorrente, os N lançamentos (SEMANAL/MENSAL/ANUAL). Não há regeneração em cascata."""
    criadas = srv.criar(ctx.db, dados)
    ctx.auditar("criar", "conta_pagar", criadas[0].id,
                f"Criou {len(criadas)} lançamento(s) a pagar de R$ {dados.valor}"
                + (f" ({dados.recorrencia} x{len(criadas)})" if len(criadas) > 1 else ""),
                depois=audit.snapshot(criadas[0]))
    ctx.db.commit()
    return CriarPagarOut(criadas=[consultas.uma_pagar(ctx.db, c.id) for c in criadas])


@router.get("/{conta_id:int}", response_model=ContaPagarOut)
def obter(conta_id: int, ctx: Ctx):
    c = consultas.uma_pagar(ctx.db, conta_id)
    if not c:
        raise ErroDeNegocio("Conta a pagar não encontrada.", 404)
    return c


@router.put("/{conta_id:int}", response_model=ContaPagarOut)
def editar(conta_id: int, dados: ContaPagarEditarIn, ctx: Ctx):
    conta = srv.obter(ctx.db, conta_id)
    antes = audit.snapshot(conta)
    srv.editar(ctx.db, conta, dados)
    a, d = audit.diff(antes, audit.snapshot(conta))
    ctx.auditar("editar", "conta_pagar", conta.id, "Editou conta a pagar", antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_pagar(ctx.db, conta_id)


@router.delete("/{conta_id:int}", response_model=Mensagem)
def excluir(conta_id: int, ctx: Ctx):
    conta = srv.obter(ctx.db, conta_id)
    antes = audit.snapshot(conta)
    srv.excluir(ctx.db, conta)
    ctx.auditar("excluir", "conta_pagar", conta_id, f"Excluiu conta a pagar de R$ {antes['valor']}", antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Lançamento excluído.")


@router.post("/{conta_id:int}/pagar", response_model=ContaPagarOut)
def pagar(
    conta_id: int,
    ctx: Ctx,
    data_pagamento: Annotated[date | None, Form()] = None,
    conta_bancaria_id: Annotated[int | None, Form()] = None,
    comprovante: Annotated[UploadFile | None, File()] = None,
):
    """Registra o pagamento (multipart): data (padrão hoje), comprovante opcional e conta bancária (gera a SAÍDA)."""
    conta = srv.obter(ctx.db, conta_id)
    antes = audit.snapshot(conta)
    mov = srv.pagar(ctx.db, conta, data_pagamento=data_pagamento, conta_bancaria_id=conta_bancaria_id,
                    comprovante=_arquivo(comprovante))
    a, d = audit.diff(antes, audit.snapshot(conta))
    ctx.auditar("pagar", "conta_pagar", conta.id,
                f"Pagamento de R$ {conta.valor} em {conta.pagamento:%d/%m/%Y}" + (f" (movimento #{mov.id})" if mov else ""),
                antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_pagar(ctx.db, conta_id)


@router.post("/{conta_id:int}/comprovante", response_model=ContaPagarOut)
def anexar_comprovante(conta_id: int, ctx: Ctx, comprovante: Annotated[UploadFile, File()]):
    conta = srv.obter(ctx.db, conta_id)
    arq = _arquivo(comprovante)
    if arq is None:
        raise ErroDeNegocio("Envie o arquivo do comprovante.", 422)
    srv.anexar_comprovante(ctx.db, conta, *arq)
    ctx.auditar("anexar_comprovante", "conta_pagar", conta.id, "Anexou comprovante")
    ctx.db.commit()
    return consultas.uma_pagar(ctx.db, conta_id)


@router.get("/{conta_id:int}/comprovante")
def baixar_comprovante(conta_id: int, ctx: Ctx):
    conta = srv.obter(ctx.db, conta_id)
    if not conta.comprovante_path or not storage.existe(conta.comprovante_path):
        raise ErroDeNegocio("Esta conta não tem comprovante.", 404)
    return FileResponse(storage.resolver(conta.comprovante_path),
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.post("/{conta_id:int}/cancelar", response_model=ContaPagarOut)
def cancelar(conta_id: int, dados: CancelarPagarIn, ctx: Ctx):
    conta = srv.obter(ctx.db, conta_id)
    antes = audit.snapshot(conta)
    srv.cancelar(ctx.db, conta, dados.motivo)
    a, d = audit.diff(antes, audit.snapshot(conta))
    ctx.auditar("cancelar", "conta_pagar", conta.id, f"Cancelou conta a pagar: {dados.motivo}", antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_pagar(ctx.db, conta_id)


@router.post("/{conta_id:int}/reabrir", response_model=ContaPagarOut)
def reabrir(conta_id: int, ctx: Ctx):
    conta = srv.obter(ctx.db, conta_id)
    antes = audit.snapshot(conta)
    srv.reabrir(ctx.db, conta)
    a, d = audit.diff(antes, audit.snapshot(conta))
    ctx.auditar("reabrir", "conta_pagar", conta.id, "Reabriu conta a pagar", antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_pagar(ctx.db, conta_id)
