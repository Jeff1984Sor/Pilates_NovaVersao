"""Zera os dados de teste antes de colocar um ambiente no ar. **Mantém usuários, perfis, identidade e configurações.**

    uv run python -m app.limpar_dados --confirmar "LIMPAR TUDO" [--manter tabela1,tabela2]

A lista de tabelas vem dos METADADOS dos models (todas as tabelas registradas, em ordem segura de chaves estrangeiras),
nunca de uma lista manual: tabela nova de qualquer módulo entra sozinha. São MANTIDAS as tabelas do core
(`usuario`, `perfil_acesso`, `identidade`, `config_email`, `config_ia`) e `alembic_version`; use --manter para poupar
outras (ex.: cadastros de unidades e planos). Os arquivos do storage também são apagados, exceto fotos e identidade.

A auditoria é imutável no sistema; aqui ela é zerada uma única vez, de propósito, e a própria limpeza fica registrada
como o primeiro evento. Recusa rodar em prod.
"""

import argparse
import shutil
import sys

from sqlalchemy import delete, func, select

import app.modules as modulos_pkg
from app.core import audit
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.storage import raiz

MANTER_PADRAO = {"usuario", "perfil_acesso", "identidade", "config_email", "config_ia", "alembic_version"}
PASTAS_MANTIDAS = {"identidade", "usuarios"}


def carregar_modelos() -> None:
    """Importa os models de todos os módulos para que os metadados estejam completos."""
    import importlib
    import pkgutil

    import app.core.models  # noqa: F401

    for info in pkgutil.iter_modules(modulos_pkg.__path__):
        try:
            importlib.import_module(f"app.modules.{info.name}.models")
        except ModuleNotFoundError as e:
            if e.name != f"app.modules.{info.name}.models":
                raise


def tabelas_a_limpar(manter: set[str]) -> list:
    """Tabelas do metadata, filhos antes dos pais, menos as mantidas."""
    return [t for t in reversed(Base.metadata.sorted_tables) if t.name not in (MANTER_PADRAO | manter)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirmar", default="", help='digite exatamente: "LIMPAR TUDO"')
    ap.add_argument("--manter", default="", help="tabelas extras a preservar, separadas por vírgula")
    a = ap.parse_args()
    if a.confirmar != "LIMPAR TUDO":
        sys.exit('Nada foi apagado. Para confirmar: --confirmar "LIMPAR TUDO"')
    if settings.ambiente == "prod":
        sys.exit("Recusado: esta ferramenta não roda em produção.")

    carregar_modelos()
    manter = {t.strip() for t in a.manter.split(",") if t.strip()}
    contagem = {}
    with engine.begin() as conn:
        conn.info["liberar_limpeza_auditoria"] = True
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for t in tabelas_a_limpar(manter):
            contagem[t.name] = conn.execute(select(func.count()).select_from(t)).scalar()
            conn.execute(delete(t))
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.info.pop("liberar_limpeza_auditoria", None)

    removidas = []
    base = raiz()
    for item in base.iterdir():
        if item.name in PASTAS_MANTIDAS:
            continue
        removidas.append(item.name)
        shutil.rmtree(item) if item.is_dir() else item.unlink()

    with SessionLocal() as db:
        audit.registrar(db, usuario=None, acao="ambiente.limpeza", entidade="sistema",
                        descricao="Dados de teste apagados antes da entrada em operação (usuários e configurações mantidos).")
        db.commit()

    print("Apagado:")
    for nome, n in contagem.items():
        print(f"  {nome:<30} {n}")
    print(f"  arquivos: {', '.join(removidas) or 'nenhum'}")
    print(f"Mantidos: {', '.join(sorted(MANTER_PADRAO | manter))}.")


if __name__ == "__main__":
    main()
