"""PDF do contrato: abre, contém o texto (títulos, parágrafos, negrito/itálico, listas, tabela, quebra de página, assinatura, rodapé)."""

import re
from datetime import datetime, UTC

from app.modules.contratos import pdf
from tests.contratos.conftest import cabecalho, png_data_url

import base64


def texto_bruto(b: bytes) -> str:
    """Texto desenhado no PDF (sem compressão): junta os `(...) Tj`, desfaz escapes e octais do reportlab (WinAnsi)."""
    saida = []
    for m in re.finditer(rb"\(((?:\\.|[^\\)])*)\) Tj", b):
        bruto = m.group(1)
        bruto = re.sub(rb"\\([0-7]{3})", lambda o: bytes([int(o.group(1), 8)]), bruto)
        bruto = re.sub(rb"\\(.)", rb"\1", bruto)
        saida.append(bruto.decode("cp1252", "replace"))
    return b.decode("latin-1") + chr(10) + "".join(saida)


def paginas(b: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b", b))


def dados(html, **extra) -> pdf.DadosPdf:
    return pdf.DadosPdf(titulo="Contrato 7", html=html, estudio_nome="Studio Mayris", rodape_extra="Contrato nº 7", comprimir=False, **extra)


def test_pdf_basico_abre_e_tem_o_texto():
    b = pdf.gerar_pdf(dados("<h2>CONTRATO DE PRESTACAO</h2><p>Aluna <strong>Maria</strong> e <em>Souza</em> contratam.</p>"))
    assert b.startswith(b"%PDF") and b.rstrip().endswith(b"%%EOF")
    t = texto_bruto(b)
    for trecho in ("CONTRATO DE PRESTACAO", "Maria", "Souza", "contratam", "Studio Mayris", "Contrato n"):
        assert trecho in t, trecho
    assert "Helvetica-Bold" in t and "Helvetica-Oblique" in t  # negrito e itálico
    assert paginas(b) == 1


def test_pdf_comprimido_tambem_e_valido():
    b = pdf.gerar_pdf(pdf.DadosPdf(titulo="x", html="<p>ola</p>", estudio_nome="Studio"))
    assert b.startswith(b"%PDF") and b.rstrip().endswith(b"%%EOF")


def test_listas_tabela_e_hr():
    html = ("<ul><li>Primeiro item</li><li>Segundo item<ul><li>Subitem aninhado</li></ul></li></ul>"
            "<ol><li>Passo um</li><li>Passo dois</li></ol><hr>"
            "<table><tr><th>Parcela</th><th>Valor</th></tr><tr><td>Primeira</td><td>R$ 300,00</td></tr>"
            "<tr><td colspan=\"2\">Linha mesclada</td></tr></table>")
    t = texto_bruto(pdf.gerar_pdf(dados(html)))
    for trecho in ("Primeiro item", "Segundo item", "Subitem aninhado", "Passo um", "Passo dois", "Parcela", "Primeira", "300,00", "Linha mesclada"):
        assert trecho in t, trecho


def test_quebra_de_pagina_por_estilo_e_por_marcador():
    um = pdf.gerar_pdf(dados("<p>Pagina A</p><p>Pagina B</p>"))
    assert paginas(um) == 1
    por_estilo = pdf.gerar_pdf(dados("<p>Pagina A</p><div style=\"page-break-after: always\"></div><p>Pagina B</p>"))
    por_marcador = pdf.gerar_pdf(dados("<p>Pagina A</p><p>{QUEBRA_DE_PAGINA}</p><p>Pagina B</p>"))
    assert paginas(por_estilo) == 2 and paginas(por_marcador) == 2
    assert "Pagina B" in texto_bruto(por_marcador) and "QUEBRA" not in texto_bruto(por_marcador)


def test_texto_longo_vira_varias_paginas():
    html = "".join(f"<p>Clausula {i}. " + "Texto de preenchimento do contrato. " * 12 + "</p>" for i in range(60))
    b = pdf.gerar_pdf(dados(html))
    assert paginas(b) >= 3 and "Clausula 59" in texto_bruto(b)
    assert "Página 2" in texto_bruto(b)  # rodapé numerado


def test_html_hostil_ou_vazio_nao_quebra():
    assert pdf.gerar_pdf(dados("")).startswith(b"%PDF")
    b = pdf.gerar_pdf(dados("<p>&lt;script&gt;alert(1)&lt;/script&gt; <b>negrito sem fechar<p>outro <unknown>x</unknown></p><table></table><ul></ul>"))
    assert b.startswith(b"%PDF") and "alert(1)" in texto_bruto(b)


def test_assinatura_embutida_so_quando_assinado():
    png = base64.b64decode(png_data_url().split(",", 1)[1])
    sem = texto_bruto(pdf.gerar_pdf(dados("<p>Contrato</p>")))
    assert "assinado digitalmente" not in sem
    ass = pdf.Assinatura(nome="Maria da Silva Souza", documento="529.982.247-25", assinado_em=datetime(2026, 11, 3, 14, 30, tzinfo=UTC),
                         ip="203.0.113.7", metodo="digital", imagem_png=png)
    com = pdf.gerar_pdf(dados("<p>Contrato</p>", assinatura=ass))
    t = texto_bruto(com)
    assert "Maria da Silva Souza" in t and "529.982.247-25" in t and "203.0.113.7" in t and "assinado digitalmente" in t and "03/11/2026" in t
    assert b"/Subtype /Image" in com
    local = texto_bruto(pdf.gerar_pdf(dados("<p>x</p>", assinatura=pdf.Assinatura("Ana", None, None, None, "local", None))))
    assert "assinado na recep" in local


def test_imagem_invalida_nao_derruba_o_pdf():
    ass = pdf.Assinatura("Ana", None, None, None, "local", b"isto nao e um png")
    b = pdf.gerar_pdf(dados("<p>x</p>", assinatura=ass, logo=b"lixo"))
    assert b.startswith(b"%PDF")


# ------------------------------------------------------------------------------------- integração com o contrato
def test_pdf_do_contrato_usa_o_modelo_do_plano_e_escapa_valores(client, full, db, cen, novo_contrato):
    cen.aluno.nome = "Maria <b>Hacker</b> & Cia"
    db.commit()
    cid = novo_contrato()["contrato"]["id"]
    r = client.get(f"/api/contratos/{cid}/pdf", headers=cabecalho(full))
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    from app.modules.contratos import servico
    from app.modules.contratos.models import Contrato

    b = servico.gerar_pdf_do_contrato(db, db.get(Contrato, cid), comprimir=False)
    t = texto_bruto(b)
    assert "CONTRATO N" in t and "Pilates 2x" in t and "R$ 300,00" in t and "R$ 900,00" in t
    assert "02/11/2026" in t and "01/02/2027" in t and "529.982.247-25" not in t  # cpf do outro aluno de teste não aparece
    assert "<b>Hacker</b> & Cia" in t  # o texto aparece literal: nunca vira negrito de verdade


def test_sem_modelo_no_plano_usa_o_contrato_padrao(client, full, db, cen, novo_contrato):
    cen.plano.modelo_contrato_id = None
    db.commit()
    cid = novo_contrato()["contrato"]["id"]
    from app.modules.contratos import servico
    from app.modules.contratos.models import Contrato

    t = texto_bruto(servico.gerar_pdf_do_contrato(db, db.get(Contrato, cid), comprimir=False))
    assert "Valor parcela" in t and "R$ 300,00" in t


def test_pdf_exige_login_e_permissao(client, professor, cen, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    assert client.get(f"/api/contratos/{cid}/pdf").status_code == 401
    assert client.get(f"/api/contratos/{cid}/pdf", headers=cabecalho(professor)).status_code == 403
