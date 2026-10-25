"""Valores de referência gerados pelo sistema antigo em 2026-10-25 (receita_saude).

ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um
SQLite temporário com dados sintéticos. Não edite à mão: regenere.
"""
# ruff: noqa
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

# valor gerado pelo sistema antigo em 2026-10-25
CASOS = [
    {
        'rotulo': 'simples',
        'itens': [({}, {})],
        'config': {},
        'conteudo': '05/10/2026;R01.001.001;231;150,00;;Aulas de Pilates - competencia 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;79013-F\r\n',
        'erros': [],
    },
    {
        'rotulo': 'valor_1234_50',
        'itens': [({'valor': '1234.5'}, {})],
        'config': {},
        'conteudo': '05/10/2026;R01.001.001;231;1234,50;;Aulas de Pilates - competencia 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;79013-F\r\n',
        'erros': [],
    },
    {
        'rotulo': 'pagador_diferente',
        'itens': [({}, {'pagador': '390.533.447-05'})],
        'config': {},
        'conteudo': '05/10/2026;R01.001.001;231;150,00;;Aulas de Pilates - competencia 2026-10;PF;39053344705;11144477735;;;;;S;52998224725;79013-F\r\n',
        'erros': [],
    },
    {
        'rotulo': 'descricao_acentos_e_ponto_virgula',
        'itens': [
            (
                {
                    'descricao': 'Sessão; fisioterapia\ncom acentuação xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                    'competencia': '',
                },
                {},
            ),
        ],
        'config': {},
        'conteudo': '05/10/2026;R01.001.001;231;150,00;;Sessao, fisioterapia com acentuacao xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx;PF;11144477735;11144477735;;;;;S;52998224725;79013-F\r\n',
        'erros': [],
    },
    {
        'rotulo': 'competencia_ja_na_descricao',
        'itens': [({'descricao': 'Mensalidade 2026-10'}, {})],
        'config': {},
        'conteudo': '05/10/2026;R01.001.001;231;150,00;;Mensalidade 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;79013-F\r\n',
        'erros': [],
    },
    {
        'rotulo': 'sem_descricao_usa_padrao',
        'itens': [({'descricao': '', 'competencia': ''}, {})],
        'config': {},
        'conteudo': '05/10/2026;R01.001.001;231;150,00;;Aulas de Pilates;PF;11144477735;11144477735;;;;;S;52998224725;79013-F\r\n',
        'erros': [],
    },
    {
        'rotulo': 'varias_linhas_ordem_dada',
        'itens': [({'pago': date(2026, 10, 20), 'valor': '200'}, {}), ({'pago': date(2026, 10, 5)}, {})],
        'config': {},
        'conteudo': '20/10/2026;R01.001.001;231;200,00;;Aulas de Pilates - competencia 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;79013-F\r\n05/10/2026;R01.001.001;231;150,00;;Aulas de Pilates - competencia 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;79013-F\r\n',
        'erros': [],
    },
    {
        'rotulo': 'config_none',
        'itens': [({}, {})],
        'config': None,
        'conteudo': None,
        'erros': ['Configure o CPF do profissional em Configuracoes > Receita Saude.'],
    },
    {
        'rotulo': 'cpf_profissional_invalido',
        'itens': [({}, {})],
        'config': {'cpf_profissional': '123'},
        'conteudo': None,
        'erros': ['CPF do profissional invalido em Configuracoes > Receita Saude.'],
    },
    {
        'rotulo': 'ocupacao_invalida',
        'itens': [({}, {})],
        'config': {'codigo_ocupacao': '999'},
        'conteudo': None,
        'erros': ['Codigo de ocupacao invalido em Configuracoes > Receita Saude.'],
    },
    {
        'rotulo': 'registro_longo_e_com_espacos',
        'itens': [({}, {})],
        'config': {'registro_profissional': '  1234567890123456789  '},
        'conteudo': '05/10/2026;R01.001.001;231;150,00;;Aulas de Pilates - competencia 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;123456789012345\r\n',
        'erros': [],
    },
    {
        'rotulo': 'registro_vazio',
        'itens': [({}, {})],
        'config': {'registro_profissional': ''},
        'conteudo': '05/10/2026;R01.001.001;231;150,00;;Aulas de Pilates - competencia 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;\r\n',
        'erros': [],
    },
    {
        'rotulo': 'sem_itens',
        'itens': [],
        'config': {},
        'conteudo': None,
        'erros': ['Selecione ao menos um pagamento.'],
    },
    {
        'rotulo': 'nao_paga',
        'itens': [({'status': 'ABERTO'}, {})],
        'config': {},
        'conteudo': None,
        'erros': ['05/10/2026 (R$ 150,00): Ainda nao esta paga.'],
    },
    {
        'rotulo': 'sem_data_pagamento',
        'itens': [({'pago': None}, {})],
        'config': {},
        'conteudo': None,
        'erros': ['05/10/2026 (R$ 150,00): Sem data de pagamento.'],
    },
    {
        'rotulo': 'valor_zero',
        'itens': [({'valor': '0'}, {})],
        'config': {},
        'conteudo': None,
        'erros': ['05/10/2026 (R$ 0,00): Valor deve ser maior que zero.'],
    },
    {
        'rotulo': 'aluno_sem_cpf_campo_vazio',
        'itens': [({}, {'cpf': ''})],
        'config': {},
        'conteudo': None,
        'erros': ['05/10/2026 (R$ 150,00): Aluno sem CPF (obrigatorio no recibo).'],
    },
    {
        'rotulo': 'aluno_sem_cpf_flag',
        'itens': [({}, {'sem_cpf': True})],
        'config': {},
        'conteudo': None,
        'erros': ['05/10/2026 (R$ 150,00): Aluno sem CPF (obrigatorio no recibo).'],
    },
    {
        'rotulo': 'cpf_aluno_invalido',
        'itens': [({}, {'cpf': '12345678900'})],
        'config': {},
        'conteudo': None,
        'erros': [
            '05/10/2026 (R$ 150,00): CPF do aluno invalido.',
            '05/10/2026 (R$ 150,00): CPF do pagador invalido.',
        ],
    },
    {
        'rotulo': 'cpf_pagador_invalido',
        'itens': [({}, {'pagador': '11111111111'})],
        'config': {},
        'conteudo': None,
        'erros': ['05/10/2026 (R$ 150,00): CPF do pagador invalido.'],
    },
    {
        'rotulo': 'anos_misturados',
        'itens': [({'pago': date(2025, 12, 30)}, {}), ({'pago': date(2026, 1, 2)}, {})],
        'config': {},
        'conteudo': None,
        'erros': ['Todos os pagamentos do arquivo devem ser do mesmo ano (selecionados: 2025, 2026).'],
    },
    {
        'rotulo': 'mil_linhas',
        'itens': ('REPETIR', 1000),
        'config': {},
        'conteudo': (
            'QTD_LINHAS',
            1000,
            '05/10/2026;R01.001.001;231;150,00;;Aulas de Pilates - competencia 2026-10;PF;11144477735;11144477735;;;;;S;52998224725;79013-F',
        ),
        'erros': [],
    },
    {
        'rotulo': 'mil_e_uma_linhas',
        'itens': ('REPETIR', 1001),
        'config': {},
        'conteudo': None,
        'erros': ['O arquivo aceita ate 1000 linhas; foram selecionados 1001.'],
    },
    {
        'rotulo': 'varios_erros_juntos',
        'itens': [({'status': 'ABERTO', 'valor': '0', 'pago': None}, {'cpf': '1'})],
        'config': {'cpf_profissional': '1', 'codigo_ocupacao': '1'},
        'conteudo': None,
        'erros': [
            'CPF do profissional invalido em Configuracoes > Receita Saude.',
            'Codigo de ocupacao invalido em Configuracoes > Receita Saude.',
            '05/10/2026 (R$ 0,00): Ainda nao esta paga.',
            '05/10/2026 (R$ 0,00): Sem data de pagamento.',
            '05/10/2026 (R$ 0,00): Valor deve ser maior que zero.',
            '05/10/2026 (R$ 0,00): CPF do aluno invalido.',
            '05/10/2026 (R$ 0,00): CPF do pagador invalido.',
        ],
    },
]

# valor gerado pelo sistema antigo em 2026-10-25
SLUGS = [
    ('Ana Souza', 1, 'ana-souza'),
    ('José da Conceição', 2, 'jose-da-conceicao'),
    ('', 3, 3),
    ('  Maria--Lúcia  ', 4, 'maria-lucia'),
    ("O'Neil & Co.", 5, 'oneil-co'),
    ('123', 6, '123'),
]

# valor gerado pelo sistema antigo em 2026-10-25
MAX_LINHAS = 1000

# valor gerado pelo sistema antigo em 2026-10-25
OCUPACOES = {
    '225': 'Medico',
    '226': 'Odontologo',
    '230': 'Fonoaudiologo',
    '231': 'Fisioterapeuta',
    '232': 'Terapeuta ocupacional',
    '255': 'Psicologo',
}
