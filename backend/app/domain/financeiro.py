"""Financeiro: atraso derivado, fluxo de caixa, DRE e recorrência de contas a pagar (R7, R12).

Origem no sistema antigo (``core/views.py``):
- ATRASADO derivado: ``contas_pagar_list`` (2528-2545), ``_filtrar_contas_pagar`` (2604), ``dashboard`` (570)
- fluxo de caixa: ``_build_fluxo_caixa_data_for_period`` (2646-2790), ``_build_fluxo_caixa_data`` (2793-2840),
  ``_shift_month_clamped`` (2637)
- DRE: ``dre_view`` (3179-3222) e ``dre_relatorio`` (3225-3370)
- recorrência de contas a pagar: ``create_view`` (4921-4955), ``_add_months``/``_add_years`` (1686-1695)
- cobrança da aula avulsa: ``aluno_aula_avulsa_agenda`` (1295-1304)

Regime: FLUXO DE CAIXA por data de VENCIMENTO (exclui CANCELADO); DRE por data de PAGAMENTO (só PAGO).
"""
from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.parcelas import add_months, competencia_avulsa

FUSO_NEGOCIO = ZoneInfo("America/Sao_Paulo")
STATUS_ENCERRADOS = ("PAGO", "CANCELADO")
ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Atraso derivado
# ---------------------------------------------------------------------------

def hoje_de_negocio(agora: datetime) -> date:
    """Data local (America/Sao_Paulo) de um instante.

    # COMPORTAMENTO ANTIGO (bug): as telas de contas a pagar, fluxo de caixa e DRE usavam ``timezone.now().date()``,
    que é a data em UTC. Depois das 21h de Brasília "hoje" já era amanhã e uma conta que vence hoje aparecia
    ATRASADA à noite (ver ``ATRASO`` no golden). Use SEMPRE esta função para obter "hoje".
    """
    if agora.tzinfo is None:
        return agora.date()
    return agora.astimezone(FUSO_NEGOCIO).date()


def hoje_utc_comportamento_antigo(agora: datetime) -> date:
    """# COMPORTAMENTO ANTIGO: ``timezone.now().date()`` (data em UTC). Só para caracterização."""
    return agora.astimezone(ZoneInfo("UTC")).date() if agora.tzinfo else agora.date()


def esta_atrasada(status: str, vencimento: date | None, hoje: date) -> bool:
    """ATRASADO não é gravado: é "vencida (``vencimento < hoje``) e não paga nem cancelada".

    Vale para contas a receber e a pagar. Vencer HOJE não é atraso.
    """
    return status not in STATUS_ENCERRADOS and vencimento is not None and vencimento < hoje


def status_exibido_pagar(status: str, vencimento: date | None, hoje: date) -> str:
    """PAGO, CANCELADO, ATRASADO (vencida e aberta) ou AGENDADO."""
    if status == "PAGO":
        return "PAGO"
    if status == "CANCELADO":
        return "CANCELADO"
    if esta_atrasada(status, vencimento, hoje):
        return "ATRASADO"
    return "AGENDADO"


def status_exibido_receber(status: str, vencimento: date | None, hoje: date) -> str:
    """PAGO, CANCELADO, ATRASADO (vencida e aberta) ou ABERTO.

    # COMPORTAMENTO ANTIGO: a lista de contas a receber mostrava o status GRAVADO; o valor ``ATRASADO`` existe nas
    opções do campo mas nada o grava. A derivação aqui é a regra R7 (e é o que o painel e o WhatsApp de atraso usam).
    """
    if status == "PAGO":
        return "PAGO"
    if status == "CANCELADO":
        return "CANCELADO"
    return "ATRASADO" if esta_atrasada(status, vencimento, hoje) else "ABERTO"


# ---------------------------------------------------------------------------
# Fluxo de caixa (por vencimento)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Lancamento:
    """Uma conta a receber (tipo "Receita") ou a pagar (tipo "Despesa") prevista no fluxo."""

    id: int
    vencimento: date
    valor: Decimal | None
    status: str
    descricao: str
    detalhe: str


