"""Tela do TotalPass (credenciais somente escrita, testar conexão, sincronização, eventos) e permissões.

O cliente HTTP do TotalPass é um `httpx.MockTransport`: nenhuma chamada sai para a internet.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.integracoes import tarefas, totalpass
from app.modules.integracoes.models import TotalpassConfig, TotalpassEvento
from tests.integracoes.conftest import cpf_valido
from tests.integracoes.test_totalpass_webhook import hoje, total

CPF1, CPF2, CPF3 = cpf_valido(400000001), cpf_valido(400000002), cpf_valido(400000003)
CHAVE_PARCEIRO, CHAVE_UNIDADE = "chave-parceiro-sintetica-1234", "chave-unidade-sintetica-5678"
BASE = "https://totalpass.invalid"


class Servidor:
    """TotalPass falso: registra as chamadas e responde conforme o cenário."""

    def __init__(self, slots=None, auth_status=200, slot_status=200):
        self.slots, self.auth_status, self.slot_status, self.chamadas = slots or [], auth_status, slot_status, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.chamadas.append(request)
        if request.url.path == "/partner/auth":
            corpo = json.loads(request.content)
            ok = corpo == {"partner_api_key": CHAVE_PARCEIRO, "place_api_key": CHAVE_UNIDADE}
            if self.auth_status != 200 or not ok:
                return httpx.Response(401 if self.auth_status == 200 else self.auth_status, json={"message": "no"})
            return httpx.Response(200, json={"token": "jwt-sintetico"})
        if request.url.path == "/partner/slot":
            if request.headers.get("authorization") != "Bearer jwt-sintetico":
                return httpx.Response(401, json={})
            return httpx.Response(self.slot_status, json={"items": self.slots})
        return httpx.Response(404)


def instalar(servidor: Servidor):
    totalpass.definir_fabrica_cliente(
        lambda: totalpass.ClienteTotalpass(BASE, transport=httpx.MockTransport(servidor)))
    return servidor


def slot(cpf=CPF1, *, dia=None, hora="09:00", status="active", sid="S1", eid="E1", titulo="Pilates"):
    return {"event_id": eid, "event_title": titulo, "place_id": "PLACE-1", "user_name": "Aluna Sincronizada",
            "user_email": "sync@exemplo.invalid", "phone": "11977776666", "document_number": cpf,
            "slot_id": sid, "status": status, "date": (dia or hoje()).isoformat(), "start_time": hora}


@pytest.fixture
def cfg_url(base):
    return f"/api/integracoes/totalpass/{base.unidade.id}"


@pytest.fixture
def configurado(client, base, full, cfg_url):
    r = client.put(cfg_url, headers=full, json={"place_id": "PLACE-1", "partner_api_key": CHAVE_PARCEIRO,
                                                "place_api_key": CHAVE_UNIDADE})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------------------------------------ configuração
def test_tela_lista_unidades_sem_criar_nada(client, db, base, full):
    r = client.get("/api/integracoes/totalpass", headers=full)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["webhook_caminho"] == "/api/webhooks/totalpass"
    assert [c["unidade_nome"] for c in corpo["configuracoes"]] == ["Matriz"]
    c = corpo["configuracoes"][0]
    assert c["configurada"] is False and c["ativo"] is True and c["somente_dia"] is True and c["criar_aluno_automatico"] is True
    assert c["sync_ativo"] is False and c["partner_api_key"] == {"definido": False, "final": None}
    assert [s["nome"] for s in corpo["servicos"]] == ["Pilates"]
    assert total(db, TotalpassConfig) == 0  # GET não tem efeito colateral


def test_segredos_somente_escrita(client, db, full, cfg_url, configurado):
    assert configurado["partner_api_key"] == {"definido": True, "final": "1234"}
    assert configurado["place_api_key"] == {"definido": True, "final": "5678"}
    assert configurado["webhook_token"] == {"definido": False, "final": None}
    leitura = client.get("/api/integracoes/totalpass", headers=full)
    assert CHAVE_PARCEIRO not in leitura.text and CHAVE_UNIDADE not in leitura.text
    assert CHAVE_PARCEIRO not in json.dumps(configurado)
    # salvar de novo sem informar as chaves MANTÉM as chaves
    r = client.put(cfg_url, headers=full, json={"place_id": "PLACE-9"})
    assert r.json()["partner_api_key"]["definido"] is True and r.json()["place_id"] == "PLACE-9"
    # string vazia também mantém; limpar é explícito
    r = client.put(cfg_url, headers=full, json={"partner_api_key": "  ", "limpar": ["place_api_key"]})
    assert r.json()["partner_api_key"]["definido"] is True and r.json()["place_api_key"] == {"definido": False, "final": None}


def test_nenhum_campo_de_resposta_devolve_chave(client, full, cfg_url, configurado):
    for resp in (client.get("/api/integracoes/totalpass", headers=full),
                 client.put(cfg_url, headers=full, json={"partner_api_key": "outra-chave-sintetica-9999"}),
                 client.get("/api/integracoes/totalpass/eventos", headers=full)):
        assert "outra-chave" not in resp.text and CHAVE_PARCEIRO not in resp.text and "_cifrado" not in resp.text


def test_token_do_webhook_gerado_aparece_uma_vez(client, full, cfg_url, configurado):
    r = client.post(cfg_url + "/token-webhook", headers=full)
    assert r.status_code == 200 and r.json()["valor"].startswith("tpw_") and r.json()["final"] == r.json()["valor"][-4:]
    tela = client.get("/api/integracoes/totalpass", headers=full)
    assert r.json()["valor"] not in tela.text
    assert tela.json()["configuracoes"][0]["webhook_token"] == {"definido": True, "final": r.json()["final"]}


def test_token_do_webhook_digitado_exige_tamanho(client, full, cfg_url):
    assert client.put(cfg_url, headers=full, json={"webhook_token": "curto"}).status_code == 422
    r = client.put(cfg_url, headers=full, json={"webhook_token": "token-digitado-pelo-usuario-1"})
    assert r.status_code == 200 and r.json()["webhook_token"] == {"definido": True, "final": "io-1"}


def test_auditoria_registra_a_troca_sem_o_valor(client, db, full, cfg_url, configurado):
    client.put(cfg_url, headers=full, json={"partner_api_key": "chave-nova-sintetica-0000", "somente_dia": False})
    tok = client.post(cfg_url + "/token-webhook", headers=full).json()["valor"]
    db.expire_all()
    linhas = list(db.scalars(select(Auditoria).where(Auditoria.entidade == "totalpass_config").order_by(Auditoria.id)))
    assert [a.acao for a in linhas] == ["totalpass.configurar", "totalpass.configurar", "totalpass.gerar_token_webhook"]
    tudo = " ".join(f"{a.descricao} {a.antes_json} {a.depois_json}" for a in linhas)
    for segredo in (CHAVE_PARCEIRO, CHAVE_UNIDADE, "chave-nova-sintetica-0000", tok):
        assert segredo not in tudo
    assert "partner_api_key: alterado" in tudo and "somente_dia" in tudo


def test_validacoes_da_configuracao(client, full, base, cfg_url):
    assert client.put("/api/integracoes/totalpass/999", headers=full, json={}).status_code == 404
    assert client.put(cfg_url, headers=full, json={"servico_padrao_id": 999}).status_code == 422
    assert client.put(cfg_url, headers=full, json={"campo_inventado": 1}).status_code == 422
    r = client.put(cfg_url, headers=full, json={"sync_ativo": True})
    assert r.status_code == 422 and "chave" in r.json()["detail"]


def test_sincronizacao_vem_desligada_por_padrao(client, full, configurado):
    assert configurado["sync_ativo"] is False


# ------------------------------------------------------------------------------------------------ testar conexão
def test_testar_conexao_ok(client, full, cfg_url, configurado):
    srv = instalar(Servidor())
    r = client.post(cfg_url + "/testar", headers=full)
    assert r.status_code == 200 and "OK" in r.json()["mensagem"]
    assert [c.url.path for c in srv.chamadas] == ["/partner/auth"]
    assert str(srv.chamadas[0].url).startswith(BASE)


def test_testar_conexao_chave_recusada_nao_vaza_a_chave(client, db, full, cfg_url, configurado, caplog):
    instalar(Servidor(auth_status=401))
    with caplog.at_level(logging.DEBUG):
        r = client.post(cfg_url + "/testar", headers=full)
    assert r.status_code == 502 and "recusou" in r.json()["detail"]
    assert CHAVE_PARCEIRO not in r.text and CHAVE_UNIDADE not in r.text
    assert CHAVE_PARCEIRO not in caplog.text and CHAVE_UNIDADE not in caplog.text


def test_testar_conexao_falhas(client, full, cfg_url, base):
    assert client.post(cfg_url + "/testar", headers=full).status_code == 409  # sem configuração salva
    client.put(cfg_url, headers=full, json={"place_id": "P"})
    r = client.post(cfg_url + "/testar", headers=full)
    assert r.status_code == 502 and "Cadastre a chave" in r.json()["detail"]
    client.put(cfg_url, headers=full, json={"partner_api_key": CHAVE_PARCEIRO, "place_api_key": CHAVE_UNIDADE})

    def cai(_):
        raise httpx.ConnectError("sem rede")

    totalpass.definir_fabrica_cliente(lambda: totalpass.ClienteTotalpass(BASE, transport=httpx.MockTransport(cai)))
    r = client.post(cfg_url + "/testar", headers=full)
    assert r.status_code == 502 and "Não foi possível falar" in r.json()["detail"]
    instalar(Servidor(auth_status=500))
    assert "erro 500" in client.post(cfg_url + "/testar", headers=full).json()["detail"]


def test_o_cliente_real_nunca_e_criado_nos_testes(client, full, cfg_url, configurado):
    """O autouse `_sem_internet` troca a fábrica por uma que explode: se algum caminho tentar o cliente real, falha."""
    with pytest.raises(AssertionError, match="internet proibida"):
        client.post(cfg_url + "/testar", headers=full)


# ------------------------------------------------------------------------------------------------ sincronização
def test_sincronizar_processa_slots_do_dia(client, db, full, cfg_url, configurado):
    srv = instalar(Servidor([slot(CPF1, sid="S1", eid="E1"), slot(CPF2, sid="S2", eid="E2", hora="10:00")]))
    r = client.post(cfg_url + "/sincronizar", headers=full, json={})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert (corpo["recebidos"], corpo["processados"], corpo["erros"]) == (2, 2, 0) and corpo["dia"] == hoje().isoformat()
    chamada = srv.chamadas[1]
    assert chamada.url.path == "/partner/slot"
    assert chamada.url.params["slotDateFrom"] == chamada.url.params["slotDateTo"] == hoje().isoformat()
    assert chamada.url.params["placeId"] == "PLACE-1"
    db.expire_all()
    assert total(db, Reserva) == 2 and {e.origem for e in db.scalars(select(TotalpassEvento))} == {"sync"}
    cfg = db.scalar(select(TotalpassConfig))
    assert cfg.sync_ultimo_em is not None and "2 processados" in cfg.sync_ultimo_resumo


def test_sincronizar_e_idempotente_e_convive_com_o_webhook(client, db, full, cfg_url, configurado):
    instalar(Servidor([slot(CPF1)]))
    assert client.post(cfg_url + "/sincronizar", headers=full, json={}).json()["processados"] == 1
    r2 = client.post(cfg_url + "/sincronizar", headers=full, json={}).json()
    assert (r2["processados"], r2["duplicados"]) == (0, 1)
    db.expire_all()
    assert total(db, Reserva) == 1 and total(db, TotalpassEvento) == 1


def test_sincronizar_cancelamento_erro_e_descarte(client, db, base, full, cfg_url, configurado):
    outro_dia = hoje() + timedelta(days=3)
    instalar(Servidor([slot(CPF1, sid="A"), slot(CPF1, sid="A", status="canceled"), slot(CPF2, sid="B", titulo="Sem Serviço"),
                       slot("123", sid="C", hora="11:00"), slot(CPF3, sid="D", dia=outro_dia, hora="12:00")]))
    corpo = client.post(cfg_url + "/sincronizar", headers=full, json={}).json()
    assert (corpo["recebidos"], corpo["processados"], corpo["cancelados"], corpo["erros"], corpo["descartados"]) == (5, 2, 1, 2, 0)
    db.expire_all()
    assert db.scalar(select(Reserva.status)) == StatusReserva.CANCELADA
    # `somente_dia` não vale no sync (o dia pedido é explícito): o slot de outro dia é processado
    assert db.scalar(select(AulaSessao).where(AulaSessao.data == outro_dia)) is not None


def test_sincronizar_dia_especifico(client, db, full, cfg_url, configurado):
    dia = hoje() - timedelta(days=2)
    srv = instalar(Servidor([slot(CPF1, dia=dia)]))
    r = client.post(cfg_url + "/sincronizar", headers=full, json={"dia": dia.isoformat()})
    assert r.status_code == 200 and r.json()["dia"] == dia.isoformat()
    assert srv.chamadas[1].url.params["slotDateFrom"] == dia.isoformat()


def test_sincronizar_falhas(client, full, cfg_url, base):
    assert client.post(cfg_url + "/sincronizar", headers=full, json={}).status_code == 409
    client.put(cfg_url, headers=full, json={"partner_api_key": CHAVE_PARCEIRO, "place_api_key": CHAVE_UNIDADE})
    instalar(Servidor(auth_status=403))
    r = client.post(cfg_url + "/sincronizar", headers=full, json={})
    assert r.status_code == 502 and CHAVE_PARCEIRO not in r.text
    instalar(Servidor(slot_status=500))
    assert client.post(cfg_url + "/sincronizar", headers=full, json={}).status_code == 502


def test_get_nunca_sincroniza(client, full, cfg_url, configurado):
    srv = instalar(Servidor([slot()]))
    for url in ("/api/integracoes/totalpass", "/api/integracoes/totalpass/eventos", "/api/integracoes/tokens"):
        assert client.get(url, headers=full).status_code == 200
    assert client.get(cfg_url + "/sincronizar", headers=full).status_code in (404, 405)
    assert srv.chamadas == []


# ------------------------------------------------------------------------------------------------ tarefa agendada
def test_tarefa_agendada_ignora_quem_nao_ligou(db, client, full, cfg_url, configurado):
    srv = instalar(Servidor([slot()]))
    assert tarefas.sincronizar_agendado() == 0 and srv.chamadas == []
    db.expire_all()
    assert total(db, Reserva) == 0


def test_tarefa_agendada_sincroniza_quem_ligou(db, client, full, cfg_url, configurado):
    assert client.put(cfg_url, headers=full, json={"sync_ativo": True}).status_code == 200
    instalar(Servidor([slot(CPF1)]))
    assert tarefas.sincronizar_agendado() == 1
    db.expire_all()
    assert total(db, Reserva) == 1
    assert "1 processados" in db.scalar(select(TotalpassConfig.sync_ultimo_resumo))


def test_tarefa_agendada_registra_o_erro_sem_derrubar(db, client, full, cfg_url, configurado):
    client.put(cfg_url, headers=full, json={"sync_ativo": True})
    instalar(Servidor(auth_status=401))
    assert tarefas.sincronizar_agendado() == 1
    db.expire_all()
    resumo = db.scalar(select(TotalpassConfig.sync_ultimo_resumo))
    assert resumo.startswith("Erro:") and CHAVE_PARCEIRO not in resumo


def test_tarefa_registrada_no_worker():
    from app.worker import TAREFAS

    importar = __import__("app.modules.integracoes.tarefas", fromlist=["x"])
    assert importar is tarefas
    assert any(t.nome == "totalpass-sincronizar" and t.intervalo_s >= 300 for t in TAREFAS)


# ------------------------------------------------------------------------------------------------ eventos (tela)
def test_lista_de_eventos_com_status_erro_e_filtros(client, db, base, full, cfg_url, configurado):
    from tests.integracoes.test_totalpass_webhook import enviar, payload

    tok = client.post(cfg_url + "/token-webhook", headers=full).json()["valor"]
    tp = type("T", (), {"h": {"X-Totalpass-Token": tok}})
    enviar(client, tp, payload(CPF1))
    enviar(client, tp, payload("123", slot="x", evento="x"))
    enviar(client, tp, payload(CPF2, dia=hoje() + timedelta(days=1), slot="y", evento="y"))
    enviar(client, tp, payload(CPF1, status="canceled"))
    r = client.get("/api/integracoes/totalpass/eventos", headers=full)
    assert r.status_code == 200 and r.json()["total"] == 4
    por = {e["resultado"]: e for e in r.json()["itens"]}
    assert set(por) == {"processado", "erro", "descartado", "cancelado"}
    assert por["erro"]["erro"] and por["descartado"]["erro"] == "Fora do dia atual." and por["processado"]["reserva_id"]
    assert por["processado"]["titulo"] == "Pilates" and por["processado"]["aula_em"].endswith("09:00")
    assert por["processado"]["documento_mascarado"].endswith(CPF1[-2:]) and CPF1 not in r.text  # CPF mascarado
    assert [e["id"] for e in r.json()["itens"]] == sorted((e["id"] for e in r.json()["itens"]), reverse=True)
    assert client.get("/api/integracoes/totalpass/eventos?resultado=erro", headers=full).json()["total"] == 1
    assert client.get("/api/integracoes/totalpass/eventos?resultado=descartado", headers=full).json()["total"] == 1
    pag = client.get("/api/integracoes/totalpass/eventos?por_pagina=2&pagina=2", headers=full).json()
    assert pag["total"] == 4 and len(pag["itens"]) == 2
    assert client.get("/api/integracoes/totalpass/eventos?resultado=xyz", headers=full).status_code == 422


def test_eventos_importados_do_antigo_sem_resultado(client, db, full):
    from app.core.db import agora

    db.add_all([
        TotalpassEvento(event_id="a", payload={}, recebido_em=agora(), processado_em=agora()),
        TotalpassEvento(event_id="b", payload={"x": 1}, recebido_em=agora(), erro="Capacidade excedida"),
        TotalpassEvento(event_id="c", payload=None, recebido_em=agora()),
    ])
    db.commit()
    r = client.get("/api/integracoes/totalpass/eventos", headers=full).json()
    assert {e["event_id"]: e["resultado"] for e in r["itens"]} == {"a": "processado", "b": "erro", "c": "pendente"}
    assert client.get("/api/integracoes/totalpass/eventos?resultado=erro", headers=full).json()["total"] == 1
    assert client.get("/api/integracoes/totalpass/eventos?resultado=processado", headers=full).json()["total"] == 1
    assert client.get("/api/integracoes/totalpass/eventos?resultado=pendente", headers=full).json()["total"] == 1


# ------------------------------------------------------------------------------------------------ permissões
@pytest.mark.parametrize("quem", ["secretaria", "professor"])
def test_so_o_perfil_full_ve_e_configura_o_totalpass(client, request, base, full, cfg_url, configurado, quem):
    cab = request.getfixturevalue(quem)
    for metodo, url, corpo in (
        ("get", "/api/integracoes/totalpass", None), ("get", "/api/integracoes/totalpass/eventos", None),
        ("put", cfg_url, {"ativo": False}), ("post", cfg_url + "/token-webhook", None),
        ("post", cfg_url + "/testar", None), ("post", cfg_url + "/sincronizar", {}),
    ):
        r = getattr(client, metodo)(url, headers=cab, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 403, (metodo, url, r.status_code)
    # nada mudou
    assert client.get("/api/integracoes/totalpass", headers=full).json()["configuracoes"][0]["ativo"] is True


def test_sem_login_nao_acessa(client, cfg_url):
    for url in ("/api/integracoes/totalpass", "/api/integracoes/totalpass/eventos", "/api/integracoes/tokens"):
        assert client.get(url).status_code == 401
    assert client.put(cfg_url, json={}).status_code == 401
