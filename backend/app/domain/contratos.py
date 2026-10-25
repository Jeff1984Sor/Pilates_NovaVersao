"""Contratos: plano de exclusão (R13) e situação de vigência (gestão de contratos).

Origem no sistema antigo (``core/views.py``):
- ``delete_view`` para ``Contrato`` (5101-5145): o que a exclusão apaga;
- ``contratos_gestao`` (5810-5890): filtros ativos/vencendo/vencidos, situação e badge, resumo;
- ``dashboard`` (570-577): "contratos vencendo em 7 dias".

MODELO NOVO: as reservas terão FK para o contrato (``contrato_id``). Por isso o plano de exclusão tem duas formas:
``plano_exclusao_por_fk`` (o que o sistema novo fará) e ``plano_exclusao_inferido`` (o que o antigo fazia, inferindo
pelo período + unidade + serviço do plano). ``vincular_reservas_aos_contratos`` aplica a mesma inferência para o ETL
preencher a FK, e ``comparar_planos`` mostra o que muda (conciliação).
"""
from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

DIAS_VENCENDO_GESTAO = 30
DIAS_VENCE_ESTA_SEMANA = 7


# ---------------------------------------------------------------------------
# Exclusão de contrato
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContratoRef:
    id: int
    aluno_id: int
    unidade_id: int
    tipo_servico_id: int | None
    inicio: date
    fim: date


@dataclass(frozen=True)
class ReservaRef:
    """Uma reserva e a sessão (aula) onde ela está."""

    id: int
    aluno_id: int
    sessao_id: int
    data_aula: date
    unidade_id: int
    tipo_servico_id: int | None
    status: str = "RESERVADA"
    contrato_id: int | None = None      # FK nova (None no modelo antigo)
    pacote_avulso_id: int | None = None  # aula avulsa não pertence a contrato


@dataclass(frozen=True)
class ContaRef:
    id: int
    contrato_id: int | None
    status: str = "ABERTO"


@dataclass
class PlanoExclusao:
    contas_receber_ids: list[int] = field(default_factory=list)
    reservas_ids: list[int] = field(default_factory=list)
    sessoes_ids: list[int] = field(default_factory=list)
    #: ids de contas JÁ PAGAS que seriam apagadas (histórico financeiro!)
    contas_pagas_ids: list[int] = field(default_factory=list)
    #: reservas apagadas que têm evolução/avaliação (o antigo apaga em cascata)
    reservas_com_historico_clinico: list[int] = field(default_factory=list)
    #: reservas apagadas que são de aula avulsa, não do contrato (só ocorre na forma inferida)
    reservas_avulsas_atingidas: list[int] = field(default_factory=list)

    @property
    def resumo(self) -> dict[str, int]:
        """``delete_summary`` da tela de confirmação do antigo: contas, reservas e aulas (sessões distintas das reservas)."""
        return {"contas_receber": len(self.contas_receber_ids), "reservas": len(self.reservas_ids), "aulas": self.aulas_das_reservas}

    aulas_das_reservas: int = 0


def exige_confirmacao(confirm_delete: str | None) -> bool:
    """O antigo só exclui com ``confirm_delete == "1"``; qualquer outra coisa cancela com
    ``"Confirme a exclusao do contrato."``."""
    return confirm_delete == "1"


MENSAGEM_CONFIRMAR_EXCLUSAO = "Confirme a exclusao do contrato."


def _montar(
    contrato: ContratoRef,
    contas: Iterable[ContaRef],
    escolhidas: list[ReservaRef],
    todas_reservas_das_sessoes: Iterable[ReservaRef],
    reservas_com_historico: Collection[int],
) -> PlanoExclusao:
    contas_do_contrato = [c for c in contas if c.contrato_id == contrato.id]
    ids_escolhidos = {r.id for r in escolhidas}
    sessoes_tocadas = {r.sessao_id for r in escolhidas}
    restantes_por_sessao: dict[int, int] = {s: 0 for s in sessoes_tocadas}
    for r in todas_reservas_das_sessoes:
        if r.sessao_id in restantes_por_sessao and r.id not in ids_escolhidos:
            restantes_por_sessao[r.sessao_id] += 1
    return PlanoExclusao(
        contas_receber_ids=sorted(c.id for c in contas_do_contrato),
        reservas_ids=sorted(ids_escolhidos),
        sessoes_ids=sorted(s for s, restantes in restantes_por_sessao.items() if restantes == 0),
        contas_pagas_ids=sorted(c.id for c in contas_do_contrato if c.status == "PAGO"),
        reservas_com_historico_clinico=sorted(i for i in ids_escolhidos if i in reservas_com_historico),
        reservas_avulsas_atingidas=sorted(r.id for r in escolhidas if r.pacote_avulso_id is not None),
        aulas_das_reservas=len(sessoes_tocadas),
    )


