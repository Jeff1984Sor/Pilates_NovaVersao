"""Regras de aplicação dos contratos (a rota só orquestra). Regras de negócio puras vêm de `app.domain`.

Serviços estáveis para outros módulos:
- `contexto_documento(db, contrato)` / `html_do_contrato(db, contrato)` / `gerar_pdf_do_contrato(db, contrato)`
- `definir_enviador_whatsapp(fn)` — ponto de extensão para o agente de COMUNICAÇÃO (ver abaixo)
- `emitir_link_assinatura(contrato_id)` — link público de assinatura

Contrato com o módulo financeiro/agenda (nunca reimplementamos o que eles já fazem):
- parcelas: `financeiro.servico.gerar_contas_do_contrato` (R2);
- reservas: `agenda.servico.gerar_agenda_do_contrato` / `excluir_reserva` (cada reserva leva `contrato_id`, FK);
- conta paga nunca é apagada (`financeiro.servico.excluir_conta_receber` recusa).

Transações: as funções que recebem `ctx` fazem o `commit`; as que recebem `db` não.
"""

from __future__ import annotations

import calendar
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core import email as core_email
from app.core import storage
from app.core.config import settings
from app.core.db import agora
from app.core.deps import Contexto
from app.core.models import Identidade
from app.domain import agenda as dom_agenda
from app.domain import contratos as dom
from app.domain import modelos_documento as md
from app.domain import precos
from app.domain.documentos import formatar_cpf, so_digitos, validar_cpf
from app.domain.parcelas import gerar_parcelas
from app.modules.agenda import servico as agenda_servico
from app.modules.agenda.models import AulaAvaliativa, AulaSessao, Avaliacao, Evolucao, Reserva, StatusReserva
from app.modules.alunos import servico as alunos_servico
from app.modules.alunos.models import Aluno, AlunoDocumento, OrigemDocumento, StatusAluno, WhatsappMensagem
from app.modules.cadastros.models import (
    ModeloContrato,
    Plano,
    Profissao,
    Profissional,
    Recorrencia,
    Unidade,
    proximo_codigo,
)
from app.modules.contratos import pdf as pdf_mod
from app.modules.contratos import schemas as sc
from app.modules.contratos import tokens
from app.modules.contratos.models import Contrato, FormaPagamento, StatusAssinatura
from app.modules.financeiro import servico as fin
from app.modules.financeiro.models import Comissao, ContaReceber, StatusReceber

log = logging.getLogger(__name__)

CAT_ASSINATURAS = "assinaturas"  # assinaturas/contrato/contrato_<id>.png (mesmo caminho que o ETL usa)
storage.registrar_categoria(CAT_ASSINATURAS, "contratos.ver", {".png"}, 1)

PNG_MAGICO = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
ROTULO_FORMA = {"DINHEIRO": "Dinheiro", "PIX": "Pix", "CREDITO": "Cartão de crédito", "DEBITO": "Cartão de débito"}
ROTULO_RECORRENCIA = {"MENSAL": "Mensal", "SEMANAL": "Semanal"}


