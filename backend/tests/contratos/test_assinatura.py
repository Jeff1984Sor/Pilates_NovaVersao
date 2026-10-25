"""Assinatura por link (R10): tokens novos e legados, prazos, adulteração, GET sem efeito colateral, assinatura dupla,
rate limit, sem vazamento de dados, assinatura local, envio por e-mail e WhatsApp (ponto de extensão) e confirmações."""

import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core import links, storage
from app.core.config import settings
from app.core.models import Auditoria
from app.domain import tokens_legados as legado
from app.modules.alunos.models import AlunoDocumento
from app.modules.contratos import servico, tokens
from app.modules.contratos.models import Contrato, StatusAssinatura
from tests.contratos.conftest import cabecalho, png_data_url

CHAVE_ANTIGA = "chave-secreta-do-django-antigo-so-para-teste-0123456789"
CPF = "529.982.247-25"


def corpo(**extra):
    base = {"nome": "Maria da Silva Souza", "documento": CPF, "assinatura": png_data_url(), "li_e_concordo": True}
    return {**base, **extra}


@pytest.fixture
def contrato_id(novo_contrato):
    return novo_contrato()["contrato"]["id"]


@pytest.fixture
def token(contrato_id):
    return tokens.emitir_contrato(contrato_id).token


@pytest.fixture
def chave_antiga(monkeypatch):
    monkeypatch.setattr(settings, "legacy_django_secret_key", CHAVE_ANTIGA, raising=False)
    return CHAVE_ANTIGA


def legado_token(contrato_id, *, sal=legado.SAL_CONTRATO, chave=CHAVE_ANTIGA, quando=None):
    return legado.gerar_token_django(str(contrato_id), sal, chave, quando if quando is not None else time.time())


