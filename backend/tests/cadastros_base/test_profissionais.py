from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import escopo
from app.core.deps import Contexto
from app.core.models import PerfilAcesso, Usuario
from app.modules.agenda.models import AulaSessao
from app.modules.cadastros.models import Profissional, TipoServico, Unidade
from tests.cadastros_base.conftest import auditorias
from tests.conftest import SENHA, auth, criar_usuario, entrar

PF = "/api/cadastros/profissionais"


def perfil_id(db, nome):
    return db.scalar(select(PerfilAcesso.id).where(PerfilAcesso.nome == nome))


def base(**extra):
    d = {"nome": "Ana Souza", "login": "ana", "email": "ana@exemplo.com", "celular": "(11) 98888-7777", "crefito": "CREFITO-3/123456",
         "data_nascimento": "1990-05-17", "comissao_percentual": "30"}
    d.update(extra)
    return d


# -------------------------------------------------------------------------------------------- sem login
def test_criar_profissional_sem_acesso_ao_sistema(client, db, h_full):
    r = client.post(PF, headers=h_full, json=base())
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["codigo"] == 1 and p["acesso_sistema"] is False and p["usuario_id"] is None and p["perfil_acesso_nome"] is None
    assert p["celular"] == "5511988887777"  # normalizado (R16)
    assert p["comissao_percentual"] in ("30", "30.00", 30)
    assert db.scalar(select(Usuario.id).where(Usuario.email == "ana@exemplo.com")) is None
    assert auditorias(db, "profissional.criar")


def test_profissional_sem_email_e_sem_acesso_e_valido(client, h_full):
    r = client.post(PF, headers=h_full, json={"nome": "Beto Lima"})
    assert r.status_code == 201 and r.json()["email"] is None


@pytest.mark.parametrize("mudanca", [
    {"nome": "A"},
    {"email": "nao-e-email"},
    {"celular": "123"},
    {"comissao_percentual": "-1"},
    {"comissao_percentual": "100.01"},
    {"data_nascimento": (date.today() + timedelta(days=1)).isoformat()},
    {"data_nascimento": "1850-01-01"},
])
def test_profissional_validacoes(client, h_full, mudanca):
    r = client.post(PF, headers=h_full, json=base(**mudanca))
    assert r.status_code == 422, r.text


def test_comissao_nos_limites(client, h_full):
    assert client.post(PF, headers=h_full, json=base(nome="Zero", email="z@exemplo.com", comissao_percentual="0")).status_code == 201
    assert client.post(PF, headers=h_full, json=base(nome="Cem", email="c@exemplo.com", comissao_percentual="100")).status_code == 201


def test_email_de_profissional_duplicado(client, h_full):
    client.post(PF, headers=h_full, json=base())
    r = client.post(PF, headers=h_full, json=base(nome="Outra", email="ANA@exemplo.com"))
    assert r.status_code == 409 and "e-mail" in r.json()["detail"]


