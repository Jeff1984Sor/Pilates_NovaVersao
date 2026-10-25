"""Fixtures do painel: relógio fixo (domingo 25/10/2026 12:00 em Brasília), usuários por perfil e um cenário numérico."""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core import escopo
from app.modules import registrar_modelos

registrar_modelos()

from app.core.models import PerfilAcesso  # noqa: E402
from app.modules.agenda import servico as agenda  # noqa: E402
from app.modules.agenda.models import Evolucao, StatusReserva, WhatsappAgendamentoLog  # noqa: E402
from app.modules.alunos.models import Aluno, StatusAluno  # noqa: E402
from app.modules.app_aluno.models import ReposicaoPedido, StatusPedido  # noqa: E402
from app.modules.cadastros.models import Plano  # noqa: E402
from app.modules.cadastros.vinculo_usuario import resolver_profissional_id  # noqa: E402
from app.modules.contratos.models import Contrato, StatusAssinatura  # noqa: E402
from app.modules.financeiro.models import ContaReceber, StatusReceber  # noqa: E402
from app.modules.integracoes.models import TotalpassEvento, WhatsappConfig  # noqa: E402
from tests.agenda import fabrica  # noqa: E402
from tests.conftest import auth, criar_usuario, entrar  # noqa: E402,F401

#: domingo 25/10/2026 12:00 em Brasília (15:00 UTC)
AGORA = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)
HOJE = date(2026, 10, 25)


@pytest.fixture(autouse=True)
def _relogio_e_resolvedor(monkeypatch):
    from app.modules.painel import routes

    monkeypatch.setattr(routes, "_agora", lambda: AGORA)
    antigo = escopo._resolvedor
    escopo.registrar_resolvedor_profissional(resolver_profissional_id)
    yield
    escopo.registrar_resolvedor_profissional(antigo)


def fixar_agora(monkeypatch, instante: datetime) -> None:
    from app.modules.painel import routes

    monkeypatch.setattr(routes, "_agora", lambda: instante)


def _token(client, db, perfil, email, **extra):
    criar_usuario(db, perfil, email=email, **extra)
    return auth(entrar(client, email).json()["access_token"])


@pytest.fixture
def full(client, db):
    return _token(client, db, "Full", "full@x.com")


@pytest.fixture
def secretaria(client, db):
    return _token(client, db, "Secretária", "sec@x.com")


def novo_professor_logado(client, db, nome="Natalia"):
    """Professor com login vinculado a um profissional. Devolve (cabeçalho, profissional)."""
    h = _token(client, db, "Professor", "prof@x.com")
    from sqlalchemy import select

    from app.core.models import Usuario

    uid = db.scalar(select(Usuario.id).where(Usuario.email == "prof@x.com"))
    p = fabrica.profissional(db, nome, usuario_id=uid)
    db.commit()
    return h, p


def mk_aluno(db, un, nome, n, nasc=None, status=StatusAluno.ATIVO):
    a = Aluno(nome=nome, cpf=f"{10000000000 + n}", unidade_id=un.id, data_nascimento=nasc, status=status)
    db.add(a)
    db.flush()
    return a