def reserva_cai_no_contrato_antigo(contrato: ContratoRef, reserva: ReservaRef) -> bool:
    """Inferência do antigo: mesmo aluno, data da aula dentro de ``[início, fim]`` (inclusive), mesma unidade e
    mesmo tipo de serviço do plano. NÃO olha status nem se a reserva é de aula avulsa."""
    return (
        reserva.aluno_id == contrato.aluno_id
        and contrato.inicio <= reserva.data_aula <= contrato.fim
        and reserva.unidade_id == contrato.unidade_id
        and reserva.tipo_servico_id == contrato.tipo_servico_id
    )


def plano_exclusao_inferido(
    contrato: ContratoRef,
    contas: Iterable[ContaRef],
    reservas: Iterable[ReservaRef],
    reservas_com_historico: Collection[int] = (),
) -> PlanoExclusao:
    """O que o sistema ANTIGO apagaria ao excluir o contrato (após confirmação):

    1. TODAS as contas a receber do contrato (inclusive as já PAGAS);
    2. as reservas do aluno no período/unidade/serviço do contrato (inclusive concluídas, faltas e AULAS AVULSAS), com
       as evoluções/avaliações dessas reservas em cascata;
    3. as sessões que ficarem sem nenhuma reserva (de qualquer aluno).

    ``reservas``: todas as reservas das sessões candidatas (de qualquer aluno), para decidir quais sessões esvaziam.
    # COMPORTAMENTO ANTIGO: ver docs/progresso-dominio.md (tabela de divergências) para as sugestões.
    """
    lista = list(reservas)
    escolhidas = [r for r in lista if reserva_cai_no_contrato_antigo(contrato, r)]
    return _montar(contrato, contas, escolhidas, lista, reservas_com_historico)


def plano_exclusao_por_fk(
    contrato: ContratoRef,
    contas: Iterable[ContaRef],
    reservas: Iterable[ReservaRef],
    reservas_com_historico: Collection[int] = (),
) -> PlanoExclusao:
    """O que o sistema NOVO apagaria: contas do contrato e as reservas com ``contrato_id == contrato.id`` (nunca aulas
    avulsas nem reservas de outro contrato), mais as sessões que esvaziarem. Não depende de datas."""
    lista = list(reservas)
    escolhidas = [r for r in lista if r.contrato_id == contrato.id]
    return _montar(contrato, contas, escolhidas, lista, reservas_com_historico)


@dataclass
class ComparacaoPlanos:
    so_no_inferido_reservas: list[int]
    so_na_fk_reservas: list[int]
    iguais: bool


def comparar_planos(inferido: PlanoExclusao, por_fk: PlanoExclusao) -> ComparacaoPlanos:
    """Conciliação do ETL: diferenças de reservas entre a inferência antiga e a FK nova."""
    a, b = set(inferido.reservas_ids), set(por_fk.reservas_ids)
    return ComparacaoPlanos(sorted(a - b), sorted(b - a), a == b and inferido.sessoes_ids == por_fk.sessoes_ids)


@dataclass
class VinculoReservas:
    #: reserva_id -> contrato_id (inferência inequívoca)
    vinculos: dict[int, int] = field(default_factory=dict)
    #: reserva_id -> contratos candidatos (mais de um contrato do aluno cobre a mesma aula)
    ambiguas: dict[int, list[int]] = field(default_factory=dict)
    #: reservas sem contrato que as cubra (aula avulsa, experimental, TotalPass, contrato apagado...)
    sem_contrato: list[int] = field(default_factory=list)