# -------------------------------------------------------------------------------------------- com login
def test_criar_com_acesso_cria_usuario_com_perfil_e_envia_convite(client, db, h_full, emails):
    r = client.post(PF, headers=h_full, json=base(acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor")))
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["acesso_sistema"] is True and p["login"] == "ana" and p["perfil_acesso_nome"] == "Professor" and p["convite_pendente"] is True
    assert p["convite_enviado"] is True
    u = db.get(Usuario, p["usuario_id"])
    assert u.login == "ana" and u.email == "ana@exemplo.com" and u.nome == "Ana Souza" and u.acesso_sistema and u.ativo
    assert u.senha_hash is None and u.convite_pendente and u.telefone == "5511988887777"
    assert u.perfil_acesso.nome == "Professor"
    assert len(emails) == 1 and emails[0][0] == ["ana@exemplo.com"] and "redefinir-senha?token=" in emails[0][2]
    assert auditorias(db, "usuario.criar") and auditorias(db, "profissional.criar")


def test_convite_com_smtp_fora_do_ar_nao_desfaz_o_cadastro(client, db, h_full, monkeypatch):
    monkeypatch.setattr("app.core.email.enviar", lambda *a, **k: False)
    r = client.post(PF, headers=h_full, json=base(acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Secretária")))
    assert r.status_code == 201 and r.json()["convite_enviado"] is False and r.json()["acesso_sistema"] is True


def test_criar_com_acesso_exige_email_perfil_e_usuarios_editar(client, db, h_full):
    assert client.post(PF, headers=h_full, json=base(email=None, acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor"))).status_code == 422
    assert client.post(PF, headers=h_full, json=base(acesso_sistema=True)).status_code == 422
    assert client.post(PF, headers=h_full, json=base(acesso_sistema=True, perfil_acesso_id=9999)).status_code == 422
    r = client.post(PF, headers=h_full, json=base(acesso_sistema=True, ativo=False, perfil_acesso_id=perfil_id(db, "Professor")))
    assert r.status_code == 400
    assert db.scalar(select(Profissional.id)) is None  # nada foi criado nas recusas


def test_email_ja_usado_por_outro_usuario_recusa_sem_criar_nada(client, db, h_full):
    criar_usuario(db, "Secretária", email="ana@exemplo.com", login="outra.ana")  # login diferente: o conflito testado é o do e-mail
    r = client.post(PF, headers=h_full, json=base(acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor")))
    assert r.status_code == 409 and "usuário" in r.json()["detail"]
    assert db.scalar(select(Profissional.id)) is None


def test_quem_edita_cadastros_mas_nao_gere_usuarios_nao_da_acesso(client, db, h_full):
    # perfil com cadastros_profissionais.editar mas sem usuarios.editar
    from app.core.permissoes import normalizar

    p = PerfilAcesso(nome="Gestora de cadastros", permissoes=normalizar(["cadastros_profissionais.editar", "cadastros_profissionais.excluir"]))
    db.add(p)
    db.commit()
    criar_usuario(db, "Full", email="g@exemplo.com")  # só para ter admin
    u = Usuario(nome="Gestora", email="gestora@exemplo.com", login="gestora", perfil_acesso_id=p.id, senha_hash=criar_usuario(db, "Full", email="x@exemplo.com").senha_hash)
    db.add(u)
    db.commit()
    h = auth(entrar(client, "gestora@exemplo.com").json()["access_token"])
    assert client.post(PF, headers=h, json=base()).status_code == 201  # sem login: pode
    r = client.post(PF, headers=h, json=base(nome="Com", email="com@exemplo.com", login="com", acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor")))
    assert r.status_code == 403
    pid = client.get(PF, headers=h).json()["itens"][0]["id"]
    assert client.post(f"{PF}/{pid}/acesso", headers=h, json={"perfil_acesso_id": perfil_id(db, "Professor"), "login": "ana"}).status_code == 403
    assert client.delete(f"{PF}/{pid}/acesso", headers=h).status_code == 403


def test_novo_profissional_define_senha_pelo_convite_e_entra(client, db, h_full, emails):
    p = client.post(PF, headers=h_full, json=base(acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor"))).json()
    token = emails[0][2].split("token=")[1].split()[0]
    r = client.post("/api/auth/reset", json={"token": token, "senha": SENHA})
    assert r.status_code == 200, r.text
    assert entrar(client, "ana").status_code == 200
    assert db.get(Usuario, p["usuario_id"]).convite_pendente is False


def test_dar_acesso_depois_e_revogar(client, db, h_full, emails):
    p = client.post(PF, headers=h_full, json=base()).json()
    r = client.post(f"{PF}/{p['id']}/acesso", headers=h_full, json={"perfil_acesso_id": perfil_id(db, "Secretária"), "login": "ana"})
    assert r.status_code == 200 and r.json()["acesso_sistema"] is True and r.json()["perfil_acesso_nome"] == "Secretária"
    assert client.post(f"{PF}/{p['id']}/acesso", headers=h_full, json={"perfil_acesso_id": perfil_id(db, "Secretária"), "login": "ana"}).status_code == 409
    u = db.get(Usuario, r.json()["usuario_id"])
    u.senha_hash = criar_usuario(db, "Full", email="tmp@exemplo.com").senha_hash  # senha conhecida
    db.commit()
    tok = entrar(client, "ana").json()["access_token"]
    assert client.get("/api/auth/me", headers=auth(tok)).status_code == 200
    versao = db.get(Usuario, u.id).token_version

    r = client.delete(f"{PF}/{p['id']}/acesso", headers=h_full)
    assert r.status_code == 200 and r.json()["acesso_sistema"] is False and r.json()["usuario_id"] == u.id
    db.expire_all()
    assert db.get(Usuario, u.id).token_version > versao
    assert client.get("/api/auth/me", headers=auth(tok)).status_code == 401  # sessão em curso caiu
    assert entrar(client, "ana").status_code == 401
    assert client.delete(f"{PF}/{p['id']}/acesso", headers=h_full).status_code == 400
    assert auditorias(db, "profissional.revogar_acesso") and auditorias(db, "profissional.dar_acesso")

    # dar acesso de novo reaproveita o mesmo usuário e exige nova senha
    r = client.post(f"{PF}/{p['id']}/acesso", headers=h_full, json={"perfil_acesso_id": perfil_id(db, "Professor"), "login": "ana"})
    assert r.status_code == 200 and r.json()["usuario_id"] == u.id and r.json()["convite_pendente"] is True
    assert entrar(client, "ana").status_code == 401


def test_dar_acesso_exige_email(client, db, h_full):
    p = client.post(PF, headers=h_full, json={"nome": "Sem Email"}).json()
    r = client.post(f"{PF}/{p['id']}/acesso", headers=h_full, json={"perfil_acesso_id": perfil_id(db, "Professor"), "login": "ana"})
    assert r.status_code == 422 and "e-mail" in r.json()["detail"]


def test_reenviar_convite(client, db, h_full, emails):
    p = client.post(PF, headers=h_full, json=base(acesso_sistema=True, perfil_acesso_id=perfil_id(db, "Professor"))).json()
    r = client.post(f"{PF}/{p['id']}/acesso/convite", headers=h_full)
    assert r.status_code == 200 and len(emails) == 2
    sem = client.post(PF, headers=h_full, json={"nome": "Sem Login"}).json()
    assert client.post(f"{PF}/{sem['id']}/acesso/convite", headers=h_full).status_code == 400


def test_administrador_nao_tira_o_proprio_acesso_nem_o_ultimo_admin(client, db, h_full):
    admin = db.scalar(select(Usuario).where(Usuario.email == "full@exemplo.com"))
    p = Profissional(nome="Dono", email="full@exemplo.com", usuario_id=admin.id)
    db.add(p)
    db.commit()
    r = client.delete(f"{PF}/{p.id}/acesso", headers=h_full)
    assert r.status_code == 400 and "próprio acesso" in r.json()["detail"]
    r = client.post(f"{PF}/{p.id}/desativar", headers=h_full)
    assert r.status_code == 400
    db.expire_all()
    assert db.get(Profissional, p.id).ativo is True

    # outro admin com profissional: não pode ser o último
    outro = criar_usuario(db, "Full", email="outro@exemplo.com")
    q = Profissional(nome="Outro", email="outro@exemplo.com", usuario_id=outro.id)
    db.add(q)
    db.commit()
    assert client.delete(f"{PF}/{q.id}/acesso", headers=h_full).status_code == 200  # há o admin logado


# -------------------------------------------------------------------------------------------- sincronização
def _com_acesso(client, db, h, perfil="Professor", **extra):
    return client.post(PF, headers=h, json=base(acesso_sistema=True, perfil_acesso_id=perfil_id(db, perfil), **extra)).json()


def test_editar_profissional_sincroniza_o_usuario(client, db, h_full, emails):
    p = _com_acesso(client, db, h_full)
    r = client.put(f"{PF}/{p['id']}", headers=h_full, json=base(nome="Ana Souza Lima", email="ana.lima@exemplo.com", celular="21 97777-6666",
                                                                perfil_acesso_id=perfil_id(db, "Secretária")))
    assert r.status_code == 200, r.text
    assert r.json()["perfil_acesso_nome"] == "Secretária" and r.json()["celular"] == "5521977776666"
    db.expire_all()
    u = db.get(Usuario, p["usuario_id"])
    assert (u.nome, u.email, u.telefone) == ("Ana Souza Lima", "ana.lima@exemplo.com", "5521977776666")
    assert u.perfil_acesso.nome == "Secretária" and u.token_version == 1
    assert db.get(Profissional, p["id"]).perfil_acesso_id == u.perfil_acesso_id
    sync = auditorias(db, "usuario.alterar")
    assert sync and "sincronizado" in sync[-1].descricao
    alterar = auditorias(db, "profissional.alterar")[-1]
    assert alterar.antes_json["nome"] == "Ana Souza" and alterar.depois_json["nome"] == "Ana Souza Lima"


def test_editar_email_para_um_ja_usado_por_outro_usuario_recusa(client, db, h_full):
    p = _com_acesso(client, db, h_full)
    criar_usuario(db, "Full", email="ocupado@exemplo.com")
    r = client.put(f"{PF}/{p['id']}", headers=h_full, json=base(email="ocupado@exemplo.com"))
    assert r.status_code == 409
    db.expire_all()
    assert db.get(Usuario, p["usuario_id"]).email == "ana@exemplo.com"


def test_nao_pode_apagar_o_email_de_quem_tem_acesso(client, db, h_full):
    p = _com_acesso(client, db, h_full)
    assert client.put(f"{PF}/{p['id']}", headers=h_full, json=base(email=None)).status_code == 422


def test_desativar_profissional_derruba_o_login_e_reativar_devolve(client, db, h_full):
    p = _com_acesso(client, db, h_full)
    u = db.get(Usuario, p["usuario_id"])
    u.senha_hash = criar_usuario(db, "Full", email="tmp@exemplo.com").senha_hash
    db.commit()
    tok = entrar(client, "ana").json()["access_token"]
    assert client.post(f"{PF}/{p['id']}/desativar", headers=h_full).json()["ativo"] is False
    db.expire_all()
    assert db.get(Usuario, u.id).ativo is False
    assert client.get("/api/auth/me", headers=auth(tok)).status_code == 401
    assert client.post(f"{PF}/{p['id']}/ativar", headers=h_full).json()["ativo"] is True
    db.expire_all()
    assert db.get(Usuario, u.id).ativo is True
    assert entrar(client, "ana").status_code == 200
    assert auditorias(db, "profissional.desativar") and auditorias(db, "profissional.ativar")


def test_editar_sem_acesso_nao_mexe_em_usuario_nenhum(client, db, h_full):
    p = client.post(PF, headers=h_full, json=base()).json()
    r = client.put(f"{PF}/{p['id']}", headers=h_full, json=base(nome="Ana S.", comissao_percentual="45.5"))
    assert r.status_code == 200 and r.json()["nome"] == "Ana S." and r.json()["usuario_id"] is None


# -------------------------------------------------------------------------------------------- lista
def test_lista_busca_filtros_ordem_e_contagens(client, db, h_full):
    _com_acesso(client, db, h_full)
    client.post(PF, headers=h_full, json=base(nome="Bruno Dias", email="bruno@exemplo.com", celular="31 91111-2222", crefito="MG-99", comissao_percentual="50"))
    c = client.post(PF, headers=h_full, json=base(nome="Carla Reis", email="carla@exemplo.com", celular=None, ativo=False)).json()
    t = client.get(PF, headers=h_full).json()
    assert t["total"] == 3 and t["contagens"] == {"ativos": 2, "inativos": 1, "todos": 3}
    assert [i["nome"] for i in t["itens"]] == ["Ana Souza", "Bruno Dias", "Carla Reis"]
    assert client.get(PF, headers=h_full, params={"acesso": "com"}).json()["total"] == 1
    assert client.get(PF, headers=h_full, params={"acesso": "sem"}).json()["total"] == 2
    assert client.get(PF, headers=h_full, params={"situacao": "inativos"}).json()["itens"][0]["id"] == c["id"]
    assert client.get(PF, headers=h_full, params={"q": "mg-99"}).json()["total"] == 1
    assert client.get(PF, headers=h_full, params={"q": "91111"}).json()["total"] == 1  # busca por celular
    assert client.get(PF, headers=h_full, params={"q": "carla@"}).json()["total"] == 1
    top = client.get(PF, headers=h_full, params={"ordenar": "comissao", "direcao": "desc"}).json()["itens"][0]
    assert top["nome"] == "Bruno Dias"
    ana = client.get(PF, headers=h_full, params={"q": "ana"}).json()["itens"][0]
    assert ana["perfil_acesso_nome"] == "Professor" and ana["acesso_sistema"] is True
    assert client.get(PF, headers=h_full, params={"acesso": "talvez"}).status_code == 422


def test_perfis_de_acesso_para_o_formulario(client, h_full):
    nomes = [p["nome"] for p in client.get(f"{PF}/perfis-acesso", headers=h_full).json()]
    assert nomes[0] == "Full" and set(nomes) == {"Full", "Professor", "Secretária"}


# -------------------------------------------------------------------------------------------- exclusão
def test_excluir_profissional_sem_vinculos(client, db, h_full):
    p = client.post(PF, headers=h_full, json=base()).json()
    assert client.delete(f"{PF}/{p['id']}", headers=h_full).status_code == 200
    assert client.get(f"{PF}/{p['id']}", headers=h_full).status_code == 404
    assert auditorias(db, "profissional.excluir")


def test_excluir_profissional_com_login_desativa_o_usuario(client, db, h_full):
    p = _com_acesso(client, db, h_full)
    assert client.delete(f"{PF}/{p['id']}", headers=h_full).status_code == 200
    u = db.get(Usuario, p["usuario_id"])
    db.refresh(u)
    assert u.ativo is False and u.acesso_sistema is False


def test_profissional_com_aulas_nao_exclui_e_sugere_desativar(client, db, h_full):
    p = client.post(PF, headers=h_full, json=base()).json()
    un, ts = Unidade(nome="Matriz"), TipoServico(nome="Pilates")
    db.add_all([un, ts])
    db.flush()
    from datetime import time

    db.add(AulaSessao(unidade_id=un.id, tipo_servico_id=ts.id, profissional_id=p["id"], data=date(2026, 2, 2),
                      hora_inicio=time(9), hora_fim=time(10)))
    db.commit()
    v = client.get(f"{PF}/{p['id']}/vinculos", headers=h_full).json()
    assert v["total"] == 1 and v["pode_excluir"] is False
    r = client.delete(f"{PF}/{p['id']}", headers=h_full)
    assert r.status_code == 409 and "1 aula" in r.json()["detail"] and "Desative" in r.json()["detail"]
    assert db.get(Profissional, p["id"]) is not None


# -------------------------------------------------------------------------------------------- escopo do Professor
def test_resolvedor_liga_usuario_ao_profissional(client, db, h_full):
    p = _com_acesso(client, db, h_full)
    u = db.get(Usuario, p["usuario_id"])
    assert escopo.resolver_profissional_id(db, u) == p["id"]
    outro = criar_usuario(db, "Professor", email="sem-vinculo@exemplo.com")
    assert escopo.resolver_profissional_id(db, outro) is None


def test_professor_so_ve_as_proprias_aulas_via_contexto(client, db, h_full):
    p1 = _com_acesso(client, db, h_full)
    p2 = _com_acesso(client, db, h_full, nome="Bia Rocha", email="bia@exemplo.com", login="bia")
    prof1 = db.get(Usuario, p1["usuario_id"])
    ctx = Contexto(db=db, usuario=prof1, ip=None)
    assert ctx.somente_proprias_aulas() and ctx.profissional_id() == p1["id"]
    assert escopo.pode_acessar_profissional(ctx, p1["id"]) and not escopo.pode_acessar_profissional(ctx, p2["id"])

    un, ts = Unidade(nome="Matriz"), TipoServico(nome="Pilates")
    db.add_all([un, ts])
    db.flush()
    from datetime import time

    for i, pid in enumerate([p1["id"], p2["id"], p1["id"]]):
        db.add(AulaSessao(unidade_id=un.id, tipo_servico_id=ts.id, profissional_id=pid, data=date(2026, 2, 2),
                          hora_inicio=time(8 + i), hora_fim=time(9 + i)))
    db.commit()
    q = escopo.filtrar_proprias(ctx, select(AulaSessao.id), AulaSessao.profissional_id)
    assert len(list(db.scalars(q))) == 2
    admin = db.scalar(select(Usuario).where(Usuario.email == "full@exemplo.com"))
    admin_ctx = Contexto(db=db, usuario=admin, ip=None)
    assert len(list(db.scalars(escopo.filtrar_proprias(admin_ctx, select(AulaSessao.id), AulaSessao.profissional_id)))) == 3


def test_professor_sem_vinculo_nao_enxerga_nada(db):
    prof = criar_usuario(db, "Professor", email="solto@exemplo.com")
    ctx = Contexto(db=db, usuario=prof, ip=None)
    assert ctx.profissional_id() is None and not escopo.pode_acessar_profissional(ctx, 1)


def test_acesso_revogado_mantem_vinculo_para_o_historico(client, db, h_full):
    p = _com_acesso(client, db, h_full)
    client.delete(f"{PF}/{p['id']}/acesso", headers=h_full)
    u = db.get(Usuario, p["usuario_id"])
    assert escopo.resolver_profissional_id(db, u) == p["id"]


# -------------------------------------------------------------------------------------------- Minha conta
def test_meu_cadastro_edita_os_proprios_dados(client, db, h_full):
    p = _com_acesso(client, db, h_full)
    u = db.get(Usuario, p["usuario_id"])
    u.senha_hash = criar_usuario(db, "Full", email="tmp@exemplo.com").senha_hash
    db.commit()
    h = auth(entrar(client, "ana").json()["access_token"])  # Professor: sem permissão de cadastros
    assert client.get(PF, headers=h).status_code == 403
    me = client.get(f"{PF}/meu", headers=h).json()
    assert me["id"] == p["id"] and me["nome"] == "Ana Souza" and "comissao_percentual" not in me
    r = client.patch(f"{PF}/meu", headers=h, json={"nome": "Ana S. Lima", "celular": "11 95555-4444", "crefito": "NOVO-1", "data_nascimento": "1991-01-02"})
    assert r.status_code == 200 and r.json()["celular"] == "5511955554444"
    db.expire_all()
    assert db.get(Profissional, p["id"]).nome == "Ana S. Lima"
    assert db.get(Profissional, p["id"]).comissao_percentual == 30  # não editável por aqui
    assert db.get(Usuario, u.id).nome == "Ana S. Lima" and db.get(Usuario, u.id).telefone == "5511955554444"
    assert auditorias(db, "profissional.alterar_proprio")
    # e-mail/comissão/ativo enviados são ignorados
    client.patch(f"{PF}/meu", headers=h, json={"nome": "Ana S. Lima", "email": "hack@exemplo.com", "comissao_percentual": 99})
    db.expire_all()
    assert db.get(Profissional, p["id"]).email == "ana@exemplo.com" and db.get(Profissional, p["id"]).comissao_percentual == 30


def test_meu_cadastro_de_quem_nao_e_profissional(client, h_full):
    assert client.get(f"{PF}/meu", headers=h_full).json() is None
    r = client.patch(f"{PF}/meu", headers=h_full, json={"nome": "Alguém"})
    assert r.status_code == 404 and "profissional" in r.json()["detail"]
