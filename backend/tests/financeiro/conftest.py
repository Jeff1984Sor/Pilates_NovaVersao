"""Fixtures do financeiro: usuários por perfil e um cenário mínimo (unidade, plano, aluno, contrato, fornecedor...)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules import registrar_modelos
from tests.conftest import SENHA, auth, criar_usuario, entrar  # noqa: F401

registrar_modelos()

from app.modules.alunos.models import Aluno  # noqa: E402
from app.modules.cadastros.models import (  # noqa: E402
    Categoria,
    Fornecedor,
    Plano,
    Profissional,
    Subcategoria,
    TipoCategoria,
    TipoServico,
    Unidade,
)
from app.modules.contratos.models import Contrato  # noqa: E402


def cpf_valido(base: int) -> str:
    """CPF válido determinístico a partir de um número de 9 dígitos."""
    d = [int(c) for c in f"{base:09d}"]
    for _ in range(2):
        s = sum(v * w for v, w in zip(d, range(len(d) + 1, 1, -1), strict=False))
        d.append((s * 10 % 11) % 10)
    return "".join(map(str, d))


def novo_aluno(db, unidade_id: int, nome: str, n: int, **extra) -> Aluno:
    a = Aluno(nome=nome, cpf=cpf_valido(100000000 + n), unidade_id=unidade_id, **extra)
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def cenario(db) -> SimpleNamespace:
    un = Unidade(nome="Matriz", capacidade=4)
    srv = TipoServico(nome="Pilates")
    db.add_all([un, srv])
    db.flush()
    cat_r = Categoria(nome="Mensalidades", tipo=TipoCategoria.RECEITA)
    cat_d = Categoria(nome="Aluguel e contas", tipo=TipoCategoria.DESPESA)
    db.add_all([cat_r, cat_d])
    db.flush()
    sub_r = Subcategoria(categoria_id=cat_r.id, nome="Pilates mensal")
    sub_d = Subcategoria(categoria_id=cat_d.id, nome="Aluguel")
    db.add_all([sub_r, sub_d])
    db.flush()
    plano = Plano(nome="Plano 2x", tipo_servico_id=srv.id, categoria_receita_id=cat_r.id, subcategoria_receita_id=sub_r.id,
                  valor=Decimal("300.00"), aulas_por_semana=2, duracao_meses=3)
    prof = Profissional(nome="Ana Fisio", comissao_percentual=Decimal("10"))
    forn = Fornecedor(nome="Imobiliária Centro")
    db.add_all([plano, prof, forn])
    db.flush()
    aluno = novo_aluno(db, un.id, "Maria Souza", 1)
    outro = novo_aluno(db, un.id, "João Lima", 2)
    contrato = Contrato(aluno_id=aluno.id, plano_id=plano.id, unidade_id=un.id, profissional_id=prof.id,
                        data_inicio=date(2026, 1, 31), data_fim=date(2026, 4, 30), valor_aula=Decimal("37.50"),
                        valor_parcela=Decimal("300.00"), valor_total=Decimal("900.00"))
    db.add(contrato)
    db.commit()
    return SimpleNamespace(unidade=un, servico=srv, cat_r=cat_r, cat_d=cat_d, sub_r=sub_r, sub_d=sub_d, plano=plano,
                           prof=prof, forn=forn, aluno=aluno, outro=outro, contrato=contrato)


def _tk(client, db, perfil, email):
    criar_usuario(db, perfil, email=email)
    return entrar(client, email).json()["access_token"]


@pytest.fixture
def adm(client, db):
    return auth(_tk(client, db, "Full", "adm@x.com"))


@pytest.fixture
def secretaria(client, db):
    return auth(_tk(client, db, "Secretária", "sec@x.com"))


@pytest.fixture
def professor(client, db):
    return auth(_tk(client, db, "Professor", "prof@x.com"))
