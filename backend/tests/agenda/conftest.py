"""Fixtures da agenda: modelos registrados e cenário mínimo (unidade, serviço, professor, alunos)."""

import pytest

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
