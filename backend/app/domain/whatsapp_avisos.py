"""Avisos automáticos de WhatsApp: QUAIS estão devidos, com que texto e com que chave de deduplicação (R9).

Origem no sistema antigo (``core/whatsapp_scheduler.py``, tarefa que roda a cada 5 minutos):
- ``_run_jobs`` (627-690): para cada unidade, cada aviso dispara se está ligado e ``now.time() >= horário``;
- ``_send_class_reminders`` (240-352), ``_send_professor_schedule`` (355-405), ``_send_contract_renewals`` (408-455),
  ``_send_birthdays`` (505-515), ``_send_payment_due`` (518-536), ``_send_payment_overdue`` (539-562),
  ``_send_three_months`` (565-580), ``_send_aluno_messages`` (463-502);
- ``_log_key`` (95) e ``_already_sent`` (99): chave ``tipo:unidade:data:destinatario`` (UNIQUE);
- ``_render_template`` (36) e ``views._render_whatsapp_template`` (285): UNIFICADAS em ``renderizar_template``;
- ``_is_session_down`` (84), ``_send_with_retry`` (60): regras de execução em lote;
- textos padrão: ``models.WhatsappConfiguracao`` (campos ``template_*``).

Este módulo NÃO envia nada, NÃO lê o relógio e NÃO acessa banco: recebe ``agora``, a configuração da unidade e os dados
já carregados, e devolve a lista de ``AvisoDevido`` (com a situação de cada um). Quem executa (worker) envia com pausa de
5 s, 3 tentativas, interrompe o lote se a sessão cair e grava o log com ``dedupe_key`` UNIQUE.

Diferenças deliberadas em relação ao antigo (todas listadas em docs/progresso-dominio.md):
- telefone: usa a normalização canônica (``telefone.py``) e só CELULAR; o antigo mandava para fixo e para lixo (``"123"``);
- os textos padrão trocam CNPJ/Pix e nome do estúdio fixos por ``{PIX_TIPO}``, ``{PIX_CHAVE}`` e ``{ESTUDIO_NOME}``.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.telefone import normalizar_telefone_br, tipo_telefone

FUSO_NEGOCIO = ZoneInfo("America/Sao_Paulo")

# ---- tipos de aviso (chaves internas) e prefixos de deduplicação do antigo
LEMBRETE_ALUNO = "lembrete_aluno"
AGENDA_PROFESSOR = "agenda_professor"
RENOVACAO = "renovacao"
ANIVERSARIO = "aniversario"
VENCIMENTO = "vencimento"
ATRASO = "atraso"
TRES_MESES = "tres_meses"
TIPOS = (LEMBRETE_ALUNO, AGENDA_PROFESSOR, RENOVACAO, ANIVERSARIO, VENCIMENTO, ATRASO, TRES_MESES)

PREFIXO_DEDUPE = {
    LEMBRETE_ALUNO: "student_reminder",
    AGENDA_PROFESSOR: "professor_schedule",
    RENOVACAO: "contract_renewal",
    ANIVERSARIO: "birthday",
    VENCIMENTO: "payment_due",
    ATRASO: "payment_overdue",
    TRES_MESES: "three_months",
}
#: valor do campo ``tipo`` gravado no log/mensagem do antigo
TIPO_NO_LOG = {
    LEMBRETE_ALUNO: "automated_reminder",
    AGENDA_PROFESSOR: "professor_schedule",
    RENOVACAO: "contract_renewal",
    ANIVERSARIO: "manual",
    VENCIMENTO: "manual",
    ATRASO: "manual",
    TRES_MESES: "manual",
}

STATUS_FORA_DO_LEMBRETE = frozenset({"CANCELADA", "CONCLUIDA", "FALTOU_AVISOU", "FALTOU_SEM_AVISAR"})
STATUS_CONTRATO_ASSINADO = frozenset({"ASSINADO", "ASSINADO_DIGITALMENTE"})
DIAS_RENOVACAO = 7
DIAS_TRES_MESES = 90

#: execução em lote (não é decisão de "devido", mas é regra do R9)
INTERVALO_ENTRE_ENVIOS_SEGUNDOS = 5.0
TENTATIVAS_POR_ENVIO = 3

# ---------------------------------------------------------------------------
# textos
# ---------------------------------------------------------------------------

#: Fallbacks embutidos no código antigo, usados só quando o template da unidade está em branco.
FALLBACK_TEMPLATE = {
    LEMBRETE_ALUNO: "Boa noite {aluno}, amanhã temos aula de {tipo_servico} às {horario}. Podemos confirmar?",
    AGENDA_PROFESSOR: "Resumo de amanhã: {horario} – {alunos}",
    RENOVACAO: "Seu contrato vence em {dias_restantes} dias. Deseja renovar?",
}

#: Textos padrão (valores iniciais da configuração). Variáveis de estúdio: {ESTUDIO_NOME}, {PIX_TIPO}, {PIX_CHAVE}
#: (antes eram texto fixo: "Mayris" e "Chave Pix (CNPJ): 50.732.875/0001-56"). As demais ({aluno}, {data}, ...) são
#: preenchidas por aviso. Variável desconhecida permanece escrita como está (``{xxx}``).
TEXTOS_PADRAO: dict[str, str] = {
    "template_aviso_aluno": "Boa noite {aluno}, amanhã temos aula de {tipo_servico} às {horario}. Podemos confirmar?",
    "template_aviso_professor": "Resumo de amanhã: {horario} – {alunos}",
    "template_link_contrato": "Olá {aluno}, confirme seu contrato pelo link: {link_contrato}",
    "template_aviso_renovacao": "Seu contrato vence em {dias_restantes} dias. Deseja renovar?",
    "template_aniversario": (
        "Feliz Aniversário, {aluno}! 🎉\n"
        "Desejamos um ano cheio de energia boa, leveza, saúde e momentos que façam seu coração sorrir. "
        "Continue se cuidando e honrando seu corpo. É um privilégio te acompanhar nessa jornada. 🎂🎈🙏"
    ),
    "template_fim_contrato": (
        "Olá, {aluno}! Tudo bem? 🌸\n"
        "Seu ciclo atual de Pilates está chegando ao fim e adoraríamos continuar acompanhando sua evolução! "
        "Para o próximo período, o valor do plano passou por um pequeno reajuste e será de R$ {valor}.\n"
        "Podemos confirmar sua renovação e garantir seu horário? Me avise por aqui para prepararmos o novo contrato! ✨"
    ),
    "template_vencimento_proximo": (
        "Olá, {aluno}! Tudo bem? Passando para lembrar que sua mensalidade do Pilates vence em breve, "
        "no dia {data}. Qualquer dúvida, estou à disposição. 🧘‍♀️✨"
    ),
    "template_mensalidade_atraso": (
        "Olá! Tudo bem? Passando para lembrar que o pagamento da sua mensalidade do Pilates "
        "(vencimento em {data}) no valor de R$ {valor} ainda não consta em nosso sistema.\n"
        "Pode ter sido apenas um esquecimento, mas se precisar de algo, estou à disposição! 🧘‍♀️\n"
        "Chave Pix ({PIX_TIPO}): {PIX_CHAVE}\n"
        "Caso o pagamento já tenha sido realizado, por favor, desconsidere esta mensagem."
    ),
    "template_tres_meses": (
        "Olá, {aluno}! Parabéns pelos 3 meses de Pilates! 💪🏻\n"
        "Sente mais força ou mobilidade? Alguma dor reduziu? Alguma nova meta que você gostaria de trabalhar?\n"
        "Os primeiros 90 dias são essenciais para criar consistência, e você está indo muito bem!\n"
        "Obrigada por confiar na {ESTUDIO_NOME} para cuidar de você. Conte sempre comigo!"
    ),
}

#: campo da configuração -> tipo de aviso automático
CAMPO_TEMPLATE_DO_TIPO = {
    LEMBRETE_ALUNO: "template_aviso_aluno",
    AGENDA_PROFESSOR: "template_aviso_professor",
    RENOVACAO: "template_aviso_renovacao",
    ANIVERSARIO: "template_aniversario",
    VENCIMENTO: "template_vencimento_proximo",
    ATRASO: "template_mensalidade_atraso",
    TRES_MESES: "template_tres_meses",
}

#: Horário padrão e liga/desliga padrão de cada aviso (``WhatsappConfiguracao``). Aniversário, vencimento, atraso e
#: 3 meses nascem DESLIGADOS no antigo; lembrete, professor e renovação nascem ligados.
HORARIO_PADRAO = {
    LEMBRETE_ALUNO: time(19, 0), AGENDA_PROFESSOR: time(18, 0), RENOVACAO: time(10, 0), ANIVERSARIO: time(9, 0),
    VENCIMENTO: time(10, 0), ATRASO: time(10, 0), TRES_MESES: time(10, 0),
}
LIGADO_PADRAO = {
    LEMBRETE_ALUNO: True, AGENDA_PROFESSOR: True, RENOVACAO: True, ANIVERSARIO: False, VENCIMENTO: False, ATRASO: False,
    TRES_MESES: False,
}


class _VariaveisAusentes(dict):
    def __missing__(self, chave: str) -> str:
        return "{" + chave + "}"


def renderizar_template(template: str | None, **contexto: Any) -> str:
    """Renderiza ``{variavel}`` de um texto. Unifica ``_render_whatsapp_template`` (views) e ``_render_template`` (scheduler).

    - texto vazio ou só espaços -> ``""``; o resto é ``strip()``ado;
    - ``None`` no contexto vira ``""``; variável ausente permanece ``{nome}``;
    - texto com sintaxe de formato inválida (``{aluno``, ``{0}``, ``{aluno.x}``, ``{valor:.2f}`` com valor ausente...)
      NÃO levanta erro: devolve o texto original (sem renderizar).
    """
    texto = (template or "").strip()
    if not texto:
        return ""
    try:
        return texto.format_map(_VariaveisAusentes({k: "" if v is None else v for k, v in contexto.items()}))
    except Exception:  # noqa: BLE001 - o antigo engole qualquer erro de formatação
        return texto


def template_efetivo(tipo: str, template_da_unidade: str | None) -> str:
    """Template da unidade, ou o fallback embutido (só lembrete, professor e renovação têm), ou ``""``."""
    if template_da_unidade and template_da_unidade.strip():
        return template_da_unidade
    return FALLBACK_TEMPLATE.get(tipo, "")


def linhas_sem_variavel_vazia(texto: str, variaveis: Mapping[str, str | None]) -> str:
    """Remove do texto as linhas que citam uma variável de estúdio SEM valor (ex.: sem ``PIX_CHAVE`` configurada, some a
    linha "Chave Pix (...)": não vai mensagem com ``{PIX_CHAVE}`` literal para o aluno)."""
    ausentes = ["{" + k + "}" for k, v in variaveis.items() if not (v or "").strip()]
    if not ausentes:
        return texto
    return "\n".join(linha for linha in texto.split("\n") if not any(a in linha for a in ausentes))


def chave_dedupe(prefixo: str, unidade_id: int | None, data_referencia: date, destinatario_id: int | None) -> str:
    """``tipo:unidade:data:destinatario`` (``_log_key``). ``None`` vira 0; data em ISO."""
    return f"{prefixo}:{unidade_id or 0}:{data_referencia.isoformat()}:{destinatario_id or 0}"


def segunda_feira_da_semana(dia: date) -> date:
    """Referência semanal do aviso de atraso: segunda-feira da semana de ``dia``."""
    return dia - timedelta(days=dia.weekday())


def chave_dedupe_atraso(unidade_id: int | None, hoje: date, conta_id: int) -> str:
    """Chave do aviso de atraso: UMA vez por semana por conta (data de referência = segunda-feira)."""
    return chave_dedupe(PREFIXO_DEDUPE[ATRASO], unidade_id, segunda_feira_da_semana(hoje), conta_id)


# ---------------------------------------------------------------------------
# dados de entrada
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigAviso:
    ativo: bool
    horario: time
    template: str = ""


@dataclass(frozen=True)
class ConfigAvisos:
    """Configuração de WhatsApp de UMA unidade (``WhatsappConfiguracao``)."""

    unidade_id: int
    unidade_nome: str
    avisos: Mapping[str, ConfigAviso]
    #: variáveis de estúdio disponíveis em todos os textos: ESTUDIO_NOME, PIX_TIPO, PIX_CHAVE
    variaveis_estudio: Mapping[str, str] = field(default_factory=dict)

    def aviso(self, tipo: str) -> ConfigAviso:
        return self.avisos.get(tipo) or ConfigAviso(LIGADO_PADRAO[tipo], HORARIO_PADRAO[tipo], "")


@dataclass(frozen=True)
class AlunoAviso:
    id: int
    nome: str
    telefones: Sequence[str] = ()
    unidade_id: int = 0
    status: str = "ATIVO"
    nascimento: date | None = None
    #: código de negócio (``cdAluno``), usado na ordem do lembrete
    codigo: int = 0


@dataclass(frozen=True)
class ProfissionalAviso:
    id: int
    nome: str
    celular: str | None = None


@dataclass(frozen=True)
class ReservaAviso:
    id: int
    aluno: AlunoAviso
    status: str
    data: date
    hora_inicio: time
    unidade_id: int
    unidade_nome: str = ""
    tipo_servico: str | None = None
    profissional: ProfissionalAviso | None = None


@dataclass(frozen=True)
class ContratoAviso:
    id: int
    numero: int
    aluno: AlunoAviso
    unidade_id: int
    inicio: date
    fim: date
    status: str


@dataclass(frozen=True)
class ContaAviso:
    id: int
    contrato: ContratoAviso | None
    status: str
    valor: Any
    vencimento: date


@dataclass(frozen=True)
class AvisoDevido:
    tipo: str
    dedupe_key: str
    destinatario_id: int
    destinatario_nome: str
    telefone: str | None
    mensagem: str
    data_referencia: date
    #: ``enviar`` | ``sem_telefone`` | ``ja_enviado`` | ``sem_mensagem``
    situacao: str
    contrato_id: int | None = None

    @property
    def tipo_no_log(self) -> str:
        return TIPO_NO_LOG[self.tipo]


# ---------------------------------------------------------------------------
# telefone e situação
# ---------------------------------------------------------------------------

def telefone_para_whatsapp(telefones: Iterable[str | None]) -> str | None:
    """Primeiro telefone que seja CELULAR brasileiro válido, já no formato ``55DDD9XXXXXXXX``.

    # COMPORTAMENTO ANTIGO (corrigido): ``get_aluno_phone`` devolvia o primeiro número "limpo" mesmo se fosse fixo,
    incompleto (``"123"``) ou sem DDD; a mensagem era "enviada" a um destino impossível e ainda gravada como entregue.
    """
    for tel in telefones:
        canonico = normalizar_telefone_br(tel)
        if canonico and tipo_telefone(canonico) == "celular":
            return canonico
    return None


def formatar_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def formatar_valor(valor: Any) -> str:
    """``_fmt_valor``: ``300`` -> ``"300,00"``; inválido -> ``""``."""
    try:
        return f"{float(valor):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# quando disparar
# ---------------------------------------------------------------------------

def hora_local(agora: datetime) -> datetime:
    return agora.astimezone(FUSO_NEGOCIO) if agora.tzinfo else agora.replace(tzinfo=FUSO_NEGOCIO)


def horario_atingido(agora: datetime, horario: time) -> bool:
    """``now.time() >= horário`` em Brasília. O aviso fica "devido" de ``horário`` até 23:59; a deduplicação impede o
    reenvio nas rodadas seguintes de 5 minutos."""
    return hora_local(agora).time() >= horario


def tipos_a_disparar(agora: datetime, config: ConfigAvisos) -> list[str]:
    """Tipos cujo liga/desliga está ativo e cujo horário já passou, na ordem de ``_run_jobs``."""
    return [t for t in TIPOS if config.aviso(t).ativo and horario_atingido(agora, config.aviso(t).horario)]


# ---------------------------------------------------------------------------
# cada aviso
# ---------------------------------------------------------------------------

def _contexto_base(config: ConfigAvisos, extra: Mapping[str, Any]) -> dict[str, Any]:
    return {**config.variaveis_estudio, **extra}


def _renderizar(config: ConfigAvisos, tipo: str, extra: Mapping[str, Any]) -> str:
    template = template_efetivo(tipo, config.aviso(tipo).template)
    template = linhas_sem_variavel_vazia(template, {k: v for k, v in config.variaveis_estudio.items() if k == "PIX_CHAVE"})
    return renderizar_template(template, **_contexto_base(config, extra))


def _hhmm(h: time) -> str:
    return h.strftime("%H:%M")


def _formatar_aulas(reservas: Sequence[ReservaAviso]) -> str:
    linhas = []
    for r in reservas:
        linha = f"{_hhmm(r.hora_inicio)} - {r.tipo_servico or 'Aula'}"
        if r.unidade_nome:
            linha += f" - {r.unidade_nome}"
        linhas.append(linha)
    return "\n".join(linhas)


def avisos_lembrete_aula(
    config: ConfigAvisos, hoje: date, reservas: Iterable[ReservaAviso], ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Lembrete de aula de AMANHÃ, UMA mensagem por aluno (agrupa as aulas do dia).

    Entram reservas da unidade, de amanhã, fora de CANCELADA/CONCLUIDA/FALTOU_*  (RESERVADA e PENDENTE entram). Ordem:
    código do aluno, depois horário. Variáveis: ``aluno``, ``unidade``, ``data``, ``horario`` e ``tipo_servico`` (da
    PRIMEIRA aula), ``aulas`` e ``horarios`` (todas, uma por linha).
    """
    alvo = hoje + timedelta(days=1)
    elegiveis = sorted(
        (r for r in reservas if r.data == alvo and r.unidade_id == config.unidade_id and r.status not in STATUS_FORA_DO_LEMBRETE),
        key=lambda r: (r.aluno.codigo, r.hora_inicio, r.id),
    )
    grupos: dict[int, list[ReservaAviso]] = {}
    for r in elegiveis:
        grupos.setdefault(r.aluno.id, []).append(r)
    avisos = []
    for aluno_id, grupo in grupos.items():
        aluno, primeira = grupo[0].aluno, grupo[0]
        aulas = _formatar_aulas(grupo)
        mensagem = _renderizar(config, LEMBRETE_ALUNO, dict(
            aluno=aluno.nome, unidade=config.unidade_nome, data=formatar_data(alvo), horario=_hhmm(primeira.hora_inicio),
            tipo_servico=primeira.tipo_servico or "Pilates", aulas=aulas, horarios=aulas,
        ))
        chave = chave_dedupe(PREFIXO_DEDUPE[LEMBRETE_ALUNO], config.unidade_id, alvo, aluno_id)
        telefone = telefone_para_whatsapp(aluno.telefones)
        avisos.append(AvisoDevido(LEMBRETE_ALUNO, chave, aluno_id, aluno.nome, telefone, mensagem, alvo,
                                  _situacao_lembrete(telefone, chave, ja_enviados)))
    return avisos


def _situacao_lembrete(telefone: str | None, chave: str, ja_enviados: Collection[str]) -> str:
    """No lembrete o antigo checa "já enviado" ANTES de "sem telefone" (e nunca pula por mensagem vazia: tem fallback)."""
    if chave in ja_enviados:
        return "ja_enviado"
    return "enviar" if telefone else "sem_telefone"


def _situacao_telefone_primeiro(telefone: str | None, chave: str, ja_enviados: Collection[str]) -> str:
    """Professor e renovação: o antigo checa o telefone ANTES do "já enviado" (o resultado, não enviar, é o mesmo)."""
    if not telefone:
        return "sem_telefone"
    return "ja_enviado" if chave in ja_enviados else "enviar"


def avisos_agenda_professor(
    config: ConfigAvisos, hoje: date, reservas: Iterable[ReservaAviso], ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Agenda de AMANHÃ para cada professor: só reservas ``RESERVADA`` com professor, na unidade. Uma mensagem por professor.

    Variáveis: ``data``, ``unidade``, ``horario`` e ``alunos`` (as DUAS com o mesmo texto: uma linha
    ``"HH:MM - Aluno - Serviço"`` por aula; o texto padrão usa as duas e por isso a lista aparece repetida).
    Professor sem celular é ignorado em silêncio (``situacao="sem_telefone"``).
    """
    alvo = hoje + timedelta(days=1)
    elegiveis = sorted(
        (r for r in reservas if r.data == alvo and r.unidade_id == config.unidade_id and r.status == "RESERVADA" and r.profissional),
        key=lambda r: (r.profissional.id, r.hora_inicio, r.id),
    )
    grupos: dict[int, list[ReservaAviso]] = {}
    for r in elegiveis:
        grupos.setdefault(r.profissional.id, []).append(r)
    avisos = []
    for prof_id, grupo in grupos.items():
        prof = grupo[0].profissional
        agenda = "\n".join(f"{_hhmm(r.hora_inicio)} - {r.aluno.nome} - {r.tipo_servico or 'Aula'}" for r in grupo)
        mensagem = _renderizar(config, AGENDA_PROFESSOR, dict(
            data=formatar_data(alvo), unidade=config.unidade_nome, horario=agenda, alunos=agenda))
        chave = chave_dedupe(PREFIXO_DEDUPE[AGENDA_PROFESSOR], config.unidade_id, alvo, prof_id)
        telefone = telefone_para_whatsapp([prof.celular])
        avisos.append(AvisoDevido(AGENDA_PROFESSOR, chave, prof_id, prof.nome, telefone, mensagem, alvo,
                                  _situacao_telefone_primeiro(telefone, chave, ja_enviados)))
    return avisos


def avisos_renovacao(
    config: ConfigAvisos, hoje: date, contratos: Iterable[ContratoAviso], ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Contratos ASSINADOS (ou assinados digitalmente) que terminam em exatamente 7 dias. Referência = a data do fim.

    Variáveis: ``aluno``, ``contrato`` (número), ``unidade``, ``dias_restantes`` (sempre 7) e ``vencimento`` (fim, dd/mm/aaaa).
    """
    alvo = hoje + timedelta(days=DIAS_RENOVACAO)
    avisos = []
    for c in sorted((c for c in contratos if c.unidade_id == config.unidade_id and c.fim == alvo and c.status in STATUS_CONTRATO_ASSINADO), key=lambda c: c.numero):
        telefone = telefone_para_whatsapp(c.aluno.telefones)
        chave = chave_dedupe(PREFIXO_DEDUPE[RENOVACAO], config.unidade_id, alvo, c.id)
        mensagem = _renderizar(config, RENOVACAO, dict(
            aluno=c.aluno.nome, contrato=c.numero, unidade=config.unidade_nome, dias_restantes=DIAS_RENOVACAO, vencimento=formatar_data(c.fim)))
        avisos.append(AvisoDevido(RENOVACAO, chave, c.id, c.aluno.nome, telefone, mensagem, alvo,
                                  _situacao_telefone_primeiro(telefone, chave, ja_enviados), contrato_id=c.id))
    return avisos


def _simples(
    config: ConfigAvisos, tipo: str, destinatarios: Iterable[tuple[int, AlunoAviso, Mapping[str, Any], ContratoAviso | None]],
    data_referencia: date, ja_enviados: Collection[str],
) -> list[AvisoDevido]:
    """``_send_aluno_messages``: sem telefone pula; ``já enviado`` pula; mensagem vazia (template em branco, sem fallback) pula."""
    avisos = []
    for dedup_id, aluno, contexto, contrato in destinatarios:
        telefone = telefone_para_whatsapp(aluno.telefones)
        chave = chave_dedupe(PREFIXO_DEDUPE[tipo], config.unidade_id, data_referencia, dedup_id)
        mensagem = _renderizar(config, tipo, dict(aluno=aluno.nome, **contexto))
        if not telefone:
            situacao = "sem_telefone"
        elif chave in ja_enviados:
            situacao = "ja_enviado"
        elif not mensagem:
            situacao = "sem_mensagem"
        else:
            situacao = "enviar"
        avisos.append(AvisoDevido(tipo, chave, dedup_id, aluno.nome, telefone, mensagem, data_referencia, situacao,
                                  contrato_id=contrato.id if contrato else None))
    return avisos


def avisos_aniversario(
    config: ConfigAvisos, hoje: date, alunos: Iterable[AlunoAviso], ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Alunos ATIVOS da unidade que fazem aniversário hoje (mesmo dia e mês).

    # COMPORTAMENTO ANTIGO: quem nasceu em 29/02 só recebe nos anos bissextos.
    """
    dest = [(a.id, a, {}, None) for a in alunos
            if a.unidade_id == config.unidade_id and a.status == "ATIVO" and a.nascimento
            and (a.nascimento.month, a.nascimento.day) == (hoje.month, hoje.day)]
    return _simples(config, ANIVERSARIO, dest, hoje, ja_enviados)


def avisos_vencimento(
    config: ConfigAvisos, hoje: date, contas: Iterable[ContaAviso], ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Contas com status exatamente ``ABERTO`` que vencem AMANHÃ, de contratos da unidade. Referência = data do vencimento.

    Variáveis: ``aluno``, ``valor`` (``300,00``) e ``data`` (vencimento).
    """
    alvo = hoje + timedelta(days=1)
    dest = [(c.id, c.contrato.aluno, {"valor": formatar_valor(c.valor), "data": formatar_data(c.vencimento)}, c.contrato)
            for c in sorted(contas, key=lambda c: c.id)
            if c.contrato and c.contrato.unidade_id == config.unidade_id and c.status == "ABERTO" and c.vencimento == alvo]
    return _simples(config, VENCIMENTO, dest, alvo, ja_enviados)


def avisos_atraso(
    config: ConfigAvisos, hoje: date, contas: Iterable[ContaAviso], ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Contas ``ABERTO``/``ATRASADO`` vencidas (``vencimento < hoje``), de contratos da unidade, UMA vez por semana.

    A referência da chave é a segunda-feira da semana. Uma mensagem POR CONTA: aluno com 3 faturas vencidas recebe 3.

    # COMPORTAMENTO ANTIGO: sem limite de tempo nem de quantidade (uma fatura vencida há 2 anos continua gerando
    mensagem toda semana). Ver sugestão em docs/progresso-dominio.md.
    """
    referencia = segunda_feira_da_semana(hoje)
    dest = [(c.id, c.contrato.aluno, {"valor": formatar_valor(c.valor), "data": formatar_data(c.vencimento)}, c.contrato)
            for c in sorted(contas, key=lambda c: c.id)
            if c.contrato and c.contrato.unidade_id == config.unidade_id and c.status in ("ABERTO", "ATRASADO") and c.vencimento < hoje]
    return _simples(config, ATRASO, dest, referencia, ja_enviados)


def avisos_tres_meses(
    config: ConfigAvisos, hoje: date, contratos: Iterable[ContratoAviso], ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Contratos ASSINADOS que começaram há EXATAMENTE 90 dias. Referência = a data de início."""
    alvo = hoje - timedelta(days=DIAS_TRES_MESES)
    dest = [(c.id, c.aluno, {}, c) for c in contratos
            if c.unidade_id == config.unidade_id and c.inicio == alvo and c.status in STATUS_CONTRATO_ASSINADO]
    return _simples(config, TRES_MESES, dest, alvo, ja_enviados)


@dataclass
class DadosParaAvisos:
    """Tudo que o worker carrega do banco para decidir os avisos (já filtrado por unidade ou não; o módulo refiltra)."""

    reservas: Sequence[ReservaAviso] = ()
    alunos: Sequence[AlunoAviso] = ()
    contratos: Sequence[ContratoAviso] = ()
    contas: Sequence[ContaAviso] = ()


def avisos_devidos(
    agora: datetime, config: ConfigAvisos, dados: DadosParaAvisos, ja_enviados: Collection[str] = ()
) -> list[AvisoDevido]:
    """Todos os avisos da unidade que estão devidos NESTE momento (horário atingido e liga/desliga ativo), na ordem de
    ``_run_jobs``. Inclui os que serão pulados (``situacao`` diferente de ``enviar``) para o worker registrar o motivo."""
    hoje = hora_local(agora).date()
    avisos: list[AvisoDevido] = []
    ativos = set(tipos_a_disparar(agora, config))
    if LEMBRETE_ALUNO in ativos:
        avisos += avisos_lembrete_aula(config, hoje, dados.reservas, ja_enviados)
    if AGENDA_PROFESSOR in ativos:
        avisos += avisos_agenda_professor(config, hoje, dados.reservas, ja_enviados)
    if RENOVACAO in ativos:
        avisos += avisos_renovacao(config, hoje, dados.contratos, ja_enviados)
    if ANIVERSARIO in ativos:
        avisos += avisos_aniversario(config, hoje, dados.alunos, ja_enviados)
    if VENCIMENTO in ativos:
        avisos += avisos_vencimento(config, hoje, dados.contas, ja_enviados)
    if ATRASO in ativos:
        avisos += avisos_atraso(config, hoje, dados.contas, ja_enviados)
    if TRES_MESES in ativos:
        avisos += avisos_tres_meses(config, hoje, dados.contratos, ja_enviados)
    return avisos


# ---------------------------------------------------------------------------
# execução em lote (regras do R9 que o worker aplica)
# ---------------------------------------------------------------------------

def sessao_do_whatsapp_caiu(resposta: Any) -> bool:
    """``_is_session_down``: resposta da WasenderAPI indicando sessão desconectada => abortar o lote."""
    if not isinstance(resposta, dict):
        return False
    texto = str(resposta.get("error") or "")
    interno = resposta.get("response")
    if isinstance(interno, dict):
        texto += " " + str(interno.get("message") or "")
    texto = texto.lower()
    return "not connected" in texto or ("session" in texto and "connect" in texto)


def envio_deu_certo(resposta: Any) -> bool:
    """``_send_with_retry``: sucesso = dict sem a chave ``error``."""
    return isinstance(resposta, dict) and "error" not in resposta


def proxima_pausa_de_retry(resposta: Any, pausa_atual: float) -> float:
    """Pausa antes da próxima tentativa: a atual, ou o ``retry_after`` informado pela API se for maior
    (procurado na resposta e em ``resposta["response"]``)."""
    retry_after = None
    if isinstance(resposta, dict):
        retry_after = resposta.get("retry_after")
        if retry_after is None and isinstance(resposta.get("response"), dict):
            retry_after = resposta["response"].get("retry_after")
    if retry_after is not None:
        try:
            return max(float(retry_after), pausa_atual)
        except (TypeError, ValueError):
            return pausa_atual
    return pausa_atual