# --------------------------------------------------------------------------------------------------------- erros
class ErroContrato(Exception):
    """Regra de negócio com mensagem pronta para o usuário; `status` é o HTTP sugerido."""

    def __init__(self, mensagem: str, status: int = 409, dados: dict | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.dados = dados or {}


def _hoje(hoje: date | None = None) -> date:
    return hoje or fin.hoje_de_negocio_agora()


# --------------------------------------------------------------------------- ponto de extensão: WhatsApp (COMUNICAÇÃO)
@dataclass
class MensagemWhatsapp:
    """O que o enviador de WhatsApp recebe. `tipo`: contrato_assinatura | contrato_assinado | termo_assinatura | termo_assinado."""

    tipo: str
    aluno_id: int
    telefone: str  # canônico (DDI 55)
    texto: str
    contrato_id: int | None = None
    link: str | None = None  # página de assinatura
    pdf_url: str | None = None  # PDF público por token (o provedor baixa dali); sem efeito colateral
    pdf_nome: str | None = None


_enviador_whatsapp: Callable[[Session, MensagemWhatsapp], None] | None = None


def definir_enviador_whatsapp(fn: Callable[[Session, MensagemWhatsapp], None] | None) -> None:
    """Registra quem envia WhatsApp pelos contratos e termos (o agente COMUNICAÇÃO chama isto na subida).

    Assinatura: `fn(db, mensagem: MensagemWhatsapp) -> None`; levanta exceção se não conseguir enviar. Sem enviador
    registrado, o envio manual responde 503 "WhatsApp ainda não configurado" e as confirmações automáticas são puladas.
    `definir_enviador_whatsapp(None)` desliga.
    """
    global _enviador_whatsapp
    _enviador_whatsapp = fn


def whatsapp_disponivel() -> bool:
    return _enviador_whatsapp is not None


def _enviar_whatsapp(db: Session, msg: MensagemWhatsapp) -> None:
    if _enviador_whatsapp is None:
        raise ErroContrato("WhatsApp ainda não configurado.", 503)
    try:
        _enviador_whatsapp(db, msg)
    except ErroContrato:
        raise
    except Exception as e:  # noqa: BLE001 - mensagem do provedor não vai para a tela
        log.warning("Falha ao enviar WhatsApp (%s): %s", msg.tipo, type(e).__name__)
        raise ErroContrato("Não foi possível enviar o WhatsApp agora. Tente novamente em instantes.", 502) from e


# ------------------------------------------------------------------------------------------------ utilidades
def numero_do_contrato(c: Contrato) -> int:
    return c.codigo_legado or c.id


def db_aluno(db: Session, c: Contrato) -> Aluno | None:
    return db.get(Aluno, c.aluno_id)


def obter(db: Session, contrato_id: int) -> Contrato:
    c = db.get(Contrato, contrato_id)
    if c is None:
        raise ErroContrato("Contrato não encontrado.", 404)
    return c


def _plano(db: Session, plano_id: int) -> Plano:
    p = db.get(Plano, plano_id)
    if p is None:
        raise ErroContrato("Plano não encontrado.", 422)
    return p


def fim_sugerido(inicio: date, duracao_meses: int) -> date:
    """Início + duração do plano, menos um dia (01/11 + 3 meses = 31/01). Só sugestão para a tela."""
    meses = max(int(duracao_meses or 1), 1)
    total = inicio.month - 1 + meses
    ano, mes = inicio.year + total // 12, total % 12 + 1
    dia = min(inicio.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia) - timedelta(days=1)


def _recorrencia(c: Contrato) -> str:
    return getattr(c.recorrencia, "value", c.recorrencia) or "MENSAL"


def status_val(v) -> str:
    return getattr(v, "value", v)


# ------------------------------------------------------------------------------------------- precificação (R1, R2)
def precificar(db: Session, plano_id: int, data_inicio: date, data_fim: date | None = None) -> sc.PrecificacaoOut:
    """Valores e parcelas que o contrato terá. Só LÊ (a tela chama a cada mudança de plano ou data)."""
    plano = _plano(db, plano_id)
    p = precos.precificar_contrato(plano.valor, plano.aulas_por_semana, plano.duracao_meses)
    sugerida = fim_sugerido(data_inicio, plano.duracao_meses)
    fim = data_fim or sugerida
    if fim < data_inicio:
        raise ErroContrato("A data final não pode ser anterior à inicial.", 422)
    parcelas = gerar_parcelas(p.valor_parcela, data_inicio, fim, plano.duracao_meses, p.recorrencia)
    return sc.PrecificacaoOut(
        plano_id=plano.id, plano_nome=plano.nome, avulso=plano.avulso, aulas_por_semana=plano.aulas_por_semana,
        duracao_meses=max(plano.duracao_meses or 1, 1), valor_mensal=Decimal(plano.valor), valor_aula=p.valor_aula,
        valor_parcela=p.valor_parcela, valor_total=p.valor_total, data_inicio=data_inicio, data_fim=fim,
        data_fim_sugerida=sugerida,
        parcelas=[sc.ParcelaPrevista(numero=i + 1, vencimento=x.vencimento, competencia=x.competencia, valor=x.valor)
                  for i, x in enumerate(parcelas)],
    )


def _valores_do_plano(plano: Plano) -> precos.PrecificacaoContrato:
    return precos.precificar_contrato(plano.valor, plano.aulas_por_semana, plano.duracao_meses)


def _valores_divergem(c: Contrato, plano: Plano | None) -> bool:
    if plano is None:
        return False
    p = _valores_do_plano(plano)
    return not (
        (c.valor_aula == p.valor_aula or (c.valor_aula is not None and p.valor_aula is not None and Decimal(c.valor_aula) == p.valor_aula))
        and Decimal(c.valor_parcela) == p.valor_parcela
        and Decimal(c.valor_total) == p.valor_total
    )


# ---------------------------------------------------------------------------------------------- documento / PDF
def contexto_documento(db: Session, c: Contrato, hoje: date | None = None) -> dict[str, str]:
    """Valores das variáveis `{CHAVE}` do modelo de contrato (o `renderizar` do domínio escapa o HTML)."""
    aluno = db.get(Aluno, c.aluno_id)
    plano = db.get(Plano, c.plano_id)
    unidade = db.get(Unidade, c.unidade_id)
    prof = db.get(Profissional, c.profissional_id)
    end = alunos_servico.endereco_do_aluno(db, c.aluno_id)
    profissao = db.get(Profissao, aluno.profissao_id) if aluno and aluno.profissao_id else None
    tels = ", ".join(alunos_servico.formatar_telefone(t.numero) for t in alunos_servico.telefones_do_aluno(db, c.aluno_id))
    from app.modules.cadastros.models import TipoServico

    servico = db.get(TipoServico, plano.tipo_servico_id) if plano else None
    end_txt = f"{end.logradouro}, {end.numero} - {end.bairro} - {end.cidade} ({end.cep or ''})" if end else ""
    forma = status_val(c.forma_pagamento) if c.forma_pagamento else None
    estado = status_val(aluno.estado_civil) if aluno and aluno.estado_civil else None
    rec_plano = status_val(plano.recorrencia) if plano else None
    return {
        "ALUNO_NOME": aluno.nome if aluno else "",
        "ALUNO_CPF": formatar_cpf(aluno.cpf) if aluno and aluno.cpf else "",
        "ALUNO_RG": (aluno.rg or "") if aluno else "",
        "ALUNO_NASCIMENTO": md.formatar_data(aluno.data_nascimento) if aluno else "",
        "ALUNO_ESTADO_CIVIL": alunos_servico.ROTULOS_ESTADO_CIVIL.get(estado, "") if estado else "",
        "ALUNO_PROFISSAO": profissao.nome if profissao else "",
        "ALUNO_EMAIL": (aluno.email or "") if aluno else "",
        "ALUNO_TELEFONE": tels,
        "ALUNO_ENDERECO": end_txt,
        "ENDERECO_LOGRADOURO": end.logradouro if end else "",
        "ENDERECO_NUMERO": end.numero if end else "",
        "ENDERECO_BAIRRO": end.bairro if end else "",
        "ENDERECO_CIDADE": end.cidade if end else "",
        "ENDERECO_CEP": (end.cep or "") if end else "",
        "PROFISSIONAL_NOME": prof.nome if prof else "",
        "PROFISSIONAL_CREFITO": (prof.crefito or "") if prof else "",
        "UNIDADE_NOME": unidade.nome if unidade else "",
        "UNIDADE_CAPACIDADE": str(unidade.capacidade or "") if unidade else "",
        "PLANO_NOME": plano.nome if plano else "",
        "PLANO_AULAS_SEMANA": str(plano.aulas_por_semana or "") if plano else "",
        "PLANO_DURACAO_MESES": str(plano.duracao_meses or "") if plano else "",
        "PLANO_RECORRENCIA": ROTULO_RECORRENCIA.get(rec_plano, "") if rec_plano else "",
        "TIPO_SERVICO": servico.nome if servico else "",
        "CONTRATO_NUMERO": str(numero_do_contrato(c)),
        "CONTRATO_INICIO": md.formatar_data(c.data_inicio),
        "CONTRATO_FIM": md.formatar_data(c.data_fim),
        "CONTRATO_RECORRENCIA": ROTULO_RECORRENCIA.get(_recorrencia(c), ""),
        "CONTRATO_MODO_PAGAMENTO": ROTULO_FORMA.get(forma, "") if forma else "",
        "CONTRATO_VALOR_PARCELA": md.formatar_moeda(c.valor_parcela),
        "CONTRATO_VALOR_TOTAL": md.formatar_moeda(c.valor_total),
        "DATA_HOJE": md.formatar_data(_hoje(hoje)),
    }


def modelo_html(db: Session, c: Contrato) -> str:
    plano = db.get(Plano, c.plano_id)
    modelo = db.get(ModeloContrato, plano.modelo_contrato_id) if plano and plano.modelo_contrato_id else None
    return (modelo.conteudo_html if modelo and modelo.conteudo_html else "") or md.MODELO_CONTRATO_PADRAO


def html_do_contrato(db: Session, c: Contrato, hoje: date | None = None) -> str:
    return md.renderizar(modelo_html(db, c), contexto_documento(db, c, hoje), escopo=md.ESCOPO_CONTRATO)


def nome_do_estudio(db: Session) -> str:
    ident = db.get(Identidade, 1)
    return (ident.nome_exibicao if ident and ident.nome_exibicao else None) or settings.app_name


def _logo(db: Session) -> bytes | None:
    ident = db.get(Identidade, 1)
    if ident and ident.logo_path:
        try:
            return storage.ler(ident.logo_path)
        except (FileNotFoundError, storage.ArquivoInvalido):
            return None
    return None


def _assinatura_do_contrato(c: Contrato) -> pdf_mod.Assinatura | None:
    if status_val(c.status_assinatura) == StatusAssinatura.NAO_ASSINADO or not c.assinatura_nome:
        return None
    imagem = None
    if c.assinatura_path and storage.existe(c.assinatura_path):
        imagem = storage.ler(c.assinatura_path)
    digital = status_val(c.status_assinatura) == StatusAssinatura.ASSINADO_DIGITALMENTE
    return pdf_mod.Assinatura(
        nome=c.assinatura_nome, documento=c.assinatura_documento, assinado_em=c.assinado_em, ip=c.assinatura_ip,
        metodo="digital" if digital else "local", imagem_png=imagem,
    )


def gerar_pdf_do_contrato(db: Session, c: Contrato, *, hoje: date | None = None, comprimir: bool = True) -> bytes:
    """PDF do contrato com o modelo do plano; com a assinatura embutida quando assinado. Só LÊ (sem gravar nada)."""
    numero = numero_do_contrato(c)
    return pdf_mod.gerar_pdf(pdf_mod.DadosPdf(
        titulo=f"Contrato nº {numero}", html=html_do_contrato(db, c, hoje), estudio_nome=nome_do_estudio(db),
        rodape_extra=f"Contrato nº {numero}", logo=_logo(db), assinatura=_assinatura_do_contrato(c), comprimir=comprimir,
    ))


def _documento_pdf(db: Session, contrato_id: int) -> AlunoDocumento | None:
    return db.scalar(select(AlunoDocumento).where(
        AlunoDocumento.contrato_id == contrato_id, AlunoDocumento.origem == OrigemDocumento.CONTRATO_PDF
    ).order_by(AlunoDocumento.id.desc()).limit(1))


def gravar_pdf_como_documento(db: Session, c: Contrato, pdf: bytes) -> tuple[AlunoDocumento, str]:
    """Guarda (ou atualiza) o PDF como documento do aluno, origem CONTRATO_PDF. Devolve (documento, caminho)."""
    rel = storage.salvar(alunos_servico.CAT_DOCUMENTOS, "contrato.pdf", pdf, subpasta=str(c.aluno_id),
                         nome_base=f"contrato_{c.id}", substituir=True)
    doc = _documento_pdf(db, c.id)
    sha = hashlib.sha256(pdf).hexdigest()
    titulo = f"Contrato nº {numero_do_contrato(c)}"
    if doc is None:
        doc = AlunoDocumento(aluno_id=c.aluno_id, contrato_id=c.id, titulo=titulo, arquivo_path=rel, sha256=sha,
                             descricao="Gerado automaticamente a partir do modelo do plano.", origem=OrigemDocumento.CONTRATO_PDF)
        db.add(doc)
    else:
        doc.arquivo_path, doc.sha256, doc.titulo = rel, sha, titulo
    db.flush()
    return doc, rel


def atualizar_pdf_guardado(db: Session, c: Contrato) -> None:
    """Regera o PDF do documento do aluno (depois de editar ou assinar). Falha aqui NÃO desfaz o ato principal."""
    try:
        gravar_pdf_como_documento(db, c, gerar_pdf_do_contrato(db, c))
    except Exception:  # noqa: BLE001
        log.exception("Não foi possível atualizar o PDF guardado do contrato %s", c.id)


# ------------------------------------------------------------------------------------------------- criação
def _validar_refs(db: Session, aluno_id: int, plano: Plano, unidade_id: int, profissional_id: int) -> Aluno:
    aluno = db.get(Aluno, aluno_id)
    if aluno is None:
        raise ErroContrato("Aluno não encontrado.", 422)
    if status_val(aluno.status) == StatusAluno.INATIVO:
        raise ErroContrato("O aluno está inativo. Reative o cadastro antes de criar o contrato.", 409)
    if not plano.ativo:
        raise ErroContrato("O plano está inativo.", 422)
    unidade = db.get(Unidade, unidade_id)
    if unidade is None or not unidade.ativo:
        raise ErroContrato("Unidade inválida ou inativa.", 422)
    prof = db.get(Profissional, profissional_id)
    if prof is None or not prof.ativo:
        raise ErroContrato("Profissional inválido ou inativo.", 422)
    return aluno


def _avisos_de_sobreposicao(db: Session, c: Contrato) -> list[str]:
    outros = db.scalars(select(Contrato).where(
        Contrato.aluno_id == c.aluno_id, Contrato.id != c.id, Contrato.plano_id.in_(
            select(Plano.id).where(Plano.tipo_servico_id == select(Plano.tipo_servico_id).where(Plano.id == c.plano_id).scalar_subquery())
        ), Contrato.data_inicio <= c.data_fim, Contrato.data_fim >= c.data_inicio)).all()
    return [f"O aluno já tem o contrato nº {numero_do_contrato(o)} neste período ({md.formatar_data(o.data_inicio)} a {md.formatar_data(o.data_fim)})."
            for o in outros]


def criar_contrato(ctx: Contexto, dados: sc.ContratoIn, *, hoje: date | None = None) -> sc.ContratoCriado:
    """Cria contrato + parcelas (R2) + PDF guardado como documento do aluno, TUDO ou NADA.

    Qualquer falha (plano inexistente, parcelas, PDF, gravação do arquivo) desfaz o banco e apaga o arquivo escrito.
    """
    db = ctx.db
    plano = _plano(db, dados.plano_id)
    _validar_refs(db, dados.aluno_id, plano, dados.unidade_id, dados.profissional_id)
    p = _valores_do_plano(plano)
    fim = dados.data_fim or fim_sugerido(dados.data_inicio, plano.duracao_meses)
    rel_gravado: str | None = None
    try:
        c = Contrato(
            aluno_id=dados.aluno_id, plano_id=plano.id, unidade_id=dados.unidade_id, profissional_id=dados.profissional_id,
            recorrencia=Recorrencia(p.recorrencia), forma_pagamento=dados.forma_pagamento, valor_aula=p.valor_aula,
            valor_parcela=p.valor_parcela, valor_total=p.valor_total, data_inicio=dados.data_inicio, data_fim=fim,
            status_assinatura=StatusAssinatura.NAO_ASSINADO, codigo_legado=proximo_codigo(db, "contrato"),
        )
        db.add(c)
        db.flush()
        contas = fin.gerar_contas_do_contrato(db, c)
        pdf_bytes = gerar_pdf_do_contrato(db, c, hoje=hoje)
        # caminho determinístico: dá para limpar o arquivo se qualquer passo seguinte falhar
        rel_gravado = f"{alunos_servico.CAT_DOCUMENTOS}/{c.aluno_id}/contrato_{c.id}.pdf"
        doc, _rel = gravar_pdf_como_documento(db, c, pdf_bytes)
        ctx.auditar("contrato.criar", "contrato", c.id,
                    descricao=f"Contrato nº {numero_do_contrato(c)} criado ({plano.nome}, {md.formatar_data(c.data_inicio)} a {md.formatar_data(c.data_fim)})",
                    depois={"aluno_id": c.aluno_id, "plano_id": c.plano_id, "valor_parcela": str(c.valor_parcela),
                            "valor_total": str(c.valor_total), "parcelas": len(contas)})
        db.commit()
    except BaseException:
        db.rollback()
        if rel_gravado:
            storage.remover(rel_gravado)
        raise
    avisos = _avisos_de_sobreposicao(db, c)
    det = detalhe(db, c, hoje=hoje)
    det.avisos = avisos
    return sc.ContratoCriado(contrato=det, parcelas_criadas=len(contas), pdf_documento_id=doc.id,
                             proximo_passo="nenhum" if plano.avulso else "agenda")


def renovar(ctx: Contexto, contrato_id: int, dados: sc.RenovarIn, *, hoje: date | None = None) -> sc.ContratoCriado:
    """Novo contrato a partir de um existente (renovação ou cópia): mesmo aluno, unidade e profissional; por padrão
    começa no dia seguinte ao fim do original e dura o que o plano manda. Passa por `criar_contrato` (R1, R2, PDF)."""
    antigo = obter(ctx.db, contrato_id)
    inicio = dados.data_inicio or (antigo.data_fim + timedelta(days=1))
    novo = sc.ContratoIn(
        aluno_id=antigo.aluno_id, plano_id=dados.plano_id or antigo.plano_id, unidade_id=antigo.unidade_id,
        profissional_id=antigo.profissional_id, data_inicio=inicio, data_fim=dados.data_fim,
        forma_pagamento=dados.forma_pagamento or (antigo.forma_pagamento if antigo.forma_pagamento else None),
    )
    criado = criar_contrato(ctx, novo, hoje=hoje)
    ctx.auditar("contrato.renovar", "contrato", criado.contrato.id,
                descricao=f"Contrato nº {criado.contrato.numero} criado como renovação do nº {numero_do_contrato(antigo)}",
                depois={"origem_contrato_id": antigo.id})
    ctx.db.commit()
    return criado


# -------------------------------------------------------------------------------------------------- consultas
def _situacao(c: Contrato, hoje: date) -> sc.Situacao:
    s = dom.situacao_do_contrato(c.data_fim, hoje)
    return sc.Situacao(rotulo=s.situacao, badge=s.badge, dias_restantes=s.dias_restantes)


def _resumos(db: Session, contratos: list[Contrato], hoje: date) -> list[sc.ContratoResumo]:
    if not contratos:
        return []
    ids = [c.id for c in contratos]
    nomes_aluno = dict(db.execute(select(Aluno.id, Aluno.nome).where(Aluno.id.in_({c.aluno_id for c in contratos}))).all())
    nomes_plano = dict(db.execute(select(Plano.id, Plano.nome).where(Plano.id.in_({c.plano_id for c in contratos}))).all())
    nomes_un = dict(db.execute(select(Unidade.id, Unidade.nome).where(Unidade.id.in_({c.unidade_id for c in contratos}))).all())
    nomes_prof = dict(db.execute(select(Profissional.id, Profissional.nome).where(Profissional.id.in_({c.profissional_id for c in contratos}))).all())
    abertas = dict(db.execute(select(ContaReceber.contrato_id, func.count()).where(
        ContaReceber.contrato_id.in_(ids), ContaReceber.status == StatusReceber.ABERTO).group_by(ContaReceber.contrato_id)).all())
    futuras = dict(db.execute(
        select(Reserva.contrato_id, func.count()).join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id).where(
            Reserva.contrato_id.in_(ids), Reserva.status.in_([StatusReserva.RESERVADA, StatusReserva.PENDENTE]),
            AulaSessao.data >= hoje).group_by(Reserva.contrato_id)).all())
    docs = dict(db.execute(select(AlunoDocumento.contrato_id, func.max(AlunoDocumento.id)).where(
        AlunoDocumento.contrato_id.in_(ids), AlunoDocumento.origem == OrigemDocumento.CONTRATO_PDF).group_by(AlunoDocumento.contrato_id)).all())
    saida = []
    for c in contratos:
        saida.append(sc.ContratoResumo(
            id=c.id, numero=numero_do_contrato(c), aluno=sc.PessoaRef(id=c.aluno_id, nome=nomes_aluno.get(c.aluno_id, "?")),
            plano=sc.PessoaRef(id=c.plano_id, nome=nomes_plano.get(c.plano_id, "?")),
            unidade=sc.PessoaRef(id=c.unidade_id, nome=nomes_un.get(c.unidade_id, "?")),
            profissional=sc.PessoaRef(id=c.profissional_id, nome=nomes_prof.get(c.profissional_id, "?")),
            data_inicio=c.data_inicio, data_fim=c.data_fim, valor_aula=c.valor_aula, valor_parcela=c.valor_parcela,
            valor_total=c.valor_total, forma_pagamento=c.forma_pagamento, status_assinatura=c.status_assinatura,
            situacao=_situacao(c, hoje), parcelas_abertas=abertas.get(c.id, 0), aulas_futuras=futuras.get(c.id, 0),
            pdf_documento_id=docs.get(c.id),
        ))
    return saida


