"""Rotas do módulo de comunicação (WhatsApp). Descobertas pelo ``main.py``.

Permissões (todas pelo mapa do core; ``adicionar_regras`` só acrescenta o que foge do padrão):
- ``/whatsapp/configuracao/*``  -> ``whatsapp.configurar`` (só o Full tem);
- ``GET /whatsapp/*``           -> ``whatsapp.ver``; ``POST /whatsapp/*`` -> ``whatsapp.enviar``;
- ``GET /comunicacao/*``        -> ``comunicacao.ver``; demais -> ``comunicacao.enviar``.
O perfil Professor não tem nenhuma delas (nega por padrão).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import func, or_, select

from app.core import audit, segredos
from app.core.db import agora
from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.core.schemas import Pagina
from app.domain import whatsapp_avisos as dom
from app.modules.agenda.models import WhatsappAgendamentoLog
from app.modules.alunos.models import Aluno, WhatsappMensagem
from app.modules.cadastros.models import Profissional, Unidade
from app.modules.comunicacao import comunicados as com
from app.modules.comunicacao import schemas as sc
from app.modules.comunicacao import servico as svc
from app.modules.comunicacao.models import Comunicado, ComunicadoDestinatario
from app.modules.financeiro.servico import ErroDeNegocio
from app.modules.integracoes.models import ProvedorWhatsapp, WhatsappConfig


class RotaComunicacao(APIRoute):
    """Converte ``ErroDeNegocio`` em ``{"detail": mensagem}`` com o status certo."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ErroDeNegocio as e:
                return JSONResponse({"detail": e.mensagem}, status_code=e.status)

        return handler


router = APIRouter(route_class=RotaComunicacao, tags=["comunicação"])

adicionar_regras([
    ("*", r"/whatsapp/configuracao", "whatsapp.configurar"),
])

ROTULO_TIPO = {
    "manual": "Mensagem manual", "cobranca": "Cobrança", "comunicado": "Comunicado geral",
    "contract_link": "Link do contrato", "contract_pdf": "Contrato (PDF)", "image_term_link": "Termo de uso de imagem",
    "automated_reminder": "Lembrete de aula", "professor_schedule": "Agenda do professor",
    "contract_renewal": "Renovação de contrato",
    dom.LEMBRETE_ALUNO: "Lembrete de aula", dom.AGENDA_PROFESSOR: "Agenda do professor", dom.RENOVACAO: "Renovação de contrato",
    dom.ANIVERSARIO: "Aniversário", dom.VENCIMENTO: "Vencimento próximo", dom.ATRASO: "Mensalidade em atraso",
    dom.TRES_MESES: "3 meses de aula", "alerta": "Alerta do sistema", "resumo": "Resumo ao gestor",
}
ROTULO_AVISO = {
    dom.LEMBRETE_ALUNO: "Lembrete de aula ao aluno (véspera)", dom.AGENDA_PROFESSOR: "Agenda do professor (véspera)",
    dom.RENOVACAO: "Renovação (7 dias antes do fim)", dom.ANIVERSARIO: "Aniversário", dom.VENCIMENTO: "Vencimento (amanhã)",
    dom.ATRASO: "Atraso (1 vez por semana)", dom.TRES_MESES: "3 meses de aula (90 dias)",
}
ROTULO_TEXTO = {
    "template_aviso_aluno": "Lembrete de aula", "template_aviso_professor": "Agenda do professor",
    "template_link_contrato": "Link do contrato", "template_aviso_renovacao": "Renovação de contrato",
    "template_aniversario": "Aniversário", "template_fim_contrato": "Fim de contrato (proposta de renovação)",
    "template_vencimento_proximo": "Vencimento próximo", "template_mensalidade_atraso": "Mensalidade em atraso / cobrança",
    "template_tres_meses": "3 meses de aula",
}


# =============================================================================================== configuração
def _unidade(ctx: Ctx, unidade_id: int) -> Unidade:
    u = ctx.db.get(Unidade, unidade_id)
    if not u:
        raise ErroDeNegocio("Unidade não encontrada.", 404)
    return u


def _foto(cfg: WhatsappConfig) -> dict[str, Any]:
    """Foto para a auditoria: SEM o valor (nem o cifrado) da credencial."""
    f = audit.snapshot(cfg)
    f.pop("credencial_cifrado", None)
    f["credencial_definida"] = bool(cfg.credencial_cifrado)
    return f


