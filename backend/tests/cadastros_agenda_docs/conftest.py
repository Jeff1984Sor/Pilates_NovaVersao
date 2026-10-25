"""Fixtures dos cadastros de agenda e documentos.

O `routes.py` do módulo `cadastros` é do coordenador (une este agente ao outro). Enquanto ele não existe, os testes
incluem o `router` de `routes_agenda_docs` no app; se o coordenador já o incluiu, nada é feito.
"""

from datetime import time

import pytest
from fastapi import Depends

from app.core.deps import get_contexto
from app.main import app
from app.modules import registrar_modelos
from app.modules.cadastros.models import Profissional, TipoServico, Unidade
from app.modules.cadastros.routes_agenda_docs import router as router_agenda_docs
from tests.conftest import auth, criar_usuario, entrar

registrar_modelos()


def _ja_incluido() -> bool:
    contextos = []
    for r in app.routes:
        if hasattr(r, "effective_route_contexts"):
            contextos.extend(r.effective_route_contexts())
        else:
            contextos.append(r)
    return any(getattr(r, "path", "").startswith("/api/cadastros/fornecedores") for r in contextos)


if not _ja_incluido():
    app.include_router(router_agenda_docs, prefix="/api", dependencies=[Depends(get_contexto)])


def _token(client, db, perfil: str) -> dict:
    email = f"{perfil.lower().replace('á', 'a').replace('ç', 'c')}@exemplo.com"
    criar_usuario(db, perfil, email=email)
    return auth(entrar(client, email).json()["access_token"])


@pytest.fixture
def full(client, db):
    return _token(client, db, "Full")


@pytest.fixture
def professor(client, db):
    return _token(client, db, "Professor")


@pytest.fixture
def secretaria(client, db):
    return _token(client, db, "Secretária")


@pytest.fixture
def base(db):
    """Uma unidade, dois serviços e um profissional (cadastros do outro agente, criados direto no banco)."""
    u = Unidade(nome="Studio Centro", capacidade=6, duracao_aula_minutos=50)
    s1, s2 = TipoServico(nome="Pilates"), TipoServico(nome="Fisioterapia")
    p = Profissional(nome="Dra. Ana Lima")
    db.add_all([u, s1, s2, p])
    db.commit()
    return {"unidade": u.id, "servico": s1.id, "servico2": s2.id, "profissional": p.id}


def faixa(ini: str = "08:00", fim: str = "12:00") -> dict:
    return {"hora_inicio": ini, "hora_fim": fim}


HORA = time
