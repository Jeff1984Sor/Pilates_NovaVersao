"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (whatsapp).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
PADROES = {
    'template_aviso_aluno': 'Boa noite {aluno}, amanhã temos aula de {tipo_servico} às {horario}. Podemos confirmar?',
    'template_aviso_professor': 'Resumo de amanhã: {horario} – {alunos}',
    'template_link_contrato': 'Olá {aluno}, confirme seu contrato pelo link: {link_contrato}',
    'template_aviso_renovacao': 'Seu contrato vence em {dias_restantes} dias. Deseja renovar?',
    'template_aniversario': 'Feliz Aniversário, {aluno}! 🎉\nDesejamos um ano cheio de energia boa, leveza, saúde e momentos que façam seu coração sorrir. Continue se cuidando e honrando seu corpo. É um privilégio te acompanhar nessa jornada. 🎂🎈🙏',
    'template_fim_contrato': 'Olá, {aluno}! Tudo bem? 🌸\nSeu ciclo atual de Pilates está chegando ao fim e adoraríamos continuar acompanhando sua evolução! Para o próximo período, o valor do plano passou por um pequeno reajuste e será de R$ {valor}.\nPodemos confirmar sua renovação e garantir seu horário? Me avise por aqui para prepararmos o novo contrato! ✨',
    'template_vencimento_proximo': 'Olá, {aluno}! Tudo bem? Passando para lembrar que sua mensalidade do Pilates vence em breve, no dia {data}. Qualquer dúvida, estou à disposição. 🧘\u200d♀️✨',
    'template_mensalidade_atraso': 'Olá! Tudo bem? Passando para lembrar que o pagamento da sua mensalidade do Pilates (vencimento em {data}) no valor de R$ {valor} ainda não consta em nosso sistema.\nPode ter sido apenas um esquecimento, mas se precisar de algo, estou à disposição! 🧘\u200d♀️\nChave Pix (CNPJ): 50.732.875/0001-56\nCaso o pagamento já tenha sido realizado, por favor, desconsidere esta mensagem.',
    'template_tres_meses': 'Olá, {aluno}! Parabéns pelos 3 meses de Pilates! 💪🏻\nSente mais força ou mobilidade? Alguma dor reduziu? Alguma nova meta que você gostaria de trabalhar?\nOs primeiros 90 dias são essenciais para criar consistência, e você está indo muito bem!\nObrigada por confiar na Mayris para cuidar de você. Conte sempre comigo!',
}

# valor gerado pelo sistema antigo em 2026-10-25
HORARIOS_PADRAO = {
    'horario_aviso_aluno': time(19, 0),
    'horario_aviso_professor': time(18, 0),
    'horario_aviso_renovacao': time(10, 0),
    'horario_aviso_aniversario': time(9, 0),
    'horario_aviso_vencimento': time(10, 0),
    'horario_aviso_atraso': time(10, 0),
    'horario_aviso_tres_meses': time(10, 0),
}

# valor gerado pelo sistema antigo em 2026-10-25
LIGADOS_PADRAO = {
    'avisar_aluno': True,
    'avisar_professor': True,
    'avisar_renovacao': True,
    'avisar_aniversario': False,
    'avisar_vencimento': False,
    'avisar_atraso': False,
    'avisar_tres_meses': False,
    'avisar_fim_contrato': True,
    'enviar_link_contrato': True,
}

# valor gerado pelo sistema antigo em 2026-10-25
MODELOS = [
    'Ola {aluno}',
    '  Ola {aluno}  ',
    '',
    '   ',
    None,
    'Oi {aluno}, {faltando} e {aluno}',
    'R$ {valor} em {data}',
    '{{literal}} {aluno}',
    '{aluno',
    'aluno}',
    '{0}',
    '{aluno.nome}',
    '{valor:.2f}',
    '{aluno!r}',
    'Sem variaveis',
    'Multi\nlinha {aluno}\n{aluno}',
    '{aluno} {aluno}',
    '{ALUNO}',
    'Chave {PIX_CHAVE}',
    '100% {aluno}',
    '{}',
    '{ aluno }',
    '{aluno:>10}|',
    '{n:03d}',
]

# valor gerado pelo sistema antigo em 2026-10-25
CONTEXTO = {'aluno': 'Ana', 'valor': '300,00', 'data': '27/10/2026', 'horario': '08:00', 'n': 5, 'vazio': None}

