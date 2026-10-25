"""R13 - exclusão de contrato (plano) e vigência na gestão de contratos.

Caracterização contra views.delete_view (Contrato), contratos_gestao e dashboard do sistema antigo
(ver golden_gen/gerar_golden.py, seção ``contratos``).
"""
from datetime import date

import pytest

from app.domain import contratos as ct
from tests.domain.golden import golden_contratos as g

# ---------------------------------------------------------------- reconstrução do cenário --------------------

def _contratos() -> list[ct.ContratoRef]:
    return [ct.ContratoRef(i, aluno, unidade, tipo, ini, fim) for i, aluno, unidade, tipo, ini, fim in g.CONTRATOS]


def _reservas(com_fk: dict[str, int] | None = None) -> list[ct.ReservaRef]:
    """``com_fk``: rótulo da reserva -> id do contrato (simula a FK nova preenchida pelo ETL)."""
    com_fk = com_fk or {}
    return [
        ct.ReservaRef(rid, aluno, sessao, data, unidade, tipo, status, com_fk.get(rotulo), avulso)
        for rid, rotulo, aluno, sessao, data, unidade, tipo, status, avulso, _evo in g.RESERVAS
    ]


def _contas() -> list[ct.ContaRef]:
    return [ct.ContaRef(i, contrato, status) for i, _rotulo, contrato, status in g.CONTAS]


def _rotulos_reservas(ids) -> list[str]:
    por_id = {r[0]: r[1] for r in g.RESERVAS}
    return sorted(por_id[i] for i in ids)


def _rotulos_contas(ids) -> list[str]:
    por_id = {c[0]: c[1] for c in g.CONTAS}
    return sorted(por_id[i] for i in ids)


def _com_historico() -> set[int]:
    return {r[0] for r in g.RESERVAS if r[9]}


C1, C2, C3 = (c[0] for c in g.CONTRATOS)


# ---------------------------------------------------------------- inferência antiga -----------------------------

def test_r13_plano_inferido_apaga_o_mesmo_que_o_antigo():
    contrato = _contratos()[0]
    plano = ct.plano_exclusao_inferido(contrato, _contas(), _reservas(), _com_historico())
    assert _rotulos_reservas(plano.reservas_ids) == g.RESERVAS_APAGADAS
    assert _rotulos_contas(plano.contas_receber_ids) == g.CONTAS_APAGADAS
    assert len(plano.sessoes_ids) == g.SESSOES_APAGADAS_QTD


def test_r13_resumo_da_tela_de_confirmacao_identico_ao_antigo():
    for rotulo, indice in (("c1", 0), ("c3", 2)):
        contrato = _contratos()[indice]
        plano = ct.plano_exclusao_inferido(contrato, _contas(), _reservas())
        assert plano.resumo == g.RESUMOS_CONFIRMACAO[rotulo]


def test_r13_contrato_do_outro_aluno_apaga_so_o_dele():
    plano = ct.plano_exclusao_inferido(_contratos()[2], _contas(), _reservas())
    assert _rotulos_contas(plano.contas_receber_ids) == ["c3_da_bia"]
    assert _rotulos_reservas(plano.reservas_ids) == ["r14_da_bia", "r1b_bia_na_compartilhada"]
    # a sessao compartilhada continua porque a Ana ainda esta nela: so a sessao da r14 esvazia
    assert len(plano.sessoes_ids) == 1


def test_r13_sessao_compartilhada_nao_e_apagada_enquanto_houver_reserva_de_outro_aluno():
    plano = ct.plano_exclusao_inferido(_contratos()[0], _contas(), _reservas())
    compartilhada = next(r.sessao_id for r in _reservas() if r.id and g.RESERVAS[[x[0] for x in g.RESERVAS].index(r.id)][1] == "r1_compartilhada_com_bia")
    # a Bia tambem esta nessa sessao, mas a r1 da Ana e a unica apagada ali; a da Bia permanece => sessao NAO apagada
    assert compartilhada not in plano.sessoes_ids


@pytest.mark.parametrize(
    "rotulo,cai",
    [
        ("r6_no_primeiro_dia", True), ("r7_no_ultimo_dia", True), ("r13_antes_do_inicio", False), ("r5_depois_do_fim", False),
        ("r3_outro_servico", False), ("r4_outra_unidade", False), ("r14_da_bia", False), ("r8_aula_avulsa_no_periodo", True),
        ("r9_concluida", True), ("r10_cancelada", True),
    ],
)
def test_r13_inferencia_periodo_unidade_servico_inclusive_nas_pontas(rotulo, cai):
    reserva = next(r for r, meta in zip(_reservas(), g.RESERVAS, strict=True) if meta[1] == rotulo)
    assert ct.reserva_cai_no_contrato_antigo(_contratos()[0], reserva) is cai