def _filtro_base(*, aluno_id, plano_id, de, ate, q):
    cond = []
    if aluno_id:
        cond.append(Contrato.aluno_id == aluno_id)
    if plano_id:
        cond.append(Contrato.plano_id == plano_id)
    if de:
        cond.append(Contrato.data_fim >= de)  # período: contratos que têm alguma vigência dentro de [de, ate]
    if ate:
        cond.append(Contrato.data_inicio <= ate)
    termo = (q or "").strip()
    if termo:
        digitos = so_digitos(termo)
        ou = [Aluno.nome.ilike(f"%{termo}%")]
        if digitos:
            ou.append(Aluno.cpf.like(f"%{digitos}%"))
            if len(digitos) <= 9:
                ou.extend([Contrato.codigo_legado == int(digitos), Contrato.id == int(digitos)])
        cond.append(or_(*ou))
    return cond


def listar(db: Session, *, chip: str = "ativos", aluno_id: int | None = None, plano_id: int | None = None,
           de: date | None = None, ate: date | None = None, q: str | None = None, pagina: int = 1, por_pagina: int = 25,
           hoje: date | None = None) -> sc.ListaContratos:
    """Gestão de contratos. A vigência (ativo, vencendo em 30 dias, vencido) vem de `domain.contratos`."""
    hoje = _hoje(hoje)
    linhas = db.execute(
        select(Contrato.id, Contrato.data_inicio, Contrato.data_fim, Contrato.status_assinatura)
        .join(Aluno, Aluno.id == Contrato.aluno_id)
        .where(*_filtro_base(aluno_id=aluno_id, plano_id=plano_id, de=de, ate=ate, q=q))
    ).all()
    periodos = [(r.data_inicio, r.data_fim) for r in linhas]
    resumo = dom.resumo_gestao(periodos, hoje)
    nao_assinados = [r for r in linhas if status_val(r.status_assinatura) == StatusAssinatura.NAO_ASSINADO and not dom.esta_vencido(r.data_fim, hoje)]
    if chip == "nao_assinados":
        escolhidos = nao_assinados
    else:
        filtro = {"ativos": "ativos", "vencendo": "vencendo", "vencidos": "vencidos", "todos": "todos"}[chip]
        escolhidos = [r for r in linhas if dom.passa_no_filtro(filtro, r.data_inicio, r.data_fim, hoje)]
    escolhidos.sort(key=(lambda r: (r.data_fim, r.id)) if chip == "vencendo" else (lambda r: -r.id))
    total = len(escolhidos)
    ini = (pagina - 1) * por_pagina
    ids = [r.id for r in escolhidos[ini:ini + por_pagina]]
    por_id = {c.id: c for c in db.scalars(select(Contrato).where(Contrato.id.in_(ids)))} if ids else {}
    itens = _resumos(db, [por_id[i] for i in ids if i in por_id], hoje)
    return sc.ListaContratos(
        itens=itens, total=total, pagina=pagina, por_pagina=por_pagina, chip=chip,  # type: ignore[arg-type]
        contagens=sc.Contagens(ativos=resumo["ativos"], vencendo=resumo["vencendo"], vencidos=resumo["vencidos"],
                               nao_assinados=len(nao_assinados), total=resumo["total"]),
    )