# valor gerado pelo sistema antigo em 2026-10-25
RENDER_VIEWS = [
    ('Ola {aluno}', 'Ola Ana'),
    ('  Ola {aluno}  ', 'Ola Ana'),
    ('', ''),
    ('   ', ''),
    (None, ''),
    ('Oi {aluno}, {faltando} e {aluno}', 'Oi Ana, {faltando} e Ana'),
    ('R$ {valor} em {data}', 'R$ 300,00 em 27/10/2026'),
    ('{{literal}} {aluno}', '{literal} Ana'),
    ('{aluno', '{aluno'),
    ('aluno}', 'aluno}'),
    ('{0}', '{0}'),
    ('{aluno.nome}', '{aluno.nome}'),
    ('{valor:.2f}', '{valor:.2f}'),
    ('{aluno!r}', "'Ana'"),
    ('Sem variaveis', 'Sem variaveis'),
    ('Multi\nlinha {aluno}\n{aluno}', 'Multi\nlinha Ana\nAna'),
    ('{aluno} {aluno}', 'Ana Ana'),
    ('{ALUNO}', '{ALUNO}'),
    ('Chave {PIX_CHAVE}', 'Chave {PIX_CHAVE}'),
    ('100% {aluno}', '100% Ana'),
    ('{}', '{}'),
    ('{ aluno }', '{ aluno }'),
    ('{aluno:>10}|', '       Ana|'),
    ('{n:03d}', '005'),
]

# valor gerado pelo sistema antigo em 2026-10-25
RENDER_SCHEDULER = [
    ('Ola {aluno}', 'Ola Ana'),
    ('  Ola {aluno}  ', 'Ola Ana'),
    ('', ''),
    ('   ', ''),
    (None, ''),
    ('Oi {aluno}, {faltando} e {aluno}', 'Oi Ana, {faltando} e Ana'),
    ('R$ {valor} em {data}', 'R$ 300,00 em 27/10/2026'),
    ('{{literal}} {aluno}', '{literal} Ana'),
    ('{aluno', '{aluno'),
    ('aluno}', 'aluno}'),
    ('{0}', '{0}'),
    ('{aluno.nome}', '{aluno.nome}'),
    ('{valor:.2f}', '{valor:.2f}'),
    ('{aluno!r}', "'Ana'"),
    ('Sem variaveis', 'Sem variaveis'),
    ('Multi\nlinha {aluno}\n{aluno}', 'Multi\nlinha Ana\nAna'),
    ('{aluno} {aluno}', 'Ana Ana'),
    ('{ALUNO}', '{ALUNO}'),
    ('Chave {PIX_CHAVE}', 'Chave {PIX_CHAVE}'),
    ('100% {aluno}', '100% Ana'),
    ('{}', '{}'),
    ('{ aluno }', '{ aluno }'),
    ('{aluno:>10}|', '       Ana|'),
    ('{n:03d}', '005'),
]

# valor gerado pelo sistema antigo em 2026-10-25
HOJE = date(2026, 10, 26)

# valor gerado pelo sistema antigo em 2026-10-25
AMANHA = date(2026, 10, 27)