def test_r13_antigo_apaga_conta_paga_aula_avulsa_e_historico_clinico():
    """# COMPORTAMENTO ANTIGO (riscos): excluir contrato apaga contas PAGAS, aulas avulsas do período e as
    evoluções/avaliações das reservas apagadas (CASCADE)."""
    plano = ct.plano_exclusao_inferido(_contratos()[0], _contas(), _reservas(), _com_historico())
    assert _rotulos_contas(plano.contas_pagas_ids) == ["c1_pago"]
    assert _rotulos_reservas(plano.reservas_avulsas_atingidas) == ["r8_aula_avulsa_no_periodo"]
    assert _rotulos_reservas(plano.reservas_com_historico_clinico) == ["r9_concluida"]
    assert g.EVOLUCOES_RESTANTES == 0   # confirmado no antigo: a evolução sumiu junto


def test_r13_exige_confirmacao_explicita():
    assert g.SEM_CONFIRMAR[:2] == (302, True) and g.SEM_CONFIRMAR[2] == len(g.RESERVAS)
    assert ct.exige_confirmacao("1") is True
    for ruim in (None, "", "0", "true", "on", "2"):
        assert ct.exige_confirmacao(ruim) is False
    assert ct.MENSAGEM_CONFIRMAR_EXCLUSAO == "Confirme a exclusao do contrato."


# ---------------------------------------------------------------- forma nova (FK) -----------------------------

def test_r13_plano_por_fk_so_apaga_as_reservas_vinculadas_ao_contrato():
    vinculos = ct.vincular_reservas_aos_contratos(_contratos(), _reservas(), resolver_ambiguas=True)
    por_rotulo = {meta[1]: vinculos.vinculos[meta[0]] for meta in g.RESERVAS if meta[0] in vinculos.vinculos}
    contrato = _contratos()[0]
    plano = ct.plano_exclusao_por_fk(contrato, _contas(), _reservas(por_rotulo), _com_historico())
    # as aulas avulsas nao pertencem ao contrato; na FK elas ficam
    assert "r8_aula_avulsa_no_periodo" not in _rotulos_reservas(plano.reservas_ids)
    assert plano.reservas_avulsas_atingidas == []
    # a sobreposicao (r12) foi atribuida ao contrato mais recente (c2), entao a exclusao do c1 nao a leva
    assert "r12_na_sobreposicao" not in _rotulos_reservas(plano.reservas_ids)
    assert _rotulos_contas(plano.contas_receber_ids) == g.CONTAS_APAGADAS


def test_r13_conciliacao_inferido_x_fk_mostra_a_diferenca():
    vinculos = ct.vincular_reservas_aos_contratos(_contratos(), _reservas(), resolver_ambiguas=True)
    por_rotulo = {meta[1]: vinculos.vinculos[meta[0]] for meta in g.RESERVAS if meta[0] in vinculos.vinculos}
    contrato = _contratos()[0]
    inferido = ct.plano_exclusao_inferido(contrato, _contas(), _reservas())
    por_fk = ct.plano_exclusao_por_fk(contrato, _contas(), _reservas(por_rotulo))
    comparacao = ct.comparar_planos(inferido, por_fk)
    assert _rotulos_reservas(comparacao.so_no_inferido_reservas) == [
        "r12_na_sobreposicao", "r7_no_ultimo_dia", "r8_aula_avulsa_no_periodo",
    ]   # r7 (30/11) e r12 (25/11) tambem estao no periodo do contrato 2 (que comeca em 20/11)
    assert comparacao.so_na_fk_reservas == []
    assert comparacao.iguais is False


def test_r13_sem_sobreposicao_nem_avulsa_inferido_e_fk_coincidem():
    contrato = _contratos()[2]   # contrato da Bia
    reservas = _reservas()
    vinc = ct.vincular_reservas_aos_contratos(_contratos(), reservas)
    por_rotulo = {meta[1]: vinc.vinculos[meta[0]] for meta in g.RESERVAS if meta[0] in vinc.vinculos}
    inferido = ct.plano_exclusao_inferido(contrato, _contas(), reservas)
    por_fk = ct.plano_exclusao_por_fk(contrato, _contas(), _reservas(por_rotulo))
    assert ct.comparar_planos(inferido, por_fk).iguais