def _config_out(ctx: Ctx, unidade: Unidade, cfg: WhatsappConfig | None) -> sc.ConfigOut:
    db = ctx.db
    existe = cfg is not None
    ref = cfg
    final = None
    if cfg and cfg.credencial_cifrado:
        try:
            final = segredos.decifrar_texto(cfg.credencial_cifrado.encode())[-4:]
        except segredos.SegredoInvalido:
            final = None
    ex = svc.extras(cfg) if cfg else {}
    avisos = []
    for tipo in dom.TIPOS:
        ativo = bool(getattr(ref, svc.CAMPO_ATIVO[tipo])) if ref else False  # sem configuração: tudo desligado
        horario = getattr(ref, svc.CAMPO_HORARIO[tipo]) if ref else dom.HORARIO_PADRAO[tipo]
        avisos.append(sc.AvisoOut(tipo=tipo, rotulo=ROTULO_AVISO[tipo], ativo=ativo, horario=horario or dom.HORARIO_PADRAO[tipo],
                                  campo_texto=dom.CAMPO_TEMPLATE_DO_TIPO[tipo]))
    return sc.ConfigOut(
        unidade_id=unidade.id, unidade_nome=unidade.nome, existe=existe,
        provedor=str(cfg.provedor.value) if cfg else "wasender", url_api=cfg.url_api if cfg else None,
        instancia=cfg.instancia if cfg else None, credencial_definida=bool(cfg and cfg.credencial_cifrado),
        credencial_final=final, acompanhar_envios=bool(cfg and cfg.acompanhar_envios),
        numero_acompanhamento=cfg.numero_acompanhamento if cfg else None, pausa_segundos=svc.pausa_segundos(cfg),
        pix_tipo=ex.get("PIX_TIPO") or None, pix_chave=ex.get("PIX_CHAVE") or None,
        enviar_link_contrato=bool(cfg and cfg.enviar_link_contrato), avisar_fim_contrato=bool(cfg and cfg.avisar_fim_contrato),
        avisos=avisos, textos={c: svc.texto_do_campo(cfg, c) for c in svc.CAMPOS_TEXTO},
        envio_automatico_ativo=svc.envio_automatico_ativo(db),
    )


@router.get("/whatsapp/configuracao/geral", response_model=sc.GeralOut)
def ler_geral(ctx: Ctx):
    return sc.GeralOut(envio_automatico_ativo=svc.envio_automatico_ativo(ctx.db))


@router.put("/whatsapp/configuracao/geral", response_model=sc.GeralOut)
def salvar_geral(dados: sc.GeralIn, ctx: Ctx):
    """Chave geral do ambiente. Nasce DESLIGADA; ligue só quando o sistema antigo deixar de enviar (evita mensagem em dobro)."""
    antes = svc.envio_automatico_ativo(ctx.db)
    svc.definir_parametro(ctx.db, svc.PARAM_ENVIO_AUTOMATICO, "1" if dados.envio_automatico_ativo else "0")
    ctx.auditar("whatsapp.envio_automatico", "comunicacao_parametro", svc.PARAM_ENVIO_AUTOMATICO,
                descricao="Envio automático LIGADO" if dados.envio_automatico_ativo else "Envio automático DESLIGADO",
                antes={"envio_automatico_ativo": antes}, depois={"envio_automatico_ativo": dados.envio_automatico_ativo})
    ctx.db.commit()
    return sc.GeralOut(envio_automatico_ativo=dados.envio_automatico_ativo)


@router.get("/whatsapp/configuracao/unidades", response_model=list[sc.ResumoUnidadeOut])
def listar_unidades(ctx: Ctx):
    cfgs = {c.unidade_id: c for c in ctx.db.scalars(select(WhatsappConfig))}
    saida = []
    for u in ctx.db.scalars(select(Unidade).order_by(Unidade.nome)):
        c = cfgs.get(u.id)
        ligados = sum(1 for t in dom.TIPOS if c and getattr(c, svc.CAMPO_ATIVO[t])) if c else 0
        saida.append(sc.ResumoUnidadeOut(unidade_id=u.id, unidade_nome=u.nome, configurado=bool(c and c.credencial_cifrado),
                                         provedor=str(c.provedor.value) if c else None, avisos_ligados=ligados))
    return saida


