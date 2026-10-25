"""API do app do aluno (PWA em /app/). Tudo sob ``/api/aluno-app/`` com autenticação PRÓPRIA (não usa o login da equipe).

- ``POST /auth/codigo``     pede o código (CPF); resposta igual exista ou não o CPF
- ``POST /auth/verificar``  CPF + código -> tokens do aluno (access 12 h + refresh 7 dias)
- ``POST /auth/refresh``    renova o par
- ``GET  /me`` · ``GET /aulas`` · ``POST /aulas/{id}/confirmar`` · ``POST /aulas/{id}/desmarcar``
- ``GET  /reposicoes`` · ``GET /reposicoes/{id}/opcoes`` · ``POST /reposicoes/{id}/remarcar``

Todas as rotas têm rate limit por IP; as de login também por CPF. O aluno só enxerga e mexe nas PRÓPRIAS reservas
(id alheio = 404). Token de aluno não abre rota da equipe e vice-versa (``typ``/``aud`` diferentes).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import notificador
from app.core.db import agora as agora_utc
from app.core.db import get_db
from app.core.models import Auditoria
from app.core.ratelimit import ip_do_cliente, limitar, verificar
from app.core.security import hash_token
from app.domain import documentos
from app.modules.alunos.models import Aluno
from app.modules.app_aluno import servico as srv
from app.modules.app_aluno.schemas import (
    AulaOut,
    CodigoIn,
    DesmarcarOut,
    Mensagem,
    MeOut,
    OpcaoReposicaoOut,
    RefreshIn,
    RemarcarIn,
    ReposicaoOut,
    TokensOut,
    VerificarIn,
)

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]

# limites (janela em segundos)
JANELA_LOGIN = 15 * 60
LIM_CODIGO_IP = 10
LIM_CODIGO_CPF = 3
LIM_VERIFICAR_IP = 20
LIM_VERIFICAR_CPF = 15


def _agora() -> datetime:
    """Relógio da API (os testes congelam)."""
    return agora_utc()


def _erro(e: srv.ErroAluno) -> HTTPException:
    return HTTPException(e.status, e.mensagem)


def aluno_atual(request: Request, db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> Aluno:
    """Autenticação do app: access token DO ALUNO (não aceita token da equipe nem refresh)."""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Entre com seu CPF para continuar.")
    try:
        return srv.aluno_do_token(db, cred.credentials, srv.TIPO_ACCESS)
    except srv.ErroAluno as e:
        raise _erro(e) from None


AlunoLogado = Annotated[Aluno, Depends(aluno_atual)]

router_publico = APIRouter(prefix="/aluno-app", tags=["app do aluno"])
_geral = Depends(limitar("aluno-app", 240, 60))


def _chave_cpf(cpf: str) -> str:
    """Chave de rate limit por CPF sem guardar o CPF."""
    return hash_token("rl-cpf:" + documentos.so_digitos(cpf))[:20]


def _auditar(db: Session, aluno: Aluno, acao: str, entidade: str, entidade_id, ip: str | None, descricao: str | None = None) -> None:
    db.add(
        Auditoria(
            usuario_id=None,
            usuario_nome=f"Aluno (app): {aluno.nome}"[:150],
            acao=acao,
            entidade=entidade,
            entidade_id=str(entidade_id),
            descricao=descricao,
            ip=ip,
        )
    )


# ----------------------------------------------------------------------------------------------------------- login
def _enviar_codigo(telefone: str, texto: str) -> None:
    try:
        notificador.get_notificador().enviar_texto(telefone, texto)
    except Exception:  # noqa: BLE001 - falha de envio nunca vaza para o aluno nem muda a resposta
        log.warning("Falha ao enviar o código do app do aluno.")


@router_publico.post("/auth/codigo", response_model=Mensagem)
def pedir_codigo(dados: CodigoIn, request: Request, db: DB, fundo: BackgroundTasks) -> Mensagem:
    verificar(request, "aluno-app-codigo-ip", LIM_CODIGO_IP, JANELA_LOGIN, db=db)
    verificar(request, "aluno-app-codigo-cpf", LIM_CODIGO_CPF, JANELA_LOGIN, chave=_chave_cpf(dados.cpf), db=db)
    envio = srv.pedir_codigo(db, dados.cpf, agora=_agora())
    if envio is not None:
        fundo.add_task(_enviar_codigo, envio.telefone, envio.texto)  # depois da resposta: o tempo não revela o CPF
    return Mensagem(mensagem=srv.MENSAGEM_PEDIDO)


@router_publico.post("/auth/verificar", response_model=TokensOut)
def verificar_codigo(dados: VerificarIn, request: Request, db: DB) -> TokensOut:
    verificar(request, "aluno-app-verificar-ip", LIM_VERIFICAR_IP, JANELA_LOGIN, db=db)
    verificar(request, "aluno-app-verificar-cpf", LIM_VERIFICAR_CPF, JANELA_LOGIN, chave=_chave_cpf(dados.cpf), db=db)
    try:
        aluno = srv.verificar_codigo(db, dados.cpf, dados.codigo, agora=_agora())
    except srv.ErroAluno as e:
        raise _erro(e) from None
    _auditar(db, aluno, "aluno_app.login", "aluno", aluno.id, ip_do_cliente(request))
    db.commit()
    return TokensOut(**srv.emitir_tokens(aluno.id))


@router_publico.post("/auth/refresh", response_model=TokensOut, dependencies=[Depends(limitar("aluno-app-refresh", 60, 3600))])
def renovar(dados: RefreshIn, db: DB) -> TokensOut:
    try:
        aluno = srv.aluno_do_token(db, dados.refresh_token, srv.TIPO_REFRESH)
    except srv.ErroAluno as e:
        raise _erro(e) from None
    return TokensOut(**srv.emitir_tokens(aluno.id))


# --------------------------------------------------------------------------------------------------------- consulta
@router_publico.get("/me", response_model=MeOut, dependencies=[_geral])
def eu(aluno: AlunoLogado, db: DB) -> dict:
    return srv.me(db, aluno)


@router_publico.get("/aulas", response_model=list[AulaOut], dependencies=[_geral])
def aulas(aluno: AlunoLogado, db: DB) -> list[dict]:
    return srv.listar_aulas(db, aluno, agora=_agora())


def _executar(db: Session, fn, *args, **kw):
    """Roda a ação do serviço; em erro desfaz tudo e devolve o HTTP certo."""
    try:
        return fn(db, *args, **kw)
    except srv.ErroAluno as e:
        db.rollback()
        raise HTTPException(e.status, e.mensagem) from None
    except Exception:
        db.rollback()
        raise


@router_publico.post("/aulas/{reserva_id}/confirmar", response_model=AulaOut, dependencies=[_geral])
def confirmar(reserva_id: int, aluno: AlunoLogado, request: Request, db: DB) -> dict:
    r = _executar(db, srv.confirmar, aluno, reserva_id, agora=_agora())
    _auditar(db, aluno, "aluno_app.confirmar", "reserva", reserva_id, ip_do_cliente(request))
    db.commit()
    return r


@router_publico.post("/aulas/{reserva_id}/desmarcar", response_model=DesmarcarOut, dependencies=[_geral])
def desmarcar(reserva_id: int, aluno: AlunoLogado, request: Request, db: DB) -> dict:
    r = _executar(db, srv.desmarcar, aluno, reserva_id, agora=_agora())
    _auditar(db, aluno, "aluno_app.desmarcar", "reserva", reserva_id, ip_do_cliente(request), f"reposição até {r['reposicao_ate']:%d/%m/%Y}")
    db.commit()
    return r


# ------------------------------------------------------------------------------------------------------- reposições
@router_publico.get("/reposicoes", response_model=list[ReposicaoOut], dependencies=[_geral])
def reposicoes(aluno: AlunoLogado, db: DB) -> list[dict]:
    return srv.listar_reposicoes(db, aluno, agora=_agora())


@router_publico.get("/reposicoes/{reserva_id}/opcoes", response_model=list[OpcaoReposicaoOut], dependencies=[_geral])
def opcoes(reserva_id: int, aluno: AlunoLogado, db: DB) -> list[dict]:
    return _executar(db, srv.opcoes_reposicao, aluno, reserva_id, agora=_agora())


@router_publico.post("/reposicoes/{reserva_id}/remarcar", response_model=AulaOut, dependencies=[_geral])
def remarcar(reserva_id: int, dados: RemarcarIn, aluno: AlunoLogado, request: Request, db: DB) -> dict:
    r = _executar(db, srv.remarcar_reposicao, aluno, reserva_id, dados.aula_id, agora=_agora())
    _auditar(db, aluno, "aluno_app.reposicao", "reserva", reserva_id, ip_do_cliente(request), f"nova aula em {r['data']:%d/%m/%Y}")
    db.commit()
    return r
