"""Fixtures das integrações: perfis, cenário base (unidade, serviço, aluno) e cliente HTTP do TotalPass SEMPRE falso."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.modules import registrar_modelos
from tests.conftest import SENHA, auth, criar_usuario, entrar  # noqa: F401

registrar_modelos()

from app.modules.alunos.models import Aluno  # noqa: E402
from app.modules.cadastros.models import TipoServico, Unidade  # noqa: E402
from app.modules.integracoes import api_externa, totalpass  # noqa: E402


def cpf_valido(base: int) -> str:
    """CPF válido determinístico a partir de um número de 9 dígitos."""
    d = [int(c) for c in f"{base:09d}"]
    for _ in range(2):
        s = sum(v * w for v, w in zip(d, range(len(d) + 1, 1, -1), strict=False))
        d.append((s * 10 % 11) % 10)
    return "".join(map(str, d))


@pytest.fixture(autouse=True)
def _sem_internet():
    """Nenhum teste de integração chama a internet: o cliente do TotalPass real é trocado por um que explode."""

    def proibido():
        raise AssertionError("Teste tentou criar o cliente HTTP REAL do TotalPass (internet proibida nos testes).")

    totalpass.definir_fabrica_cliente(proibido)
    yield
    totalpass.definir_fabrica_cliente(None)


@pytest.fixture
def full(client, db):
    criar_usuario(db, "Full", email="full@exemplo.com", login="full")
    return auth(entrar(client, "full@exemplo.com").json()["access_token"])


@pytest.fixture
def secretaria(client, db):
    criar_usuario(db, "Secretária", email="sec@exemplo.com", login="sec")
    return auth(entrar(client, "sec@exemplo.com").json()["access_token"])


@pytest.fixture
def professor(client, db):
    criar_usuario(db, "Professor", email="prof@exemplo.com", login="prof")
    return auth(entrar(client, "prof@exemplo.com").json()["access_token"])


@pytest.fixture
def hoje_fixo(monkeypatch):
    """Fixa o 'hoje' da API externa em 05/10/2026 (segunda-feira)."""
    dia = date(2026, 10, 5)
    monkeypatch.setattr(api_externa, "hoje", lambda: dia)
    return dia


@pytest.fixture
def base(db) -> SimpleNamespace:
    un = Unidade(nome="Matriz", capacidade=2)
    srv = TipoServico(nome="Pilates")
    db.add_all([un, srv])
    db.flush()
    db.commit()
    return SimpleNamespace(unidade=un, servico=srv)


def novo_aluno(db, unidade_id: int, nome: str, n: int, **extra) -> Aluno:
    a = Aluno(nome=nome, cpf=cpf_valido(200000000 + n), unidade_id=unidade_id, codigo_legado=1000 + n, **extra)
    db.add(a)
    db.flush()
    return a



