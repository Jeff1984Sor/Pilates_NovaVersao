"""Tela Configurações > Integrações > WhatsApp (API): somente escrita, auditoria sem segredo, permissões, chave geral."""
import logging

import httpx
from sqlalchemy import select

from app.core.models import Auditoria
from app.domain import whatsapp_avisos as dom
from app.modules.comunicacao import provedores as prov
from app.modules.comunicacao import servico as svc
from app.modules.integracoes.models import WhatsappConfig
from tests.comunicacao.conftest import TOKEN

NOVO_TOKEN = "NOVO-TOKEN-ZZZ9876"


def corpo(**extra):
    base = {"provedor": "wasender", "url_api": "https://www.wasenderapi.com", "instancia": None, "credencial": NOVO_TOKEN,
            "acompanhar_envios": True, "numero_acompanhamento": "11999990000", "pausa_segundos": 5,
            "pix_tipo": "CNPJ", "pix_chave": "00.000.000/0001-00"}
    base.update(extra)
    return base


def put(client, h, uid, **extra):
    return client.put(f"/api/whatsapp/configuracao/unidades/{uid}", json=corpo(**extra), headers=h)


def test_config_somente_escrita_nunca_devolve_a_credencial(client, full, cenario):
    r = put(client, full, cenario.un.id)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["credencial_definida"] is True and j["credencial_final"] == NOVO_TOKEN[-4:]
    assert NOVO_TOKEN not in r.text and TOKEN not in r.text
    g = client.get(f"/api/whatsapp/configuracao/unidades/{cenario.un.id}", headers=full)
    assert NOVO_TOKEN not in g.text and TOKEN not in g.text and "credencial_cifrado" not in g.text
    lista = client.get("/api/whatsapp/configuracao/unidades", headers=full)
    assert NOVO_TOKEN not in lista.text


def test_credencial_fica_cifrada_no_banco(client, full, cenario, db):
    put(client, full, cenario.un.id)
    db.expire_all()
    cfg = db.scalar(select(WhatsappConfig).where(WhatsappConfig.unidade_id == cenario.un.id))
    assert cfg.credencial_cifrado and NOVO_TOKEN not in cfg.credencial_cifrado
    assert svc.dados_do_provedor(cfg).credencial == NOVO_TOKEN


def test_salvar_sem_credencial_mantem_a_atual_e_limpar_remove(client, full, cenario, db):
    put(client, full, cenario.un.id, credencial=None)
    db.expire_all()
    cfg = db.scalar(select(WhatsappConfig).where(WhatsappConfig.unidade_id == cenario.un.id))
    assert svc.dados_do_provedor(cfg).credencial == TOKEN
    r = put(client, full, cenario.un.id, credencial=None, limpar_credencial=True)
    assert r.json()["credencial_definida"] is False


def test_auditoria_e_log_nao_contem_segredo(client, full, cenario, db, caplog, falso):
    caplog.set_level(logging.DEBUG)
    put(client, full, cenario.un.id)
    client.post(f"/api/whatsapp/configuracao/unidades/{cenario.un.id}/testar", headers=full)
    db.expire_all()
    for a in db.scalars(select(Auditoria)):
        texto = f"{a.descricao} {a.antes_json} {a.depois_json}"
        assert NOVO_TOKEN not in texto and TOKEN not in texto
    acoes = [a.acao for a in db.scalars(select(Auditoria))]
    assert "whatsapp.config.alterar" in acoes
    assert NOVO_TOKEN not in caplog.text and TOKEN not in caplog.text
    alterou = [a for a in db.scalars(select(Auditoria)) if a.acao == "whatsapp.config.alterar"][0]
    assert alterou.descricao == "Credencial alterada"
    assert "credencial_cifrado" not in str(alterou.depois_json) and "credencial_cifrado" not in str(alterou.antes_json)


def test_avisos_e_envio_automatico_nascem_desligados(client, full, cenario, db):
    j = client.get(f"/api/whatsapp/configuracao/unidades/{cenario.un.id}", headers=full).json()
    assert all(not a["ativo"] for a in j["avisos"]) and j["envio_automatico_ativo"] is False
    assert client.get("/api/whatsapp/configuracao/geral", headers=full).json() == {"envio_automatico_ativo": False}
    # unidade ainda sem configuração: também tudo desligado
    from tests.agenda import fabrica

    filial = fabrica.unidade(db, nome="Filial")
    db.commit()
    j2 = client.get(f"/api/whatsapp/configuracao/unidades/{filial.id}", headers=full).json()
    assert j2["existe"] is False and all(not a["ativo"] for a in j2["avisos"])


def test_chave_geral_so_full_liga_e_audita(client, full, secretaria, cenario, db):
    assert client.put("/api/whatsapp/configuracao/geral", json={"envio_automatico_ativo": True}, headers=secretaria).status_code == 403
    r = client.put("/api/whatsapp/configuracao/geral", json={"envio_automatico_ativo": True}, headers=full)
    assert r.status_code == 200 and r.json()["envio_automatico_ativo"] is True
    assert client.get("/api/whatsapp/status", headers=full).json()["envio_automatico_ativo"] is True
    assert any(a.acao == "whatsapp.envio_automatico" for a in db.scalars(select(Auditoria)))


