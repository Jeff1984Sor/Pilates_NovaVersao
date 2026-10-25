"""Fixtures dos cadastros-base. As rotas são montadas no app de teste aqui; o coordenador as inclui no `routes.py` do pacote."""

import pytest
from fastapi import Depends

from app.core import escopo
from app.core.deps import get_contexto
from app.main import app
from app.modules import registrar_modelos
from tests.conftest import auth, criar_usuario, entrar  # noqa: F401  (reexportados para os testes)

registrar_modelos()


@pytest.fixture(scope="session", autouse=True)
def _montar_rotas():
    from app.modules.cadastros import routes_base

    if not getattr(app.state, "cadastros_base_montado", False):
        app.include_router(routes_base.router, prefix="/api", dependencies=[Depends(get_contexto)])
        app.state.cadastros_base_montado = True
    escopo.registrar_resolvedor_profissional(escopo._sem_resolvedor)  # o import registrou o real; cada teste o liga


@pytest.fixture(autouse=True)
def _resolvedor_do_professor():
    from app.modules.cadastros import vinculo_usuario

    vinculo_usuario.registrar_escopo()
    yield
    escopo.registrar_resolvedor_profissional(escopo._sem_resolvedor)


def token_de(client, db, perfil: str, email: str) -> dict:
    criar_usuario(db, perfil, email=email)
    return auth(entrar(client, email).json()["access_token"])


@pytest.fixture
def h_full(client, db):
    return token_de(client, db, "Full", "full@exemplo.com")


@pytest.fixture
def h_secretaria(client, db):
    return token_de(client, db, "Secretária", "secretaria@exemplo.com")


@pytest.fixture
def h_professor(client, db):
    return token_de(client, db, "Professor", "professor@exemplo.com")


def auditorias(db, acao: str):
    from sqlalchemy import select

    from app.core.models import Auditoria

    return list(db.scalars(select(Auditoria).where(Auditoria.acao == acao).order_by(Auditoria.id)))
