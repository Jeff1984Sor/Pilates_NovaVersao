"""Pedidos de reposição (decisão do Jefferson, 25/10/2026): o aluno só PEDE; a gerência (perfil Full, permissão
``reposicoes``) aprova escolhendo uma aula com vaga real, ou recusa com motivo.

- Aluno: ``listar_reposicoes`` (aulas desmarcadas com prazo + situação do pedido) e ``pedir_reposicao`` (idempotente: pedir de
  novo enquanto PENDENTE só atualiza a preferência).
- Gerência: ``listar_pedidos``, ``opcoes_do_pedido`` (aulas com vaga do mesmo serviço e unidade), ``aprovar`` e ``recusar``.

A aprovação usa ``agenda.servico.remarcar_reserva`` (capacidade transacional, prazo da reposição, consome o prazo); aqui só se
escolhe a aula e se confere bloqueio, vaga e prazo antes. Nada aqui faz ``commit``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models import Usuario
from app.domain import agenda as dom_agenda
from app.domain import capacidade as cap
from app.domain import status_aula
from app.domain.financeiro import hoje_de_negocio
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno
from app.modules.app_aluno import servico as base
from app.modules.app_aluno.models import ReposicaoPedido, StatusPedido
from app.modules.app_aluno.servico import Conflito, Invalido, NaoEncontrado

MAX_PREFERENCIA = 300
MAX_MOTIVO = 300
DIAS_EXTRA_FORA_DO_PRAZO = 90  # até onde a gerência enxerga aulas quando ignora o prazo

_CONTROLE = re.compile(r"[\x00-\x1f\x7f<>]")


def limpar_texto(v: str | None, limite: int) -> str:
    """Texto livre do aluno/gerência: sem caracteres de controle nem `<` `>`, espaços normalizados, no máximo ``limite``."""
    return re.sub(r"\s+", " ", _CONTROLE.sub(" ", v or "")).strip()[:limite]


# ------------------------------------------------------------------------------------------------ candidatas (vaga real)
def _candidatas(db: Session, aluno_id: int, antiga: AulaSessao, hoje: date, momento: datetime, ate: date) -> list[AulaSessao]:
    """Aulas EXISTENTES do mesmo serviço e unidade, de hoje até ``ate``, com vaga, fora de bloqueio e onde o aluno ainda não
    tem reserva. Só lê."""
    local = status_aula.para_fuso_negocio(momento)
    ja_tem = set(db.scalars(select(Reserva.aula_sessao_id).where(Reserva.aluno_id == aluno_id)))
    sessoes = db.scalars(
        select(AulaSessao)
        .where(
            AulaSessao.unidade_id == antiga.unidade_id,
            AulaSessao.tipo_servico_id == antiga.tipo_servico_id,
            AulaSessao.data >= hoje,
            AulaSessao.data <= ate,
        )
        .order_by(AulaSessao.data, AulaSessao.hora_inicio, AulaSessao.id)
        .execution_options(populate_existing=True)  # reservas_ativas muda por UPDATE direto
    ).all()
    bloqueios = agenda.carregar_bloqueios(db, antiga.unidade_id)
    out = []
    for s in sessoes:
        if s.id in ja_tem:
            continue
        if s.data == hoje and s.hora_inicio <= local.time():
            continue
        # aula sem profissional só se a original também não tinha (a remarcação mantém/define o profissional)
        if s.profissional_id is None and antiga.profissional_id is not None:
            continue
        if cap.vagas_livres(agenda.capacidade_da_sessao(db, s), s.reservas_ativas) <= 0:
            continue
        aplic = dom_agenda.bloqueios_aplicaveis(bloqueios, s.tipo_servico_id, s.profissional_id, s.data, s.data)
        if dom_agenda.slot_bloqueado(aplic, s.data, s.hora_inicio, s.hora_fim):
            continue
        out.append(s)
    return out


def _opcao(db: Session, s: AulaSessao) -> dict:
    return {
        "aula_id": s.id,
        "data": s.data,
        "hora_inicio": s.hora_inicio,
        "hora_fim": s.hora_fim,
        "profissional": base._nome_prof(db, s.profissional_id),
        "vagas": cap.vagas_livres(agenda.capacidade_da_sessao(db, s), s.reservas_ativas),
    }


# ----------------------------------------------------------------------------------------------------------- aluno
def _pedido_dict(p: ReposicaoPedido) -> dict:
    return {
        "status": StatusPedido(p.status).value,
        "preferencia": p.preferencia,
        "pedido_em": p.criado_em,
        "aprovado_data": p.aprovado_data,
        "aprovado_hora": p.aprovado_hora,
        "motivo_recusa": p.motivo_recusa,
    }


def _item_aluno(db: Session, r: Reserva, p: ReposicaoPedido | None, hoje: date) -> dict:
    s = db.get(AulaSessao, r.aula_sessao_id)
    cancelada = StatusReserva(r.status) == StatusReserva.CANCELADA
    ate = r.reposicao_ate if cancelada and r.reposicao_ate else ((p.data_origem if p else s.data) + timedelta(days=30))
    dentro = cancelada and ate >= hoje
    pendente = p is not None and StatusPedido(p.status) == StatusPedido.PENDENTE
    return {
        "id": r.id,
        "data": p.data_origem if p else s.data,
        "hora_inicio": p.hora_origem if p else s.hora_inicio,
        "servico": base._nome_servico(db, s.tipo_servico_id),
        "profissional": base._nome_prof(db, s.profissional_id) if cancelada else None,
        "desmarcada_em": r.desmarcada_em,
        "reposicao_ate": ate,
        "dias_restantes": max((ate - hoje).days, 0),
        "dentro_do_prazo": dentro,
        "pode_pedir": dentro and (p is None or pendente),
        "pedido": _pedido_dict(p) if p else None,
    }


def listar_reposicoes(db: Session, aluno: Aluno, *, agora: datetime | None = None) -> list[dict]:
    """Aulas desmarcadas com prazo (e, por mais 30 dias, as vencidas) e a situação do pedido de cada uma. Pedidos aprovados
    ou recusados continuam visíveis por 60 dias para o aluno saber a resposta."""
    momento = base._agora(agora)
    hoje = hoje_de_negocio(momento)
    corte = momento - timedelta(days=60)
    pedidos = db.scalars(
        select(ReposicaoPedido)
        .where(
            ReposicaoPedido.aluno_id == aluno.id,
            ReposicaoPedido.status.in_([StatusPedido.PENDENTE, StatusPedido.APROVADO, StatusPedido.RECUSADO]),
            (ReposicaoPedido.status == StatusPedido.PENDENTE) | (ReposicaoPedido.criado_em >= corte),
        )
        .order_by(ReposicaoPedido.id.desc())
    ).all()
    itens: dict[int, dict] = {}
    for p in pedidos:  # do mais novo para o mais velho: um item por reserva
        if p.reserva_origem_id in itens:
            continue
        r = db.get(Reserva, p.reserva_origem_id)
        if r is None:
            continue
        # recusado e a aula foi desmarcada DE NOVO depois: o pedido velho não vale mais para a aula nova
        if (
            StatusPedido(p.status) != StatusPedido.PENDENTE
            and StatusReserva(r.status) == StatusReserva.CANCELADA
            and p.decidido_em is not None
            and r.desmarcada_em is not None
            and r.desmarcada_em > p.decidido_em
        ):
            continue
        itens[r.id] = _item_aluno(db, r, p, hoje)
    canceladas = db.scalars(
        select(Reserva).where(
            Reserva.aluno_id == aluno.id,
            Reserva.status == StatusReserva.CANCELADA,
            Reserva.reposicao_ate.is_not(None),
            Reserva.reposicao_ate >= hoje - timedelta(days=30),
        )
    ).all()
    for r in canceladas:
        if r.id not in itens:
            itens[r.id] = _item_aluno(db, r, None, hoje)
    return sorted(itens.values(), key=lambda i: (not i["dentro_do_prazo"], i["reposicao_ate"], i["id"]))


def pedir_reposicao(db: Session, aluno: Aluno, reserva_id: int, preferencia: str | None, *, agora: datetime | None = None) -> dict:
    """Cria o pedido (ou atualiza a preferência se já há um PENDENTE). Um pedido ativo por aula desmarcada."""
    momento = base._agora(agora)
    r, s = base._reserva_do_aluno(db, aluno, reserva_id)
    hoje = hoje_de_negocio(momento)
    if StatusReserva(r.status) != StatusReserva.CANCELADA or r.reposicao_ate is None:
        raise Conflito("Esta aula não está desmarcada para reposição.")
    if r.reposicao_ate < hoje:
        raise Conflito(f"O prazo desta reposição terminou em {r.reposicao_ate:%d/%m/%Y}. Fale com a recepção.")
    texto = limpar_texto(preferencia, MAX_PREFERENCIA) or None
    atual = db.scalar(
        select(ReposicaoPedido)
        .where(ReposicaoPedido.reserva_origem_id == r.id, ReposicaoPedido.status != StatusPedido.CANCELADO)
        .order_by(ReposicaoPedido.id.desc())
        .limit(1)
    )
    if atual is not None:
        redesmarcada = atual.decidido_em is not None and r.desmarcada_em is not None and r.desmarcada_em > atual.decidido_em
        st = StatusPedido(atual.status)
        if st == StatusPedido.PENDENTE:
            atual.preferencia = texto  # idempotente: só atualiza a preferência
            db.flush()
            return _item_aluno(db, r, atual, hoje)
        if not redesmarcada:
            if st == StatusPedido.RECUSADO:
                raise Conflito("Seu pedido foi recusado. Fale com a recepção se precisar de ajuda.")
            raise Conflito("Esta reposição já foi aprovada.")
        if st == StatusPedido.APROVADO:
            atual.status = StatusPedido.CANCELADO  # a aula aprovada foi desmarcada de novo: vale um pedido novo
            db.flush()
    try:
        with agenda.savepoint(db):
            novo = ReposicaoPedido(
                aluno_id=aluno.id,
                reserva_origem_id=r.id,
                data_origem=s.data,
                hora_origem=s.hora_inicio,
                preferencia=texto,
                status=StatusPedido.PENDENTE,
            )
            db.add(novo)
            db.flush()
    except IntegrityError:  # duas chamadas ao mesmo tempo: vale a que chegou primeiro
        novo = db.scalar(
            select(ReposicaoPedido).where(ReposicaoPedido.reserva_origem_id == r.id, ReposicaoPedido.status == StatusPedido.PENDENTE)
        )
        if novo is None:
            raise Conflito("Já existe um pedido para esta aula.") from None
        novo.preferencia = texto
        db.flush()
    return _item_aluno(db, r, novo, hoje)


# ---------------------------------------------------------------------------------------------------------- gerência
def _pedido(db: Session, pedido_id: int) -> ReposicaoPedido:
    p = db.get(ReposicaoPedido, pedido_id)
    if p is None:
        raise NaoEncontrado("Pedido de reposição não encontrado.")
    return p


def _item_equipe(db: Session, p: ReposicaoPedido, hoje: date) -> dict:
    r = db.get(Reserva, p.reserva_origem_id)
    aluno = db.get(Aluno, p.aluno_id)
    s = db.get(AulaSessao, r.aula_sessao_id) if r else None
    cancelada = bool(r and StatusReserva(r.status) == StatusReserva.CANCELADA)
    ate = r.reposicao_ate if (r and cancelada and r.reposicao_ate) else p.data_origem + timedelta(days=30)
    quem = db.get(Usuario, p.decidido_por_usuario_id) if p.decidido_por_usuario_id else None
    return {
        "id": p.id,
        "status": StatusPedido(p.status).value,
        "aluno": {"id": aluno.id, "nome": aluno.nome} if aluno else None,
        "reserva_id": p.reserva_origem_id,
        "aula_original": {
            "data": p.data_origem,
            "hora_inicio": p.hora_origem,
            "servico": base._nome_servico(db, s.tipo_servico_id) if s else None,
            "profissional": base._nome_prof(db, s.profissional_id) if s and cancelada else None,
        },
        "reposicao_ate": ate,
        "dias_restantes": (ate - hoje).days,
        "prazo_vencido": ate < hoje,
        "aula_desmarcada": cancelada,
        "preferencia": p.preferencia,
        "pedido_em": p.criado_em,
        "decidido_em": p.decidido_em,
        "decidido_por": quem.nome if quem else None,
        "motivo_recusa": p.motivo_recusa,
        "aprovado_data": p.aprovado_data,
        "aprovado_hora": p.aprovado_hora,
        "ignorou_prazo": bool(p.ignorou_prazo),
        "motivo_ignorar_prazo": p.motivo_ignorar_prazo,
    }


def listar_pedidos(
    db: Session, *, status: str | None = None, busca: str | None = None, limite: int = 200, agora: datetime | None = None
) -> dict:
    hoje = hoje_de_negocio(base._agora(agora))
    filtros = [ReposicaoPedido.status != StatusPedido.CANCELADO]
    juntar = bool(busca and busca.strip())
    if juntar:
        filtros.append(Aluno.nome.ilike(f"%{limpar_texto(busca, 80)}%"))
    contagem = select(ReposicaoPedido.status, func.count()).where(*filtros).group_by(ReposicaoPedido.status)
    q = select(ReposicaoPedido).where(*filtros)
    if juntar:
        contagem = contagem.join(Aluno, Aluno.id == ReposicaoPedido.aluno_id)
        q = q.join(Aluno, Aluno.id == ReposicaoPedido.aluno_id)
    contagens = {s.value: 0 for s in (StatusPedido.PENDENTE, StatusPedido.APROVADO, StatusPedido.RECUSADO)}
    for st, n in db.execute(contagem):
        contagens[StatusPedido(st).value] = n
    if status:
        try:
            q = q.where(ReposicaoPedido.status == StatusPedido(status.upper()))
        except ValueError:
            raise Invalido("Situação inválida.") from None
    pedidos = db.scalars(q.order_by(ReposicaoPedido.id.desc()).limit(limite)).all()
    itens = [_item_equipe(db, p, hoje) for p in pedidos]
    # pendentes: os de prazo mais curto primeiro
    itens.sort(key=lambda i: (i["status"] != "PENDENTE", i["reposicao_ate"] if i["status"] == "PENDENTE" else date.max, -i["id"]))
    return {"contagens": contagens, "itens": itens}


def _prazo_e_limite(r: Reserva, hoje: date, ignorar: bool) -> date:
    base_ate = r.reposicao_ate or hoje
    return max(base_ate, hoje) + timedelta(days=DIAS_EXTRA_FORA_DO_PRAZO) if ignorar else base_ate


def opcoes_do_pedido(db: Session, pedido_id: int, *, ignorar_prazo: bool = False, agora: datetime | None = None, limite: int = 80) -> list[dict]:
    momento = base._agora(agora)
    hoje = hoje_de_negocio(momento)
    p = _pedido(db, pedido_id)
    r = db.get(Reserva, p.reserva_origem_id)
    if StatusPedido(p.status) != StatusPedido.PENDENTE or r is None or StatusReserva(r.status) != StatusReserva.CANCELADA:
        return []
    antiga = db.get(AulaSessao, r.aula_sessao_id)
    return [_opcao(db, s) for s in _candidatas(db, p.aluno_id, antiga, hoje, momento, _prazo_e_limite(r, hoje, ignorar_prazo))][:limite]


def aprovar(
    db: Session,
    pedido_id: int,
    aula_id: int,
    usuario: Usuario,
    *,
    ignorar_prazo: bool = False,
    motivo: str | None = None,
    agora: datetime | None = None,
) -> ReposicaoPedido:
    """Aprova escolhendo a aula. Fora do prazo (reposição vencida ou aula depois de ``reposicao_ate``) só com
    ``ignorar_prazo`` + motivo. A reserva é remarcada pelo serviço da agenda (vaga garantida pela transação)."""
    momento = base._agora(agora)
    hoje = hoje_de_negocio(momento)
    p = _pedido(db, pedido_id)
    if StatusPedido(p.status) != StatusPedido.PENDENTE:
        raise Conflito("Este pedido já foi decidido.")
    r = db.get(Reserva, p.reserva_origem_id)
    if r is None or StatusReserva(r.status) != StatusReserva.CANCELADA:
        raise Conflito("Esta aula já não está desmarcada (foi remarcada ou excluída). Recuse ou ignore o pedido.")
    nova = db.get(AulaSessao, aula_id)
    if nova is None:
        raise Conflito("Essa aula não existe mais. Escolha outra.")
    limite = r.reposicao_ate
    fora = limite is not None and (limite < hoje or nova.data > limite)
    motivo_limpo = limpar_texto(motivo, MAX_MOTIVO)
    if fora and not ignorar_prazo:
        raise Conflito(
            f"A reposição desta aula vale até {limite:%d/%m/%Y}. Para aprovar fora do prazo, marque \"ignorar prazo\" e informe o motivo.",
            dados={"fora_do_prazo": True},
        )
    if fora and ignorar_prazo and len(motivo_limpo) < 3:
        raise Invalido("Informe o motivo para ignorar o prazo da reposição.")
    antiga = db.get(AulaSessao, r.aula_sessao_id)
    if aula_id not in {s.id for s in _candidatas(db, p.aluno_id, antiga, hoje, momento, _prazo_e_limite(r, hoje, ignorar_prazo))}:
        raise Conflito("Esse horário não está disponível (sem vaga, bloqueado, já passou ou fora do serviço/unidade da aula).")
    try:
        agenda.remarcar_reserva(
            db,
            r.id,
            data=nova.data,
            hora_inicio=nova.hora_inicio,
            profissional_id=nova.profissional_id,
            ignorar_prazo_reposicao=bool(fora and ignorar_prazo),
            agora=momento,
        )
    except agenda.ErroAgenda as e:
        raise base._traduzir(e) from e
    p.status = StatusPedido.APROVADO
    p.reserva_nova_id = r.id
    p.aprovado_data = nova.data
    p.aprovado_hora = nova.hora_inicio
    p.decidido_por_usuario_id = usuario.id
    p.decidido_em = momento
    p.ignorou_prazo = bool(fora and ignorar_prazo)
    p.motivo_ignorar_prazo = motivo_limpo if p.ignorou_prazo else None
    db.flush()
    return p


def recusar(db: Session, pedido_id: int, usuario: Usuario, motivo: str | None, *, agora: datetime | None = None) -> ReposicaoPedido:
    p = _pedido(db, pedido_id)
    if StatusPedido(p.status) != StatusPedido.PENDENTE:
        raise Conflito("Este pedido já foi decidido.")
    texto = limpar_texto(motivo, MAX_MOTIVO)
    if len(texto) < 3:
        raise Invalido("Informe o motivo da recusa (o aluno vai ler).")
    p.status = StatusPedido.RECUSADO
    p.motivo_recusa = texto
    p.decidido_por_usuario_id = usuario.id
    p.decidido_em = base._agora(agora)
    db.flush()
    return p


# ------------------------------------------------------------------------------------------------------- avisos ao aluno
def texto_aprovado(aluno: Aluno, p: ReposicaoPedido) -> str:
    primeiro = aluno.nome.split()[0] if aluno.nome else ""
    return (
        f"Olá, {primeiro}! Sua reposição foi aprovada: {p.aprovado_data:%d/%m/%Y} às {p.aprovado_hora:%H:%M}. "
        "Qualquer dúvida, fale com a recepção."
    )


def texto_recusado(aluno: Aluno, p: ReposicaoPedido) -> str:
    primeiro = aluno.nome.split()[0] if aluno.nome else ""
    return f"Olá, {primeiro}! Não foi possível aprovar sua reposição de {p.data_origem:%d/%m/%Y}. Motivo: {p.motivo_recusa}"
