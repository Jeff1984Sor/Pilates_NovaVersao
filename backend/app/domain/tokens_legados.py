"""Tokens de assinatura: verificação dos links ANTIGOS (Django) e emissão do formato novo (R10).

Origem: ``core/services.py`` linhas 269-290 (``gerar_token_contrato``/``validar_token_contrato`` com salt
``contrato-assinatura`` e 7 dias; ``gerar_token_termo``/``validar_token_termo`` com salt ``termo-assinatura`` e 30 dias),
todos via ``django.core.signing.TimestampSigner`` com a ``SECRET_KEY`` do Django.

Links de contrato/termo já enviados por e-mail/WhatsApp continuam válidos depois do cutover: este módulo reimplementa o
formato do Django SEM depender do Django em runtime:

    token  = valor ":" timestamp_base62 ":" assinatura
    assinatura = base64url_sem_padding( HMAC-SHA256( chave_derivada, valor ":" timestamp_base62 ) )
    chave_derivada = SHA256( sal + "signer" + SECRET_KEY )           # ``salted_hmac`` do Django, sal = salt + "signer"

``max_age`` é a idade máxima em segundos (``age > max_age`` expira; idade exatamente igual ainda vale; timestamp no
futuro é aceito, como no Django). Nada aqui lê o relógio: ``agora`` é sempre passado.

Formato NOVO (``emitir_token``/``verificar_token``): ``v1.<payload b64url>.<assinatura b64url>`` com payload JSON
``{"f": finalidade, "s": sujeito, "exp": epoch}`` e assinatura HMAC-SHA256 da chave do sistema, com expiração embutida.
O armazenamento/revogação dos links (tabela) é responsabilidade de outro módulo.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

SAL_CONTRATO = "contrato-assinatura"
SAL_TERMO = "termo-assinatura"
VALIDADE_CONTRATO_DIAS = 7
VALIDADE_TERMO_DIAS = 30
_SEPARADOR = ":"
_ALFABETO_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class TokenInvalido(Exception):
    """Assinatura não confere, formato inválido ou finalidade errada (equivale a ``BadSignature``)."""


class TokenExpirado(TokenInvalido):
    """Assinatura correta, mas o prazo acabou (equivale a ``SignatureExpired``)."""


# ---------------------------------------------------------------------------
# utilidades do formato Django
# ---------------------------------------------------------------------------

def _b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _b64url_decode(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _b62_encode(numero: int) -> str:
    if numero == 0:
        return "0"
    sinal = "-" if numero < 0 else ""
    numero = abs(numero)
    digitos = []
    while numero:
        numero, resto = divmod(numero, 62)
        digitos.append(_ALFABETO_B62[resto])
    return sinal + "".join(reversed(digitos))


def _b62_decode(texto: str) -> int:
    sinal = 1
    if texto.startswith("-"):
        sinal, texto = -1, texto[1:]
    numero = 0
    for c in texto:
        numero = numero * 62 + _ALFABETO_B62.index(c)
    return sinal * numero


def _epoch(agora: float | int | datetime) -> float:
    return agora.timestamp() if isinstance(agora, datetime) else float(agora)


def _assinatura_django(valor: str, sal: str, chave: str) -> str:
    """``Signer.signature``: ``base64_hmac(salt + "signer", value, key, algorithm="sha256")``."""
    chave_derivada = hashlib.sha256((sal + "signer" + chave).encode()).digest()
    return _b64url(hmac.new(chave_derivada, valor.encode(), hashlib.sha256).digest())


def gerar_token_django(valor: str, sal: str, chave: str, agora: float | int | datetime) -> str:
    """Gera um token idêntico ao ``TimestampSigner(salt=sal).sign(valor)`` do Django (usado em testes e, se preciso,
    para reemitir links antigos durante a janela de compatibilidade)."""
    com_tempo = f"{valor}{_SEPARADOR}{_b62_encode(int(_epoch(agora)))}"
    return f"{com_tempo}{_SEPARADOR}{_assinatura_django(com_tempo, sal, chave)}"


def verificar_token_django(
    token: str,
    sal: str,
    chaves: str | Sequence[str],
    max_age_segundos: float | int,
    agora: float | int | datetime,
) -> str:
    """Valor assinado (string) de um token do ``TimestampSigner`` do Django, ou levanta ``TokenInvalido``/``TokenExpirado``.

    ``chaves``: a ``SECRET_KEY`` antiga (ou uma lista dela + as anteriores, como ``SECRET_KEY_FALLBACKS``).
    """
    lista = [chaves] if isinstance(chaves, str) else list(chaves)
    if not token or _SEPARADOR not in token:
        raise TokenInvalido("Token sem separador.")
    assinado, _, assinatura = token.rpartition(_SEPARADOR)
    if not any(hmac.compare_digest(assinatura.encode(), _assinatura_django(assinado, sal, c).encode()) for c in lista):
        raise TokenInvalido("Assinatura nao confere.")
    if _SEPARADOR not in assinado:
        raise TokenInvalido("Token sem timestamp.")
    valor, _, tempo = assinado.rpartition(_SEPARADOR)
    try:
        momento = _b62_decode(tempo)
    except ValueError as exc:
        raise TokenInvalido("Timestamp invalido.") from exc
    if _epoch(agora) - momento > max_age_segundos:
        raise TokenExpirado(f"Token expirado (emitido em {momento}).")
    return valor


def verificar_token_contrato(
    token: str, chaves: str | Sequence[str], agora: float | int | datetime, validade_dias: int = VALIDADE_CONTRATO_DIAS
) -> int:
    """Id do contrato de um link ``contratos/assinar/<token>/`` antigo (7 dias). ``validar_token_contrato`` do antigo."""
    return int(verificar_token_django(token, SAL_CONTRATO, chaves, validade_dias * 86400, agora))


def verificar_token_termo(
    token: str, chaves: str | Sequence[str], agora: float | int | datetime, validade_dias: int = VALIDADE_TERMO_DIAS
) -> int:
    """Id do aluno de um link ``termos/assinar/<token>/`` antigo (30 dias). ``validar_token_termo`` do antigo."""
    return int(verificar_token_django(token, SAL_TERMO, chaves, validade_dias * 86400, agora))


# ---------------------------------------------------------------------------
# formato novo
# ---------------------------------------------------------------------------

_PREFIXO_NOVO = "v1."


def emitir_token(finalidade: str, sujeito: str | int, chave: str, agora: float | int | datetime, validade_segundos: int) -> str:
    """Token novo ``v1.<payload>.<assinatura>`` com expiração (``agora + validade_segundos``).

    ``finalidade`` impede usar um link de contrato como link de termo (ex.: ``"contrato"``, ``"termo"``).
    """
    expira = int(_epoch(agora)) + int(validade_segundos)
    payload = _b64url(json.dumps({"f": finalidade, "s": str(sujeito), "exp": expira}, separators=(",", ":"), sort_keys=True).encode())
    return f"{_PREFIXO_NOVO}{payload}.{_assinar_novo(payload, chave)}"


def _assinar_novo(payload: str, chave: str) -> str:
    return _b64url(hmac.new(chave.encode(), f"pilates-token-v1.{payload}".encode(), hashlib.sha256).digest())


def verificar_token(token: str, finalidade: str, chaves: str | Sequence[str], agora: float | int | datetime) -> str:
    """Sujeito de um token novo (string) ou levanta ``TokenInvalido``/``TokenExpirado``."""
    lista = [chaves] if isinstance(chaves, str) else list(chaves)
    if not token or not token.startswith(_PREFIXO_NOVO):
        raise TokenInvalido("Formato desconhecido.")
    try:
        payload, assinatura = token[len(_PREFIXO_NOVO):].rsplit(".", 1)
    except ValueError as exc:
        raise TokenInvalido("Formato invalido.") from exc
    if not any(hmac.compare_digest(assinatura.encode(), _assinar_novo(payload, c).encode()) for c in lista):
        raise TokenInvalido("Assinatura nao confere.")
    try:
        dados = json.loads(_b64url_decode(payload))
        exp = int(dados["exp"])
        if dados["f"] != finalidade:
            raise TokenInvalido("Finalidade incorreta.")
        sujeito = str(dados["s"])
    except (ValueError, KeyError, TypeError) as exc:
        raise TokenInvalido("Payload invalido.") from exc
    if _epoch(agora) > exp:
        raise TokenExpirado("Token expirado.")
    return sujeito


@dataclass(frozen=True)
class TokenVerificado:
    sujeito: str
    formato: str  # "novo" | "legado"


def verificar_token_aceitando_legado(
    token: str,
    finalidade: str,
    chave_nova: str | Sequence[str],
    chaves_legadas: str | Sequence[str] | None,
    agora: float | int | datetime,
) -> TokenVerificado:
    """Aceita o formato novo e, se ``chaves_legadas`` (``LEGACY_DJANGO_SECRET_KEY``) estiver configurada, o antigo.

    ``finalidade``: ``"contrato"`` (sal ``contrato-assinatura``, 7 dias) ou ``"termo"`` (sal ``termo-assinatura``, 30 dias).
    Janela de compatibilidade (pelo menos 30 dias após o cutover): deixe ``chaves_legadas`` configurada; depois, remova.
    """
    if token and token.startswith(_PREFIXO_NOVO):
        return TokenVerificado(verificar_token(token, finalidade, chave_nova, agora), "novo")
    if not chaves_legadas:
        raise TokenInvalido("Token legado nao aceito (chave antiga nao configurada).")
    if finalidade == "contrato":
        return TokenVerificado(str(verificar_token_contrato(token, chaves_legadas, agora)), "legado")
    if finalidade == "termo":
        return TokenVerificado(str(verificar_token_termo(token, chaves_legadas, agora)), "legado")
    raise TokenInvalido("Finalidade desconhecida para token legado.")
