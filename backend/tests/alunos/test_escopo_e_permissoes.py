"""Escopo do perfil Professor (só alunos com reserva em aula dele) e permissões das rotas de alunos."""

from tests.alunos.conftest import CPF_B, PDF
from tests.conftest import auth, criar_usuario, entrar


def test_professor_padrao_so_ve_o_cabecalho_do_proprio_aluno(client, h, criar, reservar, professor, token_professor):
    meu = criar(nome="Meu Aluno", telefones=[{"numero": "11988887777"}])
    alheio = criar(nome="Aluno Alheio", cpf=CPF_B)
    reservar(meu["id"], professor["profissional_id"])
    reservar(alheio["id"], professor["outro_id"])
    hp = auth(token_professor)

    r = client.get(f"/api/alunos/{meu['id']}/resumo", headers=hp)
    assert r.status_code == 200
    assert set(r.json()) == {"id", "nome", "status", "foto_url", "unidade_nome"}  # sem CPF nem telefone
    assert client.get(f"/api/alunos/{alheio['id']}/resumo", headers=hp).status_code == 404
    # o perfil padrão não tem alunos.ver: nada de ficha completa, lista, busca, documentos, termo
    for url in (f"/api/alunos/{meu['id']}", "/api/alunos", "/api/alunos/busca?q=ma", f"/api/alunos/{meu['id']}/documentos",
                f"/api/alunos/{meu['id']}/termo", f"/api/alunos/{meu['id']}/vinculos"):
        assert client.get(url, headers=hp).status_code == 403, url
    assert client.put(f"/api/alunos/{meu['id']}", headers=hp, json={"nome": "Hackeado"}).status_code == 403
    assert client.delete(f"/api/alunos/{meu['id']}", headers=hp).status_code == 403


def test_professor_com_alunos_ver_continua_restrito_aos_seus_alunos(client, h, criar, reservar, professor, token_professor_mais):
    meu = criar(nome="Meu Aluno", telefones=[{"numero": "11988887777"}])
    alheio = criar(nome="Aluno Alheio", cpf=CPF_B)
    reservar(meu["id"], professor["profissional_id"])
    reservar(alheio["id"], professor["outro_id"])
    hp = auth(token_professor_mais)

    lista = client.get("/api/alunos", headers=hp, params={"situacao": "todos"}).json()
    assert [i["nome"] for i in lista["itens"]] == ["Meu Aluno"]
    assert lista["contagens"] == {"ativos": 1, "inativos": 0, "todos": 1}  # contagem também respeita o escopo
    assert client.get(f"/api/alunos/{meu['id']}", headers=hp).status_code == 200
    assert client.get(f"/api/alunos/{alheio['id']}", headers=hp).status_code == 404
    assert client.get(f"/api/alunos/{alheio['id']}/documentos", headers=hp).status_code == 404
    assert client.get(f"/api/alunos/{alheio['id']}/termo", headers=hp).status_code == 404
    assert [x["nome"] for x in client.get("/api/alunos/busca", headers=hp, params={"q": "aluno"}).json()] == ["Meu Aluno"]
    assert client.get("/api/alunos/busca", headers=hp, params={"q": "alheio"}).json() == []


def test_professor_nunca_altera_cadastro_mesmo_com_permissao(client, db, h, criar, reservar, professor):
    from app.core.models import PerfilAcesso

    meu = criar(nome="Meu Aluno")
    reservar(meu["id"], professor["profissional_id"])
    p = PerfilAcesso(nome="Professor++", permissoes=["alunos.ver", "alunos.editar", "alunos.excluir", "aulas.ver"], somente_proprias_aulas=True)
    db.add(p)
    db.flush()
    u = criar_usuario(db, "Professor", email="prof3@exemplo.com")
    u.perfil_acesso_id = p.id
    db.commit()
    professor["mapa"][u.id] = professor["profissional_id"]
    hp = auth(entrar(client, "prof3@exemplo.com").json()["access_token"])
    assert client.put(f"/api/alunos/{meu['id']}", headers=hp, json={"nome": "Mudou Nome"}).status_code == 403
    assert client.post("/api/alunos", headers=hp, json={"nome": "Novo Aluno", "sem_cpf": True, "unidade_id": 1}).status_code == 403
    assert client.delete(f"/api/alunos/{meu['id']}", headers=hp).status_code == 403
    assert client.post(f"/api/alunos/{meu['id']}/documentos", headers=hp, data={"titulo": "x"},
                       files={"arquivo": ("a.pdf", PDF, "application/pdf")}).status_code == 403


