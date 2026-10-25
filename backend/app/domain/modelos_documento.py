"""Modelos de documento (contrato e termo de imagem): variáveis `{CHAVE}` e renderização segura.

Origem no sistema antigo (``core/views.py`` e ``core/services.py``):
- ``CONTRACT_TEMPLATE_VARIABLES`` (views.py, linhas 250-283): a lista oficial de 31 variáveis, usada pelo painel
  do editor de contrato e de termo;
- ``render_contrato_html`` (services.py, 93-146) e ``render_termo_html`` (151-175): trocam ``{CHAVE}`` pelo valor
  (``str.replace`` na ordem da lista; valor vazio/``None`` vira ``""``); quando o plano não tem modelo, usam um
  contrato padrão.

Diferenças deliberadas em relação ao antigo (todas para melhor, nenhuma muda o texto de um modelo legítimo):
- a troca é feita em UMA passada (o antigo trocava em sequência, então um valor que contivesse ``{ALUNO_CPF}`` seria
  trocado de novo); o resultado é igual para dados normais;
- os valores são ESCAPADOS como HTML por padrão (``escapar=True``): um nome de aluno com ``<script>`` não vira
  marcação no documento. Com ``escapar=False`` a saída é idêntica à do antigo (usado no teste de caracterização);
- variável desconhecida continua literal (como no antigo), mas ``variaveis_desconhecidas`` permite avisar quem edita
  o modelo, e ``marcador_desconhecida`` permite trocá-la por um aviso visível.

Tudo é função pura, sem banco e sem exceções para entradas estranhas (``None``, tipos errados, chaves ausentes).
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape

__all__ = [
    "Variavel",
    "VARIAVEIS",
    "CHAVES",
    "CHAVES_TERMO",
    "ESCOPO_CONTRATO",
    "ESCOPO_TERMO",
    "MODELO_CONTRATO_PADRAO",
    "contexto_exemplo",
    "formatar_data",
    "formatar_moeda",
    "renderizar",
    "chaves_faltando",
    "variaveis_do_escopo",
    "variaveis_desconhecidas",
    "variaveis_usadas",
]

ESCOPO_CONTRATO = "contrato"
ESCOPO_TERMO = "termo"

# {CHAVE}: letras maiúsculas, dígitos e sublinhado (todas as chaves oficiais cabem neste padrão).
_PADRAO = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


@dataclass(frozen=True)
class Variavel:
    chave: str
    descricao: str
    exemplo: str
    #: em quais documentos a variável tem valor (o termo de imagem não conhece contrato/plano/unidade)
    termo: bool = False

    @property
    def marcador(self) -> str:
        return "{" + self.chave + "}"


# Ordem e rótulos do antigo (acentuados aqui). `termo=True` = o antigo ``render_termo_html`` também as troca.
VARIAVEIS: tuple[Variavel, ...] = (
    Variavel("ALUNO_NOME", "Nome do aluno", "Maria da Silva Souza", True),
    Variavel("ALUNO_CPF", "CPF do aluno", "529.982.247-25", True),
    Variavel("ALUNO_RG", "RG do aluno", "12.345.678-9", True),
    Variavel("ALUNO_NASCIMENTO", "Nascimento do aluno", "15/03/1988", True),
    Variavel("ALUNO_ESTADO_CIVIL", "Estado civil do aluno", "Casado(a)", True),
    Variavel("ALUNO_PROFISSAO", "Profissão do aluno", "Arquiteta", True),
    Variavel("ALUNO_EMAIL", "E-mail do aluno", "maria@exemplo.com.br", True),
    Variavel("ALUNO_TELEFONE", "Telefone do aluno", "(11) 99999-0000", True),
    Variavel("ALUNO_ENDERECO", "Endereço completo", "Rua das Flores, 120 - Centro - São Paulo (01000-000)", True),
    Variavel("ENDERECO_LOGRADOURO", "Logradouro", "Rua das Flores", True),
    Variavel("ENDERECO_NUMERO", "Número", "120", True),
    Variavel("ENDERECO_BAIRRO", "Bairro", "Centro", True),
    Variavel("ENDERECO_CIDADE", "Cidade", "São Paulo", True),
    Variavel("ENDERECO_CEP", "CEP", "01000-000", True),
    Variavel("PROFISSIONAL_NOME", "Profissional", "Dra. Ana Lima"),
    Variavel("PROFISSIONAL_CREFITO", "Crefito", "123456-F"),
    Variavel("UNIDADE_NOME", "Unidade", "Studio Mayris Centro"),
    Variavel("UNIDADE_CAPACIDADE", "Capacidade", "6"),
    Variavel("PLANO_NOME", "Plano", "Pilates 2x por semana"),
    Variavel("PLANO_AULAS_SEMANA", "Aulas por semana", "2"),
    Variavel("PLANO_DURACAO_MESES", "Duração (meses)", "6"),
    Variavel("PLANO_RECORRENCIA", "Recorrência do plano", "Mensal"),
    Variavel("TIPO_SERVICO", "Tipo de serviço", "Pilates"),
    Variavel("CONTRATO_NUMERO", "Número do contrato", "1024"),
    Variavel("CONTRATO_INICIO", "Início do contrato", "01/11/2026"),
    Variavel("CONTRATO_FIM", "Fim do contrato", "30/04/2027"),
    Variavel("CONTRATO_RECORRENCIA", "Recorrência do contrato", "Mensal"),
    Variavel("CONTRATO_MODO_PAGAMENTO", "Modo de pagamento", "Pix"),
    Variavel("CONTRATO_VALOR_PARCELA", "Valor da parcela", "R$ 360,00"),
    Variavel("CONTRATO_VALOR_TOTAL", "Valor total", "R$ 2160,00"),
    Variavel("DATA_HOJE", "Data de hoje", "25/10/2026", True),
)

CHAVES: frozenset[str] = frozenset(v.chave for v in VARIAVEIS)
CHAVES_TERMO: frozenset[str] = frozenset(v.chave for v in VARIAVEIS if v.termo)

#: contrato padrão do antigo, usado quando o plano não tem modelo (services.render_contrato_html)
MODELO_CONTRATO_PADRAO = (
    "<h3>Contrato {CONTRATO_NUMERO}</h3>"
    "<p>Aluno: {ALUNO_NOME} - {ALUNO_CPF}</p>"
    "<p>Plano: {PLANO_NOME}</p>"
    "<p>Recorrencia: {CONTRATO_RECORRENCIA}</p>"
    "<p>Periodo: {CONTRATO_INICIO} a {CONTRATO_FIM}</p>"
    "<p>Valor parcela: {CONTRATO_VALOR_PARCELA}</p>"
    "<p>Valor total: {CONTRATO_VALOR_TOTAL}</p>"
)


def variaveis_do_escopo(escopo: str = ESCOPO_CONTRATO) -> tuple[Variavel, ...]:
    """Variáveis válidas no documento: ``contrato`` (todas) ou ``termo`` (aluno, endereço e data)."""
    if escopo == ESCOPO_TERMO:
        return tuple(v for v in VARIAVEIS if v.termo)
    return VARIAVEIS


def _chaves_do_escopo(escopo: str | None) -> frozenset[str]:
    return CHAVES_TERMO if escopo == ESCOPO_TERMO else CHAVES


def contexto_exemplo(escopo: str = ESCOPO_CONTRATO) -> dict[str, str]:
    """Valores de exemplo (para a pré-visualização do editor). Não são dados reais de ninguém."""
    return {v.chave: v.exemplo for v in variaveis_do_escopo(escopo)}


def formatar_data(valor: date | None) -> str:
    """``dd/mm/aaaa``; vazio quando não há data."""
    return valor.strftime("%d/%m/%Y") if isinstance(valor, date) else ""


def formatar_moeda(valor: Decimal | float | int | str | None) -> str:
    """``R$ 360,00`` como o antigo ``_currency`` (SEM separador de milhar: ``R$ 1234,50``); inválido vira ``R$ 0,00``."""
    try:
        return f"R$ {float(valor):.2f}".replace(".", ",")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "R$ 0,00"


def variaveis_usadas(html: str | None) -> list[str]:
    """Chaves ``{CHAVE}`` que aparecem no texto (qualquer chave bem formada), sem repetir, na ordem de aparição."""
    vistas: dict[str, None] = {}
    for m in _PADRAO.finditer(html or ""):
        vistas.setdefault(m.group(1), None)
    return list(vistas)


def variaveis_desconhecidas(html: str | None, escopo: str | None = None) -> list[str]:
    """Chaves bem formadas que NÃO existem na lista oficial (ex.: erro de digitação ``{ALUNO_NOEM}``).

    Com ``escopo="termo"``, as variáveis de contrato (plano, unidade...) também são consideradas desconhecidas,
    porque o termo não tem esses dados.
    """
    validas = _chaves_do_escopo(escopo)
    return [c for c in variaveis_usadas(html) if c not in validas]


def _como_texto(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, date):
        return formatar_data(valor)
    return str(valor)


def renderizar(
    html: str | None,
    contexto: Mapping[str, object] | None,
    *,
    ausente: str = "",
    escapar: bool = True,
    escopo: str | None = None,
    marcador_desconhecida: str | None = None,
) -> str:
    """Troca ``{CHAVE}`` pelo valor de ``contexto[CHAVE]``. Nunca levanta exceção.

    - chave oficial sem valor no contexto (ausente, ``None`` ou vazio) -> ``ausente`` (padrão: texto vazio, como o antigo);
    - chave desconhecida (fora da lista oficial, ou fora do ``escopo`` quando informado) -> mantida literal, como o
      antigo, ou ``marcador_desconhecida`` (ex.: ``"[?]"``; ``{chave}`` no marcador vira o nome da variável);
    - ``escapar=True`` (padrão) protege o HTML do documento contra valores com marcação; o ``html`` do modelo em si
      NÃO é alterado (ele já é sanitizado ao salvar);
    - ``html`` ``None`` -> ``""``; ``contexto`` ``None`` -> sem valores.
    """
    if not html:
        return ""
    ctx = contexto or {}
    validas = _chaves_do_escopo(escopo)

    def troca(m: re.Match[str]) -> str:
        chave = m.group(1)
        if chave not in validas:
            if marcador_desconhecida is None:
                return m.group(0)
            return marcador_desconhecida.replace("{chave}", chave)
        try:
            bruto = ctx.get(chave)
        except Exception:  # noqa: BLE001 - mapeamentos exóticos não podem derrubar a renderização
            bruto = None
        texto = _como_texto(bruto)
        if texto == "":
            return ausente
        return escape(texto, quote=True) if escapar else texto

    return _PADRAO.sub(troca, str(html))


def chaves_faltando(contexto: Mapping[str, object] | None, html: str | None) -> list[str]:
    """Variáveis oficiais usadas no modelo que o contexto não preenche (para avisar antes de gerar o documento)."""
    ctx = contexto or {}
    return [c for c in variaveis_usadas(html) if c in CHAVES and ctx.get(c) in (None, "")]
