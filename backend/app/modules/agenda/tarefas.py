"""Tarefas periódicas da agenda (rodam no worker, nunca como efeito de abrir uma tela)."""

import logging

from app.core import audit
from app.core.db import SessionLocal
from app.modules.agenda import servico
from app.worker import registrar_tarefa

log = logging.getLogger("agenda.tarefas")

#: a cada 5 minutos (R6)
INTERVALO_CONCLUSAO_S = 300


def concluir_aulas_passadas() -> int:
    """R6: RESERVADA/PENDENTE com a aula já encerrada viram CONCLUIDA. Idempotente. Devolve quantas mudaram."""
    with SessionLocal() as db:
        try:
            total = servico.concluir_aulas_passadas(db)
            if total:
                audit.registrar(
                    db,
                    usuario=None,
                    acao="aula.concluir_automatico",
                    entidade="reserva",
                    descricao=f"{total} aula(s) concluída(s) automaticamente (R6)",
                    depois={"total": total},
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
    if total:
        log.info("R6: %d reserva(s) concluída(s) automaticamente", total)
    return total


registrar_tarefa("agenda-concluir-aulas-passadas", INTERVALO_CONCLUSAO_S, concluir_aulas_passadas)
