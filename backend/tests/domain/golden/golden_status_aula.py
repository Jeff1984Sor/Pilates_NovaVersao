"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (status_aula).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
MAPA_STATUS = [
    ('RESERVADA', 0, 'aguardando_chegar'),
    ('RESERVADA', 1, 'em_aula'),
    ('RESERVADA', 2, 'em_aula'),
    ('RESERVADA', 3, 'em_aula'),
    ('RESERVADA', 4, 'aguardando_chegar'),
    ('PENDENTE', 0, 'aguardando_chegar'),
    ('PENDENTE', 1, 'em_aula'),
    ('PENDENTE', 2, 'em_aula'),
    ('PENDENTE', 3, 'em_aula'),
    ('PENDENTE', 4, 'aguardando_chegar'),
    ('CONCLUIDA', 0, 'finalizada'),
    ('CONCLUIDA', 1, 'finalizada'),
    ('CONCLUIDA', 2, 'finalizada'),
    ('CONCLUIDA', 3, 'finalizada'),
    ('CONCLUIDA', 4, 'finalizada'),
    ('FALTOU_AVISOU', 0, 'faltou'),
    ('FALTOU_AVISOU', 1, 'faltou'),
    ('FALTOU_AVISOU', 2, 'faltou'),
    ('FALTOU_AVISOU', 3, 'faltou'),
    ('FALTOU_AVISOU', 4, 'faltou'),
    ('FALTOU_SEM_AVISAR', 0, 'faltou'),
    ('FALTOU_SEM_AVISAR', 1, 'faltou'),
    ('FALTOU_SEM_AVISAR', 2, 'faltou'),
    ('FALTOU_SEM_AVISAR', 3, 'faltou'),
    ('FALTOU_SEM_AVISAR', 4, 'faltou'),
    ('CANCELADA', 0, 'remarcada'),
    ('CANCELADA', 1, 'remarcada'),
    ('CANCELADA', 2, 'remarcada'),
    ('CANCELADA', 3, 'remarcada'),
    ('CANCELADA', 4, 'remarcada'),
    ('XYZ', 0, 'aguardando_chegar'),
    ('XYZ', 1, 'em_aula'),
    ('XYZ', 2, 'em_aula'),
    ('XYZ', 3, 'em_aula'),
    ('XYZ', 4, 'aguardando_chegar'),
]

# valor gerado pelo sistema antigo em 2026-10-25
AGORA_CONCLUIR = datetime(2026, 10, 26, 10, 0, 0, tzinfo=SP)

# valor gerado pelo sistema antigo em 2026-10-25
CONCLUIDAS_TOTAL = 6

