"""Fixtures dos testes de alunos: dados sintéticos (nenhum dado real) e resolvedor de profissional de teste."""

import base64
import struct
import zlib
from datetime import date, time

import pytest

from app.core import escopo
from app.core.models import PerfilAcesso
from app.modules import registrar_modelos
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.cadastros.models import Profissao, Profissional, TermoUso, TipoServico, Unidade
from tests.conftest import auth, criar_usuario, entrar

registrar_modelos()

# CPFs sintéticos válidos
CPF_A = "529.982.247-25"
CPF_B = "111.444.777-35"
CPF_C = "390.533.447-05"


def png_bytes(w: int = 4, h: int = 4) -> bytes:
    """PNG mínimo válido gerado na hora."""
    def chunk(tipo: bytes, dados: bytes) -> bytes:
        c = struct.pack(">I", len(dados)) + tipo + dados
        return c + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def data_url_png() -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes()).decode()


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def base(db):
    un = Unidade(nome="Unidade Teste", capacidade=4)
    db.add_all([un, Profissao(nome="Engenheira"), TermoUso(nome="Termo de imagem", conteudo_html="<p>Eu, {ALUNO_NOME}, CPF {ALUNO_CPF}, autorizo. <script>x</script></p>")])
    db.commit()
    return {"unidade_id": un.id, "profissao_id": db.query(Profissao).first().id, "termo_id": db.query(TermoUso).first().id}


@pytest.fixture
def h(token_admin):
    return auth(token_admin)


def corpo(base, **extra):
    d = {"nome": "Maria Teste", "cpf": CPF_A, "unidade_id": base["unidade_id"]}
    d.update(extra)
    return d


@pytest.fixture
def criar(client, h, base):
    def _criar(**extra):
        r = client.post("/api/alunos", json=corpo(base, **extra), headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    return _criar


@pytest.fixture
def professor(db, client):
    """Professor (perfil padrão, sem alunos.ver) e Professor+ (com alunos.ver), ambos 'somente as próprias aulas'."""
    prof_usuario = criar_usuario(db, "Professor", email="prof@exemplo.com")
    prof = Profissional(nome="Prof Teste", usuario_id=prof_usuario.id)
    outro = Profissional(nome="Outro Prof")
    db.add_all([prof, outro])
    db.commit()
    mapa = {prof_usuario.id: prof.id}
    antigo = escopo._resolvedor
    escopo.registrar_resolvedor_profissional(lambda _db, u: mapa.get(u.id))
    yield {"usuario": prof_usuario, "profissional_id": prof.id, "outro_id": outro.id, "mapa": mapa}
    escopo.registrar_resolvedor_profissional(antigo)


@pytest.fixture
def token_professor(client, professor):
    return entrar(client, "prof@exemplo.com").json()["access_token"]


@pytest.fixture
def token_professor_mais(client, db, professor):
    """Professor com alunos.ver (a lista/ficha completa), ainda restrito às próprias aulas."""
    p = PerfilAcesso(nome="Professor+", permissoes=["alunos.ver", "aulas.ver", "aulas.evoluir", "aulas.avaliar"], somente_proprias_aulas=True)
    db.add(p)
    db.flush()
    u = criar_usuario(db, "Professor", email="prof2@exemplo.com")
    u.perfil_acesso_id = p.id
    db.commit()
    professor["mapa"][u.id] = professor["profissional_id"]
    return entrar(client, "prof2@exemplo.com").json()["access_token"]


@pytest.fixture
def reservar(db, base):
    """Cria uma reserva do aluno numa aula do profissional informado."""
    servico = TipoServico(nome="Pilates solo")
    db.add(servico)
    db.commit()
    contador = {"n": 0}

    def _reservar(aluno_id: int, profissional_id: int):
        contador["n"] += 1
        s = AulaSessao(unidade_id=base["unidade_id"], tipo_servico_id=servico.id, profissional_id=profissional_id,
                       data=date(2026, 11, 2), hora_inicio=time(8 + contador["n"], 0), hora_fim=time(9 + contador["n"], 0), capacidade=4)
        db.add(s)
        db.flush()
        r = Reserva(aluno_id=aluno_id, aula_sessao_id=s.id)
        db.add(r)
        db.commit()
        return r

    return _reservar
