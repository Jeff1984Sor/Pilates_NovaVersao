"""Consultas de listagem do financeiro: contas a receber e a pagar com chips de situação (contagem + valor somado).

ATRASADO nunca é gravado: é "ABERTO/AGENDADO com vencimento anterior a hoje", onde hoje = data de negócio
(America/Sao_Paulo), calculada por `servico.hoje_de_negocio_agora()`. O `hoje` pode ser injetado para testar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, case, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.core.db import agora
from app.domain import financeiro as dom
from app.modules.agenda.models import AulaAvulsa, Reserva
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Categoria, Fornecedor, Plano, Subcategoria
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaPagar, ContaReceber, StatusPagar, StatusReceber
from app.modules.financeiro.schemas import ChipPagar, ChipSituacao, ContaPagarOut, ContaReceberOut

ZERO = Decimal("0")


def _d(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))
SITUACOES_RECEBER = ("ABERTO", "PAGO", "ATRASADO", "CANCELADO")
SITUACOES_PAGAR = ("AGENDADO", "PAGO", "ATRASADO", "CANCELADO")


def _hoje(hoje: date | None) -> date:
    return hoje or dom.hoje_de_negocio(agora())


# =================================================================================================== a receber
@dataclass
class FiltrosReceber:
    situacao: str | None = None  # ABERTO | PAGO | ATRASADO | CANCELADO
    de: date | None = None  # vencimento >=
    ate: date | None = None  # vencimento <=
    aluno_id: int | None = None
    plano_id: int | None = None
    competencia: str | None = None
    q: str | None = None
    pagamento_de: date | None = None
    pagamento_ate: date | None = None


def _plano_id_expr():
    return func.coalesce(Contrato.plano_id, AulaAvulsa.plano_id)


def _base_receber(colunas: list) -> Select:
    return (
        select(*colunas)
        .select_from(ContaReceber)
        .join(Aluno, Aluno.id == ContaReceber.aluno_id)
        .outerjoin(Contrato, Contrato.id == ContaReceber.contrato_id)
        .outerjoin(Reserva, Reserva.id == ContaReceber.reserva_id)
        .outerjoin(AulaAvulsa, AulaAvulsa.id == Reserva.aula_avulsa_id)
        .outerjoin(Plano, Plano.id == _plano_id_expr())
        .outerjoin(Subcategoria, Subcategoria.id == Plano.subcategoria_receita_id)
    )


def _situacao_expr(hoje: date):
    return case(
        (ContaReceber.status == StatusReceber.PAGO, "PAGO"),
        (ContaReceber.status == StatusReceber.CANCELADO, "CANCELADO"),
        (ContaReceber.vencimento < hoje, "ATRASADO"),
        else_="ABERTO",
    )


def _aplicar_filtros_receber(stmt: Select, f: FiltrosReceber, hoje: date, *, com_situacao: bool = True) -> Select:
    if f.de:
        stmt = stmt.where(ContaReceber.vencimento >= f.de)
    if f.ate:
        stmt = stmt.where(ContaReceber.vencimento <= f.ate)
    if f.pagamento_de:
        stmt = stmt.where(ContaReceber.pagamento >= f.pagamento_de)
    if f.pagamento_ate:
        stmt = stmt.where(ContaReceber.pagamento <= f.pagamento_ate)
    if f.aluno_id:
        stmt = stmt.where(ContaReceber.aluno_id == f.aluno_id)
    if f.plano_id:
        stmt = stmt.where(_plano_id_expr() == f.plano_id)
    if f.competencia:
        stmt = stmt.where(ContaReceber.competencia == f.competencia)
    if f.q:
        like = f"%{f.q.strip()}%"
        stmt = stmt.where(or_(Aluno.nome.ilike(like), ContaReceber.descricao.ilike(like), Plano.nome.ilike(like)))
    if com_situacao and f.situacao:
        stmt = stmt.where(_situacao_expr(hoje) == f.situacao)
    return stmt


_COLUNAS_RECEBER = [
    ContaReceber,
    Aluno.nome.label("aluno_nome"),
    func.coalesce(Contrato.codigo_legado, Contrato.id).label("contrato_numero"),
    Plano.nome.label("plano_nome"),
    Subcategoria.nome.label("subcategoria_nome"),
    func.coalesce(AulaAvulsa.codigo_legado, AulaAvulsa.id).label("avulsa_numero"),
]


def _origem(conta: ContaReceber, contrato_numero, avulsa_numero) -> str:
    if conta.contrato_id:
        return f"Contrato #{contrato_numero}"
    if conta.reserva_id:
        return f"Aula avulsa #{avulsa_numero}" if avulsa_numero else "Aula avulsa"
    return conta.descricao or "Lançamento avulso"


def _linha_receber(row, hoje: date) -> ContaReceberOut:
    conta: ContaReceber = row[0]
    status = conta.status.value
    situacao = dom.status_exibido_receber(status, conta.vencimento, hoje)
    return ContaReceberOut(
        id=conta.id,
        aluno_id=conta.aluno_id,
        aluno_nome=row.aluno_nome,
        contrato_id=conta.contrato_id,
        contrato_numero=int(row.contrato_numero) if conta.contrato_id and row.contrato_numero is not None else None,
        reserva_id=conta.reserva_id,
        descricao=conta.descricao,
        origem=_origem(conta, row.contrato_numero, row.avulsa_numero),
        plano_nome=row.plano_nome,
        subcategoria_nome=row.subcategoria_nome,
        status=status,
        situacao=situacao,
        dias_atraso=(hoje - conta.vencimento).days if situacao == "ATRASADO" else 0,
        valor=conta.valor,
        vencimento=conta.vencimento,
        competencia=conta.competencia,
        pagamento=conta.pagamento,
        forma_pagamento=conta.forma_pagamento,
        motivo_cancelamento=conta.motivo_cancelamento,
        recibo_saude_gerado_em=conta.recibo_saude_gerado_em,
    )


def chips_receber(db: Session, f: FiltrosReceber, hoje: date) -> list[ChipSituacao]:
    """Contagem e valor por situação, respeitando todos os filtros MENOS a própria situação (padrão da lista antiga)."""
    sit = _situacao_expr(hoje)
    stmt = _aplicar_filtros_receber(
        _base_receber([sit.label("sit"), func.count(ContaReceber.id), func.coalesce(func.sum(ContaReceber.valor), 0)]),
        f, hoje, com_situacao=False,
    ).group_by(literal_column("1"))  # ordinal: evita parâmetro diferente entre SELECT e GROUP BY no PostgreSQL
    achados = {s: (int(n), _d(v)) for s, n, v in db.execute(stmt).all()}
    chips = [ChipSituacao(situacao="TODOS", quantidade=sum(n for n, _ in achados.values()),
                          valor=sum((v for _, v in achados.values()), ZERO))]
    for s in SITUACOES_RECEBER:
        n, v = achados.get(s, (0, ZERO))
        chips.append(ChipSituacao(situacao=s, quantidade=n, valor=v))
    return chips


def listar_receber(db: Session, f: FiltrosReceber, pagina: int, por_pagina: int, hoje: date | None = None):
    hoje = _hoje(hoje)
    filtro = _aplicar_filtros_receber(_base_receber([func.count(ContaReceber.id)]), f, hoje)
    total = db.scalar(filtro) or 0
    stmt = (
        _aplicar_filtros_receber(_base_receber(_COLUNAS_RECEBER), f, hoje)
        .order_by(ContaReceber.vencimento, ContaReceber.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )
    itens = [_linha_receber(r, hoje) for r in db.execute(stmt).all()]
    return itens, total, chips_receber(db, f, hoje), hoje


def todas_receber(db: Session, f: FiltrosReceber, hoje: date | None = None, limite: int = 20000) -> list[ContaReceberOut]:
    """Todas as linhas do filtro (exportações)."""
    hoje = _hoje(hoje)
    stmt = (
        _aplicar_filtros_receber(_base_receber(_COLUNAS_RECEBER), f, hoje)
        .order_by(ContaReceber.vencimento, ContaReceber.id)
        .limit(limite)
    )
    return [_linha_receber(r, hoje) for r in db.execute(stmt).all()]


def uma_receber(db: Session, conta_id: int, hoje: date | None = None) -> ContaReceberOut | None:
    hoje = _hoje(hoje)
    row = db.execute(_base_receber(_COLUNAS_RECEBER).where(ContaReceber.id == conta_id)).first()
    return _linha_receber(row, hoje) if row else None


# ==================================================================================================== a pagar
@dataclass
class FiltrosPagar:
    situacao: str | None = None  # AGENDADO | PAGO | ATRASADO | CANCELADO
    de: date | None = None
    ate: date | None = None
    fornecedor_id: int | None = None
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    q: str | None = None


def _base_pagar(colunas: list) -> Select:
    return (
        select(*colunas)
        .select_from(ContaPagar)
        .outerjoin(Fornecedor, Fornecedor.id == ContaPagar.fornecedor_id)
        .outerjoin(Categoria, Categoria.id == ContaPagar.categoria_id)
        .outerjoin(Subcategoria, Subcategoria.id == ContaPagar.subcategoria_id)
    )


def _situacao_pagar_expr(hoje: date):
    return case(
        (ContaPagar.status == StatusPagar.PAGO, "PAGO"),
        (ContaPagar.status == StatusPagar.CANCELADO, "CANCELADO"),
        (ContaPagar.vencimento < hoje, "ATRASADO"),
        else_="AGENDADO",
    )


def _aplicar_filtros_pagar(stmt: Select, f: FiltrosPagar, hoje: date, *, com_situacao: bool = True) -> Select:
    if f.de:
        stmt = stmt.where(ContaPagar.vencimento >= f.de)
    if f.ate:
        stmt = stmt.where(ContaPagar.vencimento <= f.ate)
    if f.fornecedor_id:
        stmt = stmt.where(ContaPagar.fornecedor_id == f.fornecedor_id)
    if f.categoria_id:
        stmt = stmt.where(ContaPagar.categoria_id == f.categoria_id)
    if f.subcategoria_id:
        stmt = stmt.where(ContaPagar.subcategoria_id == f.subcategoria_id)
    if f.q:
        like = f"%{f.q.strip()}%"
        stmt = stmt.where(or_(Fornecedor.nome.ilike(like), ContaPagar.descricao.ilike(like), Categoria.nome.ilike(like),
                              Subcategoria.nome.ilike(like)))
    if com_situacao and f.situacao:
        stmt = stmt.where(_situacao_pagar_expr(hoje) == f.situacao)
    return stmt


_COLUNAS_PAGAR = [
    ContaPagar,
    Fornecedor.nome.label("fornecedor_nome"),
    Categoria.nome.label("categoria_nome"),
    Subcategoria.nome.label("subcategoria_nome"),
]


def _linha_pagar(row, hoje: date) -> ContaPagarOut:
    c: ContaPagar = row[0]
    situacao = dom.status_exibido_pagar(c.status.value, c.vencimento, hoje)
    return ContaPagarOut(
        id=c.id,
        fornecedor_id=c.fornecedor_id,
        fornecedor_nome=row.fornecedor_nome,
        categoria_id=c.categoria_id,
        categoria_nome=row.categoria_nome,
        subcategoria_id=c.subcategoria_id,
        subcategoria_nome=row.subcategoria_nome,
        descricao=c.descricao,
        vencimento=c.vencimento,
        valor=c.valor,
        recorrencia=c.recorrencia.value if c.recorrencia else None,
        recorrencia_quantidade=c.recorrencia_quantidade,
        recorrencia_grupo=c.recorrencia_grupo,
        status=c.status.value,
        situacao=situacao,
        dias_atraso=(hoje - c.vencimento).days if situacao == "ATRASADO" else 0,
        pagamento=c.pagamento,
        tem_comprovante=bool(c.comprovante_path),
        motivo_cancelamento=c.motivo_cancelamento,
    )


def chips_pagar(db: Session, f: FiltrosPagar, hoje: date) -> list[ChipPagar]:
    sit = _situacao_pagar_expr(hoje)
    stmt = _aplicar_filtros_pagar(
        _base_pagar([sit.label("sit"), func.count(ContaPagar.id), func.coalesce(func.sum(ContaPagar.valor), 0)]),
        f, hoje, com_situacao=False,
    ).group_by(literal_column("1"))  # ordinal: evita parâmetro diferente entre SELECT e GROUP BY no PostgreSQL
    achados = {s: (int(n), _d(v)) for s, n, v in db.execute(stmt).all()}
    chips = [ChipPagar(situacao="TODOS", quantidade=sum(n for n, _ in achados.values()),
                       valor=sum((v for _, v in achados.values()), ZERO))]
    for s in SITUACOES_PAGAR:
        n, v = achados.get(s, (0, ZERO))
        chips.append(ChipPagar(situacao=s, quantidade=n, valor=v))
    return chips


def listar_pagar(db: Session, f: FiltrosPagar, pagina: int, por_pagina: int, hoje: date | None = None):
    hoje = _hoje(hoje)
    total = db.scalar(_aplicar_filtros_pagar(_base_pagar([func.count(ContaPagar.id)]), f, hoje)) or 0
    stmt = (
        _aplicar_filtros_pagar(_base_pagar(_COLUNAS_PAGAR), f, hoje)
        .order_by(ContaPagar.vencimento, ContaPagar.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )
    itens = [_linha_pagar(r, hoje) for r in db.execute(stmt).all()]
    return itens, total, chips_pagar(db, f, hoje), hoje


def todas_pagar(db: Session, f: FiltrosPagar, hoje: date | None = None, limite: int = 20000) -> list[ContaPagarOut]:
    hoje = _hoje(hoje)
    stmt = (
        _aplicar_filtros_pagar(_base_pagar(_COLUNAS_PAGAR), f, hoje)
        .order_by(ContaPagar.vencimento, ContaPagar.id)
        .limit(limite)
    )
    return [_linha_pagar(r, hoje) for r in db.execute(stmt).all()]


def uma_pagar(db: Session, conta_id: int, hoje: date | None = None) -> ContaPagarOut | None:
    hoje = _hoje(hoje)
    row = db.execute(_base_pagar(_COLUNAS_PAGAR).where(ContaPagar.id == conta_id)).first()
    return _linha_pagar(row, hoje) if row else None