def _parcelas(db: Session, contrato_id: int, hoje: date) -> list[sc.ParcelaOut]:
    contas = db.scalars(select(ContaReceber).where(ContaReceber.contrato_id == contrato_id).order_by(ContaReceber.vencimento, ContaReceber.id)).all()
    return [sc.ParcelaOut(id=x.id, vencimento=x.vencimento, competencia=x.competencia, valor=x.valor,
                          situacao=fin.situacao_receber(x, hoje)) for x in contas]


def detalhe(db: Session, c: Contrato, *, hoje: date | None = None) -> sc.ContratoDetalhe:
    hoje = _hoje(hoje)
    base = _resumos(db, [c], hoje)[0]
    plano = db.get(Plano, c.plano_id)
    aluno = db.get(Aluno, c.aluno_id)
    avisos: list[str] = []
    divergem = _valores_divergem(c, plano)
    if divergem and plano is not None:
        p = _valores_do_plano(plano)
        avisos.append(f"Os valores do contrato diferem do plano atual (parcela do plano: {md.formatar_moeda(p.valor_parcela)}). "
                      "Use \"Recalcular valores\" na edição se quiser igualar.")
    ass_url = f"/arquivos/{c.assinatura_path}" if c.assinatura_path and storage.existe(c.assinatura_path) else None
    avulso = bool(plano and plano.avulso)
    return sc.ContratoDetalhe(
        **base.model_dump(), tipo_servico_id=plano.tipo_servico_id if plano else 0,
        aulas_por_semana=plano.aulas_por_semana if plano else 0, duracao_meses=plano.duracao_meses if plano else 0, avulso=avulso,
        recorrencia=_recorrencia(c), valor_do_plano=Decimal(plano.valor) if plano else Decimal(0), valores_divergem_do_plano=divergem,
        parcelas=_parcelas(db, c.id, hoje),
        assinatura=sc.AssinaturaOut(nome=c.assinatura_nome, documento=c.assinatura_documento, ip=c.assinatura_ip,
                                    assinado_em=c.assinado_em, imagem_url=ass_url),
        precisa_agenda=(not avulso and base.aulas_futuras == 0 and not dom.esta_vencido(c.data_fim, hoje)),
        aluno_email=aluno.email if aluno else None,
        aluno_telefone=alunos_servico.formatar_telefone(alunos_servico.telefone_principal(db, c.aluno_id)) if aluno else None,
        avisos=avisos,
    )


def opcoes(db: Session) -> sc.OpcoesOut:
    planos = db.scalars(select(Plano).where(Plano.ativo).order_by(Plano.nome)).all()
    return sc.OpcoesOut(
        planos=[{"id": p.id, "nome": p.nome, "valor": str(p.valor), "aulas_por_semana": p.aulas_por_semana,
                 "duracao_meses": p.duracao_meses, "avulso": p.avulso, "tipo_servico_id": p.tipo_servico_id} for p in planos],
        unidades=[sc.PessoaRef(id=u.id, nome=u.nome) for u in db.scalars(select(Unidade).where(Unidade.ativo).order_by(Unidade.nome))],
        profissionais=[sc.PessoaRef(id=x.id, nome=x.nome) for x in db.scalars(select(Profissional).where(Profissional.ativo).order_by(Profissional.nome))],
        formas_pagamento=[f.value for f in FormaPagamento], whatsapp_disponivel=whatsapp_disponivel(),
    )


