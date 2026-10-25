"""API da agenda: sessões de aula, reservas, grade semanal, painel operacional, evolução/avaliação, aula avulsa/avaliativa.

Permissões (negar por padrão; registradas aqui com ``adicionar_regras``):
- ``/agenda/*``: agenda.ver / agenda.editar / agenda.excluir (grade, aulas, reservas, avulsa, avaliativa);
- ``/aulas/*``: painel e ações da aula (aulas.ver / aulas.operar / aulas.evoluir / aulas.avaliar).

Perfil Professor (R11): só as próprias aulas e os alunos dessas aulas (``escopo``); um id alheio responde 404 (não revela
que existe). Professor NÃO desmarca, não remarca e não exclui reserva (R4), mesmo que o perfil tenha ``aulas.operar``.

Nenhum GET cria ou altera dado (o antigo criava aulas e concluía aulas em GET).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.core import audit, escopo
from app.core.db import agora as agora_utc
from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.modules.agenda import avulsa, consultas, evolucao
from app.modules.agenda import servico as srv
from app.modules.agenda.models import AulaAvaliativa, AulaAvulsa, AulaSessao, Avaliacao, Evolucao, Reserva, StatusReserva
from app.modules.agenda.schemas import (
    AvaliacaoIn,
    AvaliativaIn,
    AvulsaIn,
    EvolucaoIn,
    FichaAvaliativaIn,
    GerarSessoesIn,
    MelhorarIn,
    PresencaIn,
    RemarcarIn,
    ReservaIn,
    SessaoIn,
    SessaoPatch,
)
from app.modules.alunos.models import Aluno

router = APIRouter(tags=["agenda"])

adicionar_regras(
    [
        # --- agenda (grade, aulas, reservas, avulsa, avaliativa) ---
        ("POST", r"/agenda/sessoes/gerar$", "agenda.editar"),
        ("DELETE", r"/agenda/sessoes/\d+$", "agenda.excluir"),
        ("*", r"/agenda/sessoes", "agenda.*e"),
        ("POST", r"/agenda/reservas$", "agenda.editar"),
        ("GET", r"/agenda/reservas/\d+/horarios$", "agenda.ver"),
        ("GET", r"/agenda/alunos/\d+/evolucoes", "aulas.evoluir"),
        ("GET", r"/agenda/alunos/\d+/avaliacoes", "aulas.avaliar"),
        ("GET", r"/agenda/alunos/\d+/", "agenda.ver"),
        ("PUT", r"/agenda/avaliativas/\d+/ficha$", "aulas.avaliar"),
        ("POST", r"/agenda/avaliativas", "agenda.editar"),
        ("POST", r"/agenda/avulsas$", "agenda.editar"),
        ("GET", r"/agenda/(opcoes|grade|avulsas/slots)$", "agenda.ver"),
        # --- aulas (painel operacional e ações) ---
        ("GET", r"/aulas/painel$", "aulas.ver"),
        ("GET", r"/aulas/reservas/\d+/cobranca$", "financeiro_receber.ver"),
        ("GET", r"/aulas/reservas/\d+(/historico)?$", "aulas.ver"),
        ("POST", r"/aulas/reservas/\d+/presenca$", "aulas.ver"),  # + aulas.operar OU aulas.evoluir, conferido na rota
        ("POST", r"/aulas/reservas/\d+/(confirmar|desmarcar|remarcar)$", "aulas.operar"),
        ("DELETE", r"/aulas/reservas/\d+$", "aulas.operar"),
        ("*", r"/aulas/reservas/\d+/evolucao$", "aulas.evoluir"),
        ("*", r"/aulas/evolucoes/", "aulas.evoluir"),
        ("*", r"/aulas/reservas/\d+/avaliacao$", "aulas.avaliar"),
        ("*", r"/aulas/avaliacoes/", "aulas.avaliar"),
    ]
)


# ------------------------------------------------------------------------------------------------------- utilidades
@contextmanager
def _erros(ctx: Ctx) -> Iterator[None]:
    """Traduz os erros de regra em HTTP e desfaz TUDO que a requisição gravou (atomicidade)."""
    try:
        yield
    except srv.ErroAgenda as e:
        ctx.db.rollback()
        raise HTTPException(e.status, e.mensagem) from None


def _prof_escopo(ctx: Ctx) -> int | None:
    """Filtro de profissional do Professor: o dele, ou ``PROFISSIONAL_NENHUM`` se não tem vínculo. None = sem restrição."""
    if not ctx.somente_proprias_aulas():
        return None
    pid = ctx.profissional_id()
    return pid if pid is not None else consultas.PROFISSIONAL_NENHUM


def _nao_professor(ctx: Ctx, o_que: str) -> None:
    if ctx.somente_proprias_aulas():
        raise HTTPException(403, f"Sem permissao para {o_que}.")


def _nao_achou(msg: str = "Reserva não encontrada.") -> HTTPException:
    return HTTPException(404, msg)


def _reserva_do_escopo(ctx: Ctx, reserva_id: int) -> Reserva:
    r = ctx.db.get(Reserva, reserva_id)
    if r is None:
        raise _nao_achou()
    if ctx.somente_proprias_aulas():
        s = ctx.db.get(AulaSessao, r.aula_sessao_id)
        if not escopo.pode_acessar_profissional(ctx, s.profissional_id if s else None):
            raise _nao_achou()
    return r


def _aluno_do_escopo(ctx: Ctx, aluno_id: int) -> None:
    if not consultas.aluno_visivel(ctx.db, aluno_id, _prof_escopo(ctx)):
        raise _nao_achou("Aluno não encontrado.")


def _sessao_do_escopo(ctx: Ctx, sessao_id: int) -> AulaSessao:
    s = ctx.db.get(AulaSessao, sessao_id)
    if s is None or (ctx.somente_proprias_aulas() and not escopo.pode_acessar_profissional(ctx, s.profissional_id)):
        raise _nao_achou("Aula não encontrada.")
    return s


def _reserva_dict(ctx: Ctx, r: Reserva) -> dict[str, Any]:
    db = ctx.db
    s = db.get(AulaSessao, r.aula_sessao_id)
    db.refresh(s)
    capacidade = srv.capacidade_da_sessao(db, s)
    return {
        "id": r.id,
        "aluno_id": r.aluno_id,
        "sessao_id": s.id,
        "data": s.data.isoformat(),
        "hora_inicio": f"{s.hora_inicio:%H:%M}",
        "hora_fim": f"{s.hora_fim:%H:%M}",
        "profissional_id": s.profissional_id,
        "status": StatusReserva(r.status).value,
        "confirmada_em": r.confirmada_em.isoformat() if r.confirmada_em else None,
        "desmarcada_em": r.desmarcada_em.isoformat() if r.desmarcada_em else None,
        "reposicao_ate": r.reposicao_ate.isoformat() if r.reposicao_ate else None,
        "contrato_id": r.contrato_id,
        "ocupacao": f"{s.reservas_ativas}/{capacidade}",
    }


def _agora() -> datetime:
    return agora_utc()


def _nome_aluno(ctx: Ctx, aluno_id: int) -> str:
    a = ctx.db.get(Aluno, aluno_id)
    return a.nome if a else f"#{aluno_id}"


def _descricao_reserva(ctx: Ctx, r: Reserva) -> str:
    s = ctx.db.get(AulaSessao, r.aula_sessao_id)
    return f"{_nome_aluno(ctx, r.aluno_id)} - {s.data:%d/%m/%Y} {s.hora_inicio:%H:%M}" if s else _nome_aluno(ctx, r.aluno_id)


# ------------------------------------------------------------------------------------------------- opções e grade
@router.get("/agenda/opcoes")
def opcoes(ctx: Ctx):
    """Listas dos filtros e formulários. Professor só enxerga a si mesmo na lista de profissionais."""
    return consultas.opcoes(ctx.db, profissional_id=_prof_escopo(ctx))


@router.get("/agenda/grade")
def grade(
    ctx: Ctx,
    semana: date | None = Query(None, description="Qualquer data da semana desejada"),
    profissional_id: int | None = None,
    unidade_id: int | None = None,
):
    """Grade seg-sáb. Sem ``semana`` e hoje sendo sáb/dom, mostra a próxima semana."""
    prof = _prof_escopo(ctx)
    if prof is None:
        prof = profissional_id
    from app.domain.financeiro import hoje_de_negocio

    return consultas.montar_grade(
        ctx.db, referencia=semana, hoje=hoje_de_negocio(_agora()), profissional_id=prof, unidade_id=unidade_id
    )


# ----------------------------------------------------------------------------------------------------------- sessões
@router.get("/agenda/sessoes")
def listar_sessoes(
    ctx: Ctx,
    de: date,
    ate: date,
    unidade_id: int | None = None,
    profissional_id: int | None = None,
    tipo_servico_id: int | None = None,
):
    prof = _prof_escopo(ctx)
    return {
        "itens": consultas.listar_sessoes(
            ctx.db,
            de=de,
            ate=ate,
            unidade_id=unidade_id,
            profissional_id=prof if prof is not None else profissional_id,
            tipo_servico_id=tipo_servico_id,
        )
    }


@router.get("/agenda/sessoes/{sessao_id}")
def ver_sessao(sessao_id: int, ctx: Ctx):
    d = consultas.detalhe_sessao(ctx.db, sessao_id, profissional_id=_prof_escopo(ctx))
    if d is None:
        raise _nao_achou("Aula não encontrada.")
    return d


def _sessao_resp(ctx: Ctx, s: AulaSessao) -> dict:
    return consultas.detalhe_sessao(ctx.db, s.id) or {}


@router.post("/agenda/sessoes", status_code=201)
def criar_sessao(dados: SessaoIn, ctx: Ctx):
    with _erros(ctx):
        s = srv.criar_sessao(ctx.db, **dados.model_dump())
        ctx.auditar("agenda.sessao.criar", "aula_sessao", s.id, descricao=f"Aula {s.data:%d/%m/%Y} {s.hora_inicio:%H:%M}", depois=audit.snapshot(s))
        ctx.db.commit()
    return _sessao_resp(ctx, s)


@router.patch("/agenda/sessoes/{sessao_id}")
def editar_sessao(sessao_id: int, dados: SessaoPatch, ctx: Ctx):
    campos = {k: getattr(dados, k) for k in dados.model_fields_set}
    with _erros(ctx):
        s = ctx.db.get(AulaSessao, sessao_id)
        if s is None:
            raise srv.NaoEncontrado("Aula não encontrada.")
        antes = audit.snapshot(s)
        s = srv.editar_sessao_segura(ctx.db, sessao_id, campos)
        a, d = audit.diff(antes, audit.snapshot(s))
        ctx.auditar("agenda.sessao.alterar", "aula_sessao", s.id, descricao=f"Aula {s.data:%d/%m/%Y} {s.hora_inicio:%H:%M}", antes=a, depois=d)
        ctx.db.commit()
    return _sessao_resp(ctx, s)


@router.delete("/agenda/sessoes/{sessao_id}", status_code=204)
def excluir_sessao(sessao_id: int, ctx: Ctx):
    with _erros(ctx):
        s = ctx.db.get(AulaSessao, sessao_id)
        if s is None:
            raise srv.NaoEncontrado("Aula não encontrada.")
        antes = audit.snapshot(s)
        srv.excluir_sessao(ctx.db, sessao_id)
        ctx.auditar("agenda.sessao.excluir", "aula_sessao", sessao_id, descricao=f"Aula {antes['data']} {antes['hora_inicio']}", antes=antes)
        ctx.db.commit()
    return Response(status_code=204)


@router.post("/agenda/sessoes/gerar")
def gerar_sessoes(dados: GerarSessoesIn, ctx: Ctx):
    """Cria as aulas vazias do período pelos horários de funcionamento. Pedido explícito (POST), idempotente."""
    with _erros(ctx):
        r = srv.gerar_sessoes(ctx.db, **dados.model_dump())
        ctx.auditar(
            "agenda.sessao.gerar",
            "aula_sessao",
            None,
            descricao=f"{r['criadas']} aula(s) geradas de {dados.data_inicio:%d/%m/%Y} a {dados.data_fim:%d/%m/%Y}",
            depois={k: v for k, v in r.items() if k != "ids"},
        )
        ctx.db.commit()
    return {k: v for k, v in r.items() if k != "ids"}


# ----------------------------------------------------------------------------------------------------------- reservas
@router.post("/agenda/reservas", status_code=201)
def criar_reserva(dados: ReservaIn, ctx: Ctx):
    with _erros(ctx):
        if dados.sessao_id is not None:
            sessao_id = dados.sessao_id
        else:
            if not (dados.unidade_id and dados.tipo_servico_id and dados.data and dados.hora_inicio):
                raise srv.Invalido("Informe a aula (sessao_id) ou unidade, serviço, data e horário.")
            s, _ = srv.obter_ou_criar_sessao(
                ctx.db,
                unidade_id=dados.unidade_id,
                tipo_servico_id=dados.tipo_servico_id,
                profissional_id=dados.profissional_id,
                data=dados.data,
                hora_inicio=dados.hora_inicio,
                hora_fim=dados.hora_fim,
            )
            sessao_id = s.id
        r = srv.criar_reserva(ctx.db, dados.aluno_id, sessao_id)
        ctx.auditar("agenda.reserva.criar", "reserva", r.id, descricao=_descricao_reserva(ctx, r), depois=audit.snapshot(r))
        ctx.db.commit()
    return _reserva_dict(ctx, r)


@router.get("/agenda/reservas/{reserva_id}/horarios")
def horarios_para_remarcar(
    reserva_id: int, ctx: Ctx, de: date | None = None, ate: date | None = None
):
    """Opções de remarcação. Só lê: não cria nenhuma aula."""
    _reserva_do_escopo(ctx, reserva_id)
    from datetime import timedelta

    from app.domain.financeiro import hoje_de_negocio

    inicio = de or hoje_de_negocio(_agora())
    return {"itens": consultas.horarios_para_remarcar(ctx.db, reserva_id, inicio, ate or inicio + timedelta(days=60))}


@router.get("/agenda/alunos/{aluno_id}/reservas")
def reservas_do_aluno(
    aluno_id: int,
    ctx: Ctx,
    status: str | None = None,
    futuras: bool | None = None,
    limite: int = Query(200, ge=1, le=1000),
):
    """Aba "Aulas" da ficha do aluno. Professor: só as aulas dele, e só se o aluno for de uma aula dele."""
    _aluno_do_escopo(ctx, aluno_id)
    try:
        itens = consultas.reservas_do_aluno(
            ctx.db, aluno_id, agora=_agora(), profissional_id=_prof_escopo(ctx), status=status, futuras=futuras, limite=limite
        )
    except ValueError:
        raise HTTPException(422, "status: valor inválido") from None
    return {"itens": itens}


# ------------------------------------------------------------------------------------------------- painel e gaveta
@router.get("/aulas/painel")
def painel(
    ctx: Ctx,
    data: date | None = Query(None, description="Data alvo"),
    periodo: str = Query("hoje", pattern="^(hoje|amanha|semana)$"),
    unidade_id: int | None = None,
    profissional_id: int | None = None,
    status_aula: str | None = Query(None, pattern="^(aguardando_chegar|em_aula|finalizada|faltou|remarcada)$"),
    q: str | None = Query(None, max_length=100),
):
    prof = _prof_escopo(ctx)
    return consultas.montar_painel(
        ctx.db,
        alvo=data,
        periodo=periodo,
        agora=_agora(),
        com_cobranca=ctx.pode("financeiro_receber.ver"),
        unidade_id=unidade_id,
        profissional_id=prof if prof is not None else profissional_id,
        status_aula_filtro=status_aula,
        busca=q,
    )


def _permite(ctx: Ctx) -> dict[str, bool]:
    prof = ctx.somente_proprias_aulas()
    return {
        "chegou": ctx.pode("aulas.operar") or ctx.pode("aulas.evoluir"),
        "finalizar": ctx.pode("aulas.operar") or ctx.pode("aulas.evoluir"),
        "faltou": ctx.pode("aulas.operar") or ctx.pode("aulas.evoluir"),
        "remarcar": ctx.pode("aulas.operar") and not prof,
        "desmarcar": ctx.pode("aulas.operar") and not prof,
        "excluir": ctx.pode("aulas.operar") and not prof,
        "confirmar": ctx.pode("aulas.operar"),
        "evolucao": ctx.pode("aulas.evoluir"),
        "avaliacao": ctx.pode("aulas.avaliar"),
        "cobranca": ctx.pode("financeiro_receber.ver") and not prof,
    }


@router.get("/aulas/reservas/{reserva_id}")
def detalhe_reserva(reserva_id: int, ctx: Ctx):
    """Dados da gaveta do aluno: cartão da aula + o que este usuário pode fazer."""
    r = _reserva_do_escopo(ctx, reserva_id)
    item = consultas.item_da_reserva(
        ctx.db, r.id, agora=_agora(), com_cobranca=ctx.pode("financeiro_receber.ver"), profissional_id=_prof_escopo(ctx)
    )
    if item is None:
        raise _nao_achou()
    item["permite"] = _permite(ctx)
    return item


@router.get("/aulas/reservas/{reserva_id}/historico")
def historico(reserva_id: int, ctx: Ctx):
    r = _reserva_do_escopo(ctx, reserva_id)
    return {"itens": consultas.historico_do_aluno(ctx.db, r.aluno_id, _agora(), profissional_id=_prof_escopo(ctx))}


@router.get("/aulas/reservas/{reserva_id}/cobranca")
def cobranca(reserva_id: int, ctx: Ctx):
    _nao_professor(ctx, "ver a cobrança")
    r = _reserva_do_escopo(ctx, reserva_id)
    return {"itens": consultas.cobranca_do_aluno(ctx.db, r.aluno_id, _agora())}


@router.post("/aulas/reservas/{reserva_id}/presenca")
def presenca(reserva_id: int, dados: PresencaIn, ctx: Ctx):
    """chegou / iniciar / finalizar / faltou / faltou_avisou. Vale ``aulas.operar`` OU ``aulas.evoluir`` (o professor
    finaliza a própria aula)."""
    if not (ctx.pode("aulas.operar") or ctx.pode("aulas.evoluir")):
        raise HTTPException(403, "Seu perfil de acesso não permite esta ação.")
    r = _reserva_do_escopo(ctx, reserva_id)
    with _erros(ctx):
        antes = audit.snapshot(r)
        r = srv.aplicar_acao_presenca(ctx.db, r.id, dados.acao, agora=_agora())
        a, d = audit.diff(antes, audit.snapshot(r))
        ctx.auditar(f"aula.{dados.acao.strip().lower()}", "reserva", r.id, descricao=_descricao_reserva(ctx, r), antes=a, depois=d)
        ctx.db.commit()
    return _reserva_dict(ctx, r)


@router.post("/aulas/reservas/{reserva_id}/confirmar")
def confirmar(reserva_id: int, ctx: Ctx):
    r = _reserva_do_escopo(ctx, reserva_id)
    with _erros(ctx):
        r = srv.confirmar_reserva(ctx.db, r.id, agora=_agora())
        ctx.auditar("aula.confirmar", "reserva", r.id, descricao=_descricao_reserva(ctx, r))
        ctx.db.commit()
    return _reserva_dict(ctx, r)


@router.post("/aulas/reservas/{reserva_id}/desmarcar")
def desmarcar(reserva_id: int, ctx: Ctx):
    """Desmarcar com reposição (R4): reposição até a data da aula + 30 dias. Professor não desmarca."""
    _nao_professor(ctx, "desmarcar")
    r = _reserva_do_escopo(ctx, reserva_id)
    with _erros(ctx):
        antes = audit.snapshot(r)
        r = srv.desmarcar_reserva(ctx.db, r.id, agora=_agora(), eh_professor=ctx.somente_proprias_aulas())
        a, d = audit.diff(antes, audit.snapshot(r))
        ctx.auditar("aula.desmarcar", "reserva", r.id, descricao=_descricao_reserva(ctx, r), antes=a, depois=d)
        ctx.db.commit()
    return _reserva_dict(ctx, r)


@router.post("/aulas/reservas/{reserva_id}/remarcar")
def remarcar(reserva_id: int, dados: RemarcarIn, ctx: Ctx):
    _nao_professor(ctx, "remarcar")
    r = _reserva_do_escopo(ctx, reserva_id)
    with _erros(ctx):
        antes = audit.snapshot(r)
        r = srv.remarcar_reserva(
            ctx.db,
            r.id,
            data=dados.data,
            hora_inicio=dados.hora_inicio,
            profissional_id=dados.profissional_id,
            ignorar_prazo_reposicao=dados.ignorar_prazo_reposicao,
            agora=_agora(),
        )
        a, d = audit.diff(antes, audit.snapshot(r))
        ctx.auditar("aula.remarcar", "reserva", r.id, descricao=_descricao_reserva(ctx, r), antes=a, depois=d)
        ctx.db.commit()
    return _reserva_dict(ctx, r)


@router.delete("/aulas/reservas/{reserva_id}")
def excluir_reserva(reserva_id: int, ctx: Ctx):
    """Exclui a aula do aluno (libera a vaga; apaga a aula se ficar vazia). Professor não exclui."""
    _nao_professor(ctx, "excluir")
    r = _reserva_do_escopo(ctx, reserva_id)
    with _erros(ctx):
        descricao = _descricao_reserva(ctx, r)
        antes = audit.snapshot(r)
        resumo = srv.excluir_reserva(ctx.db, r.id)
        ctx.auditar("aula.excluir", "reserva", reserva_id, descricao=descricao, antes=antes, depois=resumo)
        ctx.db.commit()
    return {"ok": True, "reserva_id": reserva_id, **resumo}


# ------------------------------------------------------------------------------------------ evolução e avaliação
def _registro_do_escopo(ctx: Ctx, modelo, registro_id: int, rotulo: str):
    reg = ctx.db.get(modelo, registro_id)
    if reg is None:
        raise _nao_achou(f"{rotulo} não encontrada.")
    _reserva_do_escopo(ctx, reg.reserva_id)  # 404 se for de aula alheia (Professor)
    return reg


def _profissional_do_registro(ctx: Ctx, pedido: int | None) -> int | None:
    """Professor sempre registra como ele mesmo; os demais podem indicar o profissional (ou vale o da aula)."""
    if ctx.somente_proprias_aulas():
        return ctx.profissional_id()
    return pedido


@router.get("/aulas/reservas/{reserva_id}/evolucao")
def listar_evolucoes_da_reserva(reserva_id: int, ctx: Ctx):
    r = _reserva_do_escopo(ctx, reserva_id)
    return {"itens": evolucao.listar_do_aluno(ctx.db, "evolucoes", r.aluno_id, limite=20)}


@router.post("/aulas/reservas/{reserva_id}/evolucao", status_code=201)
def criar_evolucao(reserva_id: int, dados: EvolucaoIn, ctx: Ctx):
    r = _reserva_do_escopo(ctx, reserva_id)
    with _erros(ctx):
        status = None
        if dados.status:
            try:
                status = StatusReserva(dados.status.upper())
            except ValueError:
                raise srv.Invalido("Status inválido.") from None
        e = evolucao.criar_registro(
            ctx.db,
            "evolucoes",
            r.id,
            texto=dados.texto,
            profissional_id=_profissional_do_registro(ctx, dados.profissional_id),
            modelo_evolucao_id=dados.modelo_evolucao_id,
            finalizar=dados.finalizar,
            status=status,
        )
        ctx.auditar(
            "evolucao.criar",
            "evolucao",
            e.id,
            descricao=_descricao_reserva(ctx, r) + (" (aula finalizada)" if dados.finalizar else ""),
            depois={"reserva_id": r.id, "finalizar": dados.finalizar},
        )
        ctx.db.commit()
    return evolucao.para_dict(ctx.db, e) | {"status_reserva": StatusReserva(r.status).value}


@router.patch("/aulas/evolucoes/{evolucao_id}")
def editar_evolucao(evolucao_id: int, dados: AvaliacaoIn, ctx: Ctx):
    reg = _registro_do_escopo(ctx, Evolucao, evolucao_id, "Evolução")
    with _erros(ctx):
        antes = audit.snapshot(reg)
        reg = evolucao.atualizar_registro(ctx.db, "evolucoes", reg.id, dados.texto)
        a, d = audit.diff(antes, audit.snapshot(reg))
        ctx.auditar("evolucao.alterar", "evolucao", reg.id, antes=a, depois=d)
        ctx.db.commit()
    return evolucao.para_dict(ctx.db, reg)


@router.delete("/aulas/evolucoes/{evolucao_id}", status_code=204)
def excluir_evolucao(evolucao_id: int, ctx: Ctx):
    reg = _registro_do_escopo(ctx, Evolucao, evolucao_id, "Evolução")
    with _erros(ctx):
        antes = audit.snapshot(reg)
        evolucao.excluir_registro(ctx.db, "evolucoes", reg.id)
        ctx.auditar("evolucao.excluir", "evolucao", evolucao_id, antes=antes)
        ctx.db.commit()
    return Response(status_code=204)


@router.post("/aulas/evolucoes/melhorar")
def melhorar_evolucao(dados: MelhorarIn, ctx: Ctx):
    """Melhora o texto com a IA configurada. Sem IA configurada, devolve o texto original com um aviso."""
    with _erros(ctx):
        r = evolucao.melhorar_texto(ctx.db, dados.texto)
        ctx.db.commit()  # a config padrão da IA pode ter sido criada
    return {"texto": r.texto, "melhorado": r.melhorado, "aviso": r.aviso}


@router.get("/aulas/reservas/{reserva_id}/avaliacao")
def listar_avaliacoes_da_reserva(reserva_id: int, ctx: Ctx):
    r = _reserva_do_escopo(ctx, reserva_id)
    return {"itens": evolucao.listar_do_aluno(ctx.db, "avaliacoes", r.aluno_id, limite=20)}


@router.post("/aulas/reservas/{reserva_id}/avaliacao", status_code=201)
def criar_avaliacao(reserva_id: int, dados: AvaliacaoIn, ctx: Ctx):
    r = _reserva_do_escopo(ctx, reserva_id)
    with _erros(ctx):
        e = evolucao.criar_registro(
            ctx.db, "avaliacoes", r.id, texto=dados.texto, profissional_id=_profissional_do_registro(ctx, dados.profissional_id)
        )
        ctx.auditar("avaliacao.criar", "avaliacao", e.id, descricao=_descricao_reserva(ctx, r), depois={"reserva_id": r.id})
        ctx.db.commit()
    return evolucao.para_dict(ctx.db, e)


@router.patch("/aulas/avaliacoes/{avaliacao_id}")
def editar_avaliacao(avaliacao_id: int, dados: AvaliacaoIn, ctx: Ctx):
    reg = _registro_do_escopo(ctx, Avaliacao, avaliacao_id, "Avaliação")
    with _erros(ctx):
        antes = audit.snapshot(reg)
        reg = evolucao.atualizar_registro(ctx.db, "avaliacoes", reg.id, dados.texto)
        a, d = audit.diff(antes, audit.snapshot(reg))
        ctx.auditar("avaliacao.alterar", "avaliacao", reg.id, antes=a, depois=d)
        ctx.db.commit()
    return evolucao.para_dict(ctx.db, reg)


@router.delete("/aulas/avaliacoes/{avaliacao_id}", status_code=204)
def excluir_avaliacao(avaliacao_id: int, ctx: Ctx):
    reg = _registro_do_escopo(ctx, Avaliacao, avaliacao_id, "Avaliação")
    with _erros(ctx):
        antes = audit.snapshot(reg)
        evolucao.excluir_registro(ctx.db, "avaliacoes", reg.id)
        ctx.auditar("avaliacao.excluir", "avaliacao", avaliacao_id, antes=antes)
        ctx.db.commit()
    return Response(status_code=204)


@router.get("/agenda/alunos/{aluno_id}/evolucoes")
def evolucoes_do_aluno(aluno_id: int, ctx: Ctx, limite: int = Query(200, ge=1, le=1000)):
    """Histórico de evoluções do aluno (aba da ficha). Professor: só alunos das próprias aulas."""
    _aluno_do_escopo(ctx, aluno_id)
    return {"itens": evolucao.listar_do_aluno(ctx.db, "evolucoes", aluno_id, limite=limite)}


@router.get("/agenda/alunos/{aluno_id}/avaliacoes")
def avaliacoes_do_aluno(aluno_id: int, ctx: Ctx, limite: int = Query(200, ge=1, le=1000)):
    _aluno_do_escopo(ctx, aluno_id)
    return {"itens": evolucao.listar_do_aluno(ctx.db, "avaliacoes", aluno_id, limite=limite)}


def _exportar(ctx: Ctx, tipo: str, aluno_id: int, formato: str) -> Response:
    _aluno_do_escopo(ctx, aluno_id)
    with _erros(ctx):
        conteudo, mime, nome = evolucao.exportar(ctx.db, tipo, aluno_id, formato)
        ctx.auditar("evolucao.exportar" if tipo == "evolucoes" else "avaliacao.exportar", "aluno", aluno_id, descricao=f"{tipo} em {formato}")
        ctx.db.commit()
    return Response(conteudo, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/agenda/alunos/{aluno_id}/evolucoes/exportar")
def exportar_evolucoes(aluno_id: int, ctx: Ctx, formato: str = Query("pdf", pattern="^(pdf|xlsx)$")):
    return _exportar(ctx, "evolucoes", aluno_id, formato)


@router.get("/agenda/alunos/{aluno_id}/avaliacoes/exportar")
def exportar_avaliacoes(aluno_id: int, ctx: Ctx, formato: str = Query("pdf", pattern="^(pdf|xlsx)$")):
    return _exportar(ctx, "avaliacoes", aluno_id, formato)


# ------------------------------------------------------------------------------------- aula avulsa e avaliativa
@router.get("/agenda/avulsas/slots")
def slots_avulsa(
    ctx: Ctx, unidade_id: int, plano_id: int, data_inicio: date, quantidade: int = Query(1, ge=1, le=60)
):
    """Horários oferecidos para o pacote avulso. Só lê."""
    with _erros(ctx):
        return avulsa.slots_avulsa(ctx.db, unidade_id=unidade_id, plano_id=plano_id, data_inicio=data_inicio, quantidade=quantidade)


@router.post("/agenda/avulsas", status_code=201)
def criar_avulsa(dados: AvulsaIn, ctx: Ctx):
    """Cria o pacote avulso, agenda as aulas e (se valor > 0) uma cobrança por aula ligada à reserva (R12)."""
    with _erros(ctx):
        r = avulsa.criar_aula_avulsa(ctx.db, **dados.model_dump())
        pacote, res, contas = r["pacote"], r["resultado"], r["contas"]
        ctx.auditar(
            "aula_avulsa.criar",
            "aula_avulsa",
            pacote.id,
            descricao=f"{_nome_aluno(ctx, pacote.aluno_id)}: {len(res.reservas_criadas)} aula(s), {len(contas)} cobrança(s)",
            depois={**audit.snapshot(pacote), "reservas": res.reservas_criadas, "contas": [c.id for c in contas], "conflitos": res.conflitos},
        )
        ctx.db.commit()
    return {
        "id": pacote.id,
        "quantidade": pacote.quantidade,
        "valor_aula": str(pacote.valor_aula),
        "valor_total": str(pacote.valor_total),
        "data_inicio": pacote.data_inicio.isoformat(),
        "data_fim": pacote.data_fim.isoformat(),
        "reservas": res.reservas_criadas,
        "contas": [{"id": c.id, "reserva_id": c.reserva_id, "valor": str(c.valor), "vencimento": c.vencimento.isoformat()} for c in contas],
        "conflitos": res.conflitos,
        "aviso": res.mensagem_conflitos,
    }


@router.get("/agenda/alunos/{aluno_id}/avulsas")
def avulsas_do_aluno(aluno_id: int, ctx: Ctx):
    _aluno_do_escopo(ctx, aluno_id)
    itens = ctx.db.scalars(select(AulaAvulsa).where(AulaAvulsa.aluno_id == aluno_id).order_by(AulaAvulsa.data_inicio.desc()))
    return {
        "itens": [
            {
                "id": a.id,
                "plano_id": a.plano_id,
                "quantidade": a.quantidade,
                "valor_aula": str(a.valor_aula) if a.valor_aula is not None else None,
                "valor_total": str(a.valor_total),
                "data_inicio": a.data_inicio.isoformat(),
                "data_fim": a.data_fim.isoformat(),
            }
            for a in itens
        ]
    }


@router.post("/agenda/avaliativas", status_code=201)
def criar_avaliativa(dados: AvaliativaIn, ctx: Ctx):
    with _erros(ctx):
        av, reserva = avulsa.criar_aula_avaliativa(ctx.db, **dados.model_dump())
        ctx.auditar(
            "aula_avaliativa.criar",
            "aula_avaliativa",
            av.id,
            descricao=f"{_nome_aluno(ctx, av.aluno_id)} - {av.data:%d/%m/%Y} {av.hora_inicio:%H:%M} ({av.tipo})",
            depois=audit.snapshot(av),
        )
        ctx.db.commit()
    return avulsa.avaliativa_para_dict(av) | {"reserva_id": reserva.id}


@router.get("/agenda/alunos/{aluno_id}/avaliativas")
def avaliativas_do_aluno(aluno_id: int, ctx: Ctx):
    _aluno_do_escopo(ctx, aluno_id)
    q = select(AulaAvaliativa).where(AulaAvaliativa.aluno_id == aluno_id).order_by(AulaAvaliativa.data.desc())
    prof = _prof_escopo(ctx)
    if prof is not None:
        q = q.where(AulaAvaliativa.profissional_id == (None if prof == consultas.PROFISSIONAL_NENHUM else prof))
    return {"itens": [avulsa.avaliativa_para_dict(a) for a in ctx.db.scalars(q)]}


@router.put("/agenda/avaliativas/{avaliativa_id}/ficha")
def salvar_ficha(avaliativa_id: int, dados: FichaAvaliativaIn, ctx: Ctx):
    av = ctx.db.get(AulaAvaliativa, avaliativa_id)
    if av is None or not escopo.pode_acessar_profissional(ctx, av.profissional_id):
        raise _nao_achou("Aula avaliativa não encontrada.")
    with _erros(ctx):
        antes = audit.snapshot(av)
        av = avulsa.salvar_ficha_avaliativa(ctx.db, av.id, **dados.model_dump())
        a, d = audit.diff(antes, audit.snapshot(av))
        ctx.auditar("aula_avaliativa.ficha", "aula_avaliativa", av.id, antes=a, depois=d)
        ctx.db.commit()
    return avulsa.avaliativa_para_dict(av)


@router.post("/agenda/avaliativas/{avaliativa_id}/converter")
def converter_avaliativa(avaliativa_id: int, ctx: Ctx):
    """Marca como CONVERTIDA. NÃO cria contrato: crie o contrato do aluno na aba Contratos."""
    if ctx.somente_proprias_aulas():
        raise HTTPException(403, "Sem permissao para converter.")
    with _erros(ctx):
        av = avulsa.converter_avaliativa(ctx.db, avaliativa_id)
        ctx.auditar("aula_avaliativa.converter", "aula_avaliativa", av.id, descricao=_nome_aluno(ctx, av.aluno_id))
        ctx.db.commit()
    return avulsa.avaliativa_para_dict(av) | {"mensagem": "Marcada como convertida. Crie o contrato do aluno na aba Contratos."}
