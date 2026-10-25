"""Autenticação. `publico` = sem login (rate limit); `router` = conta do usuário logado."""

import json
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.core import auth_service as svc
from app.core import storage
from app.core.deps import DB, Ctx, ip_cliente
from app.core.models import Usuario
from app.core.ratelimit import limitar, verificar
from app.core.schemas import (
    ForgotIn,
    LoginIn,
    MePatch,
    Mensagem,
    RefreshIn,
    ResetCodigoIn,
    ResetIn,
    TokenOut,
    TrocarSenhaIn,
    UsuarioMe,
)

publico = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(prefix="/auth", tags=["auth"])

MSG_FORGOT = "Se a conta existir, enviamos as instruções para redefinir a senha."


def foto_url(u: Usuario) -> str | None:
    if not storage.existe(u.foto_path):
        return None
    return f"/auth/usuarios/{u.id}/foto?v={storage.versao(u.foto_path)}"


def me_out(u: Usuario) -> UsuarioMe:
    return UsuarioMe.model_validate(u).model_copy(update={
        "foto_url": foto_url(u), "administrador": u.administrador, "permissoes": sorted(u.permissoes),
        "perfil_acesso_nome": u.perfil_acesso.nome if u.perfil_acesso else None,
        "somente_proprias_aulas": bool(u.perfil_acesso and not u.administrador and u.perfil_acesso.somente_proprias_aulas)})


def _tokens(db, u: Usuario) -> TokenOut:
    access, refresh = svc.emitir_tokens(db, u)
    return TokenOut(access_token=access, refresh_token=refresh, usuario=me_out(u))


# ------------------------------------------------------------------------------------------- públicas
@publico.post("/login", response_model=TokenOut, dependencies=[Depends(limitar("login", 20, 60))])
def login(dados: LoginIn, request: Request, db: DB):
    # além do limite por IP, limita por identificador (ataque distribuído contra uma conta)
    verificar(request, "login-conta", 30, 900, chave=dados.identificador.strip().lower(), db=db)
    u = svc.autenticar(db, dados.identificador, dados.senha, ip_cliente(request))
    out = _tokens(db, u)
    db.commit()
    return out


@publico.post("/refresh", response_model=TokenOut, dependencies=[Depends(limitar("refresh", 60, 60))])
def refresh(dados: RefreshIn, request: Request, db: DB):
    u, access, refresh_token = svc.rotacionar_refresh(db, dados.refresh_token, ip_cliente(request))
    return TokenOut(access_token=access, refresh_token=refresh_token, usuario=me_out(u))


@publico.post("/forgot", response_model=Mensagem, dependencies=[Depends(limitar("forgot", 5, 900))])
def forgot(dados: ForgotIn, request: Request, db: DB):
    """Recuperação por e-mail. A resposta é a mesma exista a conta ou não."""
    verificar(request, "forgot-conta", 3, 3600, chave=dados.identificador.strip().lower(), db=db)
    u = svc.localizar(db, dados.identificador)
    if u and u.ativo and u.acesso_sistema:
        svc.enviar_link_email(db, u)
        db.commit()
    return Mensagem(mensagem=MSG_FORGOT)


@publico.post("/reset", response_model=Mensagem, dependencies=[Depends(limitar("reset", 10, 900))])
def reset(dados: ResetIn, request: Request, db: DB):
    svc.redefinir_por_token(db, dados.token, dados.senha, ip_cliente(request))
    db.commit()
    return Mensagem(mensagem="Senha definida. Você já pode entrar.")


@publico.post("/forgot-codigo", response_model=Mensagem, dependencies=[Depends(limitar("forgot-codigo", 5, 900))])
def forgot_codigo(dados: ForgotIn, request: Request, db: DB):
    """Recuperação por código enviado ao WhatsApp cadastrado. Resposta igual exista a conta (ou o telefone) ou não."""
    verificar(request, "forgot-codigo-conta", 3, 3600, chave=dados.identificador.strip().lower(), db=db)
    u = svc.localizar(db, dados.identificador)
    if u and u.ativo and u.acesso_sistema:
        svc.enviar_codigo_whatsapp(db, u)
        db.commit()
    return Mensagem(mensagem="Se a conta existir e tiver WhatsApp cadastrado, enviamos um código.")


@publico.post("/reset-codigo", response_model=Mensagem, dependencies=[Depends(limitar("reset-codigo", 10, 900))])
def reset_codigo(dados: ResetCodigoIn, request: Request, db: DB):
    svc.redefinir_por_codigo(db, dados.identificador, dados.codigo, dados.senha, ip_cliente(request))
    db.commit()
    return Mensagem(mensagem="Senha definida. Você já pode entrar.")


