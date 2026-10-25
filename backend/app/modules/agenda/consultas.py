"""Consultas de leitura da agenda: grade semanal, painel operacional, aulas do aluno e opções de filtro.

NADA aqui grava nem cria aula (nem "de passagem"): o antigo criava sessões e concluía aulas dentro de GETs; agora a
geração é pedida por POST e a conclusão é do job R6 (``tarefas.py``).

Escopo do Professor (R11): as funções recebem ``profissional_id`` já resolvido pela rota. ``PROFISSIONAL_NENHUM`` (-1)
significa "usuário restrito sem profissional vinculado": a consulta volta vazia.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.domain import capacidade as cap
from app.domain import painel as dom_painel
from app.domain import status_aula
from app.domain.financeiro import hoje_de_negocio
from app.domain.painel import BlocoMinutos
from app.modules.agenda.models import (
    AulaAvulsa,
    AulaSessao,
    Avaliacao,
    Evolucao,
    Reserva,
    StatusReserva,
)
from app.modules.alunos.models import Aluno, AlunoTelefone
from app.modules.cadastros.models import (
    HorarioFuncionamento,
    ModeloEvolucao,
    Plano,
    Profissional,
    TipoServico,
    Unidade,
)
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber, StatusReceber

PROFISSIONAL_NENHUM = -1

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_LONGOS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

ROTULO_STATUS_AULA = {
    "aguardando_chegar": "Aguardando",
    "em_aula": "Em aula",
    "finalizada": "Finalizada",
    "faltou": "Faltou",
    "remarcada": "Remarcada",
}

LEGENDA_GRADE = [
    {"cor": dom_painel.COR_A_CONFIRMAR[0], "rotulo": dom_painel.COR_A_CONFIRMAR[1]},
    {"cor": dom_painel.COR_CONFIRMADA[0], "rotulo": dom_painel.COR_CONFIRMADA[1]},
    {"cor": "#16a34a", "rotulo": "Concluída"},
    {"cor": "#eab308", "rotulo": "Falta avisada"},
    {"cor": "#ef4444", "rotulo": "Falta"},
    {"cor": "#9ca3af", "rotulo": "Cancelada"},
    {"cor": dom_painel.COR_SEM_ALUNOS[0], "rotulo": dom_painel.COR_SEM_ALUNOS[1]},
]


def _hm(t: time) -> str:
    return f"{t:%H:%M}"


def _minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def _escopo_prof(profissional_id: int | None):
    """Coluna de filtro pelo profissional da aula (None = sem filtro)."""
    if profissional_id is None:
        return None
    return AulaSessao.profissional_id == (None if profissional_id == PROFISSIONAL_NENHUM else profissional_id)


# --------------------------------------------------------------------------------------------------------- opções
def opcoes(db: Session, *, profissional_id: int | None = None) -> dict[str, Any]:
    """Listas para os filtros e formulários da agenda. Usuário restrito (Professor) só enxerga a si mesmo."""
    profs = select(Profissional).where(Profissional.ativo).order_by(Profissional.nome)
    if profissional_id is not None:
        profs = profs.where(Profissional.id == profissional_id)
    return {
        "unidades": [
            {"id": u.id, "nome": u.nome, "capacidade": u.capacidade, "duracao_aula_minutos": u.duracao_aula_minutos}
            for u in db.scalars(select(Unidade).where(Unidade.ativo).order_by(Unidade.nome))
        ],
        "profissionais": [{"id": p.id, "nome": p.nome, "iniciais": dom_painel.iniciais(p.nome)} for p in db.scalars(profs)],
        "servicos": [{"id": s.id, "nome": s.nome} for s in db.scalars(select(TipoServico).where(TipoServico.ativo).order_by(TipoServico.nome))],
        "planos_avulsos": [
            {"id": p.id, "nome": p.nome, "valor": str(p.valor), "tipo_servico_id": p.tipo_servico_id, "recorrencia": p.recorrencia.value}
            for p in db.scalars(select(Plano).where(Plano.avulso, Plano.ativo).order_by(Plano.nome))
        ],
        "modelos_evolucao": [
            {"id": m.id, "titulo": m.titulo, "texto": m.texto}
            for m in db.scalars(select(ModeloEvolucao).where(ModeloEvolucao.ativo).order_by(ModeloEvolucao.titulo))
        ],
    }


# ---------------------------------------------------------------------------------------------------------- sessões
def _linha_sessao(s: AulaSessao, unidade: Unidade, servico: TipoServico, prof: Profissional | None, reservas: list[Reserva]) -> dict:
    capacidade = cap.capacidade_efetiva(s.capacidade, unidade.capacidade)
    return {
        "id": s.id,
        "unidade_id": s.unidade_id,
        "unidade": unidade.nome,
        "tipo_servico_id": s.tipo_servico_id,
        "servico": servico.nome,
        "profissional_id": s.profissional_id,
        "profissional": prof.nome if prof else None,
        "data": s.data.isoformat(),
        "hora_inicio": _hm(s.hora_inicio),
        "hora_fim": _hm(s.hora_fim),
        "capacidade": s.capacidade,
        "capacidade_efetiva": capacidade,
        "reservas_ativas": s.reservas_ativas,
        "vagas_livres": cap.vagas_livres(capacidade, s.reservas_ativas),
        "total_reservas": len(reservas),
    }


def listar_sessoes(
    db: Session,
    *,
    de: date,
    ate: date,
    unidade_id: int | None = None,
    profissional_id: int | None = None,
    tipo_servico_id: int | None = None,
    limite: int = 500,
) -> list[dict]:
    q = (
        select(AulaSessao, Unidade, TipoServico, Profissional)
        .join(Unidade, Unidade.id == AulaSessao.unidade_id)
        .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
        .where(AulaSessao.data.between(de, ate))
        .order_by(AulaSessao.data, AulaSessao.hora_inicio, AulaSessao.id)
        .limit(limite)
        .execution_options(populate_existing=True)  # reservas_ativas muda por UPDATE direto: não ler do cache da sessão
    )
    if unidade_id:
        q = q.where(AulaSessao.unidade_id == unidade_id)
    if tipo_servico_id:
        q = q.where(AulaSessao.tipo_servico_id == tipo_servico_id)
    f = _escopo_prof(profissional_id)
    if f is not None:
        q = q.where(f)
    linhas = db.execute(q).all()
    ids = [s.id for s, *_ in linhas]
    contagem: dict[int, list[Reserva]] = defaultdict(list)
    if ids:
        for r in db.scalars(select(Reserva).where(Reserva.aula_sessao_id.in_(ids))):
            contagem[r.aula_sessao_id].append(r)
    return [_linha_sessao(s, u, sv, p, contagem[s.id]) for s, u, sv, p in linhas]


def detalhe_sessao(db: Session, sessao_id: int, *, profissional_id: int | None = None) -> dict | None:
    q = (
        select(AulaSessao, Unidade, TipoServico, Profissional)
        .join(Unidade, Unidade.id == AulaSessao.unidade_id)
        .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
        .where(AulaSessao.id == sessao_id)
        .execution_options(populate_existing=True)
    )
    f = _escopo_prof(profissional_id)
    if f is not None:
        q = q.where(f)
    linha = db.execute(q).first()
    if not linha:
        return None
    s, u, sv, p = linha
    rs = db.execute(
        select(Reserva, Aluno).join(Aluno, Aluno.id == Reserva.aluno_id).where(Reserva.aula_sessao_id == s.id).order_by(Aluno.nome)
    ).all()
    d = _linha_sessao(s, u, sv, p, [r for r, _ in rs])
    d["reservas"] = [
        {"id": r.id, "aluno_id": a.id, "aluno": a.nome, "status": StatusReserva(r.status).value, "confirmada_em": r.confirmada_em}
        for r, a in rs
    ]
    return d


# ------------------------------------------------------------------------------------------------------------ grade
def montar_grade(
    db: Session,
    *,
    referencia: date | None,
    hoje: date,
    profissional_id: int | None = None,
    unidade_id: int | None = None,
) -> dict[str, Any]:
    """Grade da semana (seg a sáb): um bloco por reserva (ou "Sem alunos" por aula vazia), cor pelo status,
    ocupação ``n/m`` e posição em colunas quando horários se sobrepõem. Sem ``referencia`` e hoje sendo sáb/dom,
    mostra a próxima semana (# COMPORTAMENTO ANTIGO mantido)."""
    inicio, fim = dom_painel.semana_da_grade(referencia, hoje)
    q = (
        select(AulaSessao, Unidade, TipoServico, Profissional)
        .join(Unidade, Unidade.id == AulaSessao.unidade_id)
        .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
        .where(AulaSessao.data.between(inicio, fim))
        .order_by(AulaSessao.data, AulaSessao.hora_inicio)
    )
    if unidade_id:
        q = q.where(AulaSessao.unidade_id == unidade_id)
    f = _escopo_prof(profissional_id)
    if f is not None:
        q = q.where(f)
    linhas = db.execute(q).all()
    ids = [s.id for s, *_ in linhas]
    reservas: dict[int, list[tuple[Reserva, Aluno]]] = defaultdict(list)
    if ids:
        for r, a in db.execute(
            select(Reserva, Aluno).join(Aluno, Aluno.id == Reserva.aluno_id).where(Reserva.aula_sessao_id.in_(ids)).order_by(Aluno.nome)
        ):
            reservas[r.aula_sessao_id].append((r, a))

    por_dia: dict[date, list[BlocoMinutos]] = defaultdict(list)
    for s, u, sv, prof in linhas:
        capacidade = cap.capacidade_efetiva(s.capacidade, u.capacidade)
        rs = reservas.get(s.id, [])
        ativos = sum(1 for r, _ in rs if StatusReserva(r.status) != StatusReserva.CANCELADA)
        ocupacao = f"{ativos}/{capacidade}" if capacidade else None
        base = {
            "sessao_id": s.id,
            "hora": _hm(s.hora_inicio),
            "hora_fim": _hm(s.hora_fim),
            "servico": sv.nome,
            "profissional_id": s.profissional_id,
            "profissional": prof.nome if prof else None,
            "unidade": u.nome,
            "ocupacao": ocupacao,
            "capacidade": capacidade,
            "ocupadas": ativos,
        }
        ini, fim_min = _minutos(s.hora_inicio), _minutos(s.hora_fim)
        if not rs:
            cor, rotulo = dom_painel.COR_SEM_ALUNOS
            por_dia[s.data].append(
                BlocoMinutos(ini, fim_min, dados={**base, "reserva_id": None, "aluno_id": None, "aluno": None, "status": None, "cor": cor, "situacao": rotulo})
            )
        for r, a in rs:
            cor, rotulo = dom_painel.cor_da_reserva(StatusReserva(r.status).value, r.confirmada_em is not None)
            por_dia[s.data].append(
                BlocoMinutos(
                    ini,
                    fim_min,
                    dados={**base, "reserva_id": r.id, "aluno_id": a.id, "aluno": a.nome, "status": StatusReserva(r.status).value, "cor": cor, "situacao": rotulo},
                )
            )
    dias = []
    for i in range(6):
        dia = inicio + timedelta(days=i)
        blocos = dom_painel.distribuir_colunas(por_dia.get(dia, []))
        dias.append(
            {
                "data": dia.isoformat(),
                "rotulo": DIAS_CURTOS[dia.weekday()],
                "numero": dia.day,
                "hoje": dia == hoje,
                "blocos": [
                    {**b.dados, "inicio_min": b.inicio, "fim_min": max(b.fim, b.inicio + 20), "coluna": b.coluna, "colunas": b.colunas}  # type: ignore[arg-type]
                    for b in blocos
                ],
            }
        )
    return {
        "semana_inicio": inicio.isoformat(),
        "semana_fim": fim.isoformat(),
        "rotulo": f"{MESES[inicio.month - 1]} {inicio.year}",
        "anterior": (inicio - timedelta(days=7)).isoformat(),
        "proxima": (inicio + timedelta(days=7)).isoformat(),
        "hoje": hoje.isoformat(),
        "grade_inicio_min": 6 * 60,
        "grade_fim_min": 22 * 60,
        "legenda": LEGENDA_GRADE,
        "dias": dias,
    }


# ---------------------------------------------------------------------------------------------------------- painel
@dataclass
class _Contexto:
    planos: dict[int, tuple[int, str]]  # reserva_id -> (plano_id, nome)
    servicos: dict[tuple[int, int, time, time], list[str]]
    telefones: dict[int, str]
    evolucoes: dict[int, tuple[str, datetime]]
    cobranca: set[int]
    sem_aceite: set[int]


def _contexto_dos_itens(
    db: Session,
    linhas: list[tuple[Reserva, AulaSessao, Aluno]],
    *,
    com_cobranca: bool,
) -> _Contexto:
    reserva_ids = [r.id for r, _, _ in linhas]
    aluno_ids = list({a.id for _, _, a in linhas})
    planos: dict[int, tuple[int, str]] = {}
    if reserva_ids:
        # 1) contrato explícito da reserva; 2) pacote avulso; 3) contrato do aluno que cobre a data (como o antigo)
        nomes = {p.id: p.nome for p in db.scalars(select(Plano))}
        contratos = {c.id: c for c in db.scalars(select(Contrato).where(Contrato.aluno_id.in_(aluno_ids)))}
        avulsas = {x.id: x for x in db.scalars(select(AulaAvulsa).where(AulaAvulsa.aluno_id.in_(aluno_ids)))}
        for r, s, a in linhas:
            plano_id = None
            if r.contrato_id and r.contrato_id in contratos:
                plano_id = contratos[r.contrato_id].plano_id
            elif r.aula_avulsa_id and r.aula_avulsa_id in avulsas:
                plano_id = avulsas[r.aula_avulsa_id].plano_id
            else:
                cobrindo = [
                    c for c in contratos.values() if c.aluno_id == a.id and c.data_inicio <= s.data <= c.data_fim
                ]
                if cobrindo:
                    plano_id = sorted(cobrindo, key=lambda c: (c.data_fim, c.id), reverse=True)[0].plano_id
            if plano_id:
                planos[r.id] = (plano_id, nomes.get(plano_id, ""))
    # serviços oferecidos no horário (janelas de funcionamento que cruzam a aula)
    unidades = {s.unidade_id for _, s, _ in linhas}
    janelas: dict[int, list[HorarioFuncionamento]] = defaultdict(list)
    if unidades:
        for h in db.scalars(select(HorarioFuncionamento).where(HorarioFuncionamento.unidade_id.in_(unidades), HorarioFuncionamento.ativo)):
            janelas[h.unidade_id].append(h)
    servicos: dict[tuple[int, int, time, time], list[str]] = {}
    for _, s, _ in linhas:
        chave = (s.unidade_id, s.data.toordinal(), s.hora_inicio, s.hora_fim)
        if chave in servicos:
            continue
        nomes_serv: list[str] = []
        for h in janelas.get(s.unidade_id, []):
            if h.dia_semana == s.data.weekday() and h.hora_inicio <= s.hora_fim and h.hora_fim >= s.hora_inicio:
                for t in h.tipos_servico:
                    if t.nome not in nomes_serv:
                        nomes_serv.append(t.nome)
        servicos[chave] = nomes_serv
    telefones: dict[int, str] = {}
    if aluno_ids:
        for t in db.scalars(select(AlunoTelefone).where(AlunoTelefone.aluno_id.in_(aluno_ids)).order_by(AlunoTelefone.ordem)):
            telefones.setdefault(t.aluno_id, t.numero)
    evolucoes: dict[int, tuple[str, datetime]] = {}
    if reserva_ids:
        for e in db.scalars(select(Evolucao).where(Evolucao.reserva_id.in_(reserva_ids)).order_by(Evolucao.criado_em, Evolucao.id)):
            evolucoes[e.reserva_id] = (e.texto, e.criado_em)
    cobranca: set[int] = set()
    if com_cobranca and aluno_ids:
        cobranca = set(
            db.scalars(select(ContaReceber.aluno_id).where(ContaReceber.aluno_id.in_(aluno_ids), ContaReceber.status == StatusReceber.ABERTO))
        )
    sem_aceite = {a.id for _, _, a in linhas if a.termo_aceite_em is None}
    return _Contexto(planos, servicos, telefones, evolucoes, cobranca, sem_aceite)


def _item_painel(r: Reserva, s: AulaSessao, a: Aluno, u: Unidade, sv: TipoServico, prof: Profissional | None, ctx: _Contexto, agora: datetime, com_cobranca: bool) -> dict:
    inicio = status_aula.momento_da_sessao(s.data, s.hora_inicio)
    fim = status_aula.momento_da_sessao(s.data, s.hora_fim)
    status = StatusReserva(r.status).value
    st_aula = status_aula.status_exibido(status, inicio, fim, agora)
    nomes = ctx.servicos.get((s.unidade_id, s.data.toordinal(), s.hora_inicio, s.hora_fim)) or [sv.nome]
    plano = ctx.planos.get(r.id)
    evo = ctx.evolucoes.get(r.id)
    return {
        "id": r.id,
        "aula_sessao_id": s.id,
        "data": s.data.isoformat(),
        "hora_inicio": _hm(s.hora_inicio),
        "hora_fim": _hm(s.hora_fim),
        "dt_inicio": inicio.isoformat(),
        "dt_fim": fim.isoformat(),
        "unidade_id": s.unidade_id,
        "unidade": u.nome,
        "profissional": {"id": prof.id, "nome": prof.nome} if prof else None,
        "aluno": {
            "id": a.id,
            "nome": a.nome,
            "iniciais": dom_painel.iniciais(a.nome),
            "telefone": ctx.telefones.get(a.id),
        },
        "plano": {"id": plano[0], "descricao": plano[1]} if plano else {"id": None, "descricao": None},
        "servico": sv.nome,
        "servicos": nomes,
        "status": status,
        "status_aula": st_aula,
        "rotulo_status": ROTULO_STATUS_AULA.get(st_aula, st_aula),
        "confirmacao": r.confirmada_em is not None,
        "confirmada_em": r.confirmada_em.isoformat() if r.confirmada_em else None,
        "reposicao_ate": r.reposicao_ate.isoformat() if r.reposicao_ate else None,
        "flags": {
            "tem_preliminares": a.id not in ctx.sem_aceite,
            # cobrança só para quem pode ver financeiro: para os demais o campo nem é calculado (None)
            "cobranca_pendente": (a.id in ctx.cobranca) if com_cobranca else None,
        },
        "ultima_evolucao": {"texto": evo[0], "criado_em": evo[1].isoformat()} if evo else {"texto": None, "criado_em": None},
        # WhatsApp: o envio é feito pelo módulo de comunicação (rotas /whatsapp/...); a tela só mostra o botão a quem
        # tem a permissão `whatsapp.enviar`. Nada é enviado por aqui.
        "whatsapp": {"disponivel": True, "motivo": ""},
    }


def _base_itens(db: Session):
    return (
        select(Reserva, AulaSessao, Aluno, Unidade, TipoServico, Profissional)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .join(Aluno, Aluno.id == Reserva.aluno_id)
        .join(Unidade, Unidade.id == AulaSessao.unidade_id)
        .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
    )


def _montar_itens(db: Session, linhas, agora: datetime, com_cobranca: bool) -> list[dict]:
    ctx = _contexto_dos_itens(db, [(r, s, a) for r, s, a, *_ in linhas], com_cobranca=com_cobranca)
    return [_item_painel(r, s, a, u, sv, p, ctx, agora, com_cobranca) for r, s, a, u, sv, p in linhas]


def item_da_reserva(db: Session, reserva_id: int, *, agora: datetime, com_cobranca: bool, profissional_id: int | None = None) -> dict | None:
    q = _base_itens(db).where(Reserva.id == reserva_id)
    f = _escopo_prof(profissional_id)
    if f is not None:
        q = q.where(f)
    linhas = db.execute(q).all()
    itens = _montar_itens(db, linhas, agora, com_cobranca)
    return itens[0] if itens else None


def montar_painel(
    db: Session,
    *,
    alvo: date | None,
    periodo: str | None,
    agora: datetime,
    com_cobranca: bool,
    unidade_id: int | None = None,
    profissional_id: int | None = None,
    status_aula_filtro: str | None = None,
    busca: str | None = None,
) -> dict[str, Any]:
    """Painel operacional agrupado por dia > horário > profissional > alunos. O status exibido (R5) vem do domínio."""
    hoje = hoje_de_negocio(agora)
    inicio, fim = dom_painel.periodo_do_painel(alvo, periodo, hoje)
    q = _base_itens(db).where(AulaSessao.data.between(inicio, fim))
    if unidade_id:
        q = q.where(AulaSessao.unidade_id == unidade_id)
    f = _escopo_prof(profissional_id)
    if f is not None:
        q = q.where(f)
    termo = (busca or "").strip()
    if termo:
        digitos = "".join(c for c in termo if c.isdigit())
        condicoes = [Aluno.nome.contains(termo, autoescape=True)]
        if digitos:
            condicoes.append(Aluno.cpf.contains(digitos, autoescape=True))
            condicoes.append(exists().where(AlunoTelefone.aluno_id == Aluno.id, AlunoTelefone.numero.contains(digitos, autoescape=True)))
        q = q.where(or_(*condicoes))
    q = q.order_by(AulaSessao.data, AulaSessao.hora_inicio, Aluno.nome)
    itens = _montar_itens(db, db.execute(q).all(), agora, com_cobranca)
    if status_aula_filtro:
        itens = [i for i in itens if i["status_aula"] == status_aula_filtro]

    por_data: dict[str, dict[tuple[str, str], dict[str, list[dict]]]] = {}
    for i in itens:
        horario = (i["hora_inicio"], i["hora_fim"])
        chave_prof = i["profissional"]["nome"] if i["profissional"] else "Sem profissional"
        por_data.setdefault(i["data"], {}).setdefault(horario, {}).setdefault(chave_prof, []).append(i)
    dias = []
    for data_iso in sorted(por_data):
        d = date.fromisoformat(data_iso)
        horarios = []
        for (h_ini, h_fim) in sorted(por_data[data_iso]):
            profs = por_data[data_iso][(h_ini, h_fim)]
            grupos = []
            for idx, nome in enumerate(sorted(profs, key=str.casefold)):
                cartoes = profs[nome]
                grupos.append(
                    {
                        "profissional_id": cartoes[0]["profissional"]["id"] if cartoes[0]["profissional"] else None,
                        "nome": nome,
                        "iniciais": dom_painel.iniciais(nome) or "?",
                        "cor_indice": idx % 6,
                        "total": len(cartoes),
                        "cartoes": cartoes,
                    }
                )
            horarios.append({"hora_inicio": h_ini, "hora_fim": h_fim, "total": sum(g["total"] for g in grupos), "profissionais": grupos})
        dias.append({"data": data_iso, "rotulo": f"{DIAS_CURTOS[d.weekday()]}, {d:%d/%m}", "total": sum(h["total"] for h in horarios), "horarios": horarios})
    return {
        "data_inicio": inicio.isoformat(),
        "data_fim": fim.isoformat(),
        "periodo": periodo if periodo in dom_painel.PERIODOS else "hoje",
        "total": len(itens),
        "pode_ver_cobranca": com_cobranca,
        "dias": dias,
    }


# ---------------------------------------------------------------------------------------------------- gaveta/ficha
def aluno_visivel(db: Session, aluno_id: int, profissional_id: int | None) -> bool:
    """Professor (R11) só enxerga aluno que tenha reserva em aula dele. ``profissional_id=None`` = sem restrição."""
    if db.get(Aluno, aluno_id) is None:
        return False
    if profissional_id is None:
        return True
    f = _escopo_prof(profissional_id)
    return bool(
        db.scalar(
            select(Reserva.id).join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id).where(Reserva.aluno_id == aluno_id, f).limit(1)
        )
    )


