"""Serviço de WhatsApp: configuração por unidade, envio a aluno (texto/documento), cobrança, enviador de contrato/termo
e o ``Notificador`` real do core (código de senha e OTP do app do aluno).

Pontos de extensão que este módulo REGISTRA (ver ``registrar_tudo``, chamado por ``routes.py`` na importação):
- ``financeiro.servico.definir_cobrador`` -> ``cobrar_conta``;
- ``core.notificador.definir_notificador`` -> ``NotificadorWhatsapp``;
- ``registrar_enviador()`` -> ``EnviadorWhatsapp`` (o coordenador liga ao envio de contrato/termo).

Segredos: a credencial fica cifrada em ``whatsapp_config.credencial_cifrado`` (Fernet), é decifrada só aqui, na hora do
envio, e NUNCA aparece em log, resposta, auditoria nem em ``resposta_payload``.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import notificador as notif
from app.core import segredos
from app.core.db import SessionLocal, agora
from app.core.models import Identidade
from app.domain import whatsapp_avisos as dom
from app.domain.telefone import normalizar_telefone_br, tipo_telefone
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.alunos.models import Aluno, AlunoTelefone, DirecaoMensagem, WhatsappMensagem
from app.modules.cadastros.models import Profissional, TipoServico, Unidade
from app.modules.comunicacao import provedores as prov
from app.modules.comunicacao.models import ComunicacaoParametro
from app.modules.financeiro.models import ContaReceber
from app.modules.financeiro.servico import ErroDeNegocio
from app.modules.integracoes.models import ProvedorWhatsapp, WhatsappConfig

log = logging.getLogger(__name__)

PARAM_ENVIO_AUTOMATICO = "envio_automatico_ativo"
PAUSA_PADRAO_S = int(dom.INTERVALO_ENTRE_ENVIOS_SEGUNDOS)
PAUSA_MAX_S = 120

#: campo ``avisar_*`` / ``horario_aviso_*`` da configuração por tipo de aviso
CAMPO_ATIVO = {
    dom.LEMBRETE_ALUNO: "avisar_aluno", dom.AGENDA_PROFESSOR: "avisar_professor", dom.RENOVACAO: "avisar_renovacao",
    dom.ANIVERSARIO: "avisar_aniversario", dom.VENCIMENTO: "avisar_vencimento", dom.ATRASO: "avisar_atraso",
    dom.TRES_MESES: "avisar_tres_meses",
}
CAMPO_HORARIO = {
    dom.LEMBRETE_ALUNO: "horario_aviso_aluno", dom.AGENDA_PROFESSOR: "horario_aviso_professor",
    dom.RENOVACAO: "horario_aviso_renovacao", dom.ANIVERSARIO: "horario_aviso_aniversario",
    dom.VENCIMENTO: "horario_aviso_vencimento", dom.ATRASO: "horario_aviso_atraso", dom.TRES_MESES: "horario_aviso_tres_meses",
}
CAMPOS_TEXTO = tuple(dom.TEXTOS_PADRAO)  # os 8 textos editáveis

#: variáveis disponíveis em cada texto (documentadas na tela)
VARIAVEIS_ESTUDIO = ("ESTUDIO_NOME", "PIX_TIPO", "PIX_CHAVE")
VARIAVEIS_DO_TEXTO: dict[str, list[str]] = {
    "template_aviso_aluno": ["aluno", "unidade", "data", "horario", "tipo_servico", "aulas", "horarios"],
    "template_aviso_professor": ["data", "unidade", "horario", "alunos"],
    "template_link_contrato": ["aluno", "link_contrato"],
    "template_aviso_renovacao": ["aluno", "contrato", "unidade", "dias_restantes", "vencimento"],
    "template_aniversario": ["aluno"],
    "template_fim_contrato": ["aluno", "valor"],
    "template_vencimento_proximo": ["aluno", "valor", "data"],
    "template_mensalidade_atraso": ["aluno", "valor", "data"],
    "template_tres_meses": ["aluno"],
}


def dormir(segundos: float) -> None:
    """Pausa entre tentativas/envios. Os testes substituem esta função (nunca esperam de verdade)."""
    time.sleep(segundos)


# ------------------------------------------------------------------------------------------------ parâmetros de ambiente
def parametro(db: Session, chave: str, padrao: str | None = None) -> str | None:
    p = db.get(ComunicacaoParametro, chave)
    return p.valor if p and p.valor is not None else padrao


def definir_parametro(db: Session, chave: str, valor: str) -> None:
    p = db.get(ComunicacaoParametro, chave)
    if p:
        p.valor = valor
    else:
        db.add(ComunicacaoParametro(chave=chave, valor=valor))
    db.flush()


def envio_automatico_ativo(db: Session) -> bool:
    """Chave geral do AMBIENTE. Nasce DESLIGADA: só o Full liga (evita mensagem em dobro enquanto o sistema antigo
    ainda está em produção). Desligada, o scheduler não envia NADA (envios manuais continuam funcionando)."""
    return parametro(db, PARAM_ENVIO_AUTOMATICO, "0") == "1"


# ------------------------------------------------------------------------------------------------ configuração
def obter_config(db: Session, unidade_id: int, *, criar: bool = False) -> WhatsappConfig | None:
    cfg = db.scalar(select(WhatsappConfig).where(WhatsappConfig.unidade_id == unidade_id))
    if cfg or not criar:
        return cfg
    # nasce com TODOS os avisos desligados e os textos padrão (decisão: nada dispara sem o Full ligar)
    cfg = WhatsappConfig(
        unidade_id=unidade_id, provedor=ProvedorWhatsapp.wasender,
        **{campo: False for campo in CAMPO_ATIVO.values()}, enviar_link_contrato=False, avisar_fim_contrato=False,
        **dict(dom.TEXTOS_PADRAO),
    )
    db.add(cfg)
    db.flush()
    return cfg


def extras(cfg: WhatsappConfig) -> dict[str, Any]:
    """``variaveis_template`` (JSON): guarda PIX_TIPO, PIX_CHAVE e pausa_segundos sem mexer no esquema da tabela."""
    return dict(cfg.variaveis_template) if isinstance(cfg.variaveis_template, dict) else {}


def pausa_segundos(cfg: WhatsappConfig | None) -> int:
    if cfg is None:
        return PAUSA_PADRAO_S
    try:
        return max(0, min(PAUSA_MAX_S, int(extras(cfg).get("pausa_segundos", PAUSA_PADRAO_S))))
    except (TypeError, ValueError):
        return PAUSA_PADRAO_S


def variaveis_estudio(db: Session, cfg: WhatsappConfig | None) -> dict[str, str]:
    ident = db.get(Identidade, 1)
    ex = extras(cfg) if cfg else {}
    return {
        "ESTUDIO_NOME": (ident.nome_exibicao if ident else "") or "",
        "PIX_TIPO": str(ex.get("PIX_TIPO") or ""),
        "PIX_CHAVE": str(ex.get("PIX_CHAVE") or ""),
    }


def config_avisos(db: Session, cfg: WhatsappConfig, unidade_nome: str) -> dom.ConfigAvisos:
    """Converte a configuração do banco no que o ``domain.whatsapp_avisos`` espera."""
    avisos = {}
    for tipo in dom.TIPOS:
        campo_texto = dom.CAMPO_TEMPLATE_DO_TIPO[tipo]
        texto = getattr(cfg, campo_texto)
        if texto is None:
            texto = dom.TEXTOS_PADRAO[campo_texto]
        avisos[tipo] = dom.ConfigAviso(bool(getattr(cfg, CAMPO_ATIVO[tipo])), getattr(cfg, CAMPO_HORARIO[tipo]), texto)
    return dom.ConfigAvisos(cfg.unidade_id, unidade_nome, avisos, variaveis_estudio(db, cfg))


def texto_do_campo(cfg: WhatsappConfig | None, campo: str) -> str:
    valor = getattr(cfg, campo, None) if cfg else None
    return dom.TEXTOS_PADRAO[campo] if valor is None else valor


def renderizar_campo(db: Session, cfg: WhatsappConfig | None, campo: str, **contexto: Any) -> str:
    """Renderiza um dos textos da configuração (variáveis do estúdio + as do contexto; some a linha do Pix se não há chave)."""
    estudio = variaveis_estudio(db, cfg)
    texto = dom.linhas_sem_variavel_vazia(texto_do_campo(cfg, campo), {"PIX_CHAVE": estudio["PIX_CHAVE"]})
    return dom.renderizar_template(texto, **{**estudio, **contexto})


def renderizar_livre(db: Session, cfg: WhatsappConfig | None, texto: str, **contexto: Any) -> str:
    """Texto digitado pelo usuário (comunicado, aviso ao aluno): variáveis do estúdio + contexto."""
    return dom.renderizar_template(texto, **{**variaveis_estudio(db, cfg), **contexto})


# ------------------------------------------------------------------------------------------------ provedor
@dataclass
class DadosProvedor:
    provedor: str
    url: str | None
    credencial: str | None
    instancia: str | None
    unidade_id: int | None = None


def dados_do_provedor(cfg: WhatsappConfig) -> DadosProvedor:
    credencial = None
    if cfg.credencial_cifrado:
        try:
            credencial = segredos.decifrar_texto(cfg.credencial_cifrado.encode())
        except segredos.SegredoInvalido:
            log.error("Credencial de WhatsApp ilegível (MASTER_KEY diferente) na unidade %s", cfg.unidade_id)
    return DadosProvedor(str(cfg.provedor.value if hasattr(cfg.provedor, "value") else cfg.provedor), cfg.url_api,
                         credencial, cfg.instancia, cfg.unidade_id)


def _fabrica_padrao(d: DadosProvedor) -> prov.Provedor:
    return prov.criar_provedor(d.provedor, d.url, d.credencial, d.instancia)


_fabrica: Callable[[DadosProvedor], prov.Provedor] = _fabrica_padrao


def definir_fabrica_provedor(fn: Callable[[DadosProvedor], prov.Provedor] | None) -> None:
    """Troca a fábrica de provedores (testes injetam um falso / transporte HTTP falso). ``None`` volta ao padrão."""
    global _fabrica
    _fabrica = fn or _fabrica_padrao


def provedor_da_config(cfg: WhatsappConfig) -> prov.Provedor:
    return _fabrica(dados_do_provedor(cfg))


def provedor_da_unidade(db: Session, unidade_id: int) -> prov.Provedor:
    cfg = obter_config(db, unidade_id)
    if not cfg or not cfg.credencial_cifrado:
        raise ErroDeNegocio("O WhatsApp desta unidade ainda não foi configurado (Configurações > Integrações > WhatsApp).", 409)
    return provedor_da_config(cfg)


# ------------------------------------------------------------------------------------------------ telefones e mensagens
def telefones_do_aluno(db: Session, aluno_id: int) -> list[str]:
    return list(db.scalars(select(AlunoTelefone.numero).where(AlunoTelefone.aluno_id == aluno_id)
                           .order_by(AlunoTelefone.ordem, AlunoTelefone.id)))


def celular_do_aluno(db: Session, aluno_id: int) -> str | None:
    return dom.telefone_para_whatsapp(telefones_do_aluno(db, aluno_id))


@dataclass
class ResultadoEnvio:
    ok: bool
    status: str  # sent | failed | sem_telefone
    erro: str | None = None
    sessao_caiu: bool = False
    telefone: str | None = None
    mensagem_id: int | None = None
    erro_autenticacao: bool = False


def _gravar_mensagem(db: Session, aluno_id: int, contrato_id: int | None, tipo: str, telefone: str | None, texto: str,
                     res: prov.Resultado) -> WhatsappMensagem:
    detalhe = res.resumo or (res.erro or "")
    if not res.ok and res.erro and res.erro not in detalhe:
        detalhe = f"{res.erro} | {detalhe}"
    m = WhatsappMensagem(aluno_id=aluno_id, contrato_id=contrato_id, tipo=tipo[:30], direcao=DirecaoMensagem.enviada,
                         telefone=telefone, mensagem=texto, status="sent" if res.ok else "failed",
                         resposta_payload=detalhe[:1000] or None, enviado_em=agora())
    db.add(m)
    db.flush()
    return m


def _com_retry(acao: Callable[[], prov.Resultado], pausa_retry_s: float | None = None) -> prov.Resultado:
    return prov.enviar_com_retry(acao, pausa_s=prov.PAUSA_RETRY_S if pausa_retry_s is None else pausa_retry_s,
                                 dormir=lambda s: dormir(s))


def enviar_texto_aluno(db: Session, aluno: Aluno, texto: str, *, tipo: str = "manual", contrato_id: int | None = None,
                       provedor: prov.Provedor | None = None) -> ResultadoEnvio:
    """Envia ``texto`` ao celular do aluno e grava ``whatsapp_mensagem``. Não faz commit (quem chama decide).

    Telefone inválido/fixo ou ausente NÃO é tentado: devolve ``status="sem_telefone"`` e nada é gravado.
    """
    texto = (texto or "").strip()
    if not texto:
        raise ErroDeNegocio("A mensagem está vazia.", 422)
    telefone = celular_do_aluno(db, aluno.id)
    if not telefone:
        return ResultadoEnvio(False, "sem_telefone", "O aluno não tem um celular válido cadastrado.")
    p = provedor or provedor_da_unidade(db, aluno.unidade_id)
    res = _com_retry(lambda: p.enviar_texto(telefone, texto))
    m = _gravar_mensagem(db, aluno.id, contrato_id, tipo, telefone, texto, res)
    return ResultadoEnvio(res.ok, m.status, res.erro, res.sessao_caiu, telefone, m.id, res.erro_autenticacao)


def enviar_documento_por_url(db: Session, aluno: Aluno, url: str, nome_arquivo: str, legenda: str = "", *,
                             tipo: str = "contract_pdf", contrato_id: int | None = None,
                             provedor: prov.Provedor | None = None) -> ResultadoEnvio:
    """Envia um documento (PDF) por URL (link assinado com prazo) e grava ``whatsapp_mensagem``. Sem commit."""
    telefone = celular_do_aluno(db, aluno.id)
    if not telefone:
        return ResultadoEnvio(False, "sem_telefone", "O aluno não tem um celular válido cadastrado.")
    p = provedor or provedor_da_unidade(db, aluno.unidade_id)
    res = _com_retry(lambda: p.enviar_documento(telefone, url, nome_arquivo, legenda))
    # o histórico guarda a legenda (e o nome do arquivo), nunca a URL assinada (é um acesso temporário ao documento)
    texto = (legenda or "").strip() or f"[documento] {nome_arquivo}"
    m = _gravar_mensagem(db, aluno.id, contrato_id, tipo, telefone, texto, res)
    return ResultadoEnvio(res.ok, m.status, res.erro, res.sessao_caiu, telefone, m.id, res.erro_autenticacao)


def exigir_envio(res: ResultadoEnvio) -> ResultadoEnvio:
    """Para rotas/serviços que precisam de sucesso: traduz a falha em ``ErroDeNegocio`` com mensagem clara."""
    if res.ok:
        return res
    if res.status == "sem_telefone":
        raise ErroDeNegocio(res.erro or "O aluno não tem celular válido.", 422)
    if res.erro_autenticacao:
        raise ErroDeNegocio("O provedor recusou a credencial do WhatsApp. Confira o token em Configurações > Integrações.", 502)
    if res.sessao_caiu:
        raise ErroDeNegocio("A sessão do WhatsApp está desconectada. Reconecte no painel do provedor e tente de novo.", 502)
    raise ErroDeNegocio(f"Não foi possível enviar a mensagem: {res.erro or 'falha desconhecida'}", 502)


# ------------------------------------------------------------------------------------------------ textos para o aluno
def texto_para_aluno(db: Session, aluno: Aluno, texto: str) -> str:
    """Aviso ao aluno / comunicado: variáveis ``{aluno}`` e ``{unidade}`` (+ ESTUDIO_NOME, PIX_*)."""
    unidade = db.get(Unidade, aluno.unidade_id)
    cfg = obter_config(db, aluno.unidade_id)
    return renderizar_livre(db, cfg, texto, aluno=aluno.nome, unidade=unidade.nome if unidade else "")


# ------------------------------------------------------------------------------------------------ cobrança
def cobrar_conta(db: Session, conta: ContaReceber, aluno: Aluno) -> str:
    """Cobrador registrado no financeiro. Vencida -> texto de atraso; a vencer -> texto de vencimento."""
    from app.modules.financeiro.servico import hoje_de_negocio_agora

    cfg = obter_config(db, aluno.unidade_id)
    campo = "template_mensalidade_atraso" if conta.vencimento < hoje_de_negocio_agora() else "template_vencimento_proximo"
    mensagem = renderizar_campo(db, cfg, campo, aluno=aluno.nome, valor=dom.formatar_valor(conta.valor),
                                data=dom.formatar_data(conta.vencimento))
    if not mensagem:
        raise ErroDeNegocio("O texto de cobrança está em branco (Configurações > Integrações > WhatsApp).", 422)
    exigir_envio(enviar_texto_aluno(db, aluno, mensagem, tipo="cobranca"))
    return mensagem


# ------------------------------------------------------------------------------------------------ "Enviar agora" (painel)
def montar_lembrete_da_reserva(db: Session, reserva_id: int) -> tuple[Aluno, str]:
    """Texto do lembrete de aula para o aluno da reserva (mesmo texto/regra do aviso automático, com todas as aulas dele no dia)."""
    r = db.get(Reserva, reserva_id)
    if not r:
        raise ErroDeNegocio("Reserva não encontrada.", 404)
    sessao = db.get(AulaSessao, r.aula_sessao_id)
    aluno = db.get(Aluno, r.aluno_id)
    unidade = db.get(Unidade, sessao.unidade_id)
    cfg = obter_config(db, sessao.unidade_id)
    linhas = db.execute(
        select(Reserva, AulaSessao, TipoServico)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .where(Reserva.aluno_id == aluno.id, AulaSessao.data == sessao.data, AulaSessao.unidade_id == sessao.unidade_id)
    ).all()
    aviso_aluno = dom.AlunoAviso(aluno.id, aluno.nome, [], aluno.unidade_id, str(aluno.status), aluno.data_nascimento, aluno.codigo_legado or 0)
    reservas = [dom.ReservaAviso(rv.id, aviso_aluno, str(rv.status), s.data, s.hora_inicio, s.unidade_id, unidade.nome, t.nome)
                for rv, s, t in linhas]
    if cfg is None:
        cfg_dom = dom.ConfigAvisos(sessao.unidade_id, unidade.nome, {}, variaveis_estudio(db, None))
    else:
        cfg_dom = config_avisos(db, cfg, unidade.nome)
    avisos = dom.avisos_lembrete_aula(cfg_dom, sessao.data - timedelta(days=1), reservas)
    if not avisos or not avisos[0].mensagem:
        raise ErroDeNegocio("Esta aula não gera lembrete (cancelada, concluída ou com falta).", 409)
    return aluno, avisos[0].mensagem


def enviar_lembrete_agora(db: Session, reserva_id: int) -> ResultadoEnvio:
    aluno, mensagem = montar_lembrete_da_reserva(db, reserva_id)
    return exigir_envio(enviar_texto_aluno(db, aluno, mensagem, tipo=dom.LEMBRETE_ALUNO))


# ------------------------------------------------------------------------------------------------ contrato / termo
class EnviadorWhatsapp:
    """Enviador de contrato e termo de imagem por WhatsApp. O coordenador liga estes métodos aos pontos de extensão de
    contratos/alunos. Todos fazem ``flush`` (sem commit) e levantam ``ErroDeNegocio`` se não conseguirem enviar."""

    def enviar_link_contrato(self, db: Session, aluno: Aluno, link: str, *, contrato_id: int | None = None) -> str:
        cfg = obter_config(db, aluno.unidade_id)
        mensagem = renderizar_campo(db, cfg, "template_link_contrato", aluno=aluno.nome, link_contrato=link)
        exigir_envio(enviar_texto_aluno(db, aluno, mensagem, tipo="contract_link", contrato_id=contrato_id))
        return mensagem

    def enviar_link_termo(self, db: Session, aluno: Aluno, link: str) -> str:
        mensagem = renderizar_livre(
            db, obter_config(db, aluno.unidade_id),
            "Olá {aluno}, para registrar sua autorização de uso de imagem acesse: {link_termo}",
            aluno=aluno.nome, link_termo=link)
        exigir_envio(enviar_texto_aluno(db, aluno, mensagem, tipo="image_term_link"))
        return mensagem

    def enviar_documento_por_url(self, db: Session, aluno: Aluno, url: str, nome_arquivo: str, legenda: str = "", *,
                                 tipo: str = "contract_pdf", contrato_id: int | None = None) -> None:
        exigir_envio(enviar_documento_por_url(db, aluno, url, nome_arquivo, legenda, tipo=tipo, contrato_id=contrato_id))


ENVIADOR: EnviadorWhatsapp | None = None


def registrar_enviador() -> EnviadorWhatsapp:
    """Cria (uma vez) e devolve o enviador de contrato/termo; o coordenador o liga aos pontos de extensão."""
    global ENVIADOR
    if ENVIADOR is None:
        ENVIADOR = EnviadorWhatsapp()
    return ENVIADOR


# ------------------------------------------------------------------------------------------------ notificador do core
class NotificadorWhatsapp:
    """Implementação real do ``core.notificador``: código de recuperação de senha e OTP do app do aluno.

    O core só conhece o telefone (não a unidade): usa a configuração utilizável da PRIMEIRA unidade (menor id) que tenha
    credencial cadastrada. Não grava histórico (o texto contém um código)."""

    def enviar_texto(self, telefone: str, texto: str) -> bool:
        canonico = normalizar_telefone_br(telefone)
        if not canonico or tipo_telefone(canonico) != "celular":
            log.warning("Notificador: telefone inválido, mensagem não enviada.")
            return False
        with SessionLocal() as db:
            cfg = db.scalar(select(WhatsappConfig).where(WhatsappConfig.credencial_cifrado.is_not(None))
                            .order_by(WhatsappConfig.unidade_id))
            if not cfg:
                log.warning("Notificador: WhatsApp não configurado, mensagem não enviada.")
                return False
            p = provedor_da_config(cfg)
        res = _com_retry(lambda: p.enviar_texto(canonico, texto))
        if not res.ok:
            log.warning("Notificador: envio falhou (%s)", "sessão desconectada" if res.sessao_caiu else (res.erro or "erro"))
        return res.ok


def enviar_mensagem_de_contrato(db: Session, m) -> None:
    """Adaptador: o módulo de contratos entrega um `MensagemWhatsapp` e este módulo envia pelo provedor da unidade.

    Tipos: contrato_assinatura (link + PDF), termo_assinatura (link), contrato_assinado e termo_assinado (confirmação).
    Levanta `ErroDeNegocio` se não conseguir enviar (o módulo de contratos devolve 502 sem vazar detalhe)."""
    aluno = db.get(Aluno, m.aluno_id)
    if aluno is None:
        raise ErroDeNegocio("Aluno não encontrado para o envio.", 404)
    env = registrar_enviador()
    if m.tipo == "contrato_assinatura":
        env.enviar_link_contrato(db, aluno, m.link, contrato_id=m.contrato_id)
        if m.pdf_url:
            env.enviar_documento_por_url(db, aluno, m.pdf_url, m.pdf_nome or "contrato.pdf", "Seu contrato",
                                         tipo="contract_pdf", contrato_id=m.contrato_id)
    elif m.tipo == "termo_assinatura":
        env.enviar_link_termo(db, aluno, m.link)
    elif m.tipo in ("contrato_assinado", "termo_assinado"):
        rotulo = "contract_signed" if m.tipo == "contrato_assinado" else "image_term_signed"
        exigir_envio(enviar_texto_aluno(db, aluno, m.texto, tipo=rotulo, contrato_id=m.contrato_id))
    else:
        raise ErroDeNegocio(f"Tipo de mensagem desconhecido: {m.tipo}.", 422)


def registrar_tudo() -> None:
    """Liga os pontos de extensão que pertencem a este módulo."""
    from app.modules.contratos import servico as contratos
    from app.modules.financeiro import servico as fin

    fin.definir_cobrador(cobrar_conta)
    notif.definir_notificador(NotificadorWhatsapp())
    registrar_enviador()
    contratos.definir_enviador_whatsapp(enviar_mensagem_de_contrato)


# ------------------------------------------------------------------------------------------------ utilidades
def hoje_local(momento: datetime | None = None) -> date:
    return dom.hora_local(momento or agora()).date()


def nomes_profissionais(db: Session, ids: list[int]) -> dict[int, Profissional]:
    if not ids:
        return {}
    return {p.id: p for p in db.scalars(select(Profissional).where(Profissional.id.in_(ids)))}
