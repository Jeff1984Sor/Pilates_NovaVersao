"""R10 - links de assinatura: tokens ANTIGOS do Django (verificados sem Django) e tokens novos.

Caracterização contra services.gerar_token_*/validar_token_* (golden gerado com o Django real) e teste CRUZADO dinâmico
com o ``django.core.signing`` real (Django está só no grupo ``dev``)."""
from __future__ import annotations

import random
import string
from datetime import UTC, datetime
from unittest import mock

import pytest

from app.domain import tokens_legados as tk
from tests.domain.golden import golden_tokens as g

ERROS = {"SignatureExpired": tk.TokenExpirado, "BadSignature": tk.TokenInvalido}


def _resultado(fn, token, *args):
    try:
        return ("ok", fn(token, *args))
    except tk.TokenExpirado:
        return ("erro", "SignatureExpired")
    except tk.TokenInvalido:
        return ("erro", "BadSignature")
    except Exception as exc:  # noqa: BLE001 - registra qualquer outra falha
        return ("erro", type(exc).__name__)


# ---------------------------------------------------------------- golden do Django antigo ---------------------

@pytest.mark.parametrize("pk,ts,token_contrato,token_termo", g.EMITIDOS)
def test_r10_gera_o_mesmo_token_que_o_django_antigo(pk, ts, token_contrato, token_termo):
    assert tk.gerar_token_django(str(pk), tk.SAL_CONTRATO, g.CHAVE, ts) == token_contrato
    assert tk.gerar_token_django(str(pk), tk.SAL_TERMO, g.CHAVE, ts) == token_termo


@pytest.mark.parametrize("pk,ts,token_contrato,token_termo", g.EMITIDOS)
def test_r10_verifica_tokens_emitidos_pelo_django_antigo(pk, ts, token_contrato, token_termo):
    assert tk.verificar_token_contrato(token_contrato, g.CHAVE, ts + 60) == pk
    assert tk.verificar_token_termo(token_termo, g.CHAVE, ts + 60) == pk


@pytest.mark.parametrize("rotulo,agora,contrato_ok,termo_ok,contrato_como_termo,termo_como_contrato", g.VALIDACOES)
def test_r10_validade_identica_ao_antigo_expirado_e_salt_errado(rotulo, agora, contrato_ok, termo_ok, contrato_como_termo, termo_como_contrato):
    assert _resultado(tk.verificar_token_contrato, g.TOKEN_CONTRATO, g.CHAVE, agora) == contrato_ok, rotulo
    assert _resultado(tk.verificar_token_termo, g.TOKEN_TERMO, g.CHAVE, agora) == termo_ok, rotulo
    # salt errado: token de contrato lido como termo e vice-versa
    assert _resultado(tk.verificar_token_termo, g.TOKEN_CONTRATO, g.CHAVE, agora) == contrato_como_termo, rotulo
    assert _resultado(tk.verificar_token_contrato, g.TOKEN_TERMO, g.CHAVE, agora) == termo_como_contrato, rotulo


def test_r10_prazos_7_e_30_dias_com_limite_inclusivo():
    t0 = g.T0
    assert tk.verificar_token_contrato(g.TOKEN_CONTRATO, g.CHAVE, t0 + 7 * 86400) == 123
    with pytest.raises(tk.TokenExpirado):
        tk.verificar_token_contrato(g.TOKEN_CONTRATO, g.CHAVE, t0 + 7 * 86400 + 1)
    assert tk.verificar_token_termo(g.TOKEN_TERMO, g.CHAVE, t0 + 30 * 86400) == 4567
    with pytest.raises(tk.TokenExpirado):
        tk.verificar_token_termo(g.TOKEN_TERMO, g.CHAVE, t0 + 30 * 86400 + 1)
    assert (tk.VALIDADE_CONTRATO_DIAS, tk.VALIDADE_TERMO_DIAS) == (7, 30)


@pytest.mark.parametrize("nome,token,esperado", g.ADULTERADOS)
def test_r10_token_adulterado_igual_ao_antigo(nome, token, esperado):
    assert _resultado(tk.verificar_token_contrato, token, g.CHAVE, g.T0 + 10) == esperado, nome


def test_r10_chave_errada_e_recusada_como_no_antigo():
    assert g.CHAVE_ERRADA == [("erro", "BadSignature")]
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token_contrato(g.TOKEN_CONTRATO, "outra-chave-qualquer", g.T0 + 10)


