"""Aula avulsa (R12) e aula avaliativa: com e sem cobrança, 2 serviços no horário, conflitos e atomicidade."""

from datetime import date, time
from decimal import Decimal

from sqlalchemy import func, select

from app.core.models import Auditoria
from app.domain.parcelas import competencia_semanal
from app.modules.agenda.models import AulaAvaliativa, AulaAvulsa, AulaSessao, Reserva, StatusAvaliativa
from app.modules.financeiro.models import ContaReceber
from tests.agenda import fabrica
from tests.conftest import auth

SEGUNDA = "2026-10-26"


def contar(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


def corpo(cenario, plano, **extra):
    base = {
        "aluno_id": cenario.a1.id,
        "plano_id": plano.id,
        "unidade_id": cenario.un.id,
        "profissional_id": cenario.prof.id,
        "quantidade": 3,
        "data_inicio": SEGUNDA,
        "dia_semana": 0,
        "hora_inicio": "09:00",
        "hora_fim": "09:50",
    }
    return {**base, **extra}


def preparar(db, cenario, valor="80.00", servicos=()):
    fabrica.funcionamento(db, cenario.un, dias=(0,), inicio=time(8, 0), fim=time(12, 0), servicos=servicos)
    plano = fabrica.plano_avulso(db, cenario.srv, valor=valor)
    db.commit()
    return plano


# ------------------------------------------------------------------------------------------------------- avulsa
def test_slots_da_avulsa_so_lendo(client, db, cenario, full):
    plano = preparar(db, cenario)
    antes = contar(db, AulaSessao)
    r = client.get("/api/agenda/avulsas/slots", params={"unidade_id": cenario.un.id, "plano_id": plano.id, "data_inicio": SEGUNDA, "quantidade": 3}, headers=auth(full))
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["data_fim"] == "2026-11-16" and [x["inicio"] for x in s["slots"]] == ["08:00", "09:00", "10:00", "11:00"]
    assert s["slots"][1]["valor"] == "0|09:00|09:50" and s["slots"][1]["profissionais"][0]["id"] == cenario.prof.id
    assert contar(db, AulaSessao) == antes


def test_avulsa_com_cobranca_uma_conta_por_aula_ligada_a_reserva(client, db, cenario, full):
    plano = preparar(db, cenario)
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano), headers=auth(full))
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["valor_aula"] == "80.00" and c["valor_total"] == "240.00"  # total = valor x quantidade (decisão documentada)
    assert c["data_inicio"] == SEGUNDA and c["data_fim"] == "2026-11-16" and c["conflitos"] == [] and c["aviso"] is None
    assert len(c["reservas"]) == 3 and len(c["contas"]) == 3
    db.expire_all()
    contas = db.scalars(select(ContaReceber).order_by(ContaReceber.vencimento)).all()
    assert [x.vencimento for x in contas] == [date(2026, 10, 26), date(2026, 11, 2), date(2026, 11, 9)]
    assert all(x.valor == Decimal("80.00") and x.status == "ABERTO" and x.contrato_id is None and x.aluno_id == cenario.a1.id for x in contas)
    assert {x.reserva_id for x in contas} == set(c["reservas"])
    assert contas[0].competencia == competencia_semanal(date(2026, 10, 26))
    reservas = db.scalars(select(Reserva).where(Reserva.aula_avulsa_id == c["id"])).all()
    assert len(reservas) == 3 and {r.status for r in reservas} == {"RESERVADA"}
    assert db.get(AulaAvulsa, c["id"]).recorrencia == "SEMANAL"
    assert "aula_avulsa.criar" in db.scalars(select(Auditoria.acao)).all()


def test_avulsa_valor_zero_totalpass_wellhub_nao_gera_cobranca(client, db, cenario, full):
    plano = preparar(db, cenario, valor="0.00")
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=2), headers=auth(full))
    assert r.status_code == 201 and len(r.json()["reservas"]) == 2 and r.json()["contas"] == []
    assert contar(db, ContaReceber) == 0
    # valor informado 0 num plano pago também não cobra (cortesia)
    pago = fabrica.plano_avulso(db, cenario.srv, valor="80.00", nome="Avulsa paga")
    db.commit()
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, pago, quantidade=1, data_inicio="2026-11-23", valor_aula="0"), headers=auth(full))
    assert r.status_code == 201 and r.json()["contas"] == []


def test_avulsa_valor_informado_substitui_o_do_plano(client, db, cenario, full):
    plano = preparar(db, cenario)
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=2, valor_aula="55.5"), headers=auth(full)).json()
    assert r["valor_aula"] == "55.5" and r["valor_total"] == "111.0"
    assert [c["valor"] for c in r["contas"]] == ["55.5", "55.5"]


def test_avulsa_horario_com_dois_servicos_nao_cobra_em_dobro(client, db, cenario, full):
    """# COMPORTAMENTO ANTIGO corrigido (R12): o antigo criava 1 reserva e 1 cobrança POR SERVIÇO do horário."""
    outro = fabrica.servico(db, "Alongamento")
    plano = preparar(db, cenario, servicos=[cenario.srv, outro])
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=2), headers=auth(full)).json()
    assert len(r["reservas"]) == 2 and len(r["contas"]) == 2  # antigo: 4 e 4
    assert contar(db, Reserva) == 2 and contar(db, ContaReceber) == 2
    servicos = {s.tipo_servico_id for s in db.scalars(select(AulaSessao))}
    assert servicos == {cenario.srv.id}


