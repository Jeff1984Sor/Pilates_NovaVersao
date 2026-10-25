"""Desempenho: o painel faz poucas consultas, não importa o volume de dados (agregação no banco)."""

from sqlalchemy import event

from app.core.db import engine

URL = "/api/painel/resumo"
LIMITE_FULL = 18  # medido: 15 (inclui a autenticação do usuário); folga pequena para não crescer sem notar


class _Contador:
    def __init__(self):
        self.consultas: list[str] = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            self.consultas.append(statement)


def _contar(client, headers) -> tuple[int, list[str]]:
    c = _Contador()
    event.listen(engine, "before_cursor_execute", c)
    try:
        r = client.get(URL, headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", c)
    assert r.status_code == 200
    return len(c.consultas), c.consultas


def test_numero_de_consultas_limitado(client, mundo, full):
    n, consultas = _contar(client, full)
    assert n <= LIMITE_FULL, "\n\n".join(consultas)


def test_consultas_nao_crescem_com_o_volume(client, db, mundo, full):
    """Mais alunos, aulas e contas não aumentam o número de consultas (nada de N+1)."""
    from datetime import date, time
    from decimal import Decimal

    from app.modules.agenda import servico as agenda
    from tests.agenda import fabrica
    from tests.painel.conftest import mk_aluno, mk_conta

    antes, _ = _contar(client, full)
    s = fabrica.sessao(db, mundo.un, mundo.srv, mundo.p2, date(2026, 10, 25), time(21, 0), capacidade=60)
    for n in range(50):
        a = mk_aluno(db, mundo.un, f"Volume {n:02d}", 200 + n, date(1990, 10, 27))
        agenda.criar_reserva(db, a.id, s.id)
        mk_conta(db, a, Decimal("10.00"), date(2026, 10, 1))
    db.commit()
    depois, _ = _contar(client, full)
    assert depois == antes


def test_professor_faz_menos_consultas(client, db, mundo):
    from tests.painel.conftest import novo_professor_logado

    h, _ = novo_professor_logado(client, db)
    n, _ = _contar(client, h)
    assert n <= 10