def mk_conta(db, aluno, valor, venc, status=StatusReceber.ABERTO, pago=None):
    c = ContaReceber(aluno_id=aluno.id, valor=Decimal(valor), vencimento=venc, status=status, pagamento=pago)
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def mundo(db):
    """Cenário numérico (ver cada teste para os números). `prof1` e `prof2` são profissionais; sem logins aqui."""
    un = fabrica.unidade(db, capacidade=5)
    srv = fabrica.servico(db)
    p1 = fabrica.profissional(db, "Natalia")
    p2 = fabrica.profissional(db, "Carla")
    plano = Plano(nome="Plano 2x", tipo_servico_id=srv.id, valor=Decimal("300.00"), aulas_por_semana=2, duracao_meses=3)
    db.add(plano)
    db.flush()
    a1 = mk_aluno(db, un, "Ana", 1, date(1990, 10, 25))      # aniversário hoje (36 anos)
    a2 = mk_aluno(db, un, "Bia", 2, date(1985, 10, 30))      # em 5 dias
    a3 = mk_aluno(db, un, "Caio", 3, date(1970, 11, 2))      # em 8 dias: fora da janela
    a4 = mk_aluno(db, un, "Dani", 4, date(1992, 10, 26))     # amanhã
    mk_aluno(db, un, "Inativa", 5, date(1980, 10, 25), status=StatusAluno.INATIVO)  # inativa não entra
    mk_aluno(db, un, "Sem data", 6)

    # ---- aulas
    s_hoje8 = fabrica.sessao(db, un, srv, p1, HOJE, time(8, 0))     # já terminou às 12:00
    s_hoje14 = fabrica.sessao(db, un, srv, p1, HOJE, time(14, 0))
    s_hoje16 = fabrica.sessao(db, un, srv, p2, HOJE, time(16, 0))
    s_amanha = fabrica.sessao(db, un, srv, p1, date(2026, 10, 26), time(9, 0))
    s_1010 = fabrica.sessao(db, un, srv, p2, date(2026, 10, 10), time(10, 0))
    s_0915 = fabrica.sessao(db, un, srv, p2, date(2026, 9, 15), time(10, 0))
    s_0502 = fabrica.sessao(db, un, srv, p2, date(2026, 5, 2), time(10, 0))
    s_0430 = fabrica.sessao(db, un, srv, p2, date(2026, 4, 30), time(10, 0))  # fora dos 6 meses
    R = StatusReserva
    agenda.criar_reserva(db, a3.id, s_hoje8.id)
    agenda.criar_reserva(db, a1.id, s_hoje14.id)
    agenda.criar_reserva(db, a2.id, s_hoje14.id, status=R.PENDENTE)
    agenda.criar_reserva(db, a4.id, s_hoje16.id)
    r_amanha = agenda.criar_reserva(db, a1.id, s_amanha.id)
    agenda.criar_reserva(db, a2.id, s_amanha.id, status=R.CANCELADA)
    r_sem_evol = agenda.criar_reserva(db, a1.id, s_1010.id, status=R.CONCLUIDA)
    r_com_evol = agenda.criar_reserva(db, a2.id, s_1010.id, status=R.CONCLUIDA)
    db.add(Evolucao(reserva_id=r_com_evol.id, profissional_id=p2.id, texto="Boa evolução"))
    for a in (a1, a2, a3):
        agenda.criar_reserva(db, a.id, s_0915.id, status=R.CONCLUIDA)
    agenda.criar_reserva(db, a1.id, s_0502.id, status=R.CONCLUIDA)
    agenda.criar_reserva(db, a1.id, s_0430.id, status=R.CONCLUIDA)

    # ---- financeiro
    mk_conta(db, a1, "100.00", date(2026, 10, 30))
    mk_conta(db, a1, "50.50", date(2026, 11, 5))
    mk_conta(db, a1, "70.00", HOJE)                    # vence hoje: ainda não é atraso
    mk_conta(db, a1, "200.00", date(2026, 10, 10))     # atrasada
    mk_conta(db, a2, "30.00", date(2026, 10, 24))      # atrasada
    mk_conta(db, a1, "300.00", date(2026, 10, 5), StatusReceber.PAGO, date(2026, 10, 5))
    mk_conta(db, a2, "40.00", date(2026, 10, 25), StatusReceber.PAGO, HOJE)
    mk_conta(db, a1, "250.00", date(2026, 9, 10), StatusReceber.PAGO, date(2026, 9, 10))   # até 25/09
    mk_conta(db, a2, "100.00", date(2026, 9, 28), StatusReceber.PAGO, date(2026, 9, 28))   # depois de 25/09
    mk_conta(db, a2, "999.00", date(2026, 10, 1), StatusReceber.CANCELADO)

    # ---- contratos (hoje = 25/10; 30 dias = 24/11)
    def contrato(aluno, fim, ass):
        c = Contrato(aluno_id=aluno.id, plano_id=plano.id, unidade_id=un.id, profissional_id=p1.id,
                     data_inicio=date(2026, 1, 1), data_fim=fim, status_assinatura=ass)
        db.add(c)
        return c

    contrato(a1, date(2026, 11, 10), StatusAssinatura.NAO_ASSINADO)   # vencendo e sem assinar
    contrato(a2, date(2026, 12, 5), StatusAssinatura.ASSINADO)         # 41 dias: fora
    contrato(a3, date(2026, 10, 1), StatusAssinatura.NAO_ASSINADO)     # já encerrado: não conta
    contrato(a4, date(2026, 11, 24), StatusAssinatura.ASSINADO_DIGITALMENTE)  # 30 dias: dentro

    # ---- reposições, WhatsApp e TotalPass
    db.add(ReposicaoPedido(aluno_id=a1.id, reserva_origem_id=r_amanha.id, data_origem=date(2026, 10, 26),
                           hora_origem=time(9, 0), status=StatusPedido.PENDENTE))
    db.add(ReposicaoPedido(aluno_id=a1.id, reserva_origem_id=r_sem_evol.id, data_origem=date(2026, 10, 10),
                           hora_origem=time(10, 0), status=StatusPedido.APROVADO))
    db.add(WhatsappConfig(unidade_id=un.id, credencial_cifrado="cifrado"))
    db.add(WhatsappAgendamentoLog(tipo="alerta", dedupe_key="parada:1", unidade_id=un.id, data_referencia=HOJE,
                                  mensagem="Lote interrompido", status="sessao_caida", enviado_em=AGORA))
    db.add(TotalpassEvento(recebido_em=datetime(2026, 10, 24, 15, 0, tzinfo=UTC), resultado="erro", erro="falhou", payload={}))
    db.add(TotalpassEvento(recebido_em=datetime(2026, 10, 24, 15, 0, tzinfo=UTC), resultado="processado", payload={}))
    db.add(TotalpassEvento(recebido_em=datetime(2026, 10, 1, 15, 0, tzinfo=UTC), resultado="erro", payload={}))  # antigo
    db.commit()
    return SimpleNamespace(un=un, srv=srv, p1=p1, p2=p2, plano=plano, a1=a1, a2=a2, a3=a3, a4=a4)


def criar_perfil_restrito(db, permissoes: list[str]) -> PerfilAcesso:
    p = PerfilAcesso(nome="Professor ampliado", somente_proprias_aulas=True, permissoes=permissoes)
    db.add(p)
    db.commit()
    return p
