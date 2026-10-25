"""R8 - Receita Saude. Parte pura dos 14 testes de core/tests/test_receita_saude.py do sistema antigo (portados
quase literalmente; os testes de tela/Django ficam para a camada de API) + golden master do módulo antigo."""
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain import receita_saude
from tests.domain.golden import golden_receita_saude as g

CPF_PROFISSIONAL = "52998224725"  # CPFs de teste com digito verificador valido
CPF_ALUNO = "11144477735"
CPF_PAI = "39053344705"


def _config(**extra):
    base = dict(cpf_profissional=CPF_PROFISSIONAL, registro_profissional="79013-F", codigo_ocupacao="231",
                descricao_padrao="Aulas de Pilates")
    base.update(extra)
    return SimpleNamespace(**base)


def _aluno(cpf=CPF_ALUNO, pagador="", sem_cpf=False):
    return SimpleNamespace(dsCPF=cpf, sem_cpf=sem_cpf, cpf_pagador_recibo=pagador)


def _conta(valor="150.00", pago=date(2026, 10, 5), status="PAGO", descricao="", competencia="2026-10"):
    return SimpleNamespace(status=status, dtPagamento=pago, valor=Decimal(valor), descricao=descricao,
                           competencia=competencia, dtVencimento=date(2026, 10, 5))


# ---------------------------------------------------------------- testes do sistema antigo (portados) ---------

def test_r8_cpf_valido():
    assert receita_saude.cpf_valido("529.982.247-25")
    assert receita_saude.cpf_valido(CPF_ALUNO)
    assert not receita_saude.cpf_valido("111.111.111-11")
    assert not receita_saude.cpf_valido("529.982.247-24")
    assert not receita_saude.cpf_valido("123")
    assert not receita_saude.cpf_valido("")


def test_r8_linha_segue_o_layout_oficial_coluna_a_coluna():
    conteudo, erros = receita_saude.gerar_arquivo([(_conta("1234.5"), _aluno())], _config())
    assert erros == []
    assert conteudo.endswith("\r\n")
    colunas = conteudo.rstrip("\r\n").split(";")
    assert len(colunas) == 16
    assert colunas == [
        "05/10/2026",        # 1 data do pagamento
        "R01.001.001",       # 2 codigo do rendimento (fixo)
        "231",               # 3 ocupacao: fisioterapeuta
        "1234,50",           # 4 valor, virgula decimal, sem milhar
        "",                  # 5 deducao: vazio
        "Aulas de Pilates - competencia 2026-10",  # 6 descricao
        "PF",                # 7 recebido de
        CPF_ALUNO,           # 8 cpf do pagador
        CPF_ALUNO,           # 9 cpf do beneficiario
        "", "", "", "",      # 10-13 vazios
        "S",                 # 14 indicador de recibo
        CPF_PROFISSIONAL,    # 15 cpf do profissional
        "79013-F",           # 16 registro profissional
    ]


def test_r8_pagador_diferente_do_aluno_vai_na_coluna_do_pagador():
    conteudo, erros = receita_saude.gerar_arquivo([(_conta(), _aluno(pagador="390.533.447-05"))], _config())
    colunas = conteudo.rstrip("\r\n").split(";")
    assert erros == [] and colunas[7] == CPF_PAI and colunas[8] == CPF_ALUNO


def test_r8_descricao_sem_acento_sem_ponto_e_virgula_e_ate_255():
    conta = _conta(descricao="Sessão; fisioterapia\ncom acentuação " + "x" * 400, competencia="")
    linha = receita_saude.montar_linha(conta, _aluno(), _config())
    descricao = linha[5]
    assert ";" not in descricao and "\n" not in descricao
    assert descricao.startswith("Sessao, fisioterapia com acentuacao")
    assert len(descricao) == 255


@pytest.mark.parametrize(
    "conta,aluno,trecho",
    [
        (_conta(status="ABERTO"), _aluno(), "nao esta paga"),
        (_conta(pago=None), _aluno(), "Sem data de pagamento"),
        (_conta(valor="0"), _aluno(), "maior que zero"),
        (_conta(), _aluno(cpf=""), "sem CPF"),
        (_conta(), _aluno(sem_cpf=True), "sem CPF"),
        (_conta(), _aluno(cpf="12345678900"), "CPF do aluno invalido"),
        (_conta(), _aluno(pagador="11111111111"), "CPF do pagador invalido"),
    ],
)
def test_r8_nao_gera_arquivo_com_pagamento_problematico(conta, aluno, trecho):
    conteudo, erros = receita_saude.gerar_arquivo([(conta, aluno)], _config())
    assert conteudo is None
    assert any(trecho.lower() in erro.lower() for erro in erros), erros


def test_r8_nao_mistura_anos_nem_passa_de_1000_linhas():
    itens = [(_conta(pago=date(2025, 12, 30)), _aluno()), (_conta(pago=date(2026, 1, 2)), _aluno())]
    conteudo, erros = receita_saude.gerar_arquivo(itens, _config())
    assert conteudo is None and any("mesmo ano" in e for e in erros)

    muitos = [(_conta(), _aluno())] * 1001
    conteudo, erros = receita_saude.gerar_arquivo(muitos, _config())
    assert conteudo is None and any("1000" in e for e in erros)

    ok, erros = receita_saude.gerar_arquivo([(_conta(), _aluno())] * 1000, _config())
    assert erros == [] and ok.count("\r\n") == 1000


