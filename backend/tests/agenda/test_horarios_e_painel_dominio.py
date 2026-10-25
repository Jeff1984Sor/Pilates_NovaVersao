"""Opções de remarcação (só leitura) e as funções puras de painel/grade do domínio."""

from datetime import date, time

from sqlalchemy import func, select

from app.domain import painel as dom
from app.modules.agenda.models import AulaSessao
from tests.agenda import fabrica
from tests.conftest import auth


# ---------------------------------------------------------------------------------------------- domínio puro
def test_periodo_do_painel():
    seg, qua, sab, dom_ = date(2026, 10, 26), date(2026, 10, 28), date(2026, 10, 24), date(2026, 10, 25)
    assert dom.periodo_do_painel(None, "hoje", qua) == (qua, qua)
    assert dom.periodo_do_painel(None, "amanha", qua) == (date(2026, 10, 29), date(2026, 10, 29))
    assert dom.periodo_do_painel(qua, "semana", seg) == (seg, date(2026, 11, 1))
    # sábado e domingo pulam para a próxima semana
    assert dom.periodo_do_painel(sab, "semana", sab) == (seg, date(2026, 11, 1))
    assert dom.periodo_do_painel(dom_, "semana", dom_) == (seg, date(2026, 11, 1))
    assert dom.periodo_do_painel(date(2026, 11, 3), "hoje", qua) == (date(2026, 11, 3), date(2026, 11, 3))
    assert dom.periodo_do_painel(qua, "qualquer", qua) == (qua, qua)


def test_semana_da_grade():
    assert dom.semana_da_grade(None, date(2026, 10, 28)) == (date(2026, 10, 26), date(2026, 10, 31))
    assert dom.semana_da_grade(None, date(2026, 10, 24)) == (date(2026, 10, 26), date(2026, 10, 31))  # sábado -> próxima
    assert dom.semana_da_grade(None, date(2026, 10, 25)) == (date(2026, 10, 26), date(2026, 10, 31))  # domingo -> próxima
    assert dom.semana_da_grade(date(2026, 10, 25), date(2026, 10, 25)) == (date(2026, 10, 19), date(2026, 10, 24))  # escolhida: respeita


def test_cor_da_reserva():
    assert dom.cor_da_reserva("RESERVADA", True) == ("#3b9ad9", "Confirmada")
    assert dom.cor_da_reserva("RESERVADA", False) == ("#f59e0b", "A confirmar")
    assert dom.cor_da_reserva("CONCLUIDA", False) == ("#16a34a", "Concluída")
    assert dom.cor_da_reserva("FALTOU_AVISOU", False)[1] == "Falta avisada"
    assert dom.cor_da_reserva("FALTOU_SEM_AVISAR", False) == ("#ef4444", "Falta")
    assert dom.cor_da_reserva("CANCELADA", False)[0] == "#9ca3af"
    assert dom.cor_da_reserva("PENDENTE", False)[0] == "#a78bfa"
    assert dom.cor_da_reserva("XPTO", False) == ("#94a3b8", "XPTO")


def test_distribuir_colunas_clusters_independentes():
    b = [dom.BlocoMinutos(540, 590), dom.BlocoMinutos(540, 590), dom.BlocoMinutos(560, 600), dom.BlocoMinutos(660, 710)]
    out = dom.distribuir_colunas(b)
    assert [(x.coluna, x.colunas) for x in out] == [(0, 3), (1, 3), (2, 3), (0, 1)]
    # aula encadeada (termina quando a outra começa) volta para a coluna 0 e não divide largura
    seq = dom.distribuir_colunas([dom.BlocoMinutos(540, 590), dom.BlocoMinutos(590, 640)])
    assert [(x.coluna, x.colunas) for x in seq] == [(0, 1), (0, 1)]
    assert dom.distribuir_colunas([]) == []


def test_iniciais():
    assert dom.iniciais("Ana Paula Souza") == "AP"
    assert dom.iniciais("  maria ") == "M"
    assert dom.iniciais(None) == "" and dom.iniciais("") == ""


# ------------------------------------------------------------------------------------------ remarcação: opções
def test_horarios_para_remarcar_lista_sem_criar_nada(client, db, cenario, full):
    c = cenario
    fabrica.funcionamento(db, c.un, dias=(2,), inicio=time(8, 0), fim=time(10, 0), servicos=[c.srv])  # quarta
    existente = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 10, 28), inicio=time(9, 0))
    cheia = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 10, 28), inicio=time(8, 0), capacidade=1)
    db.commit()
    fabrica.reserva_direta(db, c.a2, cheia)
    r = fabrica.reserva_direta(db, c.a1, c.ses)
    db.commit()
    antes = db.scalar(select(func.count()).select_from(AulaSessao))
    resp = client.get(f"/api/agenda/reservas/{r.id}/horarios", params={"de": "2026-10-26", "ate": "2026-10-30"}, headers=auth(full))
    assert resp.status_code == 200
    itens = resp.json()["itens"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AulaSessao)) == antes  # nada foi criado
    por_hora = {(i["data"], i["hora_inicio"]): i for i in itens}
    # a aula cheia (08:00, capacidade 1 ocupada) não é oferecida; a de 09:00 sim, com a professora e 2 vagas
    assert ("2026-10-28", "08:00") not in por_hora
    assert por_hora[("2026-10-28", "09:00")]["sessao_id"] == existente.id and por_hora[("2026-10-28", "09:00")]["vagas"] == 2
    # a aula atual do aluno nunca aparece como opção
    assert ("2026-10-26", "09:00") not in por_hora
    # horário de funcionamento ainda sem aula entra como candidato (sessao_id nulo): quarta 10:00 não cabe (08-10), só 08:00 e 09:00
    assert all(i["data"] == "2026-10-28" for i in itens)


def test_horarios_de_dia_bloqueado_nao_aparecem(client, db, cenario, full):
    c = cenario
    fabrica.funcionamento(db, c.un, dias=(2,), inicio=time(8, 0), fim=time(12, 0))
    fabrica.bloqueio(db, c.un, date(2026, 10, 28), inicio=time(8, 0), fim=time(10, 0))
    r = fabrica.reserva_direta(db, c.a1, c.ses)
    db.commit()
    itens = client.get(f"/api/agenda/reservas/{r.id}/horarios", params={"de": "2026-10-28", "ate": "2026-10-28"}, headers=auth(full)).json()["itens"]
    assert [i["hora_inicio"] for i in itens] == ["10:00", "11:00"]
    assert all(i["sessao_id"] is None for i in itens)


def test_horarios_reserva_inexistente_404(client, full):
    assert client.get("/api/agenda/reservas/999/horarios", headers=auth(full)).status_code == 404
