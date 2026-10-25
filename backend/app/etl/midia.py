"""Cópia dos arquivos de mídia (fotos, assinaturas, documentos, comprovantes) com verificação de hash."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.etl.transformacoes import sha256_arquivo


class Midia:
    """Registra os arquivos referenciados pelo banco e os copia para o storage novo.

    Sem `origem` configurada, a mídia não é verificada (o relatório avisa). Em `simular` só confere a existência
    e o hash do arquivo de origem, sem copiar nada.
    """

    def __init__(self, origem: Path | None, destino: Path | None, simular: bool):
        self.origem = origem
        self.destino = destino
        self.simular = simular
        self.itens: dict[str, str] = {}  # destino_rel -> origem_rel
        self.contexto: dict[str, str] = {}
        self.copiados = 0
        self.ja_iguais = 0
        self.ausentes: list[dict] = []
        self.divergentes: list[dict] = []
        self.hashes: dict[str, str] = {}  # destino_rel -> sha256

    @property
    def ativa(self) -> bool:
        return self.origem is not None

    def registrar(self, origem_rel: str | None, destino_rel: str | None, contexto: str) -> str | None:
        """Registra um arquivo e devolve o sha256 (ou None se ausente/sem verificação)."""
        if not origem_rel or not destino_rel:
            return None
        if destino_rel in self.itens:
            return self.hashes.get(destino_rel)
        self.itens[destino_rel] = origem_rel
        self.contexto[destino_rel] = contexto
        if not self.ativa:
            return None
        src = (self.origem / origem_rel.replace("\\", "/")).resolve()
        if self.origem.resolve() not in src.parents or not src.is_file():
            self.ausentes.append({"arquivo": origem_rel, "uso": contexto})
            return None
        h = sha256_arquivo(src)
        self.hashes[destino_rel] = h
        if self.simular or self.destino is None:
            return h
        alvo = (self.destino / destino_rel).resolve()
        if self.destino.resolve() not in alvo.parents:
            self.divergentes.append({"arquivo": destino_rel, "motivo": "caminho fora do storage"})
            return h
        if alvo.is_file() and sha256_arquivo(alvo) == h:
            self.ja_iguais += 1
            return h
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, alvo)
        if sha256_arquivo(alvo) != h:
            self.divergentes.append({"arquivo": destino_rel, "motivo": "hash diferente após a cópia"})
        else:
            self.copiados += 1
        return h