def reservas_do_aluno(
    db: Session,
    aluno_id: int,
    *,
    agora: datetime,
    profissional_id: int | None = None,
    status: str | None = None,
    futuras: bool | None = None,
    limite: int = 200,
) -> list[dict]:
    """Aulas do aluno (aba "Aulas" da ficha), da mais recente para a mais antiga. Professor: só as aulas dele."""
    hoje = hoje_de_negocio(agora)
    q = _base_itens(db).where(Reserva.aluno_id == aluno_id)
    f = _escopo_prof(profissional_id)
    if f is not None:
        q = q.where(f)
    if status:
        q = q.where(Reserva.status == StatusReserva(status))
    if futuras is True:
        q = q.where(AulaSessao.data >= hoje)
    elif futuras is False:
        q = q.where(AulaSessao.data < hoje)
    q = q.order_by(AulaSessao.data.desc(), AulaSessao.hora_inicio.desc()).limit(limite)
    linhas = db.execute(q).all()
    itens = _montar_itens(db, linhas, agora, com_cobranca=False)
    ids = [i["id"] for i in itens]
    evo = dict(db.execute(select(Evolucao.reserva_id, func.count()).where(Evolucao.reserva_id.in_(ids)).group_by(Evolucao.reserva_id)).all()) if ids else {}
    ava = dict(db.execute(select(Avaliacao.reserva_id, func.count()).where(Avaliacao.reserva_id.in_(ids)).group_by(Avaliacao.reserva_id)).all()) if ids else {}
    por_id = {r.id: r for r, *_ in linhas}
    for i in itens:
        r = por_id[i["id"]]
        i["tipo"] = "avulsa" if r.aula_avulsa_id else "avaliativa" if r.aula_avaliativa_id else "contrato" if r.contrato_id else "regular"
        i["contrato_id"] = r.contrato_id
        i["aula_avulsa_id"] = r.aula_avulsa_id
        i["aula_avaliativa_id"] = r.aula_avaliativa_id
        i["evolucoes"] = evo.get(i["id"], 0)
        i["avaliacoes"] = ava.get(i["id"], 0)
        i.pop("whatsapp", None)
    return itens