# valor gerado pelo sistema antigo em 2026-10-25
DEFINICOES = {
    'alunos': [
        (1, 'Ana', 1, 'ATIVO', date(1990, 10, 26), ['(15) 99776-2467']),
        (2, 'Bia', 1, 'INATIVO', date(1985, 10, 26), ['11 98888-7777']),
        (3, 'Caio', 1, 'ATIVO', date(2000, 2, 29), []),
        (4, 'Duda', 1, 'ATIVO', date(1995, 10, 27), ['21 97777-6666']),
        (5, 'Edu', 1, 'ATIVO', None, ['31 96666-5555']),
        (6, 'Fabi', 2, 'ATIVO', None, ['41 95555-4444']),
        (7, 'Dani', 1, 'ATIVO', date(1992, 1, 1), ['51 94444-3333']),
        (8, 'Gabi', 1, 'ATIVO', None, ['(15) 3333-4444']),
        (9, 'Hugo', 1, 'ATIVO', None, ['123']),
    ],
    'reservas': [
        (1, 1, 'RESERVADA', date(2026, 10, 27), time(8, 0), 'Pilates', 1, 'Unidade Teste', 1),
        (2, 1, 'PENDENTE', date(2026, 10, 27), time(9, 0), 'Pilates', 1, 'Unidade Teste', 2),
        (3, 2, 'CONCLUIDA', date(2026, 10, 27), time(10, 0), 'Pilates', 1, 'Unidade Teste', 1),
        (4, 2, 'RESERVADA', date(2026, 10, 27), time(11, 0), 'Alongamento', 1, 'Unidade Teste', 1),
        (5, 3, 'RESERVADA', date(2026, 10, 27), time(8, 0), 'Pilates', 1, 'Unidade Teste', 1),
        (6, 4, 'CANCELADA', date(2026, 10, 27), time(8, 0), 'Pilates', 1, 'Unidade Teste', 1),
        (7, 5, 'FALTOU_AVISOU', date(2026, 10, 27), time(9, 0), 'Pilates', 1, 'Unidade Teste', 1),
        (
            8,
            5,
            'FALTOU_SEM_AVISAR',
            date(2026, 10, 27),
            time(10, 0),
            'Pilates',
            1,
            'Unidade Teste',
            1,
        ),
        (9, 6, 'RESERVADA', date(2026, 10, 27), time(8, 0), 'Pilates', 2, 'Outra', 1),
        (10, 8, 'RESERVADA', date(2026, 10, 27), time(14, 0), 'Pilates', 1, 'Unidade Teste', None),
        (11, 9, 'RESERVADA', date(2026, 10, 27), time(15, 0), 'Pilates', 1, 'Unidade Teste', 1),
        (12, 7, 'PENDENTE', date(2026, 10, 27), time(7, 0), 'Pilates', 1, 'Unidade Teste', 1),
    ],
    'profissionais': [(1, 'Natalia', '(15) 98111-2222'), (2, 'Sem Celular', '')],
    'contratos': [
        (1, 26, 1, 1, date(2026, 8, 3), date(2026, 11, 2), 'ASSINADO'),
        (2, 27, 2, 1, date(2026, 8, 3), date(2026, 11, 2), 'NAO_ASSINADO'),
        (3, 28, 3, 1, date(2026, 8, 3), date(2026, 11, 2), 'ASSINADO_DIGITALMENTE'),
        (4, 29, 4, 1, date(2026, 8, 3), date(2026, 11, 1), 'ASSINADO'),
        (5, 30, 7, 1, date(2026, 7, 28), date(2027, 2, 3), 'ASSINADO'),
        (6, 31, 5, 1, date(2026, 7, 29), date(2027, 2, 3), 'ASSINADO'),
        (7, 32, 8, 1, date(2026, 7, 28), date(2027, 2, 3), 'NAO_ASSINADO'),
        (8, 33, 6, 2, date(2026, 10, 26), date(2026, 11, 2), 'ASSINADO'),
    ],
    'contas': [
        (1, 1, 'ABERTO', Decimal('300.00'), date(2026, 10, 27)),
        (2, 2, 'ABERTO', Decimal('150.50'), date(2026, 10, 27)),
        (3, 1, 'PAGO', Decimal('300.00'), date(2026, 10, 27)),
        (4, 3, 'ATRASADO', Decimal('300.00'), date(2026, 10, 27)),
        (5, 1, 'ABERTO', Decimal('300.00'), date(2026, 10, 28)),
        (6, None, 'ABERTO', Decimal('50.00'), date(2026, 10, 27)),
        (7, 8, 'ABERTO', Decimal('300.00'), date(2026, 10, 27)),
        (8, 1, 'ABERTO', Decimal('300.00'), date(2026, 10, 1)),
        (9, 1, 'ABERTO', Decimal('300.00'), date(2026, 10, 10)),
        (10, 2, 'ATRASADO', Decimal('80.00'), date(2026, 10, 20)),
        (11, 1, 'PAGO', Decimal('300.00'), date(2026, 10, 1)),
        (12, 1, 'CANCELADO', Decimal('300.00'), date(2026, 10, 1)),
        (13, 1, 'ABERTO', Decimal('300.00'), date(2026, 10, 26)),
    ],
    'unidades': {1: 'Unidade Teste', 2: 'Outra'},
    'principal': 1,
}

