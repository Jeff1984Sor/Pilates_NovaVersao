"""Webhook do TotalPass (R14): token obrigatório, cada ramo do processamento, idempotência, capacidade e cancelamento.

Payloads sintéticos. Nenhum teste chama a internet (o cliente HTTP do TotalPass é sempre falso).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core import segredos
from app.core.db import agora
from app.core.models import Auditoria
from app.domain.financeiro import hoje_de_negocio
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, AlunoTelefone
from app.modules.cadastros.models import TipoServico, Unidade
from app.modules.integracoes import routes as rotas_integ
from app.modules.integracoes.models import TotalpassConfig, TotalpassEvento
from tests.integracoes.conftest import cpf_valido, novo_aluno

URL = "/api/webhooks/totalpass"
CPF1, CPF2, CPF3 = cpf_valido(300000001), cpf_valido(300000002), cpf_valido(300000003)


def hoje():
    return hoje_de_negocio(agora())


def payload(cpf=CPF1, *, titulo="Pilates", status="active", dia=None, hora="09:00", slot="slot-1", evento="ev-1",
            nome="Maria Sintetica", email="maria@exemplo.invalid", fone="(11) 98888-7777", place="PLACE-1"):
    return {
        "event": {"id": evento, "title": titulo},
        "place": {"place": place},
        "user": {"name": nome, "email": email, "phone": fone, "document_number": cpf, "document_type": "cpf"},
        "slot": {"id": slot, "status": status, "date": (dia or hoje()).isoformat(), "start_time": hora},
    }


@pytest.fixture
def tp(client, db, base, full):
    """Unidade com TotalPass configurado (aluno automático, só o dia) e token de webhook gerado. Devolve o necessário."""
    cfg = client.put(f"/api/integracoes/totalpass/{base.unidade.id}", headers=full, json={
        "ativo": True, "place_id": "PLACE-1", "criar_aluno_automatico": True, "somente_dia": True,
        "partner_api_key": "chave-parceiro-sintetica-1234", "place_api_key": "chave-unidade-sintetica-5678"})
    assert cfg.status_code == 200, cfg.text
    tok = client.post(f"/api/integracoes/totalpass/{base.unidade.id}/token-webhook", headers=full)
    assert tok.status_code == 200, tok.text
    return type("TP", (), {"unidade": base.unidade, "servico": base.servico, "token": tok.json()["valor"],
                           "h": {"X-Totalpass-Token": tok.json()["valor"]}, "full": full})


def enviar(client, tp, corpo, headers=None):
    return client.post(URL, json=corpo, headers=tp.h if headers is None else headers)


def evento(db, **filtros):
    db.expire_all()
    q = select(TotalpassEvento).order_by(TotalpassEvento.id.desc())
    for k, v in filtros.items():
        q = q.where(getattr(TotalpassEvento, k) == v)
    return db.scalars(q).first()


def total(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


# ------------------------------------------------------------------------------------------------ autenticação
def test_sem_token_configurado_a_rota_recusa(client, db, base):
    """O antigo aceitava QUALQUER POST quando nenhum token estava configurado. O novo recusa."""
    r = client.post(URL, json=payload(), headers={"X-Totalpass-Token": "qualquer-coisa"})
    assert r.status_code == 403 and "não configurado" in r.json()["detail"]
    assert client.post(URL, json=payload()).status_code == 403
    assert total(db, TotalpassEvento) == 0 and total(db, Aluno) == 0


def test_config_sem_token_gravado_tambem_recusa(client, db, base, full):
    client.put(f"/api/integracoes/totalpass/{base.unidade.id}", headers=full, json={"partner_api_key": "x" * 12})
    assert client.post(URL, json=payload(), headers={"X-Totalpass-Token": ""}).status_code == 403


def test_token_ausente_401_e_errado_403(client, db, tp):
    assert client.post(URL, json=payload()).status_code == 401
    assert client.post(URL, json=payload(), headers={"X-Totalpass-Token": "errado"}).status_code == 403
    assert client.post(URL, json=payload(), headers={"X-Totalpass-Token": tp.token + "x"}).status_code == 403
    assert client.post(URL, json=payload(), headers={"X-Totalpass-Token": tp.token[:-1]}).status_code == 403
    assert client.post(URL, json=payload(), headers={"X-Totalpass-Token": "tokén-ñ-não-ascii".encode()}).status_code == 403
    assert total(db, TotalpassEvento) == 0 and total(db, Aluno) == 0


def test_token_de_usuario_logado_nao_vale_no_webhook(client, tp):
    assert client.post(URL, json=payload(), headers={**tp.full}).status_code == 401


def test_comparacao_do_token_em_tempo_constante(monkeypatch, client, tp):
    usados = []
    original = rotas_integ.hmac.compare_digest

    def espiao(a, b):
        usados.append((type(a), type(b)))
        return original(a, b)

    monkeypatch.setattr(rotas_integ.hmac, "compare_digest", espiao)
    assert enviar(client, tp, payload()).status_code == 200
    assert usados and all(t == (bytes, bytes) for t in usados)


def test_webhook_so_aceita_post(client, tp):
    assert client.get(URL, headers=tp.h).status_code == 405


def test_rate_limit_de_falhas_do_webhook(client, tp, monkeypatch):
    monkeypatch.setattr(rotas_integ, "LIMITE_FALHAS_WEBHOOK_POR_IP", 3)
    codigos = [client.post(URL, json=payload(), headers={"X-Totalpass-Token": f"chute-{i}"}).status_code for i in range(5)]
    assert codigos == [403, 403, 403, 429, 429]


def test_rate_limit_geral_do_webhook(client, tp, monkeypatch):
    monkeypatch.setattr(rotas_integ, "LIMITE_WEBHOOK_POR_IP", 2)
    codigos = [enviar(client, tp, payload(slot=f"s{i}", evento=f"e{i}")).status_code for i in range(4)]
    assert codigos[:2] == [200, 200] and codigos[2:] == [429, 429]


def test_payload_enorme_ou_invalido(client, tp):
    assert client.post(URL, content=b"nao e json", headers={**tp.h, "Content-Type": "application/json"}).status_code == 422
    assert enviar(client, tp, ["lista"]).status_code == 422
    r = client.post(URL, content=b"{}", headers={**tp.h, "Content-Type": "application/json", "Content-Length": str(10**7)})
    assert r.status_code in (413, 400)


def test_integracao_desativada_responde_202_e_nao_grava(client, db, base, tp, full):
    client.put(f"/api/integracoes/totalpass/{base.unidade.id}", headers=full, json={"ativo": False})
    r = enviar(client, tp, payload())
    assert r.status_code == 202 and r.json()["warning"]
    assert total(db, TotalpassEvento) == 0 and total(db, Aluno) == 0


# ------------------------------------------------------------------------------------------------ processamento
def test_cria_aluno_sessao_sem_profissional_e_reserva(client, db, tp):
    r = enviar(client, tp, payload())
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["reserva_id"]
    db.expire_all()
    aluno = db.scalar(select(Aluno).where(Aluno.cpf == CPF1))
    assert aluno.nome == "Maria Sintetica" and aluno.email == "maria@exemplo.invalid" and aluno.unidade_id == tp.unidade.id
    assert aluno.codigo_legado is not None and aluno.sem_cpf is False
    tel = db.scalar(select(AlunoTelefone).where(AlunoTelefone.aluno_id == aluno.id))
    assert tel.numero == "5511988887777" and tel.numero_original == "(11) 98888-7777"
    sessao = db.scalar(select(AulaSessao))
    assert sessao.profissional_id is None and sessao.tipo_servico_id == tp.servico.id and sessao.unidade_id == tp.unidade.id
    assert sessao.data == hoje() and sessao.hora_inicio.strftime("%H:%M") == "09:00" and sessao.hora_fim.strftime("%H:%M") == "09:50"
    assert sessao.capacidade is None  # herda a capacidade da unidade
    reserva = db.scalar(select(Reserva))
    assert reserva.aluno_id == aluno.id and reserva.status == StatusReserva.RESERVADA and sessao.reservas_ativas == 1
    ev = evento(db)
    assert ev.resultado == "processado" and ev.erro is None and ev.processado_em and ev.reserva_id == reserva.id
    assert ev.event_id == "ev-1" and ev.slot_id == "slot-1" and ev.documento_usuario == CPF1 and ev.origem == "webhook"
    assert ev.payload["event"]["title"] == "Pilates"


def test_cpf_com_mascara_e_achar_aluno_existente_sem_duplicar(client, db, base, tp):
    existente = novo_aluno(db, base.unidade.id, "Aluna Antiga", 1)
    existente.cpf = CPF2
    db.commit()
    masc = f"{CPF2[:3]}.{CPF2[3:6]}.{CPF2[6:9]}-{CPF2[9:]}"
    r = enviar(client, tp, payload(masc, nome="Outro Nome"))
    assert r.status_code == 200
    db.expire_all()
    assert total(db, Aluno) == 1
    assert db.scalar(select(Reserva.aluno_id)) == existente.id
    assert db.get(Aluno, existente.id).nome == "Aluna Antiga"  # não sobrescreve cadastro


def test_nao_cria_aluno_quando_desligado(client, db, base, tp, full):
    client.put(f"/api/integracoes/totalpass/{base.unidade.id}", headers=full, json={"criar_aluno_automatico": False})
    r = enviar(client, tp, payload())
    assert r.status_code == 400 and r.json()["error"] == "Aluno não encontrado pelo CPF."
    assert total(db, Aluno) == 0 and total(db, Reserva) == 0
    ev = evento(db)
    assert ev.resultado == "erro" and ev.erro == "Aluno não encontrado pelo CPF." and ev.processado_em is None


@pytest.mark.parametrize("doc,msg", [("", "CPF não informado"), ("123.456", "CPF inválido"), ("11111111111", "CPF inválido"),
                                      ("52998224724", "CPF inválido")])
def test_cpf_ruim_nao_cria_aluno(client, db, tp, doc, msg):
    r = enviar(client, tp, payload(doc))
    assert r.status_code == 400 and msg in r.json()["error"]
    assert total(db, Aluno) == 0 and total(db, Reserva) == 0 and total(db, AulaSessao) == 0
    assert evento(db).resultado == "erro"


def test_servico_resolvido_pelo_titulo(client, db, base, tp):
    db.add(TipoServico(nome="Pilates Solo Avançado"))
    db.commit()
    assert enviar(client, tp, payload(titulo="pilates")).status_code == 200  # exato (sem diferenciar maiúsculas)
    db.expire_all()
    assert db.scalar(select(AulaSessao.tipo_servico_id)) == base.servico.id
    assert enviar(client, tp, payload(CPF2, titulo="Solo Avan", slot="s2", evento="e2", hora="10:00")).status_code == 200  # contém
    db.expire_all()
    ids = {s.hora_inicio.strftime("%H:%M"): s.tipo_servico_id for s in db.scalars(select(AulaSessao))}
    assert ids["10:00"] != base.servico.id


def test_servico_inativo_nao_e_usado_e_sem_padrao_da_erro(client, db, base, tp):
    base.servico.ativo = False
    db.commit()
    r = enviar(client, tp, payload())
    assert r.status_code == 400 and "Tipo de serviço não encontrado" in r.json()["error"]
    assert total(db, Aluno) == 0  # nada pela metade: o aluno não ficou criado


def test_servico_padrao_quando_o_titulo_nao_casa(client, db, base, tp, full):
    padrao = TipoServico(nome="TotalPass")
    db.add(padrao)
    db.commit()
    r = enviar(client, tp, payload(titulo="Evento Desconhecido"))
    assert r.status_code == 400
    client.put(f"/api/integracoes/totalpass/{base.unidade.id}", headers=full, json={"servico_padrao_id": padrao.id})
    r = enviar(client, tp, payload(titulo="Evento Desconhecido"))
    assert r.status_code == 200, r.text  # o mesmo evento, reenviado, agora é processado (erro anterior não trava)
    db.expire_all()
    assert db.scalar(select(AulaSessao.tipo_servico_id)) == padrao.id
    assert total(db, TotalpassEvento) == 1  # reaproveitou a linha do evento com erro


def test_capacidade_da_unidade_e_respeitada(client, db, tp):
    assert tp.unidade.capacidade == 2
    assert enviar(client, tp, payload(CPF1, slot="s1", evento="e1")).status_code == 200
    assert enviar(client, tp, payload(CPF2, slot="s2", evento="e2")).status_code == 200
    r = enviar(client, tp, payload(CPF3, slot="s3", evento="e3"))
    assert r.status_code == 400 and "Capacidade excedida" in r.json()["error"] and "2 de 2" in r.json()["error"]
    db.expire_all()
    assert total(db, Reserva) == 2 and db.scalar(select(AulaSessao.reservas_ativas)) == 2
    ev = evento(db, slot_id="s3")
    assert ev.resultado == "erro" and "Capacidade excedida" in ev.erro and ev.reserva_id is None
    # o aluno não ficou criado pela metade quando a reserva falhou
    assert db.scalar(select(Aluno).where(Aluno.cpf == CPF3)) is None


def test_cancelamento_libera_vaga_e_mantem_historico(client, db, tp):
    assert enviar(client, tp, payload(CPF1, slot="s1", evento="e1")).status_code == 200
    assert enviar(client, tp, payload(CPF2, slot="s2", evento="e2")).status_code == 200
    r = enviar(client, tp, payload(CPF1, slot="s1", evento="e1", status="canceled"))
    assert r.status_code == 200 and r.json()["resultado"] == "cancelado" and r.json()["reserva_id"]
    db.expire_all()
    aluno = db.scalar(select(Aluno).where(Aluno.cpf == CPF1))
    reserva = db.scalar(select(Reserva).where(Reserva.aluno_id == aluno.id))
    assert reserva.status == StatusReserva.CANCELADA and reserva.reposicao_ate is None
    assert db.scalar(select(AulaSessao.reservas_ativas)) == 1
    # a vaga liberada pode ser usada por outro aluno
    assert enviar(client, tp, payload(CPF3, slot="s3", evento="e3")).status_code == 200
    assert evento(db, slot_id="s1", status="canceled").resultado == "cancelado"


@pytest.mark.parametrize("status", ["canceled", "cancelled", "inactive", "CANCELED", "Inactive"])
def test_status_de_cancelamento(client, db, tp, status):
    enviar(client, tp, payload())
    r = enviar(client, tp, payload(status=status))
    assert r.status_code == 200 and r.json()["resultado"] == "cancelado"
    db.expire_all()
    assert db.scalar(select(Reserva.status)) == StatusReserva.CANCELADA


def test_cancelar_sem_reserva_nao_cria_nada(client, db, tp):
    r = enviar(client, tp, payload(status="canceled"))
    assert r.status_code == 200 and r.json()["resultado"] == "cancelado" and r.json()["reserva_id"] is None
    assert total(db, Aluno) == 0 and total(db, AulaSessao) == 0 and total(db, Reserva) == 0
    assert evento(db).resultado == "cancelado"


def test_cancelar_duas_vezes_e_idempotente(client, db, tp):
    enviar(client, tp, payload())
    assert enviar(client, tp, payload(status="canceled")).status_code == 200
    r = enviar(client, tp, payload(status="canceled"))
    assert r.status_code == 200 and r.json().get("duplicado") is True
    db.expire_all()
    assert db.scalar(select(AulaSessao.reservas_ativas)) == 0


def test_reagendar_depois_de_cancelar_reativa_a_mesma_reserva(client, db, tp):
    enviar(client, tp, payload())
    enviar(client, tp, payload(status="canceled"))
    r = enviar(client, tp, payload(slot="slot-2", evento="ev-2"))  # novo agendamento do mesmo aluno na mesma aula
    assert r.status_code == 200
    db.expire_all()
    assert total(db, Reserva) == 1 and db.scalar(select(Reserva.status)) == StatusReserva.RESERVADA
    assert db.scalar(select(AulaSessao.reservas_ativas)) == 1


def test_somente_dia_descarta_outro_dia(client, db, base, tp, full):
    amanha = hoje() + timedelta(days=1)
    r = enviar(client, tp, payload(dia=amanha))
    assert r.status_code == 202 and r.json()["descartado"] == "Fora do dia atual."
    assert total(db, Aluno) == 0 and total(db, Reserva) == 0 and total(db, AulaSessao) == 0
    ev = evento(db)
    assert ev.resultado == "descartado" and ev.erro == "Fora do dia atual." and ev.processado_em is None
    client.put(f"/api/integracoes/totalpass/{base.unidade.id}", headers=full, json={"somente_dia": False})
    r = enviar(client, tp, payload(dia=amanha))  # o mesmo evento descartado antes agora é processado
    assert r.status_code == 200 and r.json()["resultado"] == "processado"
    assert total(db, TotalpassEvento) == 1


def test_idempotencia_por_evento_slot_status_e_documento(client, db, tp):
    primeira = enviar(client, tp, payload())
    segunda = enviar(client, tp, payload())
    assert primeira.status_code == 200 and segunda.status_code == 200
    assert segunda.json() == {"ok": True, "duplicado": True, "reserva_id": primeira.json()["reserva_id"]}
    db.expire_all()
    assert total(db, TotalpassEvento) == 1 and total(db, Reserva) == 1 and total(db, Aluno) == 1
    assert db.scalar(select(AulaSessao.reservas_ativas)) == 1
    # mesmo "evento" (a aula) com outro aluno NÃO é duplicado
    assert enviar(client, tp, payload(CPF2, slot="slot-2")).json().get("duplicado") is None
    assert total(db, TotalpassEvento) == 2


def test_dois_agendamentos_do_mesmo_aluno_na_mesma_aula_nao_duplicam_reserva(client, db, tp):
    enviar(client, tp, payload(slot="a", evento="e1"))
    r = enviar(client, tp, payload(slot="b", evento="e2"))  # outro slot, mesmo aluno/aula
    assert r.status_code == 200
    db.expire_all()
    assert total(db, Reserva) == 1 and db.scalar(select(AulaSessao.reservas_ativas)) == 1


def test_data_hora_formatos(client, db, tp):
    h = hoje().isoformat()
    p = payload()
    p["slot"] = {"id": "x", "status": "active", "date": f"{h}T10:30:00", "start_time": ""}
    assert enviar(client, tp, p).status_code == 200
    p2 = payload(CPF2, slot="y", evento="e2")
    p2["slot"] = {"id": "y", "status": "active", "start_at": h, "startTime": "11:15:00"}
    assert enviar(client, tp, p2).status_code == 200
    db.expire_all()
    horas = sorted(s.hora_inicio.strftime("%H:%M") for s in db.scalars(select(AulaSessao)))
    assert horas == ["10:30", "11:15"]


@pytest.mark.parametrize("slot,msg", [
    ({"id": "1", "status": "active", "start_time": "09:00"}, "Data não informada"),
    ({"id": "1", "status": "active", "date": "ontem", "start_time": "09:00"}, "Data inválida"),
    ({"id": "1", "status": "active", "date": "HOJE", "start_time": "9h"}, "Data inválida"),
    ({"id": "1", "status": "active", "date": "2026-10-25", "start_time": "9h"}, "Hora inválida"),
    ({"id": "1", "status": "active", "date": "2026-10-25"}, "Horário não informado"),
])
def test_datas_e_horas_invalidas_viram_erro_registrado(client, db, tp, slot, msg):
    p = payload()
    p["slot"] = slot
    r = enviar(client, tp, p)
    assert r.status_code == 400 and msg in r.json()["error"]
    assert evento(db).resultado == "erro" and total(db, Aluno) == 0


def test_duas_unidades_o_place_escolhe_a_config(client, db, base, tp, full):
    un2 = Unidade(nome="Filial", capacidade=5)
    db.add(un2)
    db.commit()
    client.put(f"/api/integracoes/totalpass/{un2.id}", headers=full, json={"place_id": "PLACE-2", "somente_dia": False})
    # mesmo token nas duas unidades (cadastrado pelo usuário): quem decide é o place
    cfg2 = db.scalar(select(TotalpassConfig).where(TotalpassConfig.unidade_id == un2.id))
    cfg1 = db.scalar(select(TotalpassConfig).where(TotalpassConfig.unidade_id == base.unidade.id))
    cfg2.webhook_token_cifrado = cfg1.webhook_token_cifrado
    db.commit()
    assert enviar(client, tp, payload(place="PLACE-2")).status_code == 200
    db.expire_all()
    assert db.scalar(select(AulaSessao.unidade_id)) == un2.id
    assert db.scalar(select(Aluno.unidade_id)) == un2.id
    # place desconhecido com duas configurações para o mesmo token: ambíguo
    r = enviar(client, tp, payload(CPF2, place="OUTRO", slot="z", evento="ez"))
    assert r.status_code == 400 and "unidade" in r.json()["error"]


def test_token_de_uma_unidade_nao_abre_a_outra(client, db, base, tp, full):
    un2 = Unidade(nome="Filial", capacidade=5)
    db.add(un2)
    db.commit()
    client.put(f"/api/integracoes/totalpass/{un2.id}", headers=full, json={"place_id": "PLACE-2"})
    tok2 = client.post(f"/api/integracoes/totalpass/{un2.id}/token-webhook", headers=full).json()["valor"]
    assert tok2 != tp.token
    # com o token da filial e o place da matriz, só a configuração da filial é candidata (e é a única): usa a filial
    assert client.post(URL, json=payload(place="PLACE-1"), headers={"X-Totalpass-Token": tok2}).status_code == 200
    db.expire_all()
    assert db.scalar(select(AulaSessao.unidade_id)) == un2.id


def test_token_regenerado_invalida_o_anterior(client, base, tp, full):
    novo = client.post(f"/api/integracoes/totalpass/{base.unidade.id}/token-webhook", headers=full).json()["valor"]
    assert enviar(client, tp, payload()).status_code == 403  # token antigo
    assert client.post(URL, json=payload(), headers={"X-Totalpass-Token": novo}).status_code == 200


def test_segredos_cifrados_no_banco(client, db, tp):
    db.expire_all()
    cfg = db.scalar(select(TotalpassConfig))
    for coluna, valor in (("partner_api_key_cifrado", "chave-parceiro-sintetica-1234"),
                          ("place_api_key_cifrado", "chave-unidade-sintetica-5678"), ("webhook_token_cifrado", tp.token)):
        guardado = getattr(cfg, coluna)
        assert guardado and valor not in guardado
        assert segredos.decifrar_texto(guardado.encode()) == valor


def test_auditoria_do_processamento_sem_dados_sensiveis(client, db, tp):
    enviar(client, tp, payload())
    enviar(client, tp, payload(status="canceled"))
    db.expire_all()
    acoes = [a.acao for a in db.scalars(select(Auditoria).where(Auditoria.acao.like("totalpass.%")).order_by(Auditoria.id))]
    assert "totalpass.aluno_criar" in acoes and "totalpass.reserva_criar" in acoes and "totalpass.reserva_cancelar" in acoes
    tudo = " ".join(f"{a.descricao} {a.antes_json} {a.depois_json}" for a in db.scalars(select(Auditoria)))
    assert tp.token not in tudo and "chave-parceiro" not in tudo and "chave-unidade" not in tudo
    assert CPF1 not in tudo


def test_resposta_do_webhook_nao_vaza_dados(client, tp):
    r = enviar(client, tp, payload())
    assert set(r.json()) == {"ok", "reserva_id", "resultado"}
    r = enviar(client, tp, payload(CPF2, titulo="Nada Casa Com Isso", slot="q", evento="q"))
    assert tp.token not in r.text and CPF2 not in r.text
