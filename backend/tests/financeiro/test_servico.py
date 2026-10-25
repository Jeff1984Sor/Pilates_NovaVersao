"""Funções estáveis de `financeiro/servico.py` usadas por outros módulos (R1/R2/R7/R12)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.financeiro import servico
from app.modules.financeiro.models import ContaReceber, StatusReceber
from app.modules.financeiro.servico import ErroDeNegocio


def test_gerar_contas_do_contrato_segue_r2_dia_limitado_a_28(db, cenario):
    # contrato iniciado em 31/01/2026, plano de 3 meses, parcela de R$ 300,00 (R1: 300 x 3 = 900)
    contas = servico.gerar_contas_do_contrato(db, cenario.contrato)
    db.commit()
    assert [c.vencimento for c in contas] == [date(2026, 1, 28), date(2026, 2, 28), date(2026, 3, 28)]
    assert [c.competencia for c in contas] == ["2026-01", "2026-02", "2026-03"]
    assert all(c.valor == Decimal("300.00") and c.status == StatusReceber.ABERTO for c in contas)
    assert all(c.aluno_id == cenario.aluno.id and c.contrato_id == cenario.contrato.id for c in contas)
    assert sum(c.valor for c in contas) == Decimal("900.00")


def test_gerar_contas_do_contrato_nao_duplica(db, cenario):
    servico.gerar_contas_do_contrato(db, cenario.contrato)
    db.commit()
    with pytest.raises(ErroDeNegocio):
        servico.gerar_contas_do_contrato(db, cenario.contrato)


def test_gerar_contas_contrato_semanal(db, cenario):
    from app.modules.cadastros.models import Recorrencia

    c = cenario.contrato
    c.recorrencia = Recorrencia.SEMANAL
    c.data_inicio, c.data_fim = date(2026, 3, 2), date(2026, 3, 23)
    contas = servico.gerar_contas_do_contrato(db, c)
    assert [x.vencimento for x in contas] == [date(2026, 3, 2), date(2026, 3, 9), date(2026, 3, 16), date(2026, 3, 23)]
    assert contas[0].competencia == "2026-10"  # semana ISO


def _reserva(db, cenario):
    from datetime import time

    from app.modules.agenda.models import AulaSessao, Reserva

    s = AulaSessao(unidade_id=cenario.unidade.id, tipo_servico_id=cenario.servico.id, profissional_id=cenario.prof.id,
                   data=date(2026, 10, 27), hora_inicio=time(9), hora_fim=time(10))
    db.add(s)
    db.flush()
    r = Reserva(aluno_id=cenario.aluno.id, aula_sessao_id=s.id)
    db.add(r)
    db.flush()
    return r


def test_aula_avulsa_gera_uma_conta_com_competencia_mensal_ou_semanal(db, cenario):
    r = _reserva(db, cenario)
    c = servico.criar_conta_aula_avulsa(db, aluno_id=cenario.aluno.id, reserva_id=r.id, valor_aula=Decimal("80"),
                                        data_aula=date(2026, 10, 27), recorrencia_pacote="MENSAL")
    assert c.valor == Decimal("80") and c.vencimento == date(2026, 10, 27) and c.competencia == "2026-10"
    assert c.status == StatusReceber.ABERTO and c.reserva_id == r.id
    # idempotente: a mesma reserva devolve a mesma conta
    c2 = servico.criar_conta_aula_avulsa(db, aluno_id=cenario.aluno.id, reserva_id=r.id, valor_aula=Decimal("80"),
                                         data_aula=date(2026, 10, 27), recorrencia_pacote="MENSAL")
    assert c2.id == c.id
    assert db.query(ContaReceber).count() == 1


@pytest.mark.parametrize("valor", [None, Decimal("0")])
def test_aula_avulsa_valor_zero_nao_cobra(db, cenario, valor):
    r = _reserva(db, cenario)
    assert servico.criar_conta_aula_avulsa(db, aluno_id=cenario.aluno.id, reserva_id=r.id, valor_aula=valor,
                                           data_aula=date(2026, 10, 27)) is None
    assert db.query(ContaReceber).count() == 0


def test_resumo_financeiro_do_aluno(db, cenario):
    contas = servico.gerar_contas_do_contrato(db, cenario.contrato)  # 28/01, 28/02, 28/03 de 2026
    contas[0].status, contas[0].pagamento = StatusReceber.PAGO, date(2026, 1, 28)
    db.commit()
    hoje = date(2026, 3, 1)  # 28/02 já venceu; 28/03 ainda não
    r = servico.resumo_financeiro_do_aluno(db, cenario.aluno.id, hoje=hoje)
    assert (r.total_pago, r.total_atrasado, r.total_aberto) == (Decimal("300.00"), Decimal("300.00"), Decimal("300.00"))
    assert (r.qtd_pago, r.qtd_atrasado, r.qtd_aberto) == (1, 1, 1)
    assert r.proximo_vencimento == date(2026, 3, 28) and r.em_dia is False
    assert servico.resumo_financeiro_do_aluno(db, cenario.outro.id).em_dia is True


def test_hoje_de_negocio_usa_sao_paulo_e_nao_utc(monkeypatch):
    # 26/10 01:30 UTC = 25/10 22:30 em São Paulo
    monkeypatch.setattr(servico, "agora", lambda: datetime(2026, 10, 26, 1, 30, tzinfo=UTC))
    assert servico.hoje_de_negocio_agora() == date(2026, 10, 25)


def test_atrasado_derivado_respeita_fuso_no_resumo(db, cenario, monkeypatch):
    c = servico.lancar_avulso(db, aluno_id=cenario.aluno.id, descricao="Taxa", valor=Decimal("50"),
                              vencimento=date(2026, 10, 25))
    db.commit()
    monkeypatch.setattr(servico, "agora", lambda: datetime(2026, 10, 26, 1, 30, tzinfo=UTC))  # ainda 25/10 em SP
    assert servico.situacao_receber(c) == "ABERTO"  # vence hoje: não é atraso (o antigo, em UTC, diria ATRASADO)
    assert servico.resumo_financeiro_do_aluno(db, cenario.aluno.id).em_dia is True
    monkeypatch.setattr(servico, "agora", lambda: datetime(2026, 10, 26, 3, 30, tzinfo=UTC))  # 26/10 00:30 em SP
    assert servico.situacao_receber(c) == "ATRASADO"