def vincular_reservas_aos_contratos(
    contratos: Sequence[ContratoRef],
    reservas: Iterable[ReservaRef],
    *,
    resolver_ambiguas: bool = False,
) -> VinculoReservas:
    """Preenche ``reserva.contrato_id`` na migração, com a MESMA inferência do antigo.

    - reservas de aula avulsa (``pacote_avulso_id``) nunca são vinculadas a contrato;
    - se exatamente um contrato cobre a reserva, vincula;
    - se vários cobrem (contratos sobrepostos do mesmo aluno/unidade/serviço), vai para ``ambiguas``; com
      ``resolver_ambiguas=True`` escolhe o contrato de início mais recente (empate: maior id).
    """
    resultado = VinculoReservas()
    for r in reservas:
        if r.pacote_avulso_id is not None:
            resultado.sem_contrato.append(r.id)
            continue
        candidatos = [c for c in contratos if reserva_cai_no_contrato_antigo(c, r)]
        if not candidatos:
            resultado.sem_contrato.append(r.id)
        elif len(candidatos) == 1:
            resultado.vinculos[r.id] = candidatos[0].id
        elif resolver_ambiguas:
            resultado.vinculos[r.id] = max(candidatos, key=lambda c: (c.inicio, c.id)).id
        else:
            resultado.ambiguas[r.id] = sorted(c.id for c in candidatos)
    return resultado


# ---------------------------------------------------------------------------
# Vigência (gestão de contratos)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SituacaoContrato:
    dias_restantes: int
    situacao: str
    badge: str


def situacao_do_contrato(fim: date, hoje: date) -> SituacaoContrato:
    """``dias = fim - hoje``: < 0 Vencido (danger); <= 7 Vence esta semana (danger); <= 30 Vence em breve (warning);
    senão Vigente (success). O dia do fim ainda conta como vigente (dias = 0 -> "Vence esta semana")."""
    dias = (fim - hoje).days
    if dias < 0:
        return SituacaoContrato(dias, "Vencido", "danger")
    if dias <= DIAS_VENCE_ESTA_SEMANA:
        return SituacaoContrato(dias, "Vence esta semana", "danger")
    if dias <= DIAS_VENCENDO_GESTAO:
        return SituacaoContrato(dias, "Vence em breve", "warning")
    return SituacaoContrato(dias, "Vigente", "success")


def esta_ativo(inicio: date, fim: date, hoje: date) -> bool:
    """Vigente hoje: ``inicio <= hoje <= fim``."""
    return inicio <= hoje <= fim


def esta_vencendo(fim: date, hoje: date, dias: int = DIAS_VENCENDO_GESTAO) -> bool:
    """``hoje <= fim <= hoje + dias`` (não olha o início: contrato futuro com fim próximo também entra)."""
    return hoje <= fim <= hoje + timedelta(days=dias)


def esta_vencido(fim: date, hoje: date) -> bool:
    return fim < hoje


def passa_no_filtro(filtro: str, inicio: date, fim: date, hoje: date) -> bool:
    """Filtros da tela de gestão: ``vencidos``, ``vencendo`` (30 dias), ``todos``; qualquer outro valor = ``ativos``."""
    if filtro == "vencidos":
        return esta_vencido(fim, hoje)
    if filtro == "vencendo":
        return esta_vencendo(fim, hoje)
    if filtro == "todos":
        return True
    return esta_ativo(inicio, fim, hoje)


def filtro_normalizado(filtro: str | None) -> str:
    return filtro if filtro in ("vencidos", "vencendo", "todos") else "ativos"


def resumo_gestao(periodos: Iterable[tuple[date, date]], hoje: date) -> dict[str, int]:
    """Contadores do topo da tela (independentes do filtro): ativos, vencendo (30 dias), vencidos e total."""
    lista = list(periodos)
    return {
        "ativos": sum(1 for i, f in lista if esta_ativo(i, f, hoje)),
        "vencendo": sum(1 for _, f in lista if esta_vencendo(f, hoje)),
        "vencidos": sum(1 for _, f in lista if esta_vencido(f, hoje)),
        "total": len(lista),
    }


def contratos_vencendo_no_painel(fins: Iterable[date], hoje: date, dias: int = 7) -> int:
    """Alerta do dashboard: contratos que terminam entre hoje e hoje + 7 dias."""
    return sum(1 for f in fins if esta_vencendo(f, hoje, dias))


def alertas_do_painel(contas_atrasadas: int, contratos_vencendo: int) -> list[str]:
    """Textos de alerta do dashboard antigo."""
    alertas = []
    if contas_atrasadas:
        alertas.append(f"{contas_atrasadas} faturas em atraso")
    if contratos_vencendo:
        alertas.append(f"{contratos_vencendo} contratos vencendo em 7 dias")
    return alertas


def reservas_por_sessao(reservas: Iterable[ReservaRef]) -> Mapping[int, int]:
    """Utilitário: contagem de reservas por sessão."""
    contagem: dict[int, int] = {}
    for r in reservas:
        contagem[r.sessao_id] = contagem.get(r.sessao_id, 0) + 1
    return contagem
