"""Cálculo do resumo do painel inicial.

Regras:
- "hoje" é a data de negócio (America/Sao_Paulo, ``domain.financeiro.hoje_de_negocio``): às 23h em Brasília ainda é o mesmo dia.
- Cada bloco só é calculado se o perfil tem a permissão do assunto. Perfil restrito (Professor, ``somente_proprias_aulas``)
  só enxerga aulas, e só as próprias; nunca financeiro, contratos, alunos nem aniversariantes, mesmo que a matriz de
  permissões do perfil libere algo disso.
- Tudo é agregado no banco (poucas consultas, ver ``tests/painel/test_desempenho.py``); nada é gravado.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, distinct, extract, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Contexto
from app.domain.financeiro import (
    FUSO_NEGOCIO,
    deslocar_mes_limitado,
    hoje_de_negocio,
    ultimo_dia_do_mes_anterior,
)
from app.modules.agenda.models import AulaSessao, Evolucao, Reserva, StatusReserva, WhatsappAgendamentoLog
from app.modules.alunos.models import Aluno, StatusAluno
from app.modules.app_aluno.models import ReposicaoPedido, StatusPedido
from app.modules.cadastros.models import Plano, Profissional, TipoServico, Unidade
from app.modules.comunicacao import servico as comunicacao
from app.modules.contratos.models import Contrato, StatusAssinatura
from app.modules.financeiro.models import ContaReceber, StatusReceber
from app.modules.integracoes.models import TotalpassEvento, WhatsappConfig
from app.modules.painel import schemas as sc

MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
ASSUNTOS_DO_RESTRITO = {"painel", "aulas", "agenda"}  # o resto é bloqueado para o perfil Professor
JANELA_VENCIMENTO_DIAS = 30
JANELA_ANIVERSARIO_DIAS = 7
JANELA_SEM_EVOLUCAO_DIAS = 30
JANELA_ERRO_TOTALPASS_DIAS = 3
LIMITE_PROXIMAS = 8
LIMITE_ANIVERSARIANTES = 20
LIMITE_RANKING = 6
_GRAVIDADE = {"critico": 0, "aviso": 1, "info": 2}


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _mes(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _inicio_mes(d: date, deslocamento: int = 0) -> date:
    return deslocar_mes_limitado(d.replace(day=1), deslocamento)


def _bissexto(ano: int) -> bool:
    return ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)


class _Calculo:
    def __init__(self, ctx: Contexto, agora: datetime):
        self.ctx = ctx
        self.db: Session = ctx.db
        self.agora = agora
        self.hoje = hoje_de_negocio(agora)
        self.restrito = ctx.somente_proprias_aulas()
        self.profissional_id = ctx.profissional_id() if self.restrito else None

    # ------------------------------------------------------------------ permissões e escopo
    def pode(self, permissao: str) -> bool:
        if not self.ctx.pode(permissao):
            return False
        return not self.restrito or permissao.split(".")[0] in ASSUNTOS_DO_RESTRITO

    def escopo_aulas(self, consulta):
        """Perfil restrito: só as aulas do próprio profissional (sem vínculo, nada)."""
        if not self.restrito:
            return consulta
        if self.profissional_id is None:
            return consulta.where(false())
        return consulta.where(AulaSessao.profissional_id == self.profissional_id)

    # ------------------------------------------------------------------ blocos
    def alunos_ativos(self) -> sc.KpiNumero:
        if not self.pode("alunos.ver"):
            return sc.KpiNumero()
        n = self.db.scalar(select(func.count()).select_from(Aluno).where(Aluno.status == StatusAluno.ATIVO)) or 0
        return sc.KpiNumero(visivel=True, valor=n, href="/alunos?status=ATIVO")

    def aulas(self) -> tuple[sc.KpiAulas, sc.AulasPorMes]:
        """Aulas de hoje/amanhã e dos últimos 6 meses numa consulta só (reservas não canceladas)."""
        if not self.pode("aulas.ver"):
            return sc.KpiAulas(), sc.AulasPorMes()
        amanha = self.hoje + timedelta(days=1)
        inicios = [_inicio_mes(self.hoje, k) for k in range(-5, 1)]
        fim = deslocar_mes_limitado(inicios[-1], 1)
        limites = [*inicios[1:], fim]
        colunas = [
            func.coalesce(func.sum(case((AulaSessao.data == self.hoje, 1), else_=0)), 0),
            func.coalesce(func.sum(case((AulaSessao.data == amanha, 1), else_=0)), 0),
        ] + [
            func.coalesce(func.sum(case((and_(AulaSessao.data >= ini, AulaSessao.data < lim), 1), else_=0)), 0)
            for ini, lim in zip(inicios, limites, strict=True)
        ]
        # o intervalo vai até amanhã mesmo no último dia do mês (amanhã pode cair no mês seguinte)
        topo = max(fim, amanha + timedelta(days=1))
        q = (
            select(*colunas)
            .select_from(Reserva)
            .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
            .where(Reserva.status != StatusReserva.CANCELADA, AulaSessao.data >= inicios[0], AulaSessao.data < topo)
        )
        linha = self.db.execute(self.escopo_aulas(q)).one()
        hoje_n, amanha_n, *por_mes = (int(x) for x in linha)
        meses = [
            sc.AulasMes(mes=_mes(ini), rotulo=f"{MESES[ini.month - 1]}/{str(ini.year)[-2:]}", total=n)
            for ini, n in zip(inicios, por_mes, strict=True)
        ]
        return (
            sc.KpiAulas(visivel=True, hoje=hoje_n, amanha=amanha_n, href="/agenda/aulas"),
            sc.AulasPorMes(visivel=True, meses=meses, total=sum(por_mes)),
        )

    def ranking(self) -> sc.RankingProfessores:
        if not self.pode("aulas.ver"):
            return sc.RankingProfessores()
        ini = _inicio_mes(self.hoje)
        fim = deslocar_mes_limitado(ini, 1)
        total = func.count(Reserva.id)
        q = (
            select(AulaSessao.profissional_id, Profissional.nome, total)
            .select_from(Reserva)
            .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
            .join(Profissional, Profissional.id == AulaSessao.profissional_id)
            .where(Reserva.status != StatusReserva.CANCELADA, AulaSessao.data >= ini, AulaSessao.data < fim)
            .group_by(AulaSessao.profissional_id, Profissional.nome)
            .order_by(total.desc(), Profissional.nome)
            .limit(LIMITE_RANKING)
        )
        itens = [sc.ProfessorRanking(profissional_id=p, nome=n, total=t) for p, n, t in self.db.execute(self.escopo_aulas(q))]
        return sc.RankingProfessores(visivel=True, mes=_mes(ini), itens=itens)

    def proximas(self) -> sc.ProximasAulas:
        if not self.pode("aulas.ver"):
            return sc.ProximasAulas()
        agora_local = self.agora.astimezone(FUSO_NEGOCIO).time() if self.agora.tzinfo else self.agora.time()
        ver_alunos = self.pode("alunos.ver")
        q = (
            select(Reserva.id, AulaSessao.id, AulaSessao.hora_inicio, Aluno.nome, Profissional.nome, Reserva.status,
                   func.count().over())
            .select_from(Reserva)
            .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
            .join(Aluno, Aluno.id == Reserva.aluno_id)
            .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
            .where(
                AulaSessao.data == self.hoje,
                AulaSessao.hora_fim > agora_local,
                Reserva.status.in_([StatusReserva.RESERVADA, StatusReserva.PENDENTE]),
            )
            .order_by(AulaSessao.hora_inicio, Aluno.nome)
            .limit(LIMITE_PROXIMAS)
        )
        linhas = self.db.execute(self.escopo_aulas(q)).all()
        itens = [
            sc.ProximaAula(reserva_id=r, sessao_id=s, hora=h.strftime("%H:%M"), aluno=a if ver_alunos else None,
                           professor=p, status=str(getattr(st, "value", st)))
            for r, s, h, a, p, st, _ in linhas
        ]
        total = linhas[0][6] if linhas else 0
        return sc.ProximasAulas(visivel=True, itens=itens, restantes=max(total - len(itens), 0), href="/agenda/aulas")

    def contratos(self) -> tuple[sc.KpiNumero, int | None]:
        """(KPI de contratos vencendo em 30 dias, contratos vigentes sem assinatura)."""
        if not self.pode("contratos.ver"):
            return sc.KpiNumero(), None
        limite = self.hoje + timedelta(days=JANELA_VENCIMENTO_DIAS)
        vencendo, sem_assinar = self.db.execute(
            select(
                func.coalesce(func.sum(case((Contrato.data_fim <= limite, 1), else_=0)), 0),
                func.coalesce(func.sum(case((Contrato.status_assinatura == StatusAssinatura.NAO_ASSINADO, 1), else_=0)), 0),
            ).where(Contrato.data_fim >= self.hoje)
        ).one()
        return sc.KpiNumero(visivel=True, valor=int(vencendo), href="/contratos?vencendo=30"), int(sem_assinar)

    def receber(self) -> tuple[sc.KpiValor, sc.KpiValor, sc.RecebidoMes]:
        if not self.pode("financeiro_receber.ver"):
            return sc.KpiValor(), sc.KpiValor(), sc.RecebidoMes()
        ini = _inicio_mes(self.hoje)
        fim = deslocar_mes_limitado(ini, 1) - timedelta(days=1)
        ant_ini = _inicio_mes(self.hoje, -1)
        ant_fim = ultimo_dia_do_mes_anterior(ini)
        ant_mesmo_dia = deslocar_mes_limitado(self.hoje, -1)
        aberto = ContaReceber.status == StatusReceber.ABERTO
        pago = ContaReceber.status == StatusReceber.PAGO

        def soma(cond):
            return func.coalesce(func.sum(case((cond, ContaReceber.valor), else_=0)), 0)

        def qtd(cond):
            return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

        a_vencer = and_(aberto, ContaReceber.vencimento >= self.hoje)
        atrasada = and_(aberto, ContaReceber.vencimento < self.hoje)
        v_aberto, n_aberto, v_atraso, n_atraso, rec, rec_ant, rec_ant_dia = self.db.execute(
            select(
                soma(a_vencer), qtd(a_vencer), soma(atrasada), qtd(atrasada),
                soma(and_(pago, ContaReceber.pagamento >= ini, ContaReceber.pagamento <= fim)),
                soma(and_(pago, ContaReceber.pagamento >= ant_ini, ContaReceber.pagamento <= ant_fim)),
                soma(and_(pago, ContaReceber.pagamento >= ant_ini, ContaReceber.pagamento <= ant_mesmo_dia)),
            ).where(ContaReceber.status.in_([StatusReceber.ABERTO, StatusReceber.PAGO]))
        ).one()
        rec, rec_ant, rec_ant_dia = _dec(rec), _dec(rec_ant), _dec(rec_ant_dia)
        variacao = round(float((rec - rec_ant_dia) / rec_ant_dia * 100), 1) if rec_ant_dia > 0 else None
        return (
            sc.KpiValor(visivel=True, valor=_dec(v_aberto), quantidade=int(n_aberto), href="/financeiro/receber?status=ABERTO"),
            sc.KpiValor(visivel=True, valor=_dec(v_atraso), quantidade=int(n_atraso), href="/financeiro/receber?status=ATRASADO"),
            sc.RecebidoMes(visivel=True, mes=_mes(ini), valor=rec, mes_anterior=rec_ant, anterior_ate_mesmo_dia=rec_ant_dia,
                           variacao_pct=variacao, href="/financeiro/receber?status=PAGO"),
        )

    def aniversariantes(self) -> sc.Aniversariantes:
        if not self.pode("alunos.ver"):
            return sc.Aniversariantes()
        dias = [self.hoje + timedelta(days=k) for k in range(JANELA_ANIVERSARIO_DIAS + 1)]
        pares: dict[tuple[int, int], date] = {(d.month, d.day): d for d in dias}
        for d in dias:  # 29/02 comemora em 28/02 nos anos sem bissexto
            if (d.month, d.day) == (2, 28) and not _bissexto(d.year):
                pares[(2, 29)] = d
        cond = or_(*[and_(extract("month", Aluno.data_nascimento) == m, extract("day", Aluno.data_nascimento) == dia)
                     for (m, dia) in pares])
        linhas = self.db.execute(
            select(Aluno.id, Aluno.nome, Aluno.data_nascimento)
            .where(Aluno.status == StatusAluno.ATIVO, Aluno.data_nascimento.is_not(None), cond)
        ).all()
        itens = []
        for aid, nome, nasc in linhas:
            quando = pares[(nasc.month, nasc.day)]  # a virada de ano já está nas datas da janela
            itens.append(sc.Aniversariante(aluno_id=aid, nome=nome, dia=quando, idade=quando.year - nasc.year, hoje=quando == self.hoje))
        itens.sort(key=lambda a: (a.dia, a.nome))
        return sc.Aniversariantes(visivel=True, itens=itens[:LIMITE_ANIVERSARIANTES])

    # ------------------------------------------------------------------ alertas
    def alertas(self, atrasado: sc.KpiValor, nao_assinados: int | None) -> sc.Alertas:
        itens: list[sc.Alerta] = []
        permissoes = [
            self.pode("financeiro_receber.ver"), self.pode("aulas.ver"), self.pode("contratos.ver"),
            self.pode("reposicoes.ver"), self.pode("whatsapp.configurar"), self.pode("integracoes.ver"),
        ]
        if atrasado.visivel and atrasado.quantidade:
            itens.append(sc.Alerta(chave="contas_atrasadas", titulo="Contas a receber em atraso", quantidade=atrasado.quantidade,
                                   valor=atrasado.valor, gravidade="critico", href=atrasado.href,
                                   detalhe="Cobre os alunos com mensalidade vencida."))
        if self.pode("aulas.ver"):
            n = self._sem_evolucao()
            if n:
                itens.append(sc.Alerta(chave="aulas_sem_evolucao", titulo="Aulas passadas sem evolução", quantidade=n,
                                       gravidade="aviso", href="/agenda/aulas",
                                       detalhe=f"Aulas concluídas nos últimos {JANELA_SEM_EVOLUCAO_DIAS} dias."))
        if nao_assinados:
            itens.append(sc.Alerta(chave="contratos_nao_assinados", titulo="Contratos não assinados", quantidade=nao_assinados,
                                   gravidade="aviso", href="/contratos?assinatura=NAO_ASSINADO",
                                   detalhe="Contratos vigentes aguardando assinatura do aluno."))
        if self.pode("reposicoes.ver"):
            n = self.db.scalar(select(func.count()).select_from(ReposicaoPedido).where(ReposicaoPedido.status == StatusPedido.PENDENTE)) or 0
            if n:
                itens.append(sc.Alerta(chave="reposicoes_pendentes", titulo="Pedidos de reposição pendentes", quantidade=n,
                                       gravidade="aviso", href="/reposicoes", detalhe="Aguardando decisão da gerência."))
        if self.pode("whatsapp.configurar"):
            itens.extend(self._alertas_whatsapp())
        if self.pode("integracoes.ver"):
            desde = self.agora - timedelta(days=JANELA_ERRO_TOTALPASS_DIAS)
            n = self.db.scalar(select(func.count()).select_from(TotalpassEvento)
                               .where(TotalpassEvento.resultado == "erro", TotalpassEvento.recebido_em >= desde)) or 0
            if n:
                itens.append(sc.Alerta(chave="totalpass_erro", titulo="TotalPass com erro recente", quantidade=n, gravidade="critico",
                                       href="/configuracoes/integracoes",
                                       detalhe=f"{n} evento(s) com erro nos últimos {JANELA_ERRO_TOTALPASS_DIAS} dias."))
        itens.sort(key=lambda a: _GRAVIDADE.get(a.gravidade, 9))
        return sc.Alertas(visivel=any(permissoes), itens=itens)

    def _sem_evolucao(self) -> int:
        q = (
            select(func.count(distinct(Reserva.id)))
            .select_from(Reserva)
            .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
            .outerjoin(Evolucao, Evolucao.reserva_id == Reserva.id)
            .where(
                Reserva.status == StatusReserva.CONCLUIDA,
                Evolucao.id.is_(None),
                AulaSessao.data <= self.hoje,
                AulaSessao.data >= self.hoje - timedelta(days=JANELA_SEM_EVOLUCAO_DIAS),
            )
        )
        return self.db.scalar(self.escopo_aulas(q)) or 0

    def _alertas_whatsapp(self) -> list[sc.Alerta]:
        configuradas, caida = self.db.execute(
            select(
                select(func.count()).select_from(WhatsappConfig).where(WhatsappConfig.credencial_cifrado.is_not(None)).scalar_subquery(),
                select(func.count()).select_from(WhatsappAgendamentoLog).where(
                    WhatsappAgendamentoLog.tipo == "alerta",
                    WhatsappAgendamentoLog.status.in_(["sessao_caida", "credencial_recusada"]),
                    WhatsappAgendamentoLog.data_referencia >= self.hoje - timedelta(days=1),
                ).scalar_subquery(),
            )
        ).one()
        if not configuradas:
            return []  # WhatsApp ainda não configurado: o "Primeiros passos" cuida disso
        out: list[sc.Alerta] = []
        if caida:
            out.append(sc.Alerta(chave="whatsapp_sessao", titulo="WhatsApp com sessão caída ou credencial recusada", quantidade=caida,
                                 gravidade="critico", href="/comunicacao/whatsapp",
                                 detalhe="Os avisos automáticos pararam. Reconecte a sessão."))
        if not comunicacao.envio_automatico_ativo(self.db):
            out.append(sc.Alerta(chave="whatsapp_automatico_desligado", titulo="Avisos automáticos de WhatsApp desligados", quantidade=1,
                                 gravidade="info", href="/comunicacao/whatsapp",
                                 detalhe="Nenhum aviso (aula, vencimento, aniversário) será enviado sozinho."))
        return out

    # ------------------------------------------------------------------ primeiros passos
    def primeiros_passos(self) -> tuple[sc.PrimeirosPassos, int | None]:
        """(bloco, total de alunos). Só para quem pode cadastrar (Full); some quando o básico está cadastrado."""
        if not self.pode("cadastros_unidades.editar"):
            return sc.PrimeirosPassos(), None
        un, srv, pl, pr, al, zap = self.db.execute(
            select(
                select(func.count()).select_from(Unidade).where(Unidade.ativo.is_(True)).scalar_subquery(),
                select(func.count()).select_from(TipoServico).where(TipoServico.ativo.is_(True)).scalar_subquery(),
                select(func.count()).select_from(Plano).scalar_subquery(),
                select(func.count()).select_from(Profissional).where(Profissional.ativo.is_(True)).scalar_subquery(),
                select(func.count()).select_from(Aluno).scalar_subquery(),
                select(func.count()).select_from(WhatsappConfig).where(WhatsappConfig.credencial_cifrado.is_not(None)).scalar_subquery(),
            )
        ).one()
        passos = [
            sc.PassoInicial(chave="unidade", titulo="Cadastre a unidade", descricao="Nome, capacidade por aula e duração da aula.", feito=un > 0, href="/cadastros/unidades"),
            sc.PassoInicial(chave="servico", titulo="Cadastre o tipo de serviço", descricao="Por exemplo, Pilates de solo.", feito=srv > 0, href="/cadastros/servicos"),
            sc.PassoInicial(chave="plano", titulo="Crie os planos", descricao="Valor mensal e aulas por semana.", feito=pl > 0, href="/cadastros/planos"),
            sc.PassoInicial(chave="profissional", titulo="Cadastre os profissionais", descricao="Quem dá aula e a comissão de cada um.", feito=pr > 0, href="/cadastros/profissionais"),
            sc.PassoInicial(chave="aluno", titulo="Cadastre os alunos", descricao="Ou aguarde a carga dos dados do sistema antigo.", feito=al > 0, href="/alunos/novo"),
        ]
        if self.pode("whatsapp.configurar"):
            passos.append(sc.PassoInicial(chave="whatsapp", titulo="Configure o WhatsApp", descricao="Em Configurações > Integrações: avisos e códigos do app do aluno.",
                                          feito=zap > 0, href="/configuracoes/integracoes", conta=False))
        completo = all(p.feito for p in passos if p.conta)
        return sc.PrimeirosPassos(visivel=True, completo=completo, passos=passos), al


def calcular_resumo(ctx: Contexto, agora: datetime | None = None) -> sc.ResumoPainel:
    """Resumo do painel para o usuário do contexto. ``agora`` (UTC) existe para teste."""
    agora = agora or datetime.now(UTC)
    c = _Calculo(ctx, agora)
    kpi_aulas, aulas_mes = c.aulas()
    kpi_contratos, nao_assinados = c.contratos()
    a_receber, atrasado, recebido = c.receber()
    alunos = c.alunos_ativos()
    passos, total_alunos = c.primeiros_passos()
    if total_alunos is not None:
        vazio = total_alunos == 0
    else:
        vazio = alunos.visivel and alunos.valor == 0
    return sc.ResumoPainel(
        hoje=c.hoje,
        gerado_em=agora,
        restrito=c.restrito,
        vazio=bool(vazio),
        kpis=sc.Kpis(alunos_ativos=alunos, aulas=kpi_aulas, contratos_vencendo=kpi_contratos, a_receber=a_receber, atrasado=atrasado),
        recebido_mes=recebido,
        aulas_por_mes=aulas_mes,
        ranking_professores=c.ranking(),
        proximas_aulas=c.proximas(),
        aniversariantes=c.aniversariantes(),
        alertas=c.alertas(atrasado, nao_assinados),
        primeiros_passos=passos,
    )
