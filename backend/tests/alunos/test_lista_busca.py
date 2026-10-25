from app.modules.alunos.models import Aluno
from tests.alunos.conftest import CPF_A, CPF_B, CPF_C


def test_lista_chips_e_contagem(client, h, criar):
    criar(nome="Ana Souza", cpf=CPF_A)
    criar(nome="Bruno Lima", cpf=CPF_B)
    c = criar(nome="Carla Dias", cpf=CPF_C)
    client.post(f"/api/alunos/{c['id']}/inativar", headers=h)

    r = client.get("/api/alunos", headers=h).json()  # padrão: ativos
    assert [i["nome"] for i in r["itens"]] == ["Ana Souza", "Bruno Lima"]
    assert r["contagens"] == {"ativos": 2, "inativos": 1, "todos": 3}
    assert [i["nome"] for i in client.get("/api/alunos", headers=h, params={"situacao": "inativos"}).json()["itens"]] == ["Carla Dias"]
    assert client.get("/api/alunos", headers=h, params={"situacao": "todos"}).json()["total"] == 3
    assert client.get("/api/alunos", headers=h, params={"situacao": "qualquer"}).status_code == 422


def test_busca_por_nome_cpf_rg_telefone_e_codigo(client, h, criar):
    criar(nome="Ana Souza", cpf=CPF_A, rg="MG-12.345", telefones=[{"numero": "(31) 98888-1111"}])
    criar(nome="Bruno Lima", cpf=CPF_B, telefones=[{"numero": "11977776666"}])

    def nomes(q, **p):
        return [i["nome"] for i in client.get("/api/alunos", headers=h, params={"q": q, **p}).json()["itens"]]

    assert nomes("souza") == ["Ana Souza"]
    assert nomes("ANA") == ["Ana Souza"]
    assert nomes("529.982") == ["Ana Souza"] and nomes("52998224725") == ["Ana Souza"]
    assert nomes("mg-12") == ["Ana Souza"]
    assert nomes("98888-1111") == ["Ana Souza"] and nomes("31988881111") == ["Ana Souza"]
    assert nomes("977776666") == ["Bruno Lima"]
    assert "Bruno Lima" in nomes("2")  # código 2 (número curto também casa com outros campos)
    assert nomes("zzz") == []
    assert nomes("") == ["Ana Souza", "Bruno Lima"]


def test_ordenacao_e_paginacao(client, h, criar):
    for n, c in [("Carla", CPF_C), ("Ana", CPF_A), ("Bruno", CPF_B)]:
        criar(nome=n, cpf=c)
    r = client.get("/api/alunos", headers=h, params={"ordem": "-nome"}).json()
    assert [i["nome"] for i in r["itens"]] == ["Carla", "Bruno", "Ana"]
    assert [i["nome"] for i in client.get("/api/alunos", headers=h, params={"ordem": "codigo"}).json()["itens"]] == ["Carla", "Ana", "Bruno"]
    p2 = client.get("/api/alunos", headers=h, params={"por_pagina": 2, "pagina": 2}).json()
    assert p2["total"] == 3 and [i["nome"] for i in p2["itens"]] == ["Carla"] and p2["pagina"] == 2
    assert client.get("/api/alunos", headers=h, params={"por_pagina": 500}).status_code == 422
    assert client.get("/api/alunos", headers=h, params={"ordem": "inexistente"}).status_code == 200  # cai no padrão


def test_lista_traz_cpf_mascarado_telefone_e_aulas(client, h, criar, reservar, professor):
    a = criar(telefones=[{"numero": "11988887777"}])
    reservar(a["id"], professor["profissional_id"])
    i = client.get("/api/alunos", headers=h).json()["itens"][0]
    assert i["cpf_mascarado"] == "***.***.247-25" and "529" not in str(i)
    assert i["telefone"] == "(11) 98888-7777" and i["aulas_reservadas"] == 1


def test_busca_rapida(client, h, criar):
    criar(nome="Ana Souza", cpf=CPF_A, telefones=[{"numero": "11988887777"}])
    b = client.get("/api/alunos/busca", headers=h, params={"q": "ana"}).json()
    assert [x["nome"] for x in b] == ["Ana Souza"] and b[0]["telefone"] == "(11) 98888-7777"
    assert client.get("/api/alunos/busca", headers=h, params={"q": "98888"}).json()[0]["id"] == b[0]["id"]
    assert client.get("/api/alunos/busca", headers=h, params={"q": "52998224725"}).json()[0]["id"] == b[0]["id"]
    assert client.get("/api/alunos/busca", headers=h, params={"q": "a"}).json() == []  # mínimo de 2 caracteres


def test_busca_rapida_limita_resultados(client, h, base, db):
    for i in range(20):
        db.add(Aluno(nome=f"Marta {i:02d}", sem_cpf=True, unidade_id=base["unidade_id"]))
    db.commit()
    assert len(client.get("/api/alunos/busca", headers=h, params={"q": "marta"}).json()) == 8
    assert len(client.get("/api/alunos/busca", headers=h, params={"q": "marta", "limite": 3}).json()) == 3


def test_opcoes_para_os_selects(client, h, base):
    o = client.get("/api/alunos/opcoes", headers=h).json()
    assert o["unidades"] == [{"id": base["unidade_id"], "nome": "Unidade Teste", "ativo": True}]
    assert [p["nome"] for p in o["profissoes"]] == ["Engenheira"] and [t["nome"] for t in o["termos"]] == ["Termo de imagem"]
    assert {e["id"] for e in o["estados_civis"]} >= {"SOLTEIRO", "CASADO", "UNIAO_ESTAVEL"}
    assert client.get("/api/alunos/opcoes").status_code == 401