# valor gerado pelo sistema antigo em 2026-10-25
EXECUCOES = [
    {
        'lembrete_aluno': {
            'funcao': 'lembrete_aluno',
            'retorno': {
                'eligible_students': 6,
                'sent': 5,
                'without_phone': 1,
                'rate_limited': 0,
                'already_sent': 0,
                'failed': 0,
            },
            'chamadas': [
                (
                    'aluno',
                    'Ana',
                    '5515997762467',
                    'Boa noite Ana, amanhã temos aula de Pilates às 08:00. Podemos confirmar?',
                    'automated_reminder',
                    None,
                ),
                (
                    'aluno',
                    'Bia',
                    '5511988887777',
                    'Boa noite Bia, amanhã temos aula de Alongamento às 11:00. Podemos confirmar?',
                    'automated_reminder',
                    None,
                ),
                (
                    'aluno',
                    'Dani',
                    '5551944443333',
                    'Boa noite Dani, amanhã temos aula de Pilates às 07:00. Podemos confirmar?',
                    'automated_reminder',
                    None,
                ),
                (
                    'aluno',
                    'Gabi',
                    '551533334444',
                    'Boa noite Gabi, amanhã temos aula de Pilates às 14:00. Podemos confirmar?',
                    'automated_reminder',
                    None,
                ),
                (
                    'aluno',
                    'Hugo',
                    '123',
                    'Boa noite Hugo, amanhã temos aula de Pilates às 15:00. Podemos confirmar?',
                    'automated_reminder',
                    None,
                ),
            ],
            'logs_total': 5,
            'entradas': [
                (
                    'Ana',
                    'sent',
                    '5515997762467',
                    'Boa noite Ana, amanhã temos aula de Pilates às 08:00. Podemos confirmar?',
                ),
                (
                    'Bia',
                    'sent',
                    '5511988887777',
                    'Boa noite Bia, amanhã temos aula de Alongamento às 11:00. Podemos confirmar?',
                ),
                ('Caio', 'without_phone', '', ''),
                (
                    'Dani',
                    'sent',
                    '5551944443333',
                    'Boa noite Dani, amanhã temos aula de Pilates às 07:00. Podemos confirmar?',
                ),
                (
                    'Gabi',
                    'sent',
                    '551533334444',
                    'Boa noite Gabi, amanhã temos aula de Pilates às 14:00. Podemos confirmar?',
                ),
                (
                    'Hugo',
                    'sent',
                    '123',
                    'Boa noite Hugo, amanhã temos aula de Pilates às 15:00. Podemos confirmar?',
                ),
            ],
        },
        'agenda_professor': {
            'funcao': 'agenda_professor',
            'retorno': 1,
            'chamadas': [
                (
                    'professor',
                    None,
                    '5515981112222',
                    'Resumo de amanhã: 08:00 - Ana - Pilates\n08:00 - Caio - Pilates\n11:00 - Bia - Alongamento\n15:00 - Hugo - Pilates – 08:00 - Ana - Pilates\n08:00 - Caio - Pilates\n11:00 - Bia - Alongamento\n15:00 - Hugo - Pilates',
                    None,
                    None,
                ),
            ],
            'logs_total': 6,
        },
        'renovacao': {
            'funcao': 'renovacao',
            'retorno': 1,
            'chamadas': [
                (
                    'aluno',
                    'Ana',
                    '5515997762467',
                    'Seu contrato vence em 7 dias. Deseja renovar?',
                    'contract_renewal',
                    26,
                ),
            ],
            'logs_total': 7,
        },
        'aniversario': {
            'funcao': 'aniversario',
            'retorno': 1,
            'chamadas': [
                (
                    'aluno',
                    'Ana',
                    '5515997762467',
                    'Feliz Aniversário, Ana! 🎉\nDesejamos um ano cheio de energia boa, leveza, saúde e momentos que façam seu coração sorrir. Continue se cuidando e honrando seu corpo. É um privilégio te acompanhar nessa jornada. 🎂🎈🙏',
                    'manual',
                    None,
                ),
            ],
            'logs_total': 8,
        },
        'vencimento': {
            'funcao': 'vencimento',
            'retorno': 2,
            'chamadas': [
                (
                    'aluno',
                    'Ana',
                    '5515997762467',
                    'Olá, Ana! Tudo bem? Passando para lembrar que sua mensalidade do Pilates vence em breve, no dia 27/10/2026. Qualquer dúvida, estou à disposição. 🧘\u200d♀️✨',
                    'manual',
                    26,
                ),
                (
                    'aluno',
                    'Bia',
                    '5511988887777',
                    'Olá, Bia! Tudo bem? Passando para lembrar que sua mensalidade do Pilates vence em breve, no dia 27/10/2026. Qualquer dúvida, estou à disposição. 🧘\u200d♀️✨',
                    'manual',
                    27,
                ),
            ],
            'logs_total': 10,
        },
        'atraso': {
            'funcao': 'atraso',
            'retorno': 3,
            'chamadas': [
                (
                    'aluno',
                    'Ana',
                    '5515997762467',
                    'Olá! Tudo bem? Passando para lembrar que o pagamento da sua mensalidade do Pilates (vencimento em 01/10/2026) no valor de R$ 300,00 ainda não consta em nosso sistema.\nPode ter sido apenas um esquecimento, mas se precisar de algo, estou à disposição! 🧘\u200d♀️\nChave Pix (CNPJ): 50.732.875/0001-56\nCaso o pagamento já tenha sido realizado, por favor, desconsidere esta mensagem.',
                    'manual',
                    26,
                ),
                (
                    'aluno',
                    'Ana',
                    '5515997762467',
                    'Olá! Tudo bem? Passando para lembrar que o pagamento da sua mensalidade do Pilates (vencimento em 10/10/2026) no valor de R$ 300,00 ainda não consta em nosso sistema.\nPode ter sido apenas um esquecimento, mas se precisar de algo, estou à disposição! 🧘\u200d♀️\nChave Pix (CNPJ): 50.732.875/0001-56\nCaso o pagamento já tenha sido realizado, por favor, desconsidere esta mensagem.',
                    'manual',
                    26,
                ),
                (
                    'aluno',
                    'Bia',
                    '5511988887777',
                    'Olá! Tudo bem? Passando para lembrar que o pagamento da sua mensalidade do Pilates (vencimento em 20/10/2026) no valor de R$ 80,00 ainda não consta em nosso sistema.\nPode ter sido apenas um esquecimento, mas se precisar de algo, estou à disposição! 🧘\u200d♀️\nChave Pix (CNPJ): 50.732.875/0001-56\nCaso o pagamento já tenha sido realizado, por favor, desconsidere esta mensagem.',
                    'manual',
                    27,
                ),
            ],
            'logs_total': 13,
        },
        'tres_meses': {
            'funcao': 'tres_meses',
            'retorno': 1,
            'chamadas': [
                (
                    'aluno',
                    'Dani',
                    '5551944443333',
                    'Olá, Dani! Parabéns pelos 3 meses de Pilates! 💪🏻\nSente mais força ou mobilidade? Alguma dor reduziu? Alguma nova meta que você gostaria de trabalhar?\nOs primeiros 90 dias são essenciais para criar consistência, e você está indo muito bem!\nObrigada por confiar na Mayris para cuidar de você. Conte sempre comigo!',
                    'manual',
                    30,
                ),
            ],
            'logs_total': 14,
        },
    },
    {
        'lembrete_aluno': {
            'funcao': 'lembrete_aluno',
            'retorno': {
                'eligible_students': 6,
                'sent': 0,
                'without_phone': 1,
                'rate_limited': 0,
                'already_sent': 5,
                'failed': 0,
            },
            'chamadas': [],
            'logs_total': 14,
            'entradas': [
                ('Ana', 'skipped', '', ''),
                ('Bia', 'skipped', '', ''),
                ('Caio', 'without_phone', '', ''),
                ('Dani', 'skipped', '', ''),
                ('Gabi', 'skipped', '', ''),
                ('Hugo', 'skipped', '', ''),
            ],
        },
        'agenda_professor': {'funcao': 'agenda_professor', 'retorno': 0, 'chamadas': [], 'logs_total': 14},
        'renovacao': {'funcao': 'renovacao', 'retorno': 0, 'chamadas': [], 'logs_total': 14},
        'aniversario': {'funcao': 'aniversario', 'retorno': 0, 'chamadas': [], 'logs_total': 14},
        'vencimento': {'funcao': 'vencimento', 'retorno': 0, 'chamadas': [], 'logs_total': 14},
        'atraso': {'funcao': 'atraso', 'retorno': 0, 'chamadas': [], 'logs_total': 14},
        'tres_meses': {'funcao': 'tres_meses', 'retorno': 0, 'chamadas': [], 'logs_total': 14},
    },
]