# -------------------------------------------------------------------------------------------------------- editar
def editar(ctx: Contexto, contrato_id: int, dados: sc.EditarIn, *, hoje: date | None = None) -> sc.ContratoDetalhe:
    """Edita o contrato. Valores só mudam se o usuário PEDIR (`recalcular_valores`) ou DIGITAR (`valor_*`): mudar plano
    ou datas sozinho nunca sobrescreve valor em silêncio (a resposta avisa quando ficam diferentes do plano)."""
    db = ctx.db
    c = obter(db, contrato_id)
    if dados.recalcular_valores and any(v is not None for v in (dados.valor_aula, dados.valor_parcela, dados.valor_total)):
        raise ErroContrato("Escolha: recalcular os valores pelo plano OU digitar os valores. Os dois juntos não.", 422)
    antes = {k: _jsonavel(getattr(c, k)) for k in ("unidade_id", "profissional_id", "forma_pagamento", "plano_id",
                                                   "data_inicio", "data_fim", "valor_aula", "valor_parcela", "valor_total")}
    muda_contratual = (
        (dados.plano_id is not None and dados.plano_id != c.plano_id)
        or (dados.data_inicio is not None and dados.data_inicio != c.data_inicio)
        or (dados.data_fim is not None and dados.data_fim != c.data_fim)
        or dados.recalcular_valores
        or any(v is not None for v in (dados.valor_aula, dados.valor_parcela, dados.valor_total))
    )
    if muda_contratual and status_val(c.status_assinatura) != StatusAssinatura.NAO_ASSINADO and not dados.confirmar_alterar_assinado:
        raise ErroContrato("Este contrato já foi assinado. Alterar plano, datas ou valores muda o que foi assinado: "
                           "prefira renovar/criar um novo, ou confirme a alteração.", 409, {"exige_confirmacao": True})
    if dados.plano_id is not None and dados.plano_id != c.plano_id:
        c.plano_id = _plano(db, dados.plano_id).id
    if dados.unidade_id is not None:
        u = db.get(Unidade, dados.unidade_id)
        if u is None or not u.ativo:
            raise ErroContrato("Unidade inválida ou inativa.", 422)
        c.unidade_id = u.id
    if dados.profissional_id is not None:
        pr = db.get(Profissional, dados.profissional_id)
        if pr is None or not pr.ativo:
            raise ErroContrato("Profissional inválido ou inativo.", 422)
        c.profissional_id = pr.id
    if dados.forma_pagamento is not None:
        c.forma_pagamento = dados.forma_pagamento
    elif dados.limpar_forma_pagamento:
        c.forma_pagamento = None
    if dados.data_inicio is not None:
        c.data_inicio = dados.data_inicio
    if dados.data_fim is not None:
        c.data_fim = dados.data_fim
    if c.data_fim < c.data_inicio:
        raise ErroContrato("A data final não pode ser anterior à inicial.", 422)
    plano = db.get(Plano, c.plano_id)
    if dados.recalcular_valores and plano is not None:
        p = _valores_do_plano(plano)
        c.valor_aula, c.valor_parcela, c.valor_total = p.valor_aula, p.valor_parcela, p.valor_total
    else:
        if dados.valor_aula is not None:
            c.valor_aula = dados.valor_aula
        if dados.valor_parcela is not None:
            c.valor_parcela = dados.valor_parcela
        if dados.valor_total is not None:
            c.valor_total = dados.valor_total
    db.flush()
    depois = {k: _jsonavel(getattr(c, k)) for k in antes}
    ctx.auditar("contrato.editar", "contrato", c.id, descricao=f"Contrato nº {numero_do_contrato(c)} editado",
                antes={k: v for k, v in antes.items() if v != depois[k]}, depois={k: v for k, v in depois.items() if v != antes[k]})
    atualizar_pdf_guardado(db, c)
    db.commit()
    det = detalhe(db, c, hoje=hoje)
    if muda_contratual and any(x.situacao in ("ABERTO", "ATRASADO") for x in det.parcelas):
        det.avisos.append("As parcelas já geradas não foram alteradas. Ajuste-as em Financeiro > Contas a receber, se precisar.")
    return det


def _jsonavel(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return getattr(v, "value", v)


# ---------------------------------------------------------------------------------------------------- recalcular
def recalcular(ctx: Contexto, dados: sc.RecalcularIn, *, hoje: date | None = None) -> sc.RecalculoOut:
    """Equivalente ao comando `recalcular_contratos` do sistema antigo: valor da aula, parcela e total pela regra R1
    do plano. Com `simular` (padrão) só mostra o que mudaria. Não mexe nas parcelas já geradas."""
    db = ctx.db
    hoje = _hoje(hoje)
    q = select(Contrato).order_by(Contrato.id)
    if dados.contrato_ids:
        q = q.where(Contrato.id.in_(dados.contrato_ids))
    if dados.somente_vigentes:
        q = q.where(Contrato.data_fim >= hoje)
    itens: list[sc.RecalculoItem] = []
    verificados = 0
    for c in db.scalars(q):
        plano = db.get(Plano, c.plano_id)
        if plano is None:
            continue
        verificados += 1
        p = _valores_do_plano(plano)
        antes = {"valor_aula": c.valor_aula, "valor_parcela": c.valor_parcela, "valor_total": c.valor_total}
        depois = {"valor_aula": p.valor_aula, "valor_parcela": p.valor_parcela, "valor_total": p.valor_total}
        if all((antes[k] is None and depois[k] is None) or (antes[k] is not None and depois[k] is not None and Decimal(antes[k]) == depois[k]) for k in antes):
            continue
        aluno = db.get(Aluno, c.aluno_id)
        itens.append(sc.RecalculoItem(contrato_id=c.id, numero=numero_do_contrato(c), aluno=aluno.nome if aluno else "?",
                                      plano=plano.nome, antes=antes, depois=depois))
        if not dados.simular:
            c.valor_aula, c.valor_parcela, c.valor_total = p.valor_aula, p.valor_parcela, p.valor_total
    if not dados.simular and itens:
        ctx.auditar("contrato.recalcular", "contrato", None, descricao=f"{len(itens)} contrato(s) recalculados pela regra do plano",
                    depois={"contratos": [i.contrato_id for i in itens]})
        db.commit()
    elif dados.simular:
        db.rollback()
    return sc.RecalculoOut(simulacao=dados.simular, verificados=verificados, alterados=len(itens), itens=itens)


# ----------------------------------------------------------------------------------------------------- encerrar
def _reservas_do_contrato(db: Session, contrato_id: int):
    return db.execute(
        select(Reserva, AulaSessao).join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id).where(Reserva.contrato_id == contrato_id)
    ).all()


def encerrar(ctx: Contexto, contrato_id: int, dados: sc.EncerrarIn, *, hoje: date | None = None) -> sc.EncerramentoOut:
    """Encerra o contrato HOJE sem apagar histórico: a data final passa a ser ontem (vira "Vencido"), as parcelas
    futuras em aberto são canceladas e as aulas de hoje em diante ainda não realizadas saem da agenda (opcional).
    Parcela paga, aula passada, evolução e comissão ficam intactas."""
    db = ctx.db
    hoje = _hoje(hoje)
    c = obter(db, contrato_id)
    if dom.esta_vencido(c.data_fim, hoje):
        raise ErroContrato("Este contrato já está vencido/encerrado.")
    antes = {"data_fim": c.data_fim.isoformat()}
    c.data_fim = max(hoje - timedelta(days=1), c.data_inicio)
    canceladas = removidas = mantidas = 0
    motivo = (dados.motivo or "").strip() or "Contrato encerrado"
    if dados.cancelar_parcelas_futuras:
        for conta in db.scalars(select(ContaReceber).where(
                ContaReceber.contrato_id == c.id, ContaReceber.status == StatusReceber.ABERTO, ContaReceber.vencimento >= hoje)):
            fin.cancelar_conta_receber(db, conta, motivo)
            canceladas += 1
    if dados.remover_aulas_futuras:
        for reserva, sessao in _reservas_do_contrato(db, c.id):
            if sessao.data >= hoje and status_val(reserva.status) in ("RESERVADA", "PENDENTE"):
                try:
                    with agenda_servico.savepoint(db):
                        agenda_servico.excluir_reserva(db, reserva.id)
                    removidas += 1
                except agenda_servico.ErroAgenda:
                    mantidas += 1
    db.flush()
    ctx.auditar("contrato.encerrar", "contrato", c.id, descricao=f"Contrato nº {numero_do_contrato(c)} encerrado. {motivo}",
                antes=antes, depois={"data_fim": c.data_fim.isoformat(), "parcelas_canceladas": canceladas, "aulas_removidas": removidas})
    db.commit()
    return sc.EncerramentoOut(contrato=detalhe(db, c, hoje=hoje), parcelas_canceladas=canceladas, reservas_removidas=removidas,
                              reservas_mantidas=mantidas)


