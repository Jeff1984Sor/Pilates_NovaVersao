"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (documentos).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
CPFS = [
    ('529.982.247-25', True, True, '52998224725'),
    ('52998224725', True, True, '52998224725'),
    ('111.111.111-11', False, False, '11111111111'),
    ('123', False, False, '123'),
    ('', False, False, ''),
    (None, False, False, ''),
    ('390.533.447-05', True, True, '39053344705'),
    ('11144477735', True, True, '11144477735'),
    ('000.000.000-00', False, False, '00000000000'),
    ('529.982.247-24', False, False, '52998224724'),
    ('5299822472', False, False, '5299822472'),
    ('529982247250', False, False, '529982247250'),
    ('abc', False, False, ''),
    ('529 982 247 25', True, True, '52998224725'),
    ('123.456.789-09', True, True, '12345678909'),
    ('12345678909', True, True, '12345678909'),
    ('98765432100', True, True, '98765432100'),
]