def descrever_receita(
    id: int,
    contrato_numero: int | None = None,
    aluno_do_contrato: str | None = None,
    plano: str | None = None,
    reserva_aluno: str | None = None,
    reserva_hora=None,
    reserva_servico: str | None = None,
    tem_reserva: bool = False,
) -> tuple[str, str]:
    """``(descricao, detalhe)`` de uma receita no fluxo de caixa.

    - de contrato: ``"Contrato #N - Aluno"`` / nome do plano (ou "Sem plano");
    - de aula avulsa (reserva): ``"Aula avulsa - Aluno (HH:MM)"`` / serviço (ou "Aula");
    - lançamento manual: ``"Receita #id"`` / ``"Lancamento manual"``.
    """
    if contrato_numero is not None:
        return f"Contrato #{contrato_numero} - {aluno_do_contrato or 'Sem aluno'}", plano or "Sem plano"
    if tem_reserva or reserva_aluno is not None:
        cliente = reserva_aluno or "Sem aluno"
        horario = f"{reserva_hora:%H:%M}" if reserva_hora else ""
        return f"Aula avulsa - {cliente}" + (f" ({horario})" if horario else ""), reserva_servico or "Aula"
    return f"Receita #{id}", "Lancamento manual"


def descrever_despesa(fornecedor: str | None, categoria: str | None, subcategoria: str | None) -> tuple[str, str]:
    """``(descricao, detalhe)`` de uma despesa: fornecedor / ``"Categoria"`` ou ``"Categoria / Subcategoria"``."""
    cat = categoria or "Sem categoria"
    return fornecedor or "Sem fornecedor", cat if not subcategoria else f"{cat} / {subcategoria}"


def saldo_bancario_base(saldo_inicial_total: Decimal, entradas_anteriores: Decimal, saidas_anteriores: Decimal) -> Decimal:
    """Saldo dos bancos no início do período: saldo inicial das contas ATIVAS + entradas - saídas anteriores ao período."""
    return saldo_inicial_total + entradas_anteriores - saidas_anteriores


@dataclass(frozen=True)
class DiaFluxo:
    data: date
    receitas: Decimal
    despesas: Decimal
    saldo: Decimal


@dataclass(frozen=True)
class SemanaFluxo:
    inicio: date
    fim: date
    receitas: Decimal
    despesas: Decimal
    saldo: Decimal


@dataclass(frozen=True)
class LinhaFluxo:
    data: date
    tipo: str  # "Receita" | "Despesa"
    origem: str
    descricao: str
    detalhe: str
    status: str
    valor: Decimal


@dataclass
class FluxoCaixa:
    saldo_bancario_base: Decimal
    saldo_projetado_final: Decimal
    total_receitas: Decimal
    total_despesas: Decimal
    lancamentos: list[LinhaFluxo] = field(default_factory=list)
    saldo_diario: list[DiaFluxo] = field(default_factory=list)
    saldo_semanal: list[SemanaFluxo] = field(default_factory=list)


