"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (capacidade).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
MSG_CLEAN = [
    'Capacidade excedida: a aula de 12/10 as 08:00 ja tem 2 de 2 vagas ocupadas. Escolha outro horario.',
]

# valor gerado pelo sistema antigo em 2026-10-25
OK_POR_STATUS = {'CANCELADA': True, 'PENDENTE': True, 'CONCLUIDA': True, 'FALTOU_AVISOU': True}

# valor gerado pelo sistema antigo em 2026-10-25
EFETIVAS = [(None, 2, 2), (0, 2, 0), (5, 2, 5)]

# valor gerado pelo sistema antigo em 2026-10-25
ZERO_RECUSA = True

# valor gerado pelo sistema antigo em 2026-10-25
MSG_ZERO = [
    'Capacidade excedida: a aula de 14/10 as 08:00 ja tem 0 de 0 vagas ocupadas. Escolha outro horario.',
]

# valor gerado pelo sistema antigo em 2026-10-25
REMARCAR_CHEIA = (
    400,
    {
        'error': 'Sem vaga neste horario: a aula de 12/10 as 08:00 ja tem 2 de 2 vagas ocupadas. Escolha outro horario.',
    },
)

# valor gerado pelo sistema antigo em 2026-10-25
REMARCAR_CAP_ZERO = (200, True)
