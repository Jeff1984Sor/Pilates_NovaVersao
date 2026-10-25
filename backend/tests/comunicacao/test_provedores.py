"""Provedores de WhatsApp com HTTP FALSO (httpx.MockTransport): nenhuma chamada sai para a internet."""
import json

import httpx
import pytest

from app.modules.comunicacao import provedores as prov

TOKEN = "TOKEN-SECRETO-ABCD1234"


def transporte(resposta, chamadas: list):
    def tratar(req: httpx.Request) -> httpx.Response:
        chamadas.append(req)
        r = resposta(req) if callable(resposta) else resposta
        if isinstance(r, Exception):
            raise r
        return r

    return httpx.MockTransport(tratar)


def wasender(resposta, chamadas):
    return prov.Wasender(url="https://www.wasenderapi.com/api/send-message", credencial=TOKEN, transporte=transporte(resposta, chamadas))


def evolution(resposta, chamadas):
    return prov.Evolution(url="https://evo.exemplo.com/", credencial=TOKEN, instancia="studio", transporte=transporte(resposta, chamadas))


def test_wasender_envia_texto_com_bearer_e_numero_normalizado():
    ch = []
    r = wasender(httpx.Response(200, json={"success": True, "data": {"msgId": 1}}), ch).enviar_texto("(11) 99999-0000", "Olá")
    assert r.ok
    req = ch[0]
    assert str(req.url) == "https://www.wasenderapi.com/api/send-message"
    assert req.headers["authorization"] == f"Bearer {TOKEN}"
    assert json.loads(req.content) == {"to": "+5511999990000", "text": "Olá"}


def test_wasender_documento_por_url_no_mesmo_endpoint():
    ch = []
    r = wasender(httpx.Response(200, json={"success": True}), ch).enviar_documento("11999990000", "https://x.exemplo.com/c.pdf", "contrato.pdf", "Segue")
    assert r.ok
    corpo = json.loads(ch[0].content)
    assert corpo["documentUrl"] == "https://x.exemplo.com/c.pdf" and corpo["fileName"] == "contrato.pdf" and corpo["text"] == "Segue"


def test_documento_rejeita_url_que_nao_e_http():
    ch = []
    r = wasender(httpx.Response(200, json={}), ch).enviar_documento("11999990000", "file:///etc/passwd", "x.pdf")
    assert not r.ok and r.definitivo and not ch


def test_evolution_envia_texto_com_apikey():
    ch = []
    r = evolution(httpx.Response(201, json={"key": {"id": "abc"}}), ch).enviar_texto("5511999990000", "Oi")
    assert r.ok
    assert str(ch[0].url) == "https://evo.exemplo.com/message/sendText/studio"
    assert ch[0].headers["apikey"] == TOKEN and "authorization" not in ch[0].headers
    assert json.loads(ch[0].content) == {"number": "5511999990000", "text": "Oi"}


def test_evolution_documento_usa_sendmedia():
    ch = []
    evolution(httpx.Response(201, json={}), ch).enviar_documento("11999990000", "https://x.exemplo.com/t.pdf", "termo.pdf")
    assert str(ch[0].url).endswith("/message/sendMedia/studio")
    assert json.loads(ch[0].content)["mediatype"] == "document"


def test_telefone_invalido_nao_chama_a_rede():
    ch = []
    r = wasender(httpx.Response(200, json={}), ch).enviar_texto("123", "x")
    assert not r.ok and r.definitivo and not ch


def test_401_e_erro_de_autenticacao_e_nao_repete(sem_espera):
    ch = []
    p = wasender(httpx.Response(401, json={"message": "Unauthorized"}), ch)
    r = prov.enviar_com_retry(lambda: p.enviar_texto("11999990000", "x"), dormir=sem_espera.append)
    assert not r.ok and r.erro_autenticacao and len(ch) == 1 and sem_espera == []


def test_sessao_desconectada_wasender_http_200_success_false():
    ch = []
    resp = httpx.Response(200, json={"success": False, "message": "Session is not connected"})
    r = wasender(resp, ch).enviar_texto("11999990000", "x")
    assert not r.ok and r.sessao_caiu


def test_sessao_desconectada_evolution_400():
    ch = []
    resp = httpx.Response(400, json={"message": "Connection Closed"})
    assert evolution(resp, ch).enviar_texto("11999990000", "x").sessao_caiu


