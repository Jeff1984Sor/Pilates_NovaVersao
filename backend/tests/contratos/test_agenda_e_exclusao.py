"""Agenda do contrato (FK contrato_id, conflitos sem desfazer o resto) e exclusão segura (R13)."""

from datetime import date, time

from sqlalchemy import func, select

from app.core.models import Auditoria
from app.modules.agenda import servico as agenda_servico
from app.modules.agenda.models import AulaSessao, Avaliacao, Evolucao, Reserva, StatusReserva
from app.modules.alunos.models import AlunoDocumento
from app.modules.contratos import servico
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import Comissao, ContaReceber, StatusReceber
from tests.contratos.conftest import cabecalho, png_data_url

SEG, QUA, TER = 0, 2, 1


def contar(db, modelo, *where):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo).where(*where))


def sel(dia, prof, ini="09:00", fim="09:50"):
    return {"dia_semana": dia, "inicio": ini, "fim": fim, "profissional_id": prof.id}


def agendar(client, token, cid, selecoes):
    return client.post(f"/api/contratos/{cid}/agenda", json={"selecoes": selecoes}, headers=cabecalho(token))


def contrato_curto(novo_contrato):
    """02/11/2026 (segunda) a 29/11/2026: 4 segundas e 4 quartas."""
    return novo_contrato(data_inicio="2026-11-02", data_fim="2026-11-29")["contrato"]["id"]


# -------------------------------------------------------------------------------------------------------- agenda
def test_opcoes_vem_de_funcionamento_menos_bloqueios_e_lotacao(client, full, db, cen, novo_contrato):
    cid = contrato_curto(novo_contrato)
    r = client.get(f"/api/contratos/{cid}/agenda/opcoes", headers=cabecalho(full))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["exatamente"] == 2 and j["inicio"] == "2026-11-02" and j["fim"] == "2026-11-29" and j["ja_agendadas"] == 0
    dias = {s["dia_semana"] for s in j["slots"]}
    assert dias == {0, 1, 2, 3, 4}  # seg-sex
    horarios_seg = [s["inicio"] for s in j["slots"] if s["dia_semana"] == 0]
    assert horarios_seg == ["08:00", "09:00", "10:00", "11:00"] and {p["nome"] for p in j["slots"][0]["profissionais"]} == {"Natalia Souza", "Bia Prado"}
    # bloqueio de uma segunda 09:00 para a Natalia tira só ela daquele horário; lotação de outra segunda tira o horário
    from app.modules.cadastros.models import BloqueioAgenda

    db.add(BloqueioAgenda(unidade_id=cen.un.id, profissional_id=cen.p1.id, recorrente=False, data_inicio=date(2026, 11, 9),
                          data_fim=date(2026, 11, 9), hora_inicio=time(9, 0), hora_fim=time(9, 50), ativo=True))
    sessao = agenda_servico.criar_sessao(db, unidade_id=cen.un.id, tipo_servico_id=cen.srv.id, profissional_id=cen.p2.id,
                                         data=date(2026, 11, 16), hora_inicio=time(10, 0), capacidade=1)
    agenda_servico.criar_reserva(db, cen.outro.id, sessao.id)
    db.commit()
    j = client.get(f"/api/contratos/{cid}/agenda/opcoes", headers=cabecalho(full)).json()
    s9 = next(s for s in j["slots"] if s["dia_semana"] == 0 and s["inicio"] == "09:00")
    assert [p["nome"] for p in s9["profissionais"]] == ["Bia Prado"]
    s10 = next(s for s in j["slots"] if s["dia_semana"] == 0 and s["inicio"] == "10:00")
    assert [p["nome"] for p in s10["profissionais"]] == ["Natalia Souza"]  # Bia lotada em 16/11


