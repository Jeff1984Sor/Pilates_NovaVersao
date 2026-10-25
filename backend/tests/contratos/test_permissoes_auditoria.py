"""Permissões Full/Secretária/Professor em todas as rotas de contratos, rotas públicas com rate limit e auditoria completa."""

import re

import pytest
from sqlalchemy import select

from app.core.deps import get_contexto
from app.core.models import Auditoria
from app.core.permissoes import permissao_da_rota, rota_autenticacao_propria, rota_publica
from app.modules.contratos import servico
from tests.contratos.conftest import cabecalho, png_data_url
from tests.test_cobertura_rotas import _depende_de, _rotas


def _rotas_contratos():
    for r, metodo, caminho in _rotas():
        if r.path.startswith("/api/contratos"):
            yield r, metodo, caminho


def test_toda_rota_de_contratos_tem_regra_e_exige_login():
    achadas = list(_rotas_contratos())
    assert len(achadas) >= 20
    for r, metodo, caminho in achadas:
        assert not rota_publica(metodo, caminho), r.path
        mapeada, permissao = permissao_da_rota(metodo, caminho)
        assert mapeada and permissao, f"{metodo} {r.path}"
        assert _depende_de(r.dependant, get_contexto), r.path
        assert permissao.split(".")[0] in ("contratos", "alunos"), (r.path, permissao)


def test_rotas_publicas_de_assinatura_tem_rate_limit_e_validam_token():
    publicas = [(r, m) for r, m, c in _rotas() if r.path.startswith("/api/assinar/")]
    assert len(publicas) == 5
    for r, _m in publicas:
        assert rota_autenticacao_propria(re.sub(r"\{[^}]+\}", "1", r.path)), r.path
        assert not _depende_de(r.dependant, get_contexto), r.path  # não usam o login do estúdio
        nomes = [getattr(d.call, "__qualname__", "") for d in r.dependant.dependencies]
        assert any("limitar" in n for n in nomes), f"sem rate limit: {r.path}"
        assert "{token}" in r.path


ENDPOINTS = [
    # (método, caminho, corpo, permissão esperada para Secretária (200/2xx), Professor sempre 403)
    ("GET", "/api/contratos", None),
    ("GET", "/api/contratos/opcoes", None),
    ("POST", "/api/contratos/precificar", {"plano_id": "{plano}", "data_inicio": "2026-11-02"}),
    ("GET", "/api/contratos/{c}", None),
    ("GET", "/api/contratos/{c}/exclusao", None),
    ("GET", "/api/contratos/{c}/pdf", None),
    ("GET", "/api/contratos/{c}/agenda/opcoes", None),
]


@pytest.mark.parametrize(("metodo", "caminho", "corpo"), ENDPOINTS)
def test_matriz_de_leitura(client, full, secretaria, professor, cen, novo_contrato, metodo, caminho, corpo):
    cid = novo_contrato()["contrato"]["id"]
    url = caminho.replace("{c}", str(cid))
    json = {k: (cen.plano.id if v == "{plano}" else v) for k, v in corpo.items()} if corpo else None
    sem = client.request(metodo, url, json=json)
    assert sem.status_code == 401
    assert client.request(metodo, url, json=json, headers=cabecalho(professor)).status_code == 403
    assert client.request(metodo, url, json=json, headers=cabecalho(secretaria)).status_code < 300
    assert client.request(metodo, url, json=json, headers=cabecalho(full)).status_code < 300


