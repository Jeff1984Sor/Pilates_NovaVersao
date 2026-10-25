"""Fixtures dos testes de dados: destino SQLite temporário (create_all) e a origem sintética versionada."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event

from app.core.db import Base
from app.modules import registrar_modelos

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ORIGEM = FIXTURES / "origem_sintetica.sqlite"
MIDIA_ORIGEM = FIXTURES / "midia_origem"


def criar_engine(url: str):
    eng = create_engine(url)

    @event.listens_for(eng, "connect")
    def _fk(conn, _):  # noqa: ANN001
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


@pytest.fixture
def master_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def engine(tmp_path):
    registrar_modelos()
    url = f"sqlite:///{(tmp_path / 'destino.sqlite').as_posix()}"
    eng = criar_engine(url)
    Base.metadata.create_all(eng)
    eng.url_texto = url  # type: ignore[attr-defined]
    yield eng
    eng.dispose()