@router.get("/whatsapp/configuracao/textos-padrao", response_model=sc.TextosPadraoOut)
def textos_padrao(ctx: Ctx):
    return sc.TextosPadraoOut(
        campos=[sc.CampoTextoOut(campo=c, rotulo=ROTULO_TEXTO[c], padrao=dom.TEXTOS_PADRAO[c], variaveis=svc.VARIAVEIS_DO_TEXTO[c])
                for c in svc.CAMPOS_TEXTO],
        variaveis_estudio=list(svc.VARIAVEIS_ESTUDIO))


@router.get("/whatsapp/configuracao/unidades/{unidade_id}", response_model=sc.ConfigOut)
def ler_config(unidade_id: int, ctx: Ctx):
    u = _unidade(ctx, unidade_id)
    return _config_out(ctx, u, svc.obter_config(ctx.db, unidade_id))


@router.put("/whatsapp/configuracao/unidades/{unidade_id}", response_model=sc.ConfigOut)
def salvar_config(unidade_id: int, dados: sc.ConfigIn, ctx: Ctx):
    u = _unidade(ctx, unidade_id)
    cfg = svc.obter_config(ctx.db, unidade_id, criar=True)
    antes = _foto(cfg)
    cfg.provedor = ProvedorWhatsapp(dados.provedor)
    cfg.url_api = dados.url_api
    cfg.instancia = (dados.instancia or "").strip() or None
    cfg.acompanhar_envios = dados.acompanhar_envios
    cfg.numero_acompanhamento = (dados.numero_acompanhamento or "").strip() or None
    cfg.enviar_link_contrato = dados.enviar_link_contrato
    cfg.avisar_fim_contrato = dados.avisar_fim_contrato
    descricao = None
    nova = (dados.credencial or "").strip()
    if dados.limpar_credencial:
        cfg.credencial_cifrado = None
        descricao = "Credencial removida"
    elif nova:
        cfg.credencial_cifrado = segredos.cifrar_texto(nova).decode()
        descricao = "Credencial alterada"
    for tipo, a in dados.avisos.items():
        setattr(cfg, svc.CAMPO_ATIVO[tipo], a.ativo)
        setattr(cfg, svc.CAMPO_HORARIO[tipo], a.horario)
    for campo, texto in dados.textos.items():
        setattr(cfg, campo, texto)
    ex = svc.extras(cfg)
    ex.update(pausa_segundos=dados.pausa_segundos, PIX_TIPO=(dados.pix_tipo or "").strip(), PIX_CHAVE=(dados.pix_chave or "").strip())
    cfg.variaveis_template = ex
    ctx.db.flush()
    a, d = audit.diff(antes, _foto(cfg))
    ctx.auditar("whatsapp.config.alterar", "whatsapp_config", cfg.id, descricao=descricao or f"Configuração de WhatsApp de {u.nome}",
                antes=a, depois=d)
    ctx.db.commit()
    return _config_out(ctx, u, cfg)


@router.post("/whatsapp/configuracao/unidades/{unidade_id}/testar", response_model=sc.TesteOut)
def testar_conexao(unidade_id: int, ctx: Ctx):
    """Consulta o status da sessão do WhatsApp no provedor com a credencial já salva (a tela nunca a recebe de volta)."""
    u = _unidade(ctx, unidade_id)
    cfg = svc.obter_config(ctx.db, unidade_id)
    if not cfg or not cfg.credencial_cifrado:
        raise ErroDeNegocio("Cadastre e salve o token/chave antes de testar a conexão.", 409)
    st = svc.provedor_da_config(cfg).status_sessao()
    ctx.auditar("whatsapp.config.testar", "whatsapp_config", cfg.id,
                descricao=f"Teste de conexão ({u.nome}): " + ("conectada" if st.conectada else "não conectada"))
    ctx.db.commit()
    return sc.TesteOut(conectada=st.conectada, detalhe=st.detalhe)


# =============================================================================================== acompanhamento
@router.get("/whatsapp/status", response_model=sc.StatusOut)
def status_geral(ctx: Ctx):
    n = ctx.db.scalar(select(func.count()).select_from(WhatsappConfig).where(WhatsappConfig.credencial_cifrado.is_not(None))) or 0
    return sc.StatusOut(unidades_configuradas=n, envio_automatico_ativo=svc.envio_automatico_ativo(ctx.db))


