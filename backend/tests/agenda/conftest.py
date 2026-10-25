"""Fixtures da agenda: modelos registrados e cenário mínimo (unidade, serviço, professor, alunos)."""

from datetime import UTC, datetime, time

import pytest
from sqlalchemy import select

from app.core import escopo
from app.modules import registrar_modelos

registrar_modelos()

from tests.agenda import fabrica  # noqa: E402


class Cenario:
    pass


@pytest.fixture
def cenario(db):
    """Unidade com 2 vagas, serviço, uma professora, duas alunas e uma aula em 26/10/2026 (segunda) às 09:00."""
    un = fabrica.unidade(db, capacidade=2)
    srv = fabrica.servico(db)
    prof = fabrica.profissional(db)
    a1 = fabrica.aluno(db, un, "Ana Paula")
    a2 = fabrica.aluno(db, un, "Bruna Lima")
    ses = fabrica.sessao(db, un, srv, prof)
    db.commit()
    c = Cenario()
    c.un, c.srv, c.prof, c.a1, c.a2, c.ses = un, srv, prof, a1, a2, ses
    return c


#: "agora" fixo dos testes de API (domingo 25/10/2026 15:00 em Brasília): a aula do cenário (seg 26/10 09:00) é futura
AGORA_FIXO = datetime(2026, 10, 25, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _relogio_e_resolvedor(monkeypatch):
    """Congela o relógio da API e registra o resolvedor usuário->profissional (o real vem do módulo de cadastros)."""
    from app.modules.agenda import routes
    from app.modules.cadastros.models import Profissional

    monkeypatch.setattr(routes, "_agora", lambda: AGORA_FIXO)
    antigo = escopo._resolvedor
    escopo.registrar_resolvedor_profissional(
        lambda db, u: db.scalar(select(Profissional.id).where(Profissional.usuario_id == u.id))
    )
    yield
    escopo.registrar_resolvedor_profissional(antigo)


@pytest.fixture
def full(client, db):
    """Token do perfil Full."""
    from tests.conftest import criar_usuario, entrar

    criar_usuario(db, "Full", email="full@exemplo.com")
    return entrar(client, "full@exemplo.com").json()["access_token"]


@pytest.fixture
def secretaria(client, db):
    from tests.conftest import criar_usuario, entrar

    criar_usuario(db, "Secretária", email="sec@exemplo.com")
    return entrar(client, "sec@exemplo.com").json()["access_token"]


@pytest.fixture
def professor(client, db, cenario):
    """Token da professora do cenário (usuário vinculado ao profissional da aula)."""
    from tests.conftest import criar_usuario, entrar

    u = criar_usuario(db, "Professor", email="prof@exemplo.com")
    cenario.prof.usuario_id = u.id
    db.commit()
    return entrar(client, "prof@exemplo.com").json()["access_token"]


@pytest.fixture
def outro_professor(client, db, cenario):
    """Segunda professora (com login) e uma aula só dela, com uma aluna só dela."""
    from tests.agenda import fabrica
    from tests.conftest import criar_usuario, entrar

    u = criar_usuario(db, "Professor", email="prof2@exemplo.com")
    p2 = fabrica.profissional(db, "Outra Professora", usuario_id=u.id)
    aluna = fabrica.aluno(db, cenario.un, "Aluna Alheia")
    ses = fabrica.sessao(db, cenario.un, cenario.srv, p2, inicio=time(10, 0))
    db.commit()
    from app.modules.agenda import servico

    r = servico.criar_reserva(db, aluna.id, ses.id)
    db.commit()

    class Outro:
        pass

    o = Outro()
    o.token, o.prof, o.aluna, o.ses, o.reserva = entrar(client, "prof2@exemplo.com").json()["access_token"], p2, aluna, ses, r
    return o
