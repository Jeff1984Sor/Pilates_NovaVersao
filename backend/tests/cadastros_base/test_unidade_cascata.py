"""Unidade: capacidade mínima 1 e exclusão que leva horários e bloqueios junto (mas bloqueia com vínculos reais)."""

from datetime import date, time

from sqlalchemy import func, select

from app.modules.agenda.models import AulaSessao
from app.modules.cadastros.models import (
    BloqueioAgenda,
    HorarioFuncionamento,
    HorarioStudio,
    TipoServico,
    Unidade,
    horario_funcionamento_tipo_servico,
)
from tests.cadastros_base.conftest import auditorias

U = "/api/cadastros/unidades"


def test_capacidade_zero_tem_mensagem_clara_em_portugues(client, h_full):
    r = client.post(U, headers=h_full, json={"nome": "Matriz", "capacidade": 0})
    assert r.status_code == 422 and "pelo menos 1 vaga" in r.json()["detail"]
    u = client.post(U, headers=h_full, json={"nome": "Matriz", "capacidade": 4}).json()
    r = client.put(f"{U}/{u['id']}", headers=h_full, json={"nome": "Matriz", "capacidade": 0})
    assert r.status_code == 422 and "pelo menos 1 vaga" in r.json()["detail"]
    r = client.post(U, headers=h_full, json={"nome": "Outra", "duracao_aula_minutos": 0})
    assert r.status_code == 422 and "1 minuto" in r.json()["detail"]
    assert client.post(U, headers=h_full, json={"nome": "Mínima", "capacidade": 1, "duracao_aula_minutos": 1}).status_code == 201


def _unidade_com_horarios(db):
    un, ts = Unidade(nome="Matriz", capacidade=5), TipoServico(nome="Pilates")
    db.add_all([un, ts])
    db.flush()
    hf = HorarioFuncionamento(unidade_id=un.id, dia_semana=0, hora_inicio=time(7), hora_fim=time(20))
    hf.tipos_servico.append(ts)
    db.add_all([hf, HorarioStudio(unidade_id=un.id, tipo_servico_id=ts.id, dia_semana=1, hora_inicio=time(8), hora_fim=time(9)),
                BloqueioAgenda(unidade_id=un.id, data_inicio=date(2026, 1, 5), hora_inicio=time(8), hora_fim=time(9))])
    db.commit()
    return un.id, ts.id


def test_vinculos_separam_o_que_bloqueia_do_que_sai_junto(client, db, h_full):
    uid, _ = _unidade_com_horarios(db)
    v = client.get(f"{U}/{uid}/vinculos", headers=h_full).json()
    assert v["pode_excluir"] is True and v["total"] == 0 and v["itens"] == []
    assert v["total_junto"] == 3
    assert {i["rotulo"] for i in v["junto"]} == {"horário de funcionamento", "horário da grade", "bloqueio de agenda"}


def test_excluir_unidade_leva_horarios_e_bloqueios_junto(client, db, h_full):
    uid, _ = _unidade_com_horarios(db)
    assert client.delete(f"{U}/{uid}", headers=h_full).status_code == 200
    db.expire_all()
    assert db.get(Unidade, uid) is None
    for m in (HorarioFuncionamento, HorarioStudio, BloqueioAgenda):
        assert db.scalar(select(func.count()).select_from(m)) == 0
    assert db.scalar(select(func.count()).select_from(horario_funcionamento_tipo_servico)) == 0
    assert "removidos junto" in auditorias(db, "unidade.excluir")[-1].descricao


def test_unidade_com_aula_bloqueia_e_nao_apaga_nada(client, db, h_full):
    uid, tid = _unidade_com_horarios(db)
    db.add(AulaSessao(unidade_id=uid, tipo_servico_id=tid, data=date(2026, 1, 5), hora_inicio=time(8), hora_fim=time(9)))
    db.commit()
    v = client.get(f"{U}/{uid}/vinculos", headers=h_full).json()
    assert v["pode_excluir"] is False and v["itens"][0]["rotulo"] == "aula" and v["total_junto"] == 3
    r = client.delete(f"{U}/{uid}", headers=h_full)
    assert r.status_code == 409 and "1 aula" in r.json()["detail"] and "Desative" in r.json()["detail"]
    assert "horário" not in r.json()["detail"]
    assert db.scalar(select(func.count()).select_from(HorarioFuncionamento)) == 1  # nada foi removido
    assert db.get(Unidade, uid) is not None
