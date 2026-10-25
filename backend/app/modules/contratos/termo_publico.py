"""Termo de uso de imagem do aluno: link de assinatura (30 dias) e página pública `/assinar/termo/[token]`.

PONTO DE EXTENSÃO para o coordenador (não editamos o módulo `alunos`): `alunos.servico.gerar_link_assinatura_termo(a)`
hoje levanta `NotImplementedError`. Para ligar, uma vez, na subida do app (por exemplo no `main.py`/`routes` do coordenador):

    from app.modules.contratos import termo_publico
    termo_publico.registrar_no_modulo_alunos()

Isso troca a função do `alunos.servico` por `gerar_link_assinatura_termo` deste arquivo (devolve a URL completa).

Mesmos cuidados do contrato (ver `publico.py`): token com prazo (novo) ou antigo do Django (sal `termo-assinatura`),
resposta genérica para link inválido, GET sem efeito colateral, assinatura gravada uma única vez e CPF validado.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import audit, storage
from app.core.db import agora
from app.core.deps import Contexto
from app.modules.alunos import servico as alunos_servico
from app.modules.alunos.models import Aluno
from app.modules.cadastros.html_seguro import HtmlGrandeDemais, sanitizar
from app.modules.cadastros.models import TermoUso
from app.modules.contratos import schemas as sc
from app.modules.contratos import servico, tokens

log = logging.getLogger(__name__)

MSG_INVALIDO = "Link inválido. Peça um novo link ao estúdio."
MSG_EXPIRADO = "Este link expirou. Peça um novo link ao estúdio."


def _base_site() -> str:
    return servico._base_site()


def link_do_aluno(aluno_id: int, *, agora_s: float | None = None) -> sc.LinkOut:
    t = tokens.emitir_termo(aluno_id, agora_s=agora_s)
    return sc.LinkOut(url=f"{_base_site()}/assinar/termo/{t.token}", expira_em=t.expira_em, pdf_url="")


def gerar_link_assinatura_termo(a: Aluno) -> str:
    """Substituta de `alunos.servico.gerar_link_assinatura_termo`: URL completa da página pública (vale 30 dias)."""
    return link_do_aluno(a.id).url


def registrar_no_modulo_alunos() -> None:
    """Liga `gerar_link_assinatura_termo` real no `alunos.servico` (chamar uma vez na subida)."""
    alunos_servico.gerar_link_assinatura_termo = gerar_link_assinatura_termo  # type: ignore[assignment]


def _termo_do(db: Session, a: Aluno) -> TermoUso | None:
    if a.termo_uso_id:
        t = db.get(TermoUso, a.termo_uso_id)
        if t:
            return t
    return db.scalar(select(TermoUso).order_by(TermoUso.id).limit(1))


def aluno_do_token(db: Session, token: str) -> Aluno:
    try:
        lido = tokens.ler_termo(token)
    except tokens.LinkExpirado:
        raise servico.ErroContrato(MSG_EXPIRADO, 410) from None
    except tokens.LinkInvalido:
        raise servico.ErroContrato(MSG_INVALIDO, 404) from None
    a = db.get(Aluno, lido.sujeito_id)
    if a is None:
        raise servico.ErroContrato(MSG_INVALIDO, 404)
    return a


def _html_seguro(html: str) -> str:
    try:
        return sanitizar(html)
    except HtmlGrandeDemais:
        return html


def visualizar(db: Session, token: str) -> sc.TermoPublico:
    a = aluno_do_token(db, token)
    base = dict(estudio_nome=servico.nome_do_estudio(db), aluno_primeiro_nome=servico.primeiro_nome(a.nome))
    if a.termo_assinado_em is not None:
        return sc.TermoPublico(estado="assinado", assinado_em=a.termo_assinado_em, **base)
    termo = _termo_do(db, a)
    if termo is None:
        raise servico.ErroContrato("O termo ainda não está disponível. Fale com o estúdio.", 409)
    return sc.TermoPublico(estado="pendente", termo_nome=termo.nome,
                           html=_html_seguro(alunos_servico.renderizar_termo_html(db, termo, a)), **base)


def assinar(db: Session, token: str, dados: sc.AssinarPublicoIn, ip: str | None) -> sc.AssinadoOut:
    if not dados.li_e_concordo:
        raise servico.ErroContrato("Para assinar é preciso confirmar que leu e concorda com o termo.", 422)
    a = aluno_do_token(db, token)
    if a.termo_assinado_em is not None:
        raise servico.ErroContrato("O termo já foi assinado.", 409)
    termo = _termo_do(db, a)
    if termo is None:
        raise servico.ErroContrato("O termo ainda não está disponível. Fale com o estúdio.", 409)
    nome, documento = servico.validar_assinante(dados.nome, dados.documento)
    png = servico.decodificar_png(dados.assinatura)
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise servico.ErroContrato("A assinatura deve ser uma imagem PNG.", 422)
    ip = (ip or "")[:45] or None
    quando = agora()
    rel = f"{alunos_servico.CAT_ALUNOS}/termo/termo_{a.id}.png"
    r = db.execute(update(Aluno).where(Aluno.id == a.id, Aluno.termo_assinado_em.is_(None)).values(
        termo_uso_id=termo.id, termo_assinatura_nome=nome, termo_assinatura_documento=documento, termo_assinatura_ip=ip,
        termo_assinatura_path=rel, autoriza_imagem=True, termo_aceite_em=quando, termo_assinado_em=quando, atualizado_em=quando))
    if r.rowcount != 1:
        db.rollback()
        raise servico.ErroContrato("O termo já foi assinado.", 409)
    try:
        storage.salvar(alunos_servico.CAT_ALUNOS, "assinatura.png", png, subpasta="termo", nome_base=f"termo_{a.id}", substituir=True)
    except storage.ArquivoInvalido as e:
        db.rollback()
        raise servico.ErroContrato(str(e), 422) from e
    audit.registrar(db, usuario=None, acao="aluno.termo.assinar_link", entidade="aluno", entidade_id=a.id,
                    descricao=f"Termo \"{termo.nome}\" assinado por link por {nome}",
                    depois={"termo_uso_id": termo.id, "assinatura_nome": nome, "ip": ip}, ip=ip)
    db.commit()
    _notificar(db, a, termo)
    return sc.AssinadoOut(mensagem="Termo assinado com sucesso. Obrigado!", assinado_em=quando)


def _notificar(db: Session, a: Aluno, termo: TermoUso) -> None:
    """Confirmação ao aluno (e-mail e WhatsApp pelo ponto de extensão). Nunca levanta."""
    try:
        db.refresh(a)
        estudio = servico.nome_do_estudio(db)
        if (a.email or "").strip():
            servico.core_email.enviar([a.email.strip()], f"Termo de uso de imagem assinado - {estudio}",
                                      f"Olá, {servico.primeiro_nome(a.nome)}!\n\nRecebemos a assinatura do termo \"{termo.nome}\".\n\n{estudio}", db=db)
        telefone = alunos_servico.telefone_principal(db, a.id)
        if servico.whatsapp_disponivel() and telefone:
            servico._enviar_whatsapp(db, servico.MensagemWhatsapp(
                tipo="termo_assinado", aluno_id=a.id, telefone=telefone,
                texto=f"Olá, {servico.primeiro_nome(a.nome)}! Recebemos a assinatura do termo de uso de imagem. Obrigado! {estudio}"))
    except Exception:  # noqa: BLE001 - cortesia: a assinatura já valeu
        log.warning("Não foi possível enviar a confirmação do termo do aluno %s", a.id, exc_info=True)


# ---------------------------------------------------------------------------------- protegidas (usuário do estúdio)
def criar_link(ctx: Contexto, aluno_id: int) -> sc.LinkOut:
    a = ctx.db.get(Aluno, aluno_id)
    if a is None:
        raise servico.ErroContrato("Aluno não encontrado.", 404)
    if a.termo_assinado_em is not None:
        raise servico.ErroContrato("O termo deste aluno já está assinado.", 409)
    if _termo_do(ctx.db, a) is None:
        raise servico.ErroContrato("Nenhum termo cadastrado. Cadastre em Cadastros > Termos.", 409)
    link = link_do_aluno(a.id)
    ctx.auditar("aluno.termo.link", "aluno", a.id, descricao=f"Link de assinatura do termo de {a.nome} gerado")
    ctx.db.commit()
    return link


def enviar(ctx: Contexto, aluno_id: int, canal: str) -> sc.EnvioOut:
    link = criar_link(ctx, aluno_id)
    a = ctx.db.get(Aluno, aluno_id)
    estudio = servico.nome_do_estudio(ctx.db)
    primeiro = servico.primeiro_nome(a.nome)
    if canal == "email":
        if not (a.email or "").strip():
            raise servico.ErroContrato("O aluno não tem e-mail cadastrado.", 422)
        ok = servico.core_email.enviar([a.email.strip()], f"Termo de uso de imagem - {estudio}",
                                       f"Olá, {primeiro}!\n\nPara assinar o termo de uso de imagem, acesse:\n{link.url}\n\n"
                                       f"O link vale por 30 dias.\n\n{estudio}", db=ctx.db)
        if not ok:
            raise servico.ErroContrato("Não foi possível enviar o e-mail agora.", 502)
        destino = a.email.strip()
    else:
        if not servico.whatsapp_disponivel():
            raise servico.ErroContrato("WhatsApp ainda não configurado.", 503)
        telefone = alunos_servico.telefone_principal(ctx.db, a.id)
        if not telefone:
            raise servico.ErroContrato("O aluno não tem telefone cadastrado.", 422)
        servico._enviar_whatsapp(ctx.db, servico.MensagemWhatsapp(
            tipo="termo_assinatura", aluno_id=a.id, telefone=telefone, link=link.url,
            texto=f"Olá, {primeiro}! Para assinar o termo de uso de imagem, acesse (vale por 30 dias): {link.url} - {estudio}"))
        destino = alunos_servico.formatar_telefone(telefone)
    ctx.auditar("aluno.termo.enviar", "aluno", a.id, descricao=f"Link do termo de {a.nome} enviado por {canal}")
    ctx.db.commit()
    return sc.EnvioOut(canal=canal, destino=destino, mensagem="Link do termo enviado.")  # type: ignore[arg-type]
