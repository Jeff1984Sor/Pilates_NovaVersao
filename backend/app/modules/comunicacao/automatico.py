"""Avisos automáticos de WhatsApp (R9): o que o worker executa a cada 5 minutos.

Quem DECIDE o que está devido (horário, liga/desliga, textos, chave de deduplicação) é ``domain.whatsapp_avisos``.
Aqui ficam só: carregar os dados do banco, reservar o envio, enviar e registrar.

Segurança contra duplicidade (inclusive com mais de um worker):
1. a linha de ``whatsapp_agendamento_log`` com ``dedupe_key`` UNIQUE é gravada (``pendente``) e confirmada ANTES de enviar:
   quem perder a corrida (``IntegrityError``) simplesmente não envia;
2. sucesso -> ``sent``; falha depois de 3 tentativas -> ``failed`` (definitivo para aquele dia/semana: não insiste);
   sessão caída ou credencial recusada -> a reserva é APAGADA (o aviso volta a ficar devido na próxima rodada) e o lote
   da unidade é abortado; ``pendente`` esquecido (worker morreu no meio) NÃO é reenviado (prefere-se perder a repetir);
3. telefone ausente/fixo/inválido: grava ``sem_telefone`` e segue (aparece no acompanhamento).
Nada é enviado se a chave geral "envio automático ativo" do ambiente estiver desligada.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import extract, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import email as mail
from app.core.db import SessionLocal, agora
from app.core.models import PerfilAcesso, Usuario
from app.domain import whatsapp_avisos as dom
from app.domain.telefone import normalizar_telefone_br
from app.modules.agenda.models import AulaSessao, Reserva, WhatsappAgendamentoLog
from app.modules.alunos.models import Aluno, StatusAluno
from app.modules.cadastros.models import Profissional, TipoServico, Unidade
from app.modules.comunicacao import servico as svc
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber, StatusReceber
from app.modules.integracoes.models import WhatsappConfig

log = logging.getLogger(__name__)

MAX_ENVIOS_POR_RODADA = 60  # ~5 min de envios com pausa de 5 s; o resto fica para a próxima rodada


@dataclass
class ResumoRodada:
    enviados: int = 0
    falhas: int = 0
    sem_telefone: int = 0
    abortadas: list[int] = field(default_factory=list)  # unidades abortadas por sessão caída/credencial recusada
    desligado: bool = False
    por_tipo: dict[str, int] = field(default_factory=dict)


@dataclass
class _Ids:
    aluno_id: int | None = None
    profissional_id: int | None = None
    contrato_id: int | None = None


# ------------------------------------------------------------------------------------------------ carga de dados
def _telefones(db: Session, aluno_ids: set[int]) -> dict[int, list[str]]:
    from app.modules.alunos.models import AlunoTelefone

    mapa: dict[int, list[str]] = defaultdict(list)
    if aluno_ids:
        for aid, num in db.execute(select(AlunoTelefone.aluno_id, AlunoTelefone.numero)
                                   .where(AlunoTelefone.aluno_id.in_(aluno_ids)).order_by(AlunoTelefone.ordem, AlunoTelefone.id)):
            mapa[aid].append(num)
    return mapa


def _aluno_aviso(a: Aluno, tel: dict[int, list[str]]) -> dom.AlunoAviso:
    return dom.AlunoAviso(a.id, a.nome, tel.get(a.id, []), a.unidade_id, str(a.status.value), a.data_nascimento, a.codigo_legado or 0)


def carregar_dados(db: Session, unidade: Unidade, hoje: date, tipos: set[str]) -> tuple[dom.DadosParaAvisos, dict[str, dict]]:
    """Carrega só o que os tipos ativos precisam. Devolve também os mapas destinatário -> ids do banco, para o log."""
    ids: dict[str, dict] = {t: {} for t in dom.TIPOS}
    reservas: list[dom.ReservaAviso] = []
    alunos: list[dom.AlunoAviso] = []
    contratos: list[dom.ContratoAviso] = []
    contas: list[dom.ContaAviso] = []

    if tipos & {dom.LEMBRETE_ALUNO, dom.AGENDA_PROFESSOR}:
        amanha = hoje + timedelta(days=1)
        linhas = db.execute(
            select(Reserva, AulaSessao, Aluno, TipoServico, Profissional)
            .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
            .join(Aluno, Aluno.id == Reserva.aluno_id)
            .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
            .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
            .where(AulaSessao.unidade_id == unidade.id, AulaSessao.data == amanha)
        ).all()
        tel = _telefones(db, {a.id for _, _, a, _, _ in linhas})
        for r, s, a, t, p in linhas:
            prof = dom.ProfissionalAviso(p.id, p.nome, p.celular) if p else None
            reservas.append(dom.ReservaAviso(r.id, _aluno_aviso(a, tel), str(r.status.value), s.data, s.hora_inicio,
                                             s.unidade_id, unidade.nome, t.nome, prof))
        for r in reservas:
            ids[dom.LEMBRETE_ALUNO][r.aluno.id] = _Ids(aluno_id=r.aluno.id)
            if r.profissional:
                ids[dom.AGENDA_PROFESSOR][r.profissional.id] = _Ids(profissional_id=r.profissional.id)

    if dom.ANIVERSARIO in tipos:
        encontrados = db.scalars(select(Aluno).where(
            Aluno.unidade_id == unidade.id, Aluno.status == StatusAluno.ATIVO, Aluno.data_nascimento.is_not(None),
            extract("month", Aluno.data_nascimento) == hoje.month, extract("day", Aluno.data_nascimento) == hoje.day)).all()
        tel = _telefones(db, {a.id for a in encontrados})
        alunos = [_aluno_aviso(a, tel) for a in encontrados]
        for a in alunos:
            ids[dom.ANIVERSARIO][a.id] = _Ids(aluno_id=a.id)

    if tipos & {dom.RENOVACAO, dom.TRES_MESES}:
        filtros = []
        if dom.RENOVACAO in tipos:
            filtros.append(Contrato.data_fim == hoje + timedelta(days=dom.DIAS_RENOVACAO))
        if dom.TRES_MESES in tipos:
            filtros.append(Contrato.data_inicio == hoje - timedelta(days=dom.DIAS_TRES_MESES))
        linhas = db.execute(select(Contrato, Aluno).join(Aluno, Aluno.id == Contrato.aluno_id)
                            .where(Contrato.unidade_id == unidade.id, or_(*filtros))).all()
        tel = _telefones(db, {a.id for _, a in linhas})
        for c, a in linhas:
            contratos.append(dom.ContratoAviso(c.id, c.codigo_legado or c.id, _aluno_aviso(a, tel), c.unidade_id,
                                               c.data_inicio, c.data_fim, str(c.status_assinatura.value)))
            ids[dom.RENOVACAO][c.id] = _Ids(aluno_id=a.id, contrato_id=c.id)
            ids[dom.TRES_MESES][c.id] = _Ids(aluno_id=a.id, contrato_id=c.id)

    if tipos & {dom.VENCIMENTO, dom.ATRASO}:
        limite = hoje + timedelta(days=1)
        linhas = db.execute(
            select(ContaReceber, Contrato, Aluno)
            .join(Contrato, Contrato.id == ContaReceber.contrato_id).join(Aluno, Aluno.id == ContaReceber.aluno_id)
            .where(Contrato.unidade_id == unidade.id, ContaReceber.status == StatusReceber.ABERTO, ContaReceber.vencimento <= limite)
        ).all()
        tel = _telefones(db, {a.id for _, _, a in linhas})
        for conta, c, a in linhas:
            ca = dom.ContratoAviso(c.id, c.codigo_legado or c.id, _aluno_aviso(a, tel), c.unidade_id, c.data_inicio, c.data_fim,
                                   str(c.status_assinatura.value))
            contas.append(dom.ContaAviso(conta.id, ca, str(conta.status.value), conta.valor, conta.vencimento))
            for t in (dom.VENCIMENTO, dom.ATRASO):
                ids[t][conta.id] = _Ids(aluno_id=a.id, contrato_id=c.id)

    return dom.DadosParaAvisos(reservas, alunos, contratos, contas), ids


# ------------------------------------------------------------------------------------------------ rodada
def _chaves_existentes(db: Session, chaves: list[str]) -> set[str]:
    achadas: set[str] = set()
    for i in range(0, len(chaves), 400):
        achadas.update(db.scalars(select(WhatsappAgendamentoLog.dedupe_key)
                                  .where(WhatsappAgendamentoLog.dedupe_key.in_(chaves[i:i + 400]))))
    return achadas


def avisos_devidos_da_unidade(db: Session, cfg: WhatsappConfig, unidade: Unidade, momento: datetime):
    """(lista de ``AvisoDevido`` já descontando o que já foi registrado, mapas de ids)."""
    config = svc.config_avisos(db, cfg, unidade.nome)
    tipos = set(dom.tipos_a_disparar(momento, config))
    if not tipos:
        return [], {}
    hoje = dom.hora_local(momento).date()
    dados, ids = carregar_dados(db, unidade, hoje, tipos)
    candidatos = dom.avisos_devidos(momento, config, dados, ())
    existentes = _chaves_existentes(db, [a.dedupe_key for a in candidatos])
    return dom.avisos_devidos(momento, config, dados, existentes), ids


def _reservar(db: Session, aviso: dom.AvisoDevido, unidade_id: int, ids: _Ids, status: str, momento: datetime) -> WhatsappAgendamentoLog | None:
    registro = WhatsappAgendamentoLog(
        tipo=aviso.tipo, dedupe_key=aviso.dedupe_key, unidade_id=unidade_id, aluno_id=ids.aluno_id,
        profissional_id=ids.profissional_id, contrato_id=ids.contrato_id, data_referencia=aviso.data_referencia,
        telefone=aviso.telefone, mensagem=aviso.mensagem, status=status, enviado_em=momento)
    db.add(registro)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return registro


def _alerta_unico(db: Session, chave: str, unidade_id: int, hoje: date, status: str, texto: str, momento: datetime) -> bool:
    """Registra (uma vez por chave) um alerta no log. Devolve True se foi o primeiro."""
    registro = WhatsappAgendamentoLog(tipo="alerta", dedupe_key=chave, unidade_id=unidade_id, data_referencia=hoje,
                                      mensagem=texto, status=status, enviado_em=momento)
    db.add(registro)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


def _avisar_gestores_por_email(db: Session, unidade: Unidade, motivo: str) -> None:
    try:
        emails = [e for (e,) in db.execute(select(Usuario.email).join(PerfilAcesso, PerfilAcesso.id == Usuario.perfil_acesso_id)
                                            .where(PerfilAcesso.administrador.is_(True), Usuario.ativo.is_(True)))]
        if emails:
            mail.enviar(emails, "WhatsApp automático parado",
                        f"Os avisos automáticos de WhatsApp da unidade {unidade.nome} foram interrompidos: {motivo}\n"
                        "Reconecte a sessão (ou confira a credencial) em Configurações > Integrações > WhatsApp.", db=db)
    except Exception:  # noqa: BLE001 - o alerta por e-mail é auxiliar
        log.exception("Não foi possível avisar os gestores por e-mail")


def _resumo_ao_gestor(db: Session, cfg: WhatsappConfig, unidade: Unidade, parcial: ResumoRodada, momento: datetime,
                      nome_unidade: str) -> None:
    destino = normalizar_telefone_br(cfg.numero_acompanhamento)
    if not (cfg.acompanhar_envios and destino):
        return
    total = parcial.enviados + parcial.falhas
    if not total:
        return
    texto = (f"Resumo dos avisos automáticos ({nome_unidade}): {parcial.enviados} enviado(s), {parcial.falhas} falha(s), "
             f"{parcial.sem_telefone} sem telefone válido.")
    hoje = dom.hora_local(momento).date()
    chave = f"resumo:{unidade.id}:{hoje.isoformat()}:{dom.hora_local(momento).strftime('%H%M')}"
    if not _alerta_unico(db, chave, unidade.id, hoje, "resumo", texto, momento):
        return
    try:
        res = svc._com_retry(lambda: svc.provedor_da_config(cfg).enviar_texto(destino, texto))
        if not res.ok:
            log.warning("Resumo ao gestor não enviado (%s)", res.erro)
    except Exception:  # noqa: BLE001
        log.exception("Resumo ao gestor falhou")


def processar_unidade(db: Session, cfg: WhatsappConfig, unidade: Unidade, momento: datetime, resumo: ResumoRodada,
                      restante: list[int], primeiro_da_rodada: list[bool]) -> None:
    """Uma unidade. ``restante`` e ``primeiro_da_rodada`` são "caixas" compartilhadas com as outras unidades da rodada."""
    devidos, ids = avisos_devidos_da_unidade(db, cfg, unidade, momento)
    if not devidos:
        return
    hoje = dom.hora_local(momento).date()
    provedor = svc.provedor_da_config(cfg)
    pausa = svc.pausa_segundos(cfg)
    parcial = ResumoRodada()
    for aviso in devidos:
        _ids = ids.get(aviso.tipo, {}).get(aviso.destinatario_id) or _Ids()
        if aviso.situacao == "sem_telefone":
            if _reservar(db, aviso, unidade.id, _ids, "sem_telefone", momento):
                parcial.sem_telefone += 1
            continue
        if aviso.situacao != "enviar":
            continue
        if restante[0] <= 0:
            break
        registro = _reservar(db, aviso, unidade.id, _ids, "pendente", momento)
        if registro is None:  # outro worker (ou outra rodada) já cuidou deste aviso
            continue
        if not primeiro_da_rodada[0] and pausa:
            svc.dormir(pausa)
        primeiro_da_rodada[0] = False
        restante[0] -= 1
        res = svc._com_retry(lambda a=aviso: provedor.enviar_texto(a.telefone, a.mensagem))
        if res.sessao_caiu or res.erro_autenticacao:
            motivo = "a sessão do WhatsApp está desconectada" if res.sessao_caiu else "a credencial foi recusada pelo provedor"
            db.delete(registro)  # volta a ficar devido na próxima rodada
            db.commit()
            resumo.abortadas.append(unidade.id)
            log.warning("Avisos automáticos da unidade %s interrompidos: %s", unidade.id, motivo)
            if _alerta_unico(db, f"parada:{unidade.id}:{hoje.isoformat()}:{'sessao' if res.sessao_caiu else 'credencial'}",
                             unidade.id, hoje, "sessao_caida" if res.sessao_caiu else "credencial_recusada",
                             f"Lote interrompido: {motivo}.", momento):
                _avisar_gestores_por_email(db, unidade, motivo)
            break
        registro.status = "sent" if res.ok else "failed"
        registro.resposta_payload = ((res.resumo or res.erro or "") if res.ok else f"{res.erro or ''} | {res.resumo or ''}")[:1000] or None
        registro.enviado_em = agora()
        if _ids.aluno_id:
            svc._gravar_mensagem(db, _ids.aluno_id, _ids.contrato_id, aviso.tipo, aviso.telefone, aviso.mensagem, res)
        db.commit()
        if res.ok:
            parcial.enviados += 1
            resumo.por_tipo[aviso.tipo] = resumo.por_tipo.get(aviso.tipo, 0) + 1
        else:
            parcial.falhas += 1
    resumo.enviados += parcial.enviados
    resumo.falhas += parcial.falhas
    resumo.sem_telefone += parcial.sem_telefone
    if unidade.id not in resumo.abortadas:
        _resumo_ao_gestor(db, cfg, unidade, parcial, momento, unidade.nome)


def executar_rodada(momento: datetime | None = None, *, max_envios: int = MAX_ENVIOS_POR_RODADA) -> ResumoRodada:
    """Uma rodada do scheduler (chamada a cada 5 min pelo worker). ``momento`` é injetável nos testes."""
    momento = momento or agora()
    resumo = ResumoRodada()
    with SessionLocal() as db:
        if not svc.envio_automatico_ativo(db):
            resumo.desligado = True
            return resumo
        unidades = db.execute(
            select(WhatsappConfig, Unidade).join(Unidade, Unidade.id == WhatsappConfig.unidade_id)
            .where(Unidade.ativo.is_(True), WhatsappConfig.credencial_cifrado.is_not(None)).order_by(Unidade.id)
        ).all()
        restante = [max_envios]
        primeiro = [True]
        for cfg, unidade in unidades:
            if restante[0] <= 0:
                break
            try:
                processar_unidade(db, cfg, unidade, momento, resumo, restante, primeiro)
            except Exception:  # noqa: BLE001 - uma unidade com problema não derruba as outras
                db.rollback()
                log.exception("Falha ao processar avisos da unidade %s", unidade.id)
    return resumo