def test_avulsa_mensal_usa_competencia_mensal(client, db, cenario, full):
    from app.modules.cadastros.models import Recorrencia

    fabrica.funcionamento(db, cenario.un, dias=(0,), inicio=time(8, 0), fim=time(12, 0))
    plano = fabrica.plano_avulso(db, cenario.srv, recorrencia=Recorrencia.MENSAL)
    db.commit()
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=2), headers=auth(full))
    assert r.status_code == 201, r.text
    db.expire_all()
    assert {c.competencia for c in db.scalars(select(ContaReceber))} == {"2026-10", "2026-11"}


def test_avulsa_valida_plano_slot_e_professor(client, db, cenario, full):
    plano = preparar(db, cenario)
    nao_avulso = fabrica.plano_avulso(db, cenario.srv, avulso=False, nome="Mensal")
    db.commit()
    h = auth(full)
    assert client.post("/api/agenda/avulsas", json=corpo(cenario, nao_avulso), headers=h).json()["detail"] == "Selecione um plano de aula avulsa válido."
    assert client.post("/api/agenda/avulsas", json=corpo(cenario, plano, hora_inicio="13:00", hora_fim="13:50"), headers=h).json()["detail"] == "Horario invalido para o dia selecionado."
    assert client.post("/api/agenda/avulsas", json=corpo(cenario, plano, dia_semana=2), headers=h).status_code == 422
    assert client.post("/api/agenda/avulsas", json=corpo(cenario, plano, profissional_id=999), headers=h).status_code == 422
    assert client.post("/api/agenda/avulsas", json=corpo(cenario, plano, aluno_id=999), headers=h).status_code == 404
    assert client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=0), headers=h).status_code == 422
    assert client.post("/api/agenda/avulsas", json=corpo(cenario, plano, valor_aula="-1"), headers=h).status_code == 422
    assert contar(db, AulaAvulsa) == 0 and contar(db, Reserva) == 0 and contar(db, ContaReceber) == 0


def test_avulsa_sem_nenhuma_vaga_nao_grava_nada(client, db, cenario, full):
    """Sem horários de funcionamento, vale o plano B (aulas existentes). Aula lotada em todas as datas -> nada é criado."""
    plano = fabrica.plano_avulso(db, cenario.srv)
    cheia = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 11, 2), capacidade=1)
    db.commit()
    fabrica.reserva_direta(db, cenario.a2, cheia)
    db.commit()
    # o único slot conhecido (segunda 09:00) existe só na sessão cheia: a sessão do cenário (26/10) também é segunda 09:00
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=1, data_inicio="2026-11-02"), headers=auth(full))
    assert r.status_code in (409, 422), r.text
    assert contar(db, AulaAvulsa) == 0 and contar(db, ContaReceber) == 0


def test_avulsa_conflitos_parciais_mantem_as_demais(client, db, cenario, full):
    """Plano B (sem horários cadastrados): bloqueio numa data e aula lotada em outra viram avisos; as demais ficam."""
    plano = fabrica.plano_avulso(db, cenario.srv)
    fabrica.bloqueio(db, cenario.un, date(2026, 11, 2), prof=cenario.prof)
    lotada = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=date(2026, 11, 9), capacidade=1)
    db.commit()
    fabrica.reserva_direta(db, cenario.a2, lotada)
    db.commit()
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=4), headers=auth(full))
    assert r.status_code == 201, r.text
    c = r.json()
    assert len(c["reservas"]) == 2 and len(c["contas"]) == 2  # 26/10 e 16/11
    assert c["conflitos"] == ["Bloqueio em 2026-11-02 09:00", "Sem vaga em 2026-11-09 09:00"]
    assert c["aviso"].startswith("Conflitos ao reservar: Bloqueio em 2026-11-02")
    db.expire_all()
    assert db.get(AulaSessao, lotada.id).reservas_ativas == 1  # a vaga da outra aluna intacta


def test_avulsa_idempotente_nao_duplica_reserva_nem_cobranca(client, db, cenario, full):
    plano = preparar(db, cenario)
    h = auth(full)
    client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=2), headers=h)
    r = client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=2), headers=h)
    # segundo pacote cai nas mesmas aulas: aluno já está nelas, nada novo é cobrado
    assert r.status_code == 201 and r.json()["reservas"] == [] and r.json()["contas"] == []
    assert contar(db, ContaReceber) == 2


def test_listar_avulsas_do_aluno(client, db, cenario, full):
    plano = preparar(db, cenario)
    client.post("/api/agenda/avulsas", json=corpo(cenario, plano, quantidade=2), headers=auth(full))
    itens = client.get(f"/api/agenda/alunos/{cenario.a1.id}/avulsas", headers=auth(full)).json()["itens"]
    assert len(itens) == 1 and itens[0]["valor_total"] == "160.00"


