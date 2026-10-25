"""Permissões dos cadastros de agenda e documentos: Full, Professor e Secretária; cobertura de rotas e login."""

import re

import pytest
from fastapi.routing import APIRoute

from app.core.deps import get_contexto
from app.core.permissoes import permissao_da_rota
from app.main import app

PREFIXOS = (
    "/api/cadastros/fornecedores", "/api/cadastros/categorias", "/api/cadastros/horarios", "/api/cadastros/bloqueios",
    "/api/cadastros/termos", "/api/cadastros/modelos",
)

LEITURAS = [
    "/api/cadastros/fornecedores", "/api/cadastros/categorias", "/api/cadastros/categorias/subcategorias",
    "/api/cadastros/horarios", "/api/cadastros/horarios/studio", "/api/cadastros/horarios/opcoes",
    "/api/cadastros/bloqueios", "/api/cadastros/bloqueios/opcoes", "/api/cadastros/termos", "/api/cadastros/termos/variaveis",
    "/api/cadastros/modelos/variaveis", "/api/cadastros/modelos/contrato", "/api/cadastros/modelos/evolucao",
]
# (método, caminho, corpo mínimo válido): o perfil sem permissão tem de levar 403 ANTES de qualquer validação
ESCRITAS = [
    ("POST", "/api/cadastros/fornecedores", {"nome": "Fornecedor X"}),
    ("PUT", "/api/cadastros/fornecedores/1", {"nome": "Fornecedor Y"}),
    ("DELETE", "/api/cadastros/fornecedores/1", None),
    ("POST", "/api/cadastros/categorias", {"nome": "Cat X", "tipo": "DESPESA"}),
    ("POST", "/api/cadastros/categorias/subcategorias", {"categoria_id": 1, "nome": "Sub X"}),
    ("POST", "/api/cadastros/horarios/gerar", {"unidade_id": 1, "dias_semana": [0], "hora_inicio": "08:00", "hora_fim": "09:00"}),
    (
        "POST", "/api/cadastros/horarios/studio/gerar",
        {"unidade_id": 1, "tipo_servico_id": 1, "dias_semana": [0], "hora_inicio": "08:00", "hora_fim": "09:00", "intervalo_minutos": 30},
    ),
    ("DELETE", "/api/cadastros/horarios/1", None),
    ("DELETE", "/api/cadastros/bloqueios/1", None),
    ("POST", "/api/cadastros/termos", {"nome": "Termo X", "conteudo_html": "<p>x</p>"}),
    ("POST", "/api/cadastros/termos/1/duplicar", None),
    ("POST", "/api/cadastros/modelos/contrato", {"nome": "Modelo X", "conteudo_html": "<p>x</p>"}),
    ("POST", "/api/cadastros/modelos/contrato/1/duplicar", None),
    ("POST", "/api/cadastros/modelos/evolucao", {"titulo": "Evo X", "texto": "texto"}),
    ("DELETE", "/api/cadastros/modelos/evolucao/1", None),
]


def _pede(client, metodo, url, token, corpo=None):
    return client.request(metodo, url, json=corpo, headers=token)