def test_r8_exige_configuracao_valida_e_ao_menos_um_pagamento():
    _, erros = receita_saude.gerar_arquivo([(_conta(), _aluno())], None)
    assert any("Configure" in e for e in erros)
    _, erros = receita_saude.gerar_arquivo([(_conta(), _aluno())], _config(cpf_profissional="123"))
    assert any("CPF do profissional" in e for e in erros)
    _, erros = receita_saude.gerar_arquivo([(_conta(), _aluno())], _config(codigo_ocupacao="999"))
    assert any("ocupacao" in e.lower() for e in erros)
    _, erros = receita_saude.gerar_arquivo([], _config())
    assert any("ao menos um" in e for e in erros)


# ---------------------------------------------------------------- golden master (módulo antigo executado) -------

def _itens_do_caso(caso):
    itens = caso["itens"]
    if isinstance(itens, tuple) and itens[0] == "REPETIR":
        return [(_conta(), _aluno())] * itens[1]
    return [(_conta(**c), _aluno(**a)) for c, a in itens]


@pytest.mark.parametrize("caso", g.CASOS, ids=lambda c: c["rotulo"])
def test_r8_arquivo_identico_ao_do_modulo_antigo(caso):
    config = None if caso["config"] is None else _config(**caso["config"])
    conteudo, erros = receita_saude.gerar_arquivo(_itens_do_caso(caso), config)
    assert erros == caso["erros"]
    esperado = caso["conteudo"]
    if isinstance(esperado, tuple):   # resumo de arquivos grandes
        _, qtd, primeira = esperado
        assert conteudo.count("\r\n") == qtd and conteudo.split("\r\n")[0] == primeira
    else:
        assert conteudo == esperado


def test_r8_formato_do_csv_crlf_sem_cabecalho_ponto_e_virgula():
    conteudo, _ = receita_saude.gerar_arquivo([(_conta(), _aluno()), (_conta("10"), _aluno())], _config())
    linhas = conteudo.split("\r\n")
    assert linhas[-1] == "" and len(linhas) == 3 and "\n" not in "".join(linhas)
    assert all(linha.count(";") == 15 for linha in linhas[:-1])
    assert not linhas[0].startswith("Data")


def test_r8_constantes_iguais_as_do_antigo():
    assert receita_saude.MAX_LINHAS == g.MAX_LINHAS
    assert receita_saude.OCUPACOES == g.OCUPACOES
    assert receita_saude.CODIGO_RENDIMENTO == "R01.001.001"


def test_r8_formatar_valor():
    assert receita_saude.formatar_valor(1234.5) == "1234,50"
    # COMPORTAMENTO ANTIGO: quantize sem ROUND_HALF_UP (arredondamento bancario): 0,005 -> 0,00 e 0,015 -> 0,02
    assert receita_saude.formatar_valor(Decimal("0.005")) == "0,00"
    assert receita_saude.formatar_valor(Decimal("0.015")) == "0,02"
    assert receita_saude.formatar_valor("10") == "10,00"


def test_r8_cpfs_do_aluno_sem_cpf_nao_tem_beneficiario():
    assert receita_saude.cpfs_do_aluno(_aluno(sem_cpf=True, pagador=CPF_PAI)) == (CPF_PAI, "")
    assert receita_saude.cpfs_do_aluno(_aluno()) == (CPF_ALUNO, CPF_ALUNO)


def test_r8_problemas_sem_aluno():
    assert receita_saude.problemas_da_conta(_conta(), None) == ["Cobranca sem aluno vinculado."]


# ---------------------------------------------------------------- regras da tela ------------------------------

def test_r8_recibo_ja_gerado_bloqueia_duplicidade_ate_liberar():
    novas = [SimpleNamespace(id=1, recibo_saude_gerado_em=None), SimpleNamespace(id=2, recibo_saude_gerado_em=datetime(2026, 10, 5))]
    ja = receita_saude.contas_ja_geradas(novas)
    assert [c.id for c in ja] == [2]
    assert "1 pagamento(s) marcado(s) ja tiveram o arquivo gerado" in receita_saude.mensagem_recibos_ja_gerados(len(ja))
    assert "Liberar" in receita_saude.mensagem_recibos_ja_gerados(1)
    novas[1].recibo_saude_gerado_em = None   # "liberar"
    assert receita_saude.contas_ja_geradas(novas) == []


def test_r8_ordenacao_por_data_de_pagamento_e_id():
    a = SimpleNamespace(id=2, dtPagamento=date(2026, 10, 20))
    b = SimpleNamespace(id=1, dtPagamento=date(2026, 10, 20))
    c = SimpleNamespace(id=9, dtPagamento=None)
    assert [x.id for x in sorted([a, b, c], key=receita_saude.chave_de_ordenacao)] == [9, 1, 2]


@pytest.mark.parametrize("nome,aluno_id,slug", g.SLUGS)
def test_r8_nome_do_arquivo_com_slug_do_django(nome, aluno_id, slug):
    assert receita_saude.nome_do_arquivo(nome, aluno_id, datetime(2026, 10, 25)) == f"receita-saude-{slug}-20261025.csv"