# ----------------------------------------------------------------------------------------------------- exclusão
@dataclass
class _Exclusao:
    plano_dom: dom.PlanoExclusao
    contas: list[ContaReceber]
    reservas_apagar: list[tuple[Reserva, AulaSessao]]
    reservas_manter: list[Reserva]
    comissoes: int
    bloqueios: list[str]


def _montar_exclusao(db: Session, c: Contrato, hoje: date) -> _Exclusao:
    plano = db.get(Plano, c.plano_id)
    contas = list(db.scalars(select(ContaReceber).where(ContaReceber.contrato_id == c.id).order_by(ContaReceber.vencimento)))
    linhas = _reservas_do_contrato(db, c.id)
    ids_res = [r.id for r, _ in linhas]
    com_historico = set()
    pagas_por_reserva: set[int] = set()
    if ids_res:
        com_historico = set(db.scalars(select(Evolucao.reserva_id).where(Evolucao.reserva_id.in_(ids_res)))) | set(
            db.scalars(select(Avaliacao.reserva_id).where(Avaliacao.reserva_id.in_(ids_res))))
        pagas_por_reserva = set(db.scalars(select(ContaReceber.reserva_id).where(
            ContaReceber.reserva_id.in_(ids_res), ContaReceber.status == StatusReceber.PAGO)))
    apagar, manter = [], []
    for r, s in linhas:
        apagavel = (status_val(r.status) in ("RESERVADA", "PENDENTE") and s.data >= hoje
                    and r.id not in com_historico and r.id not in pagas_por_reserva)
        (apagar if apagavel else manter).append((r, s) if apagavel else r)
    ids_apagar = {r.id for r, _ in apagar}
    sessoes = {s.id for _, s in linhas}
    todas = db.execute(select(Reserva.id, Reserva.aluno_id, Reserva.aula_sessao_id, Reserva.contrato_id, Reserva.aula_avulsa_id,
                              AulaSessao.data, AulaSessao.unidade_id, AulaSessao.tipo_servico_id, Reserva.status)
                       .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
                       .where(Reserva.aula_sessao_id.in_(sessoes))).all() if sessoes else []
    refs = [dom.ReservaRef(id=x.id, aluno_id=x.aluno_id, sessao_id=x.aula_sessao_id, data_aula=x.data, unidade_id=x.unidade_id,
                           tipo_servico_id=x.tipo_servico_id, status=status_val(x.status),
                           contrato_id=c.id if x.id in ids_apagar else None, pacote_avulso_id=x.aula_avulsa_id) for x in todas]
    cref = dom.ContratoRef(id=c.id, aluno_id=c.aluno_id, unidade_id=c.unidade_id,
                           tipo_servico_id=plano.tipo_servico_id if plano else None, inicio=c.data_inicio, fim=c.data_fim)
    plano_dom = dom.plano_exclusao_por_fk(
        cref, [dom.ContaRef(id=x.id, contrato_id=x.contrato_id, status=status_val(x.status)) for x in contas], refs, com_historico)
    ids_contas = [x.id for x in contas]
    n_comissoes = (db.scalar(select(func.count()).select_from(Comissao).where(Comissao.conta_receber_id.in_(ids_contas))) or 0) if ids_contas else 0
    bloqueios = []
    if plano_dom.contas_pagas_ids:
        n = len(plano_dom.contas_pagas_ids)
        bloqueios.append(f"Há {n} parcela(s) já paga(s). Parcela paga, recibo e comissão fazem parte do histórico financeiro e não são apagados.")
    if n_comissoes:
        bloqueios.append(f"Há {n_comissoes} comissão(ões) calculada(s) sobre este contrato.")
    return _Exclusao(plano_dom, contas, apagar, manter, n_comissoes, bloqueios)


def plano_de_exclusao(db: Session, contrato_id: int, *, hoje: date | None = None) -> sc.PlanoExclusaoOut:
    """O que a exclusão faria (R13), para a tela de confirmação. Só LÊ."""
    hoje = _hoje(hoje)
    c = obter(db, contrato_id)
    ex = _montar_exclusao(db, c, hoje)
    pd = ex.plano_dom
    conta_out = lambda x: sc.ContaExclusao(id=x.id, vencimento=x.vencimento, valor=x.valor, situacao=fin.situacao_receber(x, hoje))  # noqa: E731
    pagas = [x for x in ex.contas if status_val(x.status) == "PAGO"]
    a_excluir = [x for x in ex.contas if status_val(x.status) != "PAGO"]
    pode = not ex.bloqueios
    doc = _documento_pdf(db, c.id)
    pdf_some = bool(doc and status_val(c.status_assinatura) == StatusAssinatura.NAO_ASSINADO)
    partes = [f"{len(a_excluir)} parcela(s) em aberto/cancelada(s)", f"{len(ex.reservas_apagar)} aula(s) futura(s) agendada(s)",
              f"{len(pd.sessoes_ids)} aula(s) que ficam vazias"]
    return sc.PlanoExclusaoOut(
        pode_excluir=pode, motivos_bloqueio=ex.bloqueios,
        alternativa=None if pode else "Use \"Encerrar\" para parar o contrato sem apagar o histórico financeiro.",
        contas_a_excluir=[conta_out(x) for x in a_excluir], contas_pagas=[conta_out(x) for x in pagas], comissoes=ex.comissoes,
        reservas_a_excluir=[sc.ReservaExclusao(id=r.id, data=s.data, inicio=f"{s.hora_inicio:%H:%M}", status=status_val(r.status))
                            for r, s in ex.reservas_apagar],
        reservas_mantidas=len(ex.reservas_manter), sessoes_que_ficam_vazias=len(pd.sessoes_ids),
        documento_pdf_sera_excluido=pdf_some,
        resumo="Será apagado: " + "; ".join(partes) + f". Ficam preservadas {len(ex.reservas_manter)} aula(s) já realizadas/registradas "
               "(sem vínculo ao contrato), evoluções e avaliações.",
    )


def excluir(ctx: Contexto, contrato_id: int, *, confirmar: bool, hoje: date | None = None) -> sc.ExclusaoOut:
    """Exclusão segura (R13). Recusa se houver parcela paga ou comissão; senão apaga as parcelas não pagas, as reservas
    FUTURAS vinculadas por FK (`reserva.contrato_id`) e as aulas que ficarem vazias. Aulas passadas e qualquer coisa com
    evolução/avaliação ficam, só sem o vínculo. Exige `confirmar=True`."""
    db = ctx.db
    hoje = _hoje(hoje)
    if not dom.exige_confirmacao("1" if confirmar else None):
        raise ErroContrato(dom.MENSAGEM_CONFIRMAR_EXCLUSAO, 409)
    c = obter(db, contrato_id)
    ex = _montar_exclusao(db, c, hoje)
    if ex.bloqueios:
        raise ErroContrato("Este contrato não pode ser excluído. " + " ".join(ex.bloqueios) +
                           " Use \"Encerrar\" para parar o contrato sem apagar o histórico.", 409, {"motivos": ex.bloqueios})
    numero = numero_do_contrato(c)
    doc = _documento_pdf(db, c.id)
    arquivos_apagar: list[str] = []
    sessoes_excluidas = 0
    try:
        for conta in ex.contas:
            fin.excluir_conta_receber(db, conta)
        for reserva, _ in ex.reservas_apagar:
            r = agenda_servico.excluir_reserva(db, reserva.id)
            sessoes_excluidas += 1 if r.get("sessao_apagada") else 0
        db.execute(update(Reserva).where(Reserva.contrato_id == c.id).values(contrato_id=None))
        db.execute(update(AulaAvaliativa).where(AulaAvaliativa.contrato_id == c.id).values(contrato_id=None))
        db.execute(update(WhatsappMensagem).where(WhatsappMensagem.contrato_id == c.id).values(contrato_id=None))
        from app.modules.agenda.models import WhatsappAgendamentoLog

        db.execute(update(WhatsappAgendamentoLog).where(WhatsappAgendamentoLog.contrato_id == c.id).values(contrato_id=None))
        if doc is not None:
            if status_val(c.status_assinatura) == StatusAssinatura.NAO_ASSINADO:
                arquivos_apagar.append(doc.arquivo_path)
                db.delete(doc)
            else:  # contrato assinado: o PDF assinado fica no prontuário do aluno
                doc.contrato_id = None
        db.execute(update(AlunoDocumento).where(AlunoDocumento.contrato_id == c.id).values(contrato_id=None))
        snapshot = {"aluno_id": c.aluno_id, "plano_id": c.plano_id, "data_inicio": c.data_inicio.isoformat(),
                    "data_fim": c.data_fim.isoformat(), "valor_total": str(c.valor_total), "status_assinatura": status_val(c.status_assinatura)}
        db.flush()
        db.delete(c)
        db.flush()
        ctx.auditar("contrato.excluir", "contrato", contrato_id, descricao=f"Contrato nº {numero} excluído", antes=snapshot,
                    depois={"parcelas_excluidas": len(ex.contas), "aulas_excluidas": len(ex.reservas_apagar),
                            "aulas_mantidas": len(ex.reservas_manter), "sessoes_excluidas": sessoes_excluidas})
        db.commit()
    except fin.ErroDeNegocio as e:
        db.rollback()
        raise ErroContrato(e.mensagem, 409) from e
    except BaseException:
        db.rollback()
        raise
    for rel in arquivos_apagar:
        storage.remover(rel)
    return sc.ExclusaoOut(contas_excluidas=len(ex.contas), reservas_excluidas=len(ex.reservas_apagar),
                          reservas_mantidas=len(ex.reservas_manter), sessoes_excluidas=sessoes_excluidas)


