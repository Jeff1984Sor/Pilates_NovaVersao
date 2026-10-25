"""Leitura SOMENTE LEITURA do banco ANTIGO (Django) por SQLAlchemy Core, com reflexão das tabelas `core_*` e `auth_user`."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SAWarning

PREFIXOS = ("core_", "auth_user")


def _url_somente_leitura(url: str) -> tuple[str, dict]:
    u = make_url(url)
    if u.get_backend_name() == "sqlite":
        if not u.database or u.database == ":memory:":
            raise ValueError("A origem SQLite precisa ser um arquivo existente.")
        caminho = Path(u.database).resolve()
        if not caminho.exists():
            raise FileNotFoundError(f"Banco de origem não encontrado: {caminho}")
        return f"sqlite:///file:{caminho.as_posix()}?mode=ro&uri=true", {}
    if u.get_backend_name() == "postgresql":
        # a sessão inteira nasce read-only: o ETL não consegue alterar a origem nem por engano
        return url, {"options": "-c default_transaction_read_only=on"}
    return url, {}


class Fonte:
    """Banco antigo. Todas as leituras devolvem listas de dicts com os nomes de coluna do Django."""

    def __init__(self, url: str):
        self.rotulo = url
        url_ro, connect_args = _url_somente_leitura(url)
        self.engine: Engine = create_engine(url_ro, connect_args=connect_args)
        self.metadata = MetaData()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SAWarning)  # tipos do Django que o SQLite não reconhece (bool, etc.)
            self.metadata.reflect(self.engine, only=lambda nome, _: nome.startswith(PREFIXOS))
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def fechar(self) -> None:
        self.engine.dispose()

    # ---- acesso ----------------------------------------------------------------------------------------------------
    def existe(self, nome: str) -> bool:
        return nome in self.metadata.tables

    def tabela(self, nome: str) -> Table:
        return self.metadata.tables[nome]

    def linhas(self, nome: str) -> list[dict[str, Any]]:
        """Todas as linhas da tabela, ordenadas por `id` (cache em memória: ~17 mil linhas no total)."""
        if nome not in self._cache:
            if not self.existe(nome):
                self._cache[nome] = []
            else:
                t = self.tabela(nome)
                ordem = t.c.id if "id" in t.c else None
                q = select(t).order_by(ordem) if ordem is not None else select(t)
                with self.engine.connect() as c:
                    self._cache[nome] = [dict(r._mapping) for r in c.execute(q)]
        return self._cache[nome]

    def contar(self, nome: str) -> int:
        if not self.existe(nome):
            return 0
        with self.engine.connect() as c:
            return c.execute(select(func.count()).select_from(self.tabela(nome))).scalar_one()

    def nomes(self) -> list[str]:
        return sorted(self.metadata.tables)

    # ---- integridade referencial da origem -----------------------------------------------------------------------------
    def fks_orfas(self) -> list[dict[str, Any]]:
        """Para cada FK declarada, quantas linhas apontam para um pai inexistente (o SQLite não impõe FK)."""
        achados: list[dict[str, Any]] = []
        with self.engine.connect() as c:
            for t in self.metadata.tables.values():
                for fk in t.foreign_key_constraints:
                    col = fk.columns[0]
                    pai = list(fk.elements)[0].column
                    filho_col = t.c[col.name]
                    q = (
                        select(func.count())
                        .select_from(t.outerjoin(pai.table, filho_col == pai))
                        .where(filho_col.is_not(None), pai.is_(None))
                    )
                    n = c.execute(q).scalar_one()
                    if n:
                        achados.append({"tabela": t.name, "coluna": col.name, "pai": pai.table.name, "linhas": n})
        return achados
