"""Vínculo usuário (login) <-> profissional. Substitui os signals do Django (`core/signals.py`).

Modelo: `profissional.usuario_id` (único, anulável). Profissional SEM login existe (usuario_id nulo) ou tem um
`usuario` com `acesso_sistema=False` (acesso revogado, mantido para o histórico). O login do profissional é o
LOGIN próprio (`usuario.login`, nome curto como "ana"; nunca o e-mail). O e-mail é só contato, recuperação de senha e convite. Quem tem acesso recebe o convite para
definir a senha pelos serviços do core (`auth_service.enviar_link_email`).

Escopo do Professor: `resolver_profissional_id` é registrado em `app.core.escopo` (ver `registrar_escopo`) e diz,
para o usuário logado, qual é o seu profissional; sem vínculo o perfil restrito não enxerga nada.
"""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit, escopo
from app.core import auth_service as svc
from app.core.models import PerfilAcesso, Usuario
from app.modules.cadastros.models import Profissional

log = logging.getLogger(__name__)

LOGIN_RE = re.compile(r"[a-z0-9._-]{3,30}")


# --------------------------------------------------------------------------------------------- escopo do Professor
def resolver_profissional_id(db: Session, usuario: Usuario) -> int | None:
    """Id do profissional vinculado ao usuário logado (None = sem vínculo)."""
    return db.scalar(select(Profissional.id).where(Profissional.usuario_id == usuario.id))


def registrar_escopo() -> None:
    escopo.registrar_resolvedor_profissional(resolver_profissional_id)


# ------------------------------------------------------------------------------------------------- regras de acesso
def outros_admins(db: Session, u: Usuario) -> bool:
    q = (select(Usuario.id).join(PerfilAcesso, Usuario.perfil_acesso_id == PerfilAcesso.id)
         .where(Usuario.id != u.id, Usuario.ativo, Usuario.acesso_sistema, PerfilAcesso.administrador))
    return bool(db.scalar(q))


def _exigir_pode_tirar_acesso(db: Session, u: Usuario, ator: Usuario) -> None:
    if u.id == ator.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Você não pode tirar o seu próprio acesso.")
    if u.administrador and not outros_admins(db, u):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "É preciso manter pelo menos um Administrador ativo com acesso.")


def perfil_ou_404(db: Session, perfil_id: int | None) -> PerfilAcesso:
    p = db.get(PerfilAcesso, perfil_id) if perfil_id else None
    if not p:
        raise HTTPException(422, "Escolha o perfil de acesso.")
    return p


def normalizar_login(login: str | None) -> str:
    limpo = (login or "").strip().lower()
    if not LOGIN_RE.fullmatch(limpo):
        raise HTTPException(422, "Login inválido: use de 3 a 30 caracteres entre letras minúsculas, números, ponto, hífen e sublinhado (sem @ nem espaço).")
    return limpo


def login_livre(db: Session, login: str, exceto_usuario_id: int | None = None) -> None:
    q = select(Usuario.id).where(func.lower(Usuario.login) == login.lower())
    if exceto_usuario_id:
        q = q.where(Usuario.id != exceto_usuario_id)
    if db.scalar(q):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este login já está em uso. Escolha outro.")


def email_do_usuario_livre(db: Session, email: str, exceto_usuario_id: int | None = None) -> None:
    q = select(Usuario.id).where(Usuario.email == email.lower())
    if exceto_usuario_id:
        q = q.where(Usuario.id != exceto_usuario_id)
    if db.scalar(q):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com este e-mail. Use outro e-mail ou ajuste o cadastro do usuário em Configurações.")


def _enviar_convite(db: Session, u: Usuario) -> bool:
    try:
        return bool(svc.enviar_link_email(db, u, convite=True))
    except Exception:  # SMTP fora do ar não pode desfazer o cadastro: o convite pode ser reenviado depois
        log.exception("Falha ao enviar o convite do usuário %s", u.id)
        return False