# valor gerado pelo sistema antigo em 2026-10-25
CHAVES_LOG = [
    'birthday:1:2026-10-26:1',
    'contract_renewal:1:2026-11-02:1',
    'payment_due:1:2026-10-27:1',
    'payment_due:1:2026-10-27:2',
    'payment_overdue:1:2026-10-26:10',
    'payment_overdue:1:2026-10-26:8',
    'payment_overdue:1:2026-10-26:9',
    'professor_schedule:1:2026-10-27:1',
    'student_reminder:1:2026-10-27:1',
    'student_reminder:1:2026-10-27:2',
    'student_reminder:1:2026-10-27:7',
    'student_reminder:1:2026-10-27:8',
    'student_reminder:1:2026-10-27:9',
    'three_months:1:2026-07-28:5',
]

# valor gerado pelo sistema antigo em 2026-10-25
EM_BRANCO = {
    'lembrete_aluno': {
        'funcao': 'lembrete_aluno',
        'retorno': {
            'eligible_students': 6,
            'sent': 5,
            'without_phone': 1,
            'rate_limited': 0,
            'already_sent': 0,
            'failed': 0,
        },
        'chamadas': [
            (
                'aluno',
                'Ana',
                '5515997762467',
                'Boa noite Ana, amanhã temos aula de Pilates às 08:00. Podemos confirmar?',
                'automated_reminder',
                None,
            ),
            (
                'aluno',
                'Bia',
                '5511988887777',
                'Boa noite Bia, amanhã temos aula de Alongamento às 11:00. Podemos confirmar?',
                'automated_reminder',
                None,
            ),
            (
                'aluno',
                'Dani',
                '5551944443333',
                'Boa noite Dani, amanhã temos aula de Pilates às 07:00. Podemos confirmar?',
                'automated_reminder',
                None,
            ),
            (
                'aluno',
                'Gabi',
                '551533334444',
                'Boa noite Gabi, amanhã temos aula de Pilates às 14:00. Podemos confirmar?',
                'automated_reminder',
                None,
            ),
            (
                'aluno',
                'Hugo',
                '123',
                'Boa noite Hugo, amanhã temos aula de Pilates às 15:00. Podemos confirmar?',
                'automated_reminder',
                None,
            ),
        ],
        'logs_total': 5,
        'entradas': [
            (
                'Ana',
                'sent',
                '5515997762467',
                'Boa noite Ana, amanhã temos aula de Pilates às 08:00. Podemos confirmar?',
            ),
            (
                'Bia',
                'sent',
                '5511988887777',
                'Boa noite Bia, amanhã temos aula de Alongamento às 11:00. Podemos confirmar?',
            ),
            ('Caio', 'without_phone', '', ''),
            (
                'Dani',
                'sent',
                '5551944443333',
                'Boa noite Dani, amanhã temos aula de Pilates às 07:00. Podemos confirmar?',
            ),
            (
                'Gabi',
                'sent',
                '551533334444',
                'Boa noite Gabi, amanhã temos aula de Pilates às 14:00. Podemos confirmar?',
            ),
            (
                'Hugo',
                'sent',
                '123',
                'Boa noite Hugo, amanhã temos aula de Pilates às 15:00. Podemos confirmar?',
            ),
        ],
    },
    'agenda_professor': {
        'funcao': 'agenda_professor',
        'retorno': 1,
        'chamadas': [
            (
                'professor',
                None,
                '5515981112222',
                'Resumo de amanhã: 08:00 - Ana - Pilates\n08:00 - Caio - Pilates\n11:00 - Bia - Alongamento\n15:00 - Hugo - Pilates – 08:00 - Ana - Pilates\n08:00 - Caio - Pilates\n11:00 - Bia - Alongamento\n15:00 - Hugo - Pilates',
                None,
                None,
            ),
        ],
        'logs_total': 6,
    },
    'renovacao': {
        'funcao': 'renovacao',
        'retorno': 1,
        'chamadas': [
            (
                'aluno',
                'Ana',
                '5515997762467',
                'Seu contrato vence em 7 dias. Deseja renovar?',
                'contract_renewal',
                26,
            ),
        ],
        'logs_total': 7,
    },
    'aniversario': {'funcao': 'aniversario', 'retorno': 0, 'chamadas': [], 'logs_total': 7},
    'vencimento': {'funcao': 'vencimento', 'retorno': 0, 'chamadas': [], 'logs_total': 7},
    'atraso': {'funcao': 'atraso', 'retorno': 0, 'chamadas': [], 'logs_total': 7},
    'tres_meses': {'funcao': 'tres_meses', 'retorno': 0, 'chamadas': [], 'logs_total': 7},
}

