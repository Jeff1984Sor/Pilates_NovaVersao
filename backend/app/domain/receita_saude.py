"""Arquivo de importação em lote do Receita Saúde (Receita Federal) (R8).

Porta fiel de ``core/receita_saude.py`` do sistema antigo (153 linhas). Formato do Manual do Receita Saúde v2.1
(perguntas 24 e 25): CSV com campos separados por ponto e vírgula, até 1000 linhas, todos os pagamentos do mesmo ano,
sem cabeçalho, quebra de linha CRLF. O profissional importa o arquivo no e-CAC > Carnê-Leão > Escrituração >
Importar Escrituração. Não existe API para emitir o recibo direto: quem emite é a Receita, após a importação.

Colunas, na ordem:
 1 Data do pagamento (DD/MM/AAAA)            9 CPF do beneficiário (11 dígitos)
 2 Código do rendimento (R01.001.001)       10 Ind. CPF não informado (vazio)
 3 Código da ocupação (231 = fisioterapeuta) 11 CNPJ (vazio)
 4 Valor do pagamento (1234,56)             12 Indicador de IRRF (vazio)
 5 Valor da dedução (vazio)                 13 Valor IRRF (vazio)
 6 Descrição (até 255)                      14 Indicador de recibo (S)
 7 Recebido de (PF)                         15 CPF do profissional (11 dígitos)
 8 CPF do pagador (11 dígitos)              16 Registro profissional (até 15)

Tudo-ou-nada: se QUALQUER linha tiver erro, nenhum arquivo é gerado (a Receita rejeita o lote inteiro).
``recibo_saude_gerado_em`` na conta evita emitir o mesmo recibo duas vezes (ver ``contas_ja_geradas``).

Os objetos de entrada são "duck typed" (qualquer coisa com os atributos abaixo): conta -> ``status``, ``dtPagamento``,
``valor``, ``descricao``, ``competencia``, ``dtVencimento``; aluno -> ``dsCPF``, ``sem_cpf``, ``cpf_pagador_recibo``;
config -> ``cpf_profissional``, ``registro_profissional``, ``codigo_ocupacao``, ``descricao_padrao``. Os nomes
seguem o Django antigo para o ETL e os testes portados.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.documentos import so_digitos, validar_cpf

CODIGO_RENDIMENTO = "R01.001.001"
MAX_LINHAS = 1000
OCUPACOES = {
    "225": "Medico",
    "226": "Odontologo",
    "230": "Fonoaudiologo",
    "231": "Fisioterapeuta",
    "232": "Terapeuta ocupacional",
    "255": "Psicologo",
}

#: nome mantido do sistema antigo
cpf_valido = validar_cpf

__all__ = [
    "CODIGO_RENDIMENTO", "MAX_LINHAS", "OCUPACOES", "so_digitos", "cpf_valido", "descricao_recibo", "formatar_valor",
    "problemas_da_configuracao", "cpfs_do_aluno", "problemas_da_conta", "montar_linha", "gerar_arquivo",
    "contas_ja_geradas", "mensagem_recibos_ja_gerados", "chave_de_ordenacao", "nome_do_arquivo",
]


def _sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def descricao_recibo(conta: Any, config: Any) -> str:
    """Descrição da conta (ou a padrão) + ``" - competencia AAAA-MM"`` se ainda não estiver no texto.

    Sem acento, sem ``;`` (vira ``,``), sem quebras de linha, espaços colapsados, até 255 caracteres.
    """
    base = (getattr(conta, "descricao", "") or "").strip() or config.descricao_padrao
    competencia = (getattr(conta, "competencia", "") or "").strip()
    if competencia and competencia not in base:
        base = f"{base} - competencia {competencia}"
    limpo = _sem_acentos(base).replace(";", ",")
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo[:255]


def formatar_valor(valor: Any) -> str:
    """1234.5 -> '1234,50' (vírgula decimal, sem separador de milhar)."""
    return f"{Decimal(valor).quantize(Decimal('0.01'))}".replace(".", ",")


def problemas_da_configuracao(config: Any) -> list[str]:
    problemas: list[str] = []
    if config is None:
        return ["Configure o CPF do profissional em Configuracoes > Receita Saude."]
    if not cpf_valido(config.cpf_profissional):
        problemas.append("CPF do profissional invalido em Configuracoes > Receita Saude.")
    if config.codigo_ocupacao not in OCUPACOES:
        problemas.append("Codigo de ocupacao invalido em Configuracoes > Receita Saude.")
    return problemas


def cpfs_do_aluno(aluno: Any) -> tuple[str, str]:
    """``(cpf do pagador, cpf do beneficiário)``. O pagador padrão é o próprio aluno; aluno ``sem_cpf`` não tem beneficiário."""
    beneficiario = so_digitos(aluno.dsCPF) if not aluno.sem_cpf else ""
    pagador = so_digitos(getattr(aluno, "cpf_pagador_recibo", "")) or beneficiario
    return pagador, beneficiario


def problemas_da_conta(conta: Any, aluno: Any) -> list[str]:
    """Motivos pelos quais esta cobrança não pode virar linha do arquivo (lista vazia = ok)."""
    problemas: list[str] = []
    if aluno is None:
        return ["Cobranca sem aluno vinculado."]
    if conta.status != "PAGO":
        problemas.append("Ainda nao esta paga.")
    if not conta.dtPagamento:
        problemas.append("Sem data de pagamento.")
    if not conta.valor or Decimal(conta.valor) <= 0:
        problemas.append("Valor deve ser maior que zero.")
    pagador, beneficiario = cpfs_do_aluno(aluno)
    if not beneficiario:
        problemas.append("Aluno sem CPF (obrigatorio no recibo).")
    elif not cpf_valido(beneficiario):
        problemas.append("CPF do aluno invalido.")
    if pagador and not cpf_valido(pagador):
        problemas.append("CPF do pagador invalido.")
    return problemas


def montar_linha(conta: Any, aluno: Any, config: Any) -> list[str]:
    pagador, beneficiario = cpfs_do_aluno(aluno)
    return [
        conta.dtPagamento.strftime("%d/%m/%Y"),
        CODIGO_RENDIMENTO,
        config.codigo_ocupacao,
        formatar_valor(conta.valor),
        "",  # valor da dedução: não se aplica a recibo
        descricao_recibo(conta, config),
        "PF",
        pagador,
        beneficiario,
        "", "", "", "",  # ind. CPF não informado, CNPJ, indicador de IRRF, valor IRRF
        "S",
        so_digitos(config.cpf_profissional),
        (config.registro_profissional or "").strip()[:15],
    ]


def gerar_arquivo(itens: Sequence[tuple[Any, Any]], config: Any) -> tuple[str | None, list[str]]:
    """``itens``: lista de ``(conta, aluno)``. Retorna ``(conteudo_csv, erros)``.

    Se houver qualquer erro, não devolve arquivo (``None``): a Receita rejeita o lote inteiro pelo erro de uma linha.
    """
    erros = problemas_da_configuracao(config)
    if not itens:
        erros.append("Selecione ao menos um pagamento.")
    if len(itens) > MAX_LINHAS:
        erros.append(f"O arquivo aceita ate {MAX_LINHAS} linhas; foram selecionados {len(itens)}.")
    for conta, aluno in itens:
        for problema in problemas_da_conta(conta, aluno):
            erros.append(f"{conta.dtVencimento:%d/%m/%Y} (R$ {formatar_valor(conta.valor or 0)}): {problema}")
    anos = {conta.dtPagamento.year for conta, _ in itens if conta.dtPagamento}
    if len(anos) > 1:
        erros.append("Todos os pagamentos do arquivo devem ser do mesmo ano (selecionados: " + ", ".join(str(a) for a in sorted(anos)) + ").")
    if erros:
        return None, erros

    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_NONE, escapechar="\\")
    for conta, aluno in itens:
        escritor.writerow(montar_linha(conta, aluno, config))
    return saida.getvalue(), []


# ---------------------------------------------------------------------------
# Regras da tela (``aluno_receita_saude_arquivo``, views.py:6192)
# ---------------------------------------------------------------------------

def contas_ja_geradas(contas: Iterable[Any]) -> list[Any]:
    """Contas marcadas que já tiveram o arquivo gerado (``recibo_saude_gerado_em`` preenchido)."""
    return [c for c in contas if getattr(c, "recibo_saude_gerado_em", None)]


def mensagem_recibos_ja_gerados(quantidade: int) -> str:
    return (
        f"{quantidade} pagamento(s) marcado(s) ja tiveram o arquivo gerado. "
        "Importar de novo emite o recibo em duplicidade; use 'Liberar' se for refazer."
    )


def chave_de_ordenacao(conta: Any) -> tuple[date, int]:
    """Ordem das linhas do arquivo: data do pagamento (sem data primeiro), depois id."""
    return (conta.dtPagamento or date.min, conta.id)


def nome_do_arquivo(nome_aluno: str, aluno_id: int, agora: Any) -> str:
    """``receita-saude-<slug do nome>-AAAAMMDD.csv`` (``slugify`` do Django; sem nome usa o id)."""
    texto = unicodedata.normalize("NFKD", nome_aluno or "").encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^\w\s-]", "", texto.lower())
    slug = re.sub(r"[-\s]+", "-", texto).strip("-_")
    return f"receita-saude-{slug or aluno_id}-{agora:%Y%m%d}.csv"