def test_r13_vinculo_das_reservas_para_o_etl():
    v = ct.vincular_reservas_aos_contratos(_contratos(), _reservas())
    por_rotulo = {meta[1]: meta[0] for meta in g.RESERVAS}
    assert v.vinculos[por_rotulo["r2_sozinha"]] == C1
    assert v.vinculos[por_rotulo["r11_so_do_contrato_2"]] == C2
    assert v.vinculos[por_rotulo["r14_da_bia"]] == C3
    # dois contratos da Ana cobrem 25/11 e 30/11
    assert v.ambiguas == {por_rotulo["r12_na_sobreposicao"]: [C1, C2], por_rotulo["r7_no_ultimo_dia"]: [C1, C2]}
    assert por_rotulo["r8_aula_avulsa_no_periodo"] in v.sem_contrato      # aula avulsa nunca e do contrato
    assert por_rotulo["r4_outra_unidade"] in v.sem_contrato
    assert por_rotulo["r13_antes_do_inicio"] in v.sem_contrato
    resolvido = ct.vincular_reservas_aos_contratos(_contratos(), _reservas(), resolver_ambiguas=True)
    assert resolvido.vinculos[por_rotulo["r12_na_sobreposicao"]] == C2 and resolvido.ambiguas == {}
    assert resolvido.vinculos[por_rotulo["r7_no_ultimo_dia"]] == C2


def test_r13_reservas_por_sessao():
    assert ct.reservas_por_sessao(_reservas())[next(r.sessao_id for r in _reservas())] >= 1


# ---------------------------------------------------------------- vigência ---------------------------------------

def _gestao_rotulo(filtro):
    return g.GESTAO[filtro]


@pytest.mark.parametrize("filtro", ["ativos", "vencendo", "vencidos", "todos", "xyz", ""])
def test_r13_gestao_identica_ao_antigo(filtro):
    hoje = g.HOJE
    esperado = g.GESTAO[filtro]
    efetivo = ct.filtro_normalizado(filtro)
    assert efetivo == esperado["filtro_efetivo"]
    obtido = []
    for rotulo, fim, inicio in g.FINS:
        if ct.passa_no_filtro(efetivo, inicio, fim, hoje):
            s = ct.situacao_do_contrato(fim, hoje)
            obtido.append((rotulo, s.dias_restantes, s.situacao, s.badge))
    assert sorted(obtido) == sorted(esperado["contratos"])
    resumo = ct.resumo_gestao([(i, f) for _, f, i in g.FINS], hoje)
    assert resumo == esperado["resumo"]


@pytest.mark.parametrize(
    "dias,situacao,badge",
    [(-1, "Vencido", "danger"), (0, "Vence esta semana", "danger"), (7, "Vence esta semana", "danger"),
     (8, "Vence em breve", "warning"), (30, "Vence em breve", "warning"), (31, "Vigente", "success"), (400, "Vigente", "success")],
)
def test_r13_situacao_por_dias_restantes(dias, situacao, badge):
    from datetime import timedelta

    hoje = date(2026, 10, 25)
    s = ct.situacao_do_contrato(hoje + timedelta(days=dias), hoje)
    assert (s.dias_restantes, s.situacao, s.badge) == (dias, situacao, badge)


def test_r13_vencendo_nao_olha_o_inicio_mas_ativo_olha():
    hoje = date(2026, 10, 25)
    inicio, fim = date(2026, 10, 26), date(2026, 11, 14)   # comeca amanha
    assert ct.esta_vencendo(fim, hoje) and not ct.esta_ativo(inicio, fim, hoje)
    assert ct.esta_ativo(hoje, hoje, hoje)   # comeca e termina hoje: ativo


def test_r13_painel_contratos_vencendo_em_7_dias_identico_ao_antigo():
    hoje = g.HOJE
    n = ct.contratos_vencendo_no_painel([f for _, f, _ in g.FINS], hoje)
    assert n == g.CONTRATOS_VENCENDO_PAINEL
    assert ct.alertas_do_painel(0, n) == g.ALERTAS
    assert ct.alertas_do_painel(3, 0) == ["3 faturas em atraso"]
    assert ct.alertas_do_painel(0, 0) == []
