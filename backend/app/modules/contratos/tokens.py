"""Links de assinatura (R10): formato NOVO (`core.links`, HMAC com prazo) e formato ANTIGO do Django.

- Contrato: 7 dias. Termo de imagem: 30 dias.
- Novo: `core.links.assinar(finalidade, {"i": id}, validade)`; a finalidade impede usar um link de contrato como link
  de termo (e vice-versa) e qualquer outro link do sistema (arquivos, por exemplo).
- Antigo: `django.core.signing.TimestampSigner` com a `SECRET_KEY` do Django antigo (`LEGACY_DJANGO_SECRET_KEY`) e os
  sais `contrato-assinatura` / `termo-assinatura`, verificado por `domain.tokens_legados` (sem depender do Django).
  Sem a variável configurada, token antigo é simplesmente recusado.
- Quem chama recebe só `LinkInvalido` (adulterado, malformado, sal ou finalidade errados) ou `LinkExpirado`; nenhuma
  mensagem diz POR QUE um token é inválido além de "expirou" ou "não vale".
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core import links
from app.core.config import settings
from app.core.links import LinkExpirado, LinkInvalido
from app.domain import tokens_legados as legado

FINALIDADE_CONTRATO = "assinar-contrato"
FINALIDADE_TERMO = "assinar-termo"
VALIDADE_CONTRATO_S = legado.VALIDADE_CONTRATO_DIAS * 86400
VALIDADE_TERMO_S = legado.VALIDADE_TERMO_DIAS * 86400

__all__ = [
    "FINALIDADE_CONTRATO",
    "FINALIDADE_TERMO",
    "LinkExpirado",
    "LinkInvalido",
    "TokenEmitido",
    "TokenLido",
    "emitir_contrato",
    "emitir_termo",
    "ler_contrato",
    "ler_termo",
]


@dataclass(frozen=True)
class TokenEmitido:
    token: str
    expira_em: datetime


@dataclass(frozen=True)
class TokenLido:
    sujeito_id: int
    formato: str  # "novo" | "legado"


def _emitir(finalidade: str, sujeito_id: int, validade_s: int, agora_s: float | None) -> TokenEmitido:
    t = time.time() if agora_s is None else agora_s
    token = links.assinar(finalidade, {"i": int(sujeito_id)}, validade_s, agora_s=t)
    return TokenEmitido(token, datetime.fromtimestamp(t + validade_s, tz=UTC))


def emitir_contrato(contrato_id: int, *, agora_s: float | None = None) -> TokenEmitido:
    return _emitir(FINALIDADE_CONTRATO, contrato_id, VALIDADE_CONTRATO_S, agora_s)


def emitir_termo(aluno_id: int, *, agora_s: float | None = None) -> TokenEmitido:
    return _emitir(FINALIDADE_TERMO, aluno_id, VALIDADE_TERMO_S, agora_s)


def _ler(token: str, finalidade: str, tipo_legado: str, agora_s: float | None) -> TokenLido:
    t = time.time() if agora_s is None else agora_s
    token = (token or "").strip()
    if not token or len(token) > 1200:
        raise LinkInvalido("link malformado")
    if ":" in token:  # só o formato antigo do Django usa ":" como separador
        chave = settings.legacy_django_secret_key
        if not chave:
            raise LinkInvalido("token antigo não aceito")
        try:
            if tipo_legado == "contrato":
                sujeito = legado.verificar_token_contrato(token, chave, t)
            else:
                sujeito = legado.verificar_token_termo(token, chave, t)
        except legado.TokenExpirado:
            raise LinkExpirado("link expirado") from None
        except (legado.TokenInvalido, ValueError):
            raise LinkInvalido("link inválido") from None
        return TokenLido(int(sujeito), "legado")
    dados = links.verificar(token, finalidade, agora_s=t)
    try:
        return TokenLido(int(dados["i"]), "novo")
    except (KeyError, TypeError, ValueError):
        raise LinkInvalido("link malformado") from None


def ler_contrato(token: str, *, agora_s: float | None = None) -> TokenLido:
    """Id do contrato de um link novo ou antigo; `LinkInvalido`/`LinkExpirado` caso contrário."""
    return _ler(token, FINALIDADE_CONTRATO, "contrato", agora_s)


def ler_termo(token: str, *, agora_s: float | None = None) -> TokenLido:
    """Id do aluno de um link de termo novo ou antigo."""
    return _ler(token, FINALIDADE_TERMO, "termo", agora_s)
