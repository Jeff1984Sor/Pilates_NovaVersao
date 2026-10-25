"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (comissao).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
PERCENTUAIS = {1: Decimal('10.00'), 2: Decimal('12.50'), 3: None, 4: Decimal('0.00')}

# valor gerado pelo sistema antigo em 2026-10-25
CONTAS = [
    (1, 1, None, 'pago', date(2026, 10, 5), '300.00'),
    (2, None, 2, 'pago', date(2026, 10, 6), '33.33'),
    (3, 1, None, 'pago', date(2026, 10, 7), '100.10'),
    (4, 1, None, 'aberto', None, '500.00'),
    (5, 1, None, 'pago', date(2026, 9, 30), '100.00'),
    (6, 1, None, 'pago', date(2026, 11, 1), '100.00'),
    (7, None, 3, 'pago', date(2026, 10, 8), '100.00'),
    (8, None, 4, 'pago', date(2026, 10, 9), '100.00'),
    (9, None, None, 'pago', date(2026, 10, 10), '100.00'),
    (10, 2, 1, 'pago', date(2026, 10, 11), '200.00'),
    (11, 1, None, 'pago', date(2026, 10, 12), '0.05'),
    (12, 2, None, 'pago', date(2026, 10, 31), '250.00'),
    (13, 1, None, 'vencido', None, '80.00'),
    (14, 1, None, 'cancelado', None, '80.00'),
]

# valor gerado pelo sistema antigo em 2026-10-25
CONTA_JA_GERADA = 3

# valor gerado pelo sistema antigo em 2026-10-25
PRIMEIRA = {'competencia': '2026-10', 'geradas': 5, 'valor_total': 85.43}

# valor gerado pelo sistema antigo em 2026-10-25
GERADAS = [
    (1, 1, 1, date(2026, 10, 1), Decimal('300.00'), Decimal('10.00'), Decimal('30.00'), 'pendente'),
    (2, 2, None, date(2026, 10, 1), Decimal('33.33'), Decimal('12.50'), Decimal('4.17'), 'pendente'),
    (3, 1, 1, date(2026, 10, 1), Decimal('100.10'), Decimal('10.00'), Decimal('10.01'), 'pendente'),
    (10, 1, 2, date(2026, 10, 1), Decimal('200.00'), Decimal('10.00'), Decimal('20.00'), 'pendente'),
    (11, 1, 1, date(2026, 10, 1), Decimal('0.05'), Decimal('10.00'), Decimal('0.01'), 'pendente'),
    (12, 2, 2, date(2026, 10, 1), Decimal('250.00'), Decimal('12.50'), Decimal('31.25'), 'pendente'),
]

# valor gerado pelo sistema antigo em 2026-10-25
SEGUNDA = {'competencia': '2026-10', 'geradas': 0, 'valor_total': 0.0}

# valor gerado pelo sistema antigo em 2026-10-25
OUTRO_MES = {'competencia': '2026-11', 'geradas': 1, 'valor_total': 10.0}

# valor gerado pelo sistema antigo em 2026-10-25
COMPETENCIAS = [
    ('2026-10', date(2026, 10, 1), date(2026, 11, 1), None),
    ('2026-12', date(2026, 12, 1), date(2027, 1, 1), None),
    ('2026-01', date(2026, 1, 1), date(2026, 2, 1), None),
    ('2026-13', None, None, (422, 'competencia invalida (use YYYY-MM)')),
    ('2026-00', None, None, (422, 'competencia invalida (use YYYY-MM)')),
    ('abc', None, None, (422, 'competencia invalida (use YYYY-MM)')),
    ('', None, None, (422, 'competencia invalida (use YYYY-MM)')),
    ('2026', None, None, (422, 'competencia invalida (use YYYY-MM)')),
    ('2026-1', date(2026, 1, 1), date(2026, 2, 1), None),
    ('2026-10-01', None, None, (422, 'competencia invalida (use YYYY-MM)')),
    ('26-10', date(26, 10, 1), date(26, 11, 1), None),
    (None, None, None, (422, 'competencia invalida (use YYYY-MM)')),
]
