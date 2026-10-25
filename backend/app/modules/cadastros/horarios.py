"""Horários de funcionamento da unidade (janelas por dia da semana) e horários do studio (grade legada).

Regra de negócio dos slots (arredondamento para a hora cheia, duração + 10 min de intervalo) fica em
`app.domain.agenda`; aqui só se cadastra a janela e se mostra quantas aulas ela gera.
"""

from __future__ import annotations

from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Ctx
from app.core.schemas import Mensagem, Schema
from app.domain import agenda as dom
from app.modules.cadastros.models import (
    HorarioFuncionamento,
    HorarioStudio,
    Profissional,
    TipoServico,
    Unidade,
    horario_funcionamento_tipo_servico,
    proximo_codigo,
)
from app.modules.cadastros.util_docs import (
    DIAS_SEMANA,
    PaginaContagens,
    Pedido,
    contem,
    foto,
    nao_encontrado,
    ordem,
    pagina_de,
    parametros_lista,
    regra,
)

router = APIRouter(prefix="/cadastros/horarios", tags=["cadastros: horários"])

MAX_HORARIOS_POR_GERACAO = 2000


# ------------------------------------------------------------------------------------------------ esquemas
class OpcaoOut(Schema):
    id: int
    nome: str
    ativo: bool = True


class DiaOut(Schema):
    valor: int
    nome: str


class OpcoesOut(Schema):
    unidades: list[OpcaoOut]
    servicos: list[OpcaoOut]
    profissionais: list[OpcaoOut]
    dias: list[DiaOut]


def _sem_segundos(t: time) -> time:
    return t.replace(second=0, microsecond=0)


class _Janela(Schema):
    hora_inicio: time
    hora_fim: time

    @model_validator(mode="after")
    def _fim_depois_do_inicio(self):
        self.hora_inicio, self.hora_fim = _sem_segundos(self.hora_inicio), _sem_segundos(self.hora_fim)
        if self.hora_fim <= self.hora_inicio:
            raise regra("O horário final deve ser maior que o inicial.")
        return self


class HorarioIn(_Janela):
    unidade_id: int
    dia_semana: int = Field(ge=0, le=6)
    tipos_servico_ids: list[int] = []
    ativo: bool = True


class GerarFuncionamentoIn(_Janela):
    unidade_id: int
    dias_semana: list[int] = Field(min_length=1, max_length=7)
    tipos_servico_ids: list[int] = []
    ativo: bool = True


class HorarioOut(Schema):
    id: int
    unidade_id: int
    unidade_nome: str
    dia_semana: int
    dia_nome: str
    hora_inicio: time
    hora_fim: time
    ativo: bool
    tipos_servico_ids: list[int]
    servicos: str  # "Todos os serviços" quando a lista é vazia
    aulas_por_dia: int  # quantas aulas a janela gera (duração da unidade + 10 min), via app.domain.agenda


class ResultadoGeracao(Schema):
    criados: int
    ignorados: int
    mensagem: str


class StudioIn(_Janela):
    unidade_id: int
    tipo_servico_id: int
    profissional_id: int | None = None
    dia_semana: int = Field(ge=0, le=6)
    capacidade: int | None = Field(default=None, ge=1, le=200)


class GerarStudioIn(_Janela):
    unidade_id: int
    tipo_servico_id: int
    profissional_id: int | None = None
    dias_semana: list[int] = Field(min_length=1, max_length=7)
    intervalo_minutos: int = Field(ge=5, le=480, description="Duração de cada horário gerado, em minutos")
    capacidade: int | None = Field(default=None, ge=1, le=200)


class StudioOut(Schema):
    id: int
    codigo: int | None
    unidade_id: int
    unidade_nome: str
    tipo_servico_id: int
    tipo_servico_nome: str
    profissional_id: int | None
    profissional_nome: str | None
    dia_semana: int
    dia_nome: str
    hora_inicio: time
    hora_fim: time
    capacidade: int | None
    legado: bool = True


# ------------------------------------------------------------------------------------------------ utilidades
def _dias_validos(dias: list[int]) -> list[int]:
    if any(d < 0 or d > 6 for d in dias):
        raise HTTPException(422, "Dia da semana inválido (0 = segunda ... 6 = domingo).")
    return sorted(set(dias))


