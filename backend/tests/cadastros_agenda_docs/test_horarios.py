"""Horários de funcionamento (CRUD, validações, duplicidade, gerar em lote) e horários do studio (legado)."""

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.cadastros.models import ContadorCodigo, HorarioFuncionamento, HorarioStudio

H = "/api/cadastros/horarios"


def _acoes(db):
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id)) if not a.acao.startswith("auth.")]


def _janela(base, **extra):
    return {"unidade_id": base["unidade"], "dia_semana": 0, "hora_inicio": "08:00", "hora_fim": "12:00", **extra}


def test_opcoes_para_os_formularios(client, full, base):
    o = client.get(f"{H}/opcoes", headers=full).json()
    assert [u["nome"] for u in o["unidades"]] == ["Studio Centro"]
    assert {s["nome"] for s in o["servicos"]} == {"Pilates", "Fisioterapia"}
    assert [p["nome"] for p in o["profissionais"]] == ["Dra. Ana Lima"]
    assert o["dias"][0] == {"valor": 0, "nome": "Segunda"} and len(o["dias"]) == 7


def test_crud_horario_de_funcionamento_com_servicos(client, db, full, base):
    r = client.post(H, json=_janela(base, tipos_servico_ids=[base["servico"]]), headers=full)
    assert r.status_code == 201, r.text
    h = r.json()
    assert h["servicos"] == "Pilates" and h["tipos_servico_ids"] == [base["servico"]] and h["dia_nome"] == "Segunda"
    # 08-12 com aulas de 50 min + 10 de intervalo: 08:00, 09:00, 10:00, 11:00 (domínio da agenda)
    assert h["aulas_por_dia"] == 4
    assert client.get(f"{H}/{h['id']}", headers=full).json()["id"] == h["id"]

    r = client.put(f"{H}/{h['id']}", json=_janela(base, hora_fim="13:00", tipos_servico_ids=[], ativo=False), headers=full)
    assert r.status_code == 200, r.text
    assert r.json()["servicos"] == "Todos os serviços" and r.json()["ativo"] is False and r.json()["aulas_por_dia"] == 5
    assert client.patch(f"{H}/{h['id']}/ativo", params={"ativo": True}, headers=full).json()["ativo"] is True
    assert client.delete(f"{H}/{h['id']}", headers=full).status_code == 200
    assert client.get(f"{H}/{h['id']}", headers=full).status_code == 404
    assert db.scalars(select(HorarioFuncionamento)).first() is None
    assert _acoes(db) == [
        "horario_funcionamento.criar", "horario_funcionamento.alterar", "horario_funcionamento.ativar", "horario_funcionamento.excluir",
    ]


def test_validacoes_do_horario(client, full, base):
    assert client.post(H, json=_janela(base, hora_fim="08:00"), headers=full).status_code == 422
    r = client.post(H, json=_janela(base, hora_inicio="12:00", hora_fim="08:00"), headers=full)
    assert r.status_code == 422 and "horário final deve ser maior" in r.json()["detail"]
    assert client.post(H, json=_janela(base, dia_semana=7), headers=full).status_code == 422
    assert client.post(H, json=_janela(base, dia_semana=-1), headers=full).status_code == 422
    assert client.post(H, json=_janela(base, unidade_id=999), headers=full).status_code == 422
    assert client.post(H, json=_janela(base, tipos_servico_ids=[999]), headers=full).status_code == 422
    assert client.post(H, json={"unidade_id": base["unidade"]}, headers=full).status_code == 422


def test_duplicidade_segue_a_regra_do_antigo(client, full, base):
    s1, s2 = base["servico"], base["servico2"]
    assert client.post(H, json=_janela(base, tipos_servico_ids=[s1]), headers=full).status_code == 201
    # mesmo serviço: duplicado; outro serviço: pode
    r = client.post(H, json=_janela(base, tipos_servico_ids=[s1]), headers=full)
    assert r.status_code == 409 and "Já existe um horário" in r.json()["detail"]
    assert client.post(H, json=_janela(base, tipos_servico_ids=[s2]), headers=full).status_code == 201
    # janela geral (sem serviço) idêntica a uma específica: antigo só barra se já existir uma GERAL
    assert client.post(H, json=_janela(base), headers=full).status_code == 201
    assert client.post(H, json=_janela(base), headers=full).status_code == 409
    # com uma geral cadastrada, qualquer janela igual (com serviço) também é barrada
    assert client.post(H, json=_janela(base, tipos_servico_ids=[s1]), headers=full).status_code == 409
    # outro dia / outra faixa: livre
    assert client.post(H, json=_janela(base, dia_semana=1), headers=full).status_code == 201
    assert client.post(H, json=_janela(base, hora_inicio="14:00", hora_fim="18:00"), headers=full).status_code == 201


