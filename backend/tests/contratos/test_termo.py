"""Termo de uso de imagem por link (30 dias): tokens novos e legados, segurança e ponto de extensão do módulo alunos."""

import time

import pytest
from sqlalchemy import select

from app.core import storage
from app.core.config import settings
from app.core.models import Auditoria
from app.domain import tokens_legados as legado
from app.modules.alunos import servico as alunos_servico
from app.modules.alunos.models import Aluno
from app.modules.contratos import servico, termo_publico, tokens
from tests.contratos.conftest import cabecalho, png_data_url

CPF = "529.982.247-25"
CHAVE_ANTIGA = "chave-secreta-do-django-antigo-so-para-teste-0123456789"


def corpo(**extra):
    return {"nome": "Maria da Silva Souza", "documento": CPF, "assinatura": png_data_url(), "li_e_concordo": True, **extra}


@pytest.fixture
def token(cen):
    return tokens.emitir_termo(cen.aluno.id).token


def test_visualizar_termo_renderiza_com_os_dados_do_aluno_sem_efeito_colateral(client, db, cen, token):
    r = client.get(f"/api/assinar/termo/{token}")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["estado"] == "pendente" and j["termo_nome"] == "Termo de imagem" and "Maria da Silva Souza" in j["html"]
    assert j["aluno_primeiro_nome"] == "Maria"
    db.expire_all()
    a = db.get(Aluno, cen.aluno.id)
    assert a.termo_assinado_em is None and a.termo_aceite_em is None and a.autoriza_imagem is False


def test_assinar_termo_grava_assinatura_ip_e_autoriza_imagem(client, db, cen, token, emails):
    r = client.post(f"/api/assinar/termo/{token}", json=corpo(), headers={"x-forwarded-for": "198.51.100.4"})
    assert r.status_code == 200, r.text
    db.expire_all()
    a = db.get(Aluno, cen.aluno.id)
    assert a.termo_assinado_em and a.autoriza_imagem is True and a.termo_assinatura_nome == "Maria da Silva Souza"
    assert a.termo_assinatura_documento == CPF and a.termo_assinatura_ip == "198.51.100.4" and a.termo_uso_id
    assert storage.ler(a.termo_assinatura_path).startswith(b"\x89PNG")
    au = db.scalar(select(Auditoria).where(Auditoria.acao == "aluno.termo.assinar_link"))
    assert au and au.usuario_id is None
    v = client.get(f"/api/assinar/termo/{token}").json()
    assert v["estado"] == "assinado" and v["html"] is None and v["assinado_em"] and v["termo_nome"] is None
    assert "Termo de uso de imagem" in emails[-1][1]


def test_termo_nao_assina_duas_vezes_e_valida_cpf(client, db, cen, token):
    url = f"/api/assinar/termo/{token}"
    assert client.post(url, json=corpo(documento="123.456.789-00")).status_code == 422
    assert client.post(url, json=corpo(li_e_concordo=False)).status_code == 422
    assert client.post(url, json=corpo()).status_code == 200
    r = client.post(url, json=corpo(nome="Outra Pessoa"))
    assert r.status_code == 409
    db.expire_all()
    assert db.get(Aluno, cen.aluno.id).termo_assinatura_nome == "Maria da Silva Souza"


def test_termo_link_invalido_expirado_e_de_contrato(client, cen, db):
    assert client.get("/api/assinar/termo/lixo").status_code == 404
    velho = tokens.emitir_termo(cen.aluno.id, agora_s=time.time() - 31 * 86400).token
    assert client.get(f"/api/assinar/termo/{velho}").status_code == 410
    de_contrato = tokens.emitir_contrato(cen.aluno.id).token
    assert client.get(f"/api/assinar/termo/{de_contrato}").status_code == 404
    assert client.get(f"/api/assinar/contrato/{tokens.emitir_termo(cen.aluno.id).token}").status_code == 404
    assert client.get(f"/api/assinar/termo/{tokens.emitir_termo(99999).token}").status_code == 404


