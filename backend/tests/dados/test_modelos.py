"""Modelo de dados do Pilates: caso completo e violações de constraint esperadas (create_all em SQLite)."""

from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.agenda.models import AulaSessao, Evolucao, Reserva, StatusReserva, liberar_vaga, ocupar_vaga
from app.modules.alunos.models import Aluno, AlunoEndereco, AlunoTelefone
from app.modules.cadastros.models import (
    BloqueioAgenda,
    Categoria,
    Plano,
    Profissional,
    TipoCategoria,
    TipoServico,
    Unidade,
    proximo_codigo,
)
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber, StatusReceber


@pytest.fixture
def base(engine):
    """Unidade, serviço, plano e profissional já criados."""
    with Session(engine) as s:
        un = Unidade(nome="Studio", capacidade=2, duracao_aula_minutos=50)
        ts = TipoServico(nome="Pilates")
        prof = Profissional(nome="Prof", comissao_percentual=Decimal("10.00"))  # sem login: usuario_id nulo
        s.add_all([un, ts, prof])
        s.flush()
        plano = Plano(nome="2x/sem", tipo_servico_id=ts.id, valor=Decimal("300.00"), aulas_por_semana=2, duracao_meses=3)
        s.add(plano)
        s.commit()
        yield engine, {"unidade": un.id, "servico": ts.id, "prof": prof.id, "plano": plano.id}


def _aluno(s: Session, unidade_id: int, nome="Ana", cpf: str | None = "52998224725", sem_cpf=False) -> Aluno:
    a = Aluno(nome=nome, cpf=cpf, sem_cpf=sem_cpf, unidade_id=unidade_id)
    s.add(a)
    s.flush()
    return a


def _sessao(s: Session, ids: dict, dia=date(2026, 11, 3), hora=8, prof="padrao", **kw) -> AulaSessao:
    sess = AulaSessao(
        unidade_id=ids["unidade"], tipo_servico_id=ids["servico"], profissional_id=ids["prof"] if prof == "padrao" else prof,
        data=dia, hora_inicio=time(hora), hora_fim=time(hora, 50), **kw,
    )
    s.add(sess)
    s.flush()
    return sess


def test_caso_completo(base):
    engine, ids = base
    with Session(engine) as s:
        a = _aluno(s, ids["unidade"])
        s.add(AlunoEndereco(aluno_id=a.id, logradouro="Rua A", numero="1", cep="01310100", cidade="SP", bairro="Centro"))
        s.add(AlunoTelefone(aluno_id=a.id, ordem=1, numero="5511912345678"))
        c = Contrato(aluno_id=a.id, plano_id=ids["plano"], unidade_id=ids["unidade"], profissional_id=ids["prof"],
                     valor_aula=Decimal("37.50"), valor_parcela=Decimal("300.00"), valor_total=Decimal("900.00"),
                     data_inicio=date(2026, 11, 3), data_fim=date(2027, 2, 3))
        s.add(c)
        s.flush()
        for i, venc in enumerate([date(2026, 11, 3), date(2026, 12, 3), date(2027, 1, 3)]):
            s.add(ContaReceber(aluno_id=a.id, contrato_id=c.id, valor=Decimal("300.00"), vencimento=venc,
                               competencia=venc.strftime("%Y-%m")))
        sess = _sessao(s, ids)
        assert ocupar_vaga(s, sess.id)
        r = Reserva(aluno_id=a.id, aula_sessao_id=sess.id, contrato_id=c.id)
        s.add(r)
        s.flush()
        s.add(Evolucao(reserva_id=r.id, profissional_id=ids["prof"], texto="Boa sessão"))
        s.commit()

        assert s.scalar(select(ContaReceber.status).limit(1)) == StatusReceber.ABERTO
        assert s.query(ContaReceber).count() == 3
        assert s.get(Reserva, r.id).status == StatusReserva.RESERVADA
        assert s.get(AulaSessao, sess.id).reservas_ativas == 1


def test_cpf_unico_e_sem_cpf_coerente(base):
    engine, ids = base
    with Session(engine) as s:
        _aluno(s, ids["unidade"], "A", "52998224725")
        s.commit()
        with pytest.raises(IntegrityError):  # CPF único
            _aluno(s, ids["unidade"], "B", "52998224725")
        s.rollback()
        # vários alunos sem CPF convivem (NULL não colide)
        _aluno(s, ids["unidade"], "C", None, sem_cpf=True)
        _aluno(s, ids["unidade"], "D", None, sem_cpf=True)
        s.commit()
        with pytest.raises(IntegrityError):  # sem_cpf exige cpf NULL
            _aluno(s, ids["unidade"], "E", "11144477735", sem_cpf=True)
        s.rollback()
        with pytest.raises(IntegrityError):  # com CPF obrigatório se não for sem_cpf
            _aluno(s, ids["unidade"], "F", None, sem_cpf=False)