# valor gerado pelo sistema antigo em 2026-10-25
MENSAGEM_UI = 'Aluno Ana 08:00 - Pilates - Unidade Teste\n09:00 - Pilates - Unidade Teste | 08:00 - Pilates - Unidade Teste\n09:00 - Pilates - Unidade Teste | Unidade Teste 27/10/2026 Pilates 08:00'

# valor gerado pelo sistema antigo em 2026-10-25
QUANDO = {
    '00:00': [],
    '08:59': [],
    '09:00': ['birthday'],
    '09:05': ['birthday'],
    '10:00': ['birthday', 'contract_renewal', 'payment_due', 'payment_overdue', 'three_months'],
    '17:59': ['birthday', 'contract_renewal', 'payment_due', 'payment_overdue', 'three_months'],
    '18:00': [
        'birthday',
        'contract_renewal',
        'payment_due',
        'payment_overdue',
        'professor_schedule',
        'three_months',
    ],
    '18:05': [
        'birthday',
        'contract_renewal',
        'payment_due',
        'payment_overdue',
        'professor_schedule',
        'three_months',
    ],
    '19:00': [
        'birthday',
        'contract_renewal',
        'payment_due',
        'payment_overdue',
        'professor_schedule',
        'student_reminder',
        'three_months',
    ],
    '23:55': [
        'birthday',
        'contract_renewal',
        'payment_due',
        'payment_overdue',
        'professor_schedule',
        'student_reminder',
        'three_months',
    ],
}

