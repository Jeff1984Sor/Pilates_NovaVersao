"""gerar_agenda_do_contrato / obter_ou_criar_sessao / confirmação do aluno: o serviço que o módulo de contratos usa."""

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.domain.agenda import SelecaoHorario
from app.modules.agenda import servico
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.contratos.models import Contrato
from tests.agenda import fabrica

SEG, QUA = 0, 2
INICIO = date(2026, 11, 2)  # segunda
FIM = date(2026, 11, 29)  # domingo (4 semanas)


def total(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


def sel(dia, prof, ini=time(9, 0), fim=time(9, 50)):
    return SelecaoHorario(dia, ini, fim, prof.id)


def gerar(db, cenario, selecoes, **extra):
    args = dict(
        aluno_id=cenario.a1.id,
        contrato_id=None,
        unidade_id=cenario.un.id,
        tipo_servico_id=cenario.srv.id,
        data_inicio=INICIO,
        data_fim=FIM,
        selecoes=selecoes,
        aulas_por_semana=2,
    )
    return servico.gerar_agenda_do_contrato(db, **{**args, **extra})


@pytest.fixture
def com_horarios(db, cenario):
    fabrica.funcionamento(db, cenario.un, dias=(0, 1, 2, 3, 4), inicio=time(8, 0), fim=time(12, 0))
    db.commit()
    return cenario


def test_gera_uma_reserva_por_data_de_cada_horario(db, com_horarios):
    c = com_horarios
    r = gerar(db, c, [sel(SEG, c.prof), sel(QUA, c.prof)])
    db.commit()
    assert len(r.reservas_criadas) == 8 and r.sessoes_criadas == 8 and r.conflitos == [] and r.mensagem_conflitos is None
    datas = sorted(s.data for s in db.scalars(select(AulaSessao).where(AulaSessao.data >= INICIO)))
    assert [d.day for d in datas] == [2, 4, 9, 11, 16, 18, 23, 25]
    assert all(s.tipo_servico_id == c.srv.id for s in db.scalars(select(AulaSessao)))


def test_vincula_a_reserva_ao_contrato(db, com_horarios):
    c = com_horarios
    plano = fabrica.plano_avulso(db, c.srv, avulso=False)
    contrato = Contrato(aluno_id=c.a1.id, plano_id=plano.id, unidade_id=c.un.id, profissional_id=c.prof.id, valor_aula=Decimal("37.5"),
                        valor_parcela=Decimal("300"), valor_total=Decimal("900"), data_inicio=INICIO, data_fim=FIM)
    db.add(contrato)
    db.commit()
    r = gerar(db, c, [sel(SEG, c.prof)], contrato_id=contrato.id, aulas_por_semana=1)
    db.commit()
    assert len(r.reservas_criadas) == 4
    db.expire_all()
    assert {x.contrato_id for x in db.scalars(select(Reserva).where(Reserva.id.in_(r.reservas_criadas)))} == {contrato.id}


def test_validacao_recusa_antes_de_criar_qualquer_reserva(db, com_horarios):
    """# COMPORTAMENTO ANTIGO corrigido: o 1º horário não pode sobrar criado quando o 2º é recusado."""
    c = com_horarios
    antes_r, antes_s = total(db, Reserva), total(db, AulaSessao)
    erros = [
        ([sel(SEG, c.prof)], "Selecione exatamente 2 horarios por semana."),
        ([sel(SEG, c.prof), sel(SEG, c.prof)], "Nao repita o mesmo horario."),
        ([sel(SEG, c.prof), sel(SEG, c.prof, ini=time(10), fim=time(10, 50))], "Selecione apenas um horario por dia."),
        ([sel(SEG, c.prof), SelecaoHorario(QUA, time(9), time(9, 50), None)], "Selecione o professor em todos os horarios."),
        ([sel(SEG, c.prof), sel(QUA, c.prof, ini=time(13), fim=time(13, 50))], "Horario invalido para o dia selecionado."),
        ([sel(SEG, c.prof), SelecaoHorario(QUA, time(9), time(9, 50), c.prof.id, dia_informado=3)], "Dia e horario nao conferem."),
    ]
    for selecoes, mensagem in erros:
        with pytest.raises(servico.Invalido) as e:
            gerar(db, c, selecoes)
        assert e.value.mensagem == mensagem
    assert total(db, Reserva) == antes_r and total(db, AulaSessao) == antes_s


def test_professor_inexistente_recusa_sem_criar(db, com_horarios):
    c = com_horarios
    with pytest.raises(servico.Invalido):
        gerar(db, c, [SelecaoHorario(SEG, time(9), time(9, 50), 999), sel(QUA, c.prof)])
    assert total(db, Reserva) == 0


def test_nao_sobrescreve_profissional_de_aula_existente(db, com_horarios):
    """Existe uma aula TotalPass (sem profissional) no mesmo horário: continua sem profissional; o contrato usa a aula da professora."""
    c = com_horarios
    totalpass = fabrica.sessao(db, c.un, c.srv, None, dia=date(2026, 11, 2))
    outra = fabrica.profissional(db, "Outra")
    deles = fabrica.sessao(db, c.un, c.srv, outra, dia=date(2026, 11, 4))
    db.commit()
    gerar(db, c, [sel(SEG, c.prof), sel(QUA, c.prof)])
    db.commit()
    db.expire_all()
    assert db.get(AulaSessao, totalpass.id).profissional_id is None and db.get(AulaSessao, totalpass.id).reservas_ativas == 0
    assert db.get(AulaSessao, deles.id).profissional_id == outra.id and db.get(AulaSessao, deles.id).reservas_ativas == 0


def test_reaproveita_aula_existente_com_outros_alunos(db, com_horarios):
    c = com_horarios
    existente = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 2))
    db.commit()
    fabrica.reserva_direta(db, c.a2, existente)
    db.commit()
    r = gerar(db, c, [sel(SEG, c.prof)], aulas_por_semana=1)
    db.commit()
    assert len(r.reservas_criadas) == 4 and r.sessoes_criadas == 3  # a de 02/11 já existia
    db.expire_all()
    assert db.get(AulaSessao, existente.id).reservas_ativas == 2


