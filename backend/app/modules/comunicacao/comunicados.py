"""Comunicado geral: fila de envio um a um, com pausa, progresso, pausar/retomar/cancelar e relatório.

O envio roda no worker (``processar_pendentes``, a cada 5 s): em cada passada, no máximo UMA mensagem por comunicado e só
se já passou a pausa configurada desde a anterior. O "direito de enviar" é reservado com UPDATE condicional (seguro com
mais de um worker). Sessão caída ou credencial recusada PAUSA o comunicado (nada é perdido: basta retomar).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, agora
from app.modules.alunos.models import Aluno, StatusAluno
from app.modules.comunicacao import servico as svc
from app.modules.comunicacao.models import Comunicado, ComunicadoDestinatario
from app.modules.financeiro.servico import ErroDeNegocio

log = logging.getLogger(__name__)

PUBLICOS = ("ativos", "inativos", "todos")
ESTADOS_FINAIS = ("cancelado", "concluido")
TOLERANCIA_S = 0.5
ENVIANDO_PRESO_MIN = 10


def selecionar_alunos(db: Session, publico: str, unidade_id: int | None) -> list[Aluno]:
    if publico not in PUBLICOS:
        raise ErroDeNegocio("Público inválido (use ativos, inativos ou todos).", 422)
    q = select(Aluno).order_by(Aluno.nome, Aluno.id)
    if publico == "ativos":
        q = q.where(Aluno.status == StatusAluno.ATIVO)
    elif publico == "inativos":
        q = q.where(Aluno.status == StatusAluno.INATIVO)
    if unidade_id:
        q = q.where(Aluno.unidade_id == unidade_id)
    return list(db.scalars(q))


def previa(db: Session, texto: str, publico: str, unidade_id: int | None) -> dict:
    alunos = selecionar_alunos(db, publico, unidade_id)
    com_tel = [a for a in alunos if svc.celular_do_aluno(db, a.id)]
    primeiro = com_tel[0] if com_tel else (alunos[0] if alunos else None)
    return {
        "total": len(alunos), "com_telefone": len(com_tel), "sem_telefone": len(alunos) - len(com_tel),
        "primeiro_aluno": primeiro.nome if primeiro else None,
        "mensagem": svc.texto_para_aluno(db, primeiro, texto) if primeiro else "",
    }


def criar(db: Session, usuario_id: int | None, texto: str, publico: str, unidade_id: int | None,
          pausa_segundos: int | None = None) -> Comunicado:
    texto = (texto or "").strip()
    if not texto:
        raise ErroDeNegocio("Escreva o texto do comunicado.", 422)
    alunos = selecionar_alunos(db, publico, unidade_id)
    if not alunos:
        raise ErroDeNegocio("Nenhum aluno encontrado para este público.", 422)
    if pausa_segundos is None:
        cfgs = [svc.obter_config(db, unidade_id)] if unidade_id else []
        pausa_segundos = svc.pausa_segundos(cfgs[0] if cfgs and cfgs[0] else None)
    c = Comunicado(texto=texto, publico=publico, unidade_id=unidade_id, status="enviando", criado_por_id=usuario_id,
                   pausa_segundos=max(0, min(svc.PAUSA_MAX_S, pausa_segundos)))
    db.add(c)
    db.flush()
    for a in alunos:
        tel = svc.celular_do_aluno(db, a.id)
        db.add(ComunicadoDestinatario(comunicado_id=c.id, aluno_id=a.id, nome=a.nome, telefone=tel,
                                      status="pendente" if tel else "sem_telefone"))
    db.flush()
    _concluir_se_acabou(db, c, agora())
    return c


def progresso(db: Session, c: Comunicado) -> dict:
    contagem = dict(db.execute(select(ComunicadoDestinatario.status, func.count()).where(ComunicadoDestinatario.comunicado_id == c.id)
                               .group_by(ComunicadoDestinatario.status)).all())
    total = sum(contagem.values())
    feitos = sum(contagem.get(s, 0) for s in ("enviado", "falha", "sem_telefone", "cancelado"))
    return {
        "id": c.id, "status": c.status, "texto": c.texto, "publico": c.publico, "unidade_id": c.unidade_id,
        "pausa_segundos": c.pausa_segundos, "aviso": c.aviso, "total": total,
        "enviados": contagem.get("enviado", 0), "falhas": contagem.get("falha", 0),
        "sem_telefone": contagem.get("sem_telefone", 0), "pendentes": contagem.get("pendente", 0) + contagem.get("enviando", 0),
        "cancelados": contagem.get("cancelado", 0), "percentual": int(100 * feitos / total) if total else 100,
        "criado_em": c.criado_em, "finalizado_em": c.finalizado_em,
    }


def _concluir_se_acabou(db: Session, c: Comunicado, momento: datetime) -> None:
    if c.status != "enviando":
        return
    restam = db.scalar(select(func.count()).select_from(ComunicadoDestinatario)
                       .where(ComunicadoDestinatario.comunicado_id == c.id, ComunicadoDestinatario.status.in_(("pendente", "enviando"))))
    if not restam:
        c.status, c.finalizado_em = "concluido", momento


def pausar(db: Session, c: Comunicado) -> None:
    if c.status != "enviando":
        raise ErroDeNegocio("Só é possível pausar um comunicado em andamento.", 409)
    c.status = "pausado"
    c.aviso = "Pausado por um usuário."


def retomar(db: Session, c: Comunicado) -> None:
    if c.status != "pausado":
        raise ErroDeNegocio("Só é possível retomar um comunicado pausado.", 409)
    c.status, c.aviso = "enviando", None


def cancelar(db: Session, c: Comunicado) -> None:
    if c.status in ESTADOS_FINAIS:
        raise ErroDeNegocio("Este comunicado já foi finalizado.", 409)
    db.execute(update(ComunicadoDestinatario).where(ComunicadoDestinatario.comunicado_id == c.id,
                                                    ComunicadoDestinatario.status == "pendente").values(status="cancelado"))
    c.status, c.finalizado_em, c.aviso = "cancelado", agora(), None


def _liberar_travados(db: Session, c: Comunicado, momento: datetime) -> None:
    """Destinatário "enviando" há muito tempo (worker morreu no meio): falha, SEM reenviar (poderia duplicar)."""
    if c.ultimo_envio_em and momento - c.ultimo_envio_em > timedelta(minutes=ENVIANDO_PRESO_MIN):
        db.execute(update(ComunicadoDestinatario).where(ComunicadoDestinatario.comunicado_id == c.id,
                                                        ComunicadoDestinatario.status == "enviando")
                   .values(status="falha", erro="Envio interrompido (não foi possível confirmar)."))


def _enviar_proximo(db: Session, c: Comunicado, momento: datetime) -> bool:
    """Reserva e envia 1 destinatário. Devolve True se tentou enviar."""
    limite = momento - timedelta(seconds=max(0, c.pausa_segundos - TOLERANCIA_S))
    reservou = db.execute(
        update(Comunicado).where(Comunicado.id == c.id, Comunicado.status == "enviando",
                                 (Comunicado.ultimo_envio_em.is_(None)) | (Comunicado.ultimo_envio_em <= limite))
        .values(ultimo_envio_em=momento)).rowcount
    db.commit()
    if reservou != 1:
        return False
    dest = db.scalar(select(ComunicadoDestinatario).where(ComunicadoDestinatario.comunicado_id == c.id,
                                                          ComunicadoDestinatario.status == "pendente")
                     .order_by(ComunicadoDestinatario.id).limit(1))
    if dest is None:
        return False
    pegou = db.execute(update(ComunicadoDestinatario).where(ComunicadoDestinatario.id == dest.id,
                                                            ComunicadoDestinatario.status == "pendente")
                       .values(status="enviando")).rowcount
    db.commit()
    if pegou != 1:
        return False
    aluno = db.get(Aluno, dest.aluno_id)
    try:
        texto = svc.texto_para_aluno(db, aluno, c.texto)
        res = svc.enviar_texto_aluno(db, aluno, texto, tipo="comunicado")
    except ErroDeNegocio as e:
        dest.status, dest.erro = "falha", e.mensagem[:300]
        db.commit()
        return True
    if res.sessao_caiu or res.erro_autenticacao:
        dest.status = "pendente"  # volta para a fila: nada é perdido
        c.status = "pausado"
        c.aviso = "Sessão do WhatsApp desconectada: envio pausado. Reconecte e retome." if res.sessao_caiu else \
            "Credencial do WhatsApp recusada pelo provedor: envio pausado. Confira o token e retome."
        db.commit()
        return True
    if res.ok:
        dest.status, dest.enviado_em, dest.erro = "enviado", agora(), None
    elif res.status == "sem_telefone":
        dest.status, dest.erro = "sem_telefone", (res.erro or "")[:300]
    else:
        dest.status, dest.erro = "falha", (res.erro or "Falha no envio")[:300]
    db.commit()
    return True


def processar_pendentes(momento: datetime | None = None) -> int:
    """Passada do worker: devolve quantas mensagens foram tentadas."""
    momento = momento or agora()
    tentadas = 0
    with SessionLocal() as db:
        ids = list(db.scalars(select(Comunicado.id).where(Comunicado.status == "enviando").order_by(Comunicado.id)))
        for cid in ids:
            c = db.get(Comunicado, cid)
            try:
                _liberar_travados(db, c, momento)
                if _enviar_proximo(db, c, momento):
                    tentadas += 1
                db.refresh(c)
                _concluir_se_acabou(db, c, momento)
                db.commit()
            except Exception:  # noqa: BLE001 - um comunicado com problema não derruba os outros
                db.rollback()
                log.exception("Falha ao processar o comunicado %s", cid)
    return tentadas