def cobranca_do_aluno(db: Session, aluno_id: int, agora: datetime, limite: int = 50) -> list[dict]:
    """Cobranças do aluno para a aba Cobrança da gaveta (só quem tem permissão financeira chama). ``ATRASADO`` é derivado."""
    from app.domain.financeiro import status_exibido_receber

    hoje = hoje_de_negocio(agora)
    contas = db.scalars(
        select(ContaReceber).where(ContaReceber.aluno_id == aluno_id).order_by(ContaReceber.vencimento.desc(), ContaReceber.id.desc()).limit(limite)
    )
    return [
        {
            "id": c.id,
            "descricao": c.descricao,
            "competencia": c.competencia,
            "vencimento": c.vencimento.isoformat(),
            "pagamento": c.pagamento.isoformat() if c.pagamento else None,
            "status": status_exibido_receber(StatusReceber(c.status).value, c.vencimento, hoje),
            "valor": str(c.valor),
            "contrato_id": c.contrato_id,
            "reserva_id": c.reserva_id,
        }
        for c in contas
    ]


def historico_do_aluno(db: Session, aluno_id: int, agora: datetime, limite: int = 20, profissional_id: int | None = None) -> list[dict]:
    itens = reservas_do_aluno(db, aluno_id, agora=agora, profissional_id=profissional_id, limite=limite)
    return [
        {
            "id": i["id"],
            "data": i["data"],
            "hora_inicio": i["hora_inicio"],
            "hora_fim": i["hora_fim"],
            "unidade": i["unidade"],
            "profissional": i["profissional"]["nome"] if i["profissional"] else None,
            "servico": i["servico"],
            "status": i["status"],
            "status_aula": i["status_aula"],
            "rotulo_status": i["rotulo_status"],
        }
        for i in itens
    ]


