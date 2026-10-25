"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (reposicao).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
HOJE_APP = date(2026, 10, 25)

# valor gerado pelo sistema antigo em 2026-10-25
DESMARCAR_STAFF = [
    (
        date(2026, 10, 10),
        200,
        {'reserva_id': 1, 'status': 'CANCELADA', 'reposicao_ate': '2026-11-09'},
        'CANCELADA',
        None,
        True,
        date(2026, 11, 9),
    ),
    (
        date(2026, 12, 15),
        200,
        {'reserva_id': 2, 'status': 'CANCELADA', 'reposicao_ate': '2027-01-14'},
        'CANCELADA',
        None,
        True,
        date(2027, 1, 14),
    ),
    (
        date(2024, 2, 1),
        200,
        {'reserva_id': 3, 'status': 'CANCELADA', 'reposicao_ate': '2024-03-02'},
        'CANCELADA',
        None,
        True,
        date(2024, 3, 2),
    ),
    (
        date(2026, 1, 31),
        200,
        {'reserva_id': 4, 'status': 'CANCELADA', 'reposicao_ate': '2026-03-02'},
        'CANCELADA',
        None,
        True,
        date(2026, 3, 2),
    ),
]

# valor gerado pelo sistema antigo em 2026-10-25
ACOES = [
    ('chegou', 200, 'RESERVADA'),
    ('iniciar', 200, 'RESERVADA'),
    ('finalizar', 200, 'CONCLUIDA'),
    ('faltou', 200, 'FALTOU_SEM_AVISAR'),
    ('remarcar', 200, 'CANCELADA'),
    ('desmarcar', 200, 'CANCELADA'),
    ('xyz', 400, 'RESERVADA'),
    ('', 400, 'RESERVADA'),
]

# valor gerado pelo sistema antigo em 2026-10-25
PROFESSOR = [
    ('desmarcar', 403, 'RESERVADA'),
    ('remarcar', 403, 'RESERVADA'),
    ('finalizar', 200, 'CONCLUIDA'),
    ('faltou', 200, 'FALTOU_SEM_AVISAR'),
]

# valor gerado pelo sistema antigo em 2026-10-25
APP_ALUNO = [
    (
        'futura',
        'desmarcar',
        5,
        (
            'ok',
            {
                'ok': True,
                'reserva_id': 17,
                'reposicao_ate': '2026-11-29',
                'mensagem': 'Aula desmarcada. Voce pode repor ate 29/11/2026 (30 dias).',
            },
        ),
    ),
    ('futura', 'confirmar', 5, ('ok', {'ok': True, 'reserva_id': 17, 'confirmada': True})),
    (
        'hoje',
        'desmarcar',
        0,
        (
            'ok',
            {
                'ok': True,
                'reserva_id': 18,
                'reposicao_ate': '2026-11-24',
                'mensagem': 'Aula desmarcada. Voce pode repor ate 24/11/2026 (30 dias).',
            },
        ),
    ),
    ('hoje', 'confirmar', 0, ('ok', {'ok': True, 'reserva_id': 18, 'confirmada': True})),
    ('passada', 'desmarcar', -1, ('erro', 400, 'Nao e possivel desmarcar uma aula que ja passou')),
    ('passada', 'confirmar', -1, ('erro', 400, 'Aula ja passou')),
    ('cancelada', 'desmarcar', 5, ('erro', 400, 'Aula ja desmarcada')),
    ('cancelada', 'confirmar', 5, ('erro', 400, 'Aula cancelada')),
]