def test_professor_sem_vinculo_com_profissional_nao_ve_nada(client, h, criar, reservar, professor, token_professor_mais):
    meu = criar(nome="Meu Aluno")
    reservar(meu["id"], professor["profissional_id"])
    professor["mapa"].clear()  # usuário sem profissional vinculado: negar por padrão
    hp = auth(token_professor_mais)
    assert client.get("/api/alunos", headers=hp).json()["total"] == 0
    assert client.get(f"/api/alunos/{meu['id']}", headers=hp).status_code == 404


def test_foto_do_professor_respeita_escopo(client, h, criar, reservar, professor, token_professor):
    from tests.alunos.conftest import png_bytes

    meu = criar(nome="Meu Aluno")
    alheio = criar(nome="Alheio", cpf=CPF_B)
    for a in (meu, alheio):
        client.post(f"/api/alunos/{a['id']}/foto", headers=h, files={"arquivo": ("f.png", png_bytes(), "image/png")})
    reservar(meu["id"], professor["profissional_id"])
    hp = auth(token_professor)
    assert client.get(f"/api/alunos/{meu['id']}/foto", headers=hp).status_code == 200
    assert client.get(f"/api/alunos/{alheio['id']}/foto", headers=hp).status_code == 404


def test_secretaria_pode_editar_mas_nao_excluir(client, db, criar):
    a = criar()
    criar_usuario(db, "Secretária", email="sec@exemplo.com")
    hs = auth(entrar(client, "sec@exemplo.com").json()["access_token"])
    assert client.get("/api/alunos", headers=hs).status_code == 200
    assert client.put(f"/api/alunos/{a['id']}", headers=hs, json={"rg": "1"}).status_code == 200
    assert client.post(f"/api/alunos/{a['id']}/inativar", headers=hs).status_code == 200
    assert client.delete(f"/api/alunos/{a['id']}", headers=hs).status_code == 403


def test_somente_leitura_nao_escreve(client, db, h, criar):
    from app.core.models import PerfilAcesso

    a = criar()
    p = PerfilAcesso(nome="Leitura", permissoes=["alunos.ver"])
    db.add(p)
    db.flush()
    u = criar_usuario(db, "Secretária", email="leitor@exemplo.com")
    u.perfil_acesso_id = p.id
    db.commit()
    hl = auth(entrar(client, "leitor@exemplo.com").json()["access_token"])
    assert client.get(f"/api/alunos/{a['id']}", headers=hl).status_code == 200
    assert client.put(f"/api/alunos/{a['id']}", headers=hl, json={"rg": "1"}).status_code == 403
    assert client.post(f"/api/alunos/{a['id']}/inativar", headers=hl).status_code == 403
    assert client.post(f"/api/alunos/{a['id']}/termo/registrar", headers=hl, json={"termo_id": 1}).status_code == 403
    assert client.delete(f"/api/alunos/{a['id']}/foto", headers=hl).status_code == 403


def test_todas_as_rotas_de_alunos_exigem_login(client, criar):
    a = criar()
    i = a["id"]
    for metodo, url in [("get", "/api/alunos"), ("get", "/api/alunos/busca?q=ab"), ("get", "/api/alunos/cep/01310100"),
                        ("post", "/api/alunos"), ("get", f"/api/alunos/{i}"), ("get", f"/api/alunos/{i}/resumo"),
                        ("put", f"/api/alunos/{i}"), ("delete", f"/api/alunos/{i}"), ("get", f"/api/alunos/{i}/vinculos"),
                        ("post", f"/api/alunos/{i}/inativar"), ("post", f"/api/alunos/{i}/reativar"),
                        ("post", f"/api/alunos/{i}/foto"), ("delete", f"/api/alunos/{i}/foto"), ("get", f"/api/alunos/{i}/foto"),
                        ("get", f"/api/alunos/{i}/documentos"), ("post", f"/api/alunos/{i}/documentos"),
                        ("get", f"/api/alunos/{i}/documentos/1/arquivo"), ("delete", f"/api/alunos/{i}/documentos/1"),
                        ("get", f"/api/alunos/{i}/termo"), ("post", f"/api/alunos/{i}/termo/registrar"),
                        ("post", f"/api/alunos/{i}/termo/assinatura-local"), ("get", f"/api/alunos/{i}/termo/assinatura")]:
        assert getattr(client, metodo)(url).status_code == 401, (metodo, url)
