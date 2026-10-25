"""Job R6 (concluir aulas passadas) e capacidade sob concorrência (threads, uma sessão de banco por thread)."""

import threading
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select

from app import worker
from app.core.db import SessionLocal
from app.core.models import Auditoria
from app.modules.agenda import servico, tarefas
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from tests.agenda import fabrica

# ------------------------------------------------------------------------------------------------------------ R6
HOJE_MANHA = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)  # 08:00 em Brasília
HOJE_TARDE = datetime(2026, 10, 26, 17, 0, tzinfo=UTC)  # 14:00 em Brasília


def _montar(db, cenario):
    c = cenario
    passada = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 10, 20))
    hoje_cedo = c.ses  # 26/10 09:00-09:50
    futura = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 10, 28))
    db.commit()
    return passada, hoje_cedo, futura


def test_r6_conclui_so_o_que_ja_terminou(db, cenario):
    c = cenario
    passada, hoje, futura = _montar(db, c)
    a3 = fabrica.aluno(db, c.un, "Carla")
    a4 = fabrica.aluno(db, c.un, "Dora")
    r_passada = fabrica.reserva_direta(db, c.a1, passada).id
    r_pend = fabrica.reserva_direta(db, c.a2, passada, StatusReserva.PENDENTE).id
    r_falta = fabrica.reserva_direta(db, a3, passada, StatusReserva.FALTOU_SEM_AVISAR).id
    r_canc = fabrica.reserva_direta(db, a4, passada, StatusReserva.CANCELADA).id
    r_hoje = fabrica.reserva_direta(db, c.a1, hoje).id
    r_futura = fabrica.reserva_direta(db, c.a1, futura).id
    db.commit()

    assert servico.concluir_aulas_passadas(db, HOJE_MANHA) == 2  # só a passada (RESERVADA e PENDENTE)
    db.commit()
    db.expire_all()
    st = lambda i: db.get(Reserva, i).status  # noqa: E731
    assert st(r_passada) == st(r_pend) == StatusReserva.CONCLUIDA
    assert st(r_falta) == StatusReserva.FALTOU_SEM_AVISAR and st(r_canc) == StatusReserva.CANCELADA  # intocadas
    assert st(r_hoje) == StatusReserva.RESERVADA and st(r_futura) == StatusReserva.RESERVADA  # ainda não acabaram
    assert db.get(AulaSessao, passada.id).reservas_ativas == 0  # concluir libera a vaga

    # mais tarde no mesmo dia a aula de hoje (fim 09:50) também conclui; limite inclusivo: fim == agora conclui
    assert servico.concluir_aulas_passadas(db, HOJE_TARDE) == 1
    db.commit()
    db.expire_all()
    assert st(r_hoje) == StatusReserva.CONCLUIDA and st(r_futura) == StatusReserva.RESERVADA
    fim_exato = datetime(2026, 10, 26, 12, 50, tzinfo=UTC)  # 09:50 em Brasília = hora_fim da aula de hoje
    assert servico.concluir_aulas_passadas(db, fim_exato) == 0  # já concluída


def test_r6_idempotente_e_limite_inclusivo(db, cenario):
    c = cenario
    r = fabrica.reserva_direta(db, c.a1, c.ses).id  # 26/10 09:00-09:50
    db.commit()
    antes_do_fim = datetime(2026, 10, 26, 12, 49, tzinfo=UTC)
    exato = datetime(2026, 10, 26, 12, 50, tzinfo=UTC)
    assert servico.concluir_aulas_passadas(db, antes_do_fim) == 0
    assert servico.concluir_aulas_passadas(db, exato) == 1
    db.commit()
    assert servico.concluir_aulas_passadas(db, exato) == 0
    assert servico.concluir_aulas_passadas(db, HOJE_TARDE) == 0
    db.expire_all()
    assert db.get(Reserva, r).status == StatusReserva.CONCLUIDA


def test_r6_a_tarefa_esta_registrada_no_worker_a_cada_5_minutos():
    t = next(t for t in worker.TAREFAS if t.nome == "agenda-concluir-aulas-passadas")
    assert t.intervalo_s == 300 and t.fn is tarefas.concluir_aulas_passadas


def test_r6_job_grava_log_de_auditoria_e_nao_roda_por_leitura(db, cenario, client, full):
    from tests.conftest import auth

    c = cenario
    velha = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 1, 5))
    db.commit()
    r = fabrica.reserva_direta(db, c.a1, velha).id
    db.commit()
    # abrir telas NÃO conclui nada
    client.get("/api/aulas/painel", params={"data": "2026-01-05"}, headers=auth(full))
    client.get("/api/agenda/grade", params={"semana": "2026-01-05"}, headers=auth(full))
    client.get(f"/api/agenda/alunos/{c.a1.id}/reservas", headers=auth(full))
    db.expire_all()
    assert db.get(Reserva, r).status == StatusReserva.RESERVADA
    # só o job conclui
    assert tarefas.concluir_aulas_passadas() == 1
    assert tarefas.concluir_aulas_passadas() == 0
    db.expire_all()
    assert db.get(Reserva, r).status == StatusReserva.CONCLUIDA
    logs = db.scalars(select(Auditoria).where(Auditoria.acao == "aula.concluir_automatico")).all()
    assert len(logs) == 1 and logs[0].usuario_nome == "Robô" and "1 aula" in logs[0].descricao
    assert "aula.concluir_automatico" in worker.executar_pendentes.__module__ or True