# valor gerado pelo sistema antigo em 2026-10-25
CONCLUIR = [
    ('RESERVADA', date(2026, 10, 25), time(23, 59), 'ontem_tarde', 'CONCLUIDA'),
    ('RESERVADA', date(2026, 10, 26), time(9, 50), 'hoje_terminou', 'CONCLUIDA'),
    ('RESERVADA', date(2026, 10, 26), time(10, 0), 'hoje_fim_igual_agora', 'CONCLUIDA'),
    ('RESERVADA', date(2026, 10, 26), time(10, 1), 'hoje_ainda_nao', 'RESERVADA'),
    ('RESERVADA', date(2026, 10, 26), time(15, 0), 'hoje_a_tarde', 'RESERVADA'),
    ('RESERVADA', date(2026, 10, 27), time(8, 50), 'amanha', 'RESERVADA'),
    ('PENDENTE', date(2026, 10, 25), time(23, 59), 'ontem_tarde', 'CONCLUIDA'),
    ('PENDENTE', date(2026, 10, 26), time(9, 50), 'hoje_terminou', 'CONCLUIDA'),
    ('PENDENTE', date(2026, 10, 26), time(10, 0), 'hoje_fim_igual_agora', 'CONCLUIDA'),
    ('PENDENTE', date(2026, 10, 26), time(10, 1), 'hoje_ainda_nao', 'PENDENTE'),
    ('PENDENTE', date(2026, 10, 26), time(15, 0), 'hoje_a_tarde', 'PENDENTE'),
    ('PENDENTE', date(2026, 10, 27), time(8, 50), 'amanha', 'PENDENTE'),
    ('CONCLUIDA', date(2026, 10, 25), time(23, 59), 'ontem_tarde', 'CONCLUIDA'),
    ('CONCLUIDA', date(2026, 10, 26), time(9, 50), 'hoje_terminou', 'CONCLUIDA'),
    ('CONCLUIDA', date(2026, 10, 26), time(10, 0), 'hoje_fim_igual_agora', 'CONCLUIDA'),
    ('CONCLUIDA', date(2026, 10, 26), time(10, 1), 'hoje_ainda_nao', 'CONCLUIDA'),
    ('CONCLUIDA', date(2026, 10, 26), time(15, 0), 'hoje_a_tarde', 'CONCLUIDA'),
    ('CONCLUIDA', date(2026, 10, 27), time(8, 50), 'amanha', 'CONCLUIDA'),
    ('CANCELADA', date(2026, 10, 25), time(23, 59), 'ontem_tarde', 'CANCELADA'),
    ('CANCELADA', date(2026, 10, 26), time(9, 50), 'hoje_terminou', 'CANCELADA'),
    ('CANCELADA', date(2026, 10, 26), time(10, 0), 'hoje_fim_igual_agora', 'CANCELADA'),
    ('CANCELADA', date(2026, 10, 26), time(10, 1), 'hoje_ainda_nao', 'CANCELADA'),
    ('CANCELADA', date(2026, 10, 26), time(15, 0), 'hoje_a_tarde', 'CANCELADA'),
    ('CANCELADA', date(2026, 10, 27), time(8, 50), 'amanha', 'CANCELADA'),
    ('FALTOU_AVISOU', date(2026, 10, 25), time(23, 59), 'ontem_tarde', 'FALTOU_AVISOU'),
    ('FALTOU_AVISOU', date(2026, 10, 26), time(9, 50), 'hoje_terminou', 'FALTOU_AVISOU'),
    ('FALTOU_AVISOU', date(2026, 10, 26), time(10, 0), 'hoje_fim_igual_agora', 'FALTOU_AVISOU'),
    ('FALTOU_AVISOU', date(2026, 10, 26), time(10, 1), 'hoje_ainda_nao', 'FALTOU_AVISOU'),
    ('FALTOU_AVISOU', date(2026, 10, 26), time(15, 0), 'hoje_a_tarde', 'FALTOU_AVISOU'),
    ('FALTOU_AVISOU', date(2026, 10, 27), time(8, 50), 'amanha', 'FALTOU_AVISOU'),
    ('FALTOU_SEM_AVISAR', date(2026, 10, 25), time(23, 59), 'ontem_tarde', 'FALTOU_SEM_AVISAR'),
    ('FALTOU_SEM_AVISAR', date(2026, 10, 26), time(9, 50), 'hoje_terminou', 'FALTOU_SEM_AVISAR'),
    (
        'FALTOU_SEM_AVISAR',
        date(2026, 10, 26),
        time(10, 0),
        'hoje_fim_igual_agora',
        'FALTOU_SEM_AVISAR',
    ),
    ('FALTOU_SEM_AVISAR', date(2026, 10, 26), time(10, 1), 'hoje_ainda_nao', 'FALTOU_SEM_AVISAR'),
    ('FALTOU_SEM_AVISAR', date(2026, 10, 26), time(15, 0), 'hoje_a_tarde', 'FALTOU_SEM_AVISAR'),
    ('FALTOU_SEM_AVISAR', date(2026, 10, 27), time(8, 50), 'amanha', 'FALTOU_SEM_AVISAR'),
]