def test_r10_chaves_de_fallback_como_secret_key_fallbacks():
    assert tk.verificar_token_contrato(g.TOKEN_CONTRATO, ["chave-nova", g.CHAVE], g.T0 + 10) == 123


def test_r10_aceita_datetime_com_fuso_como_agora():
    agora = datetime.fromtimestamp(g.T0 + 3600, tz=UTC)
    assert tk.verificar_token_contrato(g.TOKEN_CONTRATO, g.CHAVE, agora) == 123


# ---------------------------------------------------------------- teste cruzado com o Django real --------------

def test_r10_cruzado_django_assina_dominio_verifica_e_vice_versa():
    signing = pytest.importorskip("django.core.signing")
    rnd = random.Random(20261025)
    alfabeto = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    for _ in range(300):
        chave = "".join(rnd.choice(alfabeto) for _ in range(rnd.randint(8, 70)))
        sal = rnd.choice([tk.SAL_CONTRATO, tk.SAL_TERMO, "outro-sal", "x"])
        valor = str(rnd.choice([0, 1, 7, 123, 99999, rnd.randint(1, 10**9)]))
        ts = rnd.randint(0, 4_000_000_000)

        with mock.patch("django.core.signing.time.time", lambda ts=ts: float(ts)):
            do_django = signing.TimestampSigner(key=chave, salt=sal, fallback_keys=[]).sign(valor)
        # (a) o que o Django assina, o dominio verifica
        assert tk.verificar_token_django(do_django, sal, chave, 10**12, ts + 5) == valor
        # (b) o que o dominio assina e idêntico byte a byte e o Django aceita
        meu = tk.gerar_token_django(valor, sal, chave, ts)
        assert meu == do_django
        with mock.patch("django.core.signing.time.time", lambda ts=ts: float(ts) + 5):
            assert signing.TimestampSigner(key=chave, salt=sal, fallback_keys=[]).unsign(meu, max_age=60) == valor


def test_r10_cruzado_expirado_adulterado_e_salt_errado_concordam_com_o_django():
    signing = pytest.importorskip("django.core.signing")
    chave, ts = "chave-cruzada", 1_800_000_000
    with mock.patch("django.core.signing.time.time", lambda: float(ts)):
        token = signing.TimestampSigner(key=chave, salt=tk.SAL_CONTRATO, fallback_keys=[]).sign("42")

    def django(token_, sal, agora, max_age):
        with mock.patch("django.core.signing.time.time", lambda: float(agora)):
            try:
                return ("ok", signing.TimestampSigner(key=chave, salt=sal, fallback_keys=[]).unsign(token_, max_age=max_age))
            except signing.SignatureExpired:
                return ("erro", "SignatureExpired")
            except signing.BadSignature:
                return ("erro", "BadSignature")

    def dominio(token_, sal, agora, max_age):
        try:
            return ("ok", tk.verificar_token_django(token_, sal, chave, max_age, agora))
        except tk.TokenExpirado:
            return ("erro", "SignatureExpired")
        except tk.TokenInvalido:
            return ("erro", "BadSignature")

    for token_, sal, agora, max_age in [
        (token, tk.SAL_CONTRATO, ts + 10, 100),            # valido
        (token, tk.SAL_CONTRATO, ts + 100, 100),           # limite
        (token, tk.SAL_CONTRATO, ts + 101, 100),           # expirado
        (token, tk.SAL_TERMO, ts + 10, 100),               # salt errado
        (token[:-1] + ("a" if token[-1] != "a" else "b"), tk.SAL_CONTRATO, ts + 10, 100),   # adulterado
        ("99" + token[2:], tk.SAL_CONTRATO, ts + 10, 100),  # valor trocado
        (token, tk.SAL_CONTRATO, ts - 50, 100),            # emitido "no futuro"
    ]:
        assert dominio(token_, sal, agora, max_age) == django(token_, sal, agora, max_age)


# ---------------------------------------------------------------- formato novo ---------------------------------

CHAVE_NOVA = "chave-do-sistema-novo"
AGORA = 1_800_000_000


def test_r10_token_novo_ida_e_volta():
    t = tk.emitir_token("contrato", 123, CHAVE_NOVA, AGORA, 7 * 86400)
    assert t.startswith("v1.") and ":" not in t and "=" not in t
    assert tk.verificar_token(t, "contrato", CHAVE_NOVA, AGORA + 100) == "123"