def total(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


# ------------------------------------------------------------------------------------------------ tokens (unidade)
def test_token_novo_vale_7_dias_e_tem_finalidade():
    t = tokens.emitir_contrato(42, agora_s=1_000_000)
    assert tokens.ler_contrato(t.token, agora_s=1_000_000 + 7 * 86400).sujeito_id == 42
    with pytest.raises(links.LinkExpirado):
        tokens.ler_contrato(t.token, agora_s=1_000_000 + 7 * 86400 + 2)
    assert t.expira_em == datetime.fromtimestamp(1_000_000 + 7 * 86400, tz=UTC)
    with pytest.raises(links.LinkInvalido):
        tokens.ler_termo(t.token)  # token de contrato não vale como termo
    termo = tokens.emitir_termo(9, agora_s=1_000_000)
    assert tokens.ler_termo(termo.token, agora_s=1_000_000 + 30 * 86400).sujeito_id == 9
    with pytest.raises(links.LinkExpirado):
        tokens.ler_termo(termo.token, agora_s=1_000_000 + 30 * 86400 + 2)
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato(termo.token)


def test_token_novo_adulterado_ou_lixo_e_invalido():
    t = tokens.emitir_contrato(1).token
    bruto, mac = t.split(".")
    for ruim in (bruto + "." + mac[:-2] + "AA", "x" + t, t + "x", bruto, "", "...", "a.b.c", "v1.a.b", " "):
        with pytest.raises(links.LinkInvalido):
            tokens.ler_contrato(ruim)
    outro = links.assinar("arquivo", {"p": "documentos/1/a.pdf"}, 3600)  # link de outra finalidade do sistema
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato(outro)


def test_token_legado_do_django(chave_antiga):
    agora = 1_800_000_000
    t = legado_token(77, quando=agora)
    lido = tokens.ler_contrato(t, agora_s=agora + 3600)
    assert (lido.sujeito_id, lido.formato) == (77, "legado")
    assert tokens.ler_contrato(t, agora_s=agora + 7 * 86400).sujeito_id == 77  # no limite ainda vale
    with pytest.raises(links.LinkExpirado):
        tokens.ler_contrato(t, agora_s=agora + 7 * 86400 + 5)
    # termo: 30 dias
    tt = legado_token(5, sal=legado.SAL_TERMO, quando=agora)
    assert tokens.ler_termo(tt, agora_s=agora + 29 * 86400).sujeito_id == 5
    with pytest.raises(links.LinkExpirado):
        tokens.ler_termo(tt, agora_s=agora + 31 * 86400)


def test_token_legado_salt_errado_chave_errada_ou_sem_chave(monkeypatch):
    monkeypatch.setattr(settings, "legacy_django_secret_key", CHAVE_ANTIGA, raising=False)
    agora = 1_800_000_000
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato(legado_token(1, sal=legado.SAL_TERMO, quando=agora), agora_s=agora)  # sal do termo no contrato
    with pytest.raises(links.LinkInvalido):
        tokens.ler_termo(legado_token(1, sal=legado.SAL_CONTRATO, quando=agora), agora_s=agora)
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato(legado_token(1, chave="outra-chave-qualquer-0123456789-0123456789", quando=agora), agora_s=agora)
    adulterado = legado_token(1, quando=agora)
    partes = adulterado.split(":")
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato(f"2:{partes[1]}:{partes[2]}", agora_s=agora)  # troca o id, mantém a assinatura
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato("1:abc:def:ghi", agora_s=agora)
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato("abc:def:ghi", agora_s=agora)
    monkeypatch.setattr(settings, "legacy_django_secret_key", None, raising=False)
    with pytest.raises(links.LinkInvalido):
        tokens.ler_contrato(adulterado.replace(partes[0], "1"), agora_s=agora)  # sem a chave antiga, token antigo não vale


# ------------------------------------------------------------------------------------------------- página pública
def test_visualizar_mostra_o_contrato_sem_efeito_colateral(client, db, contrato_id, token):
    antes = (total(db, AlunoDocumento), db.get(Contrato, contrato_id).atualizado_em, total(db, Auditoria))
    doc = db.scalar(select(AlunoDocumento))
    assinatura_antes = (doc.sha256, storage.resolver(doc.arquivo_path).stat().st_mtime_ns)
    for _ in range(3):
        r = client.get(f"/api/assinar/contrato/{token}")
        assert r.status_code == 200, r.text
    j = r.json()
    assert j["estado"] == "pendente" and j["numero"] == db.get(Contrato, contrato_id).codigo_legado
    assert j["aluno_primeiro_nome"] == "Maria" and "Maria da Silva Souza" in j["html"] and "CONTRATO Nº" in j["html"]
    assert "<script" not in j["html"]
    pdf = client.get(f"/api/assinar/contrato/{token}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert "inline" in pdf.headers["content-disposition"] and "no-store" in pdf.headers["cache-control"]
    db.expire_all()
    doc = db.scalar(select(AlunoDocumento))
    assert (total(db, AlunoDocumento), db.get(Contrato, contrato_id).atualizado_em, total(db, Auditoria)) == antes
    assert (doc.sha256, storage.resolver(doc.arquivo_path).stat().st_mtime_ns) == assinatura_antes  # GET NÃO regrava o documento


def test_link_invalido_expirado_e_inexistente_nao_revelam_nada(client, db, contrato_id):
    ruim = client.get("/api/assinar/contrato/lixo")
    assert ruim.status_code == 404 and ruim.json() == {"detail": "Link inválido. Peça um novo link ao estúdio."}
    velho = tokens.emitir_contrato(contrato_id, agora_s=time.time() - 8 * 86400).token
    r = client.get(f"/api/assinar/contrato/{velho}")
    assert r.status_code == 410 and "expirou" in r.json()["detail"] and "Maria" not in r.text
    assert client.get(f"/api/assinar/contrato/{velho}/pdf").status_code == 410
    assert client.post(f"/api/assinar/contrato/{velho}", json=corpo()).status_code == 410
    inexistente = tokens.emitir_contrato(99999).token
    r = client.get(f"/api/assinar/contrato/{inexistente}")
    assert r.status_code == 404 and r.json() == ruim.json()  # mesma resposta de "token inválido"
    # token de contrato com a assinatura adulterada
    t = tokens.emitir_contrato(contrato_id).token
    assert client.get(f"/api/assinar/contrato/{t[:-3]}abc").status_code == 404


def test_assinar_por_link_grava_tudo_e_muda_o_status(client, db, contrato_id, token, emails):
    r = client.post(f"/api/assinar/contrato/{token}", json=corpo(), headers={"x-forwarded-for": "203.0.113.9"})
    assert r.status_code == 200, r.text
    db.expire_all()
    c = db.get(Contrato, contrato_id)
    assert c.status_assinatura == StatusAssinatura.ASSINADO_DIGITALMENTE
    assert c.assinatura_nome == "Maria da Silva Souza" and c.assinatura_documento == CPF and c.assinatura_ip == "203.0.113.9"
    assert c.assinado_em is not None and c.assinatura_path == f"assinaturas/contrato/contrato_{contrato_id}.png"
    assert storage.ler(c.assinatura_path).startswith(b"\x89PNG")
    a = db.scalar(select(Auditoria).where(Auditoria.acao == "contrato.assinar_link"))
    assert a and a.usuario_id is None and a.ip == "203.0.113.9" and a.depois_json["nome"] == "Maria da Silva Souza"
    # o PDF guardado do aluno foi regerado com a assinatura (mudou o hash)
    pdf = servico.gerar_pdf_do_contrato(db, c, comprimir=False)
    assert b"Maria da Silva Souza" in pdf and b"/Subtype /Image" in pdf
    # a página agora diz "assinado" e não devolve o texto
    v = client.get(f"/api/assinar/contrato/{token}").json()
    assert v["estado"] == "assinado" and v["html"] is None and v["assinado_em"]
    assert [e[1] for e in emails][-1].startswith("Contrato nº")  # confirmação por e-mail ao aluno


def test_nao_assina_duas_vezes(client, db, contrato_id, token):
    assert client.post(f"/api/assinar/contrato/{token}", json=corpo()).status_code == 200
    db.expire_all()
    primeiro = db.get(Contrato, contrato_id)
    ip1, nome1, quando1 = primeiro.assinatura_ip, primeiro.assinatura_nome, primeiro.assinado_em
    r = client.post(f"/api/assinar/contrato/{token}", json=corpo(nome="Outra Pessoa Qualquer", documento="111.444.777-35"))
    assert r.status_code == 409 and "já foi assinado" in r.json()["detail"]
    db.expire_all()
    c = db.get(Contrato, contrato_id)
    assert (c.assinatura_ip, c.assinatura_nome, c.assinado_em) == (ip1, nome1, quando1)


def test_assinatura_simultanea_so_uma_vale(db, contrato_id):
    """Duas sessões leem 'NAO_ASSINADO' ao mesmo tempo: o UPDATE condicional deixa só uma gravar e NÃO troca a imagem."""
    from app.core.db import SessionLocal

    s1, s2 = SessionLocal(), SessionLocal()
    try:
        c1, c2 = s1.get(Contrato, contrato_id), s2.get(Contrato, contrato_id)
        servico.aplicar_assinatura(s1, c1, nome="Primeira Pessoa", documento=CPF, assinatura_png=png_data_url(40, 16), ip="1.1.1.1",
                                   status=StatusAssinatura.ASSINADO_DIGITALMENTE)
        s1.commit()
        imagem = storage.ler(c1.assinatura_path)
        with pytest.raises(servico.ErroContrato) as e:
            servico.aplicar_assinatura(s2, c2, nome="Segunda Pessoa", documento="111.444.777-35", assinatura_png=png_data_url(80, 30),
                                       ip="2.2.2.2", status=StatusAssinatura.ASSINADO_DIGITALMENTE)
        assert e.value.status == 409
        assert storage.ler(c1.assinatura_path) == imagem
    finally:
        s1.close()
        s2.close()


def test_validacoes_da_assinatura(client, db, contrato_id, token):
    storage.remover(f"assinaturas/contrato/contrato_{contrato_id}.png")  # o storage é compartilhado entre testes
    url = f"/api/assinar/contrato/{token}"
    assert client.post(url, json=corpo(documento="123.456.789-00")).status_code == 422  # CPF inválido
    assert client.post(url, json=corpo(documento="111.111.111-11")).status_code == 422
    assert client.post(url, json=corpo(nome="Al")).status_code == 422
    assert client.post(url, json=corpo(li_e_concordo=False)).status_code == 422
    assert client.post(url, json=corpo(assinatura="data:image/jpeg;base64,AAAA" + "A" * 40)).status_code == 422
    assert client.post(url, json=corpo(assinatura="data:image/png;base64," + "AAAA" * 20)).status_code == 422  # não é PNG de verdade
    assert client.post(url, json={"nome": "Maria Souza"}).status_code == 422
    db.expire_all()
    assert db.get(Contrato, contrato_id).status_assinatura == StatusAssinatura.NAO_ASSINADO  # nada gravado
    assert not storage.existe(f"assinaturas/contrato/contrato_{contrato_id}.png")


def test_assinar_por_token_legado(client, db, contrato_id, chave_antiga):
    t = legado_token(contrato_id)
    assert client.get(f"/api/assinar/contrato/{t}").status_code == 200
    assert client.post(f"/api/assinar/contrato/{t}", json=corpo()).status_code == 200
    db.expire_all()
    assert db.get(Contrato, contrato_id).status_assinatura == StatusAssinatura.ASSINADO_DIGITALMENTE
    velho = legado_token(contrato_id, quando=time.time() - 8 * 86400)
    assert client.get(f"/api/assinar/contrato/{velho}").status_code == 410
    assert client.get(f"/api/assinar/contrato/{legado_token(contrato_id, sal=legado.SAL_TERMO)}").status_code == 404


def test_rate_limit_nas_rotas_publicas(client, contrato_id, token):
    url = f"/api/assinar/contrato/{token}"
    codigos = [client.post(url, json=corpo(documento="000")).status_code for _ in range(12)]
    assert codigos[:10] == [422] * 10 and codigos[10:] == [429, 429]
    assert client.post(url, json=corpo()).status_code == 429  # bloqueado até a janela passar
    r = client.get("/api/assinar/contrato/lixo")  # outro limite (leitura) segue livre
    assert r.status_code == 404
    leituras = [client.get("/api/assinar/contrato/lixo").status_code for _ in range(70)]
    assert 429 in leituras
    pdfs = [client.get(f"{url}/pdf").status_code for _ in range(35)]
    assert pdfs[0] == 200 and 429 in pdfs


# ---------------------------------------------------------------------------------------------- assinatura local
def test_assinatura_local_na_recepcao(client, full, secretaria, professor, db, contrato_id):
    url = f"/api/contratos/{contrato_id}/assinatura-local"
    dados = {"nome": "Maria da Silva Souza", "documento": CPF, "assinatura": png_data_url()}
    assert client.post(url, json=dados).status_code == 401
    assert client.post(url, json=dados, headers=cabecalho(professor)).status_code == 403
    r = client.post(url, json={**dados, "documento": "000.000.000-00"}, headers=cabecalho(secretaria))
    assert r.status_code == 422
    r = client.post(url, json=dados, headers=cabecalho(secretaria))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status_assinatura"] == "ASSINADO" and j["assinatura"]["nome"] == "Maria da Silva Souza" and j["assinatura"]["imagem_url"]
    assert j["assinatura"]["documento"] == CPF and j["assinatura"]["ip"]
    img = client.get(f"/api{j['assinatura']['imagem_url']}", headers=cabecalho(secretaria))
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    assert client.get(f"/api{j['assinatura']['imagem_url']}", headers=cabecalho(professor)).status_code == 403  # categoria exige contratos.ver
    assert client.post(url, json=dados, headers=cabecalho(full)).status_code == 409  # já assinado
    a = db.scalar(select(Auditoria).where(Auditoria.acao == "contrato.assinar_local"))
    assert a and a.usuario_nome and a.depois_json["documento"] == CPF


def test_pdf_assinado_pelo_painel_traz_a_assinatura(client, full, contrato_id):
    h = cabecalho(full)
    client.post(f"/api/contratos/{contrato_id}/assinatura-local", headers=h, json={"nome": "Maria da Silva Souza", "documento": CPF, "assinatura": png_data_url()})
    r = client.get(f"/api/contratos/{contrato_id}/pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"].startswith("inline")


# --------------------------------------------------------------------------------------------------------- envio
def test_link_de_assinatura_para_copiar(client, full, contrato_id):
    r = client.post(f"/api/contratos/{contrato_id}/link", headers=cabecalho(full))
    assert r.status_code == 200
    j = r.json()
    assert j["url"].startswith(settings.frontend_url + "/assinar/contrato/") and j["pdf_url"].endswith("/pdf")
    token = j["url"].rsplit("/", 1)[1]
    assert client.get(f"/api/assinar/contrato/{token}").status_code == 200


def test_enviar_email_com_link_e_pdf_anexo(client, full, db, contrato_id, monkeypatch):
    enviados = []

    def falso(para, assunto, corpo_, **kw):
        enviados.append((para, assunto, corpo_, kw))
        return True

    monkeypatch.setattr("app.core.email.enviar", falso)
    r = client.post(f"/api/contratos/{contrato_id}/enviar-email", headers=cabecalho(full))
    assert r.status_code == 200 and r.json()["destino"] == "maria@exemplo.com.br"
    para, assunto, texto, kw = enviados[0]
    assert para == ["maria@exemplo.com.br"] and "para assinatura" in assunto
    assert "/assinar/contrato/" in texto and "7 dias" in texto
    nome, conteudo, mime = kw["anexos"][0]
    assert nome.startswith("contrato-") and conteudo.startswith(b"%PDF") and mime == "application/pdf"
    link = texto.split("acesse:\n")[1].split("\n")[0]
    assert client.get("/api/assinar/contrato/" + link.rsplit("/", 1)[1]).status_code == 200
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "contrato.enviar_email"))


