"""Grade semanal e painel operacional: formato do payload, agrupamento, filtros, status do domínio, cobrança só p/ financeiro."""

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from app.modules.agenda import routes
from app.modules.agenda.models import StatusReserva
from app.modules.financeiro.models import ContaReceber, StatusReceber
from tests.agenda import fabrica
from tests.conftest import auth


@pytest.fixture
def aula_cheia(db, cenario):
    """Segunda 26/10 09:00 com duas alunas (Ana confirmada, Bruna não) + uma aula de outra professora às 09:00."""
    r1 = fabrica.reserva_direta(db, cenario.a1, cenario.ses)
    r1.confirmada_em = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    fabrica.reserva_direta(db, cenario.a2, cenario.ses)
    p2 = fabrica.profissional(db, "Carla Mendes")
    a3 = fabrica.aluno(db, cenario.un, "Diana Rocha", telefone="5511988887777")
    ses2 = fabrica.sessao(db, cenario.un, cenario.srv, p2)
    fabrica.reserva_direta(db, a3, ses2)
    db.commit()
    cenario.p2, cenario.a3, cenario.ses2, cenario.r1 = p2, a3, ses2, r1
    return cenario


# ----------------------------------------------------------------------------------------------------- grade
def test_grade_formato_e_ocupacao(client, db, aula_cheia, full):
    g = client.get("/api/agenda/grade", params={"semana": "2026-10-28"}, headers=auth(full)).json()
    assert g["semana_inicio"] == "2026-10-26" and g["semana_fim"] == "2026-10-31"
    assert g["rotulo"] == "Outubro 2026" and g["anterior"] == "2026-10-19" and g["proxima"] == "2026-11-02"
    assert [d["rotulo"] for d in g["dias"]] == ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    assert {"cor", "rotulo"} <= set(g["legenda"][0])
    seg = g["dias"][0]
    assert seg["data"] == "2026-10-26" and seg["numero"] == 26
    # 3 reservas na segunda: 2 na aula da Natalia e 1 na da Carla, todas no mesmo horário -> 3 colunas lado a lado
    assert len(seg["blocos"]) == 3
    b = next(b for b in seg["blocos"] if b["aluno"] == "Ana Paula")
    assert b["ocupacao"] == "2/2" and b["hora"] == "09:00" and b["inicio_min"] == 540 and b["fim_min"] == 590
    assert b["cor"] == "#3b9ad9" and b["situacao"] == "Confirmada" and b["status"] == "RESERVADA"
    assert b["colunas"] == 3 and {x["coluna"] for x in seg["blocos"]} == {0, 1, 2}
    bruna = next(b for b in seg["blocos"] if b["aluno"] == "Bruna Lima")
    assert bruna["cor"] == "#f59e0b" and bruna["situacao"] == "A confirmar"
    assert all(d["blocos"] == [] for d in g["dias"][1:])


def test_grade_cor_por_status_e_aula_vazia(client, db, aula_cheia, full):
    fabrica.reserva_direta(db, aula_cheia.a1, fabrica.sessao(db, aula_cheia.un, aula_cheia.srv, aula_cheia.prof, dia=date(2026, 10, 27), inicio=time(8, 0)), StatusReserva.CONCLUIDA)
    fabrica.sessao(db, aula_cheia.un, aula_cheia.srv, aula_cheia.prof, dia=date(2026, 10, 27), inicio=time(15, 0))
    db.commit()
    ter = client.get("/api/agenda/grade", params={"semana": "2026-10-26"}, headers=auth(full)).json()["dias"][1]["blocos"]
    concluida = next(b for b in ter if b["aluno"])
    assert concluida["cor"] == "#16a34a" and concluida["situacao"] == "Concluída"
    vazia = next(b for b in ter if not b["aluno"])
    assert vazia["cor"] == "#cbd5e1" and vazia["situacao"] == "Sem alunos" and vazia["reserva_id"] is None


