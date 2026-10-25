"""Permissões por perfil, nenhuma escrita por GET e auditoria nas rotas de escrita do financeiro."""

import inspect
import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.modules.financeiro import servico
from app.modules.financeiro.models import ContaPagar, ContaReceber, StatusPagar, StatusReceber


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    monkeypatch.setattr(servico, "agora", lambda: datetime(2026, 10, 25, 15, 0, tzinfo=UTC))


@pytest.fixture
def dados(db, cenario):
    cr = ContaReceber(aluno_id=cenario.aluno.id, valor=Decimal("100"), vencimento=date(2026, 10, 10), status=StatusReceber.ABERTO)
    cp = ContaPagar(fornecedor_id=cenario.forn.id, categoria_id=cenario.cat_d.id, subcategoria_id=cenario.sub_d.id,
                    vencimento=date(2026, 10, 10), valor=Decimal("50"), status=StatusPagar.AGENDADO)
    db.add_all([cr, cp])
    db.commit()
    return cr, cp, cenario


def _rotas_financeiro():
    pref = ("/api/financeiro", "/api/receita-saude", "/api/comissoes")
    for r in app.routes:
        for efetiva in ([r] if isinstance(r, APIRoute) else r.effective_route_contexts() if hasattr(r, "effective_route_contexts") else []):
            if efetiva.path.startswith(pref):
                yield efetiva


def test_nenhuma_rota_de_escrita_usa_get():
    """GET só lê: nenhum GET termina num verbo de ação (o antigo baixava e excluía por GET)."""
    acao = re.compile(r"/(baixa|estornar|cancelar|reabrir|excluir|liberar|arquivo|gerar|avulso|transferencias|"
                      r"desfazer-pagamento|cobrar-whatsapp|pagador)$|/\{[^}]+\}/pagar$")
    achadas = [r.path for r in _rotas_financeiro() if "GET" in r.methods and acao.search(r.path)]
    assert not achadas, f"rota de escrita aceitando GET: {achadas}"
    # e as de ação existem como POST/PUT/DELETE
    metodos: dict[str, set] = {}
    for r in _rotas_financeiro():
        metodos.setdefault(r.path, set()).update(r.methods)
    assert metodos["/api/financeiro/receber/{conta_id:int}/baixa"] == {"POST", "DELETE"}
    assert "GET" not in metodos["/api/financeiro/pagar/{conta_id:int}/pagar"]


def test_get_nunca_altera_o_banco(client, adm, db, dados):
    cr, cp, _ = dados
    rotas_get = [f"/api/financeiro/receber/{cr.id}/baixa", f"/api/financeiro/receber/{cr.id}/cancelar",
                 f"/api/financeiro/receber/{cr.id}/reabrir", f"/api/financeiro/receber/{cr.id}/cobrar-whatsapp",
                 f"/api/financeiro/pagar/{cp.id}/pagar", f"/api/financeiro/pagar/{cp.id}/cancelar",
                 f"/api/financeiro/pagar/{cp.id}/reabrir", "/api/financeiro/receber/avulso", "/api/comissoes/gerar",
                 "/api/comissoes/pagar", "/api/receita-saude/lote/arquivo", "/api/receita-saude/lote/liberar"]
    for url in rotas_get:
        assert client.get(url, headers=adm).status_code in (404, 405), url
    # o antigo baixava e excluía por GET: DELETE /{id} é a única forma de excluir; GET só lê
    assert client.get(f"/api/financeiro/receber/{cr.id}", headers=adm).status_code == 200
    db.expire_all()
    assert db.get(ContaReceber, cr.id).status == StatusReceber.ABERTO and db.get(ContaPagar, cp.id).status == StatusPagar.AGENDADO


def test_toda_rota_de_escrita_audita():
    """Todo endpoint que não é GET precisa chamar `ctx.auditar(...)` (as exportações GET auditam por serem sensíveis)."""
    sem = []
    for r in _rotas_financeiro():
        if r.methods - {"GET", "HEAD", "OPTIONS"} and "auditar" not in inspect.getsource(r.endpoint):
            sem.append(f"{sorted(r.methods)} {r.path}")
    assert not sem, f"escrita sem auditoria: {sem}"


