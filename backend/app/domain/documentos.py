"""Documentos: CPF e dígitos (R16).

Origem no sistema antigo:
- ``core/validators.py`` ``validar_cpf`` (linhas 4-20) e ``core/receita_saude.py`` ``cpf_valido``/``so_digitos``
  (linhas 36-47). Os dois algoritmos são equivalentes (o teste cruzado em ``test_documentos.py`` confirma).
- ``core/models.py`` ``Aluno.save`` (linha ~110): aluno ``sem_cpf`` recebe ``SEM_CPF_<16 hex>`` em ``dsCPF``.
- ``api/main.py`` ``_so_digitos``/``_achar_aluno_por_cpf`` (376-385): o login do app compara apenas os dígitos.
"""
from __future__ import annotations

import re

PREFIXO_SEM_CPF = "SEM_CPF_"
_NAO_DIGITO = re.compile(r"\D")


def so_digitos(valor: str | None) -> str:
    """Remove tudo que não é dígito. ``None`` vira ``""``."""
    return _NAO_DIGITO.sub("", valor or "")


def validar_cpf(cpf: str | None) -> bool:
    """Confere tamanho (11 dígitos), sequência repetida e os dois dígitos verificadores."""
    digitos = so_digitos(cpf)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if ((soma * 10) % 11) % 10 != int(digitos[tamanho]):
            return False
    return True


def eh_sem_cpf(valor: str | None) -> bool:
    """True para o marcador gravado em alunos sem CPF (``SEM_CPF_...``)."""
    return (valor or "").startswith(PREFIXO_SEM_CPF)


def gerar_marcador_sem_cpf(sufixo_hex: str) -> str:
    """Monta ``SEM_CPF_<16 primeiros hex>``. O sufixo (uuid4().hex) é sorteado por quem chama."""
    return f"{PREFIXO_SEM_CPF}{sufixo_hex[:16]}"


def normalizar_cpf(valor: str | None) -> str:
    """Forma canônica para armazenar/comparar: 11 dígitos sem máscara.

    - ``SEM_CPF_*`` é preservado exatamente (não é CPF, só marcador de unicidade).
    - Qualquer outra coisa vira só dígitos (pode não ter 11: use ``validar_cpf`` para saber se é CPF válido).
    """
    if eh_sem_cpf(valor):
        return str(valor)
    return so_digitos(valor)


def formatar_cpf(valor: str | None) -> str:
    """``52998224725`` -> ``529.982.247-25``. Se não tiver 11 dígitos devolve o texto original."""
    digitos = so_digitos(valor)
    if len(digitos) != 11:
        return valor or ""
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def mesmo_cpf(a: str | None, b: str | None) -> bool:
    """Compara dois CPFs ignorando máscara.

    # COMPORTAMENTO ANTIGO (corrigido): o login do app comparava ``so_digitos(dsCPF)`` também para
    alunos ``SEM_CPF_*``; um marcador cujos hex tivessem exatamente 11 dígitos numéricos poderia
    coincidir com um CPF digitado. Aqui um marcador ``SEM_CPF_*`` nunca é igual a nada além dele mesmo.
    """
    if eh_sem_cpf(a) or eh_sem_cpf(b):
        return a == b
    da, db = so_digitos(a), so_digitos(b)
    return bool(da) and da == db
