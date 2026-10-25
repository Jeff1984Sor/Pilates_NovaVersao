"""Criar contrato: R1 (valores) e R2 (parcelas) integrados, PDF guardado, atomicidade, validações e permissões."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core import storage
from app.core.models import Auditoria
from app.domain import parcelas as dom_parcelas
from app.domain import precos
from app.modules.alunos.models import AlunoDocumento, OrigemDocumento, StatusAluno
from app.modules.contratos import schemas as sc
from app.modules.contratos import servico
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber
from tests.contratos.conftest import cabecalho


def contar(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


def test_precificar_mostra_r1_e_r2_sem_gravar(client, full, cen, db):
    r = client.post("/api/contratos/precificar", json={"plano_id": cen.plano.id, "data_inicio": "2026-11-02"}, headers=cabecalho(full))
    assert r.status_code == 200, r.text
    j = r.json()
    # caso de caracterização R1: 300,00 · 2x/sem · 3 meses -> aula 37,50; parcela 300,00; total 900,00
    assert (Decimal(j["valor_aula"]), Decimal(j["valor_parcela"]), Decimal(j["valor_total"])) == (Decimal("37.50"), Decimal("300.00"), Decimal("900.00"))
    assert [p["vencimento"] for p in j["parcelas"]] == ["2026-11-02", "2026-12-02", "2027-01-02"]
    assert j["parcelas"][0]["competencia"] == "2026-11"
    assert j["data_fim_sugerida"] == "2027-02-01"
    assert contar(db, Contrato) == 0


def test_criar_confere_com_o_dominio_e_gera_parcelas_e_pdf(client, full, cen, db, novo_contrato):
    j = novo_contrato()
    c = j["contrato"]
    esperado = precos.precificar_contrato(cen.plano.valor, cen.plano.aulas_por_semana, cen.plano.duracao_meses)
    assert Decimal(c["valor_aula"]) == esperado.valor_aula == Decimal("37.50")
    assert Decimal(c["valor_parcela"]) == esperado.valor_parcela
    assert Decimal(c["valor_total"]) == esperado.valor_total
    assert c["data_fim"] == "2027-02-01" and c["status_assinatura"] == "NAO_ASSINADO"
    assert j["parcelas_criadas"] == 3 and j["proximo_passo"] == "agenda" and c["precisa_agenda"] is True
    contas = db.scalars(select(ContaReceber).where(ContaReceber.contrato_id == c["id"]).order_by(ContaReceber.vencimento)).all()
    previstas = dom_parcelas.gerar_parcelas(Decimal("300.00"), date(2026, 11, 2), date(2027, 2, 1), 3, "MENSAL")
    assert [(x.vencimento, x.valor, x.competencia) for x in contas] == [(p.vencimento, p.valor, p.competencia) for p in previstas]
    doc = db.scalar(select(AlunoDocumento).where(AlunoDocumento.contrato_id == c["id"]))
    assert doc.origem == OrigemDocumento.CONTRATO_PDF and doc.aluno_id == cen.aluno.id
    pdf = storage.ler(doc.arquivo_path)
    assert pdf.startswith(b"%PDF") and j["pdf_documento_id"] == doc.id and doc.sha256
    contrato = db.get(Contrato, c["id"])
    assert contrato.codigo_legado == c["numero"] and contrato.recorrencia.value == "MENSAL"
    a = db.scalar(select(Auditoria).where(Auditoria.acao == "contrato.criar"))
    assert a and a.entidade_id == str(c["id"])


def test_vencimento_com_dia_31_usa_dia_28_r2(client, full, cen, novo_contrato):
    j = novo_contrato(data_inicio="2026-01-31")
    venc = [p["vencimento"] for p in j["contrato"]["parcelas"]]
    assert venc == ["2026-01-28", "2026-02-28", "2026-03-28"]


def test_plano_avulso_nao_pede_agenda(client, full, cen, novo_contrato):
    j = novo_contrato(plano_id=cen.avulso.id)
    assert j["proximo_passo"] == "nenhum" and j["contrato"]["precisa_agenda"] is False


def test_data_fim_informada_vale(client, full, cen, novo_contrato):
    j = novo_contrato(data_fim="2027-03-31")
    assert j["contrato"]["data_fim"] == "2027-03-31"
    r = client.post("/api/contratos", json={"aluno_id": cen.aluno.id, "plano_id": cen.plano.id, "unidade_id": cen.un.id,
                                            "profissional_id": cen.p1.id, "data_inicio": "2026-11-02", "data_fim": "2026-10-01"},
                    headers=cabecalho(full))
    assert r.status_code == 422


def test_avisa_sobreposicao_mas_nao_bloqueia(client, full, cen, novo_contrato):
    novo_contrato()
    j = novo_contrato()
    assert any("já tem o contrato" in a for a in j["contrato"]["avisos"])


def test_aluno_inativo_e_plano_inativo_sao_recusados(client, full, cen, db):
    corpo = {"aluno_id": cen.aluno.id, "plano_id": cen.plano.id, "unidade_id": cen.un.id, "profissional_id": cen.p1.id, "data_inicio": "2026-11-02"}
    cen.aluno.status = StatusAluno.INATIVO
    db.commit()
    assert client.post("/api/contratos", json=corpo, headers=cabecalho(full)).status_code == 409
    cen.aluno.status = StatusAluno.ATIVO
    cen.plano.ativo = False
    db.commit()
    assert client.post("/api/contratos", json=corpo, headers=cabecalho(full)).status_code == 422
    assert contar(db, Contrato) == 0


# ------------------------------------------------------------------------------------------------ atomicidade
def _ctx(db, admin):
    from app.core.deps import Contexto

    return Contexto(db=db, usuario=admin, ip="127.0.0.1")


def _dados(cen):
    return sc.ContratoIn(aluno_id=cen.aluno.id, plano_id=cen.plano.id, unidade_id=cen.un.id, profissional_id=cen.p1.id,
                         data_inicio=date(2026, 11, 2))


def _nada_ficou(db):
    assert contar(db, Contrato) == 0 and contar(db, ContaReceber) == 0
    assert contar(db, AlunoDocumento) == 0


def test_falha_nas_parcelas_desfaz_tudo(db, admin, cen, monkeypatch):
    def quebra(*_a, **_k):
        raise RuntimeError("falha simulada nas parcelas")

    monkeypatch.setattr(servico.fin, "gerar_contas_do_contrato", quebra)
    with pytest.raises(RuntimeError):
        servico.criar_contrato(_ctx(db, admin), _dados(cen))
    _nada_ficou(db)


def test_falha_no_pdf_desfaz_contrato_e_parcelas(db, admin, cen, monkeypatch):
    def quebra(*_a, **_k):
        raise RuntimeError("falha simulada no PDF")

    monkeypatch.setattr(servico, "gerar_pdf_do_contrato", quebra)
    with pytest.raises(RuntimeError):
        servico.criar_contrato(_ctx(db, admin), _dados(cen))
    _nada_ficou(db)


def test_falha_depois_de_gravar_o_arquivo_apaga_o_arquivo(db, admin, cen, monkeypatch):
    original = servico.gravar_pdf_como_documento
    gravados = []

    def grava_e_quebra(db_, c, pdf):
        _doc, rel = original(db_, c, pdf)
        gravados.append(rel)
        raise RuntimeError("falha simulada depois do arquivo")

    monkeypatch.setattr(servico, "gravar_pdf_como_documento", grava_e_quebra)
    with pytest.raises(RuntimeError):
        servico.criar_contrato(_ctx(db, admin), _dados(cen))
    _nada_ficou(db)
    assert gravados and not storage.existe(gravados[0])


def test_falha_na_auditoria_tambem_desfaz(db, admin, cen, monkeypatch):
    ctx = _ctx(db, admin)

    def quebra(*_a, **_k):
        raise RuntimeError("auditoria fora do ar")

    monkeypatch.setattr(type(ctx), "auditar", quebra)
    with pytest.raises(RuntimeError):
        servico.criar_contrato(ctx, _dados(cen))
    _nada_ficou(db)


# ---------------------------------------------------------------------------------------------- permissões
def test_professor_nao_acessa_contratos(client, professor, cen):
    h = cabecalho(professor)
    assert client.get("/api/contratos", headers=h).status_code == 403
    assert client.get("/api/contratos/opcoes", headers=h).status_code == 403
    assert client.post("/api/contratos/precificar", json={"plano_id": cen.plano.id, "data_inicio": "2026-11-02"}, headers=h).status_code == 403
    assert client.post("/api/contratos", json={}, headers=h).status_code == 403


def test_sem_login_nao_acessa(client, cen):
    assert client.get("/api/contratos").status_code == 401
    assert client.post("/api/contratos", json={}).status_code == 401


def test_secretaria_cria_e_lista_mas_nao_exclui(client, secretaria, cen, db):
    h = cabecalho(secretaria)
    corpo = {"aluno_id": cen.aluno.id, "plano_id": cen.plano.id, "unidade_id": cen.un.id, "profissional_id": cen.p1.id, "data_inicio": "2026-11-02"}
    r = client.post("/api/contratos", json=corpo, headers=h)
    assert r.status_code == 201
    cid = r.json()["contrato"]["id"]
    assert client.get("/api/contratos", headers=h).status_code == 200
    assert client.get(f"/api/contratos/{cid}/exclusao", headers=h).status_code == 200
    assert client.delete(f"/api/contratos/{cid}?confirmar=true", headers=h).status_code == 403
    assert client.post("/api/contratos/recalcular", json={"simular": False}, headers=h).status_code == 403
    assert client.post("/api/contratos/recalcular", json={"simular": True}, headers=h).status_code == 200