def test_r10_token_novo_expira_no_prazo():
    t = tk.emitir_token("termo", "aluno-9", CHAVE_NOVA, AGORA, 3600)
    assert tk.verificar_token(t, "termo", CHAVE_NOVA, AGORA + 3600) == "aluno-9"
    with pytest.raises(tk.TokenExpirado):
        tk.verificar_token(t, "termo", CHAVE_NOVA, AGORA + 3601)


def test_r10_token_novo_recusa_finalidade_chave_e_adulteracao():
    t = tk.emitir_token("contrato", 1, CHAVE_NOVA, AGORA, 3600)
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token(t, "termo", CHAVE_NOVA, AGORA)          # link de contrato nao serve de termo
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token(t, "contrato", "outra", AGORA)
    payload, assinatura = t[3:].rsplit(".", 1)
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token(f"v1.{payload}x.{assinatura}", "contrato", CHAVE_NOVA, AGORA)
    for lixo in ("", "v1.", "v1.abc", "abc", "v1.a.b", "v1..", None):
        with pytest.raises(tk.TokenInvalido):
            tk.verificar_token(lixo, "contrato", CHAVE_NOVA, AGORA)


def test_r10_token_novo_com_assinatura_valida_mas_payload_quebrado():
    import base64
    import hashlib
    import hmac

    payload = base64.urlsafe_b64encode(b"nao-e-json").rstrip(b"=").decode()
    assinatura = base64.urlsafe_b64encode(
        hmac.new(CHAVE_NOVA.encode(), f"pilates-token-v1.{payload}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token(f"v1.{payload}.{assinatura}", "contrato", CHAVE_NOVA, AGORA)


def test_r10_aceita_novo_e_legado_na_janela_de_compatibilidade():
    novo = tk.emitir_token("contrato", 55, CHAVE_NOVA, g.T0, 7 * 86400)
    r = tk.verificar_token_aceitando_legado(novo, "contrato", CHAVE_NOVA, g.CHAVE, g.T0 + 60)
    assert (r.sujeito, r.formato) == ("55", "novo")
    r = tk.verificar_token_aceitando_legado(g.TOKEN_CONTRATO, "contrato", CHAVE_NOVA, g.CHAVE, g.T0 + 60)
    assert (r.sujeito, r.formato) == ("123", "legado")
    r = tk.verificar_token_aceitando_legado(g.TOKEN_TERMO, "termo", CHAVE_NOVA, [g.CHAVE], g.T0 + 60)
    assert (r.sujeito, r.formato) == ("4567", "legado")


def test_r10_legado_recusado_sem_chave_antiga_ou_com_finalidade_desconhecida():
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token_aceitando_legado(g.TOKEN_CONTRATO, "contrato", CHAVE_NOVA, None, g.T0 + 60)
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token_aceitando_legado(g.TOKEN_CONTRATO, "documento", CHAVE_NOVA, g.CHAVE, g.T0 + 60)
    with pytest.raises(tk.TokenExpirado):
        tk.verificar_token_aceitando_legado(g.TOKEN_CONTRATO, "contrato", CHAVE_NOVA, g.CHAVE, g.T0 + 8 * 86400)


def test_r10_base62_ida_e_volta():
    for n in (0, 1, 61, 62, 3843, 1_761_400_000, 4_000_000_000):
        assert tk._b62_decode(tk._b62_encode(n)) == n
    assert tk._b62_encode(1_761_400_000) == "1vCebQ"
    assert tk._b62_decode("-1") == -1 and tk._b62_encode(-1) == "-1"


def test_r10_token_sem_separador_ou_timestamp():
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token_django("semdoispontos", tk.SAL_CONTRATO, g.CHAVE, 100, 0)
    # assinatura valida para "123" sem timestamp: o antigo tambem recusa (ValueError no rsplit); aqui TokenInvalido
    sem_ts = "123:" + tk._assinatura_django("123", tk.SAL_CONTRATO, g.CHAVE)
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token_django(sem_ts, tk.SAL_CONTRATO, g.CHAVE, 100, 0)
    # timestamp com caractere fora do alfabeto base62, mas assinado corretamente
    assinado = "123:%%%"
    token = f"{assinado}:{tk._assinatura_django(assinado, tk.SAL_CONTRATO, g.CHAVE)}"
    with pytest.raises(tk.TokenInvalido):
        tk.verificar_token_django(token, tk.SAL_CONTRATO, g.CHAVE, 100, 0)