# ------------------------------------------------------------------------------------------- conta logada
@router.post("/trocar-senha", response_model=TokenOut)
def trocar_senha(dados: TrocarSenhaIn, ctx: Ctx):
    """Exige a senha atual. Derruba as outras sessões e devolve tokens novos para esta."""
    svc.trocar_senha(ctx.db, ctx.usuario, dados.senha_atual, dados.nova_senha, ctx.ip)
    out = _tokens(ctx.db, ctx.usuario)
    ctx.db.commit()
    return out


@router.post("/logout", response_model=Mensagem)
def logout(ctx: Ctx):
    """Encerra TODAS as sessões do usuário (invalida access e refresh em circulação)."""
    svc.invalidar_sessoes(ctx.db, ctx.usuario)
    ctx.auditar("auth.logout", "usuario", ctx.usuario.id)
    ctx.db.commit()
    return Mensagem(mensagem="Sessões encerradas.")


@router.get("/me", response_model=UsuarioMe)
def me(ctx: Ctx):
    return me_out(ctx.usuario)


@router.patch("/me", response_model=UsuarioMe)
def alterar_me(dados: MePatch, ctx: Ctx):
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(ctx.usuario, k, v)
    ctx.auditar("usuario.alterar_proprio", "usuario", ctx.usuario.id)
    ctx.db.commit()
    return me_out(ctx.usuario)


@router.put("/me/preferencias", response_model=UsuarioMe)
def salvar_preferencias(dados: dict[str, Any], ctx: Ctx):
    """Mescla as preferências enviadas (ex.: {"menu_recolhido": ["Cadastros"]}). Valor null remove a chave."""
    atual = dict(ctx.usuario.preferencias or {})
    for k, v in dados.items():
        if v is None:
            atual.pop(k, None)
        else:
            atual[str(k)[:60]] = v
    if len(json.dumps(atual)) > 20_000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Preferências grandes demais.")
    ctx.usuario.preferencias = atual
    ctx.db.commit()
    return me_out(ctx.usuario)


async def salvar_foto(u: Usuario, arquivo: UploadFile) -> None:
    conteudo = await arquivo.read(4 * 1024 * 1024 + 1)
    try:
        u.foto_path = storage.salvar("usuarios", arquivo.filename or "", conteudo, nome_base=f"usuario_{u.id}", substituir=True)
    except storage.ArquivoInvalido as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.post("/me/foto", response_model=UsuarioMe)
async def enviar_foto(ctx: Ctx, arquivo: UploadFile = File(...)):
    await salvar_foto(ctx.usuario, arquivo)
    ctx.auditar("usuario.foto", "usuario", ctx.usuario.id, descricao="Nova foto de perfil")
    ctx.db.commit()
    return me_out(ctx.usuario)


@router.delete("/me/foto", response_model=UsuarioMe)
def remover_foto(ctx: Ctx):
    storage.remover(ctx.usuario.foto_path)
    ctx.usuario.foto_path = None
    ctx.db.commit()
    return me_out(ctx.usuario)


def _usuario(ctx, uid: int) -> Usuario:
    u = ctx.db.get(Usuario, uid)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    return u


@router.post("/usuarios/{uid}/foto", response_model=Mensagem)
async def enviar_foto_de(uid: int, ctx: Ctx, arquivo: UploadFile = File(...)):
    """Quem pode editar usuários troca a foto de outro (ex.: profissional sem login)."""
    u = _usuario(ctx, uid)
    await salvar_foto(u, arquivo)
    ctx.auditar("usuario.foto", "usuario", u.id, descricao=f"Foto de {u.nome} trocada por {ctx.usuario.nome}")
    ctx.db.commit()
    return Mensagem(mensagem=f"Foto de {u.nome} atualizada.")


@router.delete("/usuarios/{uid}/foto", response_model=Mensagem)
def remover_foto_de(uid: int, ctx: Ctx):
    u = _usuario(ctx, uid)
    storage.remover(u.foto_path)
    u.foto_path = None
    ctx.auditar("usuario.foto", "usuario", u.id, descricao=f"Foto de {u.nome} removida por {ctx.usuario.nome}")
    ctx.db.commit()
    return Mensagem(mensagem="Foto removida.")


@router.get("/usuarios/{uid}/foto")
def foto(uid: int, ctx: Ctx):
    u = _usuario(ctx, uid)
    if not storage.existe(u.foto_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sem foto.")
    return FileResponse(storage.resolver(u.foto_path), headers={"Cache-Control": "private, max-age=86400"})
