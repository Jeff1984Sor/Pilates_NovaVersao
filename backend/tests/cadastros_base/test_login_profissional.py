"""Login próprio do profissional (nome curto como "ana"), nunca o e-mail."""

import pytest
from sqlalchemy import select

from app.core.models import PerfilAcesso, Usuario
from app.modules.cadastros.models import Profissional
from tests.conftest import SENHA, auth, criar_usuario, entrar

PF = "/api/cadastros/profissionais"


def perfil_id(db, nome):
    return db.scalar(select(PerfilAcesso.id).where(PerfilAcesso.nome == nome))


def base(**extra):
    d = {"nome": "Ana Souza", "login": "ana", "email": "ana@exemplo.com", "celular": "(11) 98888-7777"}
    d.update(extra)
    return d


def com_acesso(client, db, h, **extra):
    return client.post(PF, headers=h, json=base(acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor"), **extra)).json()


def com_senha(db, p):
    u = db.get(Usuario, p["usuario_id"])
    u.senha_hash = criar_usuario(db, "Full", email="tmp@exemplo.com").senha_hash
    db.commit()


@pytest.mark.parametrize("login", [None, "", "ab", "a" * 31, "ana@exemplo.com", "ana silva", "ana/x"])
def test_login_obrigatorio_e_com_formato_valido_ao_dar_acesso(client, db, h_full, login):
    r = client.post(PF, headers=h_full, json=base(login=login, acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor")))
    assert r.status_code == 422, r.text
    assert "login" in r.json()["detail"].lower()
    assert db.scalar(select(Profissional.id)) is None


def test_login_e_normalizado_em_minusculas_e_entra_so_com_ele(client, db, h_full, emails):
    p = client.post(PF, headers=h_full, json=base(login="  Ana.Souza_1 ", acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor"))).json()
    assert p["login"] == "ana.souza_1" and db.get(Usuario, p["usuario_id"]).login == "ana.souza_1"
    token = emails[0][2].split("token=")[1].split()[0]
    client.post("/api/auth/reset", json={"token": token, "senha": SENHA})
    assert entrar(client, "ana.souza_1").status_code == 200


def test_login_unico_ignorando_maiusculas(client, db, h_full):
    criar_usuario(db, "Full", email="outro@exemplo.com", login="ana")
    r = client.post(PF, headers=h_full, json=base(login="ANA", acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor")))
    assert r.status_code == 409 and "login" in r.json()["detail"].lower()
    assert db.scalar(select(Profissional.id)) is None
    p = client.post(PF, headers=h_full, json=base(email="b@exemplo.com")).json()
    r = client.post(f"{PF}/{p['id']}/acesso", headers=h_full, json={"perfil_acesso_id": perfil_id(db, "Professor"), "login": "Ana"})
    assert r.status_code == 409


def test_dar_acesso_depois_exige_login(client, db, h_full):
    p = client.post(PF, headers=h_full, json=base()).json()
    assert client.post(f"{PF}/{p['id']}/acesso", headers=h_full, json={"perfil_acesso_id": perfil_id(db, "Professor")}).status_code == 422
    r = client.post(f"{PF}/{p['id']}/acesso", headers=h_full, json={"perfil_acesso_id": perfil_id(db, "Professor"), "login": "ana.s"})
    assert r.status_code == 200 and r.json()["login"] == "ana.s"


def test_trocar_login_valida_e_derruba_as_sessoes(client, db, h_full):
    p = com_acesso(client, db, h_full)
    com_senha(db, p)
    tok = entrar(client, "ana").json()["access_token"]
    criar_usuario(db, "Full", email="o@exemplo.com", login="ocupado")
    assert client.put(f"{PF}/{p['id']}", headers=h_full, json=base(login="ocupado")).status_code == 409
    assert client.put(f"{PF}/{p['id']}", headers=h_full, json=base(login="x y")).status_code == 422
    r = client.put(f"{PF}/{p['id']}", headers=h_full, json=base(login="ana.nova"))
    assert r.status_code == 200 and r.json()["login"] == "ana.nova"
    assert client.get("/api/auth/me", headers=auth(tok)).status_code == 401
    assert entrar(client, "ana").status_code == 401
    assert entrar(client, "ana.nova").status_code == 200


def test_manter_o_mesmo_login_nao_derruba_sessao(client, db, h_full):
    p = com_acesso(client, db, h_full)
    com_senha(db, p)
    tok = entrar(client, "ana").json()["access_token"]
    assert client.put(f"{PF}/{p['id']}", headers=h_full, json=base(nome="Ana S.", login="ANA")).status_code == 200
    assert client.get("/api/auth/me", headers=auth(tok)).status_code == 200


def test_lista_mostra_e_busca_por_login(client, db, h_full):
    com_acesso(client, db, h_full)
    client.post(PF, headers=h_full, json={"nome": "Sem Login"})
    itens = client.get(PF, headers=h_full).json()["itens"]
    assert {i["nome"]: i["login"] for i in itens} == {"Ana Souza": "ana", "Sem Login": None}
    assert client.get(PF, headers=h_full, params={"q": "ana"}).json()["total"] == 1
