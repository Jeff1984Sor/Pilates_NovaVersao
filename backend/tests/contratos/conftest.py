"""Fixtures dos contratos: cenário sintético (nada de dado real), relógio congelado e tokens por perfil."""

from __future__ import annotations

import base64
import struct
import zlib
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules import registrar_modelos

registrar_modelos()

from app.modules.alunos.models import Aluno, AlunoEndereco, AlunoTelefone  # noqa: E402
from app.modules.cadastros.models import (  # noqa: E402
    HorarioFuncionamento,
    ModeloContrato,
    Plano,
    Profissional,
    TermoUso,
    TipoServico,
    Unidade,
)
from tests.conftest import criar_usuario, entrar  # noqa: E402

#: "hoje" congelado: domingo, 25/10/2026
HOJE = date(2026, 10, 25)

MODELO_HTML = (
    "<h2>CONTRATO Nº {CONTRATO_NUMERO}</h2>"
    "<p style=\"text-align:justify\">Aluno(a) <strong>{ALUNO_NOME}</strong>, CPF {ALUNO_CPF}, contrata o plano <em>{PLANO_NOME}</em>.</p>"
    "<ul><li>Início: {CONTRATO_INICIO}</li><li>Fim: {CONTRATO_FIM}</li></ul>"
    "<p>Parcela: {CONTRATO_VALOR_PARCELA} / Total: {CONTRATO_VALOR_TOTAL}</p>"
)


def cpf_valido(base: int) -> str:
    d = [int(c) for c in f"{base:09d}"]
    for _ in range(2):
        s = sum(v * w for v, w in zip(d, range(len(d) + 1, 1, -1), strict=False))
        d.append((s * 10 % 11) % 10)
    return "".join(map(str, d))


def png_data_url(largura: int = 40, altura: int = 16) -> str:
    """PNG pequeno VÁLIDO (traço preto sobre transparente), sem depender de Pillow."""

    def chunk(tipo: bytes, dados: bytes) -> bytes:
        c = struct.pack(">I", len(dados)) + tipo + dados
        return c + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    linhas = b"".join(b"\x00" + (b"\x00\x00\x00\xff" * largura if y == altura // 2 else b"\x00\x00\x00\x00" * largura) for y in range(altura))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(linhas)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    from app.modules.contratos import servico

    monkeypatch.setattr(servico, "_hoje", lambda hoje=None: hoje or HOJE)


@pytest.fixture(autouse=True)
def _sem_enviador_whatsapp():
    from app.modules.contratos import servico

    antigo = servico._enviador_whatsapp
    servico.definir_enviador_whatsapp(None)
    yield
    servico.definir_enviador_whatsapp(antigo)


@pytest.fixture
def cen(db) -> SimpleNamespace:
    """Unidade com 4 vagas, serviço, duas professoras, horário seg-sex 8h-12h, plano 2x/semana (300,00 · 3 meses) com modelo."""
    un = Unidade(nome="Matriz", capacidade=4, duracao_aula_minutos=50)
    srv = TipoServico(nome="Pilates")
    db.add_all([un, srv])
    db.flush()
    modelo = ModeloContrato(nome="Padrão", conteudo_html=MODELO_HTML)
    db.add(modelo)
    db.flush()
    plano = Plano(nome="Pilates 2x", tipo_servico_id=srv.id, valor=Decimal("300.00"), aulas_por_semana=2, duracao_meses=3,
                  modelo_contrato_id=modelo.id)
    avulso = Plano(nome="Aula avulsa", tipo_servico_id=srv.id, valor=Decimal("80.00"), aulas_por_semana=1, duracao_meses=1, avulso=True)
    p1 = Profissional(nome="Natalia Souza")
    p2 = Profissional(nome="Bia Prado")
    db.add_all([plano, avulso, p1, p2])
    db.flush()
    for dia in range(5):
        db.add(HorarioFuncionamento(unidade_id=un.id, dia_semana=dia, hora_inicio=time(8, 0), hora_fim=time(12, 0), ativo=True))
    aluno = Aluno(nome="Maria da Silva Souza", cpf=cpf_valido(100000001), unidade_id=un.id, email="maria@exemplo.com.br", rg="123456")
    outro = Aluno(nome="João Lima", cpf=cpf_valido(100000002), unidade_id=un.id)
    db.add_all([aluno, outro])
    db.flush()
    db.add_all([AlunoTelefone(aluno_id=aluno.id, ordem=1, numero="5511999990000"),
                AlunoEndereco(aluno_id=aluno.id, logradouro="Rua das Flores", numero="120", cep="01000000", cidade="São Paulo", bairro="Centro")])
    db.add(TermoUso(nome="Termo de imagem", conteudo_html="<p>Eu, {ALUNO_NOME}, autorizo o uso da minha imagem.</p>"))
    db.commit()
    return SimpleNamespace(un=un, srv=srv, plano=plano, avulso=avulso, p1=p1, p2=p2, aluno=aluno, outro=outro, modelo=modelo)


def _token(client, db, perfil, email):
    criar_usuario(db, perfil, email=email)
    return entrar(client, email).json()["access_token"]


@pytest.fixture
def full(client, db):
    return _token(client, db, "Full", "full@exemplo.com")


@pytest.fixture
def secretaria(client, db):
    return _token(client, db, "Secretária", "sec@exemplo.com")


@pytest.fixture
def professor(client, db):
    return _token(client, db, "Professor", "prof@exemplo.com")


def cabecalho(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def novo_contrato(client, full, cen):
    """Cria um contrato pela API (início 02/11/2026, segunda) e devolve o JSON de `ContratoCriado`."""

    def _criar(**extra):
        corpo = {"aluno_id": cen.aluno.id, "plano_id": cen.plano.id, "unidade_id": cen.un.id, "profissional_id": cen.p1.id,
                 "data_inicio": "2026-11-02", "forma_pagamento": "PIX", **extra}
        r = client.post("/api/contratos", json=corpo, headers=cabecalho(full))
        assert r.status_code == 201, r.text
        return r.json()

    return _criar
