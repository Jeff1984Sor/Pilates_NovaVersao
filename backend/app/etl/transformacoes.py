"""Transformações puras do ETL: CPF, telefone, datas, dinheiro, enums, caminhos de mídia e segredos.

PONTO ÚNICO DE TROCA: `normalizar_cpf_digitos`, `validar_cpf` e `normalizar_telefone_br` são implementações
locais simples. Quando o módulo `app.domain` (agente DOMÍNIO) publicar as versões oficiais (R16), basta trocar o
corpo destas três funções por uma chamada a ele; o resto do ETL só usa estas funções.
"""

from __future__ import annotations

import enum
import hashlib
import json
import posixpath
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

# --------------------------------------------------------------------------- texto


def texto(valor: Any) -> str | None:
    """Texto aparado; vazio vira None."""
    if valor is None:
        return None
    s = str(valor).strip()
    return s or None


def so_digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


# --------------------------------------------------------------------------- CPF e telefone (ponto de troca)


def normalizar_cpf_digitos(valor: Any) -> str:
    """Só os dígitos do CPF (aceita máscara, espaços, etc.)."""
    return so_digitos(valor)


def validar_cpf(cpf: str) -> bool:
    """Valida os dígitos verificadores de um CPF de 11 dígitos."""
    if len(cpf) != 11 or not cpf.isdigit() or len(set(cpf)) == 1:
        return False
    for tam in (9, 10):
        soma = sum(int(cpf[i]) * (tam + 1 - i) for i in range(tam))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[tam]):
            return False
    return True


def normalizar_telefone_br(valor: Any) -> str | None:
    """Telefone brasileiro só com dígitos e DDI 55 (55 + DDD + número); insere o nono dígito em celular de 8 dígitos.

    Devolve None se não houver dígitos suficientes (menos de 8). Números que não parecem brasileiros
    (mais de 13 dígitos) são devolvidos como estão, só com dígitos.
    """
    d = so_digitos(valor)
    if d.startswith("00"):
        d = d[2:]
    if len(d) < 8:
        return None
    if len(d) in (8, 9):  # sem DDD: não dá para completar; mantém
        return d
    if len(d) in (10, 11):
        d = "55" + d
    if d.startswith("55") and len(d) == 12 and d[4] in "6789":  # DDD + 8 dígitos de celular: falta o nono dígito
        d = d[:4] + "9" + d[4:]
    return d


# --------------------------------------------------------------------------- datas e dinheiro


def como_data(valor: Any) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def como_hora(valor: Any) -> time | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.time().replace(tzinfo=None)
    if isinstance(valor, time):
        return valor.replace(tzinfo=None)
    return time.fromisoformat(str(valor))


def como_instante(valor: Any) -> datetime | None:
    """Datetime com fuso UTC. O antigo grava em UTC (USE_TZ); valores sem fuso são tratados como UTC."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, date):
        dt = datetime.combine(valor, time.min)
    else:
        dt = datetime.fromisoformat(str(valor))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def dinheiro(valor: Any) -> Decimal | None:
    """Decimal com 2 casas (ROUND_HALF_UP); None se vazio."""
    if valor is None or valor == "":
        return None
    d = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def booleano(valor: Any, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "t", "sim", "yes")
    return bool(valor)


def como_json(valor: Any) -> Any:
    """JSON de coluna texto (SQLite) ou já decodificado (PostgreSQL jsonb)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (dict, list)):
        return valor
    try:
        return json.loads(valor)
    except (TypeError, ValueError):
        return {"_texto_original": str(valor)}


# --------------------------------------------------------------------------- enums


def como_enum(valor: Any, enum_cls: type[enum.Enum], padrao: enum.Enum | None = None) -> tuple[enum.Enum | None, bool]:
    """Converte para o enum. Devolve (membro, reconhecido). Valor vazio devolve (padrao, True)."""
    s = texto(valor)
    if s is None:
        return padrao, True
    try:
        return enum_cls(s.upper() if s.upper() in enum_cls.__members__ else s), True
    except ValueError:
        return padrao, False


# --------------------------------------------------------------------------- mídia

# (prefixo no antigo, prefixo no novo): o novo guarda caminhos relativos ao storage
_PREFIXOS_MIDIA = {
    "foto": ("alunos/", "alunos/foto/"),
    "termo": ("assinaturas_termo/", "assinaturas/termo/"),
    "assinatura_contrato": ("assinaturas/", "assinaturas/contrato/"),
    "documento": ("alunos/documentos/", "documentos/"),
    "comprovante_pagar": ("comprovantes/contas_pagar/", "comprovantes/contas_pagar/"),
    "comprovante_movimento": ("comprovantes/movimentos/", "comprovantes/movimentos/"),
}


def caminho_midia(campo: str, valor: Any) -> str | None:
    """Caminho do arquivo no storage novo (relativo, com `/`), a partir do valor gravado no Django."""
    s = texto(valor)
    if s is None:
        return None
    s = s.replace("\\", "/").lstrip("/")
    antigo, novo = _PREFIXOS_MIDIA[campo]
    resto = s[len(antigo) :] if s.startswith(antigo) else posixpath.basename(s)
    return novo + resto


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


# --------------------------------------------------------------------------- segredos e tokens


class Cifrador:
    """Cifra segredos de integração com a MASTER_KEY (Fernet), no mesmo formato do core."""

    def __init__(self, master_key: str):
        self._f = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)

    def cifrar(self, valor: Any) -> str | None:
        s = texto(valor)
        return None if s is None else self._f.encrypt(s.encode()).decode()

    def decifrar(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def semente_estavel(*partes: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, partes)).encode()).hexdigest()[:8], 16)