# -------------------------------------------------------------------------------------------------------- agenda
def _contexto_agenda(db: Session, c: Contrato, a_partir_de: date | None, hoje: date):
    plano = db.get(Plano, c.plano_id)
    if plano is None:
        raise ErroContrato("O plano do contrato não existe mais.", 409)
    if plano.avulso:
        raise ErroContrato("Contrato de plano avulso não tem agenda automática.", 409)
    rec = _recorrencia(c)
    inicio = max(a_partir_de or hoje, c.data_inicio)
    if dom.esta_vencido(c.data_fim, hoje) or inicio > c.data_fim:
        raise ErroContrato("O contrato já terminou: não há datas para agendar.", 409)
    fim = dom_agenda.fim_da_agenda_do_contrato(rec, inicio, c.data_fim)
    por_semana = dom_agenda.aulas_por_semana_do_contrato(rec, plano.aulas_por_semana)
    return plano, rec, inicio, fim, por_semana


def agenda_opcoes(db: Session, contrato_id: int, *, hoje: date | None = None) -> sc.AgendaOpcoes:
    """Horários que o aluno pode escolher: funcionamento do serviço menos bloqueios e lotação (`domain.agenda`). Só LÊ."""
    hoje = _hoje(hoje)
    c = obter(db, contrato_id)
    plano, rec, inicio, fim, por_semana = _contexto_agenda(db, c, None, hoje)
    slots = agenda_servico.calcular_slots(db, unidade_id=c.unidade_id, tipo_servico_id=plano.tipo_servico_id, inicio=inicio, fim=fim)
    nomes = dict(db.execute(select(Profissional.id, Profissional.nome)).all())
    saida = [
        sc.SlotOut(dia_semana=d, inicio=f"{i:%H:%M}", fim=f"{f:%H:%M}", valor=dom_agenda.valor_do_slot(d, i, f),
                   profissionais=[sc.PessoaRef(id=p, nome=nomes.get(p, "?")) for p in profs])
        for (d, i, f), profs in sorted(slots.items())
    ]
    futuras = db.execute(
        select(AulaSessao.data).join(Reserva, Reserva.aula_sessao_id == AulaSessao.id).where(
            Reserva.contrato_id == c.id, Reserva.status.in_([StatusReserva.RESERVADA, StatusReserva.PENDENTE]), AulaSessao.data >= hoje)
    ).scalars().all()
    return sc.AgendaOpcoes(
        contrato_id=c.id, aulas_por_semana=plano.aulas_por_semana, exatamente=por_semana, inicio=inicio, fim=fim, slots=saida,
        ja_agendadas=len(futuras), dias_semana_agendados=sorted({d.weekday() for d in futuras}),
        mensagem=None if saida else "Nenhum horário disponível: confira os horários de funcionamento, bloqueios e a lotação.",
    )


def gerar_agenda(ctx: Contexto, contrato_id: int, dados: sc.AgendaIn, *, hoje: date | None = None) -> sc.AgendaOut:
    """Gera as reservas do contrato (1 horário por dia da semana, exatamente `aulas_por_semana`), gravando
    `contrato_id` em cada uma. Escolha inválida: nada é criado. Conflito de vaga/bloqueio é LISTADO e o resto segue."""
    db = ctx.db
    hoje = _hoje(hoje)
    c = obter(db, contrato_id)
    plano, rec, inicio, _fim, _por_semana = _contexto_agenda(db, c, dados.a_partir_de, hoje)
    selecoes = []
    for s in dados.selecoes:
        try:
            selecoes.append(dom_agenda.SelecaoHorario(
                dia_semana=s.dia_semana, inicio=time.fromisoformat(s.inicio), fim=time.fromisoformat(s.fim), profissional_id=s.profissional_id))
        except ValueError:
            raise ErroContrato("Horário inválido na seleção.", 422) from None
    try:
        res = agenda_servico.gerar_agenda_do_contrato(
            db, aluno_id=c.aluno_id, contrato_id=c.id, unidade_id=c.unidade_id, tipo_servico_id=plano.tipo_servico_id,
            data_inicio=inicio, data_fim=c.data_fim, selecoes=selecoes, aulas_por_semana=plano.aulas_por_semana, recorrencia_contrato=rec)
        ctx.auditar("contrato.agenda", "contrato", c.id, descricao=f"Agenda do contrato nº {numero_do_contrato(c)}: {len(res.reservas_criadas)} aula(s) reservada(s)",
                    depois={"reservas": len(res.reservas_criadas), "conflitos": len(res.conflitos),
                            "horarios": [f"{s.dia_semana}|{s.inicio}|{s.profissional_id}" for s in dados.selecoes]})
        db.commit()
    except agenda_servico.ErroAgenda as e:
        db.rollback()
        raise ErroContrato(e.mensagem, e.status, e.dados) from e
    except BaseException:
        db.rollback()
        raise
    return sc.AgendaOut(reservas_criadas=len(res.reservas_criadas), sessoes_criadas=res.sessoes_criadas, ja_existentes=res.ja_existentes,
                        conflitos=res.conflitos, mensagem_conflitos=res.mensagem_conflitos)


# ----------------------------------------------------------------------------------- links, e-mail e WhatsApp
def _base_site() -> str:
    return settings.frontend_url.rstrip("/")


def emitir_link_assinatura(contrato_id: int, *, agora_s: float | None = None) -> sc.LinkOut:
    t = tokens.emitir_contrato(contrato_id, agora_s=agora_s)
    return sc.LinkOut(url=f"{_base_site()}/assinar/contrato/{t.token}", expira_em=t.expira_em,
                      pdf_url=f"{_base_site()}/bff/assinar/contrato/{t.token}/pdf")


def link_assinatura(ctx: Contexto, contrato_id: int) -> sc.LinkOut:
    c = obter(ctx.db, contrato_id)
    if status_val(c.status_assinatura) != StatusAssinatura.NAO_ASSINADO:
        raise ErroContrato("Este contrato já está assinado.")
    link = emitir_link_assinatura(c.id)
    ctx.auditar("contrato.link", "contrato", c.id, descricao=f"Link de assinatura do contrato nº {numero_do_contrato(c)} gerado")
    ctx.db.commit()
    return link


def primeiro_nome(nome: str) -> str:
    return (nome or "").split(" ")[0] or "aluno(a)"


