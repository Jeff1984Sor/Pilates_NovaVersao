"""Sanitização do HTML dos modelos de contrato e termo (allowlist de tags, atributos e propriedades de estilo).

O editor do frontend é um `contenteditable`; tudo o que ele produz passa por aqui ANTES de ir ao banco, e o
documento final (contrato/termo exibido ao aluno, PDF) só contém o que está nesta lista. O que não está na lista
é removido (o texto interno é mantido; `<script>`, `<style>` e comentários somem com o conteúdo).
"""

from __future__ import annotations

import html as _html
import re

import nh3

TAMANHO_MAXIMO = 300_000  # caracteres; um contrato longo tem poucas dezenas de milhares

TAGS = {
    "p", "br", "hr", "div", "span", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup", "small",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "a", "img",
}

ATRIBUTOS = {
    "*": {"style"},
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "col": {"span", "width"},
    "ol": {"start", "type"},
    "table": {"border", "cellpadding", "cellspacing", "width"},
}

#: propriedades CSS que o editor gera (alinhamento, ênfase, tabela simples); o resto (position, url(), etc.) cai
ESTILOS = {
    "text-align", "font-weight", "font-style", "text-decoration", "text-indent",
    "margin-left", "margin-top", "margin-bottom", "padding", "padding-left",
    "width", "height", "border", "border-collapse", "border-top", "border-bottom", "border-left", "border-right",
    "vertical-align", "list-style-type", "line-height", "color", "font-size",
}

ESQUEMAS_URL = {"http", "https", "mailto", "tel"}

_TAGS_FORA_COM_CONTEUDO = {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math"}
_ESPACOS = re.compile(r"\s+")


class HtmlGrandeDemais(ValueError):
    pass


def sanitizar(html: str | None) -> str:
    """HTML seguro para guardar e exibir. `None`/vazio -> `""`. Levanta `HtmlGrandeDemais` acima do limite."""
    if not html:
        return ""
    if len(html) > TAMANHO_MAXIMO:
        raise HtmlGrandeDemais(f"O texto é grande demais (máximo de {TAMANHO_MAXIMO:,} caracteres).".replace(",", "."))
    return nh3.clean(
        html,
        tags=TAGS,
        clean_content_tags=_TAGS_FORA_COM_CONTEUDO,
        attributes=ATRIBUTOS,
        filter_style_properties=ESTILOS,
        url_schemes=ESQUEMAS_URL,
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    ).strip()


def texto_puro(html: str | None, limite: int = 160) -> str:
    """Resumo em texto corrido (para a coluna "prévia" das listas)."""
    if not html:
        return ""
    sem_tags = nh3.clean(html, tags=set(), clean_content_tags=_TAGS_FORA_COM_CONTEUDO)
    texto = _ESPACOS.sub(" ", _html.unescape(sem_tags)).strip()
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"