def test_sessao_caida_nao_e_repetida():
    ch = []
    p = wasender(httpx.Response(200, json={"success": False, "message": "not connected"}), ch)
    r = prov.enviar_com_retry(lambda: p.enviar_texto("11999990000", "x"), dormir=lambda s: None)
    assert r.sessao_caiu and len(ch) == 1


def test_timeout_tenta_tres_vezes_com_pausa(sem_espera):
    ch = []
    p = wasender(httpx.ReadTimeout("lento"), ch)
    r = prov.enviar_com_retry(lambda: p.enviar_texto("11999990000", "x"), dormir=sem_espera.append)
    assert not r.ok and r.tentativas == 3 and len(ch) == 3 and len(sem_espera) == 2
    assert "Tempo esgotado" in (r.erro or "")


def test_retry_para_no_primeiro_sucesso(sem_espera):
    respostas = iter([httpx.Response(500, json={"message": "boom"}), httpx.Response(200, json={"success": True})])
    ch = []
    p = wasender(lambda req: next(respostas), ch)
    r = prov.enviar_com_retry(lambda: p.enviar_texto("11999990000", "x"), dormir=sem_espera.append)
    assert r.ok and r.tentativas == 2 and len(ch) == 2


def test_retry_after_maior_que_a_pausa_e_respeitado(sem_espera):
    respostas = iter([httpx.Response(429, json={"message": "slow"}, headers={"Retry-After": "9"}), httpx.Response(200, json={"success": True})])
    p = wasender(lambda req: next(respostas), [])
    prov.enviar_com_retry(lambda: p.enviar_texto("11999990000", "x"), dormir=sem_espera.append)
    assert sem_espera == [9.0]


def test_token_ecoado_pelo_provedor_nao_vaza_no_erro_nem_no_resumo():
    ch = []
    resp = httpx.Response(400, json={"message": f"token {TOKEN} inválido para a sessão", "echo": TOKEN})
    r = wasender(resp, ch).enviar_texto("11999990000", "x")
    assert TOKEN not in (r.erro or "") and TOKEN not in r.resumo


def test_excecao_de_rede_nao_traz_url_nem_token():
    ch = []
    r = wasender(httpx.ConnectError(f"falha em https://x/?k={TOKEN}"), ch).enviar_texto("11999990000", "x")
    assert not r.ok and TOKEN not in (r.erro or "") and "https" not in (r.erro or "")


def test_configuracao_incompleta():
    assert prov.Wasender(url=None, credencial=None).enviar_texto("11999990000", "x").definitivo
    assert prov.Evolution(url="https://e.com", credencial="k", instancia=None).enviar_texto("11999990000", "x").definitivo


def test_status_wasender_conectado_desconectado_e_401():
    ch = []
    assert wasender(httpx.Response(200, json={"status": "connected"}), ch).status_sessao().conectada is True
    assert str(ch[0].url) == "https://www.wasenderapi.com/api/status"
    st = wasender(httpx.Response(200, json={"status": "disconnected"}), []).status_sessao()
    assert st.conectada is False and "Reconecte" in st.detalhe
    assert wasender(httpx.Response(401, json={}), []).status_sessao().erro_autenticacao


def test_status_evolution():
    ch = []
    assert evolution(httpx.Response(200, json={"instance": {"state": "open"}}), ch).status_sessao().conectada is True
    assert str(ch[0].url).endswith("/instance/connectionState/studio")
    assert evolution(httpx.Response(200, json={"instance": {"state": "close"}}), []).status_sessao().conectada is False


def test_status_sem_resposta():
    st = wasender(httpx.ConnectTimeout("x"), []).status_sessao()
    assert st.conectada is None and st.sem_resposta


@pytest.mark.parametrize("url", ["https://www.wasenderapi.com", "https://www.wasenderapi.com/", "https://www.wasenderapi.com/api/send-message"])
def test_wasender_aceita_a_url_base_ou_o_endpoint_completo(url):
    ch = []
    prov.Wasender(url=url, credencial=TOKEN, transporte=transporte(httpx.Response(200, json={"success": True}), ch)).enviar_texto("11999990000", "x")
    assert str(ch[0].url) == "https://www.wasenderapi.com/api/send-message"