def test_enviar_email_sem_email_ou_smtp_fora(client, full, db, cen, contrato_id, monkeypatch):
    h = cabecalho(full)
    monkeypatch.setattr("app.core.email.enviar", lambda *a, **k: False)
    assert client.post(f"/api/contratos/{contrato_id}/enviar-email", headers=h).status_code == 502
    cen.aluno.email = None
    db.commit()
    assert client.post(f"/api/contratos/{contrato_id}/enviar-email", headers=h).status_code == 422


def test_whatsapp_sem_enviador_responde_503_amigavel(client, full, contrato_id):
    r = client.post(f"/api/contratos/{contrato_id}/enviar-whatsapp", headers=cabecalho(full))
    assert r.status_code == 503 and r.json()["detail"] == "WhatsApp ainda não configurado."
    assert client.get("/api/contratos/opcoes", headers=cabecalho(full)).json()["whatsapp_disponivel"] is False


def test_whatsapp_pelo_ponto_de_extensao(client, full, db, contrato_id):
    recebidas = []
    servico.definir_enviador_whatsapp(lambda db_, msg: recebidas.append(msg))
    r = client.post(f"/api/contratos/{contrato_id}/enviar-whatsapp", headers=cabecalho(full))
    assert r.status_code == 200 and r.json()["canal"] == "whatsapp"
    m = recebidas[0]
    assert m.tipo == "contrato_assinatura" and m.telefone == "5511999990000" and m.aluno_id and m.contrato_id == contrato_id
    assert "/assinar/contrato/" in m.link and m.pdf_url.endswith("/pdf") and m.pdf_nome.endswith(".pdf")
    assert client.get("/api/contratos/opcoes", headers=cabecalho(full)).json()["whatsapp_disponivel"] is True
    # o PDF do provedor baixa sem login, pelo mesmo token
    assert client.get(m.pdf_url.split("/bff", 1)[1].replace("/assinar", "/api/assinar", 1)).status_code == 200


