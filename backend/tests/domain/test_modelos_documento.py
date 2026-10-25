"""Modelos de documento (contrato e termo): lista oficial de variáveis e renderização segura.

Caracterização contra ``services.render_contrato_html`` / ``render_termo_html`` do sistema antigo (valores em
``tests/cadastros_agenda_docs/golden_modelos.py``, gerados por ``gerar_golden_modelos.py`` com o Django real)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from app.domain import modelos_documento as md
from tests.cadastros_agenda_docs import golden_modelos as g

ANTIGAS_31 = """ALUNO_NOME ALUNO_CPF ALUNO_RG ALUNO_NASCIMENTO ALUNO_ESTADO_CIVIL ALUNO_PROFISSAO ALUNO_EMAIL ALUNO_TELEFONE
ALUNO_ENDERECO ENDERECO_LOGRADOURO ENDERECO_NUMERO ENDERECO_BAIRRO ENDERECO_CIDADE ENDERECO_CEP PROFISSIONAL_NOME
PROFISSIONAL_CREFITO UNIDADE_NOME UNIDADE_CAPACIDADE PLANO_NOME PLANO_AULAS_SEMANA PLANO_DURACAO_MESES PLANO_RECORRENCIA
TIPO_SERVICO CONTRATO_NUMERO CONTRATO_INICIO CONTRATO_FIM CONTRATO_RECORRENCIA CONTRATO_MODO_PAGAMENTO
CONTRATO_VALOR_PARCELA CONTRATO_VALOR_TOTAL DATA_HOJE""".split()


def _contexto(completo: bool) -> dict[str, str]:
    """Os mesmos dados sintéticos do gerador do golden, já nos formatos que o antigo usava."""
    if completo:
        return {
            "ALUNO_NOME": "Maria da Silva", "ALUNO_CPF": "52998224725", "ALUNO_RG": "12.345.678-9",
            "ALUNO_NASCIMENTO": "15/03/1988", "ALUNO_ESTADO_CIVIL": "Casado(a)", "ALUNO_PROFISSAO": "Arquiteta",
            "ALUNO_EMAIL": "maria@exemplo.com.br", "ALUNO_TELEFONE": "11999990000, 1133334444",
            "ALUNO_ENDERECO": "Rua das Flores, 120 - Centro - Sao Paulo (01000-000)",
            "ENDERECO_LOGRADOURO": "Rua das Flores", "ENDERECO_NUMERO": "120", "ENDERECO_BAIRRO": "Centro",
            "ENDERECO_CIDADE": "Sao Paulo", "ENDERECO_CEP": "01000-000", "PROFISSIONAL_NOME": "Dra. Ana Lima",
            "PROFISSIONAL_CREFITO": "123456-F", "UNIDADE_NOME": "Studio Centro", "UNIDADE_CAPACIDADE": "6",
            "PLANO_NOME": "Pilates 2x", "PLANO_AULAS_SEMANA": "2", "PLANO_DURACAO_MESES": "6",
            "PLANO_RECORRENCIA": "Mensal", "TIPO_SERVICO": "Pilates", "CONTRATO_NUMERO": "1024",
            "CONTRATO_INICIO": "01/11/2026", "CONTRATO_FIM": "30/04/2027", "CONTRATO_RECORRENCIA": "Mensal",
            "CONTRATO_MODO_PAGAMENTO": "Pix", "CONTRATO_VALOR_PARCELA": md.formatar_moeda(360),
            "CONTRATO_VALOR_TOTAL": md.formatar_moeda(1234.5), "DATA_HOJE": g.HOJE,
        }
    return {
        "ALUNO_NOME": "Joao", "ALUNO_CPF": "SEM_CPF_abc", "ALUNO_RG": "", "ALUNO_NASCIMENTO": "",
        "ALUNO_ESTADO_CIVIL": "", "ALUNO_PROFISSAO": "", "ALUNO_EMAIL": "", "ALUNO_TELEFONE": "", "ALUNO_ENDERECO": "",
        "ENDERECO_LOGRADOURO": "", "ENDERECO_NUMERO": "", "ENDERECO_BAIRRO": "", "ENDERECO_CIDADE": "",
        "ENDERECO_CEP": "", "PROFISSIONAL_NOME": "Dra. Ana Lima", "PROFISSIONAL_CREFITO": "",
        "UNIDADE_NOME": "Studio Centro", "UNIDADE_CAPACIDADE": "", "PLANO_NOME": "Pilates 2x",
        "PLANO_AULAS_SEMANA": "", "PLANO_DURACAO_MESES": "", "PLANO_RECORRENCIA": "Mensal", "TIPO_SERVICO": "",
        "CONTRATO_NUMERO": "1024", "CONTRATO_INICIO": "01/11/2026", "CONTRATO_FIM": "30/04/2027",
        "CONTRATO_RECORRENCIA": "", "CONTRATO_MODO_PAGAMENTO": "", "CONTRATO_VALOR_PARCELA": md.formatar_moeda("x"),
        "CONTRATO_VALOR_TOTAL": md.formatar_moeda(None), "DATA_HOJE": g.HOJE,
    }


# ------------------------------------------------------------------------- lista oficial


def test_lista_oficial_tem_as_31_variaveis_do_antigo_na_mesma_ordem():
    assert [v.chave for v in md.VARIAVEIS] == ANTIGAS_31
    assert len(md.CHAVES) == 31


def test_toda_variavel_tem_descricao_e_exemplo():
    for v in md.VARIAVEIS:
        assert v.descricao and v.exemplo
        assert v.marcador == "{" + v.chave + "}"


def test_variaveis_do_termo_sao_as_que_o_antigo_trocava():
    esperado = set(ANTIGAS_31[:14]) | {"DATA_HOJE"}
    assert md.CHAVES_TERMO == esperado
    assert {v.chave for v in md.variaveis_do_escopo("termo")} == esperado
    assert len(md.variaveis_do_escopo("contrato")) == 31


def test_contexto_de_exemplo_cobre_o_escopo():
    assert set(md.contexto_exemplo()) == md.CHAVES
    assert set(md.contexto_exemplo("termo")) == md.CHAVES_TERMO


# ------------------------------------------------------------------------- caracterização (golden do antigo)


def _sem_milhar(texto: str) -> str:
    """DIVERGÊNCIA INTENCIONAL (moeda): o antigo gerava ``R$ 1234,50``; o novo gera ``R$ 1.234,50``.
    Só esse campo é normalizado antes de comparar com o golden do antigo."""
    return re.sub(r"R\$ (\d{1,3})\.(\d{3}),", lambda m: f"R$ {m[1]}{m[2]},", texto)


@pytest.mark.parametrize("completo,modelo,esperado", g.CONTRATOS)
def test_contrato_igual_ao_render_contrato_html_antigo(completo, modelo, esperado):
    html = md.MODELO_CONTRATO_PADRAO if modelo is None else modelo
    assert _sem_milhar(md.renderizar(html, _contexto(completo), escapar=False)) == esperado


def test_moeda_do_contrato_diverge_do_antigo_so_no_separador_de_milhar():
    saida = md.renderizar("{CONTRATO_VALOR_TOTAL}", {"CONTRATO_VALOR_TOTAL": md.formatar_moeda(1234.5)})
    assert saida == "R$ 1.234,50"
    assert "R$ 1234,50" in g.CONTRATOS[0][2]  # o golden do antigo continua sem separador


@pytest.mark.parametrize("completo,modelo,esperado", g.TERMOS)
def test_termo_igual_ao_render_termo_html_antigo(completo, modelo, esperado):
    ctx = {k: v for k, v in _contexto(completo).items() if k in md.CHAVES_TERMO}
    assert md.renderizar(modelo, ctx, escapar=False, escopo="termo") == esperado


def test_termo_deixa_literais_as_variaveis_de_contrato_como_o_antigo():
    saida = md.renderizar("{ALUNO_NOME} {PLANO_NOME}", {"ALUNO_NOME": "Ana", "PLANO_NOME": "X"}, escopo="termo")
    assert saida == "Ana {PLANO_NOME}"


# ------------------------------------------------------------------------- segurança e robustez


def test_valor_com_html_e_escapado_por_padrao():
    saida = md.renderizar("<p>{ALUNO_NOME}</p>", {"ALUNO_NOME": '<script>alert("x")</script>'})
    assert "<script>" not in saida
    assert saida == "<p>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</p>"


def test_sem_escapar_o_valor_entra_como_veio():
    assert md.renderizar("{ALUNO_NOME}", {"ALUNO_NOME": "<b>x</b>"}, escapar=False) == "<b>x</b>"


def test_troca_em_uma_passada_valor_com_marcador_nao_e_trocado_de_novo():
    saida = md.renderizar("{ALUNO_NOME} {ALUNO_CPF}", {"ALUNO_NOME": "{ALUNO_CPF}", "ALUNO_CPF": "111"})
    assert saida == "{ALUNO_CPF} 111"


def test_variavel_ausente_vira_vazio_ou_marcador_configuravel():
    assert md.renderizar("a{ALUNO_RG}b", {}) == "ab"
    assert md.renderizar("a{ALUNO_RG}b", {"ALUNO_RG": None}) == "ab"
    assert md.renderizar("a{ALUNO_RG}b", {"ALUNO_RG": ""}, ausente="____") == "a____b"


def test_desconhecida_fica_literal_ou_recebe_marcador():
    assert md.renderizar("{FOO} {ALUNO_NOME}", {"ALUNO_NOME": "Ana", "FOO": "x"}) == "{FOO} Ana"
    assert md.renderizar("{FOO}", {}, marcador_desconhecida="[{chave}?]") == "[FOO?]"


@pytest.mark.parametrize("html", [None, "", "sem variáveis"])
def test_entradas_vazias_nao_levantam(html):
    assert md.renderizar(html, None) == (html or "")


def test_contexto_estranho_nao_levanta():
    class Ruim(dict):
        def get(self, *_a, **_k):
            raise RuntimeError("boom")

    assert md.renderizar("{ALUNO_NOME}", Ruim()) == ""
    assert md.renderizar("{ALUNO_NOME}", {"ALUNO_NOME": 123}) == "123"
    assert md.renderizar("{ALUNO_NASCIMENTO}", {"ALUNO_NASCIMENTO": date(1988, 3, 5)}) == "05/03/1988"
    assert md.renderizar("{CONTRATO_NUMERO}", {"CONTRATO_NUMERO": Decimal("7")}) == "7"


def test_minusculas_e_chaves_mal_formadas_nao_sao_variaveis():
    texto = "{aluno_nome} { ALUNO_NOME } {ALUNO-NOME} {1ALUNO}"
    assert md.variaveis_usadas(texto) == []
    assert md.renderizar(texto, {"ALUNO_NOME": "x"}) == texto


# ------------------------------------------------------------------------- análise do modelo


def test_variaveis_usadas_sem_repetir_na_ordem():
    assert md.variaveis_usadas("{B} {A_1} {B} {ALUNO_NOME}") == ["B", "A_1", "ALUNO_NOME"]
    assert md.variaveis_usadas(None) == []


def test_variaveis_desconhecidas():
    html = "{ALUNO_NOME} {ALUNO_NOEM} {PLANO_NOME}"
    assert md.variaveis_desconhecidas(html) == ["ALUNO_NOEM"]
    assert md.variaveis_desconhecidas(html, "termo") == ["ALUNO_NOEM", "PLANO_NOME"]


def test_chaves_faltando():
    assert md.chaves_faltando({"ALUNO_NOME": "x"}, "{ALUNO_NOME} {ALUNO_CPF} {FOO}") == ["ALUNO_CPF"]


def test_formatar_moeda_com_milhar():
    assert md.formatar_moeda(Decimal("360")) == "R$ 360,00"
    assert md.formatar_moeda(1234.5) == "R$ 1.234,50"
    assert md.formatar_moeda("1234567.891") == "R$ 1.234.567,89"
    assert md.formatar_moeda(0) == "R$ 0,00"
    assert md.formatar_moeda(float("nan")) == "R$ 0,00"
    assert md.formatar_moeda(None) == "R$ 0,00"
    assert md.formatar_moeda("abc") == "R$ 0,00"


def test_formatar_data():
    assert md.formatar_data(date(2026, 1, 9)) == "09/01/2026"
    assert md.formatar_data(None) == ""
