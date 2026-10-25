"""Fornecedores, categorias e subcategorias: CRUD, busca, chips, códigos, exclusão com vínculos e auditoria."""

from datetime import date

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.cadastros.models import Categoria, ContadorCodigo, Plano, Subcategoria
from app.modules.financeiro.models import ContaPagar

F = "/api/cadastros/fornecedores"
C = "/api/cadastros/categorias"
S = "/api/cadastros/categorias/subcategorias"


def _acoes(db):
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id)) if not a.acao.startswith("auth.")]


# ------------------------------------------------------------------------------------------------ fornecedores
def test_crud_fornecedor_com_codigo_do_contador_e_auditoria(client, db, full):
    r = client.post(F, json={"nome": "  Limpeza   Brilho  "}, headers=full)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["nome"] == "Limpeza Brilho"  # espaços normalizados
    assert f["codigo"] == 1 and f["contas_a_pagar"] == 0
    assert client.post(F, json={"nome": "Papelaria"}, headers=full).json()["codigo"] == 2
    assert db.get(ContadorCodigo, "fornecedor").ultimo == 2

    assert client.put(f"{F}/{f['id']}", json={"nome": "Limpeza Brilho Ltda"}, headers=full).json()["nome"] == "Limpeza Brilho Ltda"
    assert client.get(f"{F}/{f['id']}", headers=full).json()["nome"] == "Limpeza Brilho Ltda"
    assert client.delete(f"{F}/{f['id']}", headers=full).status_code == 200
    assert client.get(f"{F}/{f['id']}", headers=full).status_code == 404
    assert _acoes(db) == ["fornecedor.criar", "fornecedor.criar", "fornecedor.alterar", "fornecedor.excluir"]


def test_fornecedor_validacoes_e_duplicidade(client, full):
    assert client.post(F, json={"nome": "a"}, headers=full).status_code == 422
    assert client.post(F, json={}, headers=full).status_code == 422
    assert client.post(F, json={"nome": "Papelaria"}, headers=full).status_code == 201
    r = client.post(F, json={"nome": "papelaria"}, headers=full)
    assert r.status_code == 409 and "mesmo nome" not in r.json()["detail"] and "Já existe" in r.json()["detail"]
    assert client.get(f"{F}/999", headers=full).status_code == 404
    assert client.put(f"{F}/999", json={"nome": "Xis"}, headers=full).status_code == 404


def test_fornecedor_lista_busca_ordem_paginacao_e_chips(client, db, full):
    ids = {}
    for n in ("Zeta Material", "Alfa Limpeza", "Beta Papel", "Alfa Manutenção"):
        ids[n] = client.post(F, json={"nome": n}, headers=full).json()["id"]
    cat = Categoria(nome="Despesas fixas", tipo="DESPESA")
    db.add(cat)
    db.flush()
    s = Subcategoria(categoria_id=cat.id, nome="Material")
    db.add(s)
    db.flush()
    db.add(ContaPagar(fornecedor_id=ids["Alfa Limpeza"], categoria_id=cat.id, subcategoria_id=s.id, vencimento=date(2026, 11, 5), valor=100))
    db.commit()

    r = client.get(F, headers=full).json()
    assert [i["nome"] for i in r["itens"]] == ["Alfa Limpeza", "Alfa Manutenção", "Beta Papel", "Zeta Material"]
    assert r["contagens"] == {"todos": 4, "ativos": 4, "inativos": 0, "em_uso": 1, "sem_uso": 3}
    assert [i["nome"] for i in client.get(F, params={"q": "alfa"}, headers=full).json()["itens"]] == ["Alfa Limpeza", "Alfa Manutenção"]
    assert client.get(F, params={"q": "alfa"}, headers=full).json()["contagens"]["todos"] == 2
    uso = client.get(F, params={"uso": "em_uso"}, headers=full).json()
    assert [i["nome"] for i in uso["itens"]] == ["Alfa Limpeza"] and uso["itens"][0]["contas_a_pagar"] == 1
    assert uso["contagens"]["todos"] == 4  # chips ignoram o filtro de situação
    desc = client.get(F, params={"ordenar": "nome", "direcao": "desc", "por_pagina": 2}, headers=full).json()
    assert [i["nome"] for i in desc["itens"]] == ["Zeta Material", "Beta Papel"] and desc["total"] == 4
    assert [i["nome"] for i in client.get(F, params={"pagina": 2, "por_pagina": 3}, headers=full).json()["itens"]] == ["Zeta Material"]
    assert client.get(F, params={"ordenar": "senha"}, headers=full).status_code == 422
    # % digitado na busca é texto, não curinga
    assert client.get(F, params={"q": "%"}, headers=full).json()["total"] == 0