def _unidade(db: Session, uid: int) -> Unidade:
    u = db.get(Unidade, uid)
    if not u:
        raise HTTPException(422, "Escolha uma unidade existente.")
    return u


def _servicos(db: Session, ids: list[int]) -> list[TipoServico]:
    unicos = sorted(set(ids))
    if not unicos:
        return []
    achados = list(db.scalars(select(TipoServico).where(TipoServico.id.in_(unicos)).order_by(TipoServico.nome)))
    if len(achados) != len(unicos):
        raise HTTPException(422, "Há tipo de serviço inexistente na lista.")
    return achados


def _tipo_servico(db: Session, sid: int) -> TipoServico:
    s = db.get(TipoServico, sid)
    if not s:
        raise HTTPException(422, "Escolha um tipo de serviço existente.")
    return s


def _profissional(db: Session, pid: int | None) -> Profissional | None:
    if pid is None:
        return None
    p = db.get(Profissional, pid)
    if not p:
        raise HTTPException(422, "Escolha um profissional existente.")
    return p


def _aulas_por_dia(unidade: Unidade, ini: time, fim: time) -> int:
    dur = dom.duracao_da_unidade(unidade.duracao_aula_minutos)
    return len(dom.gerar_slots_do_dia(date(2000, 1, 3), [(ini, fim)], dur))


def _servicos_do(db: Session, ids_por_horario: dict[int, list[int]], nomes: dict[int, str], hid: int) -> str:
    ids = ids_por_horario.get(hid, [])
    return ", ".join(nomes[i] for i in ids if i in nomes) if ids else "Todos os serviços"


def _ids_por_horario(db: Session, horarios: list[int]) -> dict[int, list[int]]:
    if not horarios:
        return {}
    t = horario_funcionamento_tipo_servico
    res: dict[int, list[int]] = {}
    for hid, sid in db.execute(
        select(t.c.horario_funcionamento_id, t.c.tipo_servico_id).where(t.c.horario_funcionamento_id.in_(horarios))
    ):
        res.setdefault(hid, []).append(sid)
    return res


def _out_horarios(db: Session, itens: list[tuple[HorarioFuncionamento, Unidade]]) -> list[HorarioOut]:
    ids = _ids_por_horario(db, [h.id for h, _ in itens])
    nomes = dict(db.execute(select(TipoServico.id, TipoServico.nome)).all())
    return [
        HorarioOut(
            id=h.id, unidade_id=u.id, unidade_nome=u.nome, dia_semana=h.dia_semana, dia_nome=DIAS_SEMANA[h.dia_semana],
            hora_inicio=h.hora_inicio, hora_fim=h.hora_fim, ativo=h.ativo, tipos_servico_ids=sorted(ids.get(h.id, [])),
            servicos=_servicos_do(db, ids, nomes, h.id), aulas_por_dia=_aulas_por_dia(u, h.hora_inicio, h.hora_fim),
        )
        for h, u in itens
    ]


def _um(db: Session, h: HorarioFuncionamento) -> HorarioOut:
    return _out_horarios(db, [(h, db.get(Unidade, h.unidade_id))])[0]


def _horario(ctx, hid: int) -> HorarioFuncionamento:
    h = ctx.db.get(HorarioFuncionamento, hid)
    if not h:
        raise nao_encontrado("Horário")
    return h


def _duplicado(db: Session, unidade_id: int, dia: int, ini: time, fim: time, servicos: list[int], exceto: int | None = None) -> bool:
    """Mesma regra de duplicidade do antigo: igual unidade/dia/início/fim e (sem serviço: já existe uma janela geral;
    com serviços: já existe janela geral ou que atenda algum dos mesmos serviços)."""
    q = select(HorarioFuncionamento.id).where(
        HorarioFuncionamento.unidade_id == unidade_id,
        HorarioFuncionamento.dia_semana == dia,
        HorarioFuncionamento.hora_inicio == ini,
        HorarioFuncionamento.hora_fim == fim,
        HorarioFuncionamento.id != (exceto or 0),
    )
    for hid in db.scalars(q):
        existentes = _ids_por_horario(db, [hid]).get(hid, [])
        if not existentes:
            return True  # janela geral cobre qualquer coisa que se queira cadastrar igual
        if servicos and set(existentes) & set(servicos):
            return True
    return False