def test_termo_com_token_legado_e_salt_errado(client, cen, db, monkeypatch):
    monkeypatch.setattr(settings, "legacy_django_secret_key", CHAVE_ANTIGA, raising=False)
    ok = legado.gerar_token_django(str(cen.aluno.id), legado.SAL_TERMO, CHAVE_ANTIGA, time.time() - 20 * 86400)  # 20 dias: ainda vale
    assert client.get(f"/api/assinar/termo/{ok}").status_code == 200
    expirado = legado.gerar_token_django(str(cen.aluno.id), legado.SAL_TERMO, CHAVE_ANTIGA, time.time() - 31 * 86400)
    assert client.get(f"/api/assinar/termo/{expirado}").status_code == 410
    sal_errado = legado.gerar_token_django(str(cen.aluno.id), legado.SAL_CONTRATO, CHAVE_ANTIGA, time.time())
    assert client.get(f"/api/assinar/termo/{sal_errado}").status_code == 404
    assert client.post(f"/api/assinar/termo/{ok}", json=corpo()).status_code == 200


def test_sem_termo_cadastrado_avisa(client, db, cen, token):
    from app.modules.cadastros.models import TermoUso

    for t in db.scalars(select(TermoUso)):
        db.delete(t)
    db.commit()
    assert client.get(f"/api/assinar/termo/{token}").status_code == 409


def test_rate_limit_do_termo(client, token):
    codigos = [client.post(f"/api/assinar/termo/{token}", json=corpo(documento="1")).status_code for _ in range(12)]
    assert codigos[:10] == [422] * 10 and codigos[10:] == [429, 429]


# ----------------------------------------------------------------------------------------- lado do estúdio
def test_gerar_link_e_enviar_por_email_e_whatsapp(client, db, cen, secretaria, professor, monkeypatch):
    h = cabecalho(secretaria)
    r = client.post(f"/api/contratos/termo/{cen.aluno.id}/link", headers=h)
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith(settings.frontend_url + "/assinar/termo/")
    assert client.get("/api/assinar/termo/" + url.rsplit("/", 1)[1]).status_code == 200
    assert client.post(f"/api/contratos/termo/{cen.aluno.id}/link", headers=cabecalho(professor)).status_code == 403
    assert client.post(f"/api/contratos/termo/{cen.aluno.id}/link").status_code == 401
    assert client.post("/api/contratos/termo/9999/link", headers=h).status_code == 404

    enviados = []
    monkeypatch.setattr("app.core.email.enviar", lambda para, assunto, texto, **k: enviados.append((para, assunto, texto)) or True)
    r = client.post(f"/api/contratos/termo/{cen.aluno.id}/enviar", json={"canal": "email"}, headers=h)
    assert r.status_code == 200 and "/assinar/termo/" in enviados[0][2] and "30 dias" in enviados[0][2]
    assert client.post(f"/api/contratos/termo/{cen.aluno.id}/enviar", json={"canal": "whatsapp"}, headers=h).status_code == 503
    recebidas = []
    servico.definir_enviador_whatsapp(lambda db_, m: recebidas.append(m))
    assert client.post(f"/api/contratos/termo/{cen.aluno.id}/enviar", json={"canal": "whatsapp"}, headers=h).status_code == 200
    assert recebidas[0].tipo == "termo_assinatura" and "/assinar/termo/" in recebidas[0].link
    assert client.post(f"/api/contratos/termo/{cen.aluno.id}/enviar", json={"canal": "sms"}, headers=h).status_code == 422


def test_nao_gera_link_se_termo_ja_assinado(client, db, cen, secretaria, token):
    assert client.post(f"/api/assinar/termo/{token}", json=corpo()).status_code == 200
    assert client.post(f"/api/contratos/termo/{cen.aluno.id}/link", headers=cabecalho(secretaria)).status_code == 409


def test_ponto_de_extensao_substitui_a_funcao_do_modulo_alunos(cen, db, monkeypatch):
    original = alunos_servico.gerar_link_assinatura_termo
    with pytest.raises(NotImplementedError):
        original(cen.aluno)
    try:
        termo_publico.registrar_no_modulo_alunos()
        link = alunos_servico.gerar_link_assinatura_termo(cen.aluno)
        assert link.startswith(settings.frontend_url + "/assinar/termo/")
        assert tokens.ler_termo(link.rsplit("/", 1)[1]).sujeito_id == cen.aluno.id
    finally:
        alunos_servico.gerar_link_assinatura_termo = original