def test_idempotente(db, com_horarios):
    c = com_horarios
    gerar(db, c, [sel(SEG, c.prof)], aulas_por_semana=1)
    db.commit()
    r = gerar(db, c, [sel(SEG, c.prof)], aulas_por_semana=1)
    assert r.reservas_criadas == [] and r.ja_existentes == 4 and r.conflitos == []
    assert total(db, Reserva) == 4


def test_slot_lotado_numa_data_nao_e_oferecido(db, com_horarios):
    """Regra do antigo: o horário só é oferecido se TODAS as datas daquele dia da semana têm vaga."""
    c = com_horarios
    cheia = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 9), capacidade=1)
    db.commit()
    fabrica.reserva_direta(db, c.a2, cheia)
    db.commit()
    with pytest.raises(servico.Invalido) as e:
        gerar(db, c, [sel(SEG, c.prof)], aulas_por_semana=1)
    assert "Horario invalido" in e.value.mensagem or "Professor invalido" in e.value.mensagem
    assert total(db, Reserva) == 1


def test_conflitos_nao_desfazem_o_resto_sucesso_parcial(db, cenario):
    """Plano B (sem horários cadastrados): bloqueio e lotação viram conflitos, as demais datas ficam (# COMPORTAMENTO ANTIGO)."""
    c = cenario
    fabrica.bloqueio(db, c.un, date(2026, 11, 9), prof=c.prof)
    cheia = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 16), capacidade=1)
    base = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 2))
    db.commit()
    fabrica.reserva_direta(db, c.a2, cheia)
    db.commit()
    r = gerar(db, c, [sel(SEG, c.prof)], aulas_por_semana=1)
    db.commit()
    assert r.conflitos == ["Bloqueio em 2026-11-09 09:00", "Sem vaga em 2026-11-16 09:00"]
    assert len(r.reservas_criadas) == 2  # 02/11 e 23/11
    assert r.mensagem_conflitos == "Conflitos ao reservar: Bloqueio em 2026-11-09 09:00; Sem vaga em 2026-11-16 09:00"
    db.expire_all()
    assert db.get(AulaSessao, cheia.id).reservas_ativas == 1 and db.get(AulaSessao, base.id).reservas_ativas == 1
    assert total(db, Reserva) == 3