def test_editar_nao_conflita_consigo_mesmo(client, full, base):
    h = client.post(H, json=_janela(base), headers=full).json()
    assert client.put(f"{H}/{h['id']}", json=_janela(base, ativo=False), headers=full).status_code == 200
    outro = client.post(H, json=_janela(base, dia_semana=2), headers=full).json()
    assert client.put(f"{H}/{outro['id']}", json=_janela(base, dia_semana=0), headers=full).status_code == 409


def test_lista_filtros_chips_e_ordem(client, full, base):
    s1 = base["servico"]
    client.post(H, json=_janela(base, dia_semana=2, tipos_servico_ids=[s1]), headers=full)
    client.post(H, json=_janela(base, dia_semana=0), headers=full)
    ina = client.post(H, json=_janela(base, dia_semana=4, ativo=False), headers=full).json()
    lista = client.get(H, headers=full).json()
    assert [i["dia_semana"] for i in lista["itens"]] == [0, 2, 4]
    assert lista["contagens"] == {"todos": 3, "ativos": 2, "inativos": 1}
    assert [i["id"] for i in client.get(H, params={"situacao": "inativos"}, headers=full).json()["itens"]] == [ina["id"]]
    assert client.get(H, params={"situacao": "inativos"}, headers=full).json()["contagens"]["todos"] == 3
    assert len(client.get(H, params={"dia_semana": 2}, headers=full).json()["itens"]) == 1
    # janela por serviço: a geral (segunda) e a do serviço (quarta) atendem Pilates; Fisioterapia só a geral e a inativa
    por_srv = client.get(H, params={"tipo_servico_id": base["servico2"]}, headers=full).json()["itens"]
    assert [i["dia_semana"] for i in por_srv] == [0, 4]
    assert client.get(H, params={"q": "centro"}, headers=full).json()["total"] == 3
    assert client.get(H, params={"q": "zzz"}, headers=full).json()["total"] == 0
    desc = client.get(H, params={"ordenar": "dia", "direcao": "desc"}, headers=full).json()["itens"]
    assert [i["dia_semana"] for i in desc] == [4, 2, 0]


def test_gerar_horarios_em_lote_e_idempotente(client, db, full, base):
    corpo = {
        "unidade_id": base["unidade"], "dias_semana": [0, 1, 2, 3, 4], "hora_inicio": "07:00", "hora_fim": "20:00",
        "tipos_servico_ids": [base["servico"]],
    }
    r = client.post(f"{H}/gerar", json=corpo, headers=full)
    assert r.status_code == 200, r.text
    assert r.json()["criados"] == 5 and r.json()["ignorados"] == 0
    assert db.scalars(select(HorarioFuncionamento)).all().__len__() == 5
    # de novo: nada novo
    r = client.post(f"{H}/gerar", json=corpo, headers=full).json()
    assert r["criados"] == 0 and r["ignorados"] == 5 and "já existiam" in r["mensagem"]
    # inclui sábado: só ele é novo
    r = client.post(f"{H}/gerar", json={**corpo, "dias_semana": [4, 5]}, headers=full).json()
    assert r["criados"] == 1 and r["ignorados"] == 1
    assert "horario_funcionamento.gerar" in _acoes(db)


def test_gerar_validacoes(client, full, base):
    corpo = {"unidade_id": base["unidade"], "dias_semana": [0], "hora_inicio": "10:00", "hora_fim": "09:00"}
    assert client.post(f"{H}/gerar", json=corpo, headers=full).status_code == 422
    assert client.post(f"{H}/gerar", json={**corpo, "hora_fim": "11:00", "dias_semana": []}, headers=full).status_code == 422
    assert client.post(f"{H}/gerar", json={**corpo, "hora_fim": "11:00", "dias_semana": [9]}, headers=full).status_code == 422
    assert client.post(f"{H}/gerar", json={**corpo, "hora_fim": "11:00", "unidade_id": 999}, headers=full).status_code == 422


# ------------------------------------------------------------------------------------------------ studio (legado)
def _studio(base, **extra):
    return {
        "unidade_id": base["unidade"], "tipo_servico_id": base["servico"], "dia_semana": 1, "hora_inicio": "09:00",
        "hora_fim": "09:50", "capacidade": 4, **extra,
    }


