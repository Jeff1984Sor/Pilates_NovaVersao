"""R16 - CPF. Caracterização contra validators.validar_cpf e receita_saude.cpf_valido/so_digitos."""
import pytest

from app.domain import documentos
from tests.domain.golden.golden_documentos import CPFS


@pytest.mark.parametrize("entrada,valido_validators,valido_receita,digitos", CPFS)
def test_r16_cpf_identico_aos_dois_algoritmos_antigos(entrada, valido_validators, valido_receita, digitos):
    assert valido_validators == valido_receita  # os dois algoritmos antigos concordam
    assert documentos.validar_cpf(entrada) is valido_validators
    assert documentos.so_digitos(entrada) == digitos


def test_r16_normalizar_e_formatar_cpf():
    assert documentos.normalizar_cpf("529.982.247-25") == "52998224725"
    assert documentos.normalizar_cpf(None) == ""
    assert documentos.formatar_cpf("52998224725") == "529.982.247-25"
    assert documentos.formatar_cpf("123") == "123"
    assert documentos.formatar_cpf(None) == ""


def test_r16_sem_cpf_marcador():
    marcador = documentos.gerar_marcador_sem_cpf("0123456789abcdef0000")
    assert marcador == "SEM_CPF_0123456789abcdef"
    assert documentos.eh_sem_cpf(marcador)
    assert not documentos.eh_sem_cpf("52998224725")
    assert not documentos.eh_sem_cpf(None)
    assert documentos.normalizar_cpf(marcador) == marcador


def test_r16_mesmo_cpf_ignora_mascara():
    assert documentos.mesmo_cpf("529.982.247-25", "52998224725")
    assert not documentos.mesmo_cpf("529.982.247-25", "11144477735")
    assert not documentos.mesmo_cpf("", "")
    assert not documentos.mesmo_cpf(None, "52998224725")


def test_r16_marcador_sem_cpf_nunca_casa_com_cpf_digitado():
    # COMPORTAMENTO ANTIGO corrigido: so_digitos("SEM_CPF_12345678901abcde") == "12345678901"
    marcador = "SEM_CPF_12345678901abcde"
    assert documentos.so_digitos(marcador) == "12345678901"
    assert not documentos.mesmo_cpf(marcador, "12345678901")
    assert documentos.mesmo_cpf(marcador, marcador)