def test_whatsapp_com_falha_do_provedor_vira_502_sem_vazar_detalhe(client, full, contrato_id):
    def quebra(*_a):
        raise RuntimeError("token-secreto-do-provedor invalido")

    servico.definir_enviador_whatsapp(quebra)
    r = client.post(f"/api/contratos/{contrato_id}/enviar-whatsapp", headers=cabecalho(full))
    assert r.status_code == 502 and "secreto" not in r.text


def test_confirmacao_por_whatsapp_ao_assinar(client, db, contrato_id, token, emails):
    recebidas = []
    servico.definir_enviador_whatsapp(lambda db_, msg: recebidas.append(msg))
    assert client.post(f"/api/assinar/contrato/{token}", json=corpo()).status_code == 200
    assert [m.tipo for m in recebidas] == ["contrato_assinado"] and "assinatura do seu contrato" in recebidas[0].texto


def test_falha_na_confirmacao_nao_desfaz_a_assinatura(client, db, contrato_id, token, monkeypatch):
    def quebra(*_a, **_k):
        raise RuntimeError("smtp fora")

    monkeypatch.setattr("app.core.email.enviar", quebra)
    servico.definir_enviador_whatsapp(quebra)
    assert client.post(f"/api/assinar/contrato/{token}", json=corpo()).status_code == 200
    db.expire_all()
    assert db.get(Contrato, contrato_id).status_assinatura == StatusAssinatura.ASSINADO_DIGITALMENTE


def test_permissoes_do_envio(client, secretaria, professor, contrato_id):
    for sufixo in ("link", "enviar-email", "enviar-whatsapp"):
        assert client.post(f"/api/contratos/{contrato_id}/{sufixo}").status_code == 401
        assert client.post(f"/api/contratos/{contrato_id}/{sufixo}", headers=cabecalho(professor)).status_code == 403
    assert client.post(f"/api/contratos/{contrato_id}/link", headers=cabecalho(secretaria)).status_code == 200
