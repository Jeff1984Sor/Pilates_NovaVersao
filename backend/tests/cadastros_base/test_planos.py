from datetime import date
from decimal import Decimal

import pytest

from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import (
    Categoria,
    ModeloContrato,
    Plano,
    Profissional,
    Subcategoria,
    TipoCategoria,
    TipoServico,
    Unidade,
)
from app.modules.contratos.models import Contrato
from tests.cadastros_base.conftest import auditorias

PL = "/api/planos"


@pytest.fixture
def base(db):
    ts = TipoServico(nome="Pilates")
    ts2 = TipoServico(nome="Fisioterapia")
    cr = Categoria(nome="Mensalidades", tipo=TipoCategoria.RECEITA)
    cd = Categoria(nome="Aluguel", tipo=TipoCategoria.DESPESA)
    db.add_all([ts, ts2, cr, cd])
    db.flush()
    sr = Subcategoria(categoria_id=cr.id, nome="Pilates mensal")
    sd = Subcategoria(categoria_id=cd.id, nome="Sala")
    mc = ModeloContrato(nome="Contrato padrão", conteudo_html="<p>x</p>")
    db.add_all([sr, sd, mc])
    db.commit()
    return {"ts": ts.id, "ts2": ts2.id, "cr": cr.id, "cd": cd.id, "sr": sr.id, "sd": sd.id, "mc": mc.id}


def corpo(base, **extra):
    c = {"nome": "Pilates 2x", "tipo_servico_id": base["ts"], "valor": "300.00", "aulas_por_semana": 2, "duracao_meses": 3}
    c.update(extra)
    return c


def test_plano_crud_com_valor_por_aula_r1(client, db, h_full, base):
    r = client.post(PL, headers=h_full, json=corpo(base, categoria_receita_id=base["cr"], subcategoria_receita_id=base["sr"],
                                                   modelo_contrato_id=base["mc"]))
    assert r.status_code == 201, r.text
    p = r.json()
    # caso numérico da R1: 300,00 / 2x por semana / 3 meses -> aula 37,50, total 900,00
    assert Decimal(p["valor_aula"]) == Decimal("37.50") and Decimal(p["valor_total"]) == Decimal("900.00")
    assert p["tipo_servico_nome"] == "Pilates" and p["categoria_receita_nome"] == "Mensalidades"
    assert p["subcategoria_receita_nome"] == "Pilates mensal" and p["modelo_contrato_nome"] == "Contrato padrão"
    assert p["codigo"] == 1 and p["is_avulso"] is False and p["recorrencia"] == "MENSAL"

    r = client.put(f"{PL}/{p['id']}", headers=h_full, json=corpo(base, nome="Pilates 3x", aulas_por_semana=3, valor="350.00"))
    assert r.status_code == 200
    assert Decimal(r.json()["valor_aula"]) == Decimal("29.17")  # 350 / 12 arredondado meio para cima
    assert r.json()["categoria_receita_id"] is None  # o PUT substitui o cadastro inteiro

    assert client.get(f"{PL}/{p['id']}", headers=h_full).json()["nome"] == "Pilates 3x"
    assert client.delete(f"{PL}/{p['id']}", headers=h_full).status_code == 200
    assert client.get(f"{PL}/{p['id']}", headers=h_full).status_code == 404
    for acao in ("plano.criar", "plano.alterar", "plano.excluir"):
        assert auditorias(db, acao), acao


def test_plano_sem_aulas_por_semana_nao_tem_valor_por_aula(client, h_full, base):
    r = client.post(PL, headers=h_full, json=corpo(base, nome="Livre", aulas_por_semana=0))
    assert r.json()["valor_aula"] is None


def test_plano_avulso_de_valor_zero_e_permitido(client, h_full, base):
    r = client.post(PL, headers=h_full, json=corpo(base, nome="Aula Avulsa TotalPass", valor="0", is_avulso=True, recorrencia="SEMANAL"))
    assert r.status_code == 201 and r.json()["is_avulso"] is True and r.json()["recorrencia"] == "SEMANAL"


@pytest.mark.parametrize("mudanca", [
    {"nome": "A"},
    {"valor": "-1"},
    {"valor": "10.999"},
    {"aulas_por_semana": -1},
    {"aulas_por_semana": 15},
    {"duracao_meses": 0},
    {"recorrencia": "ANUAL"},
    {"tipo_servico_id": 9999},
    {"categoria_receita_id": 9999},
    {"modelo_contrato_id": 9999},
])
def test_plano_validacoes(client, h_full, base, mudanca):
    r = client.post(PL, headers=h_full, json=corpo(base, **mudanca))
    assert r.status_code == 422, r.text


def test_plano_categoria_deve_ser_de_receita_e_subcategoria_coerente(client, h_full, base):
    r = client.post(PL, headers=h_full, json=corpo(base, categoria_receita_id=base["cd"]))
    assert r.status_code == 422 and "receita" in r.json()["detail"]
    r = client.post(PL, headers=h_full, json=corpo(base, subcategoria_receita_id=base["sd"]))
    assert r.status_code == 422
    outra = Categoria(nome="Outra receita", tipo=TipoCategoria.RECEITA)
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        s.add(outra)
        s.commit()
        outra_id = outra.id
    r = client.post(PL, headers=h_full, json=corpo(base, categoria_receita_id=outra_id, subcategoria_receita_id=base["sr"]))
    assert r.status_code == 422 and "não pertence" in r.json()["detail"]
    # só a subcategoria: a categoria é preenchida a partir dela
    r = client.post(PL, headers=h_full, json=corpo(base, subcategoria_receita_id=base["sr"]))
    assert r.status_code == 201 and r.json()["categoria_receita_id"] == base["cr"]


