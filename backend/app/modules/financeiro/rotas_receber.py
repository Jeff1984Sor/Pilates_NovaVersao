"""Rotas de contas a receber. NENHUMA ação de escrita usa GET (o sistema antigo baixava e excluía por GET)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import Query

from app.core import audit
from app.core.deps import Ctx
from app.core.schemas import Mensagem
from app.modules.alunos.models import Aluno
from app.modules.financeiro import consultas, planilhas, servico
from app.modules.financeiro.consultas import FiltrosReceber
from app.modules.financeiro.exportacao import gerar_pdf, gerar_recibo_pdf, gerar_xlsx, identidade_do_estudio
from app.modules.financeiro.models import ContaReceber
from app.modules.financeiro.rotas_base import PDF, XLSX, anexo, novo_router
from app.modules.financeiro.schemas import (
    AvulsoIn,
    BaixaIn,
    CancelarReceberIn,
    CobrancaOut,
    ContaReceberOut,
    EditarReceberIn,
    PaginaReceber,
    ResumoAlunoOut,
    SituacaoReceber,
)

router = novo_router(prefix="/financeiro/receber", tags=["financeiro: contas a receber"])


def _filtros(situacao: SituacaoReceber | None, de: date | None, ate: date | None, aluno_id: int | None,
             plano_id: int | None, competencia: str | None, q: str | None) -> FiltrosReceber:
    return FiltrosReceber(situacao=situacao, de=de, ate=ate, aluno_id=aluno_id, plano_id=plano_id,
                          competencia=competencia, q=q)


def _foto(c: ContaReceber) -> dict:
    return audit.snapshot(c)


@router.get("", response_model=PaginaReceber)
def listar(
    ctx: Ctx,
    situacao: SituacaoReceber | None = None,
    de: date | None = None,
    ate: date | None = None,
    aluno_id: int | None = None,
    plano_id: int | None = None,
    competencia: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    q: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=200),
):
    """Lista com chips de situação (Todos/Aberto/Pago/Atrasado/Cancelado): contagem e valor somado, respeitando os
    filtros menos a situação. ATRASADO é derivado (vencida e aberta) pela data de negócio de São Paulo."""
    f = _filtros(situacao, de, ate, aluno_id, plano_id, competencia, q)
    itens, total, chips, hoje = consultas.listar_receber(ctx.db, f, pagina, por_pagina)
    return PaginaReceber(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina, chips=chips, hoje=hoje)


@router.get("/exportar")
def exportar(
    ctx: Ctx,
    formato: Literal["xlsx", "pdf"] = "xlsx",
    situacao: SituacaoReceber | None = None,
    de: date | None = None,
    ate: date | None = None,
    aluno_id: int | None = None,
    plano_id: int | None = None,
    competencia: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    q: str | None = None,
):
    """Excel/PDF das faturas do filtro; com `aluno_id` é a exportação do aluno, sem ele é a geral."""
    itens = consultas.todas_receber(ctx.db, _filtros(situacao, de, ate, aluno_id, plano_id, competencia, q))
    aluno = ctx.db.get(Aluno, aluno_id) if aluno_id else None
    ctx.auditar("exportar", "conta_receber", aluno_id, f"Exportou {len(itens)} fatura(s) em {formato.upper()}"
                + (f" do aluno {aluno.nome}" if aluno else " (geral)"))
    ctx.db.commit()
    tabelas = planilhas.receber(itens)
    sufixo = f"aluno-{aluno_id}" if aluno_id else "geral"
    if formato == "xlsx":
        return anexo(gerar_xlsx(tabelas), f"faturas-{sufixo}.xlsx", XLSX)
    titulo = f"Faturas do aluno: {aluno.nome}" if aluno else "Contas a receber"
    return anexo(gerar_pdf(identidade_do_estudio(ctx.db), titulo, tabelas), f"faturas-{sufixo}.pdf", PDF)


@router.post("/avulso", response_model=ContaReceberOut, status_code=201)
def lancar_avulso(dados: AvulsoIn, ctx: Ctx):
    """Lança um valor avulso para o aluno (sem contrato nem aula)."""
    conta = servico.lancar_avulso(ctx.db, aluno_id=dados.aluno_id, descricao=dados.descricao, valor=dados.valor,
                                  vencimento=dados.vencimento, competencia=dados.competencia)
    ctx.auditar("lancar_avulso", "conta_receber", conta.id, f"Lançamento avulso de R$ {conta.valor} para o aluno #{conta.aluno_id}",
                depois=_foto(conta))
    ctx.db.commit()
    return consultas.uma_receber(ctx.db, conta.id)


@router.get("/aluno/{aluno_id}/resumo", response_model=ResumoAlunoOut)
def resumo_do_aluno(aluno_id: int, ctx: Ctx):
    if not ctx.db.get(Aluno, aluno_id):
        raise servico.ErroDeNegocio("Aluno não encontrado.", 404)
    return servico.resumo_financeiro_do_aluno(ctx.db, aluno_id)


@router.get("/{conta_id:int}", response_model=ContaReceberOut)
def obter(conta_id: int, ctx: Ctx):
    conta = consultas.uma_receber(ctx.db, conta_id)
    if not conta:
        raise servico.ErroDeNegocio("Conta a receber não encontrada.", 404)
    return conta


@router.put("/{conta_id:int}", response_model=ContaReceberOut)
def editar(conta_id: int, dados: EditarReceberIn, ctx: Ctx):
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    antes = _foto(conta)
    servico.editar_conta_receber(ctx.db, conta, **dados.model_dump(exclude_unset=True))
    a, d = audit.diff(antes, _foto(conta))
    ctx.auditar("editar", "conta_receber", conta.id, "Editou conta a receber", antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_receber(ctx.db, conta_id)


@router.delete("/{conta_id:int}", response_model=Mensagem)
def excluir(conta_id: int, ctx: Ctx):
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    antes = _foto(conta)
    servico.excluir_conta_receber(ctx.db, conta)
    ctx.auditar("excluir", "conta_receber", conta_id, f"Excluiu conta a receber de R$ {antes['valor']}", antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Lançamento excluído.")


@router.post("/{conta_id:int}/baixa", response_model=ContaReceberOut)
def baixar(conta_id: int, dados: BaixaIn, ctx: Ctx):
    """Baixa (recebimento): data (padrão hoje), forma de pagamento e, opcionalmente, a conta bancária de destino."""
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    antes = _foto(conta)
    mov = servico.baixar_conta_receber(ctx.db, conta, data_pagamento=dados.data_pagamento,
                                       forma_pagamento=dados.forma_pagamento, conta_bancaria_id=dados.conta_bancaria_id)
    a, d = audit.diff(antes, _foto(conta))
    ctx.auditar("baixar", "conta_receber", conta.id,
                f"Baixa de R$ {conta.valor} em {conta.pagamento:%d/%m/%Y}" + (f" (movimento #{mov.id})" if mov else ""),
                antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_receber(ctx.db, conta_id)


@router.delete("/{conta_id:int}/baixa", response_model=ContaReceberOut)
def estornar(conta_id: int, ctx: Ctx):
    """Estorna a baixa: volta para ABERTO e remove o movimento bancário que ela gerou."""
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    antes = _foto(conta)
    removidos = servico.estornar_baixa(ctx.db, conta)
    a, d = audit.diff(antes, _foto(conta))
    ctx.auditar("estornar_baixa", "conta_receber", conta.id,
                f"Estornou a baixa de R$ {conta.valor}" + (f" e removeu {removidos} movimento(s)" if removidos else ""),
                antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_receber(ctx.db, conta_id)


@router.post("/{conta_id:int}/cancelar", response_model=ContaReceberOut)
def cancelar(conta_id: int, dados: CancelarReceberIn, ctx: Ctx):
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    antes = _foto(conta)
    servico.cancelar_conta_receber(ctx.db, conta, dados.motivo)
    a, d = audit.diff(antes, _foto(conta))
    ctx.auditar("cancelar", "conta_receber", conta.id, f"Cancelou conta a receber: {dados.motivo}", antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_receber(ctx.db, conta_id)


@router.post("/{conta_id:int}/reabrir", response_model=ContaReceberOut)
def reabrir(conta_id: int, ctx: Ctx):
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    antes = _foto(conta)
    servico.reabrir_conta_receber(ctx.db, conta)
    a, d = audit.diff(antes, _foto(conta))
    ctx.auditar("reabrir", "conta_receber", conta.id, "Reabriu conta cancelada", antes=a, depois=d)
    ctx.db.commit()
    return consultas.uma_receber(ctx.db, conta_id)


@router.get("/{conta_id:int}/recibo")
def recibo(conta_id: int, ctx: Ctx):
    """Recibo em PDF (identidade do estúdio + dados do aluno). Só para contas pagas."""
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    if conta.status.value != "PAGO":
        raise servico.ErroDeNegocio("O recibo só pode ser emitido para contas pagas.")
    aluno = ctx.db.get(Aluno, conta.aluno_id)
    linha = consultas.uma_receber(ctx.db, conta_id)
    pdf = gerar_recibo_pdf(
        identidade_do_estudio(ctx.db), numero=conta.id, aluno_nome=aluno.nome, aluno_cpf=aluno.cpf,
        pagador_cpf=aluno.cpf_pagador_recibo, origem=linha.origem, competencia=conta.competencia,
        vencimento=conta.vencimento, pagamento=conta.pagamento, valor=conta.valor,
        forma_pagamento=conta.forma_pagamento, descricao=conta.descricao,
    )
    ctx.auditar("emitir_recibo", "conta_receber", conta.id, f"Emitiu recibo PDF da conta #{conta.id}")
    ctx.db.commit()
    return anexo(pdf, f"recibo-{conta.id}.pdf", PDF)


@router.post("/{conta_id:int}/cobrar-whatsapp", response_model=CobrancaOut)
def cobrar_whatsapp(conta_id: int, ctx: Ctx):
    """Ponto de extensão: fica desabilitado (503) até o módulo de comunicação registrar o cobrador."""
    conta = servico.obter_conta_receber(ctx.db, conta_id)
    mensagem = servico.cobrar_por_whatsapp(ctx.db, conta)
    ctx.auditar("cobrar_whatsapp", "conta_receber", conta.id, "Cobrança enviada por WhatsApp")
    ctx.db.commit()
    return CobrancaOut(enviado=True, mensagem=mensagem)


@router.get("/cobranca-whatsapp/status", response_model=CobrancaOut)
def status_cobranca(ctx: Ctx):
    ok = servico.cobrador_disponivel()
    return CobrancaOut(enviado=ok, mensagem="Disponível" if ok else "A cobrança por WhatsApp será liberada junto com o módulo de comunicação.")