def enviar_email(ctx: Contexto, contrato_id: int) -> sc.EnvioOut:
    """Manda por e-mail o link de assinatura e o PDF em anexo (contrato já assinado: só a cópia assinada)."""
    db = ctx.db
    c = obter(db, contrato_id)
    aluno = db.get(Aluno, c.aluno_id)
    if not aluno or not (aluno.email or "").strip():
        raise ErroContrato("O aluno não tem e-mail cadastrado.", 422)
    estudio = nome_do_estudio(db)
    numero = numero_do_contrato(c)
    assinado = status_val(c.status_assinatura) != StatusAssinatura.NAO_ASSINADO
    pdf = gerar_pdf_do_contrato(db, c)
    if assinado:
        corpo = (f"Olá, {primeiro_nome(aluno.nome)}!\n\nSegue em anexo a cópia do seu contrato nº {numero}, já assinado.\n\n{estudio}")
        assunto = f"Contrato nº {numero} assinado - {estudio}"
    else:
        link = emitir_link_assinatura(c.id)
        corpo = (f"Olá, {primeiro_nome(aluno.nome)}!\n\nSeu contrato nº {numero} está pronto. Para assinar digitalmente, acesse:\n"
                 f"{link.url}\n\nO link vale por 7 dias. O PDF do contrato segue em anexo.\n\n{estudio}")
        assunto = f"Contrato nº {numero} para assinatura - {estudio}"
    ok = core_email.enviar([aluno.email.strip()], assunto, corpo, db=db, anexos=[(f"contrato-{numero}.pdf", pdf, "application/pdf")])
    if not ok:
        raise ErroContrato("Não foi possível enviar o e-mail agora. Confira a configuração de e-mail e tente de novo.", 502)
    ctx.auditar("contrato.enviar_email", "contrato", c.id, descricao=f"Contrato nº {numero} enviado por e-mail a {aluno.nome}",
                depois={"destino": aluno.email.strip()})
    db.commit()
    return sc.EnvioOut(canal="email", destino=aluno.email.strip(), mensagem="Contrato enviado por e-mail.")


def enviar_whatsapp(ctx: Contexto, contrato_id: int) -> sc.EnvioOut:
    db = ctx.db
    c = obter(db, contrato_id)
    if _enviador_whatsapp is None:
        raise ErroContrato("WhatsApp ainda não configurado.", 503)
    aluno = db.get(Aluno, c.aluno_id)
    telefone = alunos_servico.telefone_principal(db, c.aluno_id)
    if not aluno or not telefone:
        raise ErroContrato("O aluno não tem telefone cadastrado.", 422)
    numero = numero_do_contrato(c)
    estudio = nome_do_estudio(db)
    assinado = status_val(c.status_assinatura) != StatusAssinatura.NAO_ASSINADO
    link = emitir_link_assinatura(c.id)
    texto = (f"Olá, {primeiro_nome(aluno.nome)}! Segue a cópia do seu contrato nº {numero}, já assinado. {estudio}" if assinado else
             f"Olá, {primeiro_nome(aluno.nome)}! Seu contrato nº {numero} está pronto. Assine por aqui (vale por 7 dias): {link.url} - {estudio}")
    _enviar_whatsapp(db, MensagemWhatsapp(tipo="contrato_assinado" if assinado else "contrato_assinatura", aluno_id=aluno.id,
                                          telefone=telefone, texto=texto, contrato_id=c.id,
                                          link=None if assinado else link.url, pdf_url=link.pdf_url, pdf_nome=f"contrato-{numero}.pdf"))
    ctx.auditar("contrato.enviar_whatsapp", "contrato", c.id, descricao=f"Contrato nº {numero} enviado por WhatsApp a {aluno.nome}")
    db.commit()
    return sc.EnvioOut(canal="whatsapp", destino=alunos_servico.formatar_telefone(telefone), mensagem="Contrato enviado por WhatsApp.")


def notificar_assinatura(db: Session, c: Contrato) -> None:
    """Confirmação ao aluno depois de assinar (e-mail com a cópia e WhatsApp pelo ponto de extensão). Nunca levanta."""
    try:
        aluno = db.get(Aluno, c.aluno_id)
        if aluno is None:
            return
        numero = numero_do_contrato(c)
        estudio = nome_do_estudio(db)
        if (aluno.email or "").strip():
            core_email.enviar([aluno.email.strip()], f"Contrato nº {numero} assinado - {estudio}",
                              f"Olá, {primeiro_nome(aluno.nome)}!\n\nRecebemos a assinatura do seu contrato nº {numero}. "
                              f"A cópia assinada segue em anexo.\n\n{estudio}",
                              db=db, anexos=[(f"contrato-{numero}.pdf", gerar_pdf_do_contrato(db, c), "application/pdf")])
        telefone = alunos_servico.telefone_principal(db, c.aluno_id)
        if _enviador_whatsapp is not None and telefone:
            link = emitir_link_assinatura(c.id)
            _enviar_whatsapp(db, MensagemWhatsapp(
                tipo="contrato_assinado", aluno_id=aluno.id, telefone=telefone, contrato_id=c.id, pdf_url=link.pdf_url,
                pdf_nome=f"contrato-{numero}.pdf",
                texto=f"Olá, {primeiro_nome(aluno.nome)}! Recebemos a assinatura do seu contrato nº {numero}. Obrigado! {estudio}"))
    except Exception:  # noqa: BLE001 - confirmação é cortesia: a assinatura já valeu
        log.warning("Não foi possível enviar a confirmação de assinatura do contrato %s", c.id, exc_info=True)


# ------------------------------------------------------------------------------------------------- assinatura
def decodificar_png(data_url: str) -> bytes:
    """PNG do canvas (`data:image/png;base64,...`). Reaproveita a validação do cadastro de alunos."""
    from fastapi import HTTPException

    try:
        return alunos_servico.decodificar_assinatura(data_url)
    except HTTPException as e:
        raise ErroContrato(str(e.detail), 422) from e


def validar_assinante(nome: str, documento: str) -> tuple[str, str]:
    nome = " ".join((nome or "").split())
    if len(nome) < 3:
        raise ErroContrato("Informe o nome completo de quem assina.", 422)
    if not validar_cpf(documento):
        raise ErroContrato("CPF inválido. Confira os 11 dígitos.", 422)
    return nome, formatar_cpf(documento)


def aplicar_assinatura(db: Session, c: Contrato, *, nome: str, documento: str, assinatura_png: str, ip: str | None,
                       status: StatusAssinatura, agora_: datetime | None = None) -> None:
    """Grava a assinatura UMA vez: o UPDATE só vale se o contrato ainda está NAO_ASSINADO (duas assinaturas simultâneas:
    uma passa, a outra recebe 409). Não faz commit."""
    nome, doc_fmt = validar_assinante(nome, documento)
    png = decodificar_png(assinatura_png)
    if not png.startswith(PNG_MAGICO):
        raise ErroContrato("A assinatura deve ser uma imagem PNG.", 422)
    quando = agora_ or agora()
    rel = f"{CAT_ASSINATURAS}/contrato/contrato_{c.id}.png"
    r = db.execute(update(Contrato).where(Contrato.id == c.id, Contrato.status_assinatura == StatusAssinatura.NAO_ASSINADO).values(
        status_assinatura=status, assinado_em=quando, assinatura_nome=nome, assinatura_documento=doc_fmt, assinatura_ip=ip,
        assinatura_path=rel, atualizado_em=quando))
    if r.rowcount != 1:  # outra assinatura ganhou a corrida: a imagem dela NÃO é tocada
        db.rollback()
        raise ErroContrato("Este contrato já foi assinado.", 409)
    try:
        storage.salvar(CAT_ASSINATURAS, "assinatura.png", png, subpasta="contrato", nome_base=f"contrato_{c.id}", substituir=True)
    except storage.ArquivoInvalido as e:
        db.rollback()
        raise ErroContrato(str(e), 422) from e
    db.refresh(c)


def assinar_local(ctx: Contexto, contrato_id: int, dados: sc.AssinaturaLocalIn) -> sc.ContratoDetalhe:
    """Assinatura na recepção (usuário logado, canvas na tela do estúdio)."""
    db = ctx.db
    c = obter(db, contrato_id)
    if status_val(c.status_assinatura) != StatusAssinatura.NAO_ASSINADO:
        raise ErroContrato("Este contrato já foi assinado.", 409)
    aplicar_assinatura(db, c, nome=dados.nome, documento=dados.documento, assinatura_png=dados.assinatura, ip=ctx.ip,
                       status=StatusAssinatura.ASSINADO)
    ctx.auditar("contrato.assinar_local", "contrato", c.id, descricao=f"Contrato nº {numero_do_contrato(c)} assinado na recepção por {c.assinatura_nome}",
                depois={"nome": c.assinatura_nome, "documento": c.assinatura_documento, "ip": ctx.ip})
    db.commit()
    atualizar_pdf_guardado(db, c)
    db.commit()
    notificar_assinatura(db, c)
    return detalhe(db, c)
