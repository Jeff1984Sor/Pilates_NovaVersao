"""Assinatura de contrato por LINK (páginas públicas, sem login). R10.

Cuidados (esta é a única porta do contrato aberta sem login):
- o link é a credencial: token com HMAC e prazo de 7 dias (novo) ou token antigo do Django (`LEGACY_DJANGO_SECRET_KEY`);
- token inválido, adulterado, de outra finalidade ou de contrato inexistente dão a MESMA resposta (404 "Link inválido.");
  expirado dá 410; nunca se revela se o contrato existe nem nada dele;
- GET não tem efeito colateral nenhum (nem regrava o documento, como o antigo fazia);
- contrato já assinado NÃO devolve o texto (só "já foi assinado") e não assina de novo (a gravação é condicional);
- o rate limit fica nas rotas (`routes.router_publico`).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import agora
from app.modules.cadastros.html_seguro import HtmlGrandeDemais, sanitizar
from app.modules.contratos import schemas as sc
from app.modules.contratos import servico, tokens
from app.modules.contratos.models import Contrato, StatusAssinatura

MSG_INVALIDO = "Link inválido. Peça um novo link ao estúdio."
MSG_EXPIRADO = "Este link expirou. Peça um novo link ao estúdio."


def contrato_do_token(db: Session, token: str) -> Contrato:
    """Valida o token e devolve o contrato. Erros genéricos (`ErroContrato` 404/410)."""
    try:
        lido = tokens.ler_contrato(token)
    except tokens.LinkExpirado:
        raise servico.ErroContrato(MSG_EXPIRADO, 410) from None
    except tokens.LinkInvalido:
        raise servico.ErroContrato(MSG_INVALIDO, 404) from None
    c = db.get(Contrato, lido.sujeito_id)
    if c is None:
        raise servico.ErroContrato(MSG_INVALIDO, 404)
    return c


def _html_seguro(html: str) -> str:
    try:
        return sanitizar(html)
    except HtmlGrandeDemais:
        return html


def visualizar(db: Session, token: str) -> sc.ContratoPublico:
    """O que a página mostra. Só LÊ."""
    c = contrato_do_token(db, token)
    aluno = servico.db_aluno(db, c)
    base = dict(estudio_nome=servico.nome_do_estudio(db), numero=servico.numero_do_contrato(c),
                aluno_primeiro_nome=servico.primeiro_nome(aluno.nome if aluno else ""))
    if servico.status_val(c.status_assinatura) != StatusAssinatura.NAO_ASSINADO:
        return sc.ContratoPublico(estado="assinado", assinado_em=c.assinado_em, **base)
    return sc.ContratoPublico(estado="pendente", html=_html_seguro(servico.html_do_contrato(db, c)), **base)


def pdf(db: Session, token: str) -> tuple[bytes, str]:
    """PDF do contrato (com a assinatura, se houver) gerado na hora. NÃO grava nada: GET sem efeito colateral."""
    c = contrato_do_token(db, token)
    return servico.gerar_pdf_do_contrato(db, c), f"contrato-{servico.numero_do_contrato(c)}.pdf"


def assinar(db: Session, token: str, dados: sc.AssinarPublicoIn, ip: str | None) -> sc.AssinadoOut:
    if not dados.li_e_concordo:
        raise servico.ErroContrato("Para assinar é preciso confirmar que leu e concorda com o contrato.", 422)
    c = contrato_do_token(db, token)
    if servico.status_val(c.status_assinatura) != StatusAssinatura.NAO_ASSINADO:
        raise servico.ErroContrato("Este contrato já foi assinado.", 409)
    ip = (ip or "")[:45] or None
    servico.aplicar_assinatura(db, c, nome=dados.nome, documento=dados.documento, assinatura_png=dados.assinatura, ip=ip,
                               status=StatusAssinatura.ASSINADO_DIGITALMENTE)
    audit.registrar(db, usuario=None, acao="contrato.assinar_link", entidade="contrato", entidade_id=c.id,
                    descricao=f"Contrato nº {servico.numero_do_contrato(c)} assinado digitalmente por link por {c.assinatura_nome}",
                    depois={"nome": c.assinatura_nome, "documento": c.assinatura_documento, "ip": ip}, ip=ip)
    db.commit()
    servico.atualizar_pdf_guardado(db, c)
    db.commit()
    servico.notificar_assinatura(db, c)
    return sc.AssinadoOut(mensagem="Contrato assinado com sucesso. Obrigado!", assinado_em=c.assinado_em or agora())