def fluxo_de_caixa(
    receitas: Iterable[Lancamento],
    despesas: Iterable[Lancamento],
    inicio: date,
    fim: date,
    saldo_base: Decimal,
) -> FluxoCaixa:
    """Fluxo de caixa PROJETADO do período, por data de vencimento.

    - entram contas com ``inicio <= vencimento <= fim`` e status diferente de CANCELADO (pagas e abertas somam;
      o realizado dos bancos entra só em ``saldo_base``);
    - ``lancamentos`` ordenados por (data, receita antes de despesa, id);
    - ``saldo_diario``: um item por dia, saldo acumulado a partir de ``saldo_base``;
    - ``saldo_semanal``: blocos de 7 dias a partir de ``inicio`` (o último pode ser menor), saldo acumulado.
    """
    rec = [r for r in receitas if r.status != "CANCELADO" and inicio <= r.vencimento <= fim]
    des = [d for d in despesas if d.status != "CANCELADO" and inicio <= d.vencimento <= fim]
    por_dia_rec: dict[date, Decimal] = {}
    por_dia_des: dict[date, Decimal] = {}
    linhas: list[tuple[date, int, int, LinhaFluxo]] = []
    for r in rec:
        valor = r.valor or ZERO
        por_dia_rec[r.vencimento] = por_dia_rec.get(r.vencimento, ZERO) + valor
        linhas.append((r.vencimento, 0, r.id, LinhaFluxo(r.vencimento, "Receita", "Contas a Receber", r.descricao, r.detalhe, r.status, valor)))
    for d in des:
        valor = d.valor or ZERO
        por_dia_des[d.vencimento] = por_dia_des.get(d.vencimento, ZERO) + valor
        linhas.append((d.vencimento, 1, d.id, LinhaFluxo(d.vencimento, "Despesa", "Contas a Pagar", d.descricao, d.detalhe, d.status, valor)))
    linhas.sort(key=lambda x: (x[0], x[1], x[2]))

    diario: list[DiaFluxo] = []
    acumulado = saldo_base
    total_rec = ZERO
    total_des = ZERO
    cursor = inicio
    while cursor <= fim:
        r_dia = por_dia_rec.get(cursor, ZERO)
        d_dia = por_dia_des.get(cursor, ZERO)
        total_rec += r_dia
        total_des += d_dia
        acumulado += r_dia - d_dia
        diario.append(DiaFluxo(cursor, r_dia, d_dia, acumulado))
        cursor += timedelta(days=1)

    semanal: list[SemanaFluxo] = []
    semana_inicio = inicio
    acumulado_sem = saldo_base
    while semana_inicio <= fim:
        semana_fim = min(semana_inicio + timedelta(days=6), fim)
        r_sem = sum((x.receitas for x in diario if semana_inicio <= x.data <= semana_fim), ZERO)
        d_sem = sum((x.despesas for x in diario if semana_inicio <= x.data <= semana_fim), ZERO)
        acumulado_sem += r_sem - d_sem
        semanal.append(SemanaFluxo(semana_inicio, semana_fim, r_sem, d_sem, acumulado_sem))
        semana_inicio = semana_fim + timedelta(days=1)

    return FluxoCaixa(
        saldo_bancario_base=saldo_base,
        saldo_projetado_final=saldo_base + total_rec - total_des,
        total_receitas=total_rec,
        total_despesas=total_des,
        lancamentos=[x[3] for x in linhas],
        saldo_diario=diario,
        saldo_semanal=semanal,
    )


def deslocar_mes_limitado(base: date, meses: int) -> date:
    """``base + meses`` com o dia limitado ao ÚLTIMO dia do mês de destino (31/03 - 1 mês = 28/02).

    Diferente de ``add_months`` (que limita a 28): é o ``_shift_month_clamped`` usado no comparativo do fluxo.
    """
    total = (base.month - 1) + meses
    ano = base.year + total // 12
    mes = total % 12 + 1
    return date(ano, mes, min(base.day, calendar.monthrange(ano, mes)[1]))


@dataclass(frozen=True)
class ComparativoMesAnterior:
    periodo: str
    receitas: Decimal
    despesas: Decimal
    saldo: Decimal
    delta_receitas: Decimal
    delta_despesas: Decimal
    delta_saldo: Decimal


def periodo_anterior(inicio: date, fim: date) -> tuple[date, date]:
    """Mesmo intervalo deslocado 1 mês para trás (dia limitado ao fim do mês)."""
    return deslocar_mes_limitado(inicio, -1), deslocar_mes_limitado(fim, -1)


def comparar_com_mes_anterior(atual: FluxoCaixa, anterior: FluxoCaixa, inicio_anterior: date, fim_anterior: date) -> ComparativoMesAnterior:
    """``comparativo_mes_anterior``: totais do período anterior e deltas (atual - anterior)."""
    return ComparativoMesAnterior(
        periodo=f"{inicio_anterior:%d/%m/%Y} a {fim_anterior:%d/%m/%Y}",
        receitas=anterior.total_receitas,
        despesas=anterior.total_despesas,
        saldo=anterior.saldo_projetado_final,
        delta_receitas=atual.total_receitas - anterior.total_receitas,
        delta_despesas=atual.total_despesas - anterior.total_despesas,
        delta_saldo=atual.saldo_projetado_final - anterior.saldo_projetado_final,
    )


