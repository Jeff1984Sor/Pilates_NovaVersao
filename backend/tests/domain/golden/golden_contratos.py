"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (contratos).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
CONTRATOS = [
    (1, 1, 1, 1, date(2026, 11, 2), date(2026, 11, 30)),
    (2, 1, 1, 1, date(2026, 11, 20), date(2026, 12, 20)),
    (3, 2, 1, 1, date(2026, 11, 2), date(2026, 11, 30)),
]

# valor gerado pelo sistema antigo em 2026-10-25
RESERVAS = [
    (1, 'r1_compartilhada_com_bia', 1, 1, date(2026, 11, 3), 1, 1, 'RESERVADA', None, False),
    (2, 'r1b_bia_na_compartilhada', 2, 1, date(2026, 11, 3), 1, 1, 'RESERVADA', None, False),
    (3, 'r2_sozinha', 1, 2, date(2026, 11, 10), 1, 1, 'RESERVADA', None, False),
    (4, 'r3_outro_servico', 1, 3, date(2026, 11, 12), 1, 2, 'RESERVADA', None, False),
    (5, 'r4_outra_unidade', 1, 4, date(2026, 11, 14), 2, 1, 'RESERVADA', None, False),
    (6, 'r5_depois_do_fim', 1, 5, date(2026, 12, 1), 1, 1, 'RESERVADA', None, False),
    (7, 'r6_no_primeiro_dia', 1, 6, date(2026, 11, 2), 1, 1, 'RESERVADA', None, False),
    (8, 'r7_no_ultimo_dia', 1, 7, date(2026, 11, 30), 1, 1, 'RESERVADA', None, False),
    (9, 'r8_aula_avulsa_no_periodo', 1, 8, date(2026, 11, 5), 1, 1, 'RESERVADA', 1, False),
    (10, 'r9_concluida', 1, 9, date(2026, 11, 6), 1, 1, 'CONCLUIDA', None, True),
    (11, 'r10_cancelada', 1, 10, date(2026, 11, 9), 1, 1, 'CANCELADA', None, False),
    (12, 'r11_so_do_contrato_2', 1, 11, date(2026, 12, 10), 1, 1, 'RESERVADA', None, False),
    (13, 'r12_na_sobreposicao', 1, 12, date(2026, 11, 25), 1, 1, 'RESERVADA', None, False),
    (14, 'r13_antes_do_inicio', 1, 13, date(2026, 11, 1), 1, 1, 'RESERVADA', None, False),
    (15, 'r14_da_bia', 2, 14, date(2026, 11, 11), 1, 1, 'RESERVADA', None, False),
]

# valor gerado pelo sistema antigo em 2026-10-25
CONTAS = [
    (1, 'c1_pago', 1, 'PAGO'),
    (2, 'c1_aberto', 1, 'ABERTO'),
    (3, 'c1_cancelado', 1, 'CANCELADO'),
    (4, 'c2_aberto', 2, 'ABERTO'),
    (5, 'avulsa_da_ana', None, 'ABERTO'),
    (6, 'c3_da_bia', 3, 'ABERTO'),
]

# valor gerado pelo sistema antigo em 2026-10-25
RESUMOS_CONFIRMACAO = {
    'c1': {'contas_receber': 3, 'reservas': 8, 'aulas': 8},
    'c3': {'contas_receber': 1, 'reservas': 2, 'aulas': 2},
}

# valor gerado pelo sistema antigo em 2026-10-25
SEM_CONFIRMAR = (302, True, 15, 6)

# valor gerado pelo sistema antigo em 2026-10-25
RESERVAS_APAGADAS = [
    'r10_cancelada',
    'r12_na_sobreposicao',
    'r1_compartilhada_com_bia',
    'r2_sozinha',
    'r6_no_primeiro_dia',
    'r7_no_ultimo_dia',
    'r8_aula_avulsa_no_periodo',
    'r9_concluida',
]

# valor gerado pelo sistema antigo em 2026-10-25
CONTAS_APAGADAS = ['c1_aberto', 'c1_cancelado', 'c1_pago']

# valor gerado pelo sistema antigo em 2026-10-25
SESSOES_APAGADAS_QTD = 7

# valor gerado pelo sistema antigo em 2026-10-25
EVOLUCOES_RESTANTES = 0

# valor gerado pelo sistema antigo em 2026-10-25
HOJE = date(2026, 10, 25)

