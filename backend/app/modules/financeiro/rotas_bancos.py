"""Contas bancárias, movimentos (com comprovante) e transferências. O saldo é sempre calculado."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core import audit, storage
from app.core.deps import Ctx
from app.core.schemas import Mensagem
from app.modules.financeiro import bancos, planilhas
from app.modules.financeiro.exportacao import gerar_pdf, gerar_xlsx, identidade_do_estudio
from app.modules.financeiro.models import ContaBancaria, MovimentoConta, TipoMovimento
from app.modules.financeiro.pagar import CATEGORIA_COMPROVANTES
from app.modules.financeiro.relatorios import periodo_padrao
from app.modules.financeiro.rotas_base import PDF, XLSX, anexo, novo_router
from app.modules.financeiro.schemas import (
    ContaBancariaIn,
    ContaBancariaOut,
    ExtratoOut,
    MovimentoOut,
    TransferenciaIn,
)
from app.modules.financeiro.servico import ErroDeNegocio, novo_grupo

router = novo_router(prefix="/financeiro/bancos", tags=["financeiro: bancos"])
ZERO = Decimal("0")
MAX_BYTES = 9 * 1024 * 1024


def _conta_out(db, c: ContaBancaria) -> ContaBancariaOut:
    return ContaBancariaOut(id=c.id, banco=c.banco, agencia=c.agencia, conta=c.conta, saldo_inicial=c.saldo_inicial,
                            ativo=c.ativo, saldo_atual=bancos.saldo_conta(db, c), total_movimentos=bancos.contar_movimentos(db, c.id))


def _nome(c: ContaBancaria) -> str:
    return f"{c.banco} ag. {c.agencia} c/c {c.conta}"


def _mov_out(m: MovimentoConta, nomes: dict[int, str]) -> MovimentoOut:
    return MovimentoOut(id=m.id, conta_id=m.conta_id, conta_nome=nomes.get(m.conta_id), tipo=m.tipo.value, valor=m.valor,
                        data=m.data, descricao=m.descricao, tem_comprovante=bool(m.comprovante_path),
                        conta_receber_id=m.conta_receber_id, conta_pagar_id=m.conta_pagar_id,
                        transferencia_id=m.transferencia_id)


def _obter_conta(db, conta_id: int) -> ContaBancaria:
    c = db.get(ContaBancaria, conta_id)
    if not c:
        raise ErroDeNegocio("Conta bancária não encontrada.", 404)
    return c


# ------------------------------------------------------------------------------------------------------ contas
@router.get("/contas", response_model=list[ContaBancariaOut])
def listar_contas(ctx: Ctx, somente_ativas: bool = False):
    stmt = select(ContaBancaria).order_by(ContaBancaria.banco, ContaBancaria.id)
    if somente_ativas:
        stmt = stmt.where(ContaBancaria.ativo.is_(True))
    return [_conta_out(ctx.db, c) for c in ctx.db.scalars(stmt)]


@router.post("/contas", response_model=ContaBancariaOut, status_code=201)
def criar_conta(dados: ContaBancariaIn, ctx: Ctx):
    c = ContaBancaria(**dados.model_dump())
    ctx.db.add(c)
    ctx.db.flush()
    ctx.auditar("criar", "conta_bancaria", c.id, f"Criou a conta {_nome(c)}", depois=audit.snapshot(c))
    ctx.db.commit()
    return _conta_out(ctx.db, c)


@router.put("/contas/{conta_id:int}", response_model=ContaBancariaOut)
def editar_conta(conta_id: int, dados: ContaBancariaIn, ctx: Ctx):
    c = _obter_conta(ctx.db, conta_id)
    antes = audit.snapshot(c)
    for k, v in dados.model_dump().items():
        setattr(c, k, v)
    ctx.db.flush()
    a, d = audit.diff(antes, audit.snapshot(c))
    ctx.auditar("editar", "conta_bancaria", c.id, f"Editou a conta {_nome(c)}", antes=a, depois=d)
    ctx.db.commit()
    return _conta_out(ctx.db, c)


@router.delete("/contas/{conta_id:int}", response_model=Mensagem)
def excluir_conta(conta_id: int, ctx: Ctx):
    c = _obter_conta(ctx.db, conta_id)
    if bancos.contar_movimentos(ctx.db, c.id):
        raise ErroDeNegocio("A conta tem movimentos: inative-a em vez de excluir.")
    antes = audit.snapshot(c)
    ctx.db.delete(c)
    ctx.auditar("excluir", "conta_bancaria", conta_id, f"Excluiu a conta {_nome(c)}", antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Conta excluída.")


# --------------------------------------------------------------------------------------------------- extrato
def montar_extrato(db, conta_id: int | None, de: date, ate: date, tipo: str | None) -> ExtratoOut:
    contas = list(db.scalars(select(ContaBancaria).where(ContaBancaria.id == conta_id) if conta_id
                             else select(ContaBancaria).where(ContaBancaria.ativo.is_(True))))
    if conta_id and not contas:
        raise ErroDeNegocio("Conta bancária não encontrada.", 404)
    ids = [c.id for c in contas]
    nomes = {c.id: _nome(c) for c in contas}
    stmt = select(MovimentoConta).where(MovimentoConta.conta_id.in_(ids), MovimentoConta.data >= de, MovimentoConta.data <= ate)
    if tipo:
        stmt = stmt.where(MovimentoConta.tipo == TipoMovimento(tipo))
    movs = list(db.scalars(stmt.order_by(MovimentoConta.data.desc(), MovimentoConta.id.desc())))
    # o filtro de tipo vale só para a LISTA; saldos e totais do período consideram todos os movimentos
    ent_ant, sai_ant = bancos.soma_movimentos(db, ids, antes_de=de)
    inicio = sum((c.saldo_inicial for c in contas), ZERO) + ent_ant - sai_ant
    ent_per, sai_per = bancos.soma_movimentos(db, ids, desde=de, ate=ate)
    return ExtratoOut(conta_id=conta_id, saldo_inicial_periodo=inicio, total_entradas=ent_per, total_saidas=sai_per,
                      saldo_final=inicio + ent_per - sai_per, movimentos=[_mov_out(m, nomes) for m in movs])


@router.get("/extrato", response_model=ExtratoOut)
def extrato(ctx: Ctx, conta_id: int | None = None, de: date | None = None, ate: date | None = None,
            tipo: Literal["ENTRADA", "SAIDA"] | None = None):
    inicio, fim = periodo_padrao(de, ate)
    return montar_extrato(ctx.db, conta_id, inicio, fim, tipo)


@router.get("/extrato/exportar")
def exportar_extrato(ctx: Ctx, formato: Literal["xlsx", "pdf"] = "xlsx", conta_id: int | None = None,
                     de: date | None = None, ate: date | None = None, tipo: Literal["ENTRADA", "SAIDA"] | None = None):
    inicio, fim = periodo_padrao(de, ate)
    ext = montar_extrato(ctx.db, conta_id, inicio, fim, tipo)
    ctx.auditar("exportar", "movimento_conta", conta_id, f"Exportou o extrato de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} em {formato.upper()}")
    ctx.db.commit()
    tabelas = planilhas.extrato(ext)
    if formato == "xlsx":
        return anexo(gerar_xlsx(tabelas), "extrato.xlsx", XLSX)
    return anexo(gerar_pdf(identidade_do_estudio(ctx.db), "Extrato bancário", tabelas,
                           subtitulo=f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"), "extrato.pdf", PDF)


# ------------------------------------------------------------------------------------------------- movimentos
@router.post("/movimentos", response_model=MovimentoOut, status_code=201)
def criar_movimento(
    ctx: Ctx,
    conta_id: Annotated[int, Form()],
    tipo: Annotated[Literal["ENTRADA", "SAIDA"], Form()],
    valor: Annotated[Decimal, Form(ge=0)],
    data: Annotated[date, Form()],
    descricao: Annotated[str | None, Form(max_length=200)] = None,
    comprovante: Annotated[UploadFile | None, File()] = None,
):
    """Movimento manual (multipart) com comprovante opcional."""
    bancos.conta_ativa(ctx.db, conta_id)
    caminho = None
    if comprovante is not None and comprovante.filename:
        try:
            caminho = storage.salvar(CATEGORIA_COMPROVANTES, comprovante.filename, comprovante.file.read(MAX_BYTES + 1),
                                     subpasta="movimentos")
        except storage.ArquivoInvalido as e:
            raise ErroDeNegocio(str(e), 422) from None
    m = bancos.criar_movimento(ctx.db, conta_id=conta_id, tipo=TipoMovimento(tipo), valor=valor, data=data,
                               descricao=descricao, comprovante_path=caminho)
    ctx.auditar("criar_movimento", "movimento_conta", m.id, f"{tipo} de R$ {valor} em {data:%d/%m/%Y}", depois=audit.snapshot(m))
    ctx.db.commit()
    return _mov_out(m, {conta_id: _nome(ctx.db.get(ContaBancaria, conta_id))})


@router.get("/movimentos/{movimento_id:int}/comprovante")
def comprovante_do_movimento(movimento_id: int, ctx: Ctx):
    m = ctx.db.get(MovimentoConta, movimento_id)
    if not m or not m.comprovante_path or not storage.existe(m.comprovante_path):
        raise ErroDeNegocio("Este movimento não tem comprovante.", 404)
    return FileResponse(storage.resolver(m.comprovante_path),
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.delete("/movimentos/{movimento_id:int}", response_model=Mensagem)
def excluir_movimento(movimento_id: int, ctx: Ctx):
    m = ctx.db.get(MovimentoConta, movimento_id)
    if not m:
        raise ErroDeNegocio("Movimento não encontrado.", 404)
    if m.conta_receber_id or m.conta_pagar_id:
        raise ErroDeNegocio("Este movimento veio da baixa de uma conta: estorne/reabra a conta para removê-lo.")
    if m.transferencia_id:
        raise ErroDeNegocio("Este movimento faz parte de uma transferência: desfaça a transferência inteira.")
    antes = audit.snapshot(m)
    caminho = m.comprovante_path
    ctx.db.delete(m)
    ctx.auditar("excluir_movimento", "movimento_conta", movimento_id, f"Excluiu movimento de R$ {antes['valor']}", antes=antes)
    ctx.db.commit()
    storage.remover(caminho)
    return Mensagem(mensagem="Movimento excluído.")


# --------------------------------------------------------------------------------------------- transferências
@router.post("/transferencias", response_model=list[MovimentoOut], status_code=201)
def transferir(dados: TransferenciaIn, ctx: Ctx):
    """Transferência entre contas: uma SAÍDA na origem e uma ENTRADA no destino, ligadas pelo mesmo `transferencia_id`."""
    if dados.conta_origem_id == dados.conta_destino_id:
        raise ErroDeNegocio("Origem e destino devem ser contas diferentes.", 422)
    origem = bancos.conta_ativa(ctx.db, dados.conta_origem_id)
    destino = bancos.conta_ativa(ctx.db, dados.conta_destino_id)
    grupo = novo_grupo()
    saida = bancos.criar_movimento(ctx.db, conta_id=origem.id, tipo=TipoMovimento.SAIDA, valor=dados.valor, data=dados.data,
                                   descricao=dados.descricao or f"Transferência para {_nome(destino)}", transferencia_id=grupo)
    entrada = bancos.criar_movimento(ctx.db, conta_id=destino.id, tipo=TipoMovimento.ENTRADA, valor=dados.valor, data=dados.data,
                                     descricao=dados.descricao or f"Transferência de {_nome(origem)}", transferencia_id=grupo)
    ctx.auditar("transferir", "movimento_conta", grupo, f"Transferiu R$ {dados.valor} de {_nome(origem)} para {_nome(destino)}")
    ctx.db.commit()
    nomes = {origem.id: _nome(origem), destino.id: _nome(destino)}
    return [_mov_out(saida, nomes), _mov_out(entrada, nomes)]


@router.delete("/transferencias/{transferencia_id}", response_model=Mensagem)
def desfazer_transferencia(transferencia_id: str, ctx: Ctx):
    movs = list(ctx.db.scalars(select(MovimentoConta).where(MovimentoConta.transferencia_id == transferencia_id)))
    if not movs:
        raise ErroDeNegocio("Transferência não encontrada.", 404)
    for m in movs:
        ctx.db.delete(m)
    ctx.auditar("desfazer_transferencia", "movimento_conta", transferencia_id, f"Desfez transferência ({len(movs)} movimentos)")
    ctx.db.commit()
    return Mensagem(mensagem="Transferência desfeita.")