def test_salvar_avisos_horarios_e_textos(client, full, cenario):
    r = put(client, full, cenario.un.id, avisos={"aniversario": {"ativo": True, "horario": "08:30:00"}},
            textos={"template_aniversario": "Parabéns {aluno}!"})
    j = r.json()
    aniv = next(a for a in j["avisos"] if a["tipo"] == "aniversario")
    assert aniv["ativo"] is True and aniv["horario"] == "08:30:00"
    assert j["textos"]["template_aniversario"] == "Parabéns {aluno}!"
    assert j["pix_chave"] == "00.000.000/0001-00"


def test_texto_nulo_volta_ao_padrao_do_dominio(client, full, cenario):
    j = put(client, full, cenario.un.id, textos={"template_aniversario": None}).json()
    assert j["textos"]["template_aniversario"] == dom.TEXTOS_PADRAO["template_aniversario"]


def test_textos_padrao_e_variaveis_batem_com_o_dominio(client, full):
    j = client.get("/api/whatsapp/configuracao/textos-padrao", headers=full).json()
    assert {c["campo"] for c in j["campos"]} == set(dom.TEXTOS_PADRAO)
    for c in j["campos"]:
        assert c["padrao"] == dom.TEXTOS_PADRAO[c["campo"]]
    assert j["variaveis_estudio"] == ["ESTUDIO_NOME", "PIX_TIPO", "PIX_CHAVE"]
    # nada de CNPJ/chave Pix/nome do estúdio fixo nos textos
    todos = " ".join(dom.TEXTOS_PADRAO.values())
    assert "50.732.875" not in todos and "Mayris" not in todos
    # as variáveis que cada texto cita são as documentadas (ou do estúdio)
    import re

    for c in j["campos"]:
        usadas = set(re.findall(r"\{(\w+)\}", c["padrao"]))
        assert usadas <= set(c["variaveis"]) | {"ESTUDIO_NOME", "PIX_TIPO", "PIX_CHAVE"}, c["campo"]


def test_validacoes_da_configuracao(client, full, cenario):
    assert put(client, full, cenario.un.id, url_api="ftp://x").status_code == 422
    assert put(client, full, cenario.un.id, avisos={"inventado": {"ativo": True, "horario": "10:00:00"}}).status_code == 422
    assert put(client, full, cenario.un.id, textos={"outro": "x"}).status_code == 422
    assert put(client, full, cenario.un.id, pausa_segundos=-1).status_code == 422
    assert put(client, full, 9999).status_code == 404


def test_testar_conexao_usa_o_provedor_e_nao_devolve_segredo(client, full, cenario, falso):
    falso.estado = prov.StatusSessao(False, "Sessão do WhatsApp não está conectada (situação: disconnected).")
    r = client.post(f"/api/whatsapp/configuracao/unidades/{cenario.un.id}/testar", headers=full)
    assert r.status_code == 200 and r.json()["conectada"] is False and "disconnected" in r.json()["detalhe"]
    falso.estado = prov.StatusSessao(True, "Sessão conectada.")
    assert client.post(f"/api/whatsapp/configuracao/unidades/{cenario.un.id}/testar", headers=full).json()["conectada"] is True


def test_testar_conexao_http_falso_ponta_a_ponta(client, full, cenario):
    """Sem o provedor falso: o Wasender real, mas com transporte HTTP falso (nada vai à internet)."""
    vistos = []

    def tratar(req):
        vistos.append(req)
        return httpx.Response(200, json={"status": "connected"})

    svc.definir_fabrica_provedor(lambda d: prov.criar_provedor(d.provedor, d.url, d.credencial, d.instancia, httpx.MockTransport(tratar)))
    try:
        r = client.post(f"/api/whatsapp/configuracao/unidades/{cenario.un.id}/testar", headers=full)
    finally:
        svc.definir_fabrica_provedor(None)
    assert r.json()["conectada"] is True and vistos[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in r.text


def test_testar_sem_credencial_pede_cadastro(client, full, cenario):
    put(client, full, cenario.un.id, credencial=None, limpar_credencial=True)
    assert client.post(f"/api/whatsapp/configuracao/unidades/{cenario.un.id}/testar", headers=full).status_code == 409


def test_configuracao_so_full(client, full, secretaria, professor, cenario):
    url = f"/api/whatsapp/configuracao/unidades/{cenario.un.id}"
    for h in (secretaria, professor):
        assert client.get(url, headers=h).status_code == 403
        assert client.put(url, json=corpo(), headers=h).status_code == 403
        assert client.post(url + "/testar", headers=h).status_code == 403
        assert client.get("/api/whatsapp/configuracao/geral", headers=h).status_code == 403
        assert client.get("/api/whatsapp/configuracao/textos-padrao", headers=h).status_code == 403
    assert client.get(url).status_code == 401


def test_acompanhamento_lista_o_log_do_scheduler(client, full, cenario):
    r = client.get("/api/whatsapp/automaticos", headers=full)
    assert r.status_code == 200 and r.json()["itens"] == [] and r.json()["envio_automatico_ativo"] is False
