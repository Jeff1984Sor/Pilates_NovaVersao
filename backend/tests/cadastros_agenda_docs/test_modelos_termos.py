"""Termos de uso e modelos de contrato/evolução: sanitização (XSS), variáveis, prévia, duplicar, vínculos, auditoria."""

import pytest
from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.alunos.models import Aluno
from app.modules.cadastros import html_seguro
from app.modules.cadastros.models import ContadorCodigo, ModeloContrato, Plano, TermoUso, TipoServico

T = "/api/cadastros/termos"
M = "/api/cadastros/modelos"
MC = f"{M}/contrato"
ME = f"{M}/evolucao"

CONTRATO = "<h3>Contrato {CONTRATO_NUMERO}</h3><p>Aluno: <strong>{ALUNO_NOME}</strong> - {ALUNO_CPF}</p>"


def _acoes(db):
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id)) if not a.acao.startswith("auth.")]


# ------------------------------------------------------------------------------------------------ sanitização
ATAQUES = [
    "<script>alert(1)</script><p>ok</p>",
    '<p onclick="alert(1)">ok</p>',
    '<a href="javascript:alert(1)">x</a>',
    '<img src=x onerror="alert(1)">',
    '<img src="javascript:alert(1)">',
    "<iframe src='https://evil.example'></iframe><p>ok</p>",
    '<p style="position:fixed;top:0;background:url(javascript:alert(1))">ok</p>',
    '<svg onload="alert(1)"><circle/></svg><p>ok</p>',
    "<style>body{display:none}</style><p>ok</p>",
    '<form action="https://evil.example"><input name=cpf></form><p>ok</p>',
    '<object data="x"></object><embed src="x"><p>ok</p>',
    "<p>ok</p><!-- <script>alert(1)</script> -->",
    '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">x</a>',
    '<math><mi xlink:href="javascript:alert(1)">x</mi></math><p>ok</p>',
]


@pytest.mark.parametrize("ataque", ATAQUES)
def test_sanitizar_remove_codigo_ativo(ataque):
    limpo = html_seguro.sanitizar(ataque).lower()
    for perigo in ("<script", "onclick", "onerror", "onload", "javascript:", "<iframe", "<style", "<form", "<input", "<svg",
                   "<object", "<embed", "position", "data:text", "<!--", "<math", "url("):
        assert perigo not in limpo, (perigo, limpo)


def test_sanitizar_preserva_o_que_o_editor_gera_e_as_variaveis():
    html = (
        '<h2 style="text-align:center">Título</h2><p style="text-align: justify">Texto <strong>forte</strong>, <em>itálico</em>,'
        " <u>sub</u>, {ALUNO_NOME}.</p><ul><li>a</li></ul><ol><li>b</li></ol>"
        '<table border="1"><thead><tr><th>A</th></tr></thead><tbody><tr><td colspan="2">x</td></tr></tbody></table>'
        '<a href="https://exemplo.com.br/x">link</a><hr><blockquote>cit</blockquote>'
    )
    limpo = html_seguro.sanitizar(html)
    for parte in ("<h2", "text-align", "<strong>", "<em>", "<u>", "{ALUNO_NOME}", "<ul>", "<ol>", "<table", "<th>", 'colspan="2"',
                  'href="https://exemplo.com.br/x"', "<hr>", "<blockquote>"):
        assert parte in limpo, parte
    assert 'rel="' in limpo and "noopener" in limpo  # links externos não vazam o opener


def test_sanitizar_limites_e_vazio():
    assert html_seguro.sanitizar(None) == "" and html_seguro.sanitizar("") == ""
    with pytest.raises(html_seguro.HtmlGrandeDemais):
        html_seguro.sanitizar("a" * (html_seguro.TAMANHO_MAXIMO + 1))
    assert html_seguro.texto_puro("<p>Olá &amp; <b>mundo</b></p><script>x</script>") == "Olá & mundo"
    assert html_seguro.texto_puro("<p>" + "a" * 500 + "</p>", 20).endswith("…")


def test_api_sanitiza_ao_salvar_modelo_e_termo(client, full):
    r = client.post(MC, json={"nome": "Ataque", "conteudo_html": "<script>alert(1)</script><p onclick='x()'>{ALUNO_NOME}</p>"}, headers=full)
    assert r.status_code == 201, r.text
    assert "script" not in r.json()["conteudo_html"] and "onclick" not in r.json()["conteudo_html"]
    assert "{ALUNO_NOME}" in r.json()["conteudo_html"]
    r = client.post(T, json={"nome": "Ataque", "conteudo_html": '<img src=x onerror="alert(1)">Eu {ALUNO_NOME}'}, headers=full)
    assert r.status_code == 201 and "onerror" not in r.json()["conteudo_html"]