# valor gerado pelo sistema antigo em 2026-10-25
SESSAO_CAIU = [
    ({'error': 'Session not connected'}, True),
    ({'error': 'x', 'response': {'message': 'WhatsApp session is not connected'}}, True),
    ({'error': 'timeout'}, False),
    ({'ok': True}, False),
    (None, False),
    ('texto', False),
    ({'error': None, 'response': {'message': 'Session disconnected: please connect'}}, True),
    ({'error': 'Rate', 'retry_after': 12}, False),
    ({'error': 'x', 'response': {'retry_after': '30'}}, False),
    ({'retry_after': 'abc', 'error': 'y'}, False),
    ({'error': 'x', 'retry_after': 2}, False),
    ({'error': 'x', 'retry_after': 0}, False),
    ({'status': 'sent'}, False),
    ({'error': 'SESSION CONNECT lost'}, True),
    ({'response': 'ok'}, False),
]

# valor gerado pelo sistema antigo em 2026-10-25
RETRY = [
    ({'error': 'Session not connected'}, [5.0, 5.0], {'error': 'Session not connected'}),
    (
        {'error': 'x', 'response': {'message': 'WhatsApp session is not connected'}},
        [5.0, 5.0],
        {'error': 'x', 'response': {'message': 'WhatsApp session is not connected'}},
    ),
    ({'error': 'timeout'}, [5.0, 5.0], {'error': 'timeout'}),
    ({'ok': True}, [], {'ok': True}),
    (None, [5.0, 5.0], {'error': 'Falha ao enviar mensagem.'}),
    ('texto', [5.0, 5.0], 'texto'),
    (
        {'error': None, 'response': {'message': 'Session disconnected: please connect'}},
        [5.0, 5.0],
        {'error': None, 'response': {'message': 'Session disconnected: please connect'}},
    ),
    ({'error': 'Rate', 'retry_after': 12}, [12.0, 12.0], {'error': 'Rate', 'retry_after': 12}),
    (
        {'error': 'x', 'response': {'retry_after': '30'}},
        [30.0, 30.0],
        {'error': 'x', 'response': {'retry_after': '30'}},
    ),
    ({'retry_after': 'abc', 'error': 'y'}, [5.0, 5.0], {'retry_after': 'abc', 'error': 'y'}),
    ({'error': 'x', 'retry_after': 2}, [5.0, 5.0], {'error': 'x', 'retry_after': 2}),
    ({'error': 'x', 'retry_after': 0}, [5.0, 5.0], {'error': 'x', 'retry_after': 0}),
    ({'status': 'sent'}, [], {'status': 'sent'}),
    ({'error': 'SESSION CONNECT lost'}, [5.0, 5.0], {'error': 'SESSION CONNECT lost'}),
    ({'response': 'ok'}, [], {'response': 'ok'}),
]