def test_plano_nome_duplicado(client, h_full, base):
    client.post(PL, headers=h_full, json=corpo(base))
    assert client.post(PL, headers=h_full, json=corpo(base, nome="pilates 2X")).status_code == 409


def test_plano_duplicar_cria_copia_com_novo_codigo(client, db, h_full, base):
    p = client.post(PL, headers=h_full, json=corpo(base, categoria_receita_id=base["cr"], modelo_contrato_id=base["mc"])).json()
    c1 = client.post(f"{PL}/{p['id']}/duplicar", headers=h_full)
    assert c1.status_code == 201
    c1 = c1.json()
    assert c1["nome"] == "Pilates 2x (cópia)" and c1["id"] != p["id"] and c1["codigo"] == p["codigo"] + 1
    for campo in ("valor", "aulas_por_semana", "duracao_meses", "tipo_servico_id", "categoria_receita_id", "modelo_contrato_id"):
        assert c1[campo] == p[campo], campo
    c2 = client.post(f"{PL}/{p['id']}/duplicar", headers=h_full).json()
    assert c2["nome"] == "Pilates 2x (cópia 2)" and c2["codigo"] == c1["codigo"] + 1
    assert client.post(f"{PL}/9999/duplicar", headers=h_full).status_code == 404
    assert auditorias(db, "plano.duplicar")


def test_plano_duplicar_respeita_limite_do_nome(client, h_full, base):
    p = client.post(PL, headers=h_full, json=corpo(base, nome="N" * 120)).json()
    c = client.post(f"{PL}/{p['id']}/duplicar", headers=h_full).json()
    assert len(c["nome"]) == 120 and c["nome"].endswith("(cópia)")


def test_plano_ativar_desativar(client, db, h_full, base):
    p = client.post(PL, headers=h_full, json=corpo(base)).json()
    assert client.post(f"{PL}/{p['id']}/desativar", headers=h_full).json()["ativo"] is False
    assert client.post(f"{PL}/{p['id']}/ativar", headers=h_full).json()["ativo"] is True
    assert auditorias(db, "plano.desativar") and auditorias(db, "plano.ativar")


def test_plano_lista_busca_filtros_e_contagens(client, h_full, base):
    client.post(PL, headers=h_full, json=corpo(base, nome="Pilates 2x"))
    client.post(PL, headers=h_full, json=corpo(base, nome="Pilates 3x", aulas_por_semana=3, valor="400"))
    client.post(PL, headers=h_full, json=corpo(base, nome="Avulsa", is_avulso=True, valor="80", aulas_por_semana=1, ativo=False))
    client.post(PL, headers=h_full, json=corpo(base, nome="Fisio 1x", tipo_servico_id=base["ts2"], aulas_por_semana=1))
    todos = client.get(PL, headers=h_full).json()
    assert todos["total"] == 4 and todos["contagens"] == {"ativos": 3, "inativos": 1, "todos": 4}
    assert client.get(PL, headers=h_full, params={"tipo": "avulso"}).json()["total"] == 1
    assert client.get(PL, headers=h_full, params={"tipo": "mensal"}).json()["total"] == 3
    assert client.get(PL, headers=h_full, params={"situacao": "ativos"}).json()["total"] == 3
    assert client.get(PL, headers=h_full, params={"q": "pilates"}).json()["total"] == 2
    assert client.get(PL, headers=h_full, params={"tipo_servico_id": base["ts2"]}).json()["itens"][0]["nome"] == "Fisio 1x"
    caro = client.get(PL, headers=h_full, params={"ordenar": "valor", "direcao": "desc"}).json()["itens"][0]
    assert caro["nome"] == "Pilates 3x"
    assert client.get(PL, headers=h_full, params={"tipo": "xx"}).status_code == 422
    assert len(client.get(PL, headers=h_full, params={"por_pagina": 2}).json()["itens"]) == 2


def test_plano_opcoes_para_o_formulario(client, h_full, base):
    o = client.get(f"{PL}/opcoes", headers=h_full).json()
    assert {t["nome"] for t in o["tipos_servico"]} == {"Pilates", "Fisioterapia"}
    assert [c["nome"] for c in o["categorias_receita"]] == ["Mensalidades"]  # despesa não entra
    assert [s["nome"] for s in o["subcategorias_receita"]] == ["Pilates mensal"]
    assert o["modelos_contrato"][0]["nome"] == "Contrato padrão"


def test_plano_em_contrato_nao_exclui(client, db, h_full, base):
    p = client.post(PL, headers=h_full, json=corpo(base)).json()
    un = Unidade(nome="Matriz")
    pf = Profissional(nome="Ana")
    db.add_all([un, pf])
    db.flush()
    al = Aluno(nome="Aluno X", unidade_id=un.id, sem_cpf=True)
    db.add(al)
    db.flush()
    db.add(Contrato(aluno_id=al.id, plano_id=p["id"], unidade_id=un.id, profissional_id=pf.id, data_inicio=date(2026, 1, 1),
                    data_fim=date(2026, 3, 31)))
    db.commit()
    r = client.delete(f"{PL}/{p['id']}", headers=h_full)
    assert r.status_code == 409 and "1 contrato" in r.json()["detail"] and "Desative" in r.json()["detail"]
    assert db.get(Plano, p["id"]) is not None
    assert client.post(f"{PL}/{p['id']}/desativar", headers=h_full).status_code == 200
