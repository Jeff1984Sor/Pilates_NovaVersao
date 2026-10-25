"""Bloqueios de agenda: pontual/recorrente, validações, "vale até quando", situação e regra da agenda."""

from datetime import date, time

import pytest
from sqlalchemy import select

from app.core.models import Auditoria
from app.domain import agenda as dom
from app.modules.cadastros import bloqueios as mod
from app.modules.cadastros.models import BloqueioAgenda

B = "/api/cadastros/bloqueios"
HOJE = date(2026, 10, 25)  # domingo


@pytest.fixture(autouse=True)
def _hoje(monkeypatch):
    monkeypatch.setattr(mod, "hoje_negocio", lambda: HOJE)


def _acoes(db):
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id)) if not a.acao.startswith("auth.")]


def _pontual(base, **extra):
    return {
        "unidade_id": base["unidade"], "recorrente": False, "data_inicio": "2026-12-24", "data_fim": "2026-12-26",
        "hora_inicio": "08:00", "hora_fim": "18:00", "motivo": "Recesso de fim de ano", **extra,
    }


def _recorrente(base, **extra):
    return {
        "unidade_id": base["unidade"], "recorrente": True, "dias_semana": [1, 3], "data_inicio": "2026-11-01",
        "data_fim": "2027-03-31", "hora_inicio": "12:00", "hora_fim": "13:00", "motivo": "Almoço da equipe", **extra,
    }


def test_opcoes_dos_formularios(client, full, base):
    o = client.get(f"{B}/opcoes", headers=full).json()
    assert o["unidades"][0]["nome"] == "Studio Centro" and len(o["dias"]) == 7


def test_crud_do_bloqueio_pontual(client, db, full, base):
    r = client.post(B, json=_pontual(base, tipo_servico_id=base["servico"], profissional_id=base["profissional"]), headers=full)
    assert r.status_code == 201, r.text
    assert r.json()["criados"] == 1
    b = r.json()["bloqueios"][0]
    assert b["vale_ate"] == "Até 26/12/2026" and b["aviso"] is None and b["situacao"] == "agendado"
    assert b["tipo_servico_nome"] == "Pilates" and b["profissional_nome"] == "Dra. Ana Lima" and b["recorrente"] is False

    r = client.put(f"{B}/{b['id']}", json=_pontual(base, data_fim="2026-12-31", motivo="Recesso"), headers=full)
    assert r.status_code == 200, r.text
    assert r.json()["vale_ate"] == "Até 31/12/2026" and r.json()["tipo_servico_nome"] == "Todos os serviços"
    assert r.json()["profissional_nome"] == "Todos os profissionais"
    assert client.patch(f"{B}/{b['id']}/ativo", params={"ativo": False}, headers=full).json()["situacao"] == "inativo"
    assert client.delete(f"{B}/{b['id']}", headers=full).status_code == 200
    assert client.get(f"{B}/{b['id']}", headers=full).status_code == 404
    assert _acoes(db) == ["bloqueio_agenda.criar", "bloqueio_agenda.alterar", "bloqueio_agenda.inativar", "bloqueio_agenda.excluir"]


def test_pontual_exige_data_final(client, full, base):
    corpo = _pontual(base)
    corpo.pop("data_fim")
    r = client.post(B, json=corpo, headers=full)
    assert r.status_code == 422 and "valendo para sempre" in r.json()["detail"]
    assert client.post(B, json={**corpo, "data_fim": None}, headers=full).status_code == 422
    # um único dia: mesma data nos dois campos
    assert client.post(B, json={**corpo, "data_fim": corpo["data_inicio"]}, headers=full).status_code == 201


def test_validacoes_de_horas_datas_e_dias(client, full, base):
    r = client.post(B, json=_pontual(base, hora_fim="08:00"), headers=full)
    assert r.status_code == 422 and "horário final deve ser maior" in r.json()["detail"]
    assert client.post(B, json=_pontual(base, hora_inicio="10:00", hora_fim="09:00"), headers=full).status_code == 422
    r = client.post(B, json=_pontual(base, data_fim="2026-12-01"), headers=full)
    assert r.status_code == 422 and "data final" in r.json()["detail"].lower()
    assert client.post(B, json=_recorrente(base, dias_semana=[]), headers=full).status_code == 422
    assert client.post(B, json=_recorrente(base, dias_semana=[7]), headers=full).status_code == 422
    assert client.post(B, json=_pontual(base, unidade_id=999), headers=full).status_code == 422
    assert client.post(B, json=_pontual(base, tipo_servico_id=999), headers=full).status_code == 422
    assert client.post(B, json=_pontual(base, profissional_id=999), headers=full).status_code == 422
    assert client.post(B, json=_pontual(base, motivo="x" * 201), headers=full).status_code == 422


def test_recorrente_cria_um_por_dia_e_pode_ficar_sem_data_final_com_aviso(client, db, full, base):
    r = client.post(B, json=_recorrente(base), headers=full).json()
    assert r["criados"] == 2
    assert sorted(b["dia_nome"] for b in r["bloqueios"]) == ["Quinta", "Terça"]
    assert db.scalars(select(BloqueioAgenda)).all().__len__() == 2

    sem_fim = _recorrente(base, dias_semana=[4])
    sem_fim.pop("data_fim")
    b = client.post(B, json=sem_fim, headers=full).json()["bloqueios"][0]
    assert b["data_fim"] is None and "vale para sempre" in b["vale_ate"] and "Sem data final" in b["aviso"]


