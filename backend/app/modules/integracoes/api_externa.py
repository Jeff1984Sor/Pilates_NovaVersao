"""API de integração externa (`/api/integracao/*`): mesmos caminhos e formatos do sistema antigo (`api/main.py` 211-380).

Autenticação: `X-API-Key: <token>` ou `Authorization: Bearer <token>` com token ATIVO (ver `tokens.py`). Cada token tem
limite de requisições por minuto e falhas de autenticação são limitadas por IP. Respostas só levam os campos do contrato.

Diferenças deliberadas do antigo (todas por segurança ou coerência com o modelo novo; ver docs/progresso-integracoes.md):
- o token não é mais guardado em claro (hash SHA-256); token migrado sem valor precisa ser regenerado;
- `ATRASADO` é derivado (aberta e vencida), então `status=aberto` não inclui vencidas e `status=atrasado` as inclui;
- busca por telefone compara com o número normalizado (o antigo não achava telefones gravados com máscara);
- `contrato_id` da mensagem só vale se for contrato do próprio aluno;
- 422 de validação sai no formato do app novo (`detail` em texto + `erros`), não na lista do FastAPI.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit, ratelimit
from app.core.db import agora, get_db
from app.domain.documentos import formatar_cpf
from app.domain.financeiro import hoje_de_negocio
from app.domain.telefone import chave_telefone
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, AlunoTelefone, DirecaoMensagem, StatusAluno, WhatsappMensagem
from app.modules.cadastros.models import Plano, Profissional, TipoServico, Unidade
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber, StatusReceber
from app.modules.integracoes import tokens

FUSO = ZoneInfo("America/Sao_Paulo")
#: requisições por minuto de cada token
LIMITE_POR_TOKEN = 120
#: tentativas de autenticação FALHAS por IP, em 5 minutos
LIMITE_FALHAS_POR_IP = 20

_MESES = ["", "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
          "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
_STATUS_FATURA = {"aberto", "pago", "atrasado", "cancelado"}


def hoje() -> date:
    """Data de negócio (São Paulo). Isolada para os testes fixarem o dia."""
    return hoje_de_negocio(agora())


# ----------------------------------------------------------------------------------------------- autenticação
class TokenAutenticado(BaseModel):
    id: int
    nome: str


def _recusar(request: Request, db: Session, detalhe: str) -> None:
    ratelimit.verificar(request, "integracao-falha", LIMITE_FALHAS_POR_IP, 300, db=db)
    raise HTTPException(401, detalhe, headers={"WWW-Authenticate": "Bearer"})


def autenticar_api_key(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenAutenticado:
    valor = tokens.valor_do_pedido(x_api_key, authorization)
    if not valor:
        _recusar(request, db, "API key ausente")
    t = tokens.autenticar(db, valor)
    if t is None:
        _recusar(request, db, "API key invalida")
    ratelimit.verificar(request, "integracao-token", LIMITE_POR_TOKEN, 60, chave=str(t.id), db=db)
    return TokenAutenticado(id=t.id, nome=t.nome)


Integrador = Annotated[TokenAutenticado, Depends(autenticar_api_key)]
DB = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/integracao", tags=["integracao (API externa)"])


# ----------------------------------------------------------------------------------------------- formatos
class AlunoPayload(BaseModel):
    id: int
    cdAluno: int | None
    dsNome: str
    dsCPF: str | None
    dsEmail: str
    dsTelefone: str | None
    status: str


class FaturaPayload(BaseModel):
    id: int
    cdAluno: int
    contrato_id: int | None
    descricao: str
    competencia: str | None
    valor: float
    vencimento: date
    dt_pagamento: date | None
    status: str


class ContratoPayload(BaseModel):
    id: int
    cdContrato: int | None
    cdAluno: int
    plano: str | None
    profissional: str | None
    unidade: str | None
    dt_inicio: date
    dt_fim: date
    status: str
    valor_parcela: float | None
    valor_total: float | None


class AulaPayload(BaseModel):
    reserva_id: int
    cdAluno: int
    data: date | None
    hora_inicio: time | None
    hora_fim: time | None
    tipo_servico: str | None
    profissional: str | None
    unidade: str | None
    status: str


class AulaAmanhaPayload(AulaPayload):
    dsNome: str
    dsTelefone: str | None


class MensagemIn(BaseModel):
    cdAluno: int
    direcao: str = "recebida"  # "recebida" (cliente -> estúdio) ou "enviada"
    texto: str = Field(min_length=1, max_length=4000)
    telefone: str | None = Field(default=None, max_length=30)
    data_iso: datetime | None = None
    contrato_id: int | None = None


# ----------------------------------------------------------------------------------------------- utilidades
def _descricao_fatura(competencia: str | None) -> str:
    if competencia and "-" in competencia:
        try:
            ano, mes = competencia.split("-")[:2]
            return f"Mensalidade {_MESES[int(mes)]}/{ano}"
        except (ValueError, IndexError):
            pass
    return "Mensalidade"


def _telefone_exibido(t: AlunoTelefone) -> str:
    return t.numero_original or t.numero


def _telefones_principais(db: Session, aluno_ids: list[int]) -> dict[int, str]:
    """Primeiro telefone (ordem, id) de cada aluno."""
    if not aluno_ids:
        return {}
    saida: dict[int, str] = {}
    for t in db.scalars(select(AlunoTelefone).where(AlunoTelefone.aluno_id.in_(aluno_ids)).order_by(
            AlunoTelefone.aluno_id, AlunoTelefone.ordem, AlunoTelefone.id)):
        saida.setdefault(t.aluno_id, _telefone_exibido(t))
    return saida


def _payload(a: Aluno, telefone: str | None) -> AlunoPayload:
    return AlunoPayload(
        id=a.id, cdAluno=a.codigo_legado, dsNome=a.nome, dsCPF=formatar_cpf(a.cpf) if a.cpf else None,
        dsEmail=a.email or "", dsTelefone=telefone, status=StatusAluno(a.status).value,
    )


def _aluno_por_codigo(db: Session, cd: int) -> Aluno | None:
    return db.scalar(select(Aluno).where(Aluno.codigo_legado == cd))


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ----------------------------------------------------------------------------------------------- alunos
@router.get("/alunos/por-telefone", response_model=AlunoPayload)
def aluno_por_telefone(_t: Integrador, db: DB, telefone: str = Query(...)):
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        raise HTTPException(400, "Telefone invalido")
    alvo = chave_telefone(telefone)
    if alvo is None:
        raise HTTPException(404, "Aluno nao encontrado")
    nucleo = digitos[-8:]
    candidatos = db.scalars(
        select(AlunoTelefone).where(AlunoTelefone.numero.contains(nucleo, autoescape=True))
        .order_by(AlunoTelefone.aluno_id, AlunoTelefone.ordem, AlunoTelefone.id)
    )
    for t in candidatos:
        if chave_telefone(t.numero) == alvo:
            aluno = db.get(Aluno, t.aluno_id)
            if aluno:
                return _payload(aluno, _telefone_exibido(t))
    raise HTTPException(404, "Aluno nao encontrado")


@router.get("/alunos/por-codigo/{cd_aluno}", response_model=AlunoPayload)
def aluno_por_codigo(cd_aluno: int, _t: Integrador, db: DB):
    aluno = _aluno_por_codigo(db, cd_aluno)
    if not aluno:
        raise HTTPException(404, "Aluno nao encontrado")
    return _payload(aluno, _telefones_principais(db, [aluno.id]).get(aluno.id))


@router.get("/alunos", response_model=list[AlunoPayload])
def listar_alunos(_t: Integrador, db: DB, nome: str | None = None, status: str | None = None,
                  limit: int = Query(50, ge=1, le=200)):
    consulta = select(Aluno)
    if nome:
        consulta = consulta.where(Aluno.nome.ilike(f"%{_escapar_like(nome)}%", escape="\\"))
    if status:
        consulta = consulta.where(Aluno.status == status.upper())
    alunos = list(db.scalars(consulta.order_by(Aluno.nome, Aluno.id).limit(limit)))
    tels = _telefones_principais(db, [a.id for a in alunos])
    return [_payload(a, tels.get(a.id)) for a in alunos]


# ----------------------------------------------------------------------------------------------- faturas
@router.get("/faturas", response_model=list[FaturaPayload])
def listar_faturas(_t: Integrador, db: DB, cdAluno: int = Query(...),
                   status: str | None = Query(None, description="aberto|pago|atrasado|cancelado")):
    consulta = (
        select(ContaReceber).join(Contrato, Contrato.id == ContaReceber.contrato_id)
        .join(Aluno, Aluno.id == Contrato.aluno_id).where(Aluno.codigo_legado == cdAluno)
    )
    h = hoje()
    if status:
        s = status.strip().lower()
        if s == "aberto":  # ATRASADO é derivado: aberta e vencida
            consulta = consulta.where(ContaReceber.status == StatusReceber.ABERTO, ContaReceber.vencimento >= h)
        elif s == "atrasado":
            consulta = consulta.where(ContaReceber.status == StatusReceber.ABERTO, ContaReceber.vencimento < h)
        elif s in ("pago", "cancelado"):
            consulta = consulta.where(ContaReceber.status == s.upper())
        else:
            consulta = consulta.where(False)
    saida = []
    for cr in db.scalars(consulta.order_by(ContaReceber.vencimento, ContaReceber.id)):
        st = StatusReceber(cr.status).value.lower()
        if st == "aberto" and cr.vencimento < h:
            st = "atrasado"
        saida.append(FaturaPayload(
            id=cr.id, cdAluno=cdAluno, contrato_id=cr.contrato_id, descricao=_descricao_fatura(cr.competencia),
            competencia=cr.competencia or None, valor=float(cr.valor), vencimento=cr.vencimento,
            dt_pagamento=cr.pagamento, status=st,
        ))
    return saida


# ----------------------------------------------------------------------------------------------- contratos
def _contratos_do_aluno(db: Session, cd_aluno: int):
    return (
        select(Contrato, Plano.nome, Profissional.nome, Unidade.nome)
        .join(Aluno, Aluno.id == Contrato.aluno_id)
        .outerjoin(Plano, Plano.id == Contrato.plano_id)
        .outerjoin(Profissional, Profissional.id == Contrato.profissional_id)
        .outerjoin(Unidade, Unidade.id == Contrato.unidade_id)
        .where(Aluno.codigo_legado == cd_aluno)
    )


def _contrato_payload(c: Contrato, cd_aluno: int, plano, prof, unidade) -> ContratoPayload:
    return ContratoPayload(
        id=c.id, cdContrato=c.codigo_legado, cdAluno=cd_aluno, plano=plano, profissional=prof, unidade=unidade,
        dt_inicio=c.data_inicio, dt_fim=c.data_fim, status=c.status_assinatura.value,
        valor_parcela=float(c.valor_parcela) if c.valor_parcela is not None else None,
        valor_total=float(c.valor_total) if c.valor_total is not None else None,
    )


@router.get("/contratos/ativo", response_model=ContratoPayload)
def contrato_ativo(_t: Integrador, db: DB, cdAluno: int = Query(...)):
    """NOVO (não existia no antigo): o contrato vigente hoje (início <= hoje <= fim); o mais recente se houver vários."""
    h = hoje()
    linha = db.execute(
        _contratos_do_aluno(db, cdAluno).where(Contrato.data_inicio <= h, Contrato.data_fim >= h)
        .order_by(Contrato.data_fim.desc(), Contrato.id.desc()).limit(1)
    ).first()
    if not linha:
        raise HTTPException(404, "Contrato ativo nao encontrado")
    return _contrato_payload(linha[0], cdAluno, linha[1], linha[2], linha[3])


@router.get("/contratos", response_model=list[ContratoPayload])
def listar_contratos(_t: Integrador, db: DB, cdAluno: int = Query(...)):
    linhas = db.execute(_contratos_do_aluno(db, cdAluno).order_by(Contrato.data_fim.desc(), Contrato.id.desc())).all()
    return [_contrato_payload(c, cdAluno, p, pr, u) for c, p, pr, u in linhas]


# ----------------------------------------------------------------------------------------------- aulas
def _consulta_aulas():
    return (
        select(Reserva, AulaSessao, Aluno, TipoServico.nome, Profissional.nome, Unidade.nome)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .join(Aluno, Aluno.id == Reserva.aluno_id)
        .outerjoin(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
        .outerjoin(Unidade, Unidade.id == AulaSessao.unidade_id)
    )


def _aula_campos(r: Reserva, s: AulaSessao, cd: int, servico, prof, unidade) -> dict:
    return dict(reserva_id=r.id, cdAluno=cd, data=s.data, hora_inicio=s.hora_inicio, hora_fim=s.hora_fim,
                tipo_servico=servico, profissional=prof, unidade=unidade, status=StatusReserva(r.status).value)


@router.get("/aulas/amanha", response_model=list[AulaAmanhaPayload])
def aulas_de_amanha(_t: Integrador, db: DB):
    """NOVO (não existia no antigo): reservas ativas (RESERVADA) de amanhã, para lembretes do chatbot."""
    amanha = hoje() + timedelta(days=1)
    linhas = db.execute(
        _consulta_aulas().where(AulaSessao.data == amanha, Reserva.status == StatusReserva.RESERVADA)
        .order_by(AulaSessao.hora_inicio, Reserva.id).limit(500)
    ).all()
    tels = _telefones_principais(db, [a.id for _, _, a, *_ in linhas])
    return [
        AulaAmanhaPayload(**_aula_campos(r, s, a.codigo_legado, sv, pr, un), dsNome=a.nome, dsTelefone=tels.get(a.id))
        for r, s, a, sv, pr, un in linhas
    ]


@router.get("/aulas", response_model=list[AulaPayload])
def listar_aulas(_t: Integrador, db: DB, cdAluno: int = Query(...), apenas_proximas: bool = False,
                 limit: int = Query(50, ge=1, le=200)):
    consulta = _consulta_aulas().where(Aluno.codigo_legado == cdAluno)
    if apenas_proximas:
        consulta = consulta.where(AulaSessao.data >= hoje())
    linhas = db.execute(consulta.order_by(AulaSessao.data.desc(), AulaSessao.hora_inicio.desc(), Reserva.id.desc())
                        .limit(limit)).all()
    return [AulaPayload(**_aula_campos(r, s, cdAluno, sv, pr, un)) for r, s, _a, sv, pr, un in linhas]


# ----------------------------------------------------------------------------------------------- WhatsApp (escrita)
@router.post("/whatsapp-mensagens")
def gravar_mensagem_whatsapp(dados: MensagemIn, t: Integrador, db: DB):
    """Salva uma mensagem de WhatsApp (recebida/enviada) no histórico do aluno."""
    aluno = _aluno_por_codigo(db, dados.cdAluno)
    if not aluno:
        raise HTTPException(404, "Aluno nao encontrado")
    direcao = (dados.direcao or "").strip().lower()
    if direcao not in ("recebida", "enviada"):
        raise HTTPException(400, "direcao deve ser 'recebida' ou 'enviada'")
    contrato_id = None
    if dados.contrato_id and db.scalar(
            select(Contrato.id).where(Contrato.id == dados.contrato_id, Contrato.aluno_id == aluno.id)):
        contrato_id = dados.contrato_id
    quando = dados.data_iso or agora()
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=FUSO)
    quando = quando.astimezone(UTC)
    m = WhatsappMensagem(
        aluno_id=aluno.id, contrato_id=contrato_id, tipo="manual",
        direcao=DirecaoMensagem(direcao), telefone=(dados.telefone or "")[:20] or None, mensagem=dados.texto,
        status="received" if direcao == "recebida" else "sent", enviado_em=quando,
    )
    db.add(m)
    db.flush()
    audit.registrar(db, usuario=None, acao="integracao.whatsapp_mensagem", entidade="whatsapp_mensagem",
                    entidade_id=m.id, descricao=f"Mensagem {direcao} gravada pelo token '{t.nome}' (aluno {aluno.id})")
    db.commit()
    return {"id": m.id, "cdAluno": aluno.codigo_legado, "direcao": direcao, "enviado_em": quando.isoformat()}



