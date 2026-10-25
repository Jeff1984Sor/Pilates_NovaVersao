"""Comissões dos profissionais (R17): percentual do cadastro sobre contas a receber PAGAS na competência.

O cálculo é de `app.domain.comissao` (ROUND_HALF_UP, uma comissão por conta, idempotente). Profissional da conta:
o do contrato; para aula avulsa (sem contrato), o profissional da sessão da reserva.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import comissao as dom
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Profissional
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import Comissao, ContaReceber, StatusReceber
from app.modules.financeiro.schemas import ComissaoOut, ComissoesOut, ResumoProfissionalOut
from app.modules.financeiro.servico import ErroDeNegocio

ZERO = Decimal("0")


def validar_competencia(competencia: str) -> tuple[date, date]:
    """`YYYY-MM` estrito (o antigo aceitava "2026-1" e "26-10")."""
    import re

    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia or ""):
        raise ErroDeNegocio("Competência inválida (use AAAA-MM).", 422)
    return dom.parse_competencia(competencia)


def gerar(db: Session, competencia: str) -> dom.ResultadoGeracao:
    inicio, fim = validar_competencia(competencia)
    stmt = (
        select(ContaReceber, Contrato.profissional_id, AulaSessao.profissional_id)
        .outerjoin(Contrato, Contrato.id == ContaReceber.contrato_id)
        .outerjoin(Reserva, Reserva.id == ContaReceber.reserva_id)
        .outerjoin(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .where(ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento >= inicio, ContaReceber.pagamento < fim)
        .order_by(ContaReceber.pagamento, ContaReceber.id)
    )
    contas = [
        dom.ContaRecebida(
            id=c.id, valor=c.valor, status="PAGO", recebido_em=c.pagamento, profissional_id=sessao_prof,
            contrato_id=c.contrato_id, contrato_profissional_id=contrato_prof,
        )
        for c, contrato_prof, sessao_prof in db.execute(stmt).all()
    ]
    percentuais = {p.id: p.comissao_percentual for p in db.scalars(select(Profissional))}
    ja = set(db.scalars(select(Comissao.conta_receber_id)))
    resultado = dom.gerar_comissoes(competencia, contas, percentuais, ja)
    for c in resultado.comissoes:
        db.add(Comissao(profissional_id=c.profissional_id, conta_receber_id=c.conta_receber_id, competencia=competencia,
                        valor_base=c.valor_base, percentual=c.percentual, valor=c.valor))
    db.flush()
    return resultado


def listar(db: Session, competencia: str | None = None, profissional_id: int | None = None,
           situacao: str | None = None) -> ComissoesOut:
    stmt = (
        select(Comissao, Profissional.nome, Aluno.nome)
        .join(Profissional, Profissional.id == Comissao.profissional_id)
        .join(ContaReceber, ContaReceber.id == Comissao.conta_receber_id)
        .join(Aluno, Aluno.id == ContaReceber.aluno_id)
        .order_by(Comissao.competencia.desc(), Profissional.nome, Comissao.id)
    )
    if competencia:
        validar_competencia(competencia)
        stmt = stmt.where(Comissao.competencia == competencia)
    if profissional_id:
        stmt = stmt.where(Comissao.profissional_id == profissional_id)
    if situacao == "PAGA":
        stmt = stmt.where(Comissao.paga_em.is_not(None))
    elif situacao == "PENDENTE":
        stmt = stmt.where(Comissao.paga_em.is_(None))
    itens = [
        ComissaoOut(id=c.id, profissional_id=c.profissional_id, profissional_nome=prof, conta_receber_id=c.conta_receber_id,
                    aluno_nome=aluno, competencia=c.competencia, valor_base=c.valor_base, percentual=c.percentual,
                    valor=c.valor, paga_em=c.paga_em)
        for c, prof, aluno in db.execute(stmt).all()
    ]
    resumo: dict[int, ResumoProfissionalOut] = {}
    for i in itens:
        r = resumo.setdefault(i.profissional_id, ResumoProfissionalOut(
            profissional_id=i.profissional_id, profissional_nome=i.profissional_nome or "-", quantidade=0,
            valor_total=ZERO, valor_pendente=ZERO))
        r.quantidade += 1
        r.valor_total += i.valor
        if not i.paga_em:
            r.valor_pendente += i.valor
    return ComissoesOut(
        competencia=competencia, itens=itens, resumo=sorted(resumo.values(), key=lambda r: r.profissional_nome),
        valor_total=sum((i.valor for i in itens), ZERO),
        valor_pendente=sum((i.valor for i in itens if not i.paga_em), ZERO),
    )


def marcar_pagas(db: Session, ids: list[int], data_pagamento: date) -> list[Comissao]:
    comissoes = db.scalars(select(Comissao).where(Comissao.id.in_(ids))).all()
    if len(comissoes) != len(set(ids)):
        raise ErroDeNegocio("Alguma comissão informada não existe.", 404)
    for c in comissoes:
        if c.paga_em:
            raise ErroDeNegocio("Alguma comissão informada já está paga.")
        c.paga_em = data_pagamento
    db.flush()
    return list(comissoes)


def desfazer_pagamento(db: Session, comissao: Comissao) -> None:
    if not comissao.paga_em:
        raise ErroDeNegocio("A comissão não está paga.")
    comissao.paga_em = None
    db.flush()


def excluir(db: Session, comissao: Comissao) -> None:
    """Só comissão ainda não paga pode ser excluída (permite estornar a baixa e gerar de novo)."""
    if comissao.paga_em:
        raise ErroDeNegocio("Comissão já paga: desfaça o pagamento antes de excluir.")
    db.delete(comissao)
    db.flush()