def test_contrato_semanal_agenda_no_maximo_4_semanas_e_1_por_semana(db, com_horarios):
    c = com_horarios
    r = gerar(db, c, [sel(SEG, c.prof)], recorrencia_contrato="SEMANAL", aulas_por_semana=3, data_fim=date(2027, 2, 1))
    assert len(r.reservas_criadas) == 4  # 02/11, 09/11, 16/11 e 23/11 (limite de 27 dias)


def test_obter_ou_criar_sessao(db, cenario):
    c = cenario
    s1, criada = servico.obter_ou_criar_sessao(db, unidade_id=c.un.id, tipo_servico_id=c.srv.id, profissional_id=c.prof.id, data=date(2026, 11, 3), hora_inicio=time(7, 0))
    assert criada and s1.hora_fim == time(7, 50) and s1.capacidade is None
    s2, criada = servico.obter_ou_criar_sessao(db, unidade_id=c.un.id, tipo_servico_id=c.srv.id, profissional_id=c.prof.id, data=date(2026, 11, 3), hora_inicio=time(7, 0), hora_fim=time(8, 30), capacidade=9)
    assert not criada and s2.id == s1.id and s2.hora_fim == time(7, 50) and s2.capacidade is None  # não mexe na existente
    s3, criada = servico.obter_ou_criar_sessao(db, unidade_id=c.un.id, tipo_servico_id=c.srv.id, profissional_id=None, data=date(2026, 11, 3), hora_inicio=time(7, 0))
    assert criada and s3.id != s1.id and s3.profissional_id is None
    s4, criada = servico.obter_ou_criar_sessao(db, unidade_id=c.un.id, tipo_servico_id=c.srv.id, profissional_id=None, data=date(2026, 11, 3), hora_inicio=time(7, 0))
    assert not criada and s4.id == s3.id
    with pytest.raises(servico.Invalido):
        servico.obter_ou_criar_sessao(db, unidade_id=999, tipo_servico_id=c.srv.id, profissional_id=None, data=date(2026, 11, 3), hora_inicio=time(7, 0))
    with pytest.raises(servico.Invalido):
        servico.obter_ou_criar_sessao(db, unidade_id=c.un.id, tipo_servico_id=c.srv.id, profissional_id=None, data=date(2026, 11, 3), hora_inicio=time(23, 30))


# --------------------------------------------------------------------------------------------- app do aluno (R15)
AGORA = datetime(2026, 10, 25, 18, 0, tzinfo=UTC)


def test_aluno_confirma_e_desmarca_a_propria_aula(db, cenario):
    c = cenario
    r = fabrica.reserva_direta(db, c.a1, c.ses)
    db.commit()
    servico.confirmar_reserva(db, r.id, aluno_id=c.a1.id, agora=AGORA)
    assert r.confirmada_em == AGORA
    servico.desmarcar_reserva_do_aluno(db, c.a1.id, r.id, agora=AGORA)
    assert r.status == StatusReserva.CANCELADA and r.reposicao_ate == date(2026, 11, 25) and r.confirmada_em is None
    with pytest.raises(servico.Conflito, match="Aula ja desmarcada"):
        servico.desmarcar_reserva_do_aluno(db, c.a1.id, r.id, agora=AGORA)
    with pytest.raises(servico.Conflito, match="Aula cancelada"):
        servico.confirmar_reserva(db, r.id, aluno_id=c.a1.id, agora=AGORA)


def test_aluno_nao_mexe_na_reserva_de_outro_nem_em_aula_passada(db, cenario):
    c = cenario
    r = fabrica.reserva_direta(db, c.a1, c.ses)
    db.commit()
    with pytest.raises(servico.NaoEncontrado):
        servico.confirmar_reserva(db, r.id, aluno_id=c.a2.id, agora=AGORA)
    with pytest.raises(servico.NaoEncontrado):
        servico.desmarcar_reserva_do_aluno(db, c.a2.id, r.id, agora=AGORA)
    depois = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)  # aula foi dia 26
    with pytest.raises(servico.Conflito, match="passou"):
        servico.desmarcar_reserva_do_aluno(db, c.a1.id, r.id, agora=depois)
    with pytest.raises(servico.Conflito, match="passou"):
        servico.confirmar_reserva(db, r.id, aluno_id=c.a1.id, agora=depois)
