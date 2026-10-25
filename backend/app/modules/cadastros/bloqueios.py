"""Bloqueios de agenda: pontual (período + faixa de horas) ou recorrente por dia da semana.

A regra de "este slot está bloqueado?" é `app.domain.agenda.slot_bloqueado` (a mesma da agenda e do contrato);
aqui só se cadastra e se explica ao usuário até quando o bloqueio vale.

Divergência deliberada do antigo: lá um bloqueio pontual sem data final valia PARA SEMPRE (sem aviso). No sistema
novo a data final é obrigatória no bloqueio pontual. Registros migrados nessa situação continuam valendo (nada
muda na agenda), aparecem com um aviso e só podem ser salvos de novo depois de informar a data final.
O bloqueio recorrente pode ficar sem data final (ex.: "toda terça das 12h às 13h"), mas o aviso fica visível.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.domain import agenda as dom
from app.modules.cadastros.horarios import OpcoesOut
from app.modules.cadastros.horarios import opcoes as opcoes_horarios
from app.modules.cadastros.models import BloqueioAgenda, Profissional, TipoServico, Unidade
from app.modules.cadastros.util_docs import (
    DIAS_SEMANA,
    PaginaContagens,
    Pedido,
    Texto,
    contem,
    foto,
    nao_encontrado,
    ordem,
    pagina_de,
    parametros_lista,
    regra,
)

router = APIRouter(prefix="/cadastros/bloqueios", tags=["cadastros: bloqueios"])

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje_negocio() -> date:
    """Data local do estúdio (America/Sao_Paulo). Isolada para os testes poderem fixar o dia."""
    return datetime.now(FUSO).date()


# ------------------------------------------------------------------------------------------------ esquemas
class BloqueioIn(Schema):
    unidade_id: int
    tipo_servico_id: int | None = None  # vazio = todos os serviços
    profissional_id: int | None = None  # vazio = todos os profissionais
    recorrente: bool = False
    dias_semana: list[int] = []  # só no recorrente (0 = segunda ... 6 = domingo); um bloqueio é criado por dia
    data_inicio: date
    data_fim: date | None = None
    hora_inicio: time
    hora_fim: time
    motivo: Texto | None = Field(default=None, max_length=200)
    ativo: bool = True

    @model_validator(mode="after")
    def _regras(self):
        self.hora_inicio, self.hora_fim = self.hora_inicio.replace(second=0, microsecond=0), self.hora_fim.replace(second=0, microsecond=0)
        if self.hora_fim <= self.hora_inicio:
            raise regra("O horário final deve ser maior que o inicial.")
        if self.data_fim is not None and self.data_fim < self.data_inicio:
            raise regra("A data final não pode ser anterior à inicial.")
        if self.recorrente:
            if not self.dias_semana:
                raise regra("Escolha ao menos um dia da semana para o bloqueio recorrente.")
            if any(d < 0 or d > 6 for d in self.dias_semana):
                raise regra("Dia da semana inválido (0 = segunda ... 6 = domingo).")
        else:
            if self.data_fim is None:
                raise regra(
                    "Informe a data final: um bloqueio pontual sem data final ficaria valendo para sempre. "
                    "Para bloquear um único dia, use a mesma data nos dois campos."
                )
            self.dias_semana = []
        return self


class BloqueioOut(Schema):
    id: int
    unidade_id: int
    unidade_nome: str
    tipo_servico_id: int | None
    tipo_servico_nome: str
    profissional_id: int | None
    profissional_nome: str
    recorrente: bool
    dia_semana: int | None
    dia_nome: str | None
    data_inicio: date
    data_fim: date | None
    hora_inicio: time
    hora_fim: time
    motivo: str | None
    ativo: bool
    situacao: str  # vigente | agendado | expirado | inativo
    vale_ate: str  # texto pronto: "Até 30/11/2026" / "Sem data final (vale para sempre)"
    aviso: str | None = None


class ResultadoCriacao(Schema):
    criados: int
    bloqueios: list[BloqueioOut]


# ------------------------------------------------------------------------------------------------ utilidades
def _situacao(b: BloqueioAgenda, hoje: date) -> str:
    if not b.ativo:
        return "inativo"
    if b.data_fim is not None and b.data_fim < hoje:
        return "expirado"
    if b.data_inicio > hoje:
        return "agendado"
    return "vigente"


def vale_ate(b: BloqueioAgenda) -> tuple[str, str | None]:
    """(texto "vale até quando", aviso). Bloqueio sem data final vale para sempre: fica explícito na tela."""
    if b.data_fim is not None:
        return f"Até {b.data_fim:%d/%m/%Y}", None
    if b.recorrente:
        return (
            "Sem data final (vale para sempre)",
            "Sem data final: este bloqueio continua valendo toda semana até ser inativado ou receber uma data final.",
        )
    return (
        "Sem data final (vale para sempre)",
        "Bloqueio pontual antigo sem data final: está valendo para sempre. Informe a data final ao editá-lo.",
    )


def _out(b: BloqueioAgenda, u: Unidade, s: TipoServico | None, p: Profissional | None, hoje: date) -> BloqueioOut:
    ate, aviso = vale_ate(b)
    return BloqueioOut(
        id=b.id, unidade_id=u.id, unidade_nome=u.nome, tipo_servico_id=b.tipo_servico_id,
        tipo_servico_nome=s.nome if s else "Todos os serviços", profissional_id=b.profissional_id,
        profissional_nome=p.nome if p else "Todos os profissionais", recorrente=b.recorrente, dia_semana=b.dia_semana,
        dia_nome=DIAS_SEMANA[b.dia_semana] if b.dia_semana is not None else None, data_inicio=b.data_inicio,
        data_fim=b.data_fim, hora_inicio=b.hora_inicio, hora_fim=b.hora_fim, motivo=b.motivo, ativo=b.ativo,
        situacao=_situacao(b, hoje), vale_ate=ate, aviso=aviso,
    )


def _select():
    return (
        select(BloqueioAgenda, Unidade, TipoServico, Profissional)
        .join(Unidade, BloqueioAgenda.unidade_id == Unidade.id)
        .outerjoin(TipoServico, BloqueioAgenda.tipo_servico_id == TipoServico.id)
        .outerjoin(Profissional, BloqueioAgenda.profissional_id == Profissional.id)
    )


def _um(db: Session, bid: int) -> BloqueioOut:
    b, u, s, p = db.execute(_select().where(BloqueioAgenda.id == bid)).one()
    return _out(b, u, s, p, hoje_negocio())


def _bloqueio(ctx, bid: int) -> BloqueioAgenda:
    b = ctx.db.get(BloqueioAgenda, bid)
    if not b:
        raise nao_encontrado("Bloqueio")
    return b


def _validar_refs(db: Session, d: BloqueioIn) -> None:
    if not db.get(Unidade, d.unidade_id):
        raise HTTPException(422, "Escolha uma unidade existente.")
    if d.tipo_servico_id is not None and not db.get(TipoServico, d.tipo_servico_id):
        raise HTTPException(422, "Escolha um tipo de serviço existente.")
    if d.profissional_id is not None and not db.get(Profissional, d.profissional_id):
        raise HTTPException(422, "Escolha um profissional existente.")


def _como_dominio(b: BloqueioAgenda) -> dom.Bloqueio:
    return dom.Bloqueio(
        hora_inicio=b.hora_inicio, hora_fim=b.hora_fim, data_inicio=b.data_inicio, data_fim=b.data_fim,
        recorrente=b.recorrente, dia_semana=b.dia_semana, ativo=b.ativo, tipo_servico_id=b.tipo_servico_id,
        profissional_id=b.profissional_id,
    )


def datas_afetadas(b: BloqueioAgenda, inicio: date, dias: int = 90) -> list[date]:
    """Datas, a partir de `inicio`, em que o bloqueio efetivamente bloqueia (usa `slot_bloqueado` da agenda)."""
    if not b.ativo:
        return []
    dom_b = _como_dominio(b)
    achadas = []
    for i in range(dias):
        dia = inicio + timedelta(days=i)
        if dom.slot_bloqueado([dom_b], dia, b.hora_inicio, b.hora_fim):
            achadas.append(dia)
    return achadas


# ------------------------------------------------------------------------------------------------ rotas
@router.get("", response_model=PaginaContagens[BloqueioOut])
def listar(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    unidade_id: Annotated[int | None, Query()] = None,
    tipo_servico_id: Annotated[int | None, Query()] = None,
    profissional_id: Annotated[int | None, Query()] = None,
    situacao: Annotated[str, Query(pattern="^(todos|vigentes|expirados|inativos)$")] = "todos",
):
    """Chips: vigentes (ativos que ainda valem, inclusive os que começam depois), expirados (data final passou) e inativos.
    `q` busca no motivo, na unidade, no serviço e no profissional."""
    hoje = hoje_negocio()
    base = _select()
    if pedido.q:
        base = base.where(
            contem(func.coalesce(BloqueioAgenda.motivo, ""), pedido.q) | contem(Unidade.nome, pedido.q)
            | contem(func.coalesce(TipoServico.nome, ""), pedido.q) | contem(func.coalesce(Profissional.nome, ""), pedido.q)
        )
    if unidade_id:
        base = base.where(BloqueioAgenda.unidade_id == unidade_id)
    if tipo_servico_id:
        base = base.where(BloqueioAgenda.tipo_servico_id == tipo_servico_id)
    if profissional_id:
        base = base.where(BloqueioAgenda.profissional_id == profissional_id)
    contagens = {"todos": 0, "vigentes": 0, "expirados": 0, "inativos": 0}
    for b, *_ in ctx.db.execute(base).all():
        contagens["todos"] += 1
        sit = _situacao(b, hoje)
        contagens["vigentes" if sit in ("vigente", "agendado") else sit + "s"] += 1
    stmt = base
    expirado = BloqueioAgenda.data_fim.is_not(None) & (BloqueioAgenda.data_fim < hoje)
    if situacao == "vigentes":
        stmt = stmt.where(BloqueioAgenda.ativo.is_(True), ~expirado)
    elif situacao == "expirados":
        stmt = stmt.where(BloqueioAgenda.ativo.is_(True), expirado)
    elif situacao == "inativos":
        stmt = stmt.where(BloqueioAgenda.ativo.is_(False))
    colunas = {
        "data": BloqueioAgenda.data_inicio, "unidade": func.lower(Unidade.nome), "inicio": BloqueioAgenda.hora_inicio,
        "fim": BloqueioAgenda.data_fim,
    }
    pedido_ord = pedido if pedido.ordenar else pedido.model_copy(update={"ordenar": "data", "direcao": "desc"})
    stmt = stmt.order_by(ordem(pedido_ord, colunas, "data"), BloqueioAgenda.hora_inicio, BloqueioAgenda.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=[_out(b, u, s, p, hoje) for b, u, s, p in linhas], total=total, pagina=pedido.pagina,
        por_pagina=pedido.por_pagina, contagens=contagens,
    )


@router.get("/opcoes", response_model=OpcoesOut)
def opcoes_bloqueio(ctx: Ctx):
    """Mesmas listas do formulário de horários (unidades, serviços, profissionais), sob a permissão de bloqueios."""
    return opcoes_horarios(ctx)


@router.get("/{bid}", response_model=BloqueioOut)
def ler(bid: int, ctx: Ctx):
    _bloqueio(ctx, bid)
    return _um(ctx.db, bid)


@router.get("/{bid}/datas", response_model=list[date])
def datas(bid: int, ctx: Ctx, dias: Annotated[int, Query(ge=1, le=366)] = 90):
    """Próximas datas (a partir de hoje) em que o bloqueio vale, conforme a regra da agenda."""
    return datas_afetadas(_bloqueio(ctx, bid), hoje_negocio(), dias)


@router.post("", response_model=ResultadoCriacao, status_code=201)
def criar(dados: BloqueioIn, ctx: Ctx):
    """Pontual: cria 1. Recorrente: cria 1 por dia da semana marcado (como o antigo)."""
    _validar_refs(ctx.db, dados)
    dias = sorted(set(dados.dias_semana)) if dados.recorrente else [None]
    criados: list[BloqueioAgenda] = []
    for dia in dias:
        b = BloqueioAgenda(
            unidade_id=dados.unidade_id, tipo_servico_id=dados.tipo_servico_id, profissional_id=dados.profissional_id,
            recorrente=dados.recorrente, dia_semana=dia, data_inicio=dados.data_inicio, data_fim=dados.data_fim,
            hora_inicio=dados.hora_inicio, hora_fim=dados.hora_fim, motivo=dados.motivo, ativo=dados.ativo,
        )
        ctx.db.add(b)
        ctx.db.flush()
        criados.append(b)
        ctx.auditar("bloqueio_agenda.criar", "bloqueio_agenda", b.id, descricao=dados.motivo, depois=foto(b))
    ctx.db.commit()
    return ResultadoCriacao(criados=len(criados), bloqueios=[_um(ctx.db, b.id) for b in criados])


@router.put("/{bid}", response_model=BloqueioOut)
def alterar(bid: int, dados: BloqueioIn, ctx: Ctx):
    b = _bloqueio(ctx, bid)
    _validar_refs(ctx.db, dados)
    if dados.recorrente and len(set(dados.dias_semana)) != 1:
        raise HTTPException(
            422, "Ao editar, escolha apenas um dia da semana. Para bloquear outros dias, crie um novo bloqueio."
        )
    antes = foto(b)
    b.unidade_id, b.tipo_servico_id, b.profissional_id = dados.unidade_id, dados.tipo_servico_id, dados.profissional_id
    b.recorrente = dados.recorrente
    b.dia_semana = dados.dias_semana[0] if dados.recorrente else None
    b.data_inicio, b.data_fim = dados.data_inicio, dados.data_fim
    b.hora_inicio, b.hora_fim, b.motivo, b.ativo = dados.hora_inicio, dados.hora_fim, dados.motivo, dados.ativo
    ctx.db.flush()
    ctx.auditar("bloqueio_agenda.alterar", "bloqueio_agenda", b.id, descricao=b.motivo, antes=antes, depois=foto(b))
    ctx.db.commit()
    return _um(ctx.db, b.id)


@router.patch("/{bid}/ativo", response_model=BloqueioOut)
def ativar(bid: int, ctx: Ctx, ativo: Annotated[bool, Query()]):
    b = _bloqueio(ctx, bid)
    if b.ativo != ativo:
        b.ativo = ativo
        ctx.auditar("bloqueio_agenda.ativar" if ativo else "bloqueio_agenda.inativar", "bloqueio_agenda", b.id, descricao=b.motivo)
        ctx.db.commit()
    return _um(ctx.db, b.id)


@router.delete("/{bid}", response_model=Mensagem)
def excluir(bid: int, ctx: Ctx):
    """Excluir libera os horários na hora; para só pausar, inative."""
    b = _bloqueio(ctx, bid)
    antes = foto(b)
    ctx.db.delete(b)
    ctx.auditar("bloqueio_agenda.excluir", "bloqueio_agenda", bid, descricao=b.motivo, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Bloqueio excluído.")