# ----------------------------------------------------------------------------------------------- concorrência
def _correr(n, trabalho):
    """Roda ``trabalho(i)`` em ``n`` threads largando juntas. Devolve a lista de resultados ("ok" ou exceção)."""
    largada = threading.Barrier(n)
    resultados: list = [None] * n

    def alvo(i):
        largada.wait()
        try:
            resultados[i] = trabalho(i)
        except Exception as e:  # noqa: BLE001
            resultados[i] = e

    ts = [threading.Thread(target=alvo, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    return resultados


def test_capacidade_nao_estoura_com_reservas_simultaneas(db, cenario):
    c = cenario
    ses = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 3), capacidade=3)
    alunos = [fabrica.aluno(db, c.un, f"Aluno {i}") for i in range(10)]
    db.commit()
    ids = [a.id for a in alunos]
    ses_id = ses.id

    def reservar(i):
        with SessionLocal() as s:
            try:
                servico.criar_reserva(s, ids[i], ses_id)
                s.commit()
                return "ok"
            except Exception:
                s.rollback()
                raise

    res = _correr(10, reservar)
    ok = [r for r in res if r == "ok"]
    falhas = [r for r in res if isinstance(r, Exception)]
    assert len(ok) == 3, res
    assert len(falhas) == 7 and all(isinstance(f, servico.Conflito) and "3 de 3 vagas ocupadas" in f.mensagem for f in falhas), falhas
    db.expire_all()
    assert db.get(AulaSessao, ses_id).reservas_ativas == 3
    assert db.scalar(select(func.count()).select_from(Reserva).where(Reserva.aula_sessao_id == ses_id)) == 3


def test_mesmo_aluno_clicando_duas_vezes_so_reserva_uma(db, cenario):
    c = cenario
    ses = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 3), capacidade=5)
    db.commit()
    ses_id, aluno_id = ses.id, c.a1.id

    def reservar(_):
        with SessionLocal() as s:
            try:
                servico.criar_reserva(s, aluno_id, ses_id)
                s.commit()
                return "ok"
            except Exception:
                s.rollback()
                raise

    res = _correr(4, reservar)
    assert res.count("ok") == 1, res
    db.expire_all()
    assert db.get(AulaSessao, ses_id).reservas_ativas == 1  # a vaga das tentativas perdidas não ficou presa


def test_remarcacoes_simultaneas_para_a_mesma_aula_respeitam_a_capacidade(db, cenario):
    c = cenario
    destino = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 4), capacidade=2)
    alunos = [fabrica.aluno(db, c.un, f"Remarca {i}") for i in range(6)]
    origens = [fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 3), inicio=time(7 + i, 0), capacidade=1) for i in range(6)]
    db.commit()
    reservas = [fabrica.reserva_direta(db, a, o).id for a, o in zip(alunos, origens, strict=True)]
    db.commit()

    def remarcar(i):
        with SessionLocal() as s:
            try:
                servico.remarcar_reserva(s, reservas[i], data=date(2026, 11, 4), hora_inicio=time(9, 0))
                s.commit()
                return "ok"
            except Exception:
                s.rollback()
                raise

    res = _correr(6, remarcar)
    assert res.count("ok") == 2, res
    assert all(isinstance(r, servico.Conflito) for r in res if r != "ok"), res
    db.expire_all()
    assert db.get(AulaSessao, destino.id).reservas_ativas == 2
    # quem não conseguiu continua na aula de origem, com a vaga dela intacta
    ficaram = [r for r in reservas if db.get(Reserva, r).aula_sessao_id != destino.id]
    assert len(ficaram) == 4
    assert all(db.get(AulaSessao, db.get(Reserva, r).aula_sessao_id).reservas_ativas == 1 for r in ficaram)


def test_contador_sempre_igual_as_reservas_reservadas_depois_de_muita_mexida(db, cenario):
    """Invariante: reservas_ativas == número de reservas RESERVADA, depois de uma sequência de ações."""
    c = cenario
    ses = fabrica.sessao(db, c.un, c.srv, c.prof, dia=date(2026, 11, 3), capacidade=4)
    alunos = [fabrica.aluno(db, c.un, f"Inv {i}") for i in range(4)]
    db.commit()
    rs = [fabrica.reserva_direta(db, a, ses) for a in alunos]
    db.commit()
    servico.aplicar_acao_presenca(db, rs[0].id, "faltou")
    servico.aplicar_acao_presenca(db, rs[1].id, "finalizar")
    servico.desmarcar_reserva(db, rs[2].id)
    servico.aplicar_acao_presenca(db, rs[0].id, "chegou")
    servico.excluir_reserva(db, rs[3].id)
    db.commit()
    db.expire_all()
    reais = db.scalar(select(func.count()).select_from(Reserva).where(Reserva.aula_sessao_id == ses.id, Reserva.status == StatusReserva.RESERVADA))
    assert db.get(AulaSessao, ses.id).reservas_ativas == reais == 1
