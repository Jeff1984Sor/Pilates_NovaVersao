"""PDF do contrato (e do termo de imagem) a partir do HTML do modelo, com reportlab.

O HTML chega JÁ renderizado (`domain.modelos_documento.renderizar`, valores escapados) e sanitizado (allowlist de
`cadastros/html_seguro.py`). Este módulo converte esse subconjunto para o PDF:

- títulos `h1`..`h6`, parágrafos/`div`/`blockquote`, `br`, `hr`;
- negrito, itálico, sublinhado, tachado, sobrescrito/subscrito, `small`, links (o texto, com o endereço entre parênteses);
- alinhamento (`text-align`) e recuo simples;
- listas `ul`/`ol` (aninhadas), tabelas simples (`colspan`, grade fina);
- quebra de página: `page-break-before/after: always` no estilo OU um parágrafo só com `{QUEBRA_DE_PAGINA}`;
- assinatura embutida (imagem PNG + nome, documento, data e IP) quando o contrato está assinado;
- rodapé com a identidade do estúdio (nome) e o número da página.

Nunca lê o relógio, o banco nem o storage: quem chama passa tudo (`DadosPdf`). Imagens (assinatura, logo) que o
reportlab não consegue abrir são ignoradas em silêncio, o texto do contrato nunca deixa de sair.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

MARCADOR_QUEBRA = "{QUEBRA_DE_PAGINA}"
_VOID = {"br", "hr", "img", "col"}
_BLOCOS = {"p", "div", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "hr", "caption"}
_INLINE_MARCAS = {
    "strong": ("<b>", "</b>"), "b": ("<b>", "</b>"),
    "em": ("<i>", "</i>"), "i": ("<i>", "</i>"),
    "u": ("<u>", "</u>"),
    "s": ("<strike>", "</strike>"), "strike": ("<strike>", "</strike>"),
    "sub": ("<sub>", "</sub>"), "sup": ("<super>", "</super>"),
    "small": ('<font size="8">', "</font>"),
}
_ALINHAMENTOS = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}
_ESPACOS = re.compile(r"\s+")
_ESTILO_ITEM = re.compile(r"\s*([a-z-]+)\s*:\s*([^;]+)")


@dataclass
class Assinatura:
    nome: str
    documento: str | None
    assinado_em: datetime | None
    ip: str | None
    metodo: str  # "digital" (link) ou "local" (recepção)
    imagem_png: bytes | None = None


@dataclass
class DadosPdf:
    titulo: str
    html: str
    estudio_nome: str
    rodape_extra: str | None = None  # ex.: "Contrato nº 12"
    logo: bytes | None = None
    assinatura: Assinatura | None = None
    comprimir: bool = True


# ----------------------------------------------------------------------------------------------- árvore HTML mínima
class _No:
    __slots__ = ("tag", "attrs", "filhos", "texto")

    def __init__(self, tag: str | None, attrs: dict[str, str] | None = None, texto: str | None = None):
        self.tag = tag  # None = nó de texto
        self.attrs = attrs or {}
        self.filhos: list[_No] = []
        self.texto = texto

    def estilo(self) -> dict[str, str]:
        return {m.group(1).lower(): m.group(2).strip().lower() for m in _ESTILO_ITEM.finditer(self.attrs.get("style", ""))}


class _Arvore(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raiz = _No("raiz")
        self._pilha = [self.raiz]

    def handle_starttag(self, tag, attrs):
        no = _No(tag, {k: (v or "") for k, v in attrs})
        self._pilha[-1].filhos.append(no)
        if tag not in _VOID:
            self._pilha.append(no)

    def handle_startendtag(self, tag, attrs):
        self._pilha[-1].filhos.append(_No(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        for i in range(len(self._pilha) - 1, 0, -1):
            if self._pilha[i].tag == tag:
                del self._pilha[i:]
                return

    def handle_data(self, data):
        self._pilha[-1].filhos.append(_No(None, texto=data))


def _arvore(html: str) -> _No:
    p = _Arvore()
    p.feed(html or "")
    p.close()
    return p.raiz


# --------------------------------------------------------------------------------------------------------- estilos
def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    normal = ParagraphStyle("Corpo", parent=base["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14.5,
                            spaceAfter=6, alignment=TA_JUSTIFY)
    est = {"p": normal}
    tamanhos = {"h1": 17, "h2": 15, "h3": 13, "h4": 12, "h5": 11, "h6": 10.5}
    for tag, tam in tamanhos.items():
        est[tag] = ParagraphStyle(tag, parent=normal, fontName="Helvetica-Bold", fontSize=tam, leading=tam + 4,
                                  spaceBefore=8, spaceAfter=6, alignment=TA_LEFT, keepWithNext=1)
    est["blockquote"] = ParagraphStyle("bq", parent=normal, leftIndent=14, textColor=colors.HexColor("#444444"))
    est["celula"] = ParagraphStyle("celula", parent=normal, fontSize=9.5, leading=12, spaceAfter=0, alignment=TA_LEFT)
    est["celula_th"] = ParagraphStyle("celula_th", parent=est["celula"], fontName="Helvetica-Bold")
    est["item"] = ParagraphStyle("item", parent=normal, spaceAfter=2)
    return est


# ------------------------------------------------------------------------------------------------------- conversão
class _Conversor:
    def __init__(self) -> None:
        self.est = _estilos()

    # --- inline -> markup do reportlab
    def _inline(self, no: _No) -> str:
        if no.tag is None:
            return xml_escape(no.texto or "")
        if no.tag == "br":
            return "<br/>"
        if no.tag == "img":
            return ""
        miolo = "".join(self._inline(f) for f in no.filhos)
        if no.tag == "a":
            href = no.attrs.get("href", "")
            if href.startswith(("http://", "https://", "mailto:", "tel:")):
                visivel = xml_escape(unescape(href))
                return f"{miolo} ({visivel})" if href not in miolo else miolo
            return miolo
        marcas = _INLINE_MARCAS.get(no.tag or "")
        est = no.estilo()
        pre, pos = marcas if marcas else ("", "")
        if est.get("font-weight") in ("bold", "700", "800", "900") and "<b>" not in pre:
            pre, pos = pre + "<b>", "</b>" + pos
        if est.get("font-style") == "italic" and "<i>" not in pre:
            pre, pos = pre + "<i>", "</i>" + pos
        if "underline" in est.get("text-decoration", "") and "<u>" not in pre:
            pre, pos = pre + "<u>", "</u>" + pos
        if "line-through" in est.get("text-decoration", "") and "<strike>" not in pre:
            pre, pos = pre + "<strike>", "</strike>" + pos
        return f"{pre}{miolo}{pos}"

    @staticmethod
    def _limpar(markup: str) -> str:
        # o HTML do editor tem quebras de linha/identação que não contam: espaços em sequência viram um
        return _ESPACOS.sub(" ", markup.replace("\xa0", " ")).strip()

    def _estilo_para(self, no: _No, nome: str) -> ParagraphStyle:
        base = self.est.get(nome, self.est["p"])
        est = no.estilo()
        extra: dict = {}
        alinhamento = est.get("text-align") or no.attrs.get("align", "").lower()
        if alinhamento in _ALINHAMENTOS:
            extra["alignment"] = _ALINHAMENTOS[alinhamento]
        margem = est.get("margin-left") or est.get("padding-left")
        if margem:
            m = re.match(r"([\d.]+)(px|pt|em|rem)?", margem)
            if m:
                valor = float(m.group(1))
                extra["leftIndent"] = min(valor * (12 if m.group(2) in ("em", "rem") else 0.75), 120)
        if est.get("text-indent"):
            m = re.match(r"([\d.]+)", est["text-indent"])
            if m:
                extra["firstLineIndent"] = min(float(m.group(1)) * 0.75, 60)
        return ParagraphStyle(f"{nome}_x", parent=base, **extra) if extra else base

    # --- blocos
    def blocos(self, filhos: list[_No], estilo_base: str = "p") -> list:
        """Converte uma lista de nós em flowables. Texto solto e inline vizinhos viram um parágrafo só."""
        saida: list = []
        buffer: list[_No] = []

        def esvaziar() -> None:
            if not buffer:
                return
            markup = self._limpar("".join(self._inline(n) for n in buffer))
            buffer.clear()
            if markup:
                saida.append(Paragraph(markup, self.est[estilo_base]))

        for no in filhos:
            if no.tag is None or no.tag not in _BLOCOS:
                if no.tag in ("script", "style"):
                    continue
                buffer.append(no)
                continue
            esvaziar()
            saida.extend(self._bloco(no, estilo_base))
        esvaziar()
        return saida

    def _quebra(self, no: _No, qual: str) -> bool:
        est = no.estilo()
        return est.get(f"page-break-{qual}") == "always" or est.get(f"break-{qual}") == "page"

    def _bloco(self, no: _No, estilo_base: str) -> list:
        tag = no.tag
        saida: list = []
        if self._quebra(no, "before"):
            saida.append(PageBreak())
        if tag == "hr":
            saida.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#999999"), spaceBefore=4, spaceAfter=8))
        elif tag in ("ul", "ol"):
            saida.append(self._lista(no))
        elif tag == "table":
            tabela = self._tabela(no)
            if tabela is not None:
                saida.append(tabela)
                saida.append(Spacer(1, 6))
        elif tag in ("div", "blockquote") and any((f.tag in _BLOCOS) for f in no.filhos):
            interno = self.blocos(no.filhos, "blockquote" if tag == "blockquote" else estilo_base)
            saida.extend(interno)
        elif tag == "li":
            saida.extend(self.blocos(no.filhos, "item"))
        else:
            nome = tag if tag in self.est else ("blockquote" if tag == "blockquote" else "p")
            markup = self._limpar("".join(self._inline(f) for f in no.filhos))
            if markup == xml_escape(MARCADOR_QUEBRA):
                saida.append(PageBreak())
            elif markup:
                saida.append(Paragraph(markup, self._estilo_para(no, nome)))
            elif tag == "p":
                saida.append(Spacer(1, 6))
        if self._quebra(no, "after"):
            saida.append(PageBreak())
        return saida

    def _lista(self, no: _No) -> ListFlowable:
        ordenada = no.tag == "ol"
        itens = []
        for filho in no.filhos:
            if filho.tag != "li":
                continue
            conteudo = self.blocos(filho.filhos, "item") or [Paragraph("", self.est["item"])]
            itens.append(ListItem(conteudo, leftIndent=18))
        try:
            inicio = int(no.attrs.get("start", "1"))
        except ValueError:
            inicio = 1
        return ListFlowable(
            itens or [ListItem(Paragraph("", self.est["item"]))],
            bulletType="1" if ordenada else "bullet",
            start=inicio if ordenada else "•",
            leftIndent=18,
            bulletFontSize=10,
            spaceAfter=6,
        )

    def _tabela(self, no: _No) -> Table | None:
        linhas: list[tuple[list[_No], bool]] = []

        def coletar(n: _No) -> None:
            for f in n.filhos:
                if f.tag == "tr":
                    celulas = [c for c in f.filhos if c.tag in ("td", "th")]
                    if celulas:
                        linhas.append((celulas, all(c.tag == "th" for c in celulas)))
                elif f.tag in ("thead", "tbody", "tfoot"):
                    coletar(f)

        coletar(no)
        if not linhas:
            return None
        n_cols = max(sum(max(int(c.attrs.get("colspan", "1") or 1), 1) for c in cs) for cs, _ in linhas)
        dados: list[list] = []
        spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for r, (celulas, eh_cab) in enumerate(linhas):
            linha: list = []
            for c in celulas:
                estilo = self.est["celula_th"] if (c.tag == "th" or eh_cab) else self.est["celula"]
                partes = self.blocos(c.filhos, "celula_th" if c.tag == "th" else "celula")
                linha.append(partes or Paragraph("", estilo))
                try:
                    ncol = max(int(c.attrs.get("colspan", "1") or 1), 1)
                except ValueError:
                    ncol = 1
                if ncol > 1:
                    col = len(linha) - 1
                    spans.append(((col, r), (col + ncol - 1, r)))
                    linha.extend([""] * (ncol - 1))
            linha.extend([""] * (n_cols - len(linha)))
            dados.append(linha)
        largura = A4[0] - 40 * mm
        tabela = Table(dados, colWidths=[largura / n_cols] * n_cols, repeatRows=0, hAlign="LEFT")
        estilo = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        # contrato precisa de tabela legível: sempre com grade fina (o editor nem sempre grava a borda)
        estilo.append(("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")))
        for r, (_, eh_cab) in enumerate(linhas):
            if eh_cab:
                estilo.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#EEEEEE")))
        for ini, fim in spans:
            estilo.append(("SPAN", ini, fim))
        tabela.setStyle(TableStyle(estilo))
        return tabela


def html_para_flowables(html: str) -> list:
    return _Conversor().blocos(_arvore(html).filhos)


# ----------------------------------------------------------------------------------------------------- assinatura
def _bloco_assinatura(a: Assinatura, est: dict[str, ParagraphStyle]) -> list:
    metodo = "assinado digitalmente por link" if a.metodo == "digital" else "assinado na recepção do estúdio"
    quando = a.assinado_em.strftime("%d/%m/%Y às %H:%M") if a.assinado_em else ""
    linhas = [f"<b>{xml_escape(a.nome)}</b>"]
    if a.documento:
        linhas.append(f"Documento: {xml_escape(a.documento)}")
    linhas.append(f"Contrato {metodo}" + (f" em {quando}" if quando else ""))
    if a.ip:
        linhas.append(f"IP de origem: {xml_escape(a.ip)}")
    pequeno = ParagraphStyle("assin", parent=est["p"], fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=2)
    itens: list = [Spacer(1, 10), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#999999"))]
    if a.imagem_png:
        try:
            img = Image(io.BytesIO(a.imagem_png))
            maxw, maxh = 70 * mm, 28 * mm
            esc = min(maxw / img.imageWidth, maxh / img.imageHeight, 1.0)
            img.drawWidth, img.drawHeight = img.imageWidth * esc, img.imageHeight * esc
            img.hAlign = "LEFT"
            itens.append(img)
        except Exception:  # noqa: BLE001 - imagem ilegível: o texto da assinatura continua valendo
            pass
    itens.extend(Paragraph(t, pequeno) for t in linhas)
    return [KeepTogether(itens)]


# ------------------------------------------------------------------------------------------------------- documento
def _rodape(estudio: str, extra: str | None):
    def desenhar(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
        canvas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
        texto = estudio + (f" · {extra}" if extra else "")
        canvas.drawString(20 * mm, 10 * mm, texto[:110])
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    return desenhar


def gerar_pdf(d: DadosPdf) -> bytes:
    """PDF (bytes) do documento. Sempre devolve um PDF válido, mesmo para HTML vazio."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
        title=d.titulo, author=d.estudio_nome, pageCompression=1 if d.comprimir else 0,
    )
    conv = _Conversor()
    historia: list = []
    cab = ParagraphStyle("cab", parent=conv.est["p"], fontName="Helvetica-Bold", fontSize=12, alignment=TA_LEFT, spaceAfter=2)
    if d.logo:
        try:
            logo = Image(io.BytesIO(d.logo))
            esc = min((14 * mm) / logo.imageHeight, (50 * mm) / logo.imageWidth, 1.0)
            logo.drawWidth, logo.drawHeight = logo.imageWidth * esc, logo.imageHeight * esc
            logo.hAlign = "LEFT"
            historia.append(logo)
        except Exception:  # noqa: BLE001 - formato que o reportlab não lê (ex.: WEBP): segue só com o nome
            pass
    historia.append(Paragraph(xml_escape(d.estudio_nome), cab))
    historia.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#6B1F3A"), spaceAfter=8))
    corpo = conv.blocos(_arvore(d.html).filhos)
    historia.extend(corpo or [Paragraph(xml_escape(d.titulo), conv.est["h3"])])
    if d.assinatura:
        historia.extend(_bloco_assinatura(d.assinatura, conv.est))
    rodape = _rodape(d.estudio_nome, d.rodape_extra)
    doc.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
