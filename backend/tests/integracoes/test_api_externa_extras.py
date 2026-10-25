"""Rotas NOVAS da API externa (contrato ativo, aulas de amanhã) e regras de segurança da escrita de mensagens."""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.alunos.models import AlunoTelefone, WhatsappMensagem
from app.modules.cadastros.models import Plano, Profissional
from app.modules.contratos.models import Contrato
from tests.integracoes.conftest import novo_aluno


@pytest.fixture
def chave(client, full):
    return {"X-API-Key": client.post("/api/integracoes/tokens", json={"nome": "Bot"}, headers=full).json()["valor"]}


@pytest.fixture
def mundo(db, base, hoje_fixo):
    prof = Profissional(nome="Paula")
    db.add(prof)
    db.flush()
    plano = Plano(nome="Plano", tipo_servico_id=base.servico.id, valor=Decimal("300"), aulas_por_semana=2)
    db.add(plano)
    ana = novo_aluno(db, base.unidade.id, "Ana", 1)
    bia = novo_aluno(db, base.unidade.id, "Bia", 2)
    db.add(AlunoTelefone(aluno_id=ana.id, ordem=1, numero="5515997762467", numero_original="(15) 99776-2467"))
    db.flush()
    hoje = hoje_fixo

    def contrato(aluno, ini, fim):
        c = Contrato(aluno_id=aluno.id, plano_id=plano.id, unidade_id=base.unidade.id, profissional_id=prof.id,
                     data_inicio=ini, data_fim=fim, valor_parcela=Decimal("300"), valor_total=Decimal("900"))
        db.add(c)
        db.flush()
        return c

    antigo = contrato(ana, hoje - timedelta(days=400), hoje - timedelta(days=40))
    vigente = contrato(ana, hoje - timedelta(days=10), hoje + timedelta(days=80))
    da_bia = contrato(bia, hoje - timedelta(days=10), hoje + timedelta(days=80))

    def aula(dia, hora):
        s = AulaSessao(unidade_id=base.unidade.id, tipo_servico_id=base.servico.id, profissional_id=prof.id, data=dia,
                       hora_inicio=time(hora), hora_fim=time(hora, 50))
        db.add(s)
        db.flush()
        return s

    amanha, hoje_s, depois = aula(hoje + timedelta(days=1), 9), aula(hoje, 9), aula(hoje + timedelta(days=2), 9)
    db.add_all([Reserva(aluno_id=ana.id, aula_sessao_id=amanha.id, status="RESERVADA"),
                Reserva(aluno_id=bia.id, aula_sessao_id=amanha.id, status="CANCELADA"),
                Reserva(aluno_id=ana.id, aula_sessao_id=hoje_s.id, status="RESERVADA"),
                Reserva(aluno_id=ana.id, aula_sessao_id=depois.id, status="RESERVADA")])
    db.commit()
    return type("M", (), {"ana": ana, "bia": bia, "antigo": antigo, "vigente": vigente, "da_bia": da_bia})


def test_contrato_ativo_e_o_vigente_hoje(client, mundo, chave):
    r = client.get("/api/integracao/contratos/ativo?cdAluno=1001", headers=chave)
    assert r.status_code == 200 and r.json()["id"] == mundo.vigente.id and r.json()["cdAluno"] == 1001
    assert set(r.json()) == {"id", "cdContrato", "cdAluno", "plano", "profissional", "unidade", "dt_inicio", "dt_fim",
                             "status", "valor_parcela", "valor_total"}
    assert client.get("/api/integracao/contratos/ativo?cdAluno=999", headers=chave).status_code == 404
    assert client.get("/api/integracao/contratos/ativo?cdAluno=1001").status_code == 401


def test_aulas_de_amanha_so_reservadas(client, mundo, chave):
    r = client.get("/api/integracao/aulas/amanha", headers=chave)
    assert r.status_code == 200
    itens = r.json()
    assert [(i["cdAluno"], i["dsNome"], i["dsTelefone"], i["status"]) for i in itens] == [(1001, "Ana", "(15) 99776-2467", "RESERVADA")]
    assert itens[0]["hora_inicio"] == "09:00:00" and "dsCPF" not in itens[0] and "dsEmail" not in itens[0]
    assert client.get("/api/integracao/aulas/amanha").status_code == 401


def test_aulas_proximas_usam_a_data_de_negocio(client, mundo, chave):
    todas = client.get("/api/integracao/aulas?cdAluno=1001", headers=chave).json()
    assert len(todas) == 3
    # inclui hoje
    assert len(client.get("/api/integracao/aulas?cdAluno=1001&apenas_proximas=true", headers=chave).json()) == 3


def test_mensagem_com_contrato_de_outro_aluno_ignora_o_contrato(client, db, mundo, chave):
    corpo = {"cdAluno": 1001, "texto": "oi", "contrato_id": mundo.da_bia.id}
    assert client.post("/api/integracao/whatsapp-mensagens", json=corpo, headers=chave).status_code == 200
    corpo["contrato_id"] = mundo.vigente.id
    assert client.post("/api/integracao/whatsapp-mensagens", json=corpo, headers=chave).status_code == 200
    db.expire_all()
    assert [m.contrato_id for m in db.scalars(select(WhatsappMensagem).order_by(WhatsappMensagem.id))] == [None, mundo.vigente.id]


def test_mensagem_sem_fuso_e_validacoes(client, db, mundo, chave):
    r = client.post("/api/integracao/whatsapp-mensagens", headers=chave,
                    json={"cdAluno": 1001, "texto": "oi", "data_iso": "2026-10-20T10:00:00"})
    assert r.status_code == 200 and r.json()["enviado_em"] == "2026-10-20T13:00:00+00:00"  # São Paulo = UTC-3
    for corpo in ({"cdAluno": 1001, "texto": ""}, {"cdAluno": 1001, "texto": "x" * 4001}, {"cdAluno": "a", "texto": "x"},
                  {"cdAluno": 1001, "texto": "x", "telefone": "9" * 31}):
        assert client.post("/api/integracao/whatsapp-mensagens", json=corpo, headers=chave).status_code == 422


def test_escrita_de_mensagem_e_auditada_sem_o_texto(client, db, mundo, chave):
    client.post("/api/integracao/whatsapp-mensagens", json={"cdAluno": 1001, "texto": "texto secreto da conversa"}, headers=chave)
    db.expire_all()
    a = db.scalar(select(Auditoria).where(Auditoria.acao == "integracao.whatsapp_mensagem"))
    assert a.usuario_nome == "Robô" and "Bot" in a.descricao and "secreto" not in a.descricao


def test_busca_por_nome_trata_curinga_como_texto(client, mundo, chave):
    assert client.get("/api/integracao/alunos?nome=%25", headers=chave).json() == []
    assert client.get("/api/integracao/alunos?nome=_na", headers=chave).json() == []
    assert [a["dsNome"] for a in client.get("/api/integracao/alunos?nome=an", headers=chave).json()] == ["Ana"]


def test_resposta_traz_somente_campos_do_contrato(client, mundo, chave):
    a = client.get("/api/integracao/alunos/por-codigo/1001", headers=chave).json()
    assert set(a) == {"id", "cdAluno", "dsNome", "dsCPF", "dsEmail", "dsTelefone", "status"}