# ---------------------------------------------------------------------------
# DRE (por pagamento)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReceitaRecebida:
    valor: Decimal | None
    pagamento: date | None
    status: str = "PAGO"
    plano: str | None = None
    categoria: str | None = None
    subcategoria: str | None = None


@dataclass(frozen=True)
class DespesaPaga:
    valor: Decimal | None
    pagamento: date | None
    status: str = "PAGO"
    categoria: str | None = None
    subcategoria: str | None = None


@dataclass
class Dre:
    receita_bruta: Decimal
    deducoes: Decimal
    receita_liquida: Decimal
    custo_direto: Decimal
    lucro_bruto: Decimal
    despesas_operacionais: Decimal
    resultado_final: Decimal
    resultado_label: str
    saldo_bancario_anterior: Decimal
    saldo_bancario_final: Decimal
    receitas_por_plano: list[tuple[str, Decimal]] = field(default_factory=list)
    receitas_por_categoria: list[tuple[str, Decimal]] = field(default_factory=list)
    receitas_por_subcategoria: list[tuple[str, Decimal]] = field(default_factory=list)
    despesas_por_categoria: list[tuple[str, Decimal]] = field(default_factory=list)
    despesas_por_subcategoria: list[tuple[str, Decimal]] = field(default_factory=list)


def ultimo_dia_do_mes_anterior(inicio: date) -> date:
    """Último dia do mês anterior ao de ``inicio`` (corte do saldo bancário anterior da DRE)."""
    return inicio.replace(day=1) - timedelta(days=1)


def _agrupar(pares: Iterable[tuple[str | None, Decimal]], rotulo_vazio: str) -> list[tuple[str, Decimal]]:
    """Soma por chave BRUTA (nome; ``None`` = sem vínculo), rótulo "Sem ..." para nulo/vazio, maior total primeiro.

    Planos/categorias diferentes com o MESMO nome são somados juntos (o antigo agrupa por nome). Empate de total
    desempata pelo rótulo (o antigo não definia ordem de desempate).
    """
    somas: dict[str | None, Decimal] = {}
    for chave, valor in pares:
        somas[chave] = somas.get(chave, ZERO) + valor
    linhas = [((chave or rotulo_vazio), total) for chave, total in somas.items()]
    linhas.sort(key=lambda x: (-x[1], x[0]))
    return linhas


def dre(
    receitas: Iterable[ReceitaRecebida],
    despesas: Iterable[DespesaPaga],
    inicio: date,
    fim: date,
    saldo_anterior: Decimal,
) -> Dre:
    """DRE por regime de CAIXA: só contas PAGAS com ``inicio <= pagamento <= fim``.

    - receita bruta = soma das receitas; deduções e custo direto = 0 (o antigo não os calcula);
    - resultado = receita líquida - despesas; rótulo ``"Lucro"`` se >= 0, senão ``"Prejuizo"``;
    - saldo bancário final = saldo anterior + receita bruta - despesas (movimentos do período não entram);
    - receitas por plano / categoria / subcategoria do PLANO do contrato (avulsas e lançamentos manuais, sem
      contrato, caem em "Sem plano" / "Sem categoria" / "Sem subcategoria"); despesas por categoria e subcategoria.
    """
    rec = [r for r in receitas if r.status == "PAGO" and r.pagamento is not None and inicio <= r.pagamento <= fim]
    des = [d for d in despesas if d.status == "PAGO" and d.pagamento is not None and inicio <= d.pagamento <= fim]
    bruta = sum((r.valor or ZERO for r in rec), ZERO)
    operacionais = sum((d.valor or ZERO for d in des), ZERO)
    liquida = bruta - ZERO
    lucro_bruto = liquida - ZERO
    resultado = lucro_bruto - operacionais
    return Dre(
        receita_bruta=bruta,
        deducoes=ZERO,
        receita_liquida=liquida,
        custo_direto=ZERO,
        lucro_bruto=lucro_bruto,
        despesas_operacionais=operacionais,
        resultado_final=resultado,
        resultado_label="Lucro" if resultado >= 0 else "Prejuizo",
        saldo_bancario_anterior=saldo_anterior,
        saldo_bancario_final=saldo_anterior + bruta - operacionais,
        receitas_por_plano=_agrupar(((r.plano, r.valor or ZERO) for r in rec), "Sem plano"),
        receitas_por_categoria=_agrupar(((r.categoria, r.valor or ZERO) for r in rec), "Sem categoria"),
        receitas_por_subcategoria=_agrupar(((r.subcategoria, r.valor or ZERO) for r in rec), "Sem subcategoria"),
        despesas_por_categoria=_agrupar(((d.categoria, d.valor or ZERO) for d in des), "Sem categoria"),
        despesas_por_subcategoria=_agrupar(((d.subcategoria, d.valor or ZERO) for d in des), "Sem subcategoria"),
    )