def conceder_acesso(db: Session, prof: Profissional, perfil: PerfilAcesso, login: str | None) -> tuple[Usuario, bool]:
    """Cria (ou reativa) o usuário do profissional e envia o convite. Devolve (usuário, convite_enviado)."""
    if not prof.email:
        raise HTTPException(422, "Informe o e-mail do profissional: ele é o login de acesso ao sistema.")
    if not prof.ativo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ative o profissional antes de dar acesso ao sistema.")
    u = db.get(Usuario, prof.usuario_id) if prof.usuario_id else None
    if u is not None and u.acesso_sistema and u.ativo:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este profissional já tem acesso ao sistema.")
    login = normalizar_login(login)
    login_livre(db, login, exceto_usuario_id=u.id if u else None)
    email_do_usuario_livre(db, prof.email, exceto_usuario_id=u.id if u else None)
    if u is None:
        u = Usuario(nome=prof.nome, login=login, email=prof.email.lower(), telefone=prof.celular, perfil_acesso_id=perfil.id,
                    acesso_sistema=True, ativo=True, convite_pendente=True)
        db.add(u)
        db.flush()
        prof.usuario_id = u.id
    else:  # acesso revogado antes: reativa o mesmo usuário (mantém o histórico) com nova senha a definir
        u.nome, u.login, u.email, u.telefone = prof.nome, login, prof.email.lower(), prof.celular
        u.perfil_acesso_id = perfil.id
        u.acesso_sistema, u.ativo = True, True
        u.senha_hash, u.convite_pendente = None, True
        svc.invalidar_sessoes(db, u)
    prof.perfil_acesso_id = perfil.id
    db.flush()
    return u, _enviar_convite(db, u)


def revogar_acesso(db: Session, prof: Profissional, ator: Usuario) -> Usuario:
    """Tira o acesso ao sistema (o profissional continua cadastrado). Derruba as sessões em curso (token_version)."""
    u = db.get(Usuario, prof.usuario_id) if prof.usuario_id else None
    if u is None or not u.acesso_sistema:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este profissional não tem acesso ao sistema.")
    _exigir_pode_tirar_acesso(db, u, ator)
    u.acesso_sistema = False
    u.convite_pendente = False
    svc.invalidar_sessoes(db, u)
    db.flush()
    return u


def sincronizar_usuario(db: Session, prof: Profissional, ator: Usuario, *, perfil_id: int | None = None, login: str | None = None) -> list[str]:
    """Propaga nome, e-mail, celular, situação e perfil do profissional para o usuário vinculado.

    Devolve a lista das mudanças feitas no usuário (para a auditoria). Sem usuário vinculado não faz nada.
    """
    u = db.get(Usuario, prof.usuario_id) if prof.usuario_id else None
    if u is None:
        return []
    antes = audit.snapshot(u)
    mudou: list[str] = []
    if u.nome != prof.nome:
        u.nome = prof.nome
    if (u.telefone or None) != (prof.celular or None):
        u.telefone = prof.celular
    if u.acesso_sistema:
        if not prof.email:
            raise HTTPException(422, "Este profissional tem acesso ao sistema: o e-mail é o login e não pode ficar vazio.")
        if u.email != prof.email.lower():
            email_do_usuario_livre(db, prof.email, exceto_usuario_id=u.id)
            u.email = prof.email.lower()
        if login is not None and login.strip().lower() != (u.login or ""):
            novo_login = normalizar_login(login)
            login_livre(db, novo_login, exceto_usuario_id=u.id)
            u.login = novo_login
            svc.invalidar_sessoes(db, u)  # quem está logado com o login antigo precisa entrar de novo
        if not prof.ativo and u.ativo:
            _exigir_pode_tirar_acesso(db, u, ator)
            u.ativo = False
            svc.invalidar_sessoes(db, u)
        elif prof.ativo and not u.ativo:
            u.ativo = True
        if perfil_id is not None and perfil_id != u.perfil_acesso_id:
            novo = perfil_ou_404(db, perfil_id)
            if u.administrador and not novo.administrador and not outros_admins(db, u):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "É preciso manter pelo menos um Administrador ativo com acesso.")
            u.perfil_acesso_id = novo.id
            prof.perfil_acesso_id = novo.id
            svc.invalidar_sessoes(db, u)  # permissões mudaram: sessões em curso saem
    db.flush()
    a, d = audit.diff(antes, audit.snapshot(u))
    mudou = sorted(a) if a else mudou
    return mudou