def test_reserva_unica_por_aluno_e_sessao(base):
    engine, ids = base
    with Session(engine) as s:
        a = _aluno(s, ids["unidade"])
        sess = _sessao(s, ids)
        s.add(Reserva(aluno_id=a.id, aula_sessao_id=sess.id))
        s.commit()
        s.add(Reserva(aluno_id=a.id, aula_sessao_id=sess.id))
        with pytest.raises(IntegrityError):
            s.commit()


def test_sessao_unica_inclusive_sem_profissional(base):
    engine, ids = base
    with Session(engine) as s:
        _sessao(s, ids)
        _sessao(s, ids, prof=None)
        s.commit()
        with pytest.raises(IntegrityError):  # mesma chave com profissional
            _sessao(s, ids)
        s.rollback()
        with pytest.raises(IntegrityError):  # NULL não escapa da unicidade (coalesce no índice)
            _sessao(s, ids, prof=None)
        s.rollback()
        _sessao(s, ids, hora=9)  # outro horário é permitido
        s.commit()


def test_codigo_legado_unico(base):
    engine, ids = base
    with Session(engine) as s:
        _aluno(s, ids["unidade"], "A", "52998224725").codigo_legado = 10
        s.commit()
        a2 = _aluno(s, ids["unidade"], "B", "11144477735")
        a2.codigo_legado = 10
        with pytest.raises(IntegrityError):
            s.commit()


def test_fk_e_checks(base):
    engine, ids = base
    with Session(engine) as s:
        s.add(Reserva(aluno_id=9999, aula_sessao_id=9999))
        with pytest.raises(IntegrityError):  # FK
            s.commit()
        s.rollback()
        s.add(Plano(nome="neg", tipo_servico_id=ids["servico"], valor=Decimal("-1")))
        with pytest.raises(IntegrityError):  # valor >= 0
            s.commit()
        s.rollback()
        s.add(BloqueioAgenda(unidade_id=ids["unidade"], data_inicio=date(2026, 1, 1), hora_inicio=time(10), hora_fim=time(9)))
        with pytest.raises(IntegrityError):  # hora_fim > hora_inicio
            s.commit()
        s.rollback()
        s.add(Categoria(nome="x", tipo=TipoCategoria.RECEITA))
        s.commit()


def test_capacidade_transacional(base):
    engine, ids = base  # unidade com capacidade 2
    with Session(engine) as s:
        herda = _sessao(s, ids)
        propria = _sessao(s, ids, hora=9, capacidade=1)
        zero = _sessao(s, ids, hora=10, capacidade=0)
        s.commit()
        assert ocupar_vaga(s, herda.id) and ocupar_vaga(s, herda.id)
        assert not ocupar_vaga(s, herda.id)  # lotada (herda 2 da unidade)
        assert ocupar_vaga(s, propria.id) and not ocupar_vaga(s, propria.id)
        assert not ocupar_vaga(s, zero.id)
        assert not ocupar_vaga(s, 999999)
        liberar_vaga(s, herda.id)
        assert ocupar_vaga(s, herda.id)
        liberar_vaga(s, zero.id)  # nunca fica negativo
        s.commit()
        s.refresh(zero)
        assert zero.reservas_ativas == 0


def test_contador_de_codigo(base):
    engine, _ = base
    with Session(engine) as s:
        assert [proximo_codigo(s, "aluno") for _ in range(3)] == [1, 2, 3]
        assert proximo_codigo(s, "contrato") == 1
        s.commit()
    with Session(engine) as s:
        assert proximo_codigo(s, "aluno") == 4


def test_profissional_sem_login_e_com_comissao(base):
    engine, ids = base
    with Session(engine) as s:
        p = s.get(Profissional, ids["prof"])
        assert p.usuario_id is None and p.comissao_percentual == Decimal("10.00")
        s.add(Profissional(nome="Outra", comissao_percentual=Decimal("120")))
        with pytest.raises(IntegrityError):
            s.commit()
