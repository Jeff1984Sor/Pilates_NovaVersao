"""Reposição por PEDIDO (decisão do Jefferson, 25/10/2026): o aluno pede, a gerência (Full) aprova ou recusa."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select

from app.core.models import Auditoria
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.app_aluno import routes
from app.modules.app_aluno.models import ReposicaoPedido, StatusPedido
from tests.agenda import fabrica
from tests.app_aluno.conftest import AGORA_FIXO, cab, entrar_aluno
from tests.conftest import auth

A = "/api/aluno-app"
E = "/api/reposicoes"


def desmarcar_ana(db, cenario):
    agenda.desmarcar_reserva_do_aluno(db, cenario.ana.id, cenario.r_ana.id, agora=AGORA_FIXO)
    db.commit()


def pedir(client, h, rid, preferencia="Prefiro terça de manhã"):
    return client.post(f"{A}/reposicoes/{rid}/pedir", json={"preferencia": preferencia}, headers=h)


def nova_aula(db, cenario, dia=date(2026, 10, 28), inicio=time(8, 0), **kw):
    s = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof, dia=dia, inicio=inicio, **kw)
    db.commit()
    return s


def acoes(db, acao):
    return db.scalars(select(Auditoria).where(Auditoria.acao == acao)).all()


# ----------------------------------------------------------------------------------------------------------- aluno
def test_pedir_cria_pedido_pendente_e_a_tela_mostra_a_situacao(client, db, cenario, ana_logada):
    desmarcar_ana(db, cenario)
    r = pedir(client, ana_logada, cenario.r_ana.id)
    assert r.status_code == 200
    j = r.json()
    assert j["pode_pedir"] is True and j["dentro_do_prazo"] is True and j["reposicao_ate"] == "2026-11-25"
    assert j["pedido"]["status"] == "PENDENTE" and j["pedido"]["preferencia"] == "Prefiro terça de manhã"
    lista = client.get(f"{A}/reposicoes", headers=ana_logada).json()
    assert len(lista) == 1 and lista[0]["pedido"]["status"] == "PENDENTE"
    p = db.scalars(select(ReposicaoPedido)).one()
    assert (p.aluno_id, p.reserva_origem_id, p.data_origem, p.hora_origem) == (cenario.ana.id, cenario.r_ana.id, date(2026, 10, 26), time(9, 0))
    # nada foi remarcado: continua desmarcada
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).status == StatusReserva.CANCELADA


def test_pedir_de_novo_atualiza_a_preferencia_sem_duplicar(client, db, cenario, ana_logada):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id, "segunda")
    r = pedir(client, ana_logada, cenario.r_ana.id, "quinta à tarde")
    assert r.status_code == 200 and r.json()["pedido"]["preferencia"] == "quinta à tarde"
    assert db.scalar(select(func.count()).select_from(ReposicaoPedido)) == 1


def test_preferencia_e_limpa_e_limitada_a_300(client, db, cenario, ana_logada):
    desmarcar_ana(db, cenario)
    r = pedir(client, ana_logada, cenario.r_ana.id, "  <script>alert(1)</script>\x00 terça\n\n  de   manhã  ")
    assert r.json()["pedido"]["preferencia"] == "script alert(1) /script terça de manhã"
    assert pedir(client, ana_logada, cenario.r_ana.id, "x" * 301).status_code == 422
    assert pedir(client, ana_logada, cenario.r_ana.id, "x" * 300).status_code == 200
    assert pedir(client, ana_logada, cenario.r_ana.id, None).json()["pedido"]["preferencia"] is None


def test_so_o_dono_pede(client, db, zap, cenario, ana_logada):
    agenda.desmarcar_reserva_do_aluno(db, cenario.bruna.id, cenario.r_bruna.id, agora=AGORA_FIXO)
    db.commit()
    assert pedir(client, ana_logada, cenario.r_bruna.id).status_code == 404
    assert pedir(client, ana_logada, 999999).status_code == 404
    assert db.scalar(select(func.count()).select_from(ReposicaoPedido)) == 0
    # a lista da Ana não mostra o pedido (nem a aula) da Bruna
    assert client.get(f"{A}/reposicoes", headers=ana_logada).json() == []


def test_aula_nao_desmarcada_nao_pede(client, cenario, ana_logada):
    assert pedir(client, ana_logada, cenario.r_ana.id).status_code == 409


def test_prazo_vencido_nao_pede(client, db, cenario, ana_logada, monkeypatch):
    desmarcar_ana(db, cenario)
    monkeypatch.setattr(routes, "_agora", lambda: AGORA_FIXO + timedelta(days=32))  # 26/11: um dia depois do prazo
    r = pedir(client, ana_logada, cenario.r_ana.id)
    assert r.status_code == 409 and "25/11/2026" in r.json()["detail"]
    lista = client.get(f"{A}/reposicoes", headers=ana_logada).json()
    assert lista[0]["dentro_do_prazo"] is False and lista[0]["pode_pedir"] is False


def test_aluno_nao_tem_mais_remarcacao_imediata_nem_opcoes(client, db, cenario, ana_logada):
    desmarcar_ana(db, cenario)
    nova = nova_aula(db, cenario)
    assert client.get(f"{A}/reposicoes/{cenario.r_ana.id}/opcoes", headers=ana_logada).status_code in (404, 405)
    r = client.post(f"{A}/reposicoes/{cenario.r_ana.id}/remarcar", json={"aula_id": nova.id}, headers=ana_logada)
    assert r.status_code in (404, 405)
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).status == StatusReserva.CANCELADA


# ------------------------------------------------------------------------------------------- 6 horas (aluno)
def test_aluno_so_desmarca_com_6h_de_antecedencia(client, db, cenario, ana_logada, monkeypatch):
    # aula 26/10 09:00 BRT = 12:00 UTC; limite 03:00 BRT = 06:00 UTC
    monkeypatch.setattr(routes, "_agora", lambda: datetime(2026, 10, 26, 6, 0, 1, tzinfo=UTC))
    r = client.post(f"{A}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada)
    assert r.status_code == 409 and "6 horas" in r.json()["detail"] and "03:00" in r.json()["detail"]
    aula = client.get(f"{A}/aulas", headers=ana_logada).json()[0]
    assert aula["pode_desmarcar"] is False and aula["pode_confirmar"] is True and aula["desmarcar_ate"] == "26/10 às 03:00"
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).status == StatusReserva.RESERVADA
    monkeypatch.setattr(routes, "_agora", lambda: datetime(2026, 10, 26, 6, 0, tzinfo=UTC))  # limite exato passa
    assert client.post(f"{A}/aulas/{cenario.r_ana.id}/desmarcar", headers=ana_logada).status_code == 200


# --------------------------------------------------------------------------------------------- permissões da equipe
def test_so_a_gerencia_enxerga_e_decide(client, db, cenario, ana_logada, secretaria, professor, full):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    nova = nova_aula(db, cenario)
    for token in (secretaria, professor):
        h = auth(token)
        assert client.get(E, headers=h).status_code == 403
        assert client.get(f"{E}/{pid}/opcoes", headers=h).status_code == 403
        assert client.post(f"{E}/{pid}/aprovar", json={"aula_id": nova.id}, headers=h).status_code == 403
        assert client.post(f"{E}/{pid}/recusar", json={"motivo": "não"}, headers=h).status_code == 403
    assert client.get(E).status_code == 401
    assert client.get(E, headers=ana_logada).status_code == 401  # token de aluno não entra na equipe
    assert client.get(E, headers=auth(full)).status_code == 200
    db.expire_all()
    assert db.get(ReposicaoPedido, pid).status == StatusPedido.PENDENTE


# --------------------------------------------------------------------------------------------- gerência: listar
def test_listagem_com_contagens_e_filtros(client, db, cenario, ana_logada, full, zap):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id, "terça")
    agenda.desmarcar_reserva_do_aluno(db, cenario.bruna.id, cenario.r_bruna.id, agora=AGORA_FIXO)
    db.commit()
    bruna = cab(entrar_aluno(client, zap, cenario.bruna))
    pedir(client, bruna, cenario.r_bruna.id, "sexta")
    j = client.get(E, headers=auth(full)).json()
    assert j["contagens"] == {"PENDENTE": 2, "APROVADO": 0, "RECUSADO": 0}
    item = next(i for i in j["itens"] if i["aluno"]["nome"] == "Ana Paula Souza")
    assert item["preferencia"] == "terça" and item["reposicao_ate"] == "2026-11-25" and item["aula_original"]["servico"] == "Pilates"
    client.post(f"{E}/{item['id']}/recusar", json={"motivo": "Sem agenda este mês"}, headers=auth(full))
    j = client.get(E, params={"status": "PENDENTE"}, headers=auth(full)).json()
    assert j["contagens"] == {"PENDENTE": 1, "APROVADO": 0, "RECUSADO": 1} and [i["aluno"]["nome"] for i in j["itens"]] == ["Bruna Lima"]
    assert [i["status"] for i in client.get(E, params={"status": "RECUSADO"}, headers=auth(full)).json()["itens"]] == ["RECUSADO"]
    assert len(client.get(E, params={"q": "bruna"}, headers=auth(full)).json()["itens"]) == 1
    assert client.get(E, params={"status": "XYZ"}, headers=auth(full)).status_code == 422


def test_opcoes_so_com_vaga_real(client, db, cenario, ana_logada, full):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    boa = nova_aula(db, cenario)
    cheia = nova_aula(db, cenario, dia=date(2026, 10, 27), inicio=time(8, 0))
    fabrica.reserva_direta(db, cenario.bruna, cheia)
    fabrica.reserva_direta(db, fabrica.aluno(db, cenario.un, "Carla Dias"), cheia)
    longe = nova_aula(db, cenario, dia=date(2026, 12, 15))
    outro = fabrica.servico(db, "Fisioterapia")
    fabrica.sessao(db, cenario.un, outro, cenario.prof, dia=date(2026, 10, 29))
    db.commit()
    ids = {o["aula_id"] for o in client.get(f"{E}/{pid}/opcoes", headers=auth(full)).json()}
    assert boa.id in ids and cheia.id not in ids and longe.id not in ids and cenario.s9.id not in ids
    com_excecao = {o["aula_id"] for o in client.get(f"{E}/{pid}/opcoes", params={"ignorar_prazo": True}, headers=auth(full)).json()}
    assert longe.id in com_excecao and cheia.id not in com_excecao


# --------------------------------------------------------------------------------------------- gerência: aprovar
def test_aprovar_remarca_consome_a_reposicao_avisa_o_aluno_e_audita(client, db, zap, cenario, ana_logada, full):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    nova = nova_aula(db, cenario)
    r = client.post(f"{E}/{pid}/aprovar", json={"aula_id": nova.id}, headers=auth(full))
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "APROVADO" and j["aprovado_data"] == "2026-10-28" and j["aprovado_hora"] == "08:00:00" and j["decidido_por"]
    db.expire_all()
    res = db.get(Reserva, cenario.r_ana.id)
    assert res.status == StatusReserva.RESERVADA and res.aula_sessao_id == nova.id and res.reposicao_ate is None
    assert db.get(AulaSessao, nova.id).reservas_ativas == 1
    p = db.get(ReposicaoPedido, pid)
    assert p.status == StatusPedido.APROVADO and p.reserva_nova_id == res.id and p.decidido_em and p.decidido_por_usuario_id and not p.ignorou_prazo
    # aviso por WhatsApp (falso)
    assert zap.enviadas[-1][0] == "5511999990001" and "28/10/2026 às 08:00" in zap.enviadas[-1][1]
    # auditoria
    a = acoes(db, "reposicao.aprovar")
    assert len(a) == 1 and a[0].entidade_id == str(pid) and "28/10/2026 08:00" in a[0].descricao
    # o aluno vê a situação
    item = client.get(f"{A}/reposicoes", headers=ana_logada).json()[0]
    assert item["pedido"]["status"] == "APROVADO" and item["pedido"]["aprovado_data"] == "2026-10-28" and item["pode_pedir"] is False
    # decidir de novo: 409
    assert client.post(f"{E}/{pid}/aprovar", json={"aula_id": nova.id}, headers=auth(full)).status_code == 409
    assert client.post(f"{E}/{pid}/recusar", json={"motivo": "tarde demais"}, headers=auth(full)).status_code == 409


def test_aprovar_aula_lotada_409_e_pedido_continua_pendente(client, db, cenario, ana_logada, full):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    cheia = nova_aula(db, cenario, dia=date(2026, 10, 27))
    fabrica.reserva_direta(db, cenario.bruna, cheia)
    fabrica.reserva_direta(db, fabrica.aluno(db, cenario.un, "Carla Dias"), cheia)
    db.commit()
    r = client.post(f"{E}/{pid}/aprovar", json={"aula_id": cheia.id}, headers=auth(full))
    assert r.status_code == 409
    assert client.post(f"{E}/{pid}/aprovar", json={"aula_id": 999999}, headers=auth(full)).status_code == 409
    db.expire_all()
    assert db.get(ReposicaoPedido, pid).status == StatusPedido.PENDENTE
    assert db.get(Reserva, cenario.r_ana.id).status == StatusReserva.CANCELADA
    assert db.get(AulaSessao, cheia.id).reservas_ativas == 2
    assert not acoes(db, "reposicao.aprovar")


def test_aprovar_aula_fora_do_prazo_so_com_ignorar_e_motivo(client, db, cenario, ana_logada, full):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    tarde = nova_aula(db, cenario, dia=date(2026, 12, 2))  # prazo vai até 25/11
    r = client.post(f"{E}/{pid}/aprovar", json={"aula_id": tarde.id}, headers=auth(full))
    assert r.status_code == 409 and "25/11/2026" in r.json()["detail"]
    assert client.post(f"{E}/{pid}/aprovar", json={"aula_id": tarde.id, "ignorar_prazo": True}, headers=auth(full)).status_code == 422
    r = client.post(f"{E}/{pid}/aprovar", json={"aula_id": tarde.id, "ignorar_prazo": True, "motivo": "Aluna viajando"}, headers=auth(full))
    assert r.status_code == 200 and r.json()["ignorou_prazo"] is True and r.json()["motivo_ignorar_prazo"] == "Aluna viajando"
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).aula_sessao_id == tarde.id
    assert "PRAZO IGNORADO: Aluna viajando" in acoes(db, "reposicao.aprovar")[0].descricao


def test_aprovar_com_prazo_vencido_exige_excecao(client, db, cenario, ana_logada, full, monkeypatch):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    nova = nova_aula(db, cenario, dia=date(2026, 11, 27))
    monkeypatch.setattr(routes, "_agora", lambda: AGORA_FIXO + timedelta(days=32))  # 26/11: reposição vencida
    j = client.get(E, headers=auth(full)).json()["itens"][0]
    assert j["prazo_vencido"] is True
    assert client.post(f"{E}/{pid}/aprovar", json={"aula_id": nova.id}, headers=auth(full)).status_code == 409
    r = client.post(f"{E}/{pid}/aprovar", json={"aula_id": nova.id, "ignorar_prazo": True, "motivo": "Atraso nosso"}, headers=auth(full))
    assert r.status_code == 200 and r.json()["ignorou_prazo"] is True


def test_aprovar_quando_a_aula_ja_foi_remarcada_pela_recepcao_409(client, db, cenario, ana_logada, full):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    nova = nova_aula(db, cenario)
    agenda.remarcar_reserva(db, cenario.r_ana.id, data=nova.data, hora_inicio=nova.hora_inicio, agora=AGORA_FIXO)
    db.commit()
    other = nova_aula(db, cenario, dia=date(2026, 10, 29))
    assert client.post(f"{E}/{pid}/aprovar", json={"aula_id": other.id}, headers=auth(full)).status_code == 409


# --------------------------------------------------------------------------------------------- gerência: recusar
def test_recusar_exige_motivo_avisa_e_o_aluno_ve(client, db, zap, cenario, ana_logada, full):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    assert client.post(f"{E}/{pid}/recusar", json={"motivo": "  "}, headers=auth(full)).status_code == 422
    assert client.post(f"{E}/{pid}/recusar", json={}, headers=auth(full)).status_code == 422
    r = client.post(f"{E}/{pid}/recusar", json={"motivo": "Estúdio fechado nesse período"}, headers=auth(full))
    assert r.status_code == 200 and r.json()["status"] == "RECUSADO"
    assert "Estúdio fechado nesse período" in zap.enviadas[-1][1]
    a = acoes(db, "reposicao.recusar")
    assert len(a) == 1 and "Estúdio fechado" in a[0].descricao
    item = client.get(f"{A}/reposicoes", headers=ana_logada).json()[0]
    assert item["pedido"]["status"] == "RECUSADO" and item["pedido"]["motivo_recusa"] == "Estúdio fechado nesse período"
    assert item["pode_pedir"] is False
    assert pedir(client, ana_logada, cenario.r_ana.id).status_code == 409
    db.expire_all()
    assert db.get(Reserva, cenario.r_ana.id).status == StatusReserva.CANCELADA


def test_falha_no_aviso_nao_desfaz_a_decisao(client, db, zap, cenario, ana_logada, full, monkeypatch):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))

    def cai(*_):
        raise RuntimeError("sem sessão no WhatsApp")

    monkeypatch.setattr(zap, "enviar_texto", cai)
    assert client.post(f"{E}/{pid}/recusar", json={"motivo": "Sem vaga"}, headers=auth(full)).status_code == 200
    db.expire_all()
    assert db.get(ReposicaoPedido, pid).status == StatusPedido.RECUSADO


def test_aprovada_e_desmarcada_de_novo_permite_novo_pedido(client, db, cenario, ana_logada, full, monkeypatch):
    desmarcar_ana(db, cenario)
    pedir(client, ana_logada, cenario.r_ana.id)
    pid = db.scalar(select(ReposicaoPedido.id))
    nova = nova_aula(db, cenario, dia=date(2026, 10, 30))
    client.post(f"{E}/{pid}/aprovar", json={"aula_id": nova.id}, headers=auth(full))
    db.expire_all()
    # a Ana desmarca a aula da reposição (dias antes), o que abre um novo prazo de 30 dias
    agenda.desmarcar_reserva_do_aluno(db, cenario.ana.id, cenario.r_ana.id, agora=AGORA_FIXO + timedelta(hours=1))
    db.commit()
    r = pedir(client, ana_logada, cenario.r_ana.id, "de novo")
    assert r.status_code == 200 and r.json()["reposicao_ate"] == "2026-11-29"
    assert sorted(p.status.value for p in db.scalars(select(ReposicaoPedido))) == ["CANCELADO", "PENDENTE"]
    assert len(client.get(f"{A}/reposicoes", headers=ana_logada).json()) == 1