# ----------------------------------------------------------------------------- horários para remarcar (sem criar)
def horarios_para_remarcar(db: Session, reserva_id: int, de: date, ate: date) -> list[dict]:
    """Opções de remarcação da reserva dentro de ``de``..``ate``: aulas já existentes (mesma unidade e serviço) com vaga
    e horários de funcionamento ainda sem aula. SÓ LÊ — o antigo criava as aulas dentro deste GET; agora a aula nasce
    quando o usuário confirma a remarcação."""
    from app.domain import agenda as dom_agenda
    from app.modules.agenda import servico as srv

    r = db.get(Reserva, reserva_id)
    if r is None:
        return []
    atual = db.get(AulaSessao, r.aula_sessao_id)
    if atual is None or ate < de:
        return []
    ate = min(ate, de + timedelta(days=120))
    unidade = db.get(Unidade, atual.unidade_id)
    existentes = db.scalars(
        select(AulaSessao).where(
            AulaSessao.unidade_id == atual.unidade_id,
            AulaSessao.tipo_servico_id == atual.tipo_servico_id,
            AulaSessao.data.between(de, ate),
        ).order_by(AulaSessao.data, AulaSessao.hora_inicio).execution_options(populate_existing=True)
    ).all()
    nomes = {p.id: p.nome for p in db.scalars(select(Profissional))}
    opcoes: list[dict] = []
    chaves_existentes = set()
    bloqueios = srv.carregar_bloqueios(db, atual.unidade_id)
    for s in existentes:
        chaves_existentes.add((s.data, s.hora_inicio))
        capacidade = cap.capacidade_efetiva(s.capacidade, unidade.capacidade)
        eh_atual = s.id == atual.id
        if not cap.slot_deve_ser_listado(capacidade, s.reservas_ativas, eh_atual) or eh_atual:
            continue
        aplicaveis = dom_agenda.bloqueios_aplicaveis(bloqueios, atual.tipo_servico_id, s.profissional_id, de, ate)
        if dom_agenda.slot_bloqueado(aplicaveis, s.data, s.hora_inicio, s.hora_fim):
            continue
        opcoes.append(
            {
                "sessao_id": s.id,
                "data": s.data.isoformat(),
                "hora_inicio": _hm(s.hora_inicio),
                "hora_fim": _hm(s.hora_fim),
                "profissional_id": s.profissional_id,
                "profissional": nomes.get(s.profissional_id),
                "vagas": cap.vagas_livres(capacidade, s.reservas_ativas),
                "rotulo": cap.rotulo_slot(s.hora_inicio, s.hora_fim, nomes.get(s.profissional_id), capacidade, s.reservas_ativas),
            }
        )
    janelas = dom_agenda.janelas_por_dia(srv.carregar_janelas(db, atual.unidade_id), atual.tipo_servico_id)
    duracao = dom_agenda.duracao_da_unidade(unidade.duracao_aula_minutos)
    dia = de
    sem_prof = dom_agenda.bloqueios_aplicaveis(bloqueios, atual.tipo_servico_id, None, de, ate)
    while dia <= ate:
        for ini, fim in dom_agenda.gerar_slots_do_dia(dia, janelas.get(dia.weekday(), ()), duracao):
            if (dia, ini) in chaves_existentes or dom_agenda.slot_bloqueado(sem_prof, dia, ini, fim):
                continue
            capacidade = unidade.capacidade
            if capacidade <= 0:
                continue
            opcoes.append(
                {
                    "sessao_id": None,
                    "data": dia.isoformat(),
                    "hora_inicio": _hm(ini),
                    "hora_fim": _hm(fim),
                    "profissional_id": atual.profissional_id,
                    "profissional": nomes.get(atual.profissional_id),
                    "vagas": capacidade,
                    "rotulo": cap.rotulo_slot(ini, fim, nomes.get(atual.profissional_id), capacidade, 0),
                }
            )
        dia += timedelta(days=1)
    opcoes.sort(key=lambda o: (o["data"], o["hora_inicio"], o["profissional"] or ""))
    return opcoes
