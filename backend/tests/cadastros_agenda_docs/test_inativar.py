"""Inativar em vez de excluir: fornecedores, categorias, subcategorias e termos; filtro para seletores."""

from datetime import date

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.cadastros.models import Categoria, Subcategoria
from app.modules.financeiro.models import ContaPagar

F = "/api/cadastros/fornecedores"
C = "/api/cadastros/categorias"
S = "/api/cadastros/categorias/subcategorias"
T = "/api/cadastros/termos"
MC = "/api/cadastros/modelos/contrato"
ME = "/api/cadastros/modelos/evolucao"


def _acoes(db):
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id)) if not a.acao.startswith("auth.")]


def test_fornecedor_inativar_reativar_chips_e_seletor(client, db, full):
    a = client.post(F, json={"nome": "Alfa"}, headers=full).json()
    client.post(F, json={"nome": "Beta"}, headers=full)
    assert a["ativo"] is True
    r = client.patch(f"{F}/{a['id']}/ativo", params={"ativo": False}, headers=full)
    assert r.status_code == 200 and r.json()["ativo"] is False
    lista = client.get(F, headers=full).json()
    assert lista["contagens"]["ativos"] == 1 and lista["contagens"]["inativos"] == 1 and lista["total"] == 2
    assert [i["nome"] for i in client.get(F, params={"situacao": "inativos"}, headers=full).json()["itens"]] == ["Alfa"]
    assert [i["nome"] for i in client.get(F, params={"situacao": "ativos"}, headers=full).json()["itens"]] == ["Beta"]
    assert [i["nome"] for i in client.get(F, params={"somente_ativos": True}, headers=full).json()["itens"]] == ["Beta"]
    assert client.patch(f"{F}/{a['id']}/ativo", params={"ativo": True}, headers=full).json()["ativo"] is True
    assert client.patch(f"{F}/999/ativo", params={"ativo": True}, headers=full).status_code == 404
    assert _acoes(db)[-2:] == ["fornecedor.inativar", "fornecedor.reativar"]


def test_exclusao_bloqueada_sugere_inativar(client, db, full):
    fid = client.post(F, json={"nome": "Energia"}, headers=full).json()["id"]
    cid = client.post(C, json={"nome": "Contas", "tipo": "DESPESA"}, headers=full).json()["id"]
    sid = client.post(S, json={"categoria_id": cid, "nome": "Luz"}, headers=full).json()["id"]
    db.add(ContaPagar(fornecedor_id=fid, categoria_id=cid, subcategoria_id=sid, vencimento=date(2026, 11, 5), valor=10))
    db.commit()
    for url in (f"{F}/{fid}", f"{C}/{cid}", f"{S}/{sid}"):
        r = client.delete(url, headers=full)
        assert r.status_code == 409 and "inativ" in r.json()["detail"].lower(), url


def test_categoria_e_subcategoria_inativas_somem_do_seletor(client, db, full):
    c1 = client.post(C, json={"nome": "Fixas", "tipo": "DESPESA"}, headers=full).json()["id"]
    c2 = client.post(C, json={"nome": "Variáveis", "tipo": "DESPESA"}, headers=full).json()["id"]
    s1 = client.post(S, json={"categoria_id": c1, "nome": "Aluguel"}, headers=full).json()["id"]
    client.post(S, json={"categoria_id": c1, "nome": "Luz"}, headers=full)
    client.post(S, json={"categoria_id": c2, "nome": "Material"}, headers=full)

    assert client.patch(f"{S}/{s1}/ativo", params={"ativo": False}, headers=full).json()["ativo"] is False
    nomes = lambda p: [i["nome"] for i in client.get(S, params=p, headers=full).json()["itens"]]  # noqa: E731
    assert nomes({"somente_ativos": True}) == ["Luz", "Material"]
    assert nomes({"situacao": "inativos"}) == ["Aluguel"]
    chips = client.get(S, headers=full).json()["contagens"]
    assert chips["ativos"] == 2 and chips["inativos"] == 1 and chips["todos"] == 3

    # categoria inativa: some do seletor e leva as subcategorias junto (somente no seletor)
    assert client.patch(f"{C}/{c2}/ativo", params={"ativo": False}, headers=full).json()["ativo"] is False
    assert [i["nome"] for i in client.get(C, params={"somente_ativos": True}, headers=full).json()["itens"]] == ["Fixas"]
    assert nomes({"somente_ativos": True}) == ["Luz"]
    assert client.get(C, headers=full).json()["contagens"]["inativos"] == 1
    r = client.post(S, json={"categoria_id": c2, "nome": "Outra"}, headers=full)
    assert r.status_code == 409 and "inativa" in r.json()["detail"]
    client.patch(f"{C}/{c2}/ativo", params={"ativo": True}, headers=full)
    assert client.post(S, json={"categoria_id": c2, "nome": "Outra"}, headers=full).status_code == 201
    assert {"categoria.inativar", "categoria.reativar", "subcategoria.inativar"} <= set(_acoes(db))


def test_termo_inativar_e_seletor(client, db, full):
    t1 = client.post(T, json={"nome": "Termo A", "conteudo_html": "<p>{ALUNO_NOME}</p>"}, headers=full).json()
    client.post(T, json={"nome": "Termo B", "conteudo_html": "<p>{ALUNO_NOME}</p>"}, headers=full)
    assert t1["ativo"] is True
    assert client.patch(f"{T}/{t1['id']}/ativo", params={"ativo": False}, headers=full).json()["ativo"] is False
    lista = client.get(T, headers=full).json()
    assert lista["contagens"] == {"todos": 2, "ativos": 1, "inativos": 1}
    assert [i["nome"] for i in client.get(T, params={"somente_ativos": True}, headers=full).json()["itens"]] == ["Termo B"]
    assert [i["nome"] for i in client.get(T, params={"situacao": "inativos"}, headers=full).json()["itens"]] == ["Termo A"]
    assert "termo.inativar" in _acoes(db)


def test_modelos_somente_ativos(client, full):
    client.post(MC, json={"nome": "Ativo", "conteudo_html": "<p>x</p>"}, headers=full)
    client.post(MC, json={"nome": "Inativo", "conteudo_html": "<p>x</p>", "ativo": False}, headers=full)
    client.post(ME, json={"titulo": "Ativo", "texto": "t"}, headers=full)
    client.post(ME, json={"titulo": "Inativo", "texto": "t", "ativo": False}, headers=full)
    assert [i["nome"] for i in client.get(MC, params={"somente_ativos": True}, headers=full).json()["itens"]] == ["Ativo"]
    assert [i["titulo"] for i in client.get(ME, params={"somente_ativos": True}, headers=full).json()["itens"]] == ["Ativo"]


def test_inativar_exige_editar(client, secretaria, professor, full):
    fid = client.post(F, json={"nome": "Alfa"}, headers=full).json()["id"]
    assert client.patch(f"{F}/{fid}/ativo", params={"ativo": False}, headers=professor).status_code == 403
    assert client.patch(f"{F}/{fid}/ativo", params={"ativo": False}, headers=secretaria).status_code == 403


def test_migracao_modelo_tem_default_ativo(db):
    c = Categoria(nome="Sem ativo informado")
    db.add(c)
    db.commit()
    assert c.ativo is True and db.scalar(select(Subcategoria.id)) is None
