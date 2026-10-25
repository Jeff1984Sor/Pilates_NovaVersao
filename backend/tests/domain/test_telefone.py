"""R16 - telefone: forma canônica nova + caracterização dos 3 comportamentos antigos."""
import pytest

from app.domain import telefone as tel
from tests.domain.golden.golden_telefone import (
    CLEAN_PHONE, ENTRADAS, FORMAT_LISTAS, FORMAT_WHATSAPP, PARES_MESMO, TELEFONE_CANON,
)


# ---- os três comportamentos antigos, portados fielmente --------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", CLEAN_PHONE)
def test_r16_clean_phone_antigo(entrada, esperado):
    assert tel.limpar_telefone_antigo(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", FORMAT_WHATSAPP)
def test_r16_format_whatsapp_number_antigo(entrada, esperado):
    assert tel.formatar_whatsapp_antigo([entrada]) == esperado


@pytest.mark.parametrize("lista,esperado", FORMAT_LISTAS)
def test_r16_format_whatsapp_number_antigo_com_listas(lista, esperado):
    assert tel.formatar_whatsapp_antigo(lista) == esperado


@pytest.mark.parametrize("entrada,esperado", TELEFONE_CANON)
def test_r16_telefone_canon_antigo(entrada, esperado):
    assert tel.chave_telefone(entrada) == esperado


@pytest.mark.parametrize("a,b,igual", PARES_MESMO)
def test_r16_mesmo_telefone_igual_ao_canon_antigo(a, b, igual):
    assert tel.mesmo_telefone(a, b) is igual


# ---- forma canônica nova --------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("(15) 99776-2467", "5515997762467"),   # com máscara, com 9
        ("15997762467", "5515997762467"),        # sem DDI
        ("5515997762467", "5515997762467"),      # com DDI
        ("+55 (15) 99776-2467", "5515997762467"),
        ("015997762467", "5515997762467"),       # zero de tronco
        ("0 15 99776-2467", "5515997762467"),
        ("1597762467", "5515997762467"),         # celular antigo sem o 9 -> ganha o nono dígito
        ("551597762467", "5515997762467"),
        ("15 9776-2467", "5515997762467"),
        ("(15) 3333-4444", "551533334444"),      # fixo continua com 10 dígitos
        ("551533334444", "551533334444"),
        ("(11) 98888-7777", "5511988887777"),
        ("(55) 99123-4567", "5555991234567"),    # DDD 55 (RS)
        ("5555991234567", "5555991234567"),
        ("555599123456", "5555999123456"),       # DDI + DDD 55 + celular antigo sem 9 -> ganha o 9
        ("55991234567", "5555991234567"),        # só DDD 55 + 9 dígitos
    ],
)
def test_r16_normalizar_telefone_br(entrada, esperado):
    assert tel.normalizar_telefone_br(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", None, "abc", "55", "5599", "123", "99776-2467", "997762467", "97762467", "11812345678", "1112345678",
     "11 1234-5678", "119888877770", "+1 415 555 2671", "(10) 99999-8888", "11 0234-5678"],
)
def test_r16_normalizar_telefone_br_invalidos(entrada):
    assert tel.normalizar_telefone_br(entrada) is None


def test_r16_sem_nono_digito_opcional():
    assert tel.normalizar_telefone_br("1597762467", adicionar_nono_digito=False) == "551597762467"


def test_r16_tipo_telefone():
    assert tel.tipo_telefone("5515997762467") == "celular"
    assert tel.tipo_telefone("551533334444") == "fixo"
    assert tel.tipo_telefone("551597762467") == "celular"
    assert tel.tipo_telefone(None) is None
    assert tel.tipo_telefone("5512") is None


def test_r16_primeiro_telefone_valido():
    assert tel.primeiro_telefone_valido(["", "123", "(15) 99776-2467", "11 98888-7777"]) == "5515997762467"
    assert tel.primeiro_telefone_valido([]) is None


def test_r16_canonica_concorda_com_o_envio_antigo_quando_o_antigo_era_valido():
    """Onde o clean_phone antigo produzia 55+10/11 dígitos, o novo produz o mesmo, exceto celular de 10 dígitos
    (que agora ganha o nono dígito)."""
    for entrada, antigo in CLEAN_PHONE:
        novo = tel.normalizar_telefone_br(entrada)
        if antigo and antigo.startswith("55") and len(antigo) in (12, 13) and novo is not None:
            if tel.tipo_telefone(antigo) == "celular" and len(antigo) == 12:
                assert novo == antigo[:4] + "9" + antigo[4:], entrada
            else:
                assert novo == antigo, entrada


def test_r16_mesmo_telefone_com_e_sem_nono_digito_e_ddi():
    assert tel.mesmo_telefone("5515997762467", "(15) 9776-2467")
    assert tel.mesmo_telefone("(15) 99776-2467", "1597762467")
    assert not tel.mesmo_telefone("(15) 99776-2467", "(11) 99776-2467")
    assert not tel.mesmo_telefone("", "")
    assert not tel.mesmo_telefone("123", "123")


def test_r16_entradas_do_golden_nao_levantam_excecao():
    for e in ENTRADAS:
        tel.normalizar_telefone_br(e)
        tel.chave_telefone(e)