# ---------------------------------------------------------------------------
# Contas a pagar recorrentes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanoRecorrenciaPagar:
    #: quantidade a gravar na conta original (recorrência informada com quantidade < 1 vira 1)
    quantidade: int
    #: vencimentos das contas ADICIONAIS (a original já existe e mantém o vencimento digitado)
    vencimentos_adicionais: list[date]


def planejar_recorrencia_pagar(vencimento: date, recorrencia: str | None, quantidade: int | None) -> PlanoRecorrenciaPagar:
    """Lançamentos extras de uma conta a pagar recorrente.

    - sem recorrência: nada a gerar (a quantidade informada é mantida);
    - ``quantidade`` total (incluindo a original); < 1 vira 1;
    - SEMANAL: ``+7*idx`` dias; ANUAL: ``+12*idx`` meses; qualquer outra recorrência (MENSAL): ``+idx`` meses,
      sempre com dia <= 28 (``add_months``). A conta original NÃO tem o dia limitado.

    # COMPORTAMENTO ANTIGO / ATENÇÃO: as contas geradas nascem com a MESMA ``recorrencia`` e ``recorrencia_quantidade``
    da original. Só a original dispara a geração (é criada pelo formulário); editar uma cópia ou recriá-la a
    partir dela duplicaria lançamentos. No sistema novo grave as cópias sem recorrência (ou com um vínculo ``grupo``)
    e NUNCA regenere em cascata. Esta função é pura: chamá-la de novo para a original reproduz a mesma lista.
    """
    qtd = quantidade or 0
    if recorrencia and qtd < 1:
        qtd = 1
    extras: list[date] = []
    if recorrencia and qtd > 1:
        for idx in range(1, qtd):
            if recorrencia == "SEMANAL":
                extras.append(vencimento + timedelta(days=7 * idx))
            elif recorrencia == "ANUAL":
                extras.append(add_months(vencimento, 12 * idx))
            else:
                extras.append(add_months(vencimento, idx))
    return PlanoRecorrenciaPagar(qtd, extras)


# ---------------------------------------------------------------------------
# Cobrança de aula avulsa (R12)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContaDeAulaAvulsa:
    valor: Decimal
    vencimento: date
    competencia: str
    status: str = "ABERTO"


def conta_da_aula_avulsa(valor_aula: Decimal | None, data_aula: date, recorrencia_pacote: str) -> ContaDeAulaAvulsa | None:
    """Cada aula avulsa agendada gera UMA conta a receber de ``valor_aula``, vencendo no dia da aula, ABERTA.

    Valor 0/nulo (TotalPass, WellHub, cortesia, aula avaliativa) NÃO gera cobrança. A competência segue
    ``competencia_avulsa`` (mensal ``YYYY-MM`` ou semanal ISO). A existência de conta anterior para a mesma reserva
    (idempotência) é verificada por quem chama.
    """
    if not valor_aula or valor_aula <= 0:
        return None
    return ContaDeAulaAvulsa(valor_aula, data_aula, competencia_avulsa(data_aula, recorrencia_pacote))


def somar(valores: Sequence[Decimal | None]) -> Decimal:
    return sum((v or ZERO for v in valores), ZERO)