def test_crud_horario_do_studio_com_codigo_e_marca_de_legado(client, db, full, base):
    r = client.post(f"{H}/studio", json=_studio(base, profissional_id=base["profissional"]), headers=full)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["legado"] is True and s["codigo"] == 1 and s["profissional_nome"] == "Dra. Ana Lima" and s["dia_nome"] == "Terça"
    assert db.get(ContadorCodigo, "horario_studio").ultimo == 1
    assert client.post(f"{H}/studio", json=_studio(base, profissional_id=base["profissional"]), headers=full).status_code == 409
    sem_prof = client.post(f"{H}/studio", json=_studio(base), headers=full)
    assert sem_prof.status_code == 201 and sem_prof.json()["profissional_nome"] is None
    assert client.post(f"{H}/studio", json=_studio(base), headers=full).status_code == 409  # sem profissional também repete
    r = client.put(f"{H}/studio/{s['id']}", json=_studio(base, profissional_id=base["profissional"], capacidade=6), headers=full)
    assert r.json()["capacidade"] == 6
    lista = client.get(f"{H}/studio", headers=full).json()
    assert lista["total"] == 2
    assert client.get(f"{H}/studio", params={"profissional_id": base["profissional"]}, headers=full).json()["total"] == 1
    assert client.get(f"{H}/studio", params={"dia_semana": 3}, headers=full).json()["total"] == 0
    assert client.delete(f"{H}/studio/{s['id']}", headers=full).status_code == 200
    assert db.get(HorarioStudio, s["id"]) is None
    assert client.delete(f"{H}/studio/999", headers=full).status_code == 404


def test_horario_do_studio_valida(client, full, base):
    assert client.post(f"{H}/studio", json=_studio(base, hora_fim="09:00"), headers=full).status_code == 422
    assert client.post(f"{H}/studio", json=_studio(base, tipo_servico_id=999), headers=full).status_code == 422
    assert client.post(f"{H}/studio", json=_studio(base, profissional_id=999), headers=full).status_code == 422
    assert client.post(f"{H}/studio", json=_studio(base, capacidade=0), headers=full).status_code == 422


def test_gerar_horarios_do_studio_divide_a_faixa_pelo_intervalo(client, db, full, base):
    corpo = {
        "unidade_id": base["unidade"], "tipo_servico_id": base["servico"], "profissional_id": base["profissional"],
        "dias_semana": [0, 2], "hora_inicio": "08:00", "hora_fim": "11:00", "intervalo_minutos": 60, "capacidade": 5,
    }
    r = client.post(f"{H}/studio/gerar", json=corpo, headers=full)
    assert r.status_code == 200, r.text
    assert r.json()["criados"] == 6  # 08-09, 09-10, 10-11 em 2 dias
    itens = client.get(f"{H}/studio", headers=full).json()["itens"]
    assert [(i["dia_semana"], i["hora_inicio"][:5], i["hora_fim"][:5], i["capacidade"]) for i in itens][:3] == [
        (0, "08:00", "09:00", 5), (0, "09:00", "10:00", 5), (0, "10:00", "11:00", 5),
    ]
    assert db.get(ContadorCodigo, "horario_studio").ultimo == 6
    r = client.post(f"{H}/studio/gerar", json=corpo, headers=full).json()
    assert r["criados"] == 0 and r["ignorados"] == 6
    assert "horario_studio.gerar" in _acoes(db)


def test_gerar_studio_recusa_intervalo_que_nao_cabe_e_excesso(client, full, base):
    corpo = {
        "unidade_id": base["unidade"], "tipo_servico_id": base["servico"], "dias_semana": [0], "hora_inicio": "08:00",
        "hora_fim": "08:30", "intervalo_minutos": 60,
    }
    r = client.post(f"{H}/studio/gerar", json=corpo, headers=full)
    assert r.status_code == 422 and "nenhum horário cabe" in r.json()["detail"]
    muito = {**corpo, "dias_semana": [0, 1, 2, 3, 4, 5, 6], "hora_inicio": "00:00", "hora_fim": "23:59", "intervalo_minutos": 5}
    assert client.post(f"{H}/studio/gerar", json=muito, headers=full).status_code == 422
    assert client.post(f"{H}/studio/gerar", json={**corpo, "intervalo_minutos": 1}, headers=full).status_code == 422
