"""Fixtures da IA de cadastro: cliente de IA FALSO (nunca chama a OpenAI), IA configurada e arquivos sintéticos."""

import pytest

from app.core import ia
from app.core.segredos import cifrar_texto
from app.modules import registrar_modelos
from app.modules.ia_cadastro import cliente as cli

registrar_modelos()

CPF_VALIDO = "52998224725"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 32


class ClienteFalso:
    """Guarda as chamadas e devolve a resposta combinada (dict) ou levanta o erro combinado."""

    def __init__(self):
        self.resposta: dict = {}
        self.erro: Exception | None = None
        self.chamadas: list[dict] = []

    def extrair(self, provedor, sistema, usuario, mime, conteudo):
        self.chamadas.append({"provedor": provedor.nome, "modelo": provedor.modelo, "mime": mime, "bytes": len(conteudo), "sistema": sistema})
        if self.erro:
            raise self.erro
        return dict(self.resposta)


@pytest.fixture(autouse=True)
def falso():
    antigo = cli._cliente
    f = ClienteFalso()
    cli.definir_cliente(f)
    yield f
    cli.definir_cliente(antigo)


@pytest.fixture
def ia_pronta(db):
    cfg = ia.config(db)
    cfg.ativo, cfg.provedor, cfg.modelo, cfg.chave_cifrada = True, "openai", "gpt-4o-mini", cifrar_texto("sk-chave-de-teste-1234")
    db.commit()


@pytest.fixture
def full(client, db):
    from tests.conftest import criar_usuario, entrar

    criar_usuario(db, "Full", email="full@exemplo.com")
    return entrar(client, "full@exemplo.com").json()["access_token"]


def enviar(client, token, caminho, nome="doc.png", conteudo=PNG, tipo="image/png"):
    from tests.conftest import auth

    return client.post(f"/api/ia/cadastro/{caminho}", files={"arquivo": (nome, conteudo, tipo)}, headers=auth(token))


@pytest.fixture
def cenario_aluno(db):
    """Access token de um aluno do app (para provar que não abre rota da equipe)."""
    from app.modules.app_aluno import servico as app_srv
    from tests.agenda import fabrica

    un = fabrica.unidade(db)
    a = fabrica.aluno(db, un, "Aluna Teste")
    db.commit()
    return app_srv.emitir_tokens(a.id)["access_token"]
