from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.agenda.models import Reserva
from app.modules.alunos.models import Aluno, AlunoEndereco, AlunoTelefone, StatusAluno
from tests.alunos.conftest import CPF_A, CPF_B, corpo


def acoes(db):
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id))]


def test_criar_e_ler_aluno_completo(client, h, base, db):
    r = client.post("/api/alunos", headers=h, json=corpo(
        base, rg="12.345.678-9", email="maria@exemplo.com", data_nascimento="1990-05-17", estado_civil="CASADO",
        profissao_id=base["profissao_id"], cpf_pagador_recibo=CPF_B, autoriza_imagem=True,
        telefones=[{"numero": "(11) 98888-7777", "principal": True}, {"numero": "1133334444"}],
        endereco={"cep": "01310-100", "logradouro": "Av. Paulista", "numero": "1000", "bairro": "Bela Vista", "cidade": "São Paulo"},
    ))
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["cpf"] == "529.982.247-25" and a["cpf_mascarado"] == "***.***.247-25"
    assert a["cpf_pagador_recibo"] == "111.444.777-35"
    assert a["codigo"] == 1 and a["status"] == "ATIVO"
    assert [t["numero"] for t in a["telefones"]] == ["5511988887777", "551133334444"]
    assert a["telefones"][0]["principal"] and a["telefones"][0]["formatado"] == "(11) 98888-7777"
    assert a["endereco"]["cep"] == "01310100" and a["endereco"]["cidade"] == "São Paulo"
    assert a["profissao_nome"] == "Engenheira" and a["unidade_nome"] == "Unidade Teste"
    assert a["vinculos"]["pode_excluir"] is True
    assert client.get(f"/api/alunos/{a['id']}", headers=h).json()["nome"] == "Maria Teste"
    assert "aluno.criar" in acoes(db)


def test_codigo_sequencial_para_alunos_novos(criar):
    assert criar()["codigo"] == 1
    assert criar(nome="Joana", cpf=CPF_B)["codigo"] == 2


def test_cpf_invalido_duplicado_e_sem_cpf(client, h, base, criar):
    assert client.post("/api/alunos", headers=h, json=corpo(base, cpf="123.456.789-00")).status_code == 422
    assert client.post("/api/alunos", headers=h, json=corpo(base, cpf="111.111.111-11")).status_code == 422
    sem = {"nome": "Sem Doc", "unidade_id": base["unidade_id"]}
    assert client.post("/api/alunos", headers=h, json=sem).status_code == 422  # nem CPF nem "sem CPF"
    criar()
    dup = client.post("/api/alunos", headers=h, json=corpo(base, nome="Outra", cpf="52998224725"))  # sem máscara, mesmo CPF
    assert dup.status_code == 409 and "Maria Teste" in dup.json()["detail"]
    for n in ("A", "B"):
        r = client.post("/api/alunos", headers=h, json={"nome": f"Aluno {n} sem cpf", "sem_cpf": True, "unidade_id": base["unidade_id"]})
        assert r.status_code == 201 and r.json()["cpf"] is None and r.json()["sem_cpf"] is True  # vários sem CPF convivem


def test_sem_cpf_nao_grava_marcador_antigo(client, h, base, db):
    r = client.post("/api/alunos", headers=h, json={"nome": "Sem Doc", "sem_cpf": True, "cpf": CPF_A, "unidade_id": base["unidade_id"]})
    assert r.status_code == 201
    a = db.get(Aluno, r.json()["id"])
    assert a.cpf is None and a.sem_cpf


def test_cpf_pagador_invalido(client, h, base):
    assert client.post("/api/alunos", headers=h, json=corpo(base, cpf_pagador_recibo="123")).status_code == 422


def test_referencias_inexistentes(client, h, base):
    assert client.post("/api/alunos", headers=h, json=corpo(base, unidade_id=999)).status_code == 422
    assert client.post("/api/alunos", headers=h, json=corpo(base, profissao_id=999)).status_code == 422
    assert client.post("/api/alunos", headers=h, json=corpo(base, email="nao-e-email")).status_code == 422


def test_editar_cpf_proprio_nao_conflita_e_duplicado_sim(client, h, criar):
    a = criar()
    b = criar(nome="Joana", cpf=CPF_B)
    assert client.put(f"/api/alunos/{a['id']}", headers=h, json={"cpf": CPF_A, "nome": "Maria Editada"}).status_code == 200
    r = client.put(f"/api/alunos/{b['id']}", headers=h, json={"cpf": CPF_A})
    assert r.status_code == 409
    assert client.put(f"/api/alunos/{a['id']}", headers=h, json={"sem_cpf": True}).json()["cpf"] is None


def test_editar_so_envia_o_que_muda(client, h, criar, db):
    a = criar(rg="111", telefones=[{"numero": "11988887777"}], endereco={"logradouro": "Rua A", "numero": "1", "bairro": "B", "cidade": "C"})
    r = client.put(f"/api/alunos/{a['id']}", headers=h, json={"rg": "222"})
    j = r.json()
    assert j["rg"] == "222" and j["nome"] == "Maria Teste"
    assert len(j["telefones"]) == 1 and j["endereco"]["logradouro"] == "Rua A"
    depois = db.scalars(select(Auditoria).where(Auditoria.acao == "aluno.alterar")).one()
    assert depois.depois_json == {"rg": "222"} and depois.antes_json == {"rg": "111"}