def _texto_duplicado(unidade: Unidade, dia: int, ini: time, fim: time) -> str:
    return (
        f"Já existe um horário de {unidade.nome} na {DIAS_SEMANA[dia].lower()} das {ini:%H:%M} às {fim:%H:%M} "
        "para este serviço."
    )


# ------------------------------------------------------------------------------------------------ opções
@router.get("/opcoes", response_model=OpcoesOut)
def opcoes(ctx: Ctx):
    """Listas para os formulários de horários e bloqueios (unidades, serviços, profissionais)."""
    db = ctx.db
    return OpcoesOut(
        unidades=[OpcaoOut(id=u.id, nome=u.nome, ativo=u.ativo) for u in db.scalars(select(Unidade).order_by(Unidade.nome))],
        servicos=[OpcaoOut(id=s.id, nome=s.nome, ativo=s.ativo) for s in db.scalars(select(TipoServico).order_by(TipoServico.nome))],
        profissionais=[
            OpcaoOut(id=p.id, nome=p.nome, ativo=p.ativo) for p in db.scalars(select(Profissional).order_by(Profissional.nome))
        ],
        dias=[DiaOut(valor=i, nome=n) for i, n in enumerate(DIAS_SEMANA)],
    )


# ------------------------------------------------------------------------------------------------ studio (legado)
def _out_studio(db: Session, linhas) -> list[StudioOut]:
    return [
        StudioOut(
            id=h.id, codigo=h.codigo_legado, unidade_id=u.id, unidade_nome=u.nome, tipo_servico_id=s.id,
            tipo_servico_nome=s.nome, profissional_id=p.id if p else None, profissional_nome=p.nome if p else None,
            dia_semana=h.dia_semana, dia_nome=DIAS_SEMANA[h.dia_semana], hora_inicio=h.hora_inicio, hora_fim=h.hora_fim,
            capacidade=h.capacidade,
        )
        for h, u, s, p in linhas
    ]


def _select_studio():
    return (
        select(HorarioStudio, Unidade, TipoServico, Profissional)
        .join(Unidade, HorarioStudio.unidade_id == Unidade.id)
        .join(TipoServico, HorarioStudio.tipo_servico_id == TipoServico.id)
        .outerjoin(Profissional, HorarioStudio.profissional_id == Profissional.id)
    )


def _studio_um(db: Session, sid: int) -> StudioOut:
    return _out_studio(db, db.execute(_select_studio().where(HorarioStudio.id == sid)).all())[0]


def _studio(ctx, sid: int) -> HorarioStudio:
    h = ctx.db.get(HorarioStudio, sid)
    if not h:
        raise nao_encontrado("Horário do studio")
    return h


def _studio_existe(db: Session, d: dict, exceto: int | None = None) -> bool:
    q = select(HorarioStudio.id).where(
        HorarioStudio.unidade_id == d["unidade_id"],
        HorarioStudio.tipo_servico_id == d["tipo_servico_id"],
        HorarioStudio.profissional_id.is_(None) if d["profissional_id"] is None else HorarioStudio.profissional_id == d["profissional_id"],
        HorarioStudio.dia_semana == d["dia_semana"],
        HorarioStudio.hora_inicio == d["hora_inicio"],
        HorarioStudio.hora_fim == d["hora_fim"],
        HorarioStudio.id != (exceto or 0),
    )
    return db.scalar(q) is not None


@router.get("/studio", response_model=PaginaContagens[StudioOut])
def listar_studio(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    unidade_id: Annotated[int | None, Query()] = None,
    tipo_servico_id: Annotated[int | None, Query()] = None,
    profissional_id: Annotated[int | None, Query()] = None,
    dia_semana: Annotated[int | None, Query(ge=0, le=6)] = None,
):
    """Grade legada do studio (herdada do sistema antigo; mantida para paridade)."""
    stmt = _select_studio()
    if unidade_id:
        stmt = stmt.where(HorarioStudio.unidade_id == unidade_id)
    if tipo_servico_id:
        stmt = stmt.where(HorarioStudio.tipo_servico_id == tipo_servico_id)
    if profissional_id:
        stmt = stmt.where(HorarioStudio.profissional_id == profissional_id)
    if dia_semana is not None:
        stmt = stmt.where(HorarioStudio.dia_semana == dia_semana)
    colunas = {
        "dia": HorarioStudio.dia_semana, "unidade": func.lower(Unidade.nome), "servico": func.lower(TipoServico.nome),
        "inicio": HorarioStudio.hora_inicio,
    }
    stmt = stmt.order_by(ordem(pedido, colunas, "dia"), HorarioStudio.hora_inicio, HorarioStudio.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=_out_studio(ctx.db, linhas), total=total, pagina=pedido.pagina, por_pagina=pedido.por_pagina,
        contagens={"todos": total},
    )