def test_api_recusa_texto_vazio_ou_so_script_e_texto_gigante(client, full):
    assert client.post(MC, json={"nome": "Vazio", "conteudo_html": "<script>x</script>"}, headers=full).status_code == 422
    assert client.post(MC, json={"nome": "Vazio", "conteudo_html": "<p> </p>"}, headers=full).status_code == 422
    assert client.post(MC, json={"nome": "Vazio", "conteudo_html": ""}, headers=full).status_code == 422
    r = client.post(MC, json={"nome": "Grande", "conteudo_html": "a" * (html_seguro.TAMANHO_MAXIMO + 1)}, headers=full)
    assert r.status_code == 422 and "grande demais" in r.json()["detail"]


# ------------------------------------------------------------------------------------------------ variáveis e prévia
def test_variaveis_oficiais_por_escopo(client, full):
    todas = client.get(f"{M}/variaveis", headers=full).json()
    assert len(todas) == 31 and todas[0] == {
        "chave": "ALUNO_NOME", "marcador": "{ALUNO_NOME}", "descricao": "Nome do aluno", "exemplo": "Maria da Silva Souza",
    }
    do_termo = client.get(f"{T}/variaveis", headers=full).json()
    assert len(do_termo) == 15 and "PLANO_NOME" not in {v["chave"] for v in do_termo}
    assert client.get(f"{M}/variaveis", params={"escopo": "termo"}, headers=full).json() == do_termo
    assert client.get(f"{M}/variaveis", params={"escopo": "x"}, headers=full).status_code == 422


def test_previa_do_contrato_com_dados_de_exemplo(client, full):
    r = client.post(f"{MC}/previa", json={"conteudo_html": CONTRATO + "{ALUNO_NOEM} <script>alert(1)</script>"}, headers=full)
    assert r.status_code == 200, r.text
    p = r.json()
    assert "Contrato 1024" in p["html"] and "<strong>Maria da Silva Souza</strong>" in p["html"] and "529.982.247-25" in p["html"]
    assert "<script" not in p["html"]
    assert p["desconhecidas"] == ["ALUNO_NOEM"] and p["usadas"] == ["CONTRATO_NUMERO", "ALUNO_NOME", "ALUNO_CPF", "ALUNO_NOEM"]
    assert "{ALUNO_NOEM}" in p["html"]  # desconhecida continua visível para quem edita


def test_previa_do_termo_nao_conhece_variaveis_de_contrato(client, full):
    r = client.post(f"{T}/previa", json={"conteudo_html": "<p>{ALUNO_NOME} {PLANO_NOME} {DATA_HOJE}</p>"}, headers=full).json()
    assert "Maria da Silva Souza" in r["html"] and "{PLANO_NOME}" in r["html"]
    assert r["desconhecidas"] == ["PLANO_NOME"]


def test_previa_nao_grava_nada(client, db, full):
    client.post(f"{MC}/previa", json={"conteudo_html": CONTRATO}, headers=full)
    client.post(f"{T}/previa", json={"conteudo_html": CONTRATO}, headers=full)
    assert db.scalars(select(ModeloContrato)).first() is None and db.scalars(select(TermoUso)).first() is None


# ------------------------------------------------------------------------------------------------ modelos de contrato
def test_crud_modelo_de_contrato(client, db, full):
    r = client.post(MC, json={"nome": "Contrato padrão", "conteudo_html": CONTRATO}, headers=full)
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["codigo"] == 1 and m["ativo"] is True and m["planos"] == 0
    assert m["variaveis_usadas"] == ["CONTRATO_NUMERO", "ALUNO_NOME", "ALUNO_CPF"] and m["variaveis_desconhecidas"] == []
    assert "Contrato" in m["previa"] and "<" not in m["previa"]
    assert db.get(ContadorCodigo, "modelo_contrato").ultimo == 1

    r = client.put(f"{MC}/{m['id']}", json={"nome": "Contrato 2026", "conteudo_html": CONTRATO + "{TIPO_SERVICO}", "ativo": False}, headers=full)
    assert r.status_code == 200 and r.json()["ativo"] is False and r.json()["nome"] == "Contrato 2026"
    assert client.patch(f"{MC}/{m['id']}/ativo", params={"ativo": True}, headers=full).json()["ativo"] is True
    assert client.get(f"{MC}/{m['id']}", headers=full).json()["conteudo_html"].endswith("{TIPO_SERVICO}")
    assert client.delete(f"{MC}/{m['id']}", headers=full).status_code == 200
    assert client.get(f"{MC}/{m['id']}", headers=full).status_code == 404
    assert _acoes(db) == ["modelo_contrato.criar", "modelo_contrato.alterar", "modelo_contrato.ativar", "modelo_contrato.excluir"]
    # a auditoria não guarda o HTML inteiro, só o tamanho
    criar = db.scalars(select(Auditoria).where(Auditoria.acao == "modelo_contrato.criar")).one()
    assert "conteudo_html" not in criar.depois_json and criar.depois_json["conteudo_html_tamanho"] > 0