def test_grade_cancelada_nao_conta_na_ocupacao(client, db, aula_cheia, full):
    rid = aula_cheia.r1.id
    client.post(f"/api/aulas/reservas/{rid}/desmarcar", headers=auth(full))
    seg = client.get("/api/agenda/grade", params={"semana": "2026-10-26"}, headers=auth(full)).json()["dias"][0]
    ana = next(b for b in seg["blocos"] if b["aluno"] == "Ana Paula")
    assert ana["cor"] == "#9ca3af" and ana["ocupacao"] == "1/2"


def test_grade_filtra_por_profissional(client, aula_cheia, full):
    g = client.get("/api/agenda/grade", params={"semana": "2026-10-26", "profissional_id": aula_cheia.p2.id}, headers=auth(full)).json()
    assert [b["aluno"] for b in g["dias"][0]["blocos"]] == ["Diana Rocha"]


def test_grade_sabado_e_domingo_mostram_a_proxima_semana(client, aula_cheia, full):
    """Sem 'semana' e hoje = domingo 25/10 (relógio congelado): mostra 26/10-31/10 (# COMPORTAMENTO ANTIGO)."""
    g = client.get("/api/agenda/grade", headers=auth(full)).json()
    assert g["semana_inicio"] == "2026-10-26" and g["hoje"] == "2026-10-25"
    # com semana explícita não troca
    g2 = client.get("/api/agenda/grade", params={"semana": "2026-10-25"}, headers=auth(full)).json()
    assert g2["semana_inicio"] == "2026-10-19"


def test_grade_marca_o_dia_de_hoje(client, aula_cheia, full, monkeypatch):
    monkeypatch.setattr(routes, "_agora", lambda: datetime(2026, 10, 28, 15, 0, tzinfo=UTC))
    g = client.get("/api/agenda/grade", headers=auth(full)).json()
    assert [d["hoje"] for d in g["dias"]] == [False, False, True, False, False, False]


