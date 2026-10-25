from datetime import date, time

import pytest
from sqlalchemy import select

from app.modules.agenda.models import AulaSessao
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import ContadorCodigo, HorarioFuncionamento, Profissao, TipoServico, Unidade
from tests.cadastros_base.conftest import auditorias

U = "/api/cadastros/unidades"
S = "/api/cadastros/servicos"
P = "/api/cadastros/profissoes"


# ------------------------------------------------------------------------------------------------ unidades
def test_unidade_crud_completo_com_codigo_e_auditoria(client, db, h_full):
    r = client.post(U, headers=h_full, json={"nome": "  Matriz  ", "capacidade": 6, "duracao_aula_minutos": 50})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["nome"] == "Matriz" and u["capacidade"] == 6 and u["ativo"] is True
    assert u["codigo"] == 1  # proximo_codigo, não max+1
    assert client.get(f"{U}/{u['id']}", headers=h_full).json()["nome"] == "Matriz"

    r = client.put(f"{U}/{u['id']}", headers=h_full, json={"nome": "Matriz Centro", "capacidade": 8, "duracao_aula_minutos": 55, "ativo": True})
    assert r.status_code == 200 and r.json()["capacidade"] == 8 and r.json()["codigo"] == 1

    r2 = client.post(U, headers=h_full, json={"nome": "Filial"})
    assert r2.json()["codigo"] == 2

    assert client.delete(f"{U}/{u['id']}", headers=h_full).status_code == 200
    assert client.get(f"{U}/{u['id']}", headers=h_full).status_code == 404
    for acao in ("unidade.criar", "unidade.alterar", "unidade.excluir"):
        assert auditorias(db, acao), acao
    alterar = auditorias(db, "unidade.alterar")[0]
    assert alterar.antes_json["capacidade"] == 6 and alterar.depois_json["capacidade"] == 8


def test_unidade_codigo_continua_depois_do_etl(client, db, h_full):
    db.add(ContadorCodigo(nome="unidade", ultimo=7))  # o ETL deixa o contador no maior código migrado
    db.commit()
    assert client.post(U, headers=h_full, json={"nome": "Nova"}).json()["codigo"] == 8


@pytest.mark.parametrize("corpo", [
    {"nome": "A"},
    {"nome": "Ok", "capacidade": -1},
    {"nome": "Ok", "capacidade": 501},
    {"nome": "Ok", "duracao_aula_minutos": 5},
    {"nome": "Ok", "duracao_aula_minutos": 500},
    {"capacidade": 3},
])
def test_unidade_validacoes(client, h_full, corpo):
    r = client.post(U, headers=h_full, json=corpo)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_unidade_nome_duplicado_ignora_caixa(client, h_full):
    client.post(U, headers=h_full, json={"nome": "Matriz"})
    r = client.post(U, headers=h_full, json={"nome": "matriz"})
    assert r.status_code == 409 and "já existe" in r.json()["detail"].lower()
    outro = client.post(U, headers=h_full, json={"nome": "Filial"}).json()
    r = client.put(f"{U}/{outro['id']}", headers=h_full, json={"nome": "MATRIZ"})
    assert r.status_code == 409


def test_unidade_lista_busca_ordem_paginacao_e_contagens(client, h_full):
    for n, cap in [("Zeta", 3), ("Alfa", 9), ("Beta", 5)]:
        client.post(U, headers=h_full, json={"nome": n, "capacidade": cap})
    inativa = client.post(U, headers=h_full, json={"nome": "Gama", "ativo": False}).json()
    r = client.get(U, headers=h_full).json()
    assert r["total"] == 4 and [i["nome"] for i in r["itens"]] == ["Alfa", "Beta", "Gama", "Zeta"]
    assert r["contagens"] == {"ativos": 3, "inativos": 1, "todos": 4}
    assert [i["nome"] for i in client.get(U, headers=h_full, params={"ordenar": "capacidade", "direcao": "desc"}).json()["itens"]][0] == "Alfa"
    pag = client.get(U, headers=h_full, params={"por_pagina": 2, "pagina": 2}).json()
    assert pag["total"] == 4 and len(pag["itens"]) == 2 and pag["pagina"] == 2
    ativos = client.get(U, headers=h_full, params={"situacao": "ativos"}).json()
    assert ativos["total"] == 3 and all(i["ativo"] for i in ativos["itens"])
    inativos = client.get(U, headers=h_full, params={"situacao": "inativos"}).json()
    assert [i["id"] for i in inativos["itens"]] == [inativa["id"]]
    busca = client.get(U, headers=h_full, params={"q": "et"}).json()
    assert [i["nome"] for i in busca["itens"]] == ["Beta", "Zeta"]
    assert busca["contagens"]["todos"] == 2  # contagens respeitam a busca
    assert client.get(U, headers=h_full, params={"q": "%"}).json()["total"] == 0  # curinga é escapado
    assert client.get(U, headers=h_full, params={"ordenar": "senha_hash; drop"}).status_code == 200  # ordem desconhecida cai no padrão
    assert client.get(U, headers=h_full, params={"situacao": "xyz"}).status_code == 422


def test_unidade_ativar_desativar(client, db, h_full):
    u = client.post(U, headers=h_full, json={"nome": "Matriz"}).json()
    assert client.post(f"{U}/{u['id']}/desativar", headers=h_full).json()["ativo"] is False
    assert client.post(f"{U}/{u['id']}/ativar", headers=h_full).json()["ativo"] is True
    assert auditorias(db, "unidade.desativar") and auditorias(db, "unidade.ativar")
    assert client.post(f"{U}/9999/ativar", headers=h_full).status_code == 404


