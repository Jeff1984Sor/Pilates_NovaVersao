"""Opções dos formulários (planos, fornecedores, categorias, contas bancárias) sem depender de rotas de outros módulos."""

from app.modules.financeiro.models import ContaBancaria


def test_opcoes_de_receber_e_pagar(client, adm, secretaria, professor, db, cenario):
    db.add_all([ContaBancaria(banco="Banco A", agencia="1", conta="2"), ContaBancaria(banco="Inativo", agencia="9", conta="9", ativo=False)])
    db.commit()
    r = client.get("/api/financeiro/receber/opcoes", headers=adm).json()
    assert [p["nome"] for p in r["planos"]] == ["Plano 2x"]
    assert [c["nome"] for c in r["contas_bancarias"]] == ["Banco A ag. 1 c/c 2"]  # só as ativas, sem saldo
    p = client.get("/api/financeiro/pagar/opcoes", headers=adm).json()
    assert [f["nome"] for f in p["fornecedores"]] == ["Imobiliária Centro"]
    desp = next(c for c in p["categorias"] if c["tipo"] == "DESPESA")
    assert desp["nome"] == "Aluguel e contas" and [s["nome"] for s in desp["subcategorias"]] == ["Aluguel"]
    # Secretária usa as opções de receber (baixa), mas não as de pagar; Professor nenhuma
    assert client.get("/api/financeiro/receber/opcoes", headers=secretaria).status_code == 200
    assert client.get("/api/financeiro/pagar/opcoes", headers=secretaria).status_code == 403
    assert client.get("/api/financeiro/receber/opcoes", headers=professor).status_code == 403
