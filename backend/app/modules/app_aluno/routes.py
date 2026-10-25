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

from app.core import audit, notificador
from app.core.db import agora as agora_utc
from app.core.db import get_db
from app.core.deps import Ctx
from app.core.models import Auditoria
from app.core.permissoes import adicionar_regras
from app.core.ratelimit import ip_do_cliente, limitar, verificar
from app.core.security import hash_token
from app.domain import documentos
from app.domain.financeiro import hoje_de_negocio
from app.modules.alunos.models import Aluno
from app.modules.app_aluno import reposicoes as reposicoes_srv
from app.modules.app_aluno import servico as srv
from app.modules.app_aluno.models import ReposicaoPedido
from app.modules.app_aluno.schemas import (
    AprovarIn,
    AulaOut,
    CodigoIn,
    DesmarcarOut,
    Mensagem,
    MeOut,
    PedirIn,
    RecusarIn,
    RefreshIn,
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
    return reposicoes_srv.listar_reposicoes(db, aluno, agora=_agora())


@router_publico.post("/reposicoes/{reserva_id}/pedir", response_model=ReposicaoOut, dependencies=[_geral])
def pedir(reserva_id: int, dados: PedirIn, aluno: AlunoLogado, request: Request, db: DB) -> dict:
    """O aluno só PEDE a reposição (com preferência em texto livre); a gerência decide. Idempotente enquanto pendente."""
    r = _executar(db, reposicoes_srv.pedir_reposicao, aluno, reserva_id, dados.preferencia, agora=_agora())
    _auditar(db, aluno, "aluno_app.reposicao_pedir", "reserva", reserva_id, ip_do_cliente(request), "pedido de reposição")
    db.commit()
    return r


# ====================================================================================================== EQUIPE (gerência)
router = APIRouter(tags=["reposicoes"])

adicionar_regras([("*", r"/reposicoes", "reposicoes.*")])  # GET = ver, POST (aprovar/recusar) = editar; só o perfil Full tem


def _equipe(db: Session, fn, *args, **kw):
    try:
        return fn(db, *args, **kw)
    except srv.ErroAluno as e:
        db.rollback()
        raise HTTPException(e.status, e.mensagem) from None


def _avisar(db: Session, aluno_id: int, texto: str) -> None:
    """WhatsApp ao aluno pelo notificador do core (ponto de extensão; falha nunca desfaz a decisão)."""
    try:
        tel = srv.telefone_do_aluno(db, aluno_id)
        if tel:
            notificador.get_notificador().enviar_texto(tel, texto)
    except Exception:  # noqa: BLE001
        log.warning("Falha ao avisar o aluno da decisão da reposição.")


@router.get("/reposicoes")
def listar_pedidos(ctx: Ctx, status: str | None = None, q: str | None = None) -> dict:
    """Pedidos de reposição, com as contagens dos chips Pendentes/Aprovados/Recusados."""
    return _equipe(ctx.db, reposicoes_srv.listar_pedidos, status=status, busca=q, agora=_agora())


@router.get("/reposicoes/{pedido_id}/opcoes")
def opcoes_do_pedido(pedido_id: int, ctx: Ctx, ignorar_prazo: bool = False) -> list[dict]:
    """Aulas com vaga real do mesmo serviço e unidade (sugestão para aprovar)."""
    return _equipe(ctx.db, reposicoes_srv.opcoes_do_pedido, pedido_id, ignorar_prazo=ignorar_prazo, agora=_agora())


def _snap_pedido(p: ReposicaoPedido) -> dict:
    return audit.snapshot(p)


@router.post("/reposicoes/{pedido_id}/aprovar")
def aprovar(pedido_id: int, dados: AprovarIn, ctx: Ctx) -> dict:
    p = _equipe(ctx.db, reposicoes_srv._pedido, pedido_id)
    antes = _snap_pedido(p)
    p = _equipe(
        ctx.db, reposicoes_srv.aprovar, pedido_id, dados.aula_id, ctx.usuario,
        ignorar_prazo=dados.ignorar_prazo, motivo=dados.motivo, agora=_agora(),
    )
    a, d = audit.diff(antes, _snap_pedido(p))
    aluno = ctx.db.get(Aluno, p.aluno_id)
    desc = f"{aluno.nome}: aula de {p.data_origem:%d/%m/%Y} para {p.aprovado_data:%d/%m/%Y} {p.aprovado_hora:%H:%M}"
    if p.ignorou_prazo:
        desc += f" | PRAZO IGNORADO: {p.motivo_ignorar_prazo}"
    ctx.auditar("reposicao.aprovar", "reposicao_pedido", p.id, descricao=desc, antes=a, depois=d)
    ctx.db.commit()
    _avisar(ctx.db, p.aluno_id, reposicoes_srv.texto_aprovado(aluno, p))
    return reposicoes_srv._item_equipe(ctx.db, p, hoje_de_negocio(_agora()))


@router.post("/reposicoes/{pedido_id}/recusar")
def recusar(pedido_id: int, dados: RecusarIn, ctx: Ctx) -> dict:
    p = _equipe(ctx.db, reposicoes_srv._pedido, pedido_id)
    antes = _snap_pedido(p)
    p = _equipe(ctx.db, reposicoes_srv.recusar, pedido_id, ctx.usuario, dados.motivo, agora=_agora())
    a, d = audit.diff(antes, _snap_pedido(p))
    aluno = ctx.db.get(Aluno, p.aluno_id)
    ctx.auditar("reposicao.recusar", "reposicao_pedido", p.id, descricao=f"{aluno.nome}: {p.motivo_recusa}", antes=a, depois=d)
    ctx.db.commit()
    _avisar(ctx.db, p.aluno_id, reposicoes_srv.texto_recusado(aluno, p))
    return reposicoes_srv._item_equipe(ctx.db, p, hoje_de_negocio(_agora()))
