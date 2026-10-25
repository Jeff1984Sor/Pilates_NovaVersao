"""Token do aluno: expira, tem tipo próprio e nunca abre rota da equipe (nem o contrário)."""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.modules.alunos.models import StatusAluno
from app.modules.app_aluno import servico as srv
from tests.app_aluno.conftest import cab, entrar_aluno
from tests.conftest import auth, criar_usuario, entrar


def _claims(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience=srv.AUDIENCIA)


def test_access_dura_12h_e_refresh_7_dias(client, zap, cenario):
    t = entrar_aluno(client, zap, cenario.ana)
    a, r = _claims(t["access_token"]), _claims(t["refresh_token"])
    assert a["exp"] - a["iat"] == 12 * 3600 and a["typ"] == "aluno_access" and a["sub"] == str(cenario.ana.id)
    assert r["exp"] - r["iat"] == 7 * 86400 and r["typ"] == "aluno_refresh"


def test_token_expirado_e_recusado(client, cenario):
    velho = srv.emitir_tokens(cenario.ana.id, agora=datetime.now(UTC) - timedelta(hours=13))
    r = client.get("/api/aluno-app/me", headers=cab(velho))
    assert r.status_code == 401


def test_sem_token_ou_token_lixo_401(client, cenario):
    assert client.get("/api/aluno-app/me").status_code == 401
    assert client.get("/api/aluno-app/aulas", headers={"Authorization": "Bearer abc"}).status_code == 401


def test_token_assinado_com_outro_segredo_401(client, cenario):
    falso = jwt.encode(
        {"sub": str(cenario.ana.id), "typ": "aluno_access", "aud": srv.AUDIENCIA, "exp": datetime.now(UTC) + timedelta(hours=1), "jti": "x"},
        "outro-segredo-qualquer-com-32-caracteres!!",
        algorithm="HS256",
    )
    assert client.get("/api/aluno-app/me", headers={"Authorization": f"Bearer {falso}"}).status_code == 401


def test_token_da_equipe_nao_abre_o_app_do_aluno(client, db, cenario):
    criar_usuario(db, "Full", email="full@exemplo.com")
    equipe = entrar(client, "full@exemplo.com").json()["access_token"]
    assert client.get("/api/aluno-app/me", headers=auth(equipe)).status_code == 401
    assert client.get("/api/aluno-app/aulas", headers=auth(equipe)).status_code == 401


def test_token_do_aluno_nao_abre_rotas_da_equipe(client, zap, cenario):
    h = cab(entrar_aluno(client, zap, cenario.ana))
    for caminho in ("/api/alunos", "/api/auth/me", "/api/agenda/grade", "/api/aulas/painel", "/api/config/ia", "/api/financeiro/receber"):
        assert client.get(caminho, headers=h).status_code == 401, caminho


def test_refresh_nao_serve_como_access_e_vice_versa(client, zap, cenario):
    t = entrar_aluno(client, zap, cenario.ana)
    assert client.get("/api/aluno-app/me", headers={"Authorization": f"Bearer {t['refresh_token']}"}).status_code == 401
    assert client.post("/api/aluno-app/auth/refresh", json={"refresh_token": t["access_token"]}).status_code == 401


def test_refresh_renova_o_par(client, zap, cenario):
    t = entrar_aluno(client, zap, cenario.ana)
    r = client.post("/api/aluno-app/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r.status_code == 200
    novo = r.json()
    assert novo["access_token"] != t["access_token"]
    assert client.get("/api/aluno-app/me", headers=cab(novo)).status_code == 200


def test_refresh_vencido_401(client, cenario):
    velho = srv.emitir_tokens(cenario.ana.id, agora=datetime.now(UTC) - timedelta(days=8))
    assert client.post("/api/aluno-app/auth/refresh", json={"refresh_token": velho["refresh_token"]}).status_code == 401


def test_aluno_inativado_perde_o_acesso_na_hora(client, db, zap, cenario):
    t = entrar_aluno(client, zap, cenario.ana)
    cenario.ana.status = StatusAluno.INATIVO
    db.commit()
    assert client.get("/api/aluno-app/me", headers=cab(t)).status_code == 401
    assert client.post("/api/aluno-app/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_me(client, ana_logada):
    r = client.get("/api/aluno-app/me", headers=ana_logada)
    assert r.json() == {"nome": "Ana Paula Souza", "primeiro_nome": "Ana", "unidade": "Matriz"}
