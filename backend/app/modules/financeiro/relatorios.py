"""Relatórios: fluxo de caixa (por vencimento, sem CANCELADO) e DRE (por data de pagamento). R7.

Os números vêm de `app.domain.financeiro` (`fluxo_de_caixa`, `dre`); aqui só se monta a entrada a partir do banco.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import financeiro as dom
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Categoria, Fornecedor, Plano, Subcategoria, TipoServico
from app.modules.contratos.models import Contrato
from app.modules.financeiro import bancos
from app.modules.financeiro.models import ContaPagar, ContaReceber, StatusPagar, StatusReceber
from app.modules.financeiro.schemas import (
    ComparativoOut,
    DiaFluxoOut,
    DreOut,
    FluxoCaixaOut,
    ItemAgrupadoOut,
    LinhaFluxoOut,
    SemanaFluxoOut,
)
from app.modules.financeiro.servico import ErroDeNegocio, hoje_de_negocio_agora

LIMITE_DIAS_FLUXO = 400


def primeiro_e_ultimo_dia(ref: date) -> tuple[date, date]:
    primeiro = ref.replace(day=1)
    proximo = (primeiro + timedelta(days=32)).replace(day=1)
    return primeiro, proximo - timedelta(days=1)


def periodo_padrao(de: date | None, ate: date | None, hoje: date | None = None) -> tuple[date, date]:
    """Sem datas: mês corrente (data de negócio). Com uma só: a outra completa o mês."""
    hoje = hoje or hoje_de_negocio_agora()
    p, u = primeiro_e_ultimo_dia(de or ate or hoje)
    inicio, fim = de or p, ate or u
    if fim < inicio:
        raise ErroDeNegocio("A data final não pode ser anterior à inicial.", 422)
    return inicio, fim


# ============================================================================================== fluxo de caixa
def _lancamentos_receita(db: Session, inicio: date, fim: date, hoje: date) -> list[dom.Lancamento]:
    stmt = (
        select(
            ContaReceber,
            Contrato.codigo_legado.label("c_legado"),
            Contrato.id.label("c_id"),
            Aluno.nome.label("aluno_nome"),
            Plano.nome.label("plano_nome"),
            Reserva.id.label("reserva_id"),
            AulaSessao.hora_inicio.label("hora"),
            TipoServico.nome.label("servico"),
        )
        .join(Aluno, Aluno.id == ContaReceber.aluno_id)
        .outerjoin(Contrato, Contrato.id == ContaReceber.contrato_id)
        .outerjoin(Plano, Plano.id == Contrato.plano_id)
        .outerjoin(Reserva, Reserva.id == ContaReceber.reserva_id)
        .outerjoin(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .outerjoin(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .where(ContaReceber.status != StatusReceber.CANCELADO, ContaReceber.vencimento >= inicio,
               ContaReceber.vencimento <= fim)
        .order_by(ContaReceber.vencimento, ContaReceber.id)
    )
    saida = []
    for r in db.execute(stmt).all():
        conta: ContaReceber = r[0]
        numero = (r.c_legado or r.c_id) if conta.contrato_id else None
        descricao, detalhe = dom.descrever_receita(
            conta.id,
            contrato_numero=numero,
            aluno_do_contrato=r.aluno_nome,
            plano=r.plano_nome,
            reserva_aluno=r.aluno_nome if conta.reserva_id else None,
            reserva_hora=r.hora,
            reserva_servico=r.servico,
            tem_reserva=bool(conta.reserva_id),
        )
        saida.append(dom.Lancamento(
            id=conta.id, vencimento=conta.vencimento, valor=conta.valor,
            status=dom.status_exibido_receber(conta.status.value, conta.vencimento, hoje),
            descricao=descricao, detalhe=detalhe,
        ))
    return saida


def _lancamentos_despesa(db: Session, inicio: date, fim: date, hoje: date) -> list[dom.Lancamento]:
    stmt = (
        select(ContaPagar, Fornecedor.nome.label("fornecedor"), Categoria.nome.label("categoria"),
               Subcategoria.nome.label("subcategoria"))
        .outerjoin(Fornecedor, Fornecedor.id == ContaPagar.fornecedor_id)
        .outerjoin(Categoria, Categoria.id == ContaPagar.categoria_id)
        .outerjoin(Subcategoria, Subcategoria.id == ContaPagar.subcategoria_id)
        .where(ContaPagar.status != StatusPagar.CANCELADO, ContaPagar.vencimento >= inicio, ContaPagar.vencimento <= fim)
        .order_by(ContaPagar.vencimento, ContaPagar.id)
    )
    saida = []
    for r in db.execute(stmt).all():
        c: ContaPagar = r[0]
        descricao, detalhe = dom.descrever_despesa(r.fornecedor, r.categoria, r.subcategoria)
        saida.append(dom.Lancamento(
            id=c.id, vencimento=c.vencimento, valor=c.valor,
            status=dom.status_exibido_pagar(c.status.value, c.vencimento, hoje),
            descricao=descricao, detalhe=detalhe,
        ))
    return saida


def calcular_fluxo(db: Session, inicio: date, fim: date, conta_id: int | None = None,
                   hoje: date | None = None) -> dom.FluxoCaixa:
    if (fim - inicio).days > LIMITE_DIAS_FLUXO:
        raise ErroDeNegocio(f"O período do fluxo de caixa pode ter no máximo {LIMITE_DIAS_FLUXO} dias.", 422)
    hoje = hoje or hoje_de_negocio_agora()
    if conta_id:
        bancos.conta_ativa(db, conta_id)
    base = bancos.saldo_base_antes_de(db, inicio, conta_id)
    return dom.fluxo_de_caixa(_lancamentos_receita(db, inicio, fim, hoje), _lancamentos_despesa(db, inicio, fim, hoje),
                              inicio, fim, base)


def fluxo_de_caixa_out(db: Session, inicio: date, fim: date, conta_id: int | None = None,
                       hoje: date | None = None) -> FluxoCaixaOut:
    atual = calcular_fluxo(db, inicio, fim, conta_id, hoje)
    ini_ant, fim_ant = dom.periodo_anterior(inicio, fim)
    anterior = calcular_fluxo(db, ini_ant, fim_ant, conta_id, hoje)
    comp = dom.comparar_com_mes_anterior(atual, anterior, ini_ant, fim_ant)
    return FluxoCaixaOut(
        inicio=inicio, fim=fim, conta_id=conta_id,
        saldo_bancario_base=atual.saldo_bancario_base,
        saldo_projetado_final=atual.saldo_projetado_final,
        total_receitas=atual.total_receitas,
        total_despesas=atual.total_despesas,
        lancamentos=[LinhaFluxoOut(**vars(x)) for x in atual.lancamentos],
        saldo_diario=[DiaFluxoOut(**vars(x)) for x in atual.saldo_diario],
        saldo_semanal=[SemanaFluxoOut(**vars(x)) for x in atual.saldo_semanal],
        comparativo_mes_anterior=ComparativoOut(**vars(comp)),
    )


# ====================================================================================================== DRE
def calcular_dre(db: Session, inicio: date, fim: date) -> dom.Dre:
    """DRE por data de PAGAMENTO. Receitas por plano/categoria/subcategoria vêm do PLANO DO CONTRATO; contas sem
    contrato (aula avulsa por reserva e lançamentos avulsos) caem em "Sem plano"/"Sem categoria" (como no antigo)."""
    rec_stmt = (
        select(ContaReceber, Plano.nome, Categoria.nome, Subcategoria.nome)
        .outerjoin(Contrato, Contrato.id == ContaReceber.contrato_id)
        .outerjoin(Plano, Plano.id == Contrato.plano_id)
        .outerjoin(Categoria, Categoria.id == Plano.categoria_receita_id)
        .outerjoin(Subcategoria, Subcategoria.id == Plano.subcategoria_receita_id)
        .where(ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento >= inicio, ContaReceber.pagamento <= fim)
    )
    receitas = [
        dom.ReceitaRecebida(valor=c.valor, pagamento=c.pagamento, status="PAGO", plano=plano, categoria=cat, subcategoria=sub)
        for c, plano, cat, sub in db.execute(rec_stmt).all()
    ]
    des_stmt = (
        select(ContaPagar, Categoria.nome, Subcategoria.nome)
        .outerjoin(Categoria, Categoria.id == ContaPagar.categoria_id)
        .outerjoin(Subcategoria, Subcategoria.id == ContaPagar.subcategoria_id)
        .where(ContaPagar.status == StatusPagar.PAGO, ContaPagar.pagamento >= inicio, ContaPagar.pagamento <= fim)
    )
    despesas = [
        dom.DespesaPaga(valor=c.valor, pagamento=c.pagamento, status="PAGO", categoria=cat, subcategoria=sub)
        for c, cat, sub in db.execute(des_stmt).all()
    ]
    saldo_anterior = bancos.saldo_base_antes_de(db, inicio.replace(day=1))
    return dom.dre(receitas, despesas, inicio, fim, saldo_anterior)


def _itens(pares: list[tuple[str, object]]) -> list[ItemAgrupadoOut]:
    return [ItemAgrupadoOut(nome=n, total=t) for n, t in pares]


def dre_out(db: Session, inicio: date, fim: date) -> DreOut:
    d = calcular_dre(db, inicio, fim)
    return DreOut(
        inicio=inicio, fim=fim,
        receita_bruta=d.receita_bruta, deducoes=d.deducoes, receita_liquida=d.receita_liquida,
        custo_direto=d.custo_direto, lucro_bruto=d.lucro_bruto, despesas_operacionais=d.despesas_operacionais,
        resultado_final=d.resultado_final, resultado_label=d.resultado_label,
        saldo_bancario_anterior=d.saldo_bancario_anterior, saldo_bancario_final=d.saldo_bancario_final,
        receitas_por_plano=_itens(d.receitas_por_plano),
        receitas_por_categoria=_itens(d.receitas_por_categoria),
        receitas_por_subcategoria=_itens(d.receitas_por_subcategoria),
        despesas_por_categoria=_itens(d.despesas_por_categoria),
        despesas_por_subcategoria=_itens(d.despesas_por_subcategoria),
    )
