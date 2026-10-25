"""Data de negócio (Brasília) e conteúdo do painel por perfil. Decisão: Professor recebe 200 com SÓ as próprias aulas
(não 403), porque o frontend o redireciona para a agenda e a API continua segura mesmo se ele abrir a rota."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from tests.painel.conftest import auth, criar_perfil_restrito, criar_usuario, entrar, fixar_agora, novo_professor_logado

URL = "/api/painel/resumo"


# ----------------------------------------------------------------------------------------------------- data de negócio
def test_as_23h_em_brasilia_ainda_e_o_mesmo_dia(client, mundo, full, monkeypatch):
    # 26/10 02:30 UTC = 25/10 23:30 em Brasília (UTC-3): em UTC já seria "amanhã"
    fixar_agora(monkeypatch, datetime(2026, 10, 26, 2, 30, tzinfo=UTC))
    r = client.get(URL, headers=full).json()
    assert r["hoje"] == "2026-10-25"
    assert (r["kpis"]["aulas"]["hoje"], r["kpis"]["aulas"]["amanha"]) == (4, 1)
    assert r["proximas_aulas"]["itens"] == []  # todas as aulas de hoje já acabaram
    assert Decimal(r["kpis"]["atrasado"]["valor"]) == Decimal("230.00")  # a conta que vence hoje NÃO está atrasada
    assert r["aniversariantes"]["itens"][0]["nome"] == "Ana" and r["aniversariantes"]["itens"][0]["hoje"] is True


def test_apos_a_meia_noite_de_brasilia_vira_o_dia(client, mundo, full, monkeypatch):
    fixar_agora(monkeypatch, datetime(2026, 10, 26, 3, 30, tzinfo=UTC))  # 00:30 de 26/10 em Brasília
    r = client.get(URL, headers=full).json()
    assert r["hoje"] == "2026-10-26"
    assert r["kpis"]["aulas"]["hoje"] == 1                          # a aula de amanhã virou "hoje"
    assert Decimal(r["kpis"]["atrasado"]["valor"]) == Decimal("300.00")  # 200 + 30 + 70 (venceu ontem)
    assert [a["nome"] for a in r["aniversariantes"]["itens"]][0] == "Dani"


def test_virada_de_mes_no_horario_de_brasilia(client, mundo, full, monkeypatch):
    # 01/11 02:00 UTC ainda é 31/10 23:00 em Brasília: o mês corrente continua outubro
    fixar_agora(monkeypatch, datetime(2026, 11, 1, 2, 0, tzinfo=UTC))
    r = client.get(URL, headers=full).json()
    assert r["hoje"] == "2026-10-31"
    assert r["recebido_mes"]["mes"] == "2026-10"


# ----------------------------------------------------------------------------------------------------------- perfis
def test_full_ve_tudo(client, mundo, full):
    r = client.get(URL, headers=full).json()
    assert r["restrito"] is False
    blocos = [r["kpis"][k]["visivel"] for k in r["kpis"]]
    assert all(blocos)
    for b in ("recebido_mes", "aulas_por_mes", "ranking_professores", "proximas_aulas", "aniversariantes", "alertas", "primeiros_passos"):
        assert r[b]["visivel"] is True, b


def test_secretaria_ve_o_que_o_perfil_permite(client, mundo, secretaria):
    r = client.get(URL, headers=secretaria).json()
    assert r["restrito"] is False
    assert r["kpis"]["alunos_ativos"]["visivel"] and r["kpis"]["aulas"]["visivel"] and r["kpis"]["contratos_vencendo"]["visivel"]
    assert r["kpis"]["atrasado"]["visivel"] and r["recebido_mes"]["visivel"]  # tem financeiro_receber.ver
    chaves = {a["chave"] for a in r["alertas"]["itens"]}
    assert {"contas_atrasadas", "aulas_sem_evolucao", "contratos_nao_assinados"} <= chaves
    # sem reposicoes.ver, sem whatsapp.configurar e sem integracoes.ver: esses alertas nem são calculados
    assert not chaves & {"reposicoes_pendentes", "whatsapp_sessao", "whatsapp_automatico_desligado", "totalpass_erro"}
    assert r["primeiros_passos"]["visivel"] is False  # só quem cadastra (Full) vê o passo a passo


def test_secretaria_sem_financeiro_nao_recebe_valores(client, db, mundo):
    p = criar_perfil_restrito(db, ["painel.ver", "aulas.ver", "alunos.ver"])
    p.somente_proprias_aulas = False
    criar_usuario(db, "Secretária", email="s2@x.com")
    from sqlalchemy import select

    from app.core.models import Usuario

    u = db.scalar(select(Usuario).where(Usuario.email == "s2@x.com"))
    u.perfil_acesso_id = p.id
    db.commit()
    h = auth(entrar(client, "s2@x.com").json()["access_token"])
    r = client.get(URL, headers=h).json()
    assert r["kpis"]["a_receber"] == {"visivel": False, "valor": None, "quantidade": None, "href": None}
    assert r["kpis"]["atrasado"]["visivel"] is False and r["recebido_mes"]["visivel"] is False
    assert r["kpis"]["contratos_vencendo"]["visivel"] is False
    assert "contas_atrasadas" not in {a["chave"] for a in r["alertas"]["itens"]}


def test_sem_permissao_painel_403(client, db):
    p = criar_perfil_restrito(db, ["alunos.ver"])
    criar_usuario(db, "Secretária", email="sp@x.com")
    from sqlalchemy import select

    from app.core.models import Usuario

    u = db.scalar(select(Usuario).where(Usuario.email == "sp@x.com"))
    u.perfil_acesso_id = p.id
    db.commit()
    h = auth(entrar(client, "sp@x.com").json()["access_token"])
    assert client.get(URL, headers=h).status_code == 403


def test_professor_so_as_proprias_aulas_e_nenhum_dado_sensivel(client, db, mundo):
    h, prof = novo_professor_logado(client, db, "Marina")
    # vincula o professor logado ao profissional "Natalia" do cenário: troca o vínculo
    from app.modules.cadastros.models import Profissional

    marina = db.get(Profissional, prof.id)
    marina.usuario_id = None
    db.flush()
    natalia = db.get(Profissional, mundo.p1.id)
    from sqlalchemy import select

    from app.core.models import Usuario

    natalia.usuario_id = db.scalar(select(Usuario.id).where(Usuario.email == "prof@x.com"))
    db.commit()
    r = client.get(URL, headers=h).json()
    assert r["restrito"] is True
    # só as aulas da Natalia: hoje 08:00 (1) + 14:00 (2) = 3; amanhã 1
    assert (r["kpis"]["aulas"]["hoje"], r["kpis"]["aulas"]["amanha"]) == (3, 1)
    assert [m["total"] for m in r["aulas_por_mes"]["meses"]] == [0, 0, 0, 0, 0, 4]
    assert [(i["nome"], i["total"]) for i in r["ranking_professores"]["itens"]] == [("Natalia", 4)]
    # a lista de próximas aulas traz só as dela e NÃO traz o nome do aluno
    itens = r["proximas_aulas"]["itens"]
    assert [(i["hora"], i["professor"]) for i in itens] == [("14:00", "Natalia"), ("14:00", "Natalia")]
    assert all(i["aluno"] is None for i in itens)
    # nada financeiro, de contratos, de alunos ou de reposição
    for k in ("alunos_ativos", "contratos_vencendo", "a_receber", "atrasado"):
        assert r["kpis"][k]["visivel"] is False
    assert r["recebido_mes"]["visivel"] is False and r["aniversariantes"]["visivel"] is False
    assert r["primeiros_passos"]["visivel"] is False
    chaves = {a["chave"] for a in r["alertas"]["itens"]}
    assert not chaves & {"contas_atrasadas", "contratos_nao_assinados", "reposicoes_pendentes", "whatsapp_sessao", "totalpass_erro"}
    texto = json.dumps(r)
    for nome in ("Ana", "Bia", "Caio", "Dani", "Carla"):  # nenhum aluno nem a outra professora
        assert nome not in texto


def test_professor_nao_ve_aulas_da_outra_professora_nem_sem_vinculo(client, db, mundo):
    h, prof = novo_professor_logado(client, db, "Sem aulas")  # vinculada a ninguém do cenário
    r = client.get(URL, headers=h).json()
    assert r["kpis"]["aulas"]["hoje"] == 0 and r["proximas_aulas"]["itens"] == []
    assert r["ranking_professores"]["itens"] == []
    assert _sem_evolucao(r) == 0


def _sem_evolucao(r):
    return next((a["quantidade"] for a in r["alertas"]["itens"] if a["chave"] == "aulas_sem_evolucao"), 0)


def test_professor_com_perfil_ampliado_continua_sem_financeiro(client, db, mundo):
    """Mesmo que o perfil restrito receba permissões de financeiro/alunos/contratos, o painel não as entrega."""
    p = criar_perfil_restrito(db, ["painel.ver", "aulas.ver", "alunos.ver", "contratos.ver", "financeiro_receber.ver",
                                   "reposicoes.ver", "whatsapp.configurar", "integracoes.ver", "cadastros_unidades.editar"])
    criar_usuario(db, "Professor", email="amp@x.com")
    from sqlalchemy import select

    from app.core.models import Usuario

    u = db.scalar(select(Usuario).where(Usuario.email == "amp@x.com"))
    u.perfil_acesso_id = p.id
    db.commit()
    r = client.get(URL, headers=auth(entrar(client, "amp@x.com").json()["access_token"])).json()
    assert r["restrito"] is True
    assert not any(r["kpis"][k]["visivel"] for k in ("alunos_ativos", "contratos_vencendo", "a_receber", "atrasado"))
    assert r["recebido_mes"]["visivel"] is False and r["aniversariantes"]["visivel"] is False
    assert r["primeiros_passos"]["visivel"] is False
    assert {a["chave"] for a in r["alertas"]["itens"]} <= {"aulas_sem_evolucao"}