@pytest.mark.parametrize("url", LEITURAS)
def test_sem_login_recusa(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", LEITURAS)
def test_professor_nao_ve_cadastros(client, professor, url):
    assert client.get(url, headers=professor).status_code == 403


@pytest.mark.parametrize("metodo,url,corpo", ESCRITAS)
def test_professor_nao_escreve_cadastros(client, professor, metodo, url, corpo):
    assert _pede(client, metodo, url, professor, corpo).status_code == 403


@pytest.mark.parametrize("url", LEITURAS)
def test_secretaria_consulta(client, secretaria, url):
    assert client.get(url, headers=secretaria).status_code == 200


FINANCEIRAS = ("/api/cadastros/fornecedores", "/api/cadastros/categorias")
FIN = [e for e in ESCRITAS if e[1].startswith(FINANCEIRAS)]
AGENDA_DOCS = [e for e in ESCRITAS if not e[1].startswith(FINANCEIRAS) and e[0] != "DELETE"]


@pytest.mark.parametrize("metodo,url,corpo", FIN)
def test_secretaria_nao_mexe_em_fornecedores_e_categorias(client, secretaria, metodo, url, corpo):
    """Cadastros financeiros continuam fora do alcance da Secretária (decisão do Jefferson)."""
    assert _pede(client, metodo, url, secretaria, corpo).status_code == 403


@pytest.mark.parametrize("metodo,url,corpo", AGENDA_DOCS)
def test_secretaria_edita_horarios_bloqueios_termos_e_modelos(client, secretaria, metodo, url, corpo):
    """Decisão do Jefferson: a Secretária edita horários (funcionamento e studio), bloqueios, termos e modelos.
    Aqui basta NÃO levar 403 (o recurso pode não existir ou o corpo ser recusado por outra regra)."""
    assert _pede(client, metodo, url, secretaria, corpo).status_code != 403


@pytest.mark.parametrize("url", LEITURAS)
def test_full_acessa_tudo(client, full, url):
    assert client.get(url, headers=full).status_code == 200


def test_previa_exige_so_ver_e_nao_grava(client, secretaria, professor):
    corpo = {"conteudo_html": "<p>{ALUNO_NOME}</p>"}
    for url in ("/api/cadastros/termos/previa", "/api/cadastros/modelos/contrato/previa"):
        assert client.post(url, json=corpo, headers=secretaria).status_code == 200
        assert client.post(url, json=corpo, headers=professor).status_code == 403


def test_professor_le_modelos_de_evolucao_ativos_para_a_gaveta(client, professor, secretaria, full):
    client.post("/api/cadastros/modelos/evolucao", json={"titulo": "Padrão", "texto": "Texto base"}, headers=full)
    r = client.get("/api/cadastros/modelos/evolucao/ativos", headers=professor)
    assert r.status_code == 200 and [m["titulo"] for m in r.json()] == ["Padrão"]
    assert client.get("/api/cadastros/modelos/evolucao/ativos", headers=secretaria).status_code == 200  # tem aulas.evoluir
    # mas a lista de gestão continua fechada para o Professor
    assert client.get("/api/cadastros/modelos/evolucao", headers=professor).status_code == 403
    assert client.get("/api/cadastros/modelos/contrato", headers=professor).status_code == 403


def test_perfil_com_so_ver_consulta_mas_nao_escreve(client, db):
    """Perfil customizado com apenas cadastros_horarios.ver: lê horários, não cria nem apaga, e não vê bloqueios."""
    from app.core.models import PerfilAcesso, Usuario
    from app.core.security import hash_senha
    from tests.conftest import SENHA, auth, entrar

    p = PerfilAcesso(nome="Leitura de horários", permissoes=["cadastros_horarios.ver"])
    db.add(p)
    db.flush()
    db.add(Usuario(nome="Leitor", email="leitor@exemplo.com", login="leitor", perfil_acesso_id=p.id, senha_hash=hash_senha(SENHA)))
    db.commit()
    tk = auth(entrar(client, "leitor@exemplo.com").json()["access_token"])
    assert client.get("/api/cadastros/horarios", headers=tk).status_code == 200
    gerar = {"unidade_id": 1, "dias_semana": [0], "hora_inicio": "08:00", "hora_fim": "09:00"}
    assert client.post("/api/cadastros/horarios/gerar", json=gerar, headers=tk).status_code == 403
    assert client.delete("/api/cadastros/horarios/1", headers=tk).status_code == 403
    assert client.get("/api/cadastros/bloqueios", headers=tk).status_code == 403


# ------------------------------------------------------------------------------------------------ cobertura das rotas
def _efetivas():
    for r in app.routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "effective_route_contexts"):
            yield from r.effective_route_contexts()


def _depende_de(dep, alvo) -> bool:
    return dep.call is alvo or any(_depende_de(d, alvo) for d in dep.dependencies)


def _minhas():
    for r in _efetivas():
        if r.path.startswith(PREFIXOS):
            caminho = re.sub(r"\{[^}]+\}", "1", r.path)
            for metodo in r.methods - {"HEAD", "OPTIONS"}:
                yield r, metodo, caminho


def test_minhas_rotas_existem_tem_login_e_regra_de_permissao():
    rotas = list(_minhas())
    assert len(rotas) >= 55
    sem_regra = [f"{m} {r.path}" for r, m, c in rotas if not permissao_da_rota(m, c)[0]]
    sem_login = [f"{m} {r.path}" for r, m, c in rotas if not _depende_de(r.dependant, get_contexto)]
    assert not sem_regra, sem_regra
    assert not sem_login, sem_login


def test_toda_escrita_exige_editar_ou_excluir():
    """Nenhuma rota que grava pode cair em permissão de 'ver' (as prévias são a exceção declarada)."""
    excecoes = {"/api/cadastros/termos/previa", "/api/cadastros/modelos/contrato/previa"}
    erradas = []
    for r, m, c in _minhas():
        _, perm = permissao_da_rota(m, c)
        if m != "GET" and r.path not in excecoes and perm and perm.endswith(".ver"):
            erradas.append(f"{m} {r.path} -> {perm}")
    assert not erradas, erradas