@router.get("/whatsapp/automaticos", response_model=sc.AcompanhamentoOut)
def acompanhar_automaticos(
    ctx: Ctx, unidade_id: int | None = None, tipo: str | None = None, status: str | None = None,
    pagina: int = Query(1, ge=1), por_pagina: int = Query(30, ge=1, le=200),
):
    """Acompanhar envios: o que o scheduler enviou, falhou ou pulou (sem telefone), e os alertas (sessão caída)."""
    L = WhatsappAgendamentoLog
    q = select(L)
    if unidade_id:
        q = q.where(L.unidade_id == unidade_id)
    if tipo:
        q = q.where(L.tipo == tipo)
    if status:
        q = q.where(L.status == status)
    total = ctx.db.scalar(select(func.count()).select_from(q.subquery())) or 0
    linhas = list(ctx.db.scalars(q.order_by(L.enviado_em.desc(), L.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)))
    alunos = {a.id: a.nome for a in ctx.db.scalars(select(Aluno).where(Aluno.id.in_({r.aluno_id for r in linhas if r.aluno_id})))} if linhas else {}
    profs = {p.id: p.nome for p in ctx.db.scalars(select(Profissional).where(Profissional.id.in_({r.profissional_id for r in linhas if r.profissional_id})))} if linhas else {}
    inicio = agora() - timedelta(hours=24)
    por_status = dict(ctx.db.execute(select(L.status, func.count()).where(L.enviado_em >= inicio).group_by(L.status)).all())
    itens = [sc.AutomaticoOut(id=r.id, tipo=r.tipo, tipo_rotulo=ROTULO_TIPO.get(r.tipo, r.tipo), unidade_id=r.unidade_id,
                              data_referencia=r.data_referencia,
                              destinatario=alunos.get(r.aluno_id) or profs.get(r.profissional_id), status=r.status,
                              mensagem=r.mensagem, enviado_em=r.enviado_em) for r in linhas]
    return sc.AcompanhamentoOut(envio_automatico_ativo=svc.envio_automatico_ativo(ctx.db), hoje=por_status, itens=itens, total=total)


# =============================================================================================== histórico e envio manual
def _msg_out(m: WhatsappMensagem, nome: str | None) -> sc.MensagemOut:
    return sc.MensagemOut(
        id=m.id, aluno_id=m.aluno_id, aluno_nome=nome, tipo=m.tipo, tipo_rotulo=ROTULO_TIPO.get(m.tipo, m.tipo),
        direcao=m.direcao.value, telefone=m.telefone, mensagem=m.mensagem, status=m.status,
        detalhe=m.resposta_payload if m.status != "sent" else None, enviado_em=m.enviado_em)


