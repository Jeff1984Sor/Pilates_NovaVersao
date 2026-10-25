"""Profissionais (`/api/cadastros/profissionais`): cadastro, comissão e vínculo opcional com um usuário de login.

- Sem acesso ao sistema: só o cadastro (aparece em agendas e comissões).
- Com acesso: cria o `usuario` (login próprio) com o perfil escolhido e envia o convite para definir a senha.
- `POST/DELETE /{id}/acesso` dá e revoga o acesso depois; editar o profissional sincroniza o usuário.
- `GET/PATCH /meu`: o próprio profissional edita os seus dados (tela Minha conta; qualquer usuário logado).
Dar ou tirar acesso exige também `usuarios.editar` (além de `cadastros_profissionais.editar`).
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core import auth_service as svc
from app.core.deps import Ctx
from app.core.models import PerfilAcesso, Usuario
from app.core.schemas import Mensagem, Schema
from app.domain.telefone import normalizar_telefone_br
from app.modules.cadastros import comum, vinculo_usuario
from app.modules.cadastros.comum import PaginaCad, Situacao, VinculosOut
from app.modules.cadastros.models import Profissional, proximo_codigo

router = APIRouter(prefix="/cadastros/profissionais", tags=["cadastros: profissionais"])

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
Texto50 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]


def _celular(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    n = normalizar_telefone_br(v)
    if not n:
        raise ValueError("celular inválido: informe o DDD e o número")
    return n


def _data_nascimento(v: date | None) -> date | None:
    if v is not None and (v > date.today() or v.year < 1900):
        raise ValueError("data de nascimento inválida")
    return v


class _Contato(BaseModel):
    nome: Nome
    celular: str | None = Field(default=None, max_length=30)
    data_nascimento: date | None = None
    crefito: Texto50 | None = None

    @field_validator("celular")
    @classmethod
    def _validar_celular(cls, v):
        return _celular(v)

    @field_validator("data_nascimento")
    @classmethod
    def _validar_nascimento(cls, v):
        return _data_nascimento(v)

    @field_validator("crefito")
    @classmethod
    def _vazio_vira_nulo(cls, v):
        return v or None


class ProfissionalIn(_Contato):
    email: EmailStr | None = None
    comissao_percentual: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    ativo: bool = True
    # só vale na criação; depois use POST/DELETE /{id}/acesso
    acesso_sistema: bool = False
    perfil_acesso_id: int | None = None
    # obrigatório ao dar acesso (3 a 30: minúsculas, números, ponto, hífen e sublinhado); na edição troca o login
    login: str | None = Field(default=None, max_length=60)


class ProfissionalPut(ProfissionalIn):
    """Edição: `perfil_acesso_id` troca o perfil de quem já tem acesso (exige `usuarios.editar`); `acesso_sistema` é ignorado."""


class AcessoIn(BaseModel):
    perfil_acesso_id: int
    login: str = Field(max_length=60)


class ProfissionalOut(Schema):
    id: int
    codigo: int | None
    nome: str
    email: str | None
    celular: str | None
    data_nascimento: date | None
    crefito: str | None
    comissao_percentual: Decimal
    ativo: bool
    usuario_id: int | None
    login: str | None = None
    acesso_sistema: bool
    convite_pendente: bool
    perfil_acesso_id: int | None
    perfil_acesso_nome: str | None
    perfil_acesso_cor: str | None
    convite_enviado: bool | None = None  # só na criação / ao dar acesso


class PerfilAcessoOpcao(Schema):
    id: int
    nome: str
    cor: str | None
    administrador: bool
    somente_proprias_aulas: bool


def _out(db, p: Profissional, u: Usuario | None = None, perfil: PerfilAcesso | None = None, convite_enviado: bool | None = None) -> ProfissionalOut:
    if u is None and p.usuario_id:
        u = db.get(Usuario, p.usuario_id)
    acesso = bool(u and u.acesso_sistema)
    if perfil is None and u is not None and acesso and u.perfil_acesso_id:
        perfil = db.get(PerfilAcesso, u.perfil_acesso_id)
    return ProfissionalOut(
        id=p.id, codigo=p.codigo_legado, nome=p.nome, email=p.email, celular=p.celular, data_nascimento=p.data_nascimento,
        crefito=p.crefito, comissao_percentual=p.comissao_percentual, ativo=p.ativo, usuario_id=p.usuario_id, login=u.login if u else None,
        acesso_sistema=acesso, convite_pendente=bool(u and acesso and u.convite_pendente),
        perfil_acesso_id=perfil.id if perfil else None, perfil_acesso_nome=perfil.nome if perfil else None,
        perfil_acesso_cor=perfil.cor if perfil else None, convite_enviado=convite_enviado)


def _obter(ctx, profissional_id: int) -> Profissional:
    p = ctx.db.get(Profissional, profissional_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profissional não encontrado.")
    return p


def _email_livre(ctx, email: str | None, exceto_id: int | None = None) -> None:
    if email and comum.duplicado(ctx.db, Profissional, Profissional.email, email, exceto_id=exceto_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um profissional com este e-mail.")


_ORDEM = {"nome": Profissional.nome, "email": Profissional.email, "comissao": Profissional.comissao_percentual,
          "codigo": Profissional.codigo_legado, "crefito": Profissional.crefito}


@router.get("/perfis-acesso", response_model=list[PerfilAcessoOpcao])
def perfis_de_acesso(ctx: Ctx):
    """Perfis que podem ser escolhidos ao dar acesso (Full, Professor, Secretária e os criados pela matriz)."""
    from app.core import perfis

    perfis.garantir_padrao(ctx.db)
    ctx.db.commit()
    lista = ctx.db.scalars(select(PerfilAcesso).order_by(PerfilAcesso.administrador.desc(), PerfilAcesso.nome))
    return [PerfilAcessoOpcao.model_validate(p) for p in lista]


# ----------------------------------------------------------------------------------- o próprio profissional (Minha conta)
class MeuProfissionalIn(_Contato):
    pass


class MeuProfissionalOut(Schema):
    id: int
    codigo: int | None
    nome: str
    email: str | None
    celular: str | None
    data_nascimento: date | None
    crefito: str | None


def _meu(ctx) -> Profissional | None:
    pid = vinculo_usuario.resolver_profissional_id(ctx.db, ctx.usuario)
    return ctx.db.get(Profissional, pid) if pid else None


def _meu_out(p: Profissional) -> MeuProfissionalOut:
    return MeuProfissionalOut(id=p.id, codigo=p.codigo_legado, nome=p.nome, email=p.email, celular=p.celular,
                              data_nascimento=p.data_nascimento, crefito=p.crefito)


@router.get("/meu", response_model=MeuProfissionalOut | None)
def meu_cadastro(ctx: Ctx):
    """Dados do profissional vinculado ao usuário logado (null se a conta não é de um profissional)."""
    p = _meu(ctx)
    return _meu_out(p) if p else None


@router.patch("/meu", response_model=MeuProfissionalOut)
def alterar_meu_cadastro(dados: MeuProfissionalIn, ctx: Ctx):
    """Nome, celular, nascimento e CREFITO do próprio profissional. E-mail, comissão, perfil e situação só pelo cadastro."""
    p = _meu(ctx)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sua conta não está vinculada a um profissional.")
    antes = audit.snapshot(p)
    for k, v in dados.model_dump().items():
        setattr(p, k, v)
    ctx.db.flush()
    vinculo_usuario.sincronizar_usuario(ctx.db, p, ctx.usuario)
    a, d = audit.diff(antes, audit.snapshot(p))
    ctx.auditar("profissional.alterar_proprio", "profissional", p.id, descricao=p.nome, antes=a, depois=d)
    ctx.db.commit()
    return _meu_out(p)


# ------------------------------------------------------------------------------------------------------------ CRUD
@router.get("", response_model=PaginaCad[ProfissionalOut])
def listar(
    ctx: Ctx,
    q: str | None = None,
    situacao: Situacao = "todos",
    acesso: Annotated[str, Query(pattern="^(todos|com|sem)$")] = "todos",
    ordenar: str | None = None,
    direcao: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
):
    filtros = []
    if q and q.strip():
        like = comum.like(q)
        cond = [Profissional.nome.ilike(like, escape="\\"), Profissional.email.ilike(like, escape="\\"),
                Profissional.crefito.ilike(like, escape="\\"), Usuario.login.ilike(like, escape="\\")]
        digitos = "".join(c for c in q if c.isdigit())
        if len(digitos) >= 4:
            cond.append(Profissional.celular.like(f"%{digitos}%"))
        filtros.append(or_(*cond))
    if acesso == "com":
        filtros.append(Usuario.acesso_sistema.is_(True))
    elif acesso == "sem":
        filtros.append(or_(Usuario.id.is_(None), Usuario.acesso_sistema.is_(False)))

    def juntar(consulta):
        return consulta.select_from(Profissional).outerjoin(Usuario, Usuario.id == Profissional.usuario_id)

    contagens = comum.contar_situacoes(ctx.db, Profissional.id, Profissional.ativo, filtros, joins=juntar)
    sit = comum.filtro_situacao(Profissional.ativo, situacao)
    onde = filtros + ([sit] if sit is not None else [])
    total = ctx.db.scalar(juntar(select(func.count(Profissional.id))).where(*onde)) or 0
    linhas = ctx.db.execute(
        select(Profissional, Usuario, PerfilAcesso)
        .outerjoin(Usuario, Usuario.id == Profissional.usuario_id)
        .outerjoin(PerfilAcesso, PerfilAcesso.id == Usuario.perfil_acesso_id)
        .where(*onde)
        .order_by(comum.ordenar_por(_ORDEM, ordenar, direcao, "nome"), Profissional.id)
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    ).all()
    itens = [_out(ctx.db, p, u, perfil if (u is not None and u.acesso_sistema) else None) for p, u, perfil in linhas]
    return PaginaCad[ProfissionalOut](itens=itens, total=total, pagina=pagina, por_pagina=por_pagina, contagens=contagens)


@router.get("/{profissional_id}", response_model=ProfissionalOut)
def ler(profissional_id: int, ctx: Ctx):
    return _out(ctx.db, _obter(ctx, profissional_id))


@router.post("", response_model=ProfissionalOut, status_code=201)
def criar(dados: ProfissionalIn, ctx: Ctx):
    """Cria o profissional. Com `acesso_sistema=true` cria também o usuário (login próprio) e envia o convite."""
    perfil = None
    if dados.acesso_sistema:
        ctx.exigir("usuarios.editar")
        if not dados.email:
            raise HTTPException(422, "Informe o e-mail do profissional: ele é o login de acesso ao sistema.")
        if not dados.ativo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Um profissional inativo não pode ter acesso ao sistema.")
        perfil = vinculo_usuario.perfil_ou_404(ctx.db, dados.perfil_acesso_id)
        vinculo_usuario.login_livre(ctx.db, vinculo_usuario.normalizar_login(dados.login))
        vinculo_usuario.email_do_usuario_livre(ctx.db, dados.email)
    _email_livre(ctx, dados.email)
    p = Profissional(
        **dados.model_dump(exclude={"acesso_sistema", "perfil_acesso_id", "email", "login"}),
        email=dados.email.lower() if dados.email else None,
        codigo_legado=proximo_codigo(ctx.db, "profissional"))
    ctx.db.add(p)
    ctx.db.flush()
    u, convite = None, None
    if perfil is not None:
        u, convite = vinculo_usuario.conceder_acesso(ctx.db, p, perfil, dados.login)
        ctx.auditar("usuario.criar", "usuario", u.id, descricao=f"{u.nome} ({perfil.nome}), via cadastro de profissional",
                    depois=audit.snapshot(u))
    ctx.auditar("profissional.criar", "profissional", p.id, descricao=p.nome + (" (com acesso ao sistema)" if u else ""),
                depois=audit.snapshot(p))
    ctx.db.commit()
    return _out(ctx.db, p, u, perfil, convite)


@router.put("/{profissional_id}", response_model=ProfissionalOut)
def alterar(profissional_id: int, dados: ProfissionalPut, ctx: Ctx):
    p = _obter(ctx, profissional_id)
    _email_livre(ctx, dados.email, exceto_id=p.id)
    u = ctx.db.get(Usuario, p.usuario_id) if p.usuario_id else None
    troca_perfil = bool(u and u.acesso_sistema and dados.perfil_acesso_id and dados.perfil_acesso_id != u.perfil_acesso_id)
    troca_login = bool(u and u.acesso_sistema and dados.login and dados.login.strip().lower() != (u.login or ""))
    if troca_perfil or troca_login or (u and u.acesso_sistema and (dados.ativo != p.ativo or (dados.email or "").lower() != (p.email or "").lower())):
        ctx.exigir("usuarios.editar")  # mexe no login de alguém: precisa poder gerir usuários
    antes = audit.snapshot(p)
    campos = dados.model_dump(exclude={"acesso_sistema", "perfil_acesso_id", "email", "login"})
    for k, v in campos.items():
        setattr(p, k, v)
    p.email = dados.email.lower() if dados.email else None
    ctx.db.flush()
    mudancas = vinculo_usuario.sincronizar_usuario(ctx.db, p, ctx.usuario, perfil_id=dados.perfil_acesso_id if troca_perfil else None,
                                                      login=dados.login if troca_login else None)
    a, d = audit.diff(antes, audit.snapshot(p))
    ctx.auditar("profissional.alterar", "profissional", p.id, descricao=p.nome, antes=a, depois=d)
    if mudancas:
        ctx.auditar("usuario.alterar", "usuario", p.usuario_id, descricao=f"{p.nome}: sincronizado pelo cadastro de profissional ({', '.join(mudancas)})")
    ctx.db.commit()
    return _out(ctx.db, p)


@router.post("/{profissional_id}/acesso", response_model=ProfissionalOut)
def dar_acesso(profissional_id: int, dados: AcessoIn, ctx: Ctx):
    """Cria o usuário (login próprio) com o perfil escolhido e envia o convite para definir a senha."""
    ctx.exigir("usuarios.editar")
    p = _obter(ctx, profissional_id)
    perfil = vinculo_usuario.perfil_ou_404(ctx.db, dados.perfil_acesso_id)
    u, convite = vinculo_usuario.conceder_acesso(ctx.db, p, perfil, dados.login)
    ctx.auditar("profissional.dar_acesso", "profissional", p.id, descricao=f"{p.nome}: acesso ao sistema com o perfil {perfil.nome}")
    ctx.auditar("usuario.criar", "usuario", u.id, descricao=f"{u.nome} ({perfil.nome}), via cadastro de profissional")
    ctx.db.commit()
    return _out(ctx.db, p, u, perfil, convite)


@router.post("/{profissional_id}/acesso/convite", response_model=ProfissionalOut)
def reenviar_convite(profissional_id: int, ctx: Ctx):
    ctx.exigir("usuarios.editar")
    p = _obter(ctx, profissional_id)
    u = ctx.db.get(Usuario, p.usuario_id) if p.usuario_id else None
    if not u or not u.acesso_sistema or not u.ativo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este profissional não tem acesso ao sistema.")
    enviado = vinculo_usuario._enviar_convite(ctx.db, u)
    if not enviado:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Não foi possível enviar o e-mail. Confira a configuração de e-mail.")
    u.convite_pendente = u.convite_pendente or not u.senha_hash
    ctx.auditar("usuario.redefinir_senha", "usuario", u.id, descricao=f"Convite reenviado a {u.nome}")
    ctx.db.commit()
    return _out(ctx.db, p, u, convite_enviado=True)


@router.delete("/{profissional_id}/acesso", response_model=ProfissionalOut)
def revogar_acesso(profissional_id: int, ctx: Ctx):
    """Tira o acesso ao sistema; o profissional continua cadastrado e as sessões abertas caem."""
    ctx.exigir("usuarios.editar")
    p = _obter(ctx, profissional_id)
    u = vinculo_usuario.revogar_acesso(ctx.db, p, ctx.usuario)
    ctx.auditar("profissional.revogar_acesso", "profissional", p.id, descricao=f"{p.nome}: acesso ao sistema revogado")
    ctx.auditar("usuario.desativar", "usuario", u.id, descricao=f"{u.nome}: acesso revogado pelo cadastro de profissional")
    ctx.db.commit()
    return _out(ctx.db, p, u)


@router.post("/{profissional_id}/ativar", response_model=ProfissionalOut)
def ativar(profissional_id: int, ctx: Ctx):
    return _definir_ativo(ctx, profissional_id, True)


@router.post("/{profissional_id}/desativar", response_model=ProfissionalOut)
def desativar(profissional_id: int, ctx: Ctx):
    return _definir_ativo(ctx, profissional_id, False)


def _definir_ativo(ctx, profissional_id: int, ativo: bool) -> ProfissionalOut:
    p = _obter(ctx, profissional_id)
    if p.ativo != ativo:
        u = ctx.db.get(Usuario, p.usuario_id) if p.usuario_id else None
        if u and u.acesso_sistema:
            ctx.exigir("usuarios.editar")
        antes = audit.snapshot(p)
        p.ativo = ativo
        ctx.db.flush()
        vinculo_usuario.sincronizar_usuario(ctx.db, p, ctx.usuario)
        a, d = audit.diff(antes, audit.snapshot(p))
        ctx.auditar(f"profissional.{'ativar' if ativo else 'desativar'}", "profissional", p.id, descricao=p.nome, antes=a, depois=d)
        ctx.db.commit()
    return _out(ctx.db, p)


@router.get("/{profissional_id}/vinculos", response_model=VinculosOut)
def ver_vinculos(profissional_id: int, ctx: Ctx):
    _obter(ctx, profissional_id)
    return comum.vinculos_out(ctx.db, Profissional, profissional_id)


@router.delete("/{profissional_id}", response_model=Mensagem)
def excluir(profissional_id: int, ctx: Ctx):
    """Exclui só quem não tem aulas, comissões etc. O usuário vinculado (se houver) perde o acesso e é desativado."""
    p = _obter(ctx, profissional_id)
    comum.bloquear_se_vinculado(ctx.db, Profissional, p.id, "o profissional")
    u = ctx.db.get(Usuario, p.usuario_id) if p.usuario_id else None
    if u is not None and u.acesso_sistema:
        ctx.exigir("usuarios.editar")
        vinculo_usuario.revogar_acesso(ctx.db, p, ctx.usuario)
    if u is not None:
        u.ativo = False
        svc.invalidar_sessoes(ctx.db, u)
    snap, nome = audit.snapshot(p), p.nome
    try:
        ctx.db.delete(p)
        ctx.auditar("profissional.excluir", "profissional", profissional_id, descricao=nome + (" (usuário vinculado desativado)" if u else ""), antes=snap)
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível excluir o profissional: ele está em uso. Desative-o em vez de excluir.") from None
    return Mensagem(mensagem=f"Profissional {nome} excluído.")
