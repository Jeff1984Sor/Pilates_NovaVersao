"""Permissões por perfil (Full / Professor / Secretária) em todos os cadastros-base; sem login = 401."""

import pytest

from app.core.permissoes import permissao_da_rota

RECURSOS = {
    "/api/cadastros/unidades": {"nome": "Matriz"},
    "/api/cadastros/servicos": {"nome": "Pilates"},
    "/api/cadastros/profissionais": {"nome": "Ana Souza"},
    "/api/cadastros/profissoes": {"nome": "Advogada"},
    "/api/planos": None,  # precisa de tipo de serviço; testado à parte
}


@pytest.mark.parametrize("caminho", list(RECURSOS) + ["/api/planos/opcoes"])
def test_sem_login_e_401(client, caminho):
    assert client.get(caminho).status_code == 401


@pytest.mark.parametrize("caminho", list(RECURSOS) + ["/api/planos/opcoes", "/api/cadastros/profissionais/perfis-acesso"])
def test_professor_nao_acessa_nenhum_cadastro(client, h_professor, caminho):
    assert client.get(caminho, headers=h_professor).status_code == 403
    if caminho in RECURSOS:
        assert client.post(caminho, headers=h_professor, json={"nome": "Invasor"}).status_code == 403
        assert client.get(f"{caminho}/1", headers=h_professor).status_code == 403
        assert client.delete(f"{caminho}/1", headers=h_professor).status_code == 403


@pytest.mark.parametrize("caminho", ["/api/cadastros/unidades", "/api/cadastros/servicos", "/api/cadastros/profissionais",
                                     "/api/cadastros/profissoes", "/api/planos"])
def test_secretaria_so_consulta(client, h_secretaria, h_full, caminho):
    assert client.get(caminho, headers=h_secretaria).status_code == 200
    assert client.post(caminho, headers=h_secretaria, json={"nome": "Nova"}).status_code == 403
    # cria como Full para testar edição/exclusão negadas à Secretária
    corpo = RECURSOS[caminho] or {"nome": "Plano", "tipo_servico_id": 1, "valor": "100"}
    if caminho == "/api/planos":
        client.post("/api/cadastros/servicos", headers=h_full, json={"nome": "Pilates"})
    r = client.post(caminho, headers=h_full, json=corpo)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert client.get(f"{caminho}/{rid}", headers=h_secretaria).status_code == 200
    assert client.put(f"{caminho}/{rid}", headers=h_secretaria, json=corpo).status_code == 403
    assert client.delete(f"{caminho}/{rid}", headers=h_secretaria).status_code == 403
    if caminho not in ("/api/cadastros/profissoes",):
        assert client.post(f"{caminho}/{rid}/desativar", headers=h_secretaria).status_code == 403
        assert client.post(f"{caminho}/{rid}/ativar", headers=h_secretaria).status_code == 403
    assert client.get(f"{caminho}/{rid}/vinculos", headers=h_secretaria).status_code == 200


def test_secretaria_nao_duplica_plano_nem_da_acesso(client, h_secretaria, h_full):
    client.post("/api/cadastros/servicos", headers=h_full, json={"nome": "Pilates"})
    p = client.post("/api/planos", headers=h_full, json={"nome": "Plano X", "tipo_servico_id": 1, "valor": "100"}).json()
    assert client.post(f"/api/planos/{p['id']}/duplicar", headers=h_secretaria).status_code == 403
    pf = client.post("/api/cadastros/profissionais", headers=h_full, json={"nome": "Ana Souza", "email": "a@exemplo.com"}).json()
    assert client.post(f"/api/cadastros/profissionais/{pf['id']}/acesso", headers=h_secretaria, json={"perfil_acesso_id": 1}).status_code == 403
    assert client.delete(f"/api/cadastros/profissionais/{pf['id']}/acesso", headers=h_secretaria).status_code == 403
    assert client.get("/api/planos/opcoes", headers=h_secretaria).status_code == 200


def test_full_faz_tudo(client, h_full):
    assert client.post("/api/cadastros/unidades", headers=h_full, json={"nome": "Matriz"}).status_code == 201
    assert client.get("/api/cadastros/profissionais/perfis-acesso", headers=h_full).status_code == 200


def test_mapa_de_permissoes_das_rotas():
    assert permissao_da_rota("GET", "/api/cadastros/unidades") == (True, "cadastros_unidades.ver")
    assert permissao_da_rota("DELETE", "/api/cadastros/unidades/3") == (True, "cadastros_unidades.excluir")
    assert permissao_da_rota("POST", "/api/cadastros/servicos/3/desativar") == (True, "cadastros_servicos.editar")
    assert permissao_da_rota("POST", "/api/planos/3/duplicar") == (True, "planos.editar")
    assert permissao_da_rota("GET", "/api/planos/opcoes") == (True, "planos.ver")
    assert permissao_da_rota("PUT", "/api/cadastros/profissoes/3") == (True, "cadastros_profissionais.editar")
    assert permissao_da_rota("DELETE", "/api/cadastros/profissionais/3/acesso") == (True, "cadastros_profissionais.editar")
    assert permissao_da_rota("DELETE", "/api/cadastros/profissionais/3") == (True, "cadastros_profissionais.excluir")
    assert permissao_da_rota("PATCH", "/api/cadastros/profissionais/meu") == (True, None)  # basta estar logado