def test_modelo_de_contrato_duplicar_gera_copia_inativa_com_nome_unico(client, db, full):
    m = client.post(MC, json={"nome": "Contrato padrão", "conteudo_html": CONTRATO}, headers=full).json()
    c1 = client.post(f"{MC}/{m['id']}/duplicar", headers=full)
    assert c1.status_code == 201, c1.text
    assert c1.json()["nome"] == "Contrato padrão (cópia)" and c1.json()["ativo"] is False
    assert c1.json()["conteudo_html"] == m["conteudo_html"] and c1.json()["codigo"] == 2 and c1.json()["id"] != m["id"]
    assert client.post(f"{MC}/{m['id']}/duplicar", headers=full).json()["nome"] == "Contrato padrão (cópia 2)"
    assert client.post(f"{MC}/{c1.json()['id']}/duplicar", headers=full).json()["nome"] == "Contrato padrão (cópia) (cópia)"
    assert client.post(f"{MC}/999/duplicar", headers=full).status_code == 404
    assert _acoes(db).count("modelo_contrato.duplicar") == 3


def test_duplicar_respeita_o_limite_do_nome(client, full):
    nome = "N" * 120
    m = client.post(MC, json={"nome": nome, "conteudo_html": CONTRATO}, headers=full).json()
    c = client.post(f"{MC}/{m['id']}/duplicar", headers=full).json()
    assert len(c["nome"]) <= 120 and c["nome"].endswith("(cópia)")


def test_modelo_de_contrato_nome_duplicado_e_lista(client, full):
    ids = {}
    for nome, ativo in (("Beta", True), ("Alfa", True), ("Gama", False)):
        ids[nome] = client.post(MC, json={"nome": nome, "conteudo_html": CONTRATO, "ativo": ativo}, headers=full).json()["id"]
    assert client.post(MC, json={"nome": "alfa", "conteudo_html": CONTRATO}, headers=full).status_code == 409
    lista = client.get(MC, headers=full).json()
    assert [i["nome"] for i in lista["itens"]] == ["Alfa", "Beta", "Gama"]
    assert lista["contagens"] == {"todos": 3, "ativos": 2, "inativos": 1}
    assert "conteudo_html" not in lista["itens"][0]  # a lista é leve
    assert [i["nome"] for i in client.get(MC, params={"situacao": "inativos"}, headers=full).json()["itens"]] == ["Gama"]
    assert client.get(MC, params={"situacao": "inativos"}, headers=full).json()["contagens"]["todos"] == 3
    assert [i["nome"] for i in client.get(MC, params={"q": "bet"}, headers=full).json()["itens"]] == ["Beta"]
    assert [i["nome"] for i in client.get(MC, params={"ordenar": "nome", "direcao": "desc", "por_pagina": 1}, headers=full).json()["itens"]] == ["Gama"]


def test_modelo_de_contrato_em_uso_por_plano_nao_e_excluido(client, db, full):
    m = client.post(MC, json={"nome": "Em uso", "conteudo_html": CONTRATO}, headers=full).json()
    srv = TipoServico(nome="Pilates")
    db.add(srv)
    db.flush()
    db.add(Plano(nome="2x", tipo_servico_id=srv.id, modelo_contrato_id=m["id"]))
    db.commit()
    r = client.delete(f"{MC}/{m['id']}", headers=full)
    assert r.status_code == 409 and "1 plano" in r.json()["detail"] and "inative" in r.json()["detail"]
    assert client.get(f"{MC}/{m['id']}", headers=full).json()["planos"] == 1
    assert client.get(MC, headers=full).json()["itens"][0]["planos"] == 1
    assert "modelo_contrato.excluir" not in _acoes(db)


# ------------------------------------------------------------------------------------------------ termos
def test_crud_termo_com_aviso_de_variavel_de_contrato(client, db, full):
    corpo = {"nome": "Termo de imagem", "conteudo_html": "<p>Eu {ALUNO_NOME}, CPF {ALUNO_CPF}, autorizo. {PLANO_NOME}</p>"}
    r = client.post(T, json=corpo, headers=full)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["codigo"] == 1 and t["alunos_com_aceite"] == 0
    assert t["variaveis_desconhecidas"] == ["PLANO_NOME"]  # o termo não conhece variáveis de contrato
    assert client.put(f"{T}/{t['id']}", json={**corpo, "nome": "Termo 2026"}, headers=full).json()["nome"] == "Termo 2026"
    assert client.post(T, json={**corpo, "nome": "termo 2026"}, headers=full).status_code == 409
    assert client.post(T, json={**corpo, "nome": "x" * 81}, headers=full).status_code == 422
    assert client.delete(f"{T}/{t['id']}", headers=full).status_code == 200
    assert _acoes(db) == ["termo.criar", "termo.alterar", "termo.excluir"]
    assert db.get(ContadorCodigo, "termo_uso").ultimo == 1


