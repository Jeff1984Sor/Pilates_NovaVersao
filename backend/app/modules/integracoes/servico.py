"""Regras de aplicação das telas de integrações: tokens de API e configuração do TotalPass (por unidade).

Estável para outros módulos: `tokens_*`/`totalpass_*` (todas recebem o `Contexto`; quem chama não precisa de mais nada).
Segredos: cifrados (`totalpass.cifrar`), somente escrita; a auditoria registra QUE mudou, nunca o valor.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core import audit
from app.core.deps import Contexto
from app.domain.documentos import so_digitos
from app.modules.cadastros.models import IntegracaoToken, TipoServico, Unidade
from app.modules.integracoes import schemas as sc
from app.modules.integracoes import tokens, totalpass
from app.modules.integracoes.models import TotalpassConfig, TotalpassEvento

CAMPOS_PUBLICOS = ("ativo", "place_id", "criar_aluno_automatico", "somente_dia", "servico_padrao_id", "sync_ativo")
SEGREDOS = ("partner_api_key", "place_api_key", "webhook_token")


def erro(codigo: int, mensagem: str) -> HTTPException:
    return HTTPException(codigo, mensagem)


# ------------------------------------------------------------------------------------------------ tokens de API
def token_out(t: IntegracaoToken) -> sc.TokenOut:
    return sc.TokenOut.model_validate(t)


def _token(ctx: Contexto, token_id: int) -> IntegracaoToken:
    t = ctx.db.get(IntegracaoToken, token_id)
    if t is None:
        raise erro(404, "Token não encontrado.")
    return t


def tokens_listar(ctx: Contexto) -> list[sc.TokenOut]:
    return [token_out(t) for t in ctx.db.scalars(
        select(IntegracaoToken).order_by(IntegracaoToken.precisa_regenerar.desc(), IntegracaoToken.nome, IntegracaoToken.id))]


def tokens_criar(ctx: Contexto, nome: str) -> sc.TokenComValorOut:
    t, valor = tokens.criar(ctx.db, nome)
    ctx.auditar("integracao_token.criar", "integracao_token", t.id, descricao=f"Token '{t.nome}' criado (final {t.token_final})")
    ctx.db.commit()
    return sc.TokenComValorOut(**token_out(t).model_dump(), valor=valor)


def tokens_editar(ctx: Contexto, token_id: int, dados: sc.TokenEditarIn) -> sc.TokenOut:
    t = _token(ctx, token_id)
    antes = {"nome": t.nome, "ativo": t.ativo}
    if dados.ativo is not None and dados.ativo and t.precisa_regenerar:
        raise erro(409, "Este token veio do sistema antigo sem o valor. Regenere o token antes de ativá-lo.")
    if dados.nome is not None:
        t.nome = dados.nome.strip()
    if dados.ativo is not None:
        t.ativo = dados.ativo
    depois = {"nome": t.nome, "ativo": t.ativo}
    if antes != depois:
        acao = ("integracao_token.ativar" if t.ativo else "integracao_token.desativar") if antes["ativo"] != t.ativo \
            else "integracao_token.renomear"
        ctx.auditar(acao, "integracao_token", t.id, descricao=f"Token '{t.nome}'", antes=antes, depois=depois)
    ctx.db.commit()
    return token_out(t)


def tokens_regenerar(ctx: Contexto, token_id: int) -> sc.TokenComValorOut:
    t = _token(ctx, token_id)
    valor = tokens.regenerar(ctx.db, t)
    ctx.auditar("integracao_token.regenerar", "integracao_token", t.id,
                descricao=f"Token '{t.nome}' regenerado (novo final {t.token_final}); o valor anterior deixou de valer")
    ctx.db.commit()
    return sc.TokenComValorOut(**token_out(t).model_dump(), valor=valor)


def tokens_excluir(ctx: Contexto, token_id: int) -> None:
    t = _token(ctx, token_id)
    ctx.auditar("integracao_token.excluir", "integracao_token", t.id, descricao=f"Token '{t.nome}' excluído")
    ctx.db.delete(t)
    ctx.db.commit()


# ------------------------------------------------------------------------------------------------ TotalPass: configuração
def _config_out(u: Unidade, c: TotalpassConfig | None) -> sc.TotalpassConfigOut:
    def seg(valor: str | None) -> sc.SegredoOut:
        return sc.SegredoOut(definido=bool(valor), final=totalpass.final_do_segredo(valor))

    return sc.TotalpassConfigOut(
        unidade_id=u.id, unidade_nome=u.nome, configurada=c is not None, ativo=c.ativo if c else True,
        place_id=c.place_id if c else None, criar_aluno_automatico=c.criar_aluno_automatico if c else True,
        somente_dia=c.somente_dia if c else True, servico_padrao_id=c.servico_padrao_id if c else None,
        sync_ativo=bool(c and c.sync_ativo), sync_ultimo_em=c.sync_ultimo_em if c else None,
        sync_ultimo_resumo=c.sync_ultimo_resumo if c else None,
        partner_api_key=seg(c.partner_api_key_cifrado if c else None), place_api_key=seg(c.place_api_key_cifrado if c else None),
        webhook_token=seg(c.webhook_token_cifrado if c else None),
    )


def totalpass_tela(ctx: Contexto) -> sc.TotalpassTelaOut:
    db = ctx.db
    unidades = list(db.scalars(select(Unidade).where(Unidade.ativo.is_(True)).order_by(Unidade.nome, Unidade.id)))
    configs = {c.unidade_id: c for c in db.scalars(select(TotalpassConfig))}
    servicos = db.scalars(select(TipoServico).where(TipoServico.ativo.is_(True)).order_by(TipoServico.nome))
    return sc.TotalpassTelaOut(
        webhook_caminho="/api/webhooks/totalpass",
        configuracoes=[_config_out(u, configs.get(u.id)) for u in unidades],
        servicos=[sc.ServicoOpcao(id=s.id, nome=s.nome) for s in servicos],
    )


def config_da_unidade(ctx: Contexto, unidade_id: int, *, criar: bool = False) -> tuple[Unidade, TotalpassConfig | None]:
    u = ctx.db.get(Unidade, unidade_id)
    if u is None:
        raise erro(404, "Unidade não encontrada.")
    c = ctx.db.scalar(select(TotalpassConfig).where(TotalpassConfig.unidade_id == unidade_id))
    if c is None and criar:
        c = TotalpassConfig(unidade_id=unidade_id, ativo=True, criar_aluno_automatico=True, somente_dia=True, sync_ativo=False)
        ctx.db.add(c)
        ctx.db.flush()
    return u, c


def _fotografia(c: TotalpassConfig) -> dict:
    snap = {k: getattr(c, k) for k in CAMPOS_PUBLICOS}
    snap.update({f"{k}_definido": bool(getattr(c, f"{k}_cifrado")) for k in SEGREDOS})
    return snap


def totalpass_salvar(ctx: Contexto, unidade_id: int, dados: sc.TotalpassConfigIn) -> sc.TotalpassConfigOut:
    u, c = config_da_unidade(ctx, unidade_id, criar=True)
    assert c is not None
    antes = _fotografia(c)
    if dados.servico_padrao_id is not None and ctx.db.get(TipoServico, dados.servico_padrao_id) is None:
        raise erro(422, "Serviço padrão não encontrado.")
    for campo in ("ativo", "criar_aluno_automatico", "somente_dia", "servico_padrao_id", "sync_ativo"):
        setattr(c, campo, getattr(dados, campo))
    c.place_id = (dados.place_id or "").strip() or None
    alterados = []
    for nome in SEGREDOS:
        novo = (getattr(dados, nome) or "").strip()
        if nome in dados.limpar:
            setattr(c, f"{nome}_cifrado", None)
            alterados.append(f"{nome}: removido")
        elif novo:
            setattr(c, f"{nome}_cifrado", totalpass.cifrar(novo))
            alterados.append(f"{nome}: alterado")
    if c.sync_ativo and not (c.partner_api_key_cifrado and c.place_api_key_cifrado):
        raise erro(422, "Para ligar a sincronização, cadastre a chave do parceiro e a chave da unidade.")
    ctx.db.flush()
    depois = _fotografia(c)
    a, d = audit.diff(antes, depois)
    ctx.auditar("totalpass.configurar", "totalpass_config", c.id, antes=a, depois=d,
                descricao=f"TotalPass da unidade {u.nome}" + (f" ({'; '.join(alterados)})" if alterados else ""))
    ctx.db.commit()
    return _config_out(u, c)


def totalpass_gerar_token_webhook(ctx: Contexto, unidade_id: int) -> sc.WebhookTokenOut:
    u, c = config_da_unidade(ctx, unidade_id, criar=True)
    assert c is not None
    valor = "tpw_" + secrets.token_urlsafe(32)
    c.webhook_token_cifrado = totalpass.cifrar(valor)
    ctx.auditar("totalpass.gerar_token_webhook", "totalpass_config", c.id,
                descricao=f"Novo token do webhook gerado para a unidade {u.nome} (final {valor[-4:]})")
    ctx.db.commit()
    return sc.WebhookTokenOut(valor=valor, final=valor[-4:])


def totalpass_testar(ctx: Contexto, unidade_id: int) -> str:
    u, c = config_da_unidade(ctx, unidade_id)
    if c is None:
        raise erro(409, "Salve a configuração do TotalPass antes de testar a conexão.")
    try:
        totalpass.testar_conexao(c)
    except totalpass.ErroTotalpass as e:
        ctx.auditar("totalpass.testar_conexao", "totalpass_config", c.id, descricao=f"Teste de conexão falhou ({u.nome})")
        ctx.db.commit()
        raise erro(502, str(e)) from None
    ctx.auditar("totalpass.testar_conexao", "totalpass_config", c.id, descricao=f"Teste de conexão OK ({u.nome})")
    ctx.db.commit()
    return "Conexão com o TotalPass OK: as chaves foram aceitas."


def totalpass_sincronizar(ctx: Contexto, unidade_id: int, dados: sc.SincronizarIn) -> sc.ResumoSyncOut:
    from app.core.db import agora
    from app.domain.financeiro import hoje_de_negocio

    u, c = config_da_unidade(ctx, unidade_id)
    if c is None:
        raise erro(409, "Salve a configuração do TotalPass antes de sincronizar.")
    dia = dados.dia or hoje_de_negocio(agora())
    try:
        resumo = totalpass.sincronizar_dia(ctx.db, c, dia)
    except totalpass.ErroTotalpass as e:
        raise erro(502, str(e)) from None
    texto = totalpass.resumo_texto(resumo)
    totalpass.registrar_sync(ctx.db, c, texto)
    ctx.auditar("totalpass.sincronizar", "totalpass_config", c.id, descricao=f"Sincronização manual ({u.nome}) {texto}")
    ctx.db.commit()
    return sc.ResumoSyncOut(resumo=texto, **{**resumo, "dia": dia})


# ------------------------------------------------------------------------------------------------ TotalPass: eventos
def _mascarar_documento(d: str | None) -> str | None:
    digitos = so_digitos(d)
    if not digitos:
        return None
    return "•••.•••.•••-" + digitos[-2:] if len(digitos) == 11 else "•" * max(len(digitos) - 2, 0) + digitos[-2:]


def _resultado(e: TotalpassEvento) -> str:
    if e.resultado:
        return e.resultado
    if e.erro:
        return "erro"
    return "processado" if e.processado_em else "pendente"


def evento_out(e: TotalpassEvento) -> sc.EventoOut:
    p = e.payload if isinstance(e.payload, dict) else {}
    ev = p.get("event") if isinstance(p.get("event"), dict) else {}
    slot = p.get("slot") if isinstance(p.get("slot"), dict) else {}
    dia = str(slot.get("date") or slot.get("start_at") or slot.get("startAt") or "")[:10]
    hora = str(slot.get("start_time") or slot.get("startTime") or slot.get("time") or "")
    return sc.EventoOut(
        id=e.id, recebido_em=e.recebido_em, processado_em=e.processado_em, origem=e.origem, event_id=e.event_id,
        slot_id=e.slot_id, documento_mascarado=_mascarar_documento(e.documento_usuario), status=e.status,
        titulo=str(ev.get("title") or "")[:120] or None, aula_em=(f"{dia} {hora}".strip() or None),
        resultado=_resultado(e), erro=e.erro, reserva_id=e.reserva_id,
    )


def totalpass_eventos(ctx: Contexto, *, resultado: str | None, pagina: int, por_pagina: int) -> sc.ListaEventosOut:
    consulta = select(TotalpassEvento)
    if resultado == "erro":
        consulta = consulta.where((TotalpassEvento.resultado == "erro") | (TotalpassEvento.resultado.is_(None) & TotalpassEvento.erro.is_not(None)))
    elif resultado == "pendente":
        consulta = consulta.where(TotalpassEvento.resultado.is_(None), TotalpassEvento.erro.is_(None), TotalpassEvento.processado_em.is_(None))
    elif resultado == "processado":
        consulta = consulta.where((TotalpassEvento.resultado == "processado") | (
            TotalpassEvento.resultado.is_(None) & TotalpassEvento.erro.is_(None) & TotalpassEvento.processado_em.is_not(None)))
    elif resultado:
        consulta = consulta.where(TotalpassEvento.resultado == resultado)
    total = ctx.db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = ctx.db.scalars(consulta.order_by(TotalpassEvento.recebido_em.desc(), TotalpassEvento.id.desc())
                           .offset((pagina - 1) * por_pagina).limit(por_pagina))
    return sc.ListaEventosOut(total=total, pagina=pagina, por_pagina=por_pagina, itens=[evento_out(e) for e in itens])