def test_fornecedor_com_contas_a_pagar_nao_pode_ser_excluido(client, db, full):
    fid = client.post(F, json={"nome": "Energia SA"}, headers=full).json()["id"]
    cat = Categoria(nome="Contas", tipo="DESPESA")
    db.add(cat)
    db.flush()
    sub = Subcategoria(categoria_id=cat.id, nome="Luz")
    db.add(sub)
    db.flush()
    db.add(ContaPagar(fornecedor_id=fid, categoria_id=cat.id, subcategoria_id=sub.id, vencimento=date(2026, 11, 5), valor=250))
    db.commit()
    r = client.delete(f"{F}/{fid}", headers=full)
    assert r.status_code == 409
    assert "1 conta a pagar" in r.json()["detail"] and "Energia SA" in r.json()["detail"]
    assert client.get(f"{F}/{fid}", headers=full).status_code == 200
    assert "fornecedor.excluir" not in _acoes(db)


# ------------------------------------------------------------------------------------------------ categorias
def test_crud_categoria_e_subcategoria(client, db, full):
    c = client.post(C, json={"nome": "Aluguel e contas", "tipo": "DESPESA"}, headers=full)
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    assert c.json()["codigo"] == 1 and c.json()["subcategorias"] == 0
    assert client.post(C, json={"nome": "Mensalidades", "tipo": "RECEITA"}, headers=full).json()["codigo"] == 2
    assert client.post(C, json={"nome": "X", "tipo": "OUTRO"}, headers=full).status_code == 422

    s = client.post(S, json={"categoria_id": cid, "nome": "Luz"}, headers=full)
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    assert s.json()["categoria_nome"] == "Aluguel e contas" and s.json()["categoria_tipo"] == "DESPESA" and s.json()["codigo"] == 1
    assert client.get(f"{C}/{cid}", headers=full).json()["subcategorias"] == 1

    assert client.put(f"{S}/{sid}", json={"categoria_id": cid, "nome": "Energia elétrica"}, headers=full).json()["nome"] == "Energia elétrica"
    assert client.put(f"{C}/{cid}", json={"nome": "Aluguel, contas", "tipo": "DESPESA"}, headers=full).json()["nome"] == "Aluguel, contas"
    assert client.delete(f"{S}/{sid}", headers=full).status_code == 200
    assert client.delete(f"{C}/{cid}", headers=full).status_code == 200
    assert _acoes(db) == [
        "categoria.criar", "categoria.criar", "subcategoria.criar", "subcategoria.alterar", "categoria.alterar",
        "subcategoria.excluir", "categoria.excluir",
    ]


def test_categoria_e_subcategoria_validam_duplicidade_e_referencia(client, full):
    cid = client.post(C, json={"nome": "Pessoal", "tipo": "DESPESA"}, headers=full).json()["id"]
    assert client.post(C, json={"nome": "pessoal", "tipo": "DESPESA"}, headers=full).status_code == 409
    assert client.post(C, json={"nome": "Pessoal", "tipo": "RECEITA"}, headers=full).status_code == 201  # tipo diferente pode
    assert client.post(S, json={"categoria_id": cid, "nome": "Salários"}, headers=full).status_code == 201
    assert client.post(S, json={"categoria_id": cid, "nome": "SALÁRIOS"}, headers=full).status_code == 409
    assert client.post(S, json={"categoria_id": 999, "nome": "Algo"}, headers=full).status_code == 422
    assert client.get(f"{C}/999", headers=full).status_code == 404
    assert client.delete(f"{S}/999", headers=full).status_code == 404


