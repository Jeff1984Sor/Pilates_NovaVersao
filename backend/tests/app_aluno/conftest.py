"""Fixtures do app do aluno: relógio congelado (domingo 25/10/2026 15:00 em Brasília), cenário sintético e login pelo código."""

import re
from datetime import UTC, datetime, time

import pytest

from app.modules import registrar_modelos

registrar_modelos()

from tests.agenda import fabrica  # noqa: E402

AGORA_FIXO = datetime(2026, 10, 25, 18, 0, tzinfo=UTC)


class Cenario:
    pass


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    from app.modules.app_aluno import routes

    monkeypatch.setattr(routes, "_agora", lambda: AGORA_FIXO)


@pytest.fixture
def cenario(db):
    """Unidade de 2 vagas, uma professora, a aluna Ana (reservada na seg 26/10 09:00) e a aluna Bruna (na seg 10:00)."""
    un = fabrica.unidade(db, capacidade=2)
    srv = fabrica.servico(db)
    prof = fabrica.profissional(db)
    ana = fabrica.aluno(db, un, "Ana Paula Souza", telefone="(11) 99999-0001")
    bruna = fabrica.aluno(db, un, "Bruna Lima", telefone="11999990002")
    s9 = fabrica.sessao(db, un, srv, prof)
    s10 = fabrica.sessao(db, un, srv, prof, inicio=time(10, 0))
    r_ana = fabrica.reserva_direta(db, ana, s9)
    r_bruna = fabrica.reserva_direta(db, bruna, s10)
    db.commit()
    c = Cenario()
    c.un, c.srv, c.prof, c.ana, c.bruna, c.s9, c.s10, c.r_ana, c.r_bruna = un, srv, prof, ana, bruna, s9, s10, r_ana, r_bruna
    return c


def cpf_mascarado(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def codigo_do_zap(zap, indice: int = -1) -> str:
    m = re.search(r"\b(\d{6})\b", zap.enviadas[indice][1])
    assert m, zap.enviadas[indice]
    return m.group(1)


def entrar_aluno(client, zap, aluno) -> dict:
    """Pede o código, lê no WhatsApp falso e verifica. Devolve os tokens."""
    assert client.post("/api/aluno-app/auth/codigo", json={"cpf": aluno.cpf}).status_code == 200
    r = client.post("/api/aluno-app/auth/verificar", json={"cpf": aluno.cpf, "codigo": codigo_do_zap(zap)})
    assert r.status_code == 200, r.text
    return r.json()


def cab(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def ana_logada(client, zap, cenario):
    return cab(entrar_aluno(client, zap, cenario.ana))


def _token_equipe(client, db, perfil: str, email: str) -> str:
    from tests.conftest import criar_usuario, entrar

    criar_usuario(db, perfil, email=email)
    return entrar(client, email).json()["access_token"]


@pytest.fixture
def full(client, db):
    return _token_equipe(client, db, "Full", "full@exemplo.com")


@pytest.fixture
def secretaria(client, db):
    return _token_equipe(client, db, "Secretária", "sec@exemplo.com")


@pytest.fixture
def professor(client, db):
    return _token_equipe(client, db, "Professor", "prof@exemplo.com")
