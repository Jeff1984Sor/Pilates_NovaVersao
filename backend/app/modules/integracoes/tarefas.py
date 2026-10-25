"""Tarefa periódica do worker: sincronização do TotalPass (por unidade, só se `sync_ativo`; DESLIGADA por padrão)."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.db import SessionLocal, agora
from app.domain.financeiro import hoje_de_negocio
from app.modules.integracoes import totalpass
from app.modules.integracoes.models import TotalpassConfig
from app.worker import registrar_tarefa

log = logging.getLogger(__name__)
INTERVALO_S = 15 * 60


def sincronizar_agendado() -> int:
    """Sincroniza o dia de hoje de cada unidade com a sincronização ligada. Devolve quantas rodaram."""
    rodou = 0
    with SessionLocal() as db:
        ids = list(db.scalars(select(TotalpassConfig.id).where(TotalpassConfig.ativo.is_(True), TotalpassConfig.sync_ativo.is_(True))))
        for cid in ids:
            cfg = db.get(TotalpassConfig, cid)
            if cfg is None:
                continue
            try:
                resumo = totalpass.sincronizar_dia(db, cfg, hoje_de_negocio(agora()))
                totalpass.registrar_sync(db, cfg, totalpass.resumo_texto(resumo))
            except totalpass.ErroTotalpass as e:
                db.rollback()
                totalpass.registrar_sync(db, cfg, f"Erro: {e}")
            except Exception:  # noqa: BLE001 - uma unidade com problema não derruba as outras
                db.rollback()
                log.exception("Sincronização do TotalPass falhou (config %s)", cid)
                totalpass.registrar_sync(db, cfg, "Erro inesperado na sincronização.")
            rodou += 1
    return rodou


registrar_tarefa("totalpass-sincronizar", INTERVALO_S, lambda: sincronizar_agendado() and None)