def test_gera_reservas_com_contrato_id(client, full, db, cen, novo_contrato):
    cid = contrato_curto(novo_contrato)
    r = agendar(client, full, cid, [sel(SEG, cen.p1), sel(QUA, cen.p1)])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["reservas_criadas"] == 8 and j["sessoes_criadas"] == 8 and j["conflitos"] == [] and j["mensagem_conflitos"] is None
    reservas = db.scalars(select(Reserva)).all()
    assert len(reservas) == 8 and all(x.contrato_id == cid and x.aluno_id == cen.aluno.id for x in reservas)
    d = client.get(f"/api/contratos/{cid}", headers=cabecalho(full)).json()
    assert d["aulas_futuras"] == 8 and d["precisa_agenda"] is False
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "contrato.agenda"))
    # idempotente: repetir não duplica
    j2 = agendar(client, full, cid, [sel(SEG, cen.p1), sel(QUA, cen.p1)]).json()
    assert j2["reservas_criadas"] == 0 and j2["ja_existentes"] == 8
    assert client.get(f"/api/contratos/{cid}/agenda/opcoes", headers=cabecalho(full)).json()["dias_semana_agendados"] == [0, 2]


def test_escolha_invalida_nao_cria_nada(client, full, db, cen, novo_contrato):
    cid = contrato_curto(novo_contrato)
    h = full
    assert agendar(client, h, cid, [sel(SEG, cen.p1)]).status_code == 422  # precisa de exatamente 2
    assert agendar(client, h, cid, [sel(SEG, cen.p1), sel(SEG, cen.p1, "10:00", "10:50")]).status_code == 422  # um por dia
    r = agendar(client, h, cid, [sel(SEG, cen.p1), sel(QUA, cen.p1, "20:00", "20:50")])
    assert r.status_code == 422 and "invalido" in r.json()["detail"]  # fora do funcionamento
    assert agendar(client, h, cid, [sel(SEG, cen.p1), sel(QUA, cen.p1, "09:00", "xx")]).status_code == 422
    assert contar(db, Reserva) == 0 and contar(db, AulaSessao) == 0


def test_conflito_de_vaga_e_listado_sem_desfazer_o_resto(client, full, db, cen, novo_contrato, monkeypatch):
    cid = contrato_curto(novo_contrato)
    # a lotação aparece DEPOIS de a tela listar os horários (corrida): 09:00 de 16/11 enche
    slots = agenda_servico.calcular_slots(db, unidade_id=cen.un.id, tipo_servico_id=cen.srv.id, inicio=date(2026, 11, 2), fim=date(2026, 11, 29))
    sessao = agenda_servico.criar_sessao(db, unidade_id=cen.un.id, tipo_servico_id=cen.srv.id, profissional_id=cen.p1.id,
                                         data=date(2026, 11, 16), hora_inicio=time(9, 0), capacidade=1)
    agenda_servico.criar_reserva(db, cen.outro.id, sessao.id)
    db.commit()
    monkeypatch.setattr(agenda_servico, "calcular_slots", lambda *_a, **_k: slots)
    r = agendar(client, full, cid, [sel(SEG, cen.p1), sel(QUA, cen.p1)])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["reservas_criadas"] == 7 and j["conflitos"] == ["Sem vaga em 2026-11-16 09:00"]
    assert j["mensagem_conflitos"] == "Conflitos ao reservar: Sem vaga em 2026-11-16 09:00"
    assert contar(db, Reserva, Reserva.contrato_id == cid) == 7


def test_plano_avulso_nao_tem_agenda(client, full, cen, novo_contrato):
    cid = novo_contrato(plano_id=cen.avulso.id)["contrato"]["id"]
    assert client.get(f"/api/contratos/{cid}/agenda/opcoes", headers=cabecalho(full)).status_code == 409


def test_contrato_vencido_nao_agenda(client, full, db, cen, novo_contrato):
    cid = novo_contrato(data_inicio="2026-01-05", data_fim="2026-03-05")["contrato"]["id"]
    assert client.get(f"/api/contratos/{cid}/agenda/opcoes", headers=cabecalho(full)).status_code == 409