@router.get("/whatsapp/mensagens", response_model=Pagina[sc.MensagemOut])
def historico(
    ctx: Ctx, aluno_id: int | None = None, tipo: str | None = None, status: str | None = None,
    de: date | None = None, ate: date | None = None, q: str | None = None,
    pagina: int = Query(1, ge=1), por_pagina: int = Query(30, ge=1, le=200),
):
    M = WhatsappMensagem
    base = select(M, Aluno.nome).join(Aluno, Aluno.id == M.aluno_id)
    if aluno_id:
        base = base.where(M.aluno_id == aluno_id)
    if tipo:
        base = base.where(M.tipo == tipo)
    if status:
        base = base.where(M.status == status)
    if de:
        base = base.where(M.enviado_em >= datetime.combine(de, time.min, tzinfo=dom.FUSO_NEGOCIO))
    if ate:
        base = base.where(M.enviado_em < datetime.combine(ate + timedelta(days=1), time.min, tzinfo=dom.FUSO_NEGOCIO))
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Aluno.nome.ilike(like), M.mensagem.ilike(like), M.telefone.ilike(like)))
    total = ctx.db.scalar(select(func.count()).select_from(base.subquery())) or 0
    linhas = ctx.db.execute(base.order_by(M.enviado_em.desc(), M.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return Pagina[sc.MensagemOut](itens=[_msg_out(m, n) for m, n in linhas], total=total, pagina=pagina, por_pagina=por_pagina)


def _aluno(ctx: Ctx, aluno_id: int) -> Aluno:
    a = ctx.db.get(Aluno, aluno_id)
    if not a:
        raise ErroDeNegocio("Aluno não encontrado.", 404)
    return a


@router.get("/whatsapp/alunos/{aluno_id}/mensagens", response_model=list[sc.MensagemOut])
def conversa_do_aluno(aluno_id: int, ctx: Ctx, limite: int = Query(200, ge=1, le=500)):
    """Aba WhatsApp da ficha: as últimas mensagens, da mais antiga para a mais nova."""
    a = _aluno(ctx, aluno_id)
    M = WhatsappMensagem
    linhas = list(ctx.db.scalars(select(M).where(M.aluno_id == aluno_id).order_by(M.enviado_em.desc(), M.id.desc()).limit(limite)))
    return [_msg_out(m, a.nome) for m in reversed(linhas)]


@router.post("/whatsapp/alunos/{aluno_id}/enviar", response_model=sc.EnvioOut)
def enviar_ao_aluno(aluno_id: int, dados: sc.EnviarIn, ctx: Ctx):
    a = _aluno(ctx, aluno_id)
    texto = svc.texto_para_aluno(ctx.db, a, dados.texto)
    res = svc.enviar_texto_aluno(ctx.db, a, texto, tipo="manual")
    ctx.auditar("whatsapp.enviar", "aluno", a.id, descricao=f"Mensagem manual para {a.nome}: {'enviada' if res.ok else 'falhou'}")
    ctx.db.commit()  # grava o histórico (inclusive a falha) antes de responder
    svc.exigir_envio(res)
    return sc.EnvioOut(enviado=True, mensagem=texto)


@router.get("/whatsapp/reservas/{reserva_id}/previa", response_model=sc.PreviaReservaOut)
def previa_lembrete(reserva_id: int, ctx: Ctx):
    aluno, msg = svc.montar_lembrete_da_reserva(ctx.db, reserva_id)
    return sc.PreviaReservaOut(aluno_id=aluno.id, aluno_nome=aluno.nome, mensagem=msg,
                               tem_celular=bool(svc.celular_do_aluno(ctx.db, aluno.id)))


@router.post("/whatsapp/reservas/{reserva_id}/enviar-agora", response_model=sc.EnvioOut)
def enviar_agora(reserva_id: int, ctx: Ctx):
    """"Enviar agora" do painel operacional: manda o lembrete da aula (mesmo texto do aviso automático) ao aluno."""
    aluno, msg = svc.montar_lembrete_da_reserva(ctx.db, reserva_id)
    res = svc.enviar_texto_aluno(ctx.db, aluno, msg, tipo=dom.LEMBRETE_ALUNO)
    ctx.auditar("whatsapp.enviar_agora", "reserva", reserva_id, descricao=f"Lembrete de aula para {aluno.nome}: {'enviado' if res.ok else 'falhou'}")
    ctx.db.commit()
    svc.exigir_envio(res)
    return sc.EnvioOut(enviado=True, mensagem=msg)


# =============================================================================================== aviso ao aluno
@router.post("/comunicacao/aviso-aluno/previa", response_model=sc.AvisoAlunoPreviaOut)
def aviso_previa(dados: sc.AvisoAlunoIn, ctx: Ctx):
    a = _aluno(ctx, dados.aluno_id)
    return sc.AvisoAlunoPreviaOut(aluno_nome=a.nome, mensagem=svc.texto_para_aluno(ctx.db, a, dados.texto),
                                  tem_celular=bool(svc.celular_do_aluno(ctx.db, a.id)))


@router.post("/comunicacao/aviso-aluno", response_model=sc.EnvioOut)
def aviso_enviar(dados: sc.AvisoAlunoIn, ctx: Ctx):
    a = _aluno(ctx, dados.aluno_id)
    texto = svc.texto_para_aluno(ctx.db, a, dados.texto)
    res = svc.enviar_texto_aluno(ctx.db, a, texto, tipo="manual")
    ctx.auditar("comunicacao.aviso_aluno", "aluno", a.id, descricao=f"Aviso para {a.nome}: {'enviado' if res.ok else 'falhou'}")
    ctx.db.commit()
    svc.exigir_envio(res)
    return sc.EnvioOut(enviado=True, mensagem=texto)


# =============================================================================================== comunicado geral
def _unidade_opcional(ctx: Ctx, unidade_id: int | None) -> None:
    if unidade_id is not None:
        _unidade(ctx, unidade_id)


def _comunicado(ctx: Ctx, comunicado_id: int) -> Comunicado:
    c = ctx.db.get(Comunicado, comunicado_id)
    if not c:
        raise ErroDeNegocio("Comunicado não encontrado.", 404)
    return c


@router.post("/comunicacao/comunicados/previa", response_model=sc.PreviaOut)
def comunicado_previa(dados: sc.PreviaIn, ctx: Ctx):
    _unidade_opcional(ctx, dados.unidade_id)
    return sc.PreviaOut(**com.previa(ctx.db, dados.texto, dados.publico, dados.unidade_id))


@router.post("/comunicacao/comunicados", response_model=sc.ComunicadoOut, status_code=201)
def comunicado_criar(dados: sc.ComunicadoIn, ctx: Ctx):
    """Cria o comunicado e entrega à fila do worker (um a um, com pausa). Acompanhe por GET /comunicacao/comunicados/{id}."""
    _unidade_opcional(ctx, dados.unidade_id)
    c = com.criar(ctx.db, ctx.usuario.id, dados.texto, dados.publico, dados.unidade_id)
    p = com.progresso(ctx.db, c)
    ctx.auditar("comunicacao.comunicado.criar", "comunicado", c.id,
                descricao=f"Comunicado para {dados.publico} ({p['total']} aluno(s), {p['sem_telefone']} sem telefone)",
                depois={"publico": dados.publico, "unidade_id": dados.unidade_id, "total": p["total"]})
    ctx.db.commit()
    return sc.ComunicadoOut(**p)


@router.get("/comunicacao/comunicados", response_model=list[sc.ComunicadoOut])
def comunicado_listar(ctx: Ctx, limite: int = Query(20, ge=1, le=100)):
    cs = ctx.db.scalars(select(Comunicado).order_by(Comunicado.id.desc()).limit(limite))
    return [sc.ComunicadoOut(**com.progresso(ctx.db, c)) for c in cs]


@router.get("/comunicacao/comunicados/{comunicado_id}", response_model=sc.ComunicadoOut)
def comunicado_ver(comunicado_id: int, ctx: Ctx):
    """Progresso ao vivo (a tela consulta a cada poucos segundos)."""
    return sc.ComunicadoOut(**com.progresso(ctx.db, _comunicado(ctx, comunicado_id)))


@router.get("/comunicacao/comunicados/{comunicado_id}/destinatarios", response_model=list[sc.DestinatarioOut])
def comunicado_relatorio(comunicado_id: int, ctx: Ctx, status: str | None = None):
    """Relatório: quem recebeu, quem falhou (com o motivo) e quem ficou sem telefone."""
    _comunicado(ctx, comunicado_id)
    D = ComunicadoDestinatario
    q = select(D).where(D.comunicado_id == comunicado_id)
    if status:
        q = q.where(D.status == status)
    return [sc.DestinatarioOut(aluno_id=d.aluno_id, nome=d.nome, telefone=d.telefone, status=d.status, erro=d.erro,
                               enviado_em=d.enviado_em) for d in ctx.db.scalars(q.order_by(D.nome, D.id))]


def _acao_comunicado(ctx: Ctx, comunicado_id: int, nome: str, fn: Callable) -> sc.ComunicadoOut:
    c = _comunicado(ctx, comunicado_id)
    fn(ctx.db, c)
    ctx.auditar(f"comunicacao.comunicado.{nome}", "comunicado", c.id, descricao=f"Comunicado {c.id}: {nome}")
    ctx.db.commit()
    return sc.ComunicadoOut(**com.progresso(ctx.db, c))


@router.post("/comunicacao/comunicados/{comunicado_id}/pausar", response_model=sc.ComunicadoOut)
def comunicado_pausar(comunicado_id: int, ctx: Ctx):
    return _acao_comunicado(ctx, comunicado_id, "pausar", com.pausar)


@router.post("/comunicacao/comunicados/{comunicado_id}/retomar", response_model=sc.ComunicadoOut)
def comunicado_retomar(comunicado_id: int, ctx: Ctx):
    return _acao_comunicado(ctx, comunicado_id, "retomar", com.retomar)


@router.post("/comunicacao/comunicados/{comunicado_id}/cancelar", response_model=sc.ComunicadoOut)
def comunicado_cancelar(comunicado_id: int, ctx: Ctx):
    return _acao_comunicado(ctx, comunicado_id, "cancelar", com.cancelar)


# =============================================================================================== pontos de extensão
svc.registrar_tudo()  # cobrador do financeiro, Notificador real do core e enviador de contrato/termo