def test_telefones_sao_atualizados_por_id_sem_recriar(client, h, criar, db):
    a = criar(telefones=[{"numero": "11988887777"}, {"numero": "11977776666"}])
    ids = [t["id"] for t in a["telefones"]]
    # corrige o 1º, mantém o 2º, acrescenta um 3º e torna o 3º o principal
    r = client.put(f"/api/alunos/{a['id']}", headers=h, json={"telefones": [
        {"id": ids[0], "numero": "(11) 91111-2222"}, {"id": ids[1], "numero": "11977776666"}, {"numero": "21 98765-4321", "principal": True}]})
    assert r.status_code == 200, r.text
    tels = r.json()["telefones"]
    assert [t["numero"] for t in tels] == ["5521987654321", "5511911112222", "5511977776666"]
    assert tels[0]["principal"] and not tels[1]["principal"]
    assert {t["id"] for t in tels} >= set(ids)  # os ids antigos continuam os mesmos
    # remover um telefone
    r = client.put(f"/api/alunos/{a['id']}", headers=h, json={"telefones": [{"id": ids[1], "numero": "11977776666"}]})
    assert [t["id"] for t in r.json()["telefones"]] == [ids[1]]
    assert db.query(AlunoTelefone).filter_by(aluno_id=a["id"]).count() == 1


def test_telefones_trocam_de_numero_entre_si(client, h, criar):
    a = criar(telefones=[{"numero": "11988887777"}, {"numero": "11977776666"}])
    i1, i2 = [t["id"] for t in a["telefones"]]
    r = client.put(f"/api/alunos/{a['id']}", headers=h, json={"telefones": [{"id": i1, "numero": "11977776666"}, {"id": i2, "numero": "11988887777"}]})
    assert r.status_code == 200, r.text
    assert {t["id"]: t["numero"] for t in r.json()["telefones"]} == {i1: "5511977776666", i2: "5511988887777"}


def test_normalizacao_de_telefone(criar):
    a = criar(telefones=[{"numero": "+55 (11) 8888-7777"}, {"numero": "011 3333-4444"}])  # celular antigo ganha o 9; fixo fica
    assert [t["numero"] for t in a["telefones"]] == ["5511988887777", "551133334444"]
    assert a["telefones"][0]["original"] == "+55 (11) 8888-7777"


def test_telefone_invalido_ou_repetido(client, h, base):
    assert client.post("/api/alunos", headers=h, json=corpo(base, telefones=[{"numero": "99999-0000"}])).status_code == 422  # sem DDD
    r = client.post("/api/alunos", headers=h, json=corpo(base, telefones=[{"numero": "11988887777"}, {"numero": "(11) 98888-7777"}]))
    assert r.status_code == 422 and "repetido" in r.json()["detail"]


def test_telefone_de_outro_aluno_e_recusado(client, h, criar):
    a = criar(telefones=[{"numero": "11988887777"}])
    b = criar(nome="Joana", cpf=CPF_B)
    r = client.put(f"/api/alunos/{b['id']}", headers=h, json={"telefones": [{"id": a["telefones"][0]["id"], "numero": "11988887777"}]})
    assert r.status_code == 422


def test_endereco_cria_atualiza_e_remove(client, h, criar, db):
    a = criar()
    assert a["endereco"] is None
    r = client.put(f"/api/alunos/{a['id']}", headers=h, json={"endereco": {"cep": "01310100", "cidade": "São Paulo"}})
    assert r.json()["endereco"]["cidade"] == "São Paulo" and r.json()["endereco"]["logradouro"] == ""
    r = client.put(f"/api/alunos/{a['id']}", headers=h, json={"endereco": {"cep": "01310100", "cidade": "Santos", "bairro": "Gonzaga"}})
    assert r.json()["endereco"]["cidade"] == "Santos"
    assert db.query(AlunoEndereco).filter_by(aluno_id=a["id"]).count() == 1
    assert client.put(f"/api/alunos/{a['id']}", headers=h, json={"endereco": {"cidade": ""}}).json()["endereco"] is None
    assert client.put(f"/api/alunos/{a['id']}", headers=h, json={"endereco": {"cep": "123"}}).status_code == 422


def test_inativar_e_reativar(client, h, criar, db):
    a = criar()
    assert client.post(f"/api/alunos/{a['id']}/inativar", headers=h).json()["status"] == "INATIVO"
    assert client.post(f"/api/alunos/{a['id']}/reativar", headers=h).json()["status"] == "ATIVO"
    assert {"aluno.inativar", "aluno.reativar"} <= set(acoes(db))


def test_excluir_sem_vinculos_remove_tudo(client, h, criar, db):
    a = criar(telefones=[{"numero": "11988887777"}], endereco={"logradouro": "Rua A"})
    assert client.delete(f"/api/alunos/{a['id']}", headers=h).status_code == 200
    assert client.get(f"/api/alunos/{a['id']}", headers=h).status_code == 404
    assert db.query(AlunoTelefone).count() == 0 and db.query(AlunoEndereco).count() == 0
    assert "aluno.excluir" in acoes(db)


def test_excluir_com_vinculos_e_recusado_e_orienta_inativar(client, h, criar, db, reservar, professor):
    a = criar()
    reservar(a["id"], professor["profissional_id"])
    v = client.get(f"/api/alunos/{a['id']}/vinculos", headers=h).json()
    assert v["reservas"] == 1 and not v["pode_excluir"]
    r = client.delete(f"/api/alunos/{a['id']}", headers=h)
    assert r.status_code == 409 and "Inative" in r.json()["detail"]
    assert db.get(Aluno, a["id"]).status == StatusAluno.ATIVO
    assert db.query(Reserva).count() == 1


def test_aluno_inexistente_404(client, h):
    assert client.get("/api/alunos/9999", headers=h).status_code == 404
    assert client.put("/api/alunos/9999", headers=h, json={"nome": "X Y"}).status_code == 404
