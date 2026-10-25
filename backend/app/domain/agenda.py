"""Agenda: slots, bloqueios, horários de funcionamento e agenda do contrato.

Origem no sistema antigo (``core/views.py``):
- ``AULA_INTERVALO_MINUTOS`` (linha 316), ``_round_to_next_hour`` (311), ``_generate_slots_for_date`` (410-421)
- ``_load_funcionamento`` (319-348): quais janelas valem para um tipo de serviço
- ``_load_bloqueios`` (371-381) e ``_is_slot_blocked`` (384-407)
- ``contrato_agenda`` (5893-6075): janela de datas, seleção de horários, bloqueios, vagas, conflitos
- ``aluno_aula_avulsa_agenda`` (1236-1310): datas do pacote avulso (``_align_date_to_weekday`` 215, ``_advance_recorrencia_date`` 212)

Tudo puro: o chamador carrega do banco (janelas, bloqueios, sessões existentes) e passa para cá.
Dias da semana seguem o Python (``date.weekday()``: 0 = segunda ... 6 = domingo), igual ao antigo.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app.domain import capacidade as cap
from app.domain.parcelas import add_months

AULA_INTERVALO_MINUTOS = 10
DURACAO_PADRAO_MINUTOS = 50
SEMANAS_AGENDA_CONTRATO_SEMANAL = 4


# ---------------------------------------------------------------------------
# Slots a partir das janelas de funcionamento
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Janela:
    """Janela de funcionamento de um dia da semana (``HorarioFuncionamento``)."""

    dia_semana: int
    hora_inicio: time
    hora_fim: time
    ativo: bool = True
    #: ids dos tipos de serviço atendidos; vazio = todos os serviços
    servicos: frozenset[int] = frozenset()


def arredondar_para_proxima_hora(momento: datetime) -> datetime:
    """Se não estiver exatamente na hora cheia, sobe para a próxima (08:30 -> 09:00).

    # COMPORTAMENTO ANTIGO: o início de cada janela é arredondado para cima. Uma janela 08:30-12:00 gera
    slots a partir das 09:00 (a meia hora inicial é perdida).
    """
    if momento.minute == 0 and momento.second == 0 and momento.microsecond == 0:
        return momento
    return momento.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def gerar_slots_do_dia(
    dia: date,
    janelas: Iterable[Janela | tuple[time, time]],
    duracao_minutos: int,
    intervalo_minutos: int = AULA_INTERVALO_MINUTOS,
) -> list[tuple[time, time]]:
    """Slots ``(inicio, fim)`` do dia: dentro de cada janela, a cada ``duracao + 10`` minutos, só os que cabem
    inteiros antes do fim da janela. A janela pode ser um ``Janela`` ou uma tupla ``(hora_inicio, hora_fim)``.
    """
    slots: list[tuple[time, time]] = []
    for janela in janelas:
        hora_ini, hora_fim = (janela.hora_inicio, janela.hora_fim) if isinstance(janela, Janela) else janela
        inicio = arredondar_para_proxima_hora(datetime.combine(dia, hora_ini))
        fim_janela = datetime.combine(dia, hora_fim)
        while inicio + timedelta(minutes=duracao_minutos) <= fim_janela:
            fim_slot = inicio + timedelta(minutes=duracao_minutos)
            slots.append((inicio.time(), fim_slot.time()))
            inicio += timedelta(minutes=duracao_minutos + intervalo_minutos)
    return slots


def duracao_da_unidade(duracao_aula_minutos: int | None) -> int:
    """``unidade.duracao_aula_minutos or 50``."""
    return duracao_aula_minutos or DURACAO_PADRAO_MINUTOS


def janelas_por_dia(janelas: Iterable[Janela], tipo_servico_id: int | None = None) -> dict[int, list[Janela]]:
    """``_load_funcionamento``: janelas ATIVAS agrupadas por dia da semana.

    Sem ``tipo_servico_id``: todas as ativas. Com ele: só as que atendem o serviço (lista ``servicos`` contém
    o id) ou as genéricas (``servicos`` vazio). Se num dia existir janela ESPECÍFICA do serviço, ela SUBSTITUI as
    genéricas daquele dia. Ordem: dia, hora de início.
    """
    ativas = sorted((j for j in janelas if j.ativo), key=lambda j: (j.dia_semana, j.hora_inicio))
    por_dia: dict[int, list[Janela]] = {}
    if tipo_servico_id is None:
        for j in ativas:
            por_dia.setdefault(j.dia_semana, []).append(j)
        return por_dia
    especificas: dict[int, list[Janela]] = {}
    for j in ativas:
        if tipo_servico_id in j.servicos:
            especificas.setdefault(j.dia_semana, []).append(j)
        elif not j.servicos:
            por_dia.setdefault(j.dia_semana, []).append(j)
    for dia, itens in especificas.items():
        por_dia[dia] = itens
    return por_dia


# ---------------------------------------------------------------------------
# Bloqueios
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Bloqueio:
    """``BloqueioAgenda``. Pontual (``recorrente=False``): vale de ``data_inicio`` até ``data_fim`` (ou sem fim)
    nos horários indicados, TODOS os dias do período. Recorrente: só no ``dia_semana``, dentro do período."""

    hora_inicio: time
    hora_fim: time
    data_inicio: date
    data_fim: date | None = None
    recorrente: bool = False
    dia_semana: int | None = None
    ativo: bool = True
    tipo_servico_id: int | None = None
    profissional_id: int | None = None


def bloqueios_aplicaveis(
    bloqueios: Iterable[Bloqueio],
    tipo_servico_id: int | None,
    profissional_id: int | None,
    inicio: date,
    fim: date,
) -> list[Bloqueio]:
    """``_load_bloqueios``: ativos que cruzam o período e que se aplicam ao serviço/profissional.

    - serviço informado: bloqueios do serviço ou sem serviço; serviço ``None``: não filtra por serviço.
    - profissional informado: do profissional ou sem profissional; sem profissional: SÓ os sem profissional.
    - período: ``data_inicio <= fim`` e (``data_fim`` nulo ou ``data_fim >= inicio``).
    """
    resultado = []
    for b in bloqueios:
        if not b.ativo:
            continue
        if tipo_servico_id is not None and b.tipo_servico_id not in (None, tipo_servico_id):
            continue
        if profissional_id:
            if b.profissional_id not in (None, profissional_id):
                continue
        elif b.profissional_id is not None:
            continue
        if b.data_inicio > fim:
            continue
        if b.data_fim is not None and b.data_fim < inicio:
            continue
        resultado.append(b)
    return resultado


def slot_bloqueado(bloqueios: Iterable[Bloqueio], dia: date, inicio: time, fim: time) -> bool:
    """``_is_slot_blocked``: algum bloqueio cobre o dia e há sobreposição de horário
    (``inicio < b.hora_fim`` e ``fim > b.hora_inicio``: encostar na borda NÃO bloqueia)."""
    for b in bloqueios:
        if b.recorrente:
            if b.dia_semana is None or b.dia_semana != dia.weekday():
                continue
            if b.data_inicio and dia < b.data_inicio:
                continue
            if b.data_fim and dia > b.data_fim:
                continue
        else:
            if dia < b.data_inicio:
                continue
            if b.data_fim and dia > b.data_fim:
                continue
        if inicio < b.hora_fim and fim > b.hora_inicio:
            return True
    return False


# ---------------------------------------------------------------------------
# Agenda do contrato
# ---------------------------------------------------------------------------

def aulas_por_semana_do_contrato(recorrencia_contrato: str, aulas_por_semana_plano: int | None) -> int:
    """Contrato SEMANAL agenda 1 aula por semana; os demais usam o plano (``or 1``)."""
    if recorrencia_contrato == "SEMANAL":
        return 1
    return aulas_por_semana_plano or 1


def fim_da_agenda_do_contrato(recorrencia_contrato: str, inicio: date, fim: date) -> date:
    """Contrato SEMANAL: no máximo 4 semanas (``inicio + 27 dias``); senão, o fim do contrato."""
    if recorrencia_contrato == "SEMANAL":
        return min(fim, inicio + timedelta(days=7 * SEMANAS_AGENDA_CONTRATO_SEMANAL - 1))
    return fim


def datas_por_dia_da_semana(inicio: date, fim: date) -> dict[int, list[date]]:
    """Todas as datas de ``inicio`` a ``fim`` (inclusive) agrupadas pelo dia da semana (0 a 6)."""
    datas: dict[int, list[date]] = {i: [] for i in range(7)}
    atual = inicio
    while atual <= fim:
        datas[atual.weekday()].append(atual)
        atual += timedelta(days=1)
    return datas


@dataclass(frozen=True)
class SelecaoHorario:
    """Um horário escolhido na tela de agenda do contrato."""

    dia_semana: int
    inicio: time
    fim: time
    profissional_id: int | None = None
    #: dia informado separadamente pelo formulário (deve bater com ``dia_semana``); ``None`` = não informado
    dia_informado: int | None = None


def validar_selecao(selecoes: Sequence[SelecaoHorario], aulas_por_semana: int) -> str | None:
    """Valida a escolha de horários do contrato; devolve a mensagem do 1º erro ou ``None``.

    Regras (na ordem do antigo): exatamente ``aulas_por_semana`` horários; sem repetir o mesmo horário;
    dia informado = dia do horário; no máximo um horário por dia da semana; professor em todos.
    """
    if len(selecoes) != aulas_por_semana:
        return f"Selecione exatamente {aulas_por_semana} horarios por semana."
    usados: set[tuple[int, time, time]] = set()
    dias: set[int] = set()
    faltando_prof = False
    for s in selecoes:
        chave = (s.dia_semana, s.inicio, s.fim)
        if chave in usados:
            return "Nao repita o mesmo horario."
        usados.add(chave)
        if s.dia_informado is not None and s.dia_informado != s.dia_semana:
            return "Dia e horario nao conferem."
        if s.dia_semana in dias:
            return "Selecione apenas um horario por dia."
        dias.add(s.dia_semana)
        if not s.profissional_id:
            faltando_prof = True
    if faltando_prof:
        return "Selecione o professor em todos os horarios."
    return None


@dataclass(frozen=True)
class SessaoExistente:
    """Sessão (``AulaSessao``) já criada para (data, início, fim) do serviço/profissional em questão."""

    ocupadas: int
    capacidade: int | None = None  # None = usa a da unidade
    aluno_ja_reservado: bool = False


ChaveSessao = tuple[date, time, time]


def slots_permitidos_do_contrato(
    janelas_do_dia: Mapping[int, Sequence[Janela]],
    datas_por_dia: Mapping[int, Sequence[date]],
    duracao_minutos: int,
    profissionais_ids: Sequence[int],
    bloqueios_por_profissional: Mapping[int, Sequence[Bloqueio]],
    sessoes_por_profissional: Mapping[int, Mapping[ChaveSessao, SessaoExistente]],
    capacidade_unidade: int | None,
) -> dict[tuple[int, time, time], list[int]]:
    """Slots oferecidos na tela de agenda do contrato: ``(dia, início, fim) -> profissionais permitidos``.

    Um profissional só é permitido num slot se, em TODAS as datas daquele dia da semana dentro da agenda,
    o horário não estiver bloqueado para ele e ainda houver vaga (``ocupadas < capacidade``; sessão que ainda
    não existe usa a capacidade da unidade). Slot sem nenhum profissional permitido não é oferecido.
    """
    slots: dict[tuple[int, time, time], list[int]] = {}
    for dia_semana, janelas in janelas_do_dia.items():
        datas = datas_por_dia.get(dia_semana) or []
        if not datas:
            continue
        for inicio, fim in gerar_slots_do_dia(datas[0], janelas, duracao_minutos):
            permitidos = []
            for prof_id in profissionais_ids:
                bloqueios = bloqueios_por_profissional.get(prof_id, ())
                sessoes = sessoes_por_profissional.get(prof_id, {})
                ok = True
                for dia in datas:
                    if slot_bloqueado(bloqueios, dia, inicio, fim):
                        ok = False
                        break
                    sessao = sessoes.get((dia, inicio, fim))
                    if sessao is not None:
                        ocupadas = sessao.ocupadas
                        capacidade = cap.capacidade_efetiva(sessao.capacidade, capacidade_unidade)
                    else:
                        ocupadas, capacidade = 0, capacidade_unidade or 0
                    if ocupadas >= (capacidade or 0):
                        ok = False
                        break
                if ok:
                    permitidos.append(prof_id)
            if permitidos:
                slots[(dia_semana, inicio, fim)] = permitidos
    return slots


@dataclass(frozen=True)
class ReservaPlanejada:
    data: date
    inicio: time
    fim: time
    profissional_id: int
    #: True se a sessão já existe (só falta a reserva); False se precisa ser criada
    sessao_existe: bool


@dataclass
class PlanoAgendaContrato:
    reservas: list[ReservaPlanejada] = field(default_factory=list)
    #: mensagens informativas; o antigo mostra as 5 primeiras e NÃO desfaz as reservas que deram certo
    conflitos: list[str] = field(default_factory=list)


def planejar_agenda_contrato(
    selecoes: Sequence[SelecaoHorario],
    inicio_contrato: date,
    fim_agenda: date,
    bloqueios_por_profissional: Mapping[int, Sequence[Bloqueio]],
    sessoes_por_profissional: Mapping[int, Mapping[ChaveSessao, SessaoExistente]],
    capacidade_unidade: int | None,
) -> PlanoAgendaContrato:
    """Quais reservas criar para o contrato e quais datas deram conflito.

    Para cada horário escolhido e cada data daquele dia da semana entre ``inicio_contrato`` e ``fim_agenda``:
    - bloqueada para o professor -> conflito ``"Bloqueio em AAAA-MM-DD HH:MM"``;
    - aluno já reservado naquela sessão -> nada a fazer (idempotente);
    - sem vaga (``ocupadas >= capacidade``) -> conflito ``"Sem vaga em AAAA-MM-DD HH:MM"``;
    - senão -> reserva planejada.
    Conflitos NÃO cancelam o resto (``# COMPORTAMENTO ANTIGO``: sucesso parcial); o chamador decide se avisa.

    # Nota: o antigo, ao reaproveitar a sessão, regravava ``profissional_id`` mas a busca já filtra pelo mesmo
    profissional, então isso nunca alterou o professor de outros alunos (o inventário se enganou).
    """
    plano = PlanoAgendaContrato()
    for s in selecoes:
        prof_id = s.profissional_id
        if not prof_id:
            continue
        bloqueios = bloqueios_por_profissional.get(prof_id, ())
        sessoes = sessoes_por_profissional.get(prof_id, {})
        atual = inicio_contrato
        while atual <= fim_agenda:
            if atual.weekday() == s.dia_semana:
                rotulo = f"{atual} {s.inicio:%H:%M}"
                if slot_bloqueado(bloqueios, atual, s.inicio, s.fim):
                    plano.conflitos.append(f"Bloqueio em {rotulo}")
                else:
                    sessao = sessoes.get((atual, s.inicio, s.fim))
                    if sessao is not None and sessao.aluno_ja_reservado:
                        pass
                    else:
                        ocupadas = sessao.ocupadas if sessao else 0
                        capacidade = cap.capacidade_efetiva(sessao.capacidade if sessao else None, capacidade_unidade)
                        if cap.pode_reservar(capacidade, ocupadas):
                            plano.reservas.append(
                                ReservaPlanejada(atual, s.inicio, s.fim, prof_id, sessao is not None)
                            )
                        else:
                            plano.conflitos.append(f"Sem vaga em {rotulo}")
            atual += timedelta(days=1)
    return plano


# ---------------------------------------------------------------------------
# Aula avulsa
# ---------------------------------------------------------------------------

def alinhar_ao_dia_da_semana(base: date, dia_semana: int) -> date:
    """Primeira data >= ``base`` que cai em ``dia_semana`` (``_align_date_to_weekday``)."""
    return base + timedelta(days=(dia_semana - base.weekday()) % 7)


def avancar_recorrencia(base: date, recorrencia: str, indice: int) -> date:
    """MENSAL: ``add_months`` (dia <= 28); senão ``+7*indice`` dias (``_advance_recorrencia_date``)."""
    if recorrencia == "MENSAL":
        return add_months(base, indice)
    return base + timedelta(days=7 * indice)


@dataclass(frozen=True)
class DataAvulsa:
    data: date
    fora_do_periodo: bool


def datas_aula_avulsa(
    inicio_pacote: date,
    dia_semana: int,
    recorrencia: str,
    quantidade: int,
    fim_pacote: date,
) -> list[DataAvulsa]:
    """As ``quantidade`` datas do pacote avulso: a primeira é a primeira ocorrência de ``dia_semana`` a partir
    do início; as demais avançam por semana (ou mês). Datas depois de ``fim_pacote`` vêm marcadas
    ``fora_do_periodo`` (o antigo avisa ``"Fora do periodo em ..."`` e não agenda)."""
    primeira = alinhar_ao_dia_da_semana(inicio_pacote, dia_semana)
    resultado = []
    for idx in range(max(quantidade, 1)):
        d = avancar_recorrencia(primeira, recorrencia, idx)
        resultado.append(DataAvulsa(d, d > fim_pacote))
    return resultado


def validar_selecao_nos_slots(
    selecoes: Sequence[SelecaoHorario],
    slots: Mapping[tuple[int, time, time], Sequence[int]],
) -> str | None:
    """Confere cada escolha contra os slots oferecidos (``slots_permitidos_do_contrato``).

    - ``"Horario invalido para o dia selecionado."``: o (dia, início, fim) não é oferecido;
    - ``"Professor invalido para o horario selecionado."``: o slot tem lista de permitidos e o professor não está nela.
    Escolhas sem professor são ignoradas aqui (``validar_selecao`` já cobra o professor).
    """
    for s in selecoes:
        if not s.profissional_id:
            continue
        chave = (s.dia_semana, s.inicio, s.fim)
        if chave not in slots:
            return "Horario invalido para o dia selecionado."
        permitidos = set(slots[chave] or ())
        if permitidos and s.profissional_id not in permitidos:
            return "Professor invalido para o horario selecionado."
    return None