# ----------------------------------------------------------------------------------------------------- painel
def painel(client, token, **params):
    r = client.get("/api/aulas/painel", params={"data": "2026-10-26", "periodo": "hoje", **params}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_painel_agrupa_por_horario_profissional_e_alunos(client, db, aula_cheia, full):
    p = painel(client, full)
    assert p["data_inicio"] == p["data_fim"] == "2026-10-26" and p["total"] == 3 and p["periodo"] == "hoje"
    assert len(p["dias"]) == 1
    dia = p["dias"][0]
    assert dia["total"] == 3 and len(dia["horarios"]) == 1
    h = dia["horarios"][0]
    assert h["hora_inicio"] == "09:00" and h["hora_fim"] == "09:50" and h["total"] == 3
    assert [g["nome"] for g in h["profissionais"]] == ["Carla Mendes", "Natalia Souza"]  # ordem alfabética
    carla, natalia = h["profissionais"]
    assert carla["iniciais"] == "CM" and carla["total"] == 1 and natalia["total"] == 2 and natalia["cor_indice"] == 1
    assert [c["aluno"]["nome"] for c in natalia["cartoes"]] == ["Ana Paula", "Bruna Lima"]


def test_painel_cartao_tem_plano_servicos_indicadores(client, db, aula_cheia, full):
    from app.modules.contratos.models import Contrato

    plano = fabrica.plano_avulso(db, aula_cheia.srv, nome="Pilates 2x", avulso=False)
    db.add(Contrato(aluno_id=aula_cheia.a1.id, plano_id=plano.id, unidade_id=aula_cheia.un.id, profissional_id=aula_cheia.prof.id,
                    valor_aula=Decimal("37.50"), valor_parcela=Decimal("300"), valor_total=Decimal("900"),
                    data_inicio=date(2026, 10, 1), data_fim=date(2026, 12, 31)))
    outro = fabrica.servico(db, "Alongamento")
    fabrica.funcionamento(db, aula_cheia.un, dias=(0,), servicos=[aula_cheia.srv, outro])
    db.commit()
    c = painel(client, full)["dias"][0]["horarios"][0]["profissionais"][1]["cartoes"][0]
    assert c["aluno"]["nome"] == "Ana Paula" and c["aluno"]["iniciais"] == "AP" and c["aluno"]["telefone"] == "5511999990000"
    assert c["plano"]["descricao"] == "Pilates 2x"
    assert c["servicos"] == ["Pilates", "Alongamento"] and c["servico"] == "Pilates"
    assert c["status"] == "RESERVADA" and c["status_aula"] == "aguardando_chegar" and c["rotulo_status"] == "Aguardando"
    assert c["confirmacao"] is True and c["flags"]["tem_preliminares"] is False
    assert c["whatsapp"]["disponivel"] is False  # ponto de extensão desabilitado
    assert c["ultima_evolucao"] == {"texto": None, "criado_em": None}
    assert {"id", "aula_sessao_id", "hora_inicio", "dt_inicio", "unidade", "profissional"} <= set(c)
    bruna = painel(client, full)["dias"][0]["horarios"][0]["profissionais"][1]["cartoes"][1]
    assert bruna["confirmacao"] is False and bruna["plano"]["descricao"] is None


def test_painel_status_em_aula_vem_do_dominio(client, db, aula_cheia, full, monkeypatch):
    monkeypatch.setattr(routes, "_agora", lambda: datetime(2026, 10, 26, 12, 30, tzinfo=UTC))  # 09:30 em Brasília
    c = painel(client, full)["dias"][0]["horarios"][0]["profissionais"][1]["cartoes"][0]
    assert c["status_aula"] == "em_aula" and c["rotulo_status"] == "Em aula"
    assert painel(client, full, status_aula="finalizada")["total"] == 0
    assert painel(client, full, status_aula="em_aula")["total"] == 3


def test_painel_filtros(client, db, aula_cheia, full):
    assert painel(client, full, profissional_id=aula_cheia.p2.id)["total"] == 1
    assert painel(client, full, unidade_id=999)["total"] == 0
    assert painel(client, full, q="bruna")["total"] == 1
    assert painel(client, full, q="Diana")["total"] == 1
    assert painel(client, full, q=aula_cheia.a1.cpf)["total"] == 1  # CPF
    assert painel(client, full, q="988887777")["total"] == 1  # telefone
    assert painel(client, full, q="zzz")["total"] == 0
    assert painel(client, full, q="%")["total"] == 0  # curinga do LIKE é escapado


def test_painel_periodos(client, db, aula_cheia, full):
    amanha = painel(client, full, data="2026-10-25", periodo="amanha")
    assert amanha["data_inicio"] == "2026-10-26" and amanha["total"] == 3
    semana = painel(client, full, data="2026-10-25", periodo="semana")  # domingo -> próxima semana
    assert (semana["data_inicio"], semana["data_fim"]) == ("2026-10-26", "2026-11-01") and semana["total"] == 3
    assert painel(client, full, data="2026-10-28", periodo="semana")["data_inicio"] == "2026-10-26"
    assert painel(client, full, data="2026-10-27")["total"] == 0
    assert client.get("/api/aulas/painel", params={"periodo": "ano"}, headers=auth(full)).status_code == 422


def test_painel_semana_agrupa_por_dia(client, db, aula_cheia, full):
    fabrica.reserva_direta(db, aula_cheia.a1, fabrica.sessao(db, aula_cheia.un, aula_cheia.srv, aula_cheia.prof, dia=date(2026, 10, 28), inicio=time(7, 0)))
    db.commit()
    dias = painel(client, full, periodo="semana")["dias"]
    assert [d["data"] for d in dias] == ["2026-10-26", "2026-10-28"] and dias[1]["rotulo"] == "Qua, 28/10"


def test_painel_aula_sem_profissional(client, db, cenario, full):
    ses = fabrica.sessao(db, cenario.un, cenario.srv, None, inicio=time(16, 0))
    fabrica.reserva_direta(db, cenario.a1, ses)
    db.commit()
    g = painel(client, full)["dias"][0]["horarios"][0]["profissionais"][0]
    assert g["nome"] == "Sem profissional" and g["profissional_id"] is None


def test_cobranca_pendente_so_para_quem_ve_financeiro(client, db, aula_cheia, full, secretaria, professor):
    db.add(ContaReceber(aluno_id=aula_cheia.a1.id, status=StatusReceber.ABERTO, valor=Decimal("100"), vencimento=date(2026, 10, 10)))
    db.commit()

    def flag(token):
        p = painel(client, token)
        cartoes = [c for h in p["dias"][0]["horarios"] for g in h["profissionais"] for c in g["cartoes"] if c["aluno"]["nome"] == "Ana Paula"]
        return p["pode_ver_cobranca"], cartoes[0]["flags"]["cobranca_pendente"] if cartoes else "sem cartão"

    assert flag(full) == (True, True)
    assert flag(secretaria) == (True, True)
    assert flag(professor) == (False, None)  # Professor nem recebe o campo calculado
    # quem não tem cobrança pendente
    p = painel(client, full)
    bruna = next(c for h in p["dias"][0]["horarios"] for g in h["profissionais"] for c in g["cartoes"] if c["aluno"]["nome"] == "Bruna Lima")
    assert bruna["flags"]["cobranca_pendente"] is False


def test_ultima_evolucao_aparece_no_cartao(client, db, aula_cheia, full):
    client.post(f"/api/aulas/reservas/{aula_cheia.r1.id}/evolucao", json={"texto": "Sentiu dor <b>lombar</b>"}, headers=auth(full))
    c = painel(client, full)["dias"][0]["horarios"][0]["profissionais"][1]["cartoes"][0]
    assert c["ultima_evolucao"]["texto"] == "Sentiu dor <b>lombar</b>"  # texto bruto: o escape é feito na tela


def test_detalhe_da_gaveta_traz_permissoes_do_usuario(client, aula_cheia, full, secretaria, professor):
    rid = aula_cheia.r1.id
    d = client.get(f"/api/aulas/reservas/{rid}", headers=auth(full)).json()
    assert d["aluno"]["nome"] == "Ana Paula" and all(d["permite"].values())
    prof = client.get(f"/api/aulas/reservas/{rid}", headers=auth(professor)).json()
    assert prof["permite"] == {"chegou": True, "finalizar": True, "faltou": True, "remarcar": False, "desmarcar": False, "excluir": False,
                               "confirmar": False, "evolucao": True, "avaliacao": True, "cobranca": False}
    assert prof["flags"]["cobranca_pendente"] is None


def test_gaveta_historico_e_cobranca(client, db, aula_cheia, full, professor):
    rid = aula_cheia.r1.id
    db.add(ContaReceber(aluno_id=aula_cheia.a1.id, status=StatusReceber.ABERTO, valor=Decimal("100"), vencimento=date(2026, 10, 10), descricao="Mensalidade"))
    db.add(ContaReceber(aluno_id=aula_cheia.a1.id, status=StatusReceber.ABERTO, valor=Decimal("100"), vencimento=date(2026, 12, 10)))
    db.commit()
    h = client.get(f"/api/aulas/reservas/{rid}/historico", headers=auth(full)).json()["itens"]
    assert h[0]["data"] == "2026-10-26" and h[0]["status_aula"] == "aguardando_chegar"
    c = client.get(f"/api/aulas/reservas/{rid}/cobranca", headers=auth(full)).json()["itens"]
    assert [x["vencimento"] for x in c] == ["2026-12-10", "2026-10-10"]
    assert c[1]["status"] == "ATRASADO" and c[0]["status"] == "ABERTO"  # ATRASADO derivado pelo domínio (hoje = 25/10)
    assert client.get(f"/api/aulas/reservas/{rid}/cobranca", headers=auth(professor)).status_code == 403