# ---------------------------------------------------------------------------------------------------- exclusão
def _com_agenda(client, full, cen, novo_contrato):
    cid = contrato_curto(novo_contrato)
    assert agendar(client, full, cid, [sel(SEG, cen.p1), sel(QUA, cen.p1)]).status_code == 200
    return cid


def test_exclusao_exige_confirmacao_e_mostra_o_plano(client, full, db, cen, novo_contrato):
    cid = _com_agenda(client, full, cen, novo_contrato)
    h = cabecalho(full)
    p = client.get(f"/api/contratos/{cid}/exclusao", headers=h).json()
    assert p["pode_excluir"] is True and len(p["contas_a_excluir"]) == 3
    assert len(p["reservas_a_excluir"]) == 8 and p["sessoes_que_ficam_vazias"] == 8 and p["reservas_mantidas"] == 0
    assert p["documento_pdf_sera_excluido"] is True and "Será apagado" in p["resumo"]
    r = client.delete(f"/api/contratos/{cid}", headers=h)
    assert r.status_code == 409 and "Confirme a exclusao" in r.json()["detail"]
    assert contar(db, Contrato) == 1 and contar(db, Reserva) == 8  # o GET do plano e o DELETE sem confirmar não mexem em nada


def test_exclui_contas_abertas_reservas_futuras_e_sessoes_vazias(client, full, db, cen, novo_contrato):
    cid = _com_agenda(client, full, cen, novo_contrato)
    # um colega na aula de segunda 02/11 09:00 (a aula NÃO pode sumir) e uma aula avulsa do mesmo aluno (NÃO é do contrato)
    sessao = db.scalar(select(AulaSessao).where(AulaSessao.data == date(2026, 11, 2)))
    agenda_servico.criar_reserva(db, cen.outro.id, sessao.id)
    avulsa_sessao = agenda_servico.criar_sessao(db, unidade_id=cen.un.id, tipo_servico_id=cen.srv.id, profissional_id=cen.p1.id,
                                                data=date(2026, 11, 3), hora_inicio=time(9, 0))
    avulsa = agenda_servico.criar_reserva(db, cen.aluno.id, avulsa_sessao.id)
    db.commit()
    r = client.delete(f"/api/contratos/{cid}?confirmar=true", headers=cabecalho(full))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j == {"contas_excluidas": 3, "reservas_excluidas": 8, "reservas_mantidas": 0, "sessoes_excluidas": 7}
    assert contar(db, Contrato) == 0 and contar(db, ContaReceber, ContaReceber.contrato_id.isnot(None)) == 0
    assert contar(db, AlunoDocumento) == 0  # PDF de contrato não assinado vai junto
    assert contar(db, AulaSessao, AulaSessao.id == sessao.id) == 1  # tinha colega: a aula fica
    assert contar(db, Reserva, Reserva.id == avulsa.id) == 1  # aula avulsa intacta
    assert contar(db, Reserva) == 2
    ex = db.scalar(select(Auditoria).where(Auditoria.acao == "contrato.excluir"))
    assert ex and ex.antes_json["aluno_id"] == cen.aluno.id and ex.depois_json["aulas_excluidas"] == 8


def test_aulas_passadas_e_evolucao_ficam_sem_vinculo(client, full, db, cen, novo_contrato):
    cid = _com_agenda(client, full, cen, novo_contrato)
    sessao = db.scalar(select(AulaSessao).where(AulaSessao.data == date(2026, 11, 2)))
    reserva = db.scalar(select(Reserva).where(Reserva.aula_sessao_id == sessao.id))
    reserva.status = StatusReserva.CONCLUIDA
    db.add_all([Evolucao(reserva_id=reserva.id, profissional_id=cen.p1.id, texto="Ótima evolução."),
                Avaliacao(reserva_id=reserva.id, profissional_id=cen.p1.id, texto="Avaliação inicial.")])
    # outra aula do contrato com evolução registrada, ainda futura: também é preservada
    outra = db.scalar(select(Reserva).join(AulaSessao).where(AulaSessao.data == date(2026, 11, 9)))
    db.add(Evolucao(reserva_id=outra.id, profissional_id=cen.p1.id, texto="Evolução antecipada."))
    db.commit()
    p = client.get(f"/api/contratos/{cid}/exclusao", headers=cabecalho(full)).json()
    assert p["reservas_mantidas"] == 2 and len(p["reservas_a_excluir"]) == 6
    assert client.delete(f"/api/contratos/{cid}?confirmar=true", headers=cabecalho(full)).status_code == 200
    db.expire_all()
    assert contar(db, Evolucao) == 2 and contar(db, Avaliacao) == 1
    mantidas = db.scalars(select(Reserva)).all()
    assert len(mantidas) == 2 and all(x.contrato_id is None for x in mantidas)