def _unidade_com_aula(db) -> tuple[int, int]:
    un = Unidade(nome="Matriz", capacidade=5)
    ts = TipoServico(nome="Pilates")
    db.add_all([un, ts])
    db.flush()
    db.add(AulaSessao(unidade_id=un.id, tipo_servico_id=ts.id, data=date(2026, 1, 5), hora_inicio=time(8), hora_fim=time(9)))
    db.commit()
    return un.id, ts.id


def test_unidade_com_aulas_nao_exclui_e_sugere_desativar(client, db, h_full):
    uid, _ = _unidade_com_aula(db)
    v = client.get(f"{U}/{uid}/vinculos", headers=h_full).json()
    assert v["total"] == 1 and v["itens"][0] == {"rotulo": "aula", "quantidade": 1} and v["pode_excluir"] is False
    r = client.delete(f"{U}/{uid}", headers=h_full)
    assert r.status_code == 409
    assert "1 aula" in r.json()["detail"] and "Desative" in r.json()["detail"]
    assert db.get(Unidade, uid) is not None
    assert not auditorias(db, "unidade.excluir")
    assert client.post(f"{U}/{uid}/desativar", headers=h_full).json()["ativo"] is False


def test_unidade_vinculo_com_horario_de_funcionamento_tambem_bloqueia(client, db, h_full):
    un = Unidade(nome="Matriz")
    db.add(un)
    db.flush()
    db.add(HorarioFuncionamento(unidade_id=un.id, dia_semana=0, hora_inicio=time(7), hora_fim=time(20)))
    db.commit()
    r = client.delete(f"{U}/{un.id}", headers=h_full)
    assert r.status_code == 409 and "horário de funcionamento" in r.json()["detail"]


# ------------------------------------------------------------------------------------------------ serviços
def test_servico_crud_codigo_busca_e_auditoria(client, db, h_full):
    a = client.post(S, headers=h_full, json={"nome": "Pilates"})
    assert a.status_code == 201 and a.json()["codigo"] == 1
    b = client.post(S, headers=h_full, json={"nome": "Fisioterapia", "ativo": False}).json()
    assert b["codigo"] == 2 and b["ativo"] is False
    assert client.post(S, headers=h_full, json={"nome": "pilates"}).status_code == 409
    assert client.post(S, headers=h_full, json={"nome": "x"}).status_code == 422
    lista = client.get(S, headers=h_full, params={"q": "fisio"}).json()
    assert lista["total"] == 1 and lista["contagens"] == {"ativos": 0, "inativos": 1, "todos": 1}
    r = client.put(f"{S}/{a.json()['id']}", headers=h_full, json={"nome": "Pilates Clínico", "ativo": True})
    assert r.json()["nome"] == "Pilates Clínico"
    assert client.post(f"{S}/{b['id']}/ativar", headers=h_full).json()["ativo"] is True
    assert client.delete(f"{S}/{b['id']}", headers=h_full).status_code == 200
    for acao in ("servico.criar", "servico.alterar", "servico.ativar", "servico.excluir"):
        assert auditorias(db, acao), acao


def test_servico_em_uso_nao_exclui(client, db, h_full):
    _, tid = _unidade_com_aula(db)
    r = client.delete(f"{S}/{tid}", headers=h_full)
    assert r.status_code == 409 and "aula" in r.json()["detail"] and "Desative" in r.json()["detail"]
    assert client.get(f"{S}/{tid}/vinculos", headers=h_full).json()["pode_desativar"] is True


# ------------------------------------------------------------------------------------------------ profissões
def test_profissao_crud_duplicado_e_busca(client, db, h_full):
    a = client.post(P, headers=h_full, json={"nome": "Advogada"})
    assert a.status_code == 201 and a.json()["codigo"] == 1
    client.post(P, headers=h_full, json={"nome": "Médico"})
    assert client.post(P, headers=h_full, json={"nome": "ADVOGADA"}).status_code == 409
    assert client.post(P, headers=h_full, json={"nome": " "}).status_code == 422
    assert client.get(P, headers=h_full, params={"q": "méd"}).json()["total"] == 1
    assert client.get(P, headers=h_full).json()["total"] == 2
    r = client.put(f"{P}/{a.json()['id']}", headers=h_full, json={"nome": "Advogado(a)"})
    assert r.json()["nome"] == "Advogado(a)"
    assert client.delete(f"{P}/{a.json()['id']}", headers=h_full).status_code == 200
    assert client.get(f"{P}/{a.json()['id']}", headers=h_full).status_code == 404
    for acao in ("profissao.criar", "profissao.alterar", "profissao.excluir"):
        assert auditorias(db, acao), acao


def test_profissao_usada_por_aluno_nao_exclui(client, db, h_full):
    un = Unidade(nome="Matriz")
    pr = Profissao(nome="Professora")
    db.add_all([un, pr])
    db.flush()
    db.add(Aluno(nome="Aluna Teste", unidade_id=un.id, profissao_id=pr.id, sem_cpf=True))
    db.commit()
    r = client.delete(f"{P}/{pr.id}", headers=h_full)
    assert r.status_code == 409 and "1 aluno" in r.json()["detail"]
    assert "Desative" not in r.json()["detail"]  # profissão não tem situação ativo/inativo
    assert db.scalar(select(Profissao.id).where(Profissao.id == pr.id)) is not None
