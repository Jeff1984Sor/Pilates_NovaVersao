"""ClienteHttp com httpx.MockTransport: confere o que seria enviado ao provedor, sem rede e sem chave real."""

import base64
import json

import httpx
import pytest

from app.core.ia import IAIndisponivel, Provedor
from app.modules.ia_cadastro.cliente import ClienteHttp

OPENAI = Provedor("openai", "gpt-4o-mini", "sk-teste")
GEMINI = Provedor("gemini", "gemini-2.0-flash", "g-teste")


def cliente(handler) -> ClienteHttp:
    return ClienteHttp(httpx.Client(transport=httpx.MockTransport(handler)))


def resp_openai(conteudo: str):
    return httpx.Response(200, json={"choices": [{"message": {"content": conteudo}}]})


def test_openai_imagem_vai_como_image_url_com_bearer():
    vistos = []

    def h(req: httpx.Request):
        vistos.append(req)
        return resp_openai('{"nome": "Ana"}')

    out = cliente(h).extrair(OPENAI, "sistema", "usuario", "image/png", b"\x89PNG-bytes")
    assert out == {"nome": "Ana"}
    req = vistos[0]
    assert str(req.url) == "https://api.openai.com/v1/chat/completions" and req.headers["authorization"] == "Bearer sk-teste"
    corpo = json.loads(req.content)
    assert corpo["model"] == "gpt-4o-mini" and corpo["response_format"] == {"type": "json_object"}
    parte = corpo["messages"][1]["content"][1]
    assert parte["type"] == "image_url"
    assert parte["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(b"\x89PNG-bytes").decode()


def test_openai_pdf_vai_como_file():
    corpo = {}

    def h(req):
        corpo.update(json.loads(req.content))
        return resp_openai("```json\n{\"cep\": \"01310100\"}\n```")

    out = cliente(h).extrair(OPENAI, "s", "u", "application/pdf", b"%PDF-1.4")
    assert out == {"cep": "01310100"}
    parte = corpo["messages"][1]["content"][1]
    assert parte["type"] == "file" and parte["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_gemini_manda_a_chave_no_cabecalho_e_nao_na_url():
    vistos = []

    def h(req):
        vistos.append(req)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"nome": "Bia"}'}]}}]})

    assert cliente(h).extrair(GEMINI, "s", "u", "image/jpeg", b"\xff\xd8\xff") == {"nome": "Bia"}
    req = vistos[0]
    assert "g-teste" not in str(req.url) and req.headers["x-goog-api-key"] == "g-teste"
    assert json.loads(req.content)["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/jpeg"


@pytest.mark.parametrize(
    ("status", "trecho"),
    [(401, "foi recusada"), (403, "foi recusada"), (429, "Limite de uso"), (404, "não existe mais"), (500, "erro \(500\)")],
)
def test_erros_http_viram_mensagens_claras(status, trecho):
    with pytest.raises(IAIndisponivel, match=trecho):
        cliente(lambda req: httpx.Response(status, json={"error": "x"})).extrair(OPENAI, "s", "u", "image/png", b"x")


def test_timeout_e_falha_de_rede():
    def demora(req):
        raise httpx.ReadTimeout("lento")

    def cai(req):
        raise httpx.ConnectError("sem rede")

    with pytest.raises(IAIndisponivel, match="demorou demais"):
        cliente(demora).extrair(OPENAI, "s", "u", "image/png", b"x")
    with pytest.raises(IAIndisponivel, match="Não foi possível falar"):
        cliente(cai).extrair(OPENAI, "s", "u", "image/png", b"x")


def test_resposta_fora_do_formato():
    with pytest.raises(IAIndisponivel, match="fora do formato"):
        cliente(lambda r: resp_openai("isto não é json")).extrair(OPENAI, "s", "u", "image/png", b"x")
    with pytest.raises(IAIndisponivel, match="fora do formato"):
        cliente(lambda r: resp_openai("[1, 2]")).extrair(OPENAI, "s", "u", "image/png", b"x")
    with pytest.raises(IAIndisponivel, match="vazia"):
        cliente(lambda r: httpx.Response(200, json={"choices": []})).extrair(OPENAI, "s", "u", "image/png", b"x")