def test_matriz_de_escrita(client, full, secretaria, professor, cen, novo_contrato):
    cid = novo_contrato()["contrato"]["id"]
    sec, prof = cabecalho(secretaria), cabecalho(professor)
    tentativas = [
        ("PUT", f"/api/contratos/{cid}", {"forma_pagamento": "DINHEIRO"}),
        ("POST", f"/api/contratos/{cid}/renovar", {}),
        ("POST", f"/api/contratos/{cid}/encerrar", {}),
        ("POST", f"/api/contratos/{cid}/agenda", {"selecoes": [{"dia_semana": 0, "inicio": "09:00", "fim": "09:50", "profissional_id": 1}]}),
        ("POST", f"/api/contratos/{cid}/assinatura-local", {"nome": "Maria Souza", "documento": "52998224725", "assinatura": png_data_url()}),
        ("POST", f"/api/contratos/{cid}/link", None),
        ("POST", "/api/contratos/recalcular", {}),
        ("POST", f"/api/contratos/termo/{cen.aluno.id}/link", None),
        ("DELETE", f"/api/contratos/{cid}?confirmar=true", None),
    ]
    for metodo, url, corpo in tentativas:
        assert client.request(metodo, url, json=corpo).status_code == 401, (metodo, url)
        assert client.request(metodo, url, json=corpo, headers=prof).status_code == 403, (metodo, url)
    # Secretária: tudo menos excluir
    for metodo, url, corpo in tentativas[:-1]:
        assert client.request(metodo, url, json=corpo, headers=sec).status_code != 403, (metodo, url)
    assert client.request("DELETE", tentativas[-1][1], headers=sec).status_code == 403


def test_acoes_sensiveis_deixam_rastro_na_auditoria(client, full, db, cen, novo_contrato):
    h = cabecalho(full)
    cid = novo_contrato(data_inicio="2026-11-02", data_fim="2026-11-29")["contrato"]["id"]
    client.put(f"/api/contratos/{cid}", json={"forma_pagamento": "DINHEIRO"}, headers=h)
    client.post(f"/api/contratos/{cid}/agenda", headers=h, json={"selecoes": [
        {"dia_semana": 0, "inicio": "09:00", "fim": "09:50", "profissional_id": cen.p1.id},
        {"dia_semana": 2, "inicio": "09:00", "fim": "09:50", "profissional_id": cen.p1.id}]})
    client.post(f"/api/contratos/{cid}/link", headers=h)
    client.post(f"/api/contratos/{cid}/enviar-email", headers=h)
    servico.definir_enviador_whatsapp(lambda *_: None)
    client.post(f"/api/contratos/{cid}/enviar-whatsapp", headers=h)
    client.post(f"/api/contratos/{cid}/renovar", json={}, headers=h)
    client.post("/api/contratos/recalcular", json={"simular": False}, headers=h)
    client.post(f"/api/contratos/termo/{cen.aluno.id}/link", headers=h)
    client.post(f"/api/contratos/{cid}/assinatura-local", headers=h, json={"nome": "Maria Souza", "documento": "52998224725", "assinatura": png_data_url()})
    client.post(f"/api/contratos/{cid}/encerrar", json={"cancelar_parcelas_futuras": False}, headers=h)
    novo = novo_contrato(data_inicio="2026-12-01")["contrato"]["id"]
    assert client.delete(f"/api/contratos/{novo}?confirmar=true", headers=h).status_code == 200
    acoes = {a.acao for a in db.scalars(select(Auditoria))}
    esperadas = {"contrato.criar", "contrato.editar", "contrato.agenda", "contrato.link", "contrato.enviar_email",
                 "contrato.enviar_whatsapp", "contrato.renovar", "aluno.termo.link", "contrato.assinar_local",
                 "contrato.encerrar", "contrato.excluir"}
    assert esperadas <= acoes, esperadas - acoes
    linha = db.scalar(select(Auditoria).where(Auditoria.acao == "contrato.criar"))
    assert linha.usuario_id and linha.ip and linha.entidade == "contrato"
    # nenhum segredo (token/link completo/imagem) vai para a auditoria
    for a in db.scalars(select(Auditoria)):
        texto = f"{a.descricao} {a.antes_json} {a.depois_json}"
        assert "data:image" not in texto and "/assinar/contrato/" not in texto
