"""Contas a pagar: criação com recorrência (R7), pagamento com comprovante, cancelamento, reabertura."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.domain.financeiro import planejar_recorrencia_pagar
from app.modules.cadastros.models import Categoria, Fornecedor, Subcategoria
from app.modules.financeiro import bancos
from app.modules.financeiro.models import ContaPagar, MovimentoConta, RecorrenciaPagar, StatusPagar, TipoMovimento
from app.modules.financeiro.schemas import ContaPagarEditarIn, ContaPagarIn
from app.modules.financeiro.servico import ErroDeNegocio, hoje_de_negocio_agora, novo_grupo

CATEGORIA_COMPROVANTES = "comprovantes"
storage.registrar_categoria(CATEGORIA_COMPROVANTES, "financeiro_pagar.ver", {".pdf", ".png", ".jpg", ".jpeg", ".webp"}, 8)


def obter(db: Session, conta_id: int) -> ContaPagar:
    c = db.get(ContaPagar, conta_id)
    if not c:
        raise ErroDeNegocio("Conta a pagar não encontrada.", 404)
    return c


def _validar_vinculos(db: Session, fornecedor_id: int, categoria_id: int, subcategoria_id: int) -> None:
    if not db.get(Fornecedor, fornecedor_id):
        raise ErroDeNegocio("Fornecedor não encontrado.", 422)
    if not db.get(Categoria, categoria_id):
        raise ErroDeNegocio("Categoria não encontrada.", 422)
    sub = db.get(Subcategoria, subcategoria_id)
    if not sub:
        raise ErroDeNegocio("Subcategoria não encontrada.", 422)
    if sub.categoria_id != categoria_id:
        raise ErroDeNegocio("A subcategoria não pertence à categoria escolhida.", 422)


def criar(db: Session, dados: ContaPagarIn) -> list[ContaPagar]:
    """Cria a conta e, se recorrente, os lançamentos adicionais (SEMANAL +7d, ANUAL +12m, MENSAL +n meses, dia ≤ 28).

    Sem regeneração em cascata: só esta chamada gera; as cópias nascem SEM recorrência, ligadas por `recorrencia_grupo`.
    A original guarda recorrência e quantidade (informativo).
    """
    _validar_vinculos(db, dados.fornecedor_id, dados.categoria_id, dados.subcategoria_id)
    plano = planejar_recorrencia_pagar(dados.vencimento, dados.recorrencia, dados.recorrencia_quantidade)
    grupo = novo_grupo() if plano.vencimentos_adicionais else None
    comum = dict(fornecedor_id=dados.fornecedor_id, categoria_id=dados.categoria_id, subcategoria_id=dados.subcategoria_id,
                 descricao=dados.descricao, valor=dados.valor, status=StatusPagar.AGENDADO, recorrencia_grupo=grupo)
    original = ContaPagar(vencimento=dados.vencimento,
                          recorrencia=RecorrenciaPagar(dados.recorrencia) if dados.recorrencia else None,
                          recorrencia_quantidade=plano.quantidade if dados.recorrencia else None, **comum)
    criadas = [original] + [ContaPagar(vencimento=v, **comum) for v in plano.vencimentos_adicionais]
    db.add_all(criadas)
    db.flush()
    return criadas


def editar(db: Session, conta: ContaPagar, dados: ContaPagarEditarIn) -> None:
    """Edição simples. Nunca regera recorrência. Conta PAGA: só a descrição."""
    if conta.status == StatusPagar.CANCELADO:
        raise ErroDeNegocio("Conta cancelada não pode ser editada: reabra antes.")
    campos = dados.model_dump(exclude_unset=True)
    if conta.status == StatusPagar.PAGO and set(campos) - {"descricao"}:
        raise ErroDeNegocio("Conta paga: só a descrição pode ser alterada. Reabra a conta para mudar valores ou datas.")
    fornecedor = campos.get("fornecedor_id", conta.fornecedor_id)
    categoria = campos.get("categoria_id", conta.categoria_id)
    sub = campos.get("subcategoria_id", conta.subcategoria_id)
    _validar_vinculos(db, fornecedor, categoria, sub)
    for k, v in campos.items():
        if v is None and k != "descricao":
            continue
        setattr(conta, k, v)
    db.flush()


def salvar_comprovante(conta_id: int, nome: str, conteudo: bytes, pasta: str = "contas_pagar") -> str:
    try:
        return storage.salvar(CATEGORIA_COMPROVANTES, nome, conteudo, subpasta=pasta)
    except storage.ArquivoInvalido as e:
        raise ErroDeNegocio(str(e), 422) from None


def pagar(db: Session, conta: ContaPagar, *, data_pagamento: date | None, conta_bancaria_id: int | None,
          comprovante: tuple[str, bytes] | None = None) -> MovimentoConta | None:
    if conta.status == StatusPagar.PAGO:
        raise ErroDeNegocio("Esta conta já está paga.")
    if conta.status == StatusPagar.CANCELADO:
        raise ErroDeNegocio("Conta cancelada: reabra antes de pagar.")
    hoje = hoje_de_negocio_agora()
    pago_em = data_pagamento or hoje
    if pago_em > hoje:
        raise ErroDeNegocio("A data do pagamento não pode ser futura.", 422)
    if conta_bancaria_id:
        bancos.conta_ativa(db, conta_bancaria_id)  # valida antes de gravar o arquivo
    if comprovante:
        antigo = conta.comprovante_path
        conta.comprovante_path = salvar_comprovante(conta.id, comprovante[0], comprovante[1])
        if antigo:
            storage.remover(antigo)
    conta.status = StatusPagar.PAGO
    conta.pagamento = pago_em
    mov = None
    if conta_bancaria_id:
        fornecedor = db.get(Fornecedor, conta.fornecedor_id)
        mov = bancos.criar_movimento(
            db, conta_id=conta_bancaria_id, tipo=TipoMovimento.SAIDA, valor=conta.valor, data=pago_em,
            descricao=f"Pagamento - {fornecedor.nome if fornecedor else 'conta #' + str(conta.id)}"[:200],
            comprovante_path=conta.comprovante_path, conta_pagar_id=conta.id,
        )
    db.flush()
    return mov


def anexar_comprovante(db: Session, conta: ContaPagar, nome: str, conteudo: bytes) -> None:
    antigo = conta.comprovante_path
    conta.comprovante_path = salvar_comprovante(conta.id, nome, conteudo)
    if antigo:
        storage.remover(antigo)
    for m in db.scalars(select(MovimentoConta).where(MovimentoConta.conta_pagar_id == conta.id)):
        m.comprovante_path = conta.comprovante_path
    db.flush()


def cancelar(db: Session, conta: ContaPagar, motivo: str) -> None:
    if conta.status == StatusPagar.PAGO:
        raise ErroDeNegocio("Conta paga não pode ser cancelada: reabra o pagamento antes.")
    if conta.status == StatusPagar.CANCELADO:
        raise ErroDeNegocio("A conta já está cancelada.")
    conta.status = StatusPagar.CANCELADO
    conta.motivo_cancelamento = motivo
    db.flush()


def reabrir(db: Session, conta: ContaPagar) -> None:
    """PAGO ou CANCELADO -> AGENDADO. Apaga o movimento bancário gerado pelo pagamento (o comprovante fica anexado)."""
    if conta.status == StatusPagar.AGENDADO:
        raise ErroDeNegocio("A conta já está agendada.")
    for m in db.scalars(select(MovimentoConta).where(MovimentoConta.conta_pagar_id == conta.id)).all():
        db.delete(m)
    conta.status = StatusPagar.AGENDADO
    conta.pagamento = None
    conta.motivo_cancelamento = None
    db.flush()


def excluir(db: Session, conta: ContaPagar) -> None:
    if conta.status == StatusPagar.PAGO:
        raise ErroDeNegocio("Conta paga não pode ser excluída: reabra o pagamento (ou cancele) antes.")
    for m in db.scalars(select(MovimentoConta).where(MovimentoConta.conta_pagar_id == conta.id)).all():
        db.delete(m)
    caminho = conta.comprovante_path
    db.delete(conta)
    db.flush()
    if caminho:
        storage.remover(caminho)
