"""R7 e R12 - financeiro: atraso derivado, fluxo de caixa, DRE, recorrência de contas a pagar, cobrança de aula avulsa.

Caracterização contra _build_fluxo_caixa_data_for_period, dre_relatorio/dre_view, contas_pagar_list, create_view
(recorrência) e aluno_aula_avulsa_agenda do sistema antigo (ver golden_gen/gerar_golden.py).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain import financeiro as fin
from tests.domain.golden import golden_avulsa as ga
from tests.domain.golden import golden_financeiro as g


# ---------------------------------------------------------------- entradas reconstruídas do golden ------------

def _receitas() -> list[fin.Lancamento]:
    lista = []
    for r in g.RECEITAS:
        descricao, detalhe = fin.descrever_receita(
            r["id"], r["contrato_cd"], r["aluno_do_contrato"], r["plano"], r["reserva_aluno"], r["reserva_hora"],
            r["reserva_servico"], tem_reserva=r["reserva_aluno"] is not None,
        )
        lista.append(fin.Lancamento(r["id"], r["vencimento"], r["valor"], r["status"], descricao, detalhe))
    return lista


def _despesas() -> list[fin.Lancamento]:
    lista = []
    for d in g.DESPESAS:
        descricao, detalhe = fin.descrever_despesa(d["fornecedor"], d["categoria"], d["subcategoria"])
        lista.append(fin.Lancamento(d["id"], d["vencimento"], d["valor"], d["status"], descricao, detalhe))
    return lista


def _saldo_base(inicio: date, todas: bool, conta_id) -> Decimal:
    ativas = {c[0] for c in g.CONTAS_BANCO if c[2]}
    if todas:
        contas = ativas
    else:
        contas = {conta_id}
    saldo_inicial = sum((c[1] for c in g.CONTAS_BANCO if c[0] in contas and (todas and c[2] or not todas)), Decimal("0"))
    entradas = sum((m[2] for m in g.MOVIMENTOS if m[0] in contas and m[1] == "ENTRADA" and m[3] < inicio), Decimal("0"))
    saidas = sum((m[2] for m in g.MOVIMENTOS if m[0] in contas and m[1] == "SAIDA" and m[3] < inicio), Decimal("0"))
    return fin.saldo_bancario_base(saldo_inicial, entradas, saidas)


@pytest.mark.parametrize("inicio,fim,todas,conta,esperado", g.FLUXOS)
def test_r7_fluxo_de_caixa_identico_ao_antigo(inicio, fim, todas, conta, esperado):
    base = _saldo_base(inicio, todas, None if todas else conta)
    f = fin.fluxo_de_caixa(_receitas(), _despesas(), inicio, fim, base)
    assert f.saldo_bancario_base == esperado["base"]
    assert f.saldo_projetado_final == esperado["final"]
    assert f.total_receitas == esperado["receitas"]
    assert f.total_despesas == esperado["despesas"]
    assert [(x.data, x.tipo, x.origem, x.descricao, x.detalhe, x.status, x.valor) for x in f.lancamentos] == esperado["lancamentos"]
    assert [(x.data, x.receitas, x.despesas, x.saldo) for x in f.saldo_diario] == esperado["diario"]
    assert [(x.inicio, x.fim, x.receitas, x.despesas, x.saldo) for x in f.saldo_semanal] == esperado["semanal"]


def test_r7_fluxo_exclui_cancelado_e_fora_do_periodo_por_vencimento():
    receitas = [
        fin.Lancamento(1, date(2026, 10, 5), Decimal("100"), "PAGO", "a", "x"),
        fin.Lancamento(2, date(2026, 10, 6), Decimal("50"), "CANCELADO", "b", "x"),
        fin.Lancamento(3, date(2026, 11, 1), Decimal("70"), "ABERTO", "c", "x"),
    ]
    f = fin.fluxo_de_caixa(receitas, [], date(2026, 10, 1), date(2026, 10, 31), Decimal("10"))
    assert f.total_receitas == Decimal("100")
    assert [x.descricao for x in f.lancamentos] == ["a"]
    assert f.saldo_projetado_final == Decimal("110")
    # a data de pagamento NAO importa para o fluxo (so o vencimento)


def test_r7_fluxo_semanas_de_7_dias_a_partir_do_inicio_com_ultima_curta():
    f = fin.fluxo_de_caixa([], [], date(2026, 10, 1), date(2026, 10, 17), Decimal("0"))
    assert [(s.inicio, s.fim) for s in f.saldo_semanal] == [
        (date(2026, 10, 1), date(2026, 10, 7)), (date(2026, 10, 8), date(2026, 10, 14)), (date(2026, 10, 15), date(2026, 10, 17)),
    ]
    assert len(f.saldo_diario) == 17


def test_r7_valor_nulo_conta_como_zero_e_receita_vem_antes_da_despesa_no_mesmo_dia():
    r = [fin.Lancamento(9, date(2026, 10, 5), None, "ABERTO", "r", "x")]
    d = [fin.Lancamento(1, date(2026, 10, 5), Decimal("5"), "AGENDADO", "d", "x")]
    f = fin.fluxo_de_caixa(r, d, date(2026, 10, 5), date(2026, 10, 5), Decimal("0"))
    assert [x.tipo for x in f.lancamentos] == ["Receita", "Despesa"]
    assert f.total_receitas == Decimal("0")


@pytest.mark.parametrize("base,n,esperado", g.SHIFT_CLAMPED)
def test_r7_deslocar_mes_limitado_identico_ao_antigo(base, n, esperado):
    assert fin.deslocar_mes_limitado(base, n) == esperado


def test_r7_comparativo_com_mes_anterior_identico_ao_antigo():
    inicio, fim = date(2026, 10, 1), date(2026, 10, 31)
    atual_ref = g.FLUXOS[0]
    assert (atual_ref[0], atual_ref[1]) == (inicio, fim)
    ini_ant, fim_ant = fin.periodo_anterior(inicio, fim)
    atual = fin.fluxo_de_caixa(_receitas(), _despesas(), inicio, fim, _saldo_base(inicio, True, None))
    anterior = fin.fluxo_de_caixa(_receitas(), _despesas(), ini_ant, fim_ant, _saldo_base(ini_ant, True, None))
    c = fin.comparar_com_mes_anterior(atual, anterior, ini_ant, fim_ant)
    esperado = g.COMPARATIVO
    assert c.periodo == esperado["periodo"]
    assert (c.receitas, c.despesas, c.saldo) == (esperado["receitas"], esperado["despesas"], esperado["saldo"])
    assert (c.delta_receitas, c.delta_despesas, c.delta_saldo) == (esperado["delta_receitas"], esperado["delta_despesas"], esperado["delta_saldo"])


# ---------------------------------------------------------------- DRE -----------------------------------------

def _recebidas():
    return [
        fin.ReceitaRecebida(r["valor"], r["pagamento"], r["status"], r["plano"], r["categoria"], r["subcategoria"])
        for r in g.RECEITAS
    ]


def _pagas():
    return [fin.DespesaPaga(d["valor"], d["pagamento"], d["status"], d["categoria"], d["subcategoria"]) for d in g.DESPESAS]


def _saldo_anterior_dre(inicio: date) -> Decimal:
    corte = fin.ultimo_dia_do_mes_anterior(inicio)
    saldo_inicial = sum((c[1] for c in g.CONTAS_BANCO if c[2]), Decimal("0"))
    entradas = sum((m[2] for m in g.MOVIMENTOS if m[1] == "ENTRADA" and m[3] <= corte), Decimal("0"))
    saidas = sum((m[2] for m in g.MOVIMENTOS if m[1] == "SAIDA" and m[3] <= corte), Decimal("0"))
    return fin.saldo_bancario_base(saldo_inicial, entradas, saidas)


@pytest.mark.parametrize("inicio_txt,fim_txt,esperado", g.DRES)
def test_r7_dre_identica_ao_antigo(inicio_txt, fim_txt, esperado):
    inicio, fim = date.fromisoformat(inicio_txt), date.fromisoformat(fim_txt)
    d = fin.dre(_recebidas(), _pagas(), inicio, fim, _saldo_anterior_dre(inicio))
    assert d.receita_bruta == esperado["receita_bruta"]
    assert d.despesas_operacionais == esperado["despesas_operacionais"]
    assert d.resultado_final == esperado["resultado_final"]
    assert d.resultado_label == esperado["resultado_label"]
    assert d.saldo_bancario_anterior == esperado["saldo_anterior"]
    assert d.saldo_bancario_final == esperado["saldo_final"]
    assert (d.receita_bruta, d.despesas_operacionais, d.resultado_final, d.resultado_label) == esperado["simples"]
    for atual, chave in [
        (d.receitas_por_plano, "por_plano"), (d.receitas_por_categoria, "por_categoria"),
        (d.receitas_por_subcategoria, "por_subcategoria"), (d.despesas_por_categoria, "desp_categoria"),
        (d.despesas_por_subcategoria, "desp_subcategoria"),
    ]:
        assert [(rot, float(total)) for rot, total in atual] == esperado[chave], chave


def test_r7_dre_por_pagamento_nao_por_vencimento():
    # receita vencida em 02/10 mas paga em 30/09 entra na DRE de setembro e nao na de outubro
    set_ = fin.dre(_recebidas(), _pagas(), date(2026, 9, 1), date(2026, 9, 30), Decimal("0"))
    out = fin.dre(_recebidas(), _pagas(), date(2026, 10, 1), date(2026, 10, 31), Decimal("0"))
    assert set_.receita_bruta == Decimal("450.00")
    assert out.receita_bruta == Decimal("963.33")


def test_r7_dre_avulsa_sem_plano_cai_no_bucket_sem_plano():
    d = fin.dre([fin.ReceitaRecebida(Decimal("80"), date(2026, 10, 1))], [], date(2026, 10, 1), date(2026, 10, 31), Decimal("0"))
    assert d.receitas_por_plano == [("Sem plano", Decimal("80"))]
    assert d.receitas_por_categoria == [("Sem categoria", Decimal("80"))]
    assert d.receitas_por_subcategoria == [("Sem subcategoria", Decimal("80"))]


def test_r7_dre_prejuizo_e_zero_a_zero_e_lucro():
    inicio, fim = date(2026, 10, 1), date(2026, 10, 31)
    assert fin.dre([], [fin.DespesaPaga(Decimal("1"), inicio)], inicio, fim, Decimal("0")).resultado_label == "Prejuizo"
    assert fin.dre([], [], inicio, fim, Decimal("0")).resultado_label == "Lucro"


def test_r7_dre_agrupa_planos_de_mesmo_nome():
    # COMPORTAMENTO ANTIGO: o agrupamento e pelo NOME do plano (dois planos "Pilates 2x" viram uma linha)
    rec = [fin.ReceitaRecebida(Decimal("10"), date(2026, 10, 1), plano="X"), fin.ReceitaRecebida(Decimal("5"), date(2026, 10, 2), plano="X")]
    assert fin.dre(rec, [], date(2026, 10, 1), date(2026, 10, 31), Decimal("0")).receitas_por_plano == [("X", Decimal("15"))]


# ---------------------------------------------------------------- atraso derivado ----------------------------

def test_r7_esta_atrasada_regra_basica():
    hoje = date(2026, 10, 25)
    assert fin.esta_atrasada("ABERTO", date(2026, 10, 24), hoje)
    assert not fin.esta_atrasada("ABERTO", date(2026, 10, 25), hoje)   # vence hoje nao e atraso
    assert not fin.esta_atrasada("ABERTO", date(2026, 10, 26), hoje)
    assert not fin.esta_atrasada("PAGO", date(2026, 1, 1), hoje)
    assert not fin.esta_atrasada("CANCELADO", date(2026, 1, 1), hoje)
    assert fin.esta_atrasada("ATRASADO", date(2026, 10, 1), hoje)
    assert fin.esta_atrasada("AGENDADO", date(2026, 10, 1), hoje)
    assert not fin.esta_atrasada("ABERTO", None, hoje)


def test_r7_status_exibido():
    hoje = date(2026, 10, 25)
    assert fin.status_exibido_pagar("AGENDADO", date(2026, 10, 1), hoje) == "ATRASADO"
    assert fin.status_exibido_pagar("AGENDADO", hoje, hoje) == "AGENDADO"
    assert fin.status_exibido_pagar("PAGO", date(2026, 10, 1), hoje) == "PAGO"
    assert fin.status_exibido_pagar("CANCELADO", date(2026, 10, 1), hoje) == "CANCELADO"
    assert fin.status_exibido_receber("ABERTO", date(2026, 10, 1), hoje) == "ATRASADO"
    assert fin.status_exibido_receber("ABERTO", hoje, hoje) == "ABERTO"
    assert fin.status_exibido_receber("PAGO", date(2026, 10, 1), hoje) == "PAGO"


@pytest.mark.parametrize("rotulo", ["tarde_brt", "noite_brt_ja_amanha_utc"])
def test_r7_atraso_identico_ao_antigo_e_hoje_correto_no_fuso_de_negocio(rotulo):
    agora = {"tarde_brt": datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc),
             "noite_brt_ja_amanha_utc": datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc)}[rotulo]
    esperado_antigo = g.ATRASO[rotulo]
    pagar = {d["id"]: d for d in g.DESPESAS}

    # 1) reproduz o antigo: "hoje" = data em UTC
    hoje_antigo = fin.hoje_utc_comportamento_antigo(agora)
    exibido = {i: fin.status_exibido_pagar(d["status"], d["vencimento"], hoje_antigo) for i, d in pagar.items()}
    assert exibido == esperado_antigo["pagar_display"]
    assert sorted(i for i, s in exibido.items() if s == "ATRASADO") == esperado_antigo["pagar_atrasadas_ids"]

    # 2) regra correta: "hoje" = data de Brasilia. 22h de 25/10 em Brasilia ainda e dia 25.
    hoje = fin.hoje_de_negocio(agora)
    assert hoje == date(2026, 10, 25)
    correto = {i: fin.status_exibido_pagar(d["status"], d["vencimento"], hoje) for i, d in pagar.items()}
    assert [i for i, s in correto.items() if s == "ATRASADO"] == [5]   # a conta 7 vence hoje e NAO esta atrasada


def test_r7_dashboard_de_receber_em_atraso_usa_data_local():
    hoje = date(2026, 10, 25)
    atrasadas = [r for r in g.RECEITAS if fin.esta_atrasada(r["status"], r["vencimento"], hoje)]
    assert len(atrasadas) == g.ATRASO["tarde_brt"]["receber_atrasadas_dashboard"] == g.ATRASO["noite_brt_ja_amanha_utc"]["receber_atrasadas_dashboard"]


def test_r7_hoje_de_negocio_sem_fuso_usa_a_propria_data():
    assert fin.hoje_de_negocio(datetime(2026, 10, 25, 23, 30)) == date(2026, 10, 25)
    assert fin.hoje_utc_comportamento_antigo(datetime(2026, 10, 25, 23, 30)) == date(2026, 10, 25)


# ---------------------------------------------------------------- recorrência de contas a pagar -----------------

@pytest.mark.parametrize("recorrencia,qtd,vencimento,http,criadas", g.RECORRENCIAS)
def test_r7_recorrencia_de_contas_a_pagar_identica_ao_antigo(recorrencia, qtd, vencimento, http, criadas):
    plano = fin.planejar_recorrencia_pagar(vencimento, recorrencia, qtd)
    esperado = [c[0] for c in criadas]
    assert [vencimento, *plano.vencimentos_adicionais] == esperado
    # a conta original grava a quantidade normalizada
    assert criadas[0][2] == plano.quantidade
    assert len(criadas) == max(1, 1 + len(plano.vencimentos_adicionais))


def test_r7_recorrencia_sem_regeneracao_em_cascata():
    """Os lançamentos extras são calculados SÓ a partir da conta original; chamar de novo com os mesmos dados dá o mesmo
    resultado e nenhuma cópia é re-expandida (as cópias antigas carregavam recorrencia/quantidade, mas nada as expandia)."""
    a = fin.planejar_recorrencia_pagar(date(2026, 10, 10), "MENSAL", 3)
    b = fin.planejar_recorrencia_pagar(date(2026, 10, 10), "MENSAL", 3)
    assert a == b and a.vencimentos_adicionais == [date(2026, 11, 10), date(2026, 12, 10)]
    # tratar uma copia como "original" regeraria 2 extras: por isso as copias NAO devem ser expandidas
    copia = fin.planejar_recorrencia_pagar(date(2026, 11, 10), "MENSAL", 3)
    assert copia.vencimentos_adicionais == [date(2026, 12, 10), date(2027, 1, 10)]


def test_r7_recorrencia_sem_tipo_nao_gera_nada():
    p = fin.planejar_recorrencia_pagar(date(2026, 10, 10), "", 5)
    assert p.vencimentos_adicionais == [] and p.quantidade == 5
    assert fin.planejar_recorrencia_pagar(date(2026, 10, 10), None, None) == fin.PlanoRecorrenciaPagar(0, [])


# ---------------------------------------------------------------- cobrança de aula avulsa (R12) ---------------

def _cenarios_confiaveis():
    return [c for c in ga.CENARIOS if c["rotulo"] != "dois_servicos_no_horario"]


@pytest.mark.parametrize("cenario", _cenarios_confiaveis(), ids=lambda c: c["rotulo"])
def test_r12_aula_avulsa_conta_por_aula_identica_ao_antigo(cenario):
    from app.domain import agenda as ag
    from app.domain import precos

    recorrencia_plano, valor_plano = cenario["plano"]
    quantidade, informado, inicio, slot = cenario["entrada"]
    p = precos.precificar_aula_avulsa(Decimal(valor_plano), quantidade, informado, recorrencia_plano)
    pacote = cenario["pacote"]
    assert (p.recorrencia, p.quantidade, p.valor_base, p.valor_total) == (pacote["recorrencia"], pacote["quantidade"], pacote["valor_aula"], pacote["valor_total"])
    fim = precos.data_fim_aula_avulsa(inicio, p.recorrencia, p.quantidade)
    assert fim == pacote["fim"]

    dia, _, _ = ag.interpretar_valor_slot(slot)
    datas = [d.data for d in ag.datas_aula_avulsa(inicio, dia, p.recorrencia, p.quantidade, fim) if not d.fora_do_periodo]
    contas = [fin.conta_da_aula_avulsa(p.valor_base, d, p.recorrencia) for d in datas]
    esperado = [(c[0], c[1], c[2], c[3]) for c in cenario["contas"]]
    obtido = [(c.vencimento, c.competencia, c.valor, c.status) for c in contas if c is not None]
    assert obtido == esperado
    assert [(d, "Pilates") for d in datas] == cenario["reservas"]


def test_r12_valor_zero_nao_gera_cobranca_cortesia_totalpass_wellhub():
    assert fin.conta_da_aula_avulsa(Decimal("0"), date(2026, 11, 2), "SEMANAL") is None
    assert fin.conta_da_aula_avulsa(None, date(2026, 11, 2), "SEMANAL") is None
    assert fin.conta_da_aula_avulsa(Decimal("-5"), date(2026, 11, 2), "SEMANAL") is None
    c = fin.conta_da_aula_avulsa(Decimal("80"), date(2026, 11, 2), "SEMANAL")
    assert (c.valor, c.vencimento, c.competencia, c.status) == (Decimal("80"), date(2026, 11, 2), "2026-45", "ABERTO")


def test_r12_comportamento_antigo_horario_com_dois_servicos_duplica_reserva_e_cobranca():
    """# COMPORTAMENTO ANTIGO / BUG: com um horario de funcionamento que atende 2 servicos, a aula avulsa cria uma
    reserva E uma conta a receber POR SERVICO (cobranca em dobro). O dominio novo cobra uma vez por aula."""
    c = next(c for c in ga.CENARIOS if c["rotulo"] == "dois_servicos_no_horario")
    assert len(c["reservas"]) == 4 and len(c["contas"]) == 4
    assert c["entrada"][0] == 2   # pacote de 2 aulas, mas 4 cobrancas de 80