def test_editar_recorrente_exige_um_unico_dia(client, full, base):
    b = client.post(B, json=_recorrente(base), headers=full).json()["bloqueios"][0]
    r = client.put(f"{B}/{b['id']}", json=_recorrente(base), headers=full)
    assert r.status_code == 422 and "apenas um dia" in r.json()["detail"]
    r = client.put(f"{B}/{b['id']}", json=_recorrente(base, dias_semana=[2]), headers=full)
    assert r.status_code == 200 and r.json()["dia_semana"] == 2


def test_bloqueio_legado_pontual_sem_data_final_continua_valendo_com_aviso(client, db, full, base):
    legado = BloqueioAgenda(
        unidade_id=base["unidade"], recorrente=False, data_inicio=date(2026, 1, 5), data_fim=None,
        hora_inicio=time(8), hora_fim=time(9), motivo="Importado",
    )
    db.add(legado)
    db.commit()
    b = client.get(f"{B}/{legado.id}", headers=full).json()
    assert b["situacao"] == "vigente" and "para sempre" in b["vale_ate"] and "Informe a data final" in b["aviso"]
    # a agenda continua bloqueando (nenhum comportamento muda sem ação do usuário)
    datas = client.get(f"{B}/{legado.id}/datas", params={"dias": 3}, headers=full).json()
    assert datas == ["2026-10-25", "2026-10-26", "2026-10-27"]
    # para salvar de novo, precisa da data final
    sem_fim = _pontual(base, data_inicio="2026-01-05")
    sem_fim.pop("data_fim")
    assert client.put(f"{B}/{legado.id}", json=sem_fim, headers=full).status_code == 422
    assert client.put(f"{B}/{legado.id}", json=_pontual(base, data_inicio="2026-01-05", data_fim="2026-11-30"), headers=full).status_code == 200


def test_datas_afetadas_usam_a_regra_da_agenda(client, full, base, db):
    r = client.post(B, json=_recorrente(base, dias_semana=[1], data_inicio="2026-10-01", data_fim="2026-11-30"), headers=full).json()
    bid = r["bloqueios"][0]["id"]
    datas = client.get(f"{B}/{bid}/datas", params={"dias": 40}, headers=full).json()
    assert datas == ["2026-10-27", "2026-11-03", "2026-11-10", "2026-11-17", "2026-11-24"]  # só terças, até a data final
    # coerente com o domínio: o slot das 12h nessas datas está bloqueado, 13h em ponto não
    b = db.get(BloqueioAgenda, bid)
    dom_b = mod._como_dominio(b)
    assert dom.slot_bloqueado([dom_b], date(2026, 11, 3), time(12, 0), time(12, 50))
    assert not dom.slot_bloqueado([dom_b], date(2026, 11, 3), time(13, 0), time(13, 50))
    assert not dom.slot_bloqueado([dom_b], date(2026, 11, 4), time(12, 0), time(12, 50))
    client.patch(f"{B}/{bid}/ativo", params={"ativo": False}, headers=full)
    assert client.get(f"{B}/{bid}/datas", headers=full).json() == []


def test_lista_chips_situacao_busca_e_ordem(client, full, base):
    client.post(B, json=_pontual(base, data_inicio="2026-01-10", data_fim="2026-01-12", motivo="Reforma"), headers=full)  # expirado
    client.post(B, json=_pontual(base, data_inicio="2026-10-20", data_fim="2026-10-30", motivo="Feriado ponte"), headers=full)  # vigente
    client.post(B, json=_pontual(base, motivo="Natal"), headers=full)  # agendado
    ina = client.post(B, json=_pontual(base, motivo="Teste inativo", ativo=False), headers=full).json()["bloqueios"][0]

    lista = client.get(B, headers=full).json()
    assert lista["contagens"] == {"todos": 4, "vigentes": 2, "expirados": 1, "inativos": 1}
    assert lista["total"] == 4
    assert [i["motivo"] for i in lista["itens"]][0] in {"Natal", "Teste inativo"}  # mais recentes primeiro
    vig = client.get(B, params={"situacao": "vigentes"}, headers=full).json()
    assert sorted(i["motivo"] for i in vig["itens"]) == ["Feriado ponte", "Natal"]
    assert vig["contagens"]["todos"] == 4
    exp = client.get(B, params={"situacao": "expirados"}, headers=full).json()
    assert [i["motivo"] for i in exp["itens"]] == ["Reforma"]
    assert [i["id"] for i in client.get(B, params={"situacao": "inativos"}, headers=full).json()["itens"]] == [ina["id"]]
    assert [i["motivo"] for i in client.get(B, params={"q": "ponte"}, headers=full).json()["itens"]] == ["Feriado ponte"]
    asc = client.get(B, params={"ordenar": "data", "direcao": "asc"}, headers=full).json()["itens"]
    assert asc[0]["motivo"] == "Reforma"
    assert client.get(B, params={"profissional_id": base["profissional"]}, headers=full).json()["total"] == 0
