"""R4 - desmarcar e reposição de 30 dias. Caracterização contra aula_status_api e api/main.aluno_app_*."""
from datetime import date, datetime, timedelta

import pytest

from app.domain import reposicao as rep
from tests.domain.golden import golden_reposicao as g


def _agora() -> datetime:
    return datetime(2026, 10, 25, 14, 30)


@pytest.mark.parametrize("data_aula,http,corpo,status,confirmada,desmarcada_ok,reposicao_ate", g.DESMARCAR_STAFF)
def test_r4_desmarcar_staff_identico_ao_antigo(data_aula, http, corpo, status, confirmada, desmarcada_ok, reposicao_ate):
    r = rep.desmarcar(data_aula, _agora())
    assert http == 200
    assert r.status == status == corpo["status"]
    assert r.confirmada_em is confirmada is None
    assert r.reposicao_ate == reposicao_ate
    assert r.reposicao_ate.isoformat() == corpo["reposicao_ate"]
    assert r.desmarcada_em == _agora() and desmarcada_ok


def test_r4_caso_oficial_aula_10_10_reposicao_ate_09_11():
    assert rep.reposicao_ate(date(2026, 10, 10)) == date(2026, 11, 9)


def test_r4_sem_sessao_nao_tem_reposicao():
    assert rep.reposicao_ate(None) is None
    assert rep.desmarcar(None, _agora()).reposicao_ate is None


def test_r4_professor_nao_desmarca_nem_remarca():
    with pytest.raises(rep.SemPermissao):
        rep.desmarcar(date(2026, 10, 10), _agora(), eh_professor=True)
    with pytest.raises(rep.SemPermissao):
        rep.acoes_permitidas_status("remarcar", eh_professor=True)
    # professor consegue as demais ações (o filtro por dono da aula é do middleware, R11)
    assert rep.acoes_permitidas_status("finalizar", eh_professor=True) == "CONCLUIDA"


def test_r4_acoes_de_status_identicas_ao_antigo():
    for acao, http, status_final in g.ACOES:
        if acao == "desmarcar":
            continue
        if http == 400:
            with pytest.raises(rep.AcaoInvalida):
                rep.acoes_permitidas_status(acao, eh_professor=False)
        else:
            assert rep.acoes_permitidas_status(acao, eh_professor=False) == status_final
    for acao, http, status_final in g.PROFESSOR:
        if http == 403 and acao == "desmarcar":
            with pytest.raises(rep.SemPermissao):
                rep.desmarcar(date(2026, 11, 3), _agora(), eh_professor=True)
        elif http == 403:
            with pytest.raises(rep.SemPermissao):
                rep.acoes_permitidas_status(acao, eh_professor=True)
        else:
            assert rep.acoes_permitidas_status(acao, eh_professor=True) == status_final


@pytest.mark.parametrize("rotulo,acao,dias,resultado", g.APP_ALUNO)
def test_r4_app_do_aluno_identico_ao_antigo(rotulo, acao, dias, resultado):
    hoje = g.HOJE_APP
    data_aula = hoje + timedelta(days=dias)
    status = "CANCELADA" if rotulo == "cancelada" else "RESERVADA"
    funcao = rep.desmarcar_pelo_aluno if acao == "desmarcar" else rep.confirmar_pelo_aluno
    if resultado[0] == "erro":
        with pytest.raises(rep.AcaoInvalida) as exc:
            funcao(status, data_aula, hoje, _agora())
        assert str(exc.value) == resultado[2]
        return
    saida = funcao(status, data_aula, hoje, _agora())
    if acao == "desmarcar":
        assert saida.reposicao_ate.isoformat() == resultado[1]["reposicao_ate"]
        assert rep.mensagem_reposicao(saida.reposicao_ate) == resultado[1]["mensagem"]
    else:
        assert saida == _agora()


def test_r4_aviso_de_6_horas_desligado_por_padrao():
    # COMPORTAMENTO ANTIGO: nada validava as 6 horas da clausula 5 do contrato
    inicio = datetime(2026, 10, 26, 8, 0)
    assert rep.aviso_minimo_cumprido(inicio, datetime(2026, 10, 26, 7, 59)) is True


def test_r4_aviso_de_6_horas_quando_ligado():
    inicio = datetime(2026, 10, 26, 8, 0)
    assert rep.aviso_minimo_cumprido(inicio, datetime(2026, 10, 26, 2, 0), ativo=True) is True      # exatamente 6h
    assert rep.aviso_minimo_cumprido(inicio, datetime(2026, 10, 26, 2, 1), ativo=True) is False
    assert rep.aviso_minimo_cumprido(inicio, datetime(2026, 10, 25, 8, 0), ativo=True) is True
    assert rep.aviso_minimo_cumprido(inicio, datetime(2026, 10, 26, 6, 0), horas_minimas=1, ativo=True) is True