def test_termo_duplicar_e_listar(client, full):
    t = client.post(T, json={"nome": "Termo A", "conteudo_html": "<p>{ALUNO_NOME}</p>"}, headers=full).json()
    c = client.post(f"{T}/{t['id']}/duplicar", headers=full).json()
    assert c["nome"] == "Termo A (cópia)" and c["conteudo_html"] == t["conteudo_html"] and c["id"] != t["id"]
    lista = client.get(T, headers=full).json()
    assert [i["nome"] for i in lista["itens"]] == ["Termo A", "Termo A (cópia)"] and lista["total"] == 2
    assert [i["nome"] for i in client.get(T, params={"q": "cópia"}, headers=full).json()["itens"]] == ["Termo A (cópia)"]


def test_termo_com_aceite_de_aluno_nao_e_excluido(client, db, full, base):
    t = client.post(T, json={"nome": "Termo A", "conteudo_html": "<p>{ALUNO_NOME}</p>"}, headers=full).json()
    aluno = Aluno(nome="Aluna Teste", sem_cpf=True, unidade_id=base["unidade"], termo_uso_id=t["id"])
    db.add(aluno)
    db.commit()
    r = client.delete(f"{T}/{t['id']}", headers=full)
    assert r.status_code == 409 and "1 aluno aceitou" in r.json()["detail"]
    assert client.get(T, headers=full).json()["itens"][0]["alunos_com_aceite"] == 1


# ------------------------------------------------------------------------------------------------ modelos de evolução
def test_crud_modelo_de_evolucao(client, db, full):
    r = client.post(ME, json={"titulo": "Evolução padrão", "texto": "Aluno realizou os exercícios sem queixas."}, headers=full)
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["codigo"] == 1 and m["ativo"] is True
    r = client.put(f"{ME}/{m['id']}", json={"titulo": "Evolução padrão", "texto": "Texto novo", "ativo": False}, headers=full)
    assert r.json()["texto"] == "Texto novo" and r.json()["ativo"] is False
    assert client.patch(f"{ME}/{m['id']}/ativo", params={"ativo": True}, headers=full).json()["ativo"] is True
    assert client.get(f"{ME}/{m['id']}", headers=full).json()["titulo"] == "Evolução padrão"
    assert client.post(ME, json={"titulo": "evolução PADRÃO", "texto": "x"}, headers=full).status_code == 409
    assert client.post(ME, json={"titulo": "Vazio", "texto": ""}, headers=full).status_code == 422
    assert client.post(ME, json={"titulo": "Só espaço", "texto": "   "}, headers=full).status_code == 422
    assert client.delete(f"{ME}/{m['id']}", headers=full).status_code == 200
    assert client.get(f"{ME}/{m['id']}", headers=full).status_code == 404
    assert _acoes(db) == ["modelo_evolucao.criar", "modelo_evolucao.alterar", "modelo_evolucao.ativar", "modelo_evolucao.excluir"]


def test_modelo_de_evolucao_guarda_texto_simples(client, full):
    r = client.post(ME, json={"titulo": "Com marcação", "texto": "<b>Dor</b> lombar <script>alert(1)</script>reduziu"}, headers=full)
    assert r.status_code == 201 and "<" not in r.json()["texto"] and "alert" not in r.json()["texto"]
    assert r.json()["texto"] == "Dor lombar reduziu"


def test_lista_de_evolucao_busca_chips_e_ativos_para_a_gaveta(client, full):
    client.post(ME, json={"titulo": "Coluna", "texto": "Trabalho de mobilidade da coluna"}, headers=full)
    client.post(ME, json={"titulo": "Ombro", "texto": "Fortalecimento do manguito", "ativo": False}, headers=full)
    lista = client.get(ME, headers=full).json()
    assert [i["titulo"] for i in lista["itens"]] == ["Coluna", "Ombro"]
    assert lista["contagens"] == {"todos": 2, "ativos": 1, "inativos": 1}
    assert [i["titulo"] for i in client.get(ME, params={"q": "manguito"}, headers=full).json()["itens"]] == ["Ombro"]
    assert [i["titulo"] for i in client.get(ME, params={"situacao": "ativos"}, headers=full).json()["itens"]] == ["Coluna"]
    gaveta = client.get(f"{ME}/ativos", headers=full).json()
    assert [i["titulo"] for i in gaveta] == ["Coluna"] and set(gaveta[0]) == {"id", "titulo", "texto"}
