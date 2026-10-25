"""Aula avulsa (pacote de N aulas, R12) e aula avaliativa/experimental (TotalPass, WellHub, avaliação).

Decisões (todas listadas em ``docs/progresso-agenda.md``):

- Aula avulsa: UMA reserva e UMA cobrança por aula agendada, SEMPRE no serviço do plano. O antigo criava uma reserva e
  uma cobrança por serviço oferecido no horário (horário com 2 serviços cobrava 2x) — corrigido.
- Valor 0 (TotalPass, WellHub, cortesia) não gera conta a receber (``domain.financeiro.conta_da_aula_avulsa``).
- O total do pacote passa a ser ``valor_aula x quantidade`` (o antigo gravava só o valor de uma aula; DÚVIDA do Jefferson
  em ``docs/progresso-dominio.md``). Troque ``MULTIPLICAR_TOTAL_DO_PACOTE`` para voltar ao comportamento antigo.
- Tudo atômico: validou, agendou ao menos uma aula e gravou; senão nada fica (``ErroAgenda``; quem chama faz rollback).
  Conflitos de data (bloqueio, sem vaga, fora do período) não desfazem as demais aulas do pacote.
- Aula avaliativa: sem cobrança; ficha de avaliação; "converter" só marca CONVERTIDA e NÃO cria contrato
  (# COMPORTAMENTO ANTIGO mantido; o contrato é criado na aba Contratos).
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import agenda as dom_agenda
from app.domain import financeiro as dom_fin
from app.domain import precos
from app.modules.agenda import servico as srv
from app.modules.agenda.models import (
    AulaAvaliativa,
    AulaAvulsa,
    Reserva,
    StatusAvaliativa,
    TipoAvaliativa,
)
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Plano, Profissional, Recorrencia, TipoServico, Unidade
from app.modules.financeiro.models import ContaReceber, StatusReceber

MULTIPLICAR_TOTAL_DO_PACOTE = True
MAX_QUANTIDADE = 60


def _data_fim(plano: Plano, inicio: date, quantidade: int) -> date:
    return precos.data_fim_aula_avulsa(inicio, plano.recorrencia.value, quantidade)


def slots_avulsa(
    db: Session, *, unidade_id: int, plano_id: int, data_inicio: date, quantidade: int
) -> dict:
    """Horários oferecidos para o pacote avulso (só leitura): agrupados por dia da semana, com os professores permitidos."""
    plano = db.get(Plano, plano_id)
    if plano is None or not plano.avulso:
        raise srv.Invalido("Selecione um plano de aula avulsa válido.")
    qtd = max(int(quantidade or 1), 1)
    fim = _data_fim(plano, data_inicio, qtd)
    slots = srv.calcular_slots(db, unidade_id=unidade_id, tipo_servico_id=plano.tipo_servico_id, inicio=data_inicio, fim=fim)
    nomes = {p.id: p.nome for p in db.scalars(select(Profissional))}
    itens = [
        {
            "dia_semana": dia,
            "inicio": f"{ini:%H:%M}",
            "fim": f"{fim_slot:%H:%M}",
            "valor": dom_agenda.valor_do_slot(dia, ini, fim_slot),
            "profissionais": [{"id": p, "nome": nomes.get(p, "")} for p in permitidos],
        }
        for (dia, ini, fim_slot), permitidos in sorted(slots.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]
    return {"data_inicio": data_inicio.isoformat(), "data_fim": fim.isoformat(), "quantidade": qtd, "slots": itens}


def criar_aula_avulsa(
    db: Session,
    *,
    aluno_id: int,
    plano_id: int,
    unidade_id: int,
    profissional_id: int,
    quantidade: int,
    data_inicio: date,
    dia_semana: int,
    hora_inicio: time,
    hora_fim: time | None = None,
    valor_aula: Decimal | str | None = None,
) -> dict:
    if db.get(Aluno, aluno_id) is None:
        raise srv.NaoEncontrado("Aluno não encontrado.")
    plano = db.get(Plano, plano_id)
    if plano is None or not plano.avulso:
        raise srv.Invalido("Selecione um plano de aula avulsa válido.")
    unidade = db.get(Unidade, unidade_id)
    if unidade is None:
        raise srv.Invalido("Unidade inválida.")
    if not profissional_id:
        raise srv.Invalido("Selecione o professor.")
    if db.get(Profissional, profissional_id) is None:
        raise srv.Invalido("Profissional inválido.")
    if not 0 <= dia_semana <= 6:
        raise srv.Invalido("Dia da semana inválido.")
    if not 1 <= int(quantidade or 1) <= MAX_QUANTIDADE:
        raise srv.Invalido(f"A quantidade de aulas deve ficar entre 1 e {MAX_QUANTIDADE}.")
    try:
        informado = None if valor_aula in (None, "") else Decimal(str(valor_aula))
    except InvalidOperation as exc:
        raise srv.Invalido("Valor da aula inválido.") from exc
    if informado is not None and (not informado.is_finite() or informado < 0):
        raise srv.Invalido("Valor da aula inválido.")
    prec = precos.precificar_aula_avulsa(
        plano.valor, quantidade, informado, plano.recorrencia.value, multiplicar_quantidade=MULTIPLICAR_TOTAL_DO_PACOTE
    )
    inicio_pacote = data_inicio
    fim_pacote = _data_fim(plano, inicio_pacote, prec.quantidade)
    if hora_fim is None:
        hora_fim = srv._somar_minutos(inicio_pacote, hora_inicio, dom_agenda.duracao_da_unidade(unidade.duracao_aula_minutos))

    slots = srv.calcular_slots(db, unidade_id=unidade_id, tipo_servico_id=plano.tipo_servico_id, inicio=inicio_pacote, fim=fim_pacote)
    erro = dom_agenda.validar_selecao_nos_slots([dom_agenda.SelecaoHorario(dia_semana, hora_inicio, hora_fim, profissional_id)], slots)
    if erro:
        raise srv.Invalido(erro)

    pacote = AulaAvulsa(
        aluno_id=aluno_id,
        plano_id=plano.id,
        unidade_id=unidade_id,
        profissional_id=profissional_id,
        recorrencia=Recorrencia(prec.recorrencia),
        quantidade=prec.quantidade,
        valor_aula=prec.valor_base,
        valor_total=prec.valor_total,
        data_inicio=inicio_pacote,
        data_fim=fim_pacote,
    )
    db.add(pacote)
    db.flush()

    resultado = srv.ResultadoAgenda()
    todas = dom_agenda.datas_aula_avulsa(inicio_pacote, dia_semana, prec.recorrencia, prec.quantidade, fim_pacote)
    datas = []
    for d in todas:
        if d.fora_do_periodo:
            resultado.conflitos.append(f"Fora do periodo em {d.data} {hora_inicio:%H:%M}")
        else:
            datas.append(d.data)
    contas: list[ContaReceber] = []

    def cobrar(reserva: Reserva, dia: date) -> None:
        # 1 reserva = 1 cobrança (R12). Valor 0/nulo -> sem cobrança.
        cobranca = dom_fin.conta_da_aula_avulsa(prec.valor_base, dia, prec.recorrencia)
        if cobranca is None:
            return
        conta = ContaReceber(
            aluno_id=aluno_id,
            contrato_id=None,
            reserva_id=reserva.id,
            descricao=f"Aula avulsa - {plano.nome} ({dia:%d/%m/%Y})",
            status=StatusReceber.ABERTO,
            valor=cobranca.valor,
            vencimento=cobranca.vencimento,
            competencia=cobranca.competencia,
        )
        db.add(conta)
        db.flush()
        contas.append(conta)

    srv._reservar_datas(
        db,
        resultado,
        aluno_id=aluno_id,
        unidade_id=unidade_id,
        tipo_servico_id=plano.tipo_servico_id,
        profissional_id=profissional_id,
        datas=datas,
        inicio=hora_inicio,
        fim=hora_fim,
        bloqueios=dom_agenda.bloqueios_aplicaveis(srv.carregar_bloqueios(db, unidade_id), None, profissional_id, inicio_pacote, fim_pacote),
        aula_avulsa_id=pacote.id,
        ao_criar=cobrar,
    )
    if not resultado.reservas_criadas and not resultado.ja_existentes:
        raise srv.Conflito(dom_agenda.mensagem_conflitos(resultado.conflitos) if resultado.conflitos else "Nenhuma aula foi agendada.")
    return {"pacote": pacote, "resultado": resultado, "contas": contas}


# --------------------------------------------------------------------------------------------------- avaliativa
def criar_aula_avaliativa(
    db: Session,
    *,
    aluno_id: int,
    unidade_id: int,
    profissional_id: int,
    tipo_servico_id: int,
    data: date,
    hora_inicio: time,
    tipo: TipoAvaliativa | str = TipoAvaliativa.AVALIATIVA,
) -> tuple[AulaAvaliativa, Reserva]:
    """Agenda a aula avaliativa/experimental: cria a ficha, a aula (se preciso) e a reserva, sem cobrança.

    # COMPORTAMENTO ANTIGO (corrigido): sem vaga, o antigo deixava a ficha criada sem reserva ("criada, mas sem vaga").
    Agora é tudo ou nada: sem vaga, nada é gravado e o usuário recebe "N de M vagas ocupadas".
    """
    if db.get(Aluno, aluno_id) is None:
        raise srv.NaoEncontrado("Aluno não encontrado.")
    unidade = db.get(Unidade, unidade_id)
    if unidade is None:
        raise srv.Invalido("Unidade inválida.")
    if db.get(Profissional, profissional_id) is None:
        raise srv.Invalido("Profissional inválido.")
    if db.get(TipoServico, tipo_servico_id) is None:
        raise srv.Invalido("Tipo de serviço inválido.")
    try:
        tipo = TipoAvaliativa(str(tipo).upper())
    except ValueError as exc:
        raise srv.Invalido("Tipo de aula inválido.") from exc
    hora_fim = srv._somar_minutos(data, hora_inicio, dom_agenda.duracao_da_unidade(unidade.duracao_aula_minutos))
    sessao, _ = srv.obter_ou_criar_sessao(
        db,
        unidade_id=unidade_id,
        tipo_servico_id=tipo_servico_id,
        profissional_id=profissional_id,
        data=data,
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
    )
    avaliativa = AulaAvaliativa(
        tipo=tipo,
        aluno_id=aluno_id,
        unidade_id=unidade_id,
        profissional_id=profissional_id,
        tipo_servico_id=tipo_servico_id,
        data=data,
        hora_inicio=hora_inicio,
        hora_fim=sessao.hora_fim,
        status=StatusAvaliativa.AGENDADA,
    )
    db.add(avaliativa)
    db.flush()
    reserva = srv.criar_reserva(db, aluno_id, sessao.id, aula_avaliativa_id=avaliativa.id)
    return avaliativa, reserva


def salvar_ficha_avaliativa(
    db: Session,
    avaliativa_id: int,
    *,
    queixa_principal: str | None = None,
    objetivos: str | None = None,
    historico_saude: str | None = None,
    observacoes: str | None = None,
    status: StatusAvaliativa | str | None = None,
) -> AulaAvaliativa:
    av = db.get(AulaAvaliativa, avaliativa_id)
    if av is None:
        raise srv.NaoEncontrado("Aula avaliativa não encontrada.")
    av.queixa_principal = (queixa_principal or "").strip() or None
    av.objetivos = (objetivos or "").strip() or None
    av.historico_saude = (historico_saude or "").strip() or None
    av.observacoes = (observacoes or "").strip() or None
    if status:
        try:
            av.status = StatusAvaliativa(str(status).upper())
        except ValueError as exc:
            raise srv.Invalido("Status inválido.") from exc
    db.flush()
    return av


def converter_avaliativa(db: Session, avaliativa_id: int) -> AulaAvaliativa:
    """Marca CONVERTIDA. NÃO cria contrato (# COMPORTAMENTO ANTIGO): o contrato é criado na aba Contratos."""
    av = db.get(AulaAvaliativa, avaliativa_id)
    if av is None:
        raise srv.NaoEncontrado("Aula avaliativa não encontrada.")
    av.status = StatusAvaliativa.CONVERTIDA
    db.flush()
    return av


def avaliativa_para_dict(av: AulaAvaliativa) -> dict:
    return {
        "id": av.id,
        "tipo": TipoAvaliativa(av.tipo).value,
        "aluno_id": av.aluno_id,
        "unidade_id": av.unidade_id,
        "profissional_id": av.profissional_id,
        "tipo_servico_id": av.tipo_servico_id,
        "data": av.data.isoformat(),
        "hora_inicio": f"{av.hora_inicio:%H:%M}",
        "hora_fim": f"{av.hora_fim:%H:%M}",
        "status": StatusAvaliativa(av.status).value,
        "queixa_principal": av.queixa_principal,
        "objetivos": av.objetivos,
        "historico_saude": av.historico_saude,
        "observacoes": av.observacoes,
        "contrato_id": av.contrato_id,
    }