def test_listas_de_categoria_e_subcategoria_com_chips_por_tipo(client, full):
    d = client.post(C, json={"nome": "Despesas", "tipo": "DESPESA"}, headers=full).json()["id"]
    r = client.post(C, json={"nome": "Receitas", "tipo": "RECEITA"}, headers=full).json()["id"]
    for cat, nome in ((d, "Luz"), (d, "Gás"), (r, "Aulas avulsas")):
        client.post(S, json={"categoria_id": cat, "nome": nome}, headers=full)
    lista = client.get(C, headers=full).json()
    assert [i["nome"] for i in lista["itens"]] == ["Despesas", "Receitas"]
    assert lista["contagens"] == {"todos": 2, "RECEITA": 1, "DESPESA": 1, "ativos": 2, "inativos": 0}
    assert [i["nome"] for i in client.get(C, params={"tipo": "RECEITA"}, headers=full).json()["itens"]] == ["Receitas"]

    subs = client.get(S, headers=full).json()
    assert [i["nome"] for i in subs["itens"]] == ["Gás", "Luz", "Aulas avulsas"]  # por categoria e nome
    assert subs["contagens"] == {"todos": 3, "RECEITA": 1, "DESPESA": 2, "ativos": 3, "inativos": 0}
    assert len(client.get(S, params={"categoria_id": d}, headers=full).json()["itens"]) == 2
    assert [i["nome"] for i in client.get(S, params={"q": "avuls"}, headers=full).json()["itens"]] == ["Aulas avulsas"]
    assert [i["nome"] for i in client.get(S, params={"tipo": "DESPESA", "ordenar": "nome", "direcao": "desc"}, headers=full).json()["itens"]] == ["Luz", "Gás"]


def test_categoria_com_vinculos_nao_e_excluida_e_explica(client, db, full):
    cid = client.post(C, json={"nome": "Contas", "tipo": "DESPESA"}, headers=full).json()["id"]
    sid = client.post(S, json={"categoria_id": cid, "nome": "Luz"}, headers=full).json()["id"]
    r = client.delete(f"{C}/{cid}", headers=full)
    assert r.status_code == 409 and "1 subcategoria" in r.json()["detail"]

    fid = client.post(F, json={"nome": "Enel"}, headers=full).json()["id"]
    db.add(ContaPagar(fornecedor_id=fid, categoria_id=cid, subcategoria_id=sid, vencimento=date(2026, 11, 5), valor=10))
    db.commit()
    r = client.delete(f"{S}/{sid}", headers=full)
    assert r.status_code == 409 and "1 conta a pagar" in r.json()["detail"]
    # tipo em uso não muda; mover subcategoria em uso também não
    assert client.put(f"{C}/{cid}", json={"nome": "Contas", "tipo": "RECEITA"}, headers=full).status_code == 409
    outra = client.post(C, json={"nome": "Outras", "tipo": "DESPESA"}, headers=full).json()["id"]
    assert client.put(f"{S}/{sid}", json={"categoria_id": outra, "nome": "Luz"}, headers=full).status_code == 409
    # renomear continua livre
    assert client.put(f"{C}/{cid}", json={"nome": "Contas fixas", "tipo": "DESPESA"}, headers=full).status_code == 200


def test_categoria_de_receita_usada_por_plano_nao_e_excluida(client, db, full):
    from app.modules.cadastros.models import TipoServico

    cid = client.post(C, json={"nome": "Mensalidades", "tipo": "RECEITA"}, headers=full).json()["id"]
    sid = client.post(S, json={"categoria_id": cid, "nome": "Pilates"}, headers=full).json()["id"]
    srv = TipoServico(nome="Pilates")
    db.add(srv)
    db.flush()
    db.add(Plano(nome="2x", tipo_servico_id=srv.id, categoria_receita_id=cid, subcategoria_receita_id=sid))
    db.commit()
    r = client.delete(f"{S}/{sid}", headers=full)
    assert r.status_code == 409 and "1 plano" in r.json()["detail"]
    assert client.get(f"{C}/{cid}", headers=full).json()["planos"] == 1
