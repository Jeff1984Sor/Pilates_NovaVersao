"""Telefone brasileiro: UMA normalização canônica (R16).

O sistema antigo tinha três comportamentos diferentes (e a nota do inventário pede um só):

1. ``core/whatsapp_service.py`` ``WhatsappService.clean_phone`` (linha 189): usada para ENVIAR WhatsApp.
   Tira não-dígitos e zeros à esquerda; com DDI 55 exige >= 12 dígitos; 10/11 dígitos ganham 55; qualquer
   outra coisa (ex.: 8 ou 9 dígitos, sem DDD) é devolvida como está.
2. ``core/views.py`` ``_format_whatsapp_number`` (linha 299): pega o primeiro telefone da lista; se começa
   com 55 devolve como está (mesmo curto); 10/11 dígitos ganham 55; senão devolve como está.
3. ``api/main.py`` ``_telefone_canon`` (linha 187): reduz a ``(ddd, 8 dígitos finais)`` tolerando DDI 55 e o
   nono dígito. Usada só para COMPARAR telefones na API de integração (``/integracao/alunos/por-telefone``).

Aqui: ``normalizar_telefone_br`` é a forma canônica para ARMAZENAR e ENVIAR (``55`` + DDD + número, só
dígitos, celular sempre com o nono dígito), ``mesmo_telefone`` é a comparação tolerante e as funções
antigas ficam portadas fielmente (sufixo ``_antigo``) só para caracterização e para a conciliação do ETL.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

DDI_BRASIL = "55"
_NAO_DIGITO = re.compile(r"\D+")


def _digitos(raw: str | None) -> str:
    return _NAO_DIGITO.sub("", raw or "")


# ---------------------------------------------------------------------------
# Forma canônica nova
# ---------------------------------------------------------------------------

def normalizar_telefone_br(raw: str | None, *, adicionar_nono_digito: bool = True) -> str | None:
    """Devolve ``55<DDD><número>`` (só dígitos) ou ``None`` se não for um telefone brasileiro plausível.

    Aceita com/sem máscara, com/sem DDI 55, com zero de operadora/tronco à esquerda, com/sem nono dígito.

    - 11 dígitos nacionais: DDD + ``9`` + 8 dígitos (celular). Se o 3º dígito não for 9, é inválido.
    - 10 dígitos nacionais: DDD + 8 dígitos. Se o número começa com 6-9 é celular antigo (sem o 9):
      ganha o nono dígito (``adicionar_nono_digito=True``); se começa com 2-5 é fixo e fica com 10 dígitos.
    - Sem DDD (8 ou 9 dígitos) é ``None``: não dá para enviar com segurança. (O antigo devolvia o texto.)
    - DDD não pode começar nem terminar com 0.
    """
    d = _digitos(raw).lstrip("0")
    if not d:
        return None
    if d.startswith(DDI_BRASIL) and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11):
        return None
    ddd, local = d[:2], d[2:]
    if ddd[1] == "0":
        return None
    if len(local) == 9:
        if local[0] != "9":
            return None
        return DDI_BRASIL + d
    if local[0] in "6789":
        return DDI_BRASIL + ddd + ("9" + local if adicionar_nono_digito else local)
    if local[0] in "2345":
        return DDI_BRASIL + d
    return None


def tipo_telefone(canonico: str | None) -> str | None:
    """``"celular"`` ou ``"fixo"`` para um número já canônico (saída de ``normalizar_telefone_br``)."""
    if not canonico:
        return None
    nacional = canonico[2:] if canonico.startswith(DDI_BRASIL) else canonico
    if len(nacional) == 11:
        return "celular"
    if len(nacional) == 10:
        return "celular" if nacional[2] in "6789" else "fixo"
    return None


def primeiro_telefone_valido(telefones: Iterable[str | None]) -> str | None:
    """Primeiro telefone da lista que normaliza (ordem preservada, como ``get_aluno_phone`` antigo)."""
    for tel in telefones:
        canonico = normalizar_telefone_br(tel)
        if canonico:
            return canonico
    return None


def chave_telefone(raw: str | None) -> tuple[str, str] | None:
    """``(ddd, 8 dígitos finais)`` tolerando DDI 55 e nono dígito. Porta fiel de ``_telefone_canon``."""
    d = _digitos(raw)
    if not d:
        return None
    if d.startswith("55") and len(d) > 11:
        d = d[2:]
    if len(d) < 10:
        return None
    ultimos8 = d[-8:]
    resto = d[:-8]
    if len(resto) >= 3 and resto[-1] == "9":
        resto = resto[:-1]
    ddd = resto[-2:]
    if len(ddd) != 2:
        return None
    return (ddd, ultimos8)


def mesmo_telefone(a: str | None, b: str | None) -> bool:
    """True se os dois números são o mesmo aparelho, ignorando máscara, DDI 55 e nono dígito."""
    ka, kb = chave_telefone(a), chave_telefone(b)
    return ka is not None and ka == kb


# ---------------------------------------------------------------------------
# Comportamentos antigos (apenas caracterização / ETL)
# ---------------------------------------------------------------------------

def limpar_telefone_antigo(raw: str | None) -> str | None:
    """# COMPORTAMENTO ANTIGO: ``WhatsappService.clean_phone``. Devolve lixo como está (ex.: 9 dígitos sem DDD)."""
    if not raw:
        return None
    cleaned = _NAO_DIGITO.sub("", raw).lstrip("0")
    if not cleaned:
        return None
    if cleaned.startswith("55"):
        return cleaned if len(cleaned) >= 12 else None
    if len(cleaned) in (10, 11):
        return f"55{cleaned}"
    return cleaned


def formatar_whatsapp_antigo(telefones: Iterable[str | None]) -> str | None:
    """# COMPORTAMENTO ANTIGO: ``views._format_whatsapp_number`` (aceita ``55`` curto e não tira zeros)."""
    for tel in telefones:
        cleaned = _NAO_DIGITO.sub("", tel or "")
        if not cleaned:
            continue
        if cleaned.startswith("55"):
            return cleaned
        if len(cleaned) in (10, 11):
            return f"55{cleaned}"
        return cleaned
    return None