def _dados_studio(db: Session, d: StudioIn) -> dict:
    _unidade(db, d.unidade_id)
    _tipo_servico(db, d.tipo_servico_id)
    _profissional(db, d.profissional_id)
    return d.model_dump()


@router.post("/studio/gerar", response_model=ResultadoGeracao)
def gerar_studio(dados: GerarStudioIn, ctx: Ctx):
    """Cria, para cada dia marcado, horários consecutivos de `intervalo_minutos` entre início e fim (como o antigo)."""
    db = ctx.db
    unidade = _unidade(db, dados.unidade_id)
    _tipo_servico(db, dados.tipo_servico_id)
    _profissional(db, dados.profissional_id)
    dias = _dias_validos(dados.dias_semana)
    ini = dados.hora_inicio.hour * 60 + dados.hora_inicio.minute
    fim = dados.hora_fim.hour * 60 + dados.hora_fim.minute
    faixas = [(m, m + dados.intervalo_minutos) for m in range(ini, fim - dados.intervalo_minutos + 1, dados.intervalo_minutos)]
    if not faixas:
        raise HTTPException(422, "O intervalo é maior que o período informado; nenhum horário cabe.")
    if len(faixas) * len(dias) > MAX_HORARIOS_POR_GERACAO:
        raise HTTPException(422, f"Isso geraria mais de {MAX_HORARIOS_POR_GERACAO} horários; reduza dias ou período.")
    criados = ignorados = 0
    for dia in dias:
        for a, b in faixas:
            d = {
                "unidade_id": dados.unidade_id, "tipo_servico_id": dados.tipo_servico_id,
                "profissional_id": dados.profissional_id, "dia_semana": dia, "hora_inicio": time(a // 60, a % 60),
                "hora_fim": time(b // 60, b % 60),
            }
            if _studio_existe(db, d):
                ignorados += 1
                continue
            db.add(HorarioStudio(**d, capacidade=dados.capacidade, codigo_legado=proximo_codigo(db, "horario_studio")))
            db.flush()
            criados += 1
    msg = f"{criados} horário(s) criado(s)." if criados else "Nenhum horário novo: todos já existiam."
    ctx.auditar(
        "horario_studio.gerar", "horario_studio", None,
        descricao=f"{unidade.nome}: {criados} criado(s), {ignorados} já existente(s)",
        depois={**dados.model_dump(mode="json"), "criados": criados, "ignorados": ignorados},
    )
    db.commit()
    return ResultadoGeracao(criados=criados, ignorados=ignorados, mensagem=msg)


@router.post("/studio", response_model=StudioOut, status_code=201)
def criar_studio(dados: StudioIn, ctx: Ctx):
    d = _dados_studio(ctx.db, dados)
    if _studio_existe(ctx.db, d):
        raise HTTPException(409, "Já existe este horário do studio (mesma unidade, serviço, profissional, dia e faixa).")
    h = HorarioStudio(**d, codigo_legado=proximo_codigo(ctx.db, "horario_studio"))
    ctx.db.add(h)
    ctx.db.flush()
    ctx.auditar("horario_studio.criar", "horario_studio", h.id, depois=foto(h))
    ctx.db.commit()
    return _studio_um(ctx.db, h.id)


@router.put("/studio/{sid}", response_model=StudioOut)
def alterar_studio(sid: int, dados: StudioIn, ctx: Ctx):
    h = _studio(ctx, sid)
    d = _dados_studio(ctx.db, dados)
    if _studio_existe(ctx.db, d, exceto=sid):
        raise HTTPException(409, "Já existe este horário do studio (mesma unidade, serviço, profissional, dia e faixa).")
    antes = foto(h)
    for k, v in d.items():
        setattr(h, k, v)
    ctx.db.flush()
    ctx.auditar("horario_studio.alterar", "horario_studio", h.id, antes=antes, depois=foto(h))
    ctx.db.commit()
    return _studio_um(ctx.db, h.id)


@router.delete("/studio/{sid}", response_model=Mensagem)
def excluir_studio(sid: int, ctx: Ctx):
    h = _studio(ctx, sid)
    antes = foto(h)
    ctx.db.delete(h)
    ctx.auditar("horario_studio.excluir", "horario_studio", sid, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Horário do studio excluído.")


# ------------------------------------------------------------------------------------------------ funcionamento
@router.post("/gerar", response_model=ResultadoGeracao)
def gerar_funcionamento(dados: GerarFuncionamentoIn, ctx: Ctx):
    """Cria a mesma janela (início/fim, serviços) em vários dias da semana de uma vez; ignora o que já existe."""
    db = ctx.db
    unidade = _unidade(db, dados.unidade_id)
    servicos = _servicos(db, dados.tipos_servico_ids)
    sids = [s.id for s in servicos]
    criados = ignorados = 0
    for dia in _dias_validos(dados.dias_semana):
        if _duplicado(db, unidade.id, dia, dados.hora_inicio, dados.hora_fim, sids):
            ignorados += 1
            continue
        h = HorarioFuncionamento(
            unidade_id=unidade.id, dia_semana=dia, hora_inicio=dados.hora_inicio, hora_fim=dados.hora_fim,
            ativo=dados.ativo, tipos_servico=servicos,
        )
        db.add(h)
        db.flush()
        criados += 1
    msg = f"{criados} horário(s) criado(s)." if criados else "Nenhum horário novo: todos já existiam."
    if criados and ignorados:
        msg += f" {ignorados} já existia(m) e foi(ram) ignorado(s)."
    ctx.auditar(
        "horario_funcionamento.gerar", "horario_funcionamento", None,
        descricao=f"{unidade.nome}: {criados} criado(s), {ignorados} já existente(s)",
        depois={**dados.model_dump(mode="json"), "criados": criados, "ignorados": ignorados},
    )
    db.commit()
    return ResultadoGeracao(criados=criados, ignorados=ignorados, mensagem=msg)


@router.get("", response_model=PaginaContagens[HorarioOut])
def listar(
    ctx: Ctx,
    pedido: Annotated[Pedido, Depends(parametros_lista)],
    unidade_id: Annotated[int | None, Query()] = None,
    dia_semana: Annotated[int | None, Query(ge=0, le=6)] = None,
    tipo_servico_id: Annotated[int | None, Query()] = None,
    situacao: Annotated[str, Query(pattern="^(todos|ativos|inativos)$")] = "todos",
):
    """`q` busca pelo nome da unidade. `tipo_servico_id` traz as janelas que atendem o serviço (inclusive as gerais)."""
    base = select(HorarioFuncionamento, Unidade).join(Unidade, HorarioFuncionamento.unidade_id == Unidade.id)
    if pedido.q:
        base = base.where(contem(Unidade.nome, pedido.q))
    if unidade_id:
        base = base.where(HorarioFuncionamento.unidade_id == unidade_id)
    if dia_semana is not None:
        base = base.where(HorarioFuncionamento.dia_semana == dia_semana)
    if tipo_servico_id:
        t = horario_funcionamento_tipo_servico
        com_servico = select(t.c.horario_funcionamento_id).where(t.c.tipo_servico_id == tipo_servico_id)
        qualquer = select(t.c.horario_funcionamento_id)
        base = base.where(HorarioFuncionamento.id.in_(com_servico) | HorarioFuncionamento.id.not_in(qualquer))
    contagens = {"todos": 0, "ativos": 0, "inativos": 0}
    for h, _u in ctx.db.execute(base).all():
        contagens["todos"] += 1
        contagens["ativos" if h.ativo else "inativos"] += 1
    stmt = base
    if situacao != "todos":
        stmt = stmt.where(HorarioFuncionamento.ativo.is_(situacao == "ativos"))
    colunas = {
        "dia": HorarioFuncionamento.dia_semana, "unidade": func.lower(Unidade.nome), "inicio": HorarioFuncionamento.hora_inicio,
    }
    stmt = stmt.order_by(ordem(pedido, colunas, "dia"), func.lower(Unidade.nome), HorarioFuncionamento.hora_inicio, HorarioFuncionamento.id)
    linhas, total = pagina_de(ctx.db, stmt, pedido)
    return PaginaContagens(
        itens=_out_horarios(ctx.db, [(h, u) for h, u in linhas]), total=total, pagina=pedido.pagina,
        por_pagina=pedido.por_pagina, contagens=contagens,
    )


@router.get("/{hid}", response_model=HorarioOut)
def ler(hid: int, ctx: Ctx):
    return _um(ctx.db, _horario(ctx, hid))


@router.post("", response_model=HorarioOut, status_code=201)
def criar(dados: HorarioIn, ctx: Ctx):
    unidade = _unidade(ctx.db, dados.unidade_id)
    servicos = _servicos(ctx.db, dados.tipos_servico_ids)
    if _duplicado(ctx.db, unidade.id, dados.dia_semana, dados.hora_inicio, dados.hora_fim, [s.id for s in servicos]):
        raise HTTPException(409, _texto_duplicado(unidade, dados.dia_semana, dados.hora_inicio, dados.hora_fim))
    h = HorarioFuncionamento(
        unidade_id=unidade.id, dia_semana=dados.dia_semana, hora_inicio=dados.hora_inicio, hora_fim=dados.hora_fim,
        ativo=dados.ativo, tipos_servico=servicos,
    )
    ctx.db.add(h)
    ctx.db.flush()
    ctx.auditar(
        "horario_funcionamento.criar", "horario_funcionamento", h.id,
        descricao=f"{unidade.nome} {DIAS_SEMANA[h.dia_semana]} {h.hora_inicio:%H:%M}-{h.hora_fim:%H:%M}",
        depois={**foto(h), "tipos_servico_ids": [s.id for s in servicos]},
    )
    ctx.db.commit()
    return _um(ctx.db, h)


@router.put("/{hid}", response_model=HorarioOut)
def alterar(hid: int, dados: HorarioIn, ctx: Ctx):
    h = _horario(ctx, hid)
    unidade = _unidade(ctx.db, dados.unidade_id)
    servicos = _servicos(ctx.db, dados.tipos_servico_ids)
    sids = [s.id for s in servicos]
    if _duplicado(ctx.db, unidade.id, dados.dia_semana, dados.hora_inicio, dados.hora_fim, sids, exceto=hid):
        raise HTTPException(409, _texto_duplicado(unidade, dados.dia_semana, dados.hora_inicio, dados.hora_fim))
    antes = {**foto(h), "tipos_servico_ids": sorted(s.id for s in h.tipos_servico)}
    h.unidade_id, h.dia_semana = unidade.id, dados.dia_semana
    h.hora_inicio, h.hora_fim, h.ativo = dados.hora_inicio, dados.hora_fim, dados.ativo
    h.tipos_servico = servicos
    ctx.db.flush()
    ctx.auditar(
        "horario_funcionamento.alterar", "horario_funcionamento", h.id, antes=antes,
        depois={**foto(h), "tipos_servico_ids": sorted(sids)},
    )
    ctx.db.commit()
    return _um(ctx.db, h)


@router.patch("/{hid}/ativo", response_model=HorarioOut)
def ativar(hid: int, ctx: Ctx, ativo: Annotated[bool, Query()]):
    h = _horario(ctx, hid)
    if h.ativo != ativo:
        h.ativo = ativo
        ctx.auditar("horario_funcionamento.ativar" if ativo else "horario_funcionamento.inativar", "horario_funcionamento", h.id)
        ctx.db.commit()
    return _um(ctx.db, h)


@router.delete("/{hid}", response_model=Mensagem)
def excluir(hid: int, ctx: Ctx):
    """Aulas já criadas a partir da janela não são afetadas; para parar de gerar novas, basta inativar."""
    h = _horario(ctx, hid)
    antes = {**foto(h), "tipos_servico_ids": sorted(s.id for s in h.tipos_servico)}
    ctx.db.delete(h)
    ctx.auditar("horario_funcionamento.excluir", "horario_funcionamento", hid, antes=antes)
    ctx.db.commit()
    return Mensagem(mensagem="Horário excluído.")
