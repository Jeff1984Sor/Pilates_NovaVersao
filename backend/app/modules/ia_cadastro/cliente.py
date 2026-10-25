"""Cliente de visão da IA (OpenAI ou Gemini) por HTTP, trocável nos testes.

``ClienteVisao`` é a interface: ``extrair(provedor, sistema, usuario, mime, conteudo) -> dict``. O padrão (``ClienteHttp``)
fala com o provedor escolhido em Configurações > Inteligência Artificial usando ``httpx``; quem testa injeta um cliente
falso (``definir_cliente``) ou um ``httpx.Client`` com ``MockTransport``. Nenhum teste chama a internet.

A chave só existe dentro de ``Provedor`` (decifrada na hora da chamada) e nunca é logada. Erros viram ``IAIndisponivel``
com texto pronto para o usuário (reaproveita as mensagens do core).
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Protocol

import httpx

from app.core.ia import PROVEDORES, IAIndisponivel, Provedor, _erro_http

log = logging.getLogger(__name__)

TIMEOUT = 90.0
URL_OPENAI = "https://api.openai.com/v1/chat/completions"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


class ClienteVisao(Protocol):
    def extrair(self, provedor: Provedor, sistema: str, usuario: str, mime: str, conteudo: bytes) -> dict:
        """Manda o arquivo (imagem ou PDF) à IA e devolve o JSON da resposta. Levanta ``IAIndisponivel``."""
        ...


class ClienteHttp:
    def __init__(self, http: httpx.Client | None = None):
        self._http = http

    def _post(self, url: str, headers: dict, corpo: dict) -> httpx.Response:
        if self._http is not None:
            return self._http.post(url, headers=headers, json=corpo, timeout=TIMEOUT)
        return httpx.post(url, headers=headers, json=corpo, timeout=TIMEOUT)

    def extrair(self, provedor: Provedor, sistema: str, usuario: str, mime: str, conteudo: bytes) -> dict:
        b64 = base64.b64encode(conteudo).decode("ascii")
        try:
            if provedor.nome == "openai":
                texto = self._openai(provedor, sistema, usuario, mime, b64)
            elif provedor.nome == "gemini":
                texto = self._gemini(provedor, sistema, usuario, mime, b64)
            else:
                raise IAIndisponivel("Provedor de IA desconhecido. Revise em Configurações › Inteligência Artificial.")
        except httpx.TimeoutException as e:
            raise IAIndisponivel("A IA demorou demais para responder. Tente novamente.") from e
        except httpx.HTTPError as e:
            raise IAIndisponivel(f"Não foi possível falar com a {PROVEDORES.get(provedor.nome, provedor.nome)}.") from e
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise IAIndisponivel("A IA devolveu uma resposta vazia. Tente novamente.") from e
        return _json(texto)

    def _openai(self, p: Provedor, sistema: str, usuario: str, mime: str, b64: str) -> str:
        if mime == "application/pdf":
            anexo = {"type": "file", "file": {"filename": "documento.pdf", "file_data": f"data:{mime};base64,{b64}"}}
        else:
            anexo = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}}
        r = self._post(
            URL_OPENAI,
            {"Authorization": f"Bearer {p.chave}"},
            {
                "model": p.modelo,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": [{"type": "text", "text": usuario}, anexo]},
                ],
            },
        )
        if r.status_code != 200:
            raise _erro_http("openai", r)
        return r.json()["choices"][0]["message"]["content"]

    def _gemini(self, p: Provedor, sistema: str, usuario: str, mime: str, b64: str) -> str:
        r = self._post(
            URL_GEMINI.format(modelo=p.modelo),
            {"x-goog-api-key": p.chave},  # chave no cabeçalho: não aparece em URL nem em log
            {
                "systemInstruction": {"parts": [{"text": sistema}]},
                "contents": [{"role": "user", "parts": [{"text": usuario}, {"inline_data": {"mime_type": mime, "data": b64}}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        if r.status_code != 200:
            raise _erro_http("gemini", r)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _json(texto: str) -> dict:
    limpo = (texto or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if "{" in limpo and "}" in limpo:
        limpo = limpo[limpo.find("{") : limpo.rfind("}") + 1]
    try:
        dados = json.loads(limpo)
    except json.JSONDecodeError as e:
        log.warning("IA devolveu JSON inválido (%d caracteres).", len(texto or ""))  # nunca loga o conteúdo
        raise IAIndisponivel("A IA devolveu uma resposta fora do formato. Tente novamente ou preencha à mão.") from e
    if not isinstance(dados, dict):
        raise IAIndisponivel("A IA devolveu uma resposta fora do formato. Tente novamente ou preencha à mão.")
    return dados


_cliente: ClienteVisao = ClienteHttp()


def definir_cliente(c: ClienteVisao) -> None:
    """Para testes e para trocar o transporte."""
    global _cliente
    _cliente = c


def get_cliente() -> ClienteVisao:
    return _cliente