def test_conta_paga_bloqueia_a_exclusao_e_oferece_encerrar(client, full, db, cen, novo_contrato):
    cid = _com_agenda(client, full, cen, novo_contrato)
    conta = db.scalar(select(ContaReceber).where(ContaReceber.contrato_id == cid).order_by(ContaReceber.vencimento))
    conta.status = StatusReceber.PAGO
    conta.pagamento = date(2026, 11, 2)
    db.commit()
    h = cabecalho(full)
    p = client.get(f"/api/contratos/{cid}/exclusao", headers=h).json()
    assert p["pode_excluir"] is False and "já paga" in p["motivos_bloqueio"][0] and "Encerrar" in p["alternativa"]
    assert len(p["contas_pagas"]) == 1
    r = client.delete(f"/api/contratos/{cid}?confirmar=true", headers=h)
    assert r.status_code == 409 and "Encerrar" in r.json()["detail"]
    assert contar(db, Contrato) == 1 and contar(db, ContaReceber) == 3 and contar(db, Reserva) == 8 and contar(db, AulaSessao) == 8


def test_comissao_bloqueia_a_exclusao(client, full, db, cen, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    conta = db.scalar(select(ContaReceber).where(ContaReceber.contrato_id == cid))
    db.add(Comissao(profissional_id=cen.p1.id, conta_receber_id=conta.id, competencia="2026-11", valor_base=conta.valor,
                    percentual=10, valor=30))
    db.commit()
    r = client.delete(f"/api/contratos/{cid}?confirmar=true", headers=cabecalho(full))
    assert r.status_code == 409 and "comiss" in r.json()["detail"]


def test_contrato_assinado_mantem_o_pdf_assinado_no_prontuario(client, full, db, cen, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    h = cabecalho(full)
    assert client.post(f"/api/contratos/{cid}/assinatura-local", headers=h, json={
        "nome": "Maria da Silva Souza", "documento": "52998224725", "assinatura": png_data_url()}).status_code == 200
    p = client.get(f"/api/contratos/{cid}/exclusao", headers=h).json()
    assert p["documento_pdf_sera_excluido"] is False
    assert client.delete(f"/api/contratos/{cid}?confirmar=true", headers=h).status_code == 200
    db.expire_all()
    doc = db.scalar(select(AlunoDocumento))
    assert doc is not None and doc.contrato_id is None


def test_falha_no_financeiro_desfaz_a_exclusao(client, full, db, cen, novo_contrato, monkeypatch):
    cid = _com_agenda(client, full, cen, novo_contrato)

    def quebra(*_a, **_k):
        raise servico.fin.ErroDeNegocio("conta travada")

    monkeypatch.setattr(servico.fin, "excluir_conta_receber", quebra)
    r = client.delete(f"/api/contratos/{cid}?confirmar=true", headers=cabecalho(full))
    assert r.status_code == 409 and "conta travada" in r.json()["detail"]
    assert contar(db, Contrato) == 1 and contar(db, Reserva, Reserva.contrato_id == cid) == 8


def test_gerar_agenda_inexistente_e_exclusao_inexistente(client, full):
    assert client.get("/api/contratos/999/agenda/opcoes", headers=cabecalho(full)).status_code == 404
    assert client.delete("/api/contratos/999?confirmar=true", headers=cabecalho(full)).status_code == 404
