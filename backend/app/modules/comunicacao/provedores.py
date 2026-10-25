"""Provedores de WhatsApp: WasenderAPI e Evolution API, com interface comum.

Regras (R9 / ``core/whatsapp_service.py`` do sistema antigo, corrigidas):
- timeout em toda chamada; a rede é injetável (``transporte``) para os testes NUNCA irem à internet;
- o token só vai no cabeçalho: nunca em log, em mensagem de erro, em resposta da API nem na auditoria
  (``_sem_segredo`` apaga qualquer eco do token de dentro do texto que volta do provedor);
- o número é normalizado por ``domain.telefone`` (``55DDD9XXXXXXXX``);
- falha de autenticação (401/403) e sessão desconectada NÃO são repetidas: repetir só atrasa o aviso;
- ``enviar_com_retry`` faz até 3 tentativas com pausa (sessão caída aborta o lote: ``sessao_caiu=True``).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from app.domain import whatsapp_avisos as dom
from app.domain.telefone import normalizar_telefone_br

log = logging.getLogger(__name__)

TIMEOUT_TEXTO_S = 15.0
TIMEOUT_DOCUMENTO_S = 30.0
TIMEOUT_STATUS_S = 10.0
TENTATIVAS = dom.TENTATIVAS_POR_ENVIO
PAUSA_RETRY_S = 2.0
WASENDER_URL_PADRAO = "https://www.wasenderapi.com"

_PISTAS_SESSAO_CAIDA = ("not connected", "disconnected", "connection closed", "session is not", "logged out", "not logged")


class ConfiguracaoIncompleta(Exception):
    """Faltam dados (URL, credencial ou instância) para falar com o provedor."""


@dataclass
class Resultado:
    ok: bool
    erro: str | None = None
    status_http: int | None = None
    sessao_caiu: bool = False
    erro_autenticacao: bool = False
    #: erro que repetir não resolve (telefone/arquivo/configuração inválidos)
    definitivo: bool = False
    retry_after: float | None = None
    #: resumo SEM segredos da resposta (vai para ``resposta_payload``)
    resumo: str = ""
    tentativas: int = 1


@dataclass
class StatusSessao:
    conectada: bool | None  # None = o provedor respondeu, mas não deu para saber
    detalhe: str
    erro_autenticacao: bool = False
    sem_resposta: bool = False


@dataclass
class Provedor:
    """Base. As subclasses montam URL/cabeçalhos/corpo; o envio HTTP e o tratamento de erro são comuns."""

    url: str | None
    credencial: str | None
    instancia: str | None = None
    transporte: httpx.BaseTransport | None = field(default=None, repr=False)
    nome = "base"

    # -- a ser implementado --------------------------------------------------------------------------------------
    def _req_texto(self, numero: str, texto: str) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def _req_documento(self, numero: str, url: str, nome: str, legenda: str) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def _req_status(self) -> tuple[str, dict]:
        raise NotImplementedError

    def _interpretar_status(self, dados: Any) -> StatusSessao:
        raise NotImplementedError

    # -- público -------------------------------------------------------------------------------------------------
    def enviar_texto(self, telefone: str, texto: str) -> Resultado:
        numero = self._numero(telefone)
        if not numero:
            return Resultado(False, "Telefone inválido para WhatsApp.", definitivo=True)
        try:
            url, cab, corpo = self._req_texto(numero, texto)
        except ConfiguracaoIncompleta as e:
            return Resultado(False, str(e), definitivo=True)
        return self._enviar(url, cab, corpo, TIMEOUT_TEXTO_S)

    def enviar_documento(self, telefone: str, url_arquivo: str, nome_arquivo: str, legenda: str = "") -> Resultado:
        numero = self._numero(telefone)
        if not numero:
            return Resultado(False, "Telefone inválido para WhatsApp.", definitivo=True)
        if not url_arquivo or urlparse(url_arquivo).scheme not in ("http", "https"):
            return Resultado(False, "Endereço do arquivo ausente ou inválido.", definitivo=True)
        try:
            url, cab, corpo = self._req_documento(numero, url_arquivo, nome_arquivo, legenda or "")
        except ConfiguracaoIncompleta as e:
            return Resultado(False, str(e), definitivo=True)
        return self._enviar(url, cab, corpo, TIMEOUT_DOCUMENTO_S)

    def status_sessao(self) -> StatusSessao:
        """Consulta se a sessão do WhatsApp está conectada (botão "Testar conexão")."""
        try:
            url, cab = self._req_status()
        except ConfiguracaoIncompleta as e:
            return StatusSessao(None, str(e), sem_resposta=True)
        try:
            with httpx.Client(transport=self.transporte, timeout=TIMEOUT_STATUS_S) as c:
                r = c.get(url, headers=cab)
        except httpx.HTTPError as e:
            return StatusSessao(None, f"Sem resposta do provedor ({type(e).__name__}).", sem_resposta=True)
        if r.status_code in (401, 403):
            return StatusSessao(None, "Credencial recusada pelo provedor (confira o token/chave).", erro_autenticacao=True)
        if r.status_code >= 400:
            return StatusSessao(None, f"O provedor respondeu HTTP {r.status_code}.")
        try:
            dados = r.json()
        except ValueError:
            return StatusSessao(None, "Resposta do provedor não reconhecida.")
        return self._interpretar_status(dados)

    # -- interno -------------------------------------------------------------------------------------------------
    @staticmethod
    def _numero(telefone: str) -> str | None:
        return normalizar_telefone_br(telefone)

    def _sem_segredo(self, texto: str) -> str:
        if self.credencial and self.credencial in texto:
            texto = texto.replace(self.credencial, "***")
        return texto

    def _enviar(self, url: str, cabecalhos: dict, corpo: dict, timeout: float) -> Resultado:
        try:
            with httpx.Client(transport=self.transporte, timeout=timeout) as c:
                r = c.post(url, json=corpo, headers=cabecalhos)
        except httpx.TimeoutException:
            return Resultado(False, "Tempo esgotado ao falar com o provedor de WhatsApp.", resumo="timeout")
        except httpx.HTTPError as e:
            # só o tipo da exceção: a mensagem do httpx pode trazer a URL
            return Resultado(False, f"Falha de rede ao falar com o provedor ({type(e).__name__}).", resumo=type(e).__name__)
        try:
            dados: Any = r.json()
        except ValueError:
            dados = {"texto": (r.text or "")[:300]}
        resumo = self._sem_segredo(_resumir(dados))[:500]
        corpo_txt = self._sem_segredo(f"{dados}").lower()
        retry_after = _retry_after(r)
        if r.status_code in (401, 403):
            return Resultado(False, "Credencial recusada pelo provedor (confira o token/chave).", r.status_code,
                             erro_autenticacao=True, resumo=resumo)
        recusado = isinstance(dados, dict) and dados.get("success") is False  # Wasender: HTTP 200 + success=false
        if r.status_code >= 400 or recusado:
            msg = ""
            if isinstance(dados, dict):
                msg = str(dados.get("message") or dados.get("error") or "")
            msg = self._sem_segredo(msg)[:200] or f"O provedor recusou o envio (HTTP {r.status_code})."
            resp = {"error": msg, "response": dados if isinstance(dados, dict) else {}}
            caiu = dom.sessao_do_whatsapp_caiu(resp) or any(p in corpo_txt for p in _PISTAS_SESSAO_CAIDA)
            return Resultado(False, msg, r.status_code, sessao_caiu=caiu, retry_after=retry_after, resumo=resumo)
        return Resultado(True, None, r.status_code, resumo=resumo)


def _retry_after(r: httpx.Response) -> float | None:
    valor = r.headers.get("Retry-After")
    try:
        return float(valor) if valor is not None else None
    except ValueError:
        return None


def _resumir(dados: Any) -> str:
    """Texto curto da resposta para o histórico (``resposta_payload``)."""
    if isinstance(dados, dict):
        partes = [f"{k}={dados[k]}" for k in ("success", "status", "message", "error", "id", "key") if k in dados]
        return "; ".join(str(p) for p in partes) or "ok"
    return str(dados)[:200]


# ------------------------------------------------------------------------------------------------- WasenderAPI
class Wasender(Provedor):
    """WasenderAPI: ``Authorization: Bearer <token da sessão>``; um único endpoint de envio (``/api/send-message``);
    documento = o mesmo endpoint com ``documentUrl`` + ``fileName``."""

    nome = "wasender"

    def _base(self) -> str:
        bruto = (self.url or WASENDER_URL_PADRAO).strip().rstrip("/")
        for sufixo in ("/api/send-message", "/api/send-media", "/api/status", "/api"):
            if bruto.endswith(sufixo):
                bruto = bruto[: -len(sufixo)]
                break
        return bruto

    def _cab(self) -> dict:
        if not self.credencial:
            raise ConfiguracaoIncompleta("Informe o token da sessão do WasenderAPI.")
        return {"Authorization": f"Bearer {self.credencial}"}

    def _req_texto(self, numero, texto):
        return f"{self._base()}/api/send-message", self._cab(), {"to": f"+{numero}", "text": texto}

    def _req_documento(self, numero, url, nome, legenda):
        corpo = {"to": f"+{numero}", "text": legenda, "documentUrl": url, "fileName": nome}
        return f"{self._base()}/api/send-message", self._cab(), corpo

    def _req_status(self):
        return f"{self._base()}/api/status", self._cab()

    def _interpretar_status(self, dados):
        estado = str(dados.get("status") or "").lower() if isinstance(dados, dict) else ""
        if estado == "connected":
            return StatusSessao(True, "Sessão conectada.")
        if estado:
            return StatusSessao(False, f"Sessão do WhatsApp não está conectada (situação: {estado}). "
                                       "Reconecte no painel do WasenderAPI.")
        return StatusSessao(None, "Resposta do provedor não reconhecida.")


# ------------------------------------------------------------------------------------------------- Evolution API
class Evolution(Provedor):
    """Evolution API (v2): cabeçalho ``apikey``; ``/message/sendText/{instancia}`` e ``/message/sendMedia/{instancia}``."""

    nome = "evolution"

    def _base(self) -> str:
        if not self.url or not self.url.strip():
            raise ConfiguracaoIncompleta("Informe o endereço (URL) da Evolution API.")
        return self.url.strip().rstrip("/")

    def _inst(self) -> str:
        if not (self.instancia or "").strip():
            raise ConfiguracaoIncompleta("Informe o nome da instância da Evolution API.")
        return (self.instancia or "").strip()

    def _cab(self) -> dict:
        if not self.credencial:
            raise ConfiguracaoIncompleta("Informe a chave (apikey) da Evolution API.")
        return {"apikey": self.credencial}

    def _req_texto(self, numero, texto):
        return f"{self._base()}/message/sendText/{self._inst()}", self._cab(), {"number": numero, "text": texto}

    def _req_documento(self, numero, url, nome, legenda):
        corpo = {"number": numero, "mediatype": "document", "media": url, "fileName": nome, "caption": legenda}
        return f"{self._base()}/message/sendMedia/{self._inst()}", self._cab(), corpo

    def _req_status(self):
        return f"{self._base()}/instance/connectionState/{self._inst()}", self._cab()

    def _interpretar_status(self, dados):
        estado = ""
        if isinstance(dados, dict):
            inst = dados.get("instance")
            estado = str((inst.get("state") if isinstance(inst, dict) else dados.get("state")) or "").lower()
        if estado == "open":
            return StatusSessao(True, "Sessão conectada.")
        if estado:
            return StatusSessao(False, f"Sessão do WhatsApp não está conectada (situação: {estado}). "
                                       "Leia o QR Code de novo na Evolution API.")
        return StatusSessao(None, "Resposta do provedor não reconhecida.")


def criar_provedor(provedor: str, url: str | None, credencial: str | None, instancia: str | None = None,
                   transporte: httpx.BaseTransport | None = None) -> Provedor:
    cls = Evolution if str(provedor) == "evolution" else Wasender
    return cls(url=url, credencial=credencial, instancia=instancia, transporte=transporte)


# ------------------------------------------------------------------------------------------------- repetição
def enviar_com_retry(
    acao: Callable[[], Resultado], *, tentativas: int = TENTATIVAS, pausa_s: float = PAUSA_RETRY_S,
    dormir: Callable[[float], None] = time.sleep,
) -> Resultado:
    """Até ``tentativas`` chamadas. Para na hora em caso de sucesso, sessão caída ou credencial recusada.
    Respeita ``Retry-After`` do provedor quando maior que a pausa."""
    ultimo = Resultado(False, "Envio não tentado.")
    pausa = pausa_s
    for n in range(1, tentativas + 1):
        ultimo = acao()
        ultimo.tentativas = n
        if ultimo.ok or ultimo.sessao_caiu or ultimo.erro_autenticacao or ultimo.definitivo:
            return ultimo
        if n < tentativas:
            pausa = max(pausa, ultimo.retry_after or 0)
            dormir(pausa)
    return ultimo