# Matriz perfil x endpoint: (método, URL, permissão que o catálogo exige)
def _casos(cr, cp):
    return [
        ("GET", "/api/financeiro/receber", "financeiro_receber.ver"),
        ("GET", f"/api/financeiro/receber/{cr}/recibo", "financeiro_receber.ver"),
        ("POST", f"/api/financeiro/receber/{cr}/baixa", "financeiro_receber.baixar"),
        ("DELETE", f"/api/financeiro/receber/{cr}/baixa", "financeiro_receber.baixar"),
        ("POST", "/api/financeiro/receber/avulso", "financeiro_receber.editar"),
        ("PUT", f"/api/financeiro/receber/{cr}", "financeiro_receber.editar"),
        ("POST", f"/api/financeiro/receber/{cr}/cancelar", "financeiro_receber.editar"),
        ("DELETE", f"/api/financeiro/receber/{cr}", "financeiro_receber.excluir"),
        ("POST", f"/api/financeiro/receber/{cr}/cobrar-whatsapp", "whatsapp.enviar"),
        ("GET", "/api/financeiro/pagar", "financeiro_pagar.ver"),
        ("POST", "/api/financeiro/pagar", "financeiro_pagar.editar"),
        ("POST", f"/api/financeiro/pagar/{cp}/pagar", "financeiro_pagar.pagar"),
        ("POST", f"/api/financeiro/pagar/{cp}/reabrir", "financeiro_pagar.pagar"),
        ("POST", f"/api/financeiro/pagar/{cp}/cancelar", "financeiro_pagar.editar"),
        ("DELETE", f"/api/financeiro/pagar/{cp}", "financeiro_pagar.excluir"),
        ("GET", "/api/financeiro/caixa", "financeiro_caixa.ver"),
        ("GET", "/api/financeiro/dre", "financeiro_dre.ver"),
        ("GET", "/api/financeiro/bancos/contas", "financeiro_bancos.ver"),
        ("POST", "/api/financeiro/bancos/contas", "financeiro_bancos.editar"),
        ("POST", "/api/financeiro/bancos/transferencias", "financeiro_bancos.editar"),
        ("DELETE", "/api/financeiro/bancos/movimentos/1", "financeiro_bancos.excluir"),
        ("GET", "/api/receita-saude/config", "receita_saude.ver"),
        ("PUT", "/api/receita-saude/config", "receita_saude.gerar"),
        ("GET", "/api/receita-saude/lote?de=2026-10-01&ate=2026-10-31", "receita_saude.ver"),
        ("POST", "/api/receita-saude/lote/arquivo", "receita_saude.gerar"),
        ("GET", "/api/comissoes", "comissoes.ver"),
        ("POST", "/api/comissoes/gerar", "comissoes.editar"),
        ("DELETE", "/api/comissoes/1", "comissoes.editar"),
    ]


def test_regras_de_permissao_batem_com_o_catalogo():
    from app.core.permissoes import permissao_da_rota

    erradas = []
    for metodo, url, esperada in _casos(1, 1):
        mapeada, perm = permissao_da_rota(metodo, url.split("?")[0])
        if not mapeada or perm != esperada:
            erradas.append((metodo, url, perm, esperada))
    assert not erradas, erradas


def test_professor_nao_acessa_nada_do_financeiro(client, professor, dados):
    cr, cp, _ = dados
    for metodo, url, _perm in _casos(cr.id, cp.id):
        r = client.request(metodo, url, headers=professor, json={})
        assert r.status_code == 403, (metodo, url, r.status_code)


def test_secretaria_so_ve_e_baixa_contas_a_receber(client, secretaria, dados):
    cr, cp, cen = dados
    permitidas = {"financeiro_receber.ver", "financeiro_receber.baixar", "whatsapp.enviar"}  # perfil Secretária
    for metodo, url, perm in _casos(cr.id, cp.id):
        r = client.request(metodo, url, headers=secretaria, json={})
        if perm in permitidas:
            assert r.status_code != 403, (metodo, url, "deveria ser liberado", r.status_code)
        else:
            assert r.status_code == 403, (metodo, url, "deveria ser negado", r.status_code)
    # na prática: lista e baixa funcionam
    assert client.get("/api/financeiro/receber", headers=secretaria).status_code == 200
    r = client.post(f"/api/financeiro/receber/{cr.id}/baixa", json={"forma_pagamento": "PIX"}, headers=secretaria)
    assert r.status_code == 200 and r.json()["situacao"] == "PAGO"
    assert client.get(f"/api/financeiro/receber/{cr.id}/recibo", headers=secretaria).status_code == 200


def test_sem_login_e_401(client, dados):
    cr, cp, _ = dados
    for metodo, url, _ in _casos(cr.id, cp.id):
        assert client.request(metodo, url).status_code == 401, (metodo, url)


def test_administrador_acessa_tudo(client, adm, dados):
    cr, cp, _ = dados
    for metodo, url, _perm in _casos(cr.id, cp.id):
        if metodo == "GET" and "/recibo" not in url:  # recibo só existe para conta paga (409 aqui)
            assert client.get(url, headers=adm).status_code == 200, url


def test_comprovante_so_para_quem_pode_ver_contas_a_pagar(client, adm, secretaria, db, dados):
    cr, cp, _ = dados
    PDF = b"%PDF-1.4\n%%EOF"
    client.post(f"/api/financeiro/pagar/{cp.id}/comprovante", headers=adm, files={"comprovante": ("c.pdf", PDF, "application/pdf")})
    db.expire_all()
    caminho = db.get(ContaPagar, cp.id).comprovante_path
    assert client.get(f"/api/arquivos/{caminho}", headers=adm).status_code == 200
    assert client.get(f"/api/arquivos/{caminho}", headers=secretaria).status_code == 403
    assert client.get(f"/api/financeiro/pagar/{cp.id}/comprovante", headers=secretaria).status_code == 403
    assert client.get(f"/api/arquivos/{caminho}").status_code == 401
