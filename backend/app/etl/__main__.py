"""Linha de comando do ETL.

    uv run python -m app.etl --origem <url do banco antigo> --destino <url do banco novo> \\
        [--simular] [--midia-origem <pasta> --midia-destino <pasta>] --relatorio saida.md

A MASTER_KEY (cifra dos segredos de integração) vem da variável de ambiente MASTER_KEY ou de --master-key.
Código de saída: 0 = conciliação OK; 1 = divergência sem justificativa ou erro; 2 = uso incorreto.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.etl.carga import Carga
from app.etl.fonte import Fonte


def _url(valor: str) -> str:
    """Aceita URL SQLAlchemy ou um caminho de arquivo .sqlite/.db."""
    if "://" in valor:
        if valor.startswith("postgres://"):
            return valor.replace("postgres://", "postgresql+psycopg://", 1)
        if valor.startswith("postgresql://"):
            return valor.replace("postgresql://", "postgresql+psycopg://", 1)
        return valor
    return "sqlite:///" + Path(valor).resolve().as_posix()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.etl", description="ETL do Pilates (Django -> esquema novo)")
    p.add_argument("--origem", required=True, help="URL (ou arquivo .sqlite) do banco ANTIGO; só leitura")
    p.add_argument("--destino", required=True, help="URL (ou arquivo .sqlite) do banco NOVO")
    p.add_argument("--simular", action="store_true", help="não grava nada (transação desfeita; mídia não é copiada)")
    p.add_argument("--midia-origem", type=Path, help="pasta media/ do sistema antigo")
    p.add_argument("--midia-destino", type=Path, help="pasta do storage do sistema novo")
    p.add_argument("--relatorio", type=Path, required=True, help="arquivo .md do relatório (grava também .json ao lado)")
    p.add_argument("--master-key", default=os.environ.get("MASTER_KEY"), help="chave Fernet; padrão: variável MASTER_KEY")
    p.add_argument("--criar-esquema", action="store_true", help="cria as tabelas (create_all) se o destino estiver vazio; só para ensaios")
    p.add_argument("--semente", type=int, default=20261025, help="semente da amostra aleatória")
    a = p.parse_args(argv)

    if not a.master_key:
        from app.core.config import settings

        a.master_key = settings.master_key
        print("AVISO: MASTER_KEY não informada; usando a do ambiente do app (em prod/hml precisa ser a real).", file=sys.stderr)
    if bool(a.midia_origem) != bool(a.midia_destino) and not a.simular:
        p.error("--midia-origem e --midia-destino devem ser usados juntos")

    fonte = Fonte(_url(a.origem))
    carga = Carga(
        fonte, _url(a.destino), master_key=a.master_key, simular=a.simular, midia_origem=a.midia_origem, midia_destino=a.midia_destino,
        semente_amostra=a.semente, criar_esquema=a.criar_esquema,
    )
    try:
        conc = carga.executar()
    except Exception as e:  # noqa: BLE001
        conc = carga.conc
        print(f"ERRO: {e}", file=sys.stderr)
    finally:
        fonte.fechar()
    a.relatorio.parent.mkdir(parents=True, exist_ok=True)
    a.relatorio.write_text(conc.markdown(), encoding="utf-8")
    a.relatorio.with_suffix(".json").write_text(conc.json(), encoding="utf-8")
    print(f"Relatório: {a.relatorio} (+ .json) — {'OK' if conc.ok else 'FALHOU'}")
    for d in conc.divergencias[:20]:
        print(" -", d, file=sys.stderr)
    return 0 if conc.ok else 1


if __name__ == "__main__":
    sys.exit(main())
