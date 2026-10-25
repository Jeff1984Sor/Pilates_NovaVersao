"""Serviço do financeiro: funções ESTÁVEIS para outros módulos e as operações de contas a receber.

Assinaturas públicas (outros módulos podem chamar, nunca reimplementar):
- `gerar_contas_do_contrato(db, contrato)`: parcelas do contrato (R2, `domain.parcelas`).
- `criar_conta_aula_avulsa(db, *, aluno_id, reserva_id, valor_aula, data_aula, recorrencia_pacote)` (R12).
- `resumo_financeiro_do_aluno(db, aluno_id)`: totais em aberto/atrasado/pago (ATRASADO derivado, R7).
- `hoje_de_negocio_agora()`: "hoje" no fuso America/Sao_Paulo (nunca UTC).

Nenhuma função aqui faz `commit`: quem chama controla a transação (as rotas dão o commit).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import agora
from app.domain import financeiro as dom
from app.domain.parcelas import competencia_mensal, gerar_parcelas
from app.modules import registrar_modelos
from app.modules.agenda.models import AulaAvulsa, Reserva
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Plano
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import (
    Comissao,
    ContaBancaria,
    ContaReceber,
    MovimentoConta,
    StatusReceber,
    TipoMovimento,
)

registrar_modelos()

ZERO = Decimal("0")


class ErroDeNegocio(Exception):
    """Erro de regra com mensagem pronta para o usuário. As rotas viram HTTP `status` (409 por padrão)."""

    def __init__(self, mensagem: str, status: int = 409):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def hoje_de_negocio_agora() -> date:
    """Data local (America/Sao_Paulo) de agora."""
    return dom.hoje_de_negocio(agora())


# ------------------------------------------------------------------------------------------------------ status
def situacao_receber(conta: ContaReceber, hoje: date | None = None) -> str:
    """ABERTO | PAGO | ATRASADO | CANCELADO (ATRASADO é derivado: vencida e aberta)."""
    return dom.status_exibido_receber(str(conta.status.value if hasattr(conta.status, "value") else conta.status),
                                      conta.vencimento, hoje or hoje_de_negocio_agora())


# ------------------------------------------------------------------------------------------ contas do contrato
def gerar_contas_do_contrato(db: Session, contrato: Contrato) -> list[ContaReceber]:
    """Cria as contas a receber (parcelas) de um contrato (R2).

    MENSAL: `max(plano.duracao_meses, 1)` parcelas de `contrato.valor_parcela`, vencimento = início + n meses com
    dia limitado a 28, competência `YYYY-MM`. SEMANAL: a cada 7 dias de `data_inicio` até `data_fim`.
    O contrato precisa existir (id) e NÃO pode ter contas ainda (levanta `ErroDeNegocio`, evita duplicar).
    Não faz commit.
    """
    db.flush()
    existentes = db.scalar(select(func.count()).select_from(ContaReceber).where(ContaReceber.contrato_id == contrato.id))
    if existentes:
        raise ErroDeNegocio(f"O contrato {contrato.id} já possui {existentes} conta(s) a receber.")
    plano = db.get(Plano, contrato.plano_id)
    meses = plano.duracao_meses if plano else 1
    recorrencia = getattr(contrato.recorrencia, "value", contrato.recorrencia) or "MENSAL"
    parcelas = gerar_parcelas(Decimal(contrato.valor_parcela), contrato.data_inicio, contrato.data_fim, meses, recorrencia)
    contas = [
        ContaReceber(
            aluno_id=contrato.aluno_id,
            contrato_id=contrato.id,
            status=StatusReceber.ABERTO,
            valor=p.valor,
            vencimento=p.vencimento,
            competencia=p.competencia,
        )
        for p in parcelas
    ]
    db.add_all(contas)
    db.flush()
    return contas


def criar_conta_aula_avulsa(
    db: Session,
    *,
    aluno_id: int,
    reserva_id: int,
    valor_aula: Decimal | None,
    data_aula: date,
    recorrencia_pacote: str = "SEMANAL",
) -> ContaReceber | None:
    """Conta a receber de UMA aula avulsa (R12): vence no dia da aula, ABERTA.

    Valor 0/nulo (TotalPass, WellHub, cortesia, aula avaliativa) não gera cobrança (devolve None).
    Idempotente: se a reserva já tem conta, devolve a existente. Não faz commit.
    """
    plano = dom.conta_da_aula_avulsa(None if valor_aula is None else Decimal(valor_aula), data_aula, recorrencia_pacote)
    if plano is None:
        return None
    existente = db.scalar(select(ContaReceber).where(ContaReceber.reserva_id == reserva_id))
    if existente:
        return existente
    conta = ContaReceber(
        aluno_id=aluno_id,
        reserva_id=reserva_id,
        status=StatusReceber.ABERTO,
        valor=plano.valor,
        vencimento=plano.vencimento,
        competencia=plano.competencia,
    )
    db.add(conta)
    db.flush()
    return conta


# ------------------------------------------------------------------------------------------------ resumo do aluno
@dataclass(frozen=True)
class ResumoFinanceiroAluno:
    aluno_id: int
    total_aberto: Decimal  # a vencer (ainda não atrasado)
    total_atrasado: Decimal
    total_pago: Decimal
    qtd_aberto: int
    qtd_atrasado: int
    qtd_pago: int
    proximo_vencimento: date | None
    em_dia: bool  # nenhuma conta atrasada


def resumo_financeiro_do_aluno(db: Session, aluno_id: int, hoje: date | None = None) -> ResumoFinanceiroAluno:
    hoje = hoje or hoje_de_negocio_agora()
    contas = db.execute(
        select(ContaReceber.status, ContaReceber.vencimento, ContaReceber.valor).where(ContaReceber.aluno_id == aluno_id)
    ).all()
    tot = {"ABERTO": ZERO, "ATRASADO": ZERO, "PAGO": ZERO}
    qtd = {"ABERTO": 0, "ATRASADO": 0, "PAGO": 0}
    proximo: date | None = None
    for status, venc, valor in contas:
        s = dom.status_exibido_receber(getattr(status, "value", status), venc, hoje)
        if s == "CANCELADO":
            continue
        tot[s] += valor or ZERO
        qtd[s] += 1
        if s == "ABERTO" and (proximo is None or venc < proximo):
            proximo = venc
    return ResumoFinanceiroAluno(
        aluno_id=aluno_id,
        total_aberto=tot["ABERTO"],
        total_atrasado=tot["ATRASADO"],
        total_pago=tot["PAGO"],
        qtd_aberto=qtd["ABERTO"],
        qtd_atrasado=qtd["ATRASADO"],
        qtd_pago=qtd["PAGO"],
        proximo_vencimento=proximo,
        em_dia=qtd["ATRASADO"] == 0,
    )


# -------------------------------------------------------------------------------------------- operações (receber)
def obter_conta_receber(db: Session, conta_id: int) -> ContaReceber:
    conta = db.get(ContaReceber, conta_id)
    if not conta:
        raise ErroDeNegocio("Conta a receber não encontrada.", 404)
    return conta


def validar_conta_bancaria(db: Session, conta_bancaria_id: int) -> ContaBancaria:
    cb = db.get(ContaBancaria, conta_bancaria_id)
    if not cb:
        raise ErroDeNegocio("Conta bancária não encontrada.", 404)
    if not cb.ativo:
        raise ErroDeNegocio("A conta bancária está inativa.", 422)
    return cb


def baixar_conta_receber(
    db: Session,
    conta: ContaReceber,
    *,
    data_pagamento: date | None = None,
    forma_pagamento: str | None = None,
    conta_bancaria_id: int | None = None,
) -> MovimentoConta | None:
    """Dá baixa (recebimento). Só contas ABERTAS (inclusive vencidas). Com `conta_bancaria_id` gera a ENTRADA."""
    if conta.status == StatusReceber.PAGO:
        raise ErroDeNegocio("Esta conta já está paga.")
    if conta.status == StatusReceber.CANCELADO:
        raise ErroDeNegocio("Conta cancelada: reabra antes de dar baixa.")
    hoje = hoje_de_negocio_agora()
    pago_em = data_pagamento or hoje
    if pago_em > hoje:
        raise ErroDeNegocio("A data do pagamento não pode ser futura.", 422)
    banco = validar_conta_bancaria(db, conta_bancaria_id) if conta_bancaria_id else None
    conta.status = StatusReceber.PAGO
    conta.pagamento = pago_em
    conta.forma_pagamento = forma_pagamento
    mov = None
    if banco:
        aluno = db.get(Aluno, conta.aluno_id)
        mov = MovimentoConta(
            conta_id=banco.id,
            tipo=TipoMovimento.ENTRADA,
            valor=conta.valor,
            data=pago_em,
            descricao=_descricao_movimento_receber(conta, aluno.nome if aluno else None),
            conta_receber_id=conta.id,
        )
        db.add(mov)
    db.flush()
    return mov


def _descricao_movimento_receber(conta: ContaReceber, aluno_nome: str | None) -> str:
    partes = ["Recebimento", aluno_nome or f"conta #{conta.id}"]
    if conta.competencia:
        partes.append(conta.competencia)
    return " - ".join(partes)[:200]


def estornar_baixa(db: Session, conta: ContaReceber) -> int:
    """Desfaz a baixa: volta para ABERTA, apaga o movimento bancário gerado por ela. Devolve quantos movimentos saíram.

    Recusa se o recibo do Receita Saúde já foi gerado (libere antes) ou se há comissão gerada sobre a conta.
    """
    if conta.status != StatusReceber.PAGO:
        raise ErroDeNegocio("Só é possível estornar uma conta paga.")
    if conta.recibo_saude_gerado_em:
        raise ErroDeNegocio("O arquivo do Receita Saúde deste pagamento já foi gerado. Libere-o em Receita Saúde antes de estornar.")
    if db.scalar(select(func.count()).select_from(Comissao).where(Comissao.conta_receber_id == conta.id)):
        raise ErroDeNegocio("Há comissão gerada sobre este pagamento. Exclua a comissão (se ainda não paga) antes de estornar.")
    movs = db.scalars(select(MovimentoConta).where(MovimentoConta.conta_receber_id == conta.id)).all()
    for m in movs:
        db.delete(m)
    conta.status = StatusReceber.ABERTO
    conta.pagamento = None
    conta.forma_pagamento = None
    db.flush()
    return len(movs)


def cancelar_conta_receber(db: Session, conta: ContaReceber, motivo: str) -> None:
    if conta.status == StatusReceber.PAGO:
        raise ErroDeNegocio("Conta paga não pode ser cancelada: estorne a baixa primeiro.")
    if conta.status == StatusReceber.CANCELADO:
        raise ErroDeNegocio("A conta já está cancelada.")
    conta.status = StatusReceber.CANCELADO
    conta.motivo_cancelamento = motivo
    db.flush()


def reabrir_conta_receber(db: Session, conta: ContaReceber) -> None:
    if conta.status != StatusReceber.CANCELADO:
        raise ErroDeNegocio("Só contas canceladas podem ser reabertas.")
    conta.status = StatusReceber.ABERTO
    conta.motivo_cancelamento = None
    db.flush()


def excluir_conta_receber(db: Session, conta: ContaReceber) -> None:
    if conta.status == StatusReceber.PAGO:
        raise ErroDeNegocio("Conta paga não pode ser excluída: estorne a baixa (ou cancele) antes.")
    if db.scalar(select(func.count()).select_from(Comissao).where(Comissao.conta_receber_id == conta.id)):
        raise ErroDeNegocio("Há comissão gerada sobre esta conta.")
    for m in db.scalars(select(MovimentoConta).where(MovimentoConta.conta_receber_id == conta.id)).all():
        db.delete(m)
    db.delete(conta)
    db.flush()


def editar_conta_receber(
    db: Session,
    conta: ContaReceber,
    *,
    descricao: str | None = None,
    valor: Decimal | None = None,
    vencimento: date | None = None,
    competencia: str | None = None,
) -> None:
    """Edita uma conta. PAGO só aceita mudar a descrição (valor e datas mexeriam em DRE e movimentos)."""
    if conta.status == StatusReceber.CANCELADO:
        raise ErroDeNegocio("Conta cancelada não pode ser editada: reabra antes.")
    if conta.status == StatusReceber.PAGO and (valor is not None or vencimento is not None or competencia is not None):
        raise ErroDeNegocio("Conta paga: só a descrição pode ser alterada. Estorne a baixa para mudar valor ou datas.")
    if descricao is not None:
        conta.descricao = descricao or None
    if valor is not None:
        conta.valor = valor
    if vencimento is not None:
        conta.vencimento = vencimento
        if competencia is None and conta.competencia is None:
            conta.competencia = competencia_mensal(vencimento)
    if competencia is not None:
        conta.competencia = competencia
    db.flush()


def lancar_avulso(db: Session, *, aluno_id: int, descricao: str, valor: Decimal, vencimento: date,
                  competencia: str | None = None) -> ContaReceber:
    """Lançamento avulso por aluno (sem contrato nem aula). Competência padrão = mês do vencimento."""
    if not db.get(Aluno, aluno_id):
        raise ErroDeNegocio("Aluno não encontrado.", 404)
    conta = ContaReceber(
        aluno_id=aluno_id,
        descricao=descricao,
        status=StatusReceber.ABERTO,
        valor=valor,
        vencimento=vencimento,
        competencia=competencia or competencia_mensal(vencimento),
    )
    db.add(conta)
    db.flush()
    return conta


# ------------------------------------------------------------------------------------ ponto de extensão: WhatsApp
_cobrador = None


def definir_cobrador(fn) -> None:
    """Registra a função que envia a cobrança por WhatsApp (módulo de comunicação, onda 3).

    Assinatura: `fn(db, conta: ContaReceber, aluno: Aluno) -> str` (devolve a mensagem enviada); levanta
    `ErroDeNegocio` se não puder enviar. Sem cobrador registrado a rota responde 503 e o botão da tela fica desabilitado.
    """
    global _cobrador
    _cobrador = fn


def cobrador_disponivel() -> bool:
    return _cobrador is not None


def cobrar_por_whatsapp(db: Session, conta: ContaReceber) -> str:
    if _cobrador is None:
        raise ErroDeNegocio("A cobrança por WhatsApp será liberada junto com o módulo de comunicação.", 503)
    if situacao_receber(conta) not in ("ABERTO", "ATRASADO"):
        raise ErroDeNegocio("Esta fatura não está em aberto. Cobrança não enviada.")
    aluno = db.get(Aluno, conta.aluno_id)
    return _cobrador(db, conta, aluno)


def novo_grupo() -> str:
    return uuid.uuid4().hex


def agora_utc() -> datetime:
    return agora()
