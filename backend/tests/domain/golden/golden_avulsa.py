"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (avulsa).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
CENARIOS = [
    {
        'rotulo': 'semanal_valor_do_plano',
        'plano': ('SEMANAL', '80'),
        'entrada': (3, '', date(2026, 11, 2), '0|09:00|09:50'),
        'pacote': {
            'recorrencia': 'SEMANAL',
            'quantidade': 3,
            'valor_aula': Decimal('80.00'),
            'valor_total': Decimal('80.00'),
            'inicio': date(2026, 11, 2),
            'fim': date(2026, 11, 23),
        },
        'mensagens': ['Aulas avulsas agendadas com sucesso.'],
        'contas': [
            (date(2026, 11, 2), '2026-45', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 9), '2026-46', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 16), '2026-47', Decimal('80.00'), 'ABERTO', None, True),
        ],
        'reservas': [
            (date(2026, 11, 2), 'Pilates'),
            (date(2026, 11, 9), 'Pilates'),
            (date(2026, 11, 16), 'Pilates'),
        ],
    },
    {
        'rotulo': 'mensal_valor_informado',
        'plano': ('MENSAL', '80'),
        'entrada': (3, '75.50', date(2026, 11, 2), '0|09:00|09:50'),
        'pacote': {
            'recorrencia': 'MENSAL',
            'quantidade': 3,
            'valor_aula': Decimal('75.50'),
            'valor_total': Decimal('75.50'),
            'inicio': date(2026, 11, 2),
            'fim': date(2027, 2, 2),
        },
        'mensagens': ['Aulas avulsas agendadas com sucesso.'],
        'contas': [
            (date(2026, 11, 2), '2026-11', Decimal('75.50'), 'ABERTO', None, True),
            (date(2026, 12, 2), '2026-12', Decimal('75.50'), 'ABERTO', None, True),
            (date(2027, 1, 2), '2027-01', Decimal('75.50'), 'ABERTO', None, True),
        ],
        'reservas': [
            (date(2026, 11, 2), 'Pilates'),
            (date(2026, 12, 2), 'Pilates'),
            (date(2027, 1, 2), 'Pilates'),
        ],
    },
    {
        'rotulo': 'cortesia_valor_zero',
        'plano': ('SEMANAL', '80'),
        'entrada': (2, '0', date(2026, 11, 2), '0|09:00|09:50'),
        'pacote': {
            'recorrencia': 'SEMANAL',
            'quantidade': 2,
            'valor_aula': Decimal('0.00'),
            'valor_total': Decimal('0.00'),
            'inicio': date(2026, 11, 2),
            'fim': date(2026, 11, 16),
        },
        'mensagens': ['Aulas avulsas agendadas com sucesso.'],
        'contas': [],
        'reservas': [(date(2026, 11, 2), 'Pilates'), (date(2026, 11, 9), 'Pilates')],
    },
    {
        'rotulo': 'comeca_na_terca_slot_segunda_fora_do_periodo',
        'plano': ('SEMANAL', '80'),
        'entrada': (4, '', date(2026, 11, 3), '0|09:00|09:50'),
        'pacote': {
            'recorrencia': 'SEMANAL',
            'quantidade': 4,
            'valor_aula': Decimal('80.00'),
            'valor_total': Decimal('80.00'),
            'inicio': date(2026, 11, 3),
            'fim': date(2026, 12, 1),
        },
        'mensagens': ['Aulas avulsas agendadas com sucesso.'],
        'contas': [
            (date(2026, 11, 9), '2026-46', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 16), '2026-47', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 23), '2026-48', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 30), '2026-49', Decimal('80.00'), 'ABERTO', None, True),
        ],
        'reservas': [
            (date(2026, 11, 9), 'Pilates'),
            (date(2026, 11, 16), 'Pilates'),
            (date(2026, 11, 23), 'Pilates'),
            (date(2026, 11, 30), 'Pilates'),
        ],
    },
    {
        'rotulo': 'mensal_dia_31',
        'plano': ('MENSAL', '60'),
        'entrada': (3, '', date(2026, 1, 31), '5|09:00|09:50'),
        'pacote': {
            'recorrencia': 'MENSAL',
            'quantidade': 3,
            'valor_aula': Decimal('60.00'),
            'valor_total': Decimal('60.00'),
            'inicio': date(2026, 1, 31),
            'fim': date(2026, 4, 28),
        },
        'mensagens': ['Aulas avulsas agendadas com sucesso.'],
        'contas': [
            (date(2026, 1, 28), '2026-01', Decimal('60.00'), 'ABERTO', None, True),
            (date(2026, 2, 28), '2026-02', Decimal('60.00'), 'ABERTO', None, True),
            (date(2026, 3, 28), '2026-03', Decimal('60.00'), 'ABERTO', None, True),
        ],
        'reservas': [
            (date(2026, 1, 28), 'Pilates'),
            (date(2026, 2, 28), 'Pilates'),
            (date(2026, 3, 28), 'Pilates'),
        ],
    },
    {
        'rotulo': 'dois_servicos_no_horario',
        'plano': ('SEMANAL', '80'),
        'entrada': (2, '', date(2026, 11, 2), '0|09:00|09:50'),
        'pacote': {
            'recorrencia': 'SEMANAL',
            'quantidade': 2,
            'valor_aula': Decimal('80.00'),
            'valor_total': Decimal('80.00'),
            'inicio': date(2026, 11, 2),
            'fim': date(2026, 11, 16),
        },
        'mensagens': ['Aulas avulsas agendadas com sucesso.'],
        'contas': [
            (date(2026, 11, 2), '2026-45', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 2), '2026-45', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 9), '2026-46', Decimal('80.00'), 'ABERTO', None, True),
            (date(2026, 11, 9), '2026-46', Decimal('80.00'), 'ABERTO', None, True),
        ],
        'reservas': [
            (date(2026, 11, 2), 'Alongamento'),
            (date(2026, 11, 2), 'Pilates'),
            (date(2026, 11, 9), 'Alongamento'),
            (date(2026, 11, 9), 'Pilates'),
        ],
    },
]