# valor gerado pelo sistema antigo em 2026-10-25
GESTAO = {
    'ativos': {
        'filtro_efetivo': 'ativos',
        'contratos': [
            ('vence_hoje', 0, 'Vence esta semana', 'danger'),
            ('termina_hoje_comecou_hoje', 0, 'Vence esta semana', 'danger'),
            ('vence_em_3', 3, 'Vence esta semana', 'danger'),
            ('vence_em_7', 7, 'Vence esta semana', 'danger'),
            ('vence_em_8', 8, 'Vence em breve', 'warning'),
            ('vence_em_30', 30, 'Vence em breve', 'warning'),
            ('vence_em_31', 31, 'Vigente', 'success'),
        ],
        'resumo': {'ativos': 7, 'vencendo': 7, 'vencidos': 2, 'total': 11},
    },
    'vencendo': {
        'filtro_efetivo': 'vencendo',
        'contratos': [
            ('vence_hoje', 0, 'Vence esta semana', 'danger'),
            ('termina_hoje_comecou_hoje', 0, 'Vence esta semana', 'danger'),
            ('vence_em_3', 3, 'Vence esta semana', 'danger'),
            ('vence_em_7', 7, 'Vence esta semana', 'danger'),
            ('vence_em_8', 8, 'Vence em breve', 'warning'),
            ('comeca_amanha_vence_em_20', 20, 'Vence em breve', 'warning'),
            ('vence_em_30', 30, 'Vence em breve', 'warning'),
        ],
        'resumo': {'ativos': 7, 'vencendo': 7, 'vencidos': 2, 'total': 11},
    },
    'vencidos': {
        'filtro_efetivo': 'vencidos',
        'contratos': [
            ('vencido_ha_um_ano', -365, 'Vencido', 'danger'),
            ('venceu_ontem', -1, 'Vencido', 'danger'),
        ],
        'resumo': {'ativos': 7, 'vencendo': 7, 'vencidos': 2, 'total': 11},
    },
    'todos': {
        'filtro_efetivo': 'todos',
        'contratos': [
            ('vencido_ha_um_ano', -365, 'Vencido', 'danger'),
            ('venceu_ontem', -1, 'Vencido', 'danger'),
            ('vence_hoje', 0, 'Vence esta semana', 'danger'),
            ('termina_hoje_comecou_hoje', 0, 'Vence esta semana', 'danger'),
            ('vence_em_3', 3, 'Vence esta semana', 'danger'),
            ('vence_em_7', 7, 'Vence esta semana', 'danger'),
            ('vence_em_8', 8, 'Vence em breve', 'warning'),
            ('comeca_amanha_vence_em_20', 20, 'Vence em breve', 'warning'),
            ('vence_em_30', 30, 'Vence em breve', 'warning'),
            ('vence_em_31', 31, 'Vigente', 'success'),
            ('comeca_amanha_vence_em_90', 90, 'Vigente', 'success'),
        ],
        'resumo': {'ativos': 7, 'vencendo': 7, 'vencidos': 2, 'total': 11},
    },
    'xyz': {
        'filtro_efetivo': 'ativos',
        'contratos': [
            ('vence_hoje', 0, 'Vence esta semana', 'danger'),
            ('termina_hoje_comecou_hoje', 0, 'Vence esta semana', 'danger'),
            ('vence_em_3', 3, 'Vence esta semana', 'danger'),
            ('vence_em_7', 7, 'Vence esta semana', 'danger'),
            ('vence_em_8', 8, 'Vence em breve', 'warning'),
            ('vence_em_30', 30, 'Vence em breve', 'warning'),
            ('vence_em_31', 31, 'Vigente', 'success'),
        ],
        'resumo': {'ativos': 7, 'vencendo': 7, 'vencidos': 2, 'total': 11},
    },
    '': {
        'filtro_efetivo': 'ativos',
        'contratos': [
            ('vence_hoje', 0, 'Vence esta semana', 'danger'),
            ('termina_hoje_comecou_hoje', 0, 'Vence esta semana', 'danger'),
            ('vence_em_3', 3, 'Vence esta semana', 'danger'),
            ('vence_em_7', 7, 'Vence esta semana', 'danger'),
            ('vence_em_8', 8, 'Vence em breve', 'warning'),
            ('vence_em_30', 30, 'Vence em breve', 'warning'),
            ('vence_em_31', 31, 'Vigente', 'success'),
        ],
        'resumo': {'ativos': 7, 'vencendo': 7, 'vencidos': 2, 'total': 11},
    },
}

# valor gerado pelo sistema antigo em 2026-10-25
FINS = [
    ('venceu_ontem', date(2026, 10, 24), date(2026, 9, 1)),
    ('vence_hoje', date(2026, 10, 25), date(2026, 9, 1)),
    ('vence_em_3', date(2026, 10, 28), date(2026, 9, 1)),
    ('vence_em_7', date(2026, 11, 1), date(2026, 9, 1)),
    ('vence_em_8', date(2026, 11, 2), date(2026, 9, 1)),
    ('vence_em_30', date(2026, 11, 24), date(2026, 9, 1)),
    ('vence_em_31', date(2026, 11, 25), date(2026, 9, 1)),
    ('comeca_amanha_vence_em_20', date(2026, 11, 14), date(2026, 10, 26)),
    ('comeca_amanha_vence_em_90', date(2027, 1, 23), date(2026, 10, 26)),
    ('termina_hoje_comecou_hoje', date(2026, 10, 25), date(2026, 10, 25)),
    ('vencido_ha_um_ano', date(2025, 10, 25), date(2025, 1, 1)),
]

# valor gerado pelo sistema antigo em 2026-10-25
CONTRATOS_VENCENDO_PAINEL = 4

# valor gerado pelo sistema antigo em 2026-10-25
ALERTAS = ['4 contratos vencendo em 7 dias']
