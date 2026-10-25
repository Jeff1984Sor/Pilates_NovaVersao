"""Fábricas de dados sintéticos para os testes da agenda (nada de dado real)."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import count

from app.core.db import agora
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, AlunoTelefone
from app.modules.cadastros.models import (
    BloqueioAgenda,
    HorarioFuncionamento,
    Plano,
    Profissional,
    Recorrencia,
    TipoServico,
    Unidade,
)

_cpf = count(10000000001)


def unidade(db, nome="Matriz", capacidade=2, duracao=50) -> Unidade:
    u = Unidade(nome=nome, capacidade=capacidade, duracao_aula_minutos=duracao)
    db.add(u)
    db.flush()
    return u


def servico(db, nome="Pilates") -> TipoServico:
    s = TipoServico(nome=nome)
    db.add(s)
    db.flush()
    return s


def profissional(db, nome="Natalia Souza", usuario_id=None) -> Profissional:
    p = Profissional(nome=nome, usuario_id=usuario_id)
    db.add(p)
    db.flush()
    return p


def aluno(db, un: Unidade, nome="Maria Aluna", telefone="5511999990000", termo=False) -> Aluno:
    a = Aluno(nome=nome, cpf=str(next(_cpf)), unidade_id=un.id, termo_aceite_em=agora() if termo else None)
    db.add(a)
    db.flush()
    if telefone:
        db.add(AlunoTelefone(aluno_id=a.id, ordem=1, numero=telefone))
        db.flush()
    return a


def sessao(db, un, srv, prof=None, dia=date(2026, 10, 26), inicio=time(9, 0), fim=None, capacidade=None) -> AulaSessao:
    fim = fim or (datetime.combine(dia, inicio) + timedelta(minutes=50)).time()
    s = AulaSessao(
        unidade_id=un.id,
        tipo_servico_id=srv.id,
        profissional_id=prof.id if prof else None,
        data=dia,
        hora_inicio=inicio,
        hora_fim=fim,
        capacidade=capacidade,
        reservas_ativas=0,
    )
    db.add(s)
    db.flush()
    return s


def plano_avulso(db, srv, valor="80.00", recorrencia=Recorrencia.SEMANAL, avulso=True, nome="Aula avulsa") -> Plano:
    p = Plano(
        nome=nome,
        tipo_servico_id=srv.id,
        valor=Decimal(valor),
        aulas_por_semana=1,
        duracao_meses=1,
        recorrencia=recorrencia,
        avulso=avulso,
    )
    db.add(p)
    db.flush()
    return p


def funcionamento(db, un, dias=(0, 1, 2, 3, 4), inicio=time(8, 0), fim=time(12, 0), servicos=()) -> list[HorarioFuncionamento]:
    out = []
    for d in dias:
        h = HorarioFuncionamento(unidade_id=un.id, dia_semana=d, hora_inicio=inicio, hora_fim=fim, ativo=True)
        h.tipos_servico = list(servicos)
        db.add(h)
        out.append(h)
    db.flush()
    return out


def bloqueio(db, un, dia: date, inicio=time(8, 0), fim=time(18, 0), prof=None) -> BloqueioAgenda:
    b = BloqueioAgenda(
        unidade_id=un.id,
        profissional_id=prof.id if prof else None,
        data_inicio=dia,
        data_fim=dia,
        hora_inicio=inicio,
        hora_fim=fim,
        recorrente=False,
        ativo=True,
    )
    db.add(b)
    db.flush()
    return b


def reserva_direta(db, al, ses, status=StatusReserva.RESERVADA) -> Reserva:
    """Cria a reserva pela porta do serviço (mantém o contador de vagas coerente)."""
    from app.modules.agenda import servico

    return servico.criar_reserva(db, al.id, ses.id, status=status)