# --------------------------------------------------------------------------------------------------- avaliativa
def corpo_av(cenario, **extra):
    return {
        "aluno_id": cenario.a1.id,
        "unidade_id": cenario.un.id,
        "profissional_id": cenario.prof.id,
        "tipo_servico_id": cenario.srv.id,
        "data": "2026-10-28",
        "hora_inicio": "09:00",
        **extra,
    }


def test_avaliativa_cria_ficha_aula_e_reserva_sem_cobranca(client, db, cenario, full):
    r = client.post("/api/agenda/avaliativas", json=corpo_av(cenario), headers=auth(full))
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["tipo"] == "AVALIATIVA" and a["status"] == "AGENDADA" and a["hora_fim"] == "09:50" and a["reserva_id"]
    db.expire_all()
    reserva = db.get(Reserva, a["reserva_id"])
    assert reserva.aula_avaliativa_id == a["id"] and reserva.status == "RESERVADA"
    assert contar(db, ContaReceber) == 0
    assert "aula_avaliativa.criar" in db.scalars(select(Auditoria.acao)).all()


def test_avaliativa_totalpass_e_wellhub(client, cenario, full):
    h = auth(full)
    t = client.post("/api/agenda/avaliativas", json=corpo_av(cenario, tipo="totalpass"), headers=h).json()
    assert t["tipo"] == "TOTALPASS"
    w = client.post("/api/agenda/avaliativas", json=corpo_av(cenario, tipo="WELLHUB", aluno_id=cenario.a2.id), headers=h).json()
    assert w["tipo"] == "WELLHUB"
    assert client.post("/api/agenda/avaliativas", json=corpo_av(cenario, tipo="OUTRA", data="2026-10-29"), headers=h).status_code == 422


def test_avaliativa_sem_vaga_nao_deixa_ficha_solta(client, db, cenario, full):
    """# COMPORTAMENTO ANTIGO corrigido: o antigo gravava a ficha mesmo sem vaga."""
    h = auth(full)
    c = corpo_av(cenario)
    a3 = fabrica.aluno(db, cenario.un, "Carla")
    db.commit()
    client.post("/api/agenda/avaliativas", json=c, headers=h)
    client.post("/api/agenda/avaliativas", json={**c, "aluno_id": cenario.a2.id}, headers=h)
    r = client.post("/api/agenda/avaliativas", json={**c, "aluno_id": a3.id}, headers=h)
    assert r.status_code == 409 and "2 de 2 vagas ocupadas" in r.json()["detail"]
    assert contar(db, AulaAvaliativa) == 2 and contar(db, Reserva) == 2


def test_avaliativa_ficha_e_conversao_sem_criar_contrato(client, db, cenario, full):
    h = auth(full)
    a = client.post("/api/agenda/avaliativas", json=corpo_av(cenario), headers=h).json()
    f = client.put(
        f"/api/agenda/avaliativas/{a['id']}/ficha",
        json={"queixa_principal": " Dor lombar ", "objetivos": "Fortalecer", "historico_saude": "Hérnia", "observacoes": "", "status": "REALIZADA"},
        headers=h,
    )
    assert f.status_code == 200
    assert f.json()["queixa_principal"] == "Dor lombar" and f.json()["observacoes"] is None and f.json()["status"] == "REALIZADA"
    assert client.put(f"/api/agenda/avaliativas/{a['id']}/ficha", json={"status": "XPTO"}, headers=h).status_code == 422
    c = client.post(f"/api/agenda/avaliativas/{a['id']}/converter", headers=h)
    assert c.status_code == 200 and c.json()["status"] == "CONVERTIDA" and "contrato" in c.json()["mensagem"].lower()
    assert c.json()["contrato_id"] is None  # NÃO cria contrato (comportamento antigo mantido)
    db.expire_all()
    assert db.get(AulaAvaliativa, a["id"]).status == StatusAvaliativa.CONVERTIDA
    lista = client.get(f"/api/agenda/alunos/{cenario.a1.id}/avaliativas", headers=h).json()["itens"]
    assert [x["status"] for x in lista] == ["CONVERTIDA"]
    assert client.post("/api/agenda/avaliativas/999/converter", headers=h).status_code == 404
    acoes = db.scalars(select(Auditoria.acao)).all()
    assert "aula_avaliativa.ficha" in acoes and "aula_avaliativa.converter" in acoes


def test_professor_preenche_ficha_das_proprias_e_nao_converte(client, db, cenario, outro_professor, professor, full):
    a = client.post("/api/agenda/avaliativas", json=corpo_av(cenario), headers=auth(full)).json()
    assert client.put(f"/api/agenda/avaliativas/{a['id']}/ficha", json={"objetivos": "x"}, headers=auth(professor)).status_code == 200
    assert client.put(f"/api/agenda/avaliativas/{a['id']}/ficha", json={"objetivos": "x"}, headers=auth(outro_professor.token)).status_code == 404
    assert client.post(f"/api/agenda/avaliativas/{a['id']}/converter", headers=auth(professor)).status_code in (403,)
