"""Escopo "somente as próprias aulas" (perfil Professor).

CONTRATO para os módulos de negócio:
  1. Registrar UMA vez, na subida, quem é o profissional do usuário logado:
         escopo.registrar_resolvedor_profissional(lambda db, usuario: id_do_profissional_ou_None)
  2. Em toda consulta de aulas/reservas/alunos/evolução, aplicar o filtro:
         if ctx.somente_proprias_aulas():
             query = escopo.filtrar_proprias(ctx, query, Aula.profissional_id)
  3. Em rotas de um item específico (ex.: evolução da reserva X), checar `escopo.pode_acessar_profissional(ctx, prof_id)`.

Sem resolvedor registrado, ou usuário sem profissional vinculado, o perfil restrito NÃO enxerga nada (negar por padrão).
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import false
from sqlalchemy.orm import Session

from app.core.models import Usuario

Resolvedor = Callable[[Session, Usuario], int | None]


def _sem_resolvedor(db: Session, usuario: Usuario) -> int | None:
    return None


_resolvedor: Resolvedor = _sem_resolvedor


def registrar_resolvedor_profissional(fn: Resolvedor) -> None:
    global _resolvedor
    _resolvedor = fn


def resolver_profissional_id(db: Session, usuario: Usuario) -> int | None:
    return _resolvedor(db, usuario)


def usuario_restrito(usuario: Usuario) -> bool:
    """Administrador nunca é restrito; senão vale a marca do perfil de acesso."""
    p = usuario.perfil_acesso
    return bool(p and not p.administrador and p.somente_proprias_aulas)


def filtrar_proprias(ctx: Any, consulta, coluna_profissional):
    """Restringe `consulta` (select) às linhas do profissional do usuário; sem vínculo, nada."""
    if not ctx.somente_proprias_aulas():
        return consulta
    pid = ctx.profissional_id()
    return consulta.where(coluna_profissional == pid) if pid is not None else consulta.where(false())


def pode_acessar_profissional(ctx: Any, profissional_id: int | None) -> bool:
    if not ctx.somente_proprias_aulas():
        return True
    pid = ctx.profissional_id()
    return pid is not None and profissional_id == pid
