"""TotalPass (R14): cliente HTTP, processamento dos eventos (webhook e sincronização) e teste de conexão.

Regras portadas de `views._process_totalpass_payload` (4305) e `totalpass_service.py`, com estas diferenças deliberadas:
- o webhook EXIGE token (o antigo aceitava qualquer POST se nenhum token estivesse configurado): ver `routes.py`;
- idempotência: o mesmo `(evento, slot, status, documento)` já processado não é processado de novo;
- CPF do payload precisa ser válido para criar aluno (o antigo criava aluno com CPF lixo);
- cancelamento NÃO cria aluno nem aula: se não houver reserva, não há o que cancelar;
- a aula nasce sem profissional e herda a capacidade da unidade (a capacidade é conferida pelo `ocupar_vaga` atômico).

O cliente HTTP é configurável: `definir_fabrica_cliente(fn)` troca a fábrica (os testes injetam um `httpx.MockTransport`;
nenhum teste chama a internet). A URL base vem de `TOTALPASS_BOOKING_BASE_URL` (não é segredo; padrão oficial).
Chaves e token do webhook ficam cifrados no banco e NUNCA aparecem em log, resposta ou auditoria.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit, segredos
from app.core.db import agora as agora_utc
from app.domain.documentos import so_digitos, validar_cpf
from app.domain.financeiro import hoje_de_negocio
from app.domain.telefone import normalizar_telefone_br
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, AlunoTelefone, StatusAluno
from app.modules.cadastros.models import TipoServico, proximo_codigo
from app.modules.integracoes.models import TotalpassConfig, TotalpassEvento

log = logging.getLogger(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")
URL_BASE_PADRAO = "https://booking-api.totalpass.com"
STATUS_CANCELAMENTO = {"canceled", "cancelled", "inactive"}
RESULTADOS_FINAIS = ("processado", "cancelado")  # não reprocessar


class ErroTotalpass(Exception):
    """Falha com mensagem pronta para o usuário (sem segredo)."""


class _Descartado(Exception):
    pass


# ------------------------------------------------------------------------------------------------ segredos
def cifrar(valor: str) -> str:
    return segredos.cifrar_texto(valor.strip()).decode()


def decifrar(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return segredos.decifrar_texto(valor.encode())
    except segredos.SegredoInvalido:
        return None


def final_do_segredo(valor_cifrado: str | None) -> str | None:
    v = decifrar(valor_cifrado)
    return v[-4:] if v else None


# ------------------------------------------------------------------------------------------------ cliente HTTP
class ClienteTotalpass:
    def __init__(self, base_url: str | None = None, *, transport: httpx.BaseTransport | None = None, timeout: float = 20):
        self.base_url = (base_url or os.environ.get("TOTALPASS_BOOKING_BASE_URL") or URL_BASE_PADRAO).rstrip("/")
        self._http = httpx.Client(transport=transport, timeout=timeout)

    def fechar(self) -> None:
        self._http.close()

    def autenticar(self, partner_api_key: str, place_api_key: str) -> str:
        resp = self._http.post(f"{self.base_url}/partner/auth",
                               json={"partner_api_key": partner_api_key, "place_api_key": place_api_key})
        resp.raise_for_status()
        dados = resp.json() if resp.content else {}
        token = (dados.get("token") or dados.get("access_token") or dados.get("jwt") or "") if isinstance(dados, dict) else ""
        if not token:
            raise ErroTotalpass("O TotalPass respondeu sem token de acesso.")
        return token

    def listar_slots(self, token: str, de: str, ate: str, place_id: str = "") -> list[dict]:
        params = {"slotDateFrom": de, "slotDateTo": ate}
        if place_id:
            params["placeId"] = place_id
        resp = self._http.get(f"{self.base_url}/partner/slot", params=params,
                              headers={"Authorization": f"Bearer {token}", "accept": "application/json"})
        resp.raise_for_status()
        dados = resp.json() if resp.content else {}
        if isinstance(dados, list):
            return [x for x in dados if isinstance(x, dict)]
        if isinstance(dados, dict):
            itens = dados.get("items") or dados.get("data") or dados.get("slots") or []
            return [x for x in itens if isinstance(x, dict)]
        return []


_fabrica: Callable[[], ClienteTotalpass] = ClienteTotalpass


def definir_fabrica_cliente(fabrica: Callable[[], ClienteTotalpass] | None) -> None:
    """Troca a fábrica do cliente (testes). `None` volta ao cliente real."""
    global _fabrica
    _fabrica = fabrica or ClienteTotalpass


def novo_cliente() -> ClienteTotalpass:
    return _fabrica()


def _traduzir_http(exc: Exception) -> ErroTotalpass:
    if isinstance(exc, ErroTotalpass):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (400, 401, 403):
            return ErroTotalpass("O TotalPass recusou as chaves informadas. Confira a chave do parceiro e a da unidade.")
        return ErroTotalpass(f"O TotalPass respondeu com erro {exc.response.status_code}. Tente de novo mais tarde.")
    if isinstance(exc, httpx.HTTPError):
        return ErroTotalpass("Não foi possível falar com o TotalPass. Confira a conexão e tente de novo.")
    return ErroTotalpass("Falha inesperada ao falar com o TotalPass.")


def _chaves(cfg: TotalpassConfig) -> tuple[str, str]:
    pk, lk = decifrar(cfg.partner_api_key_cifrado), decifrar(cfg.place_api_key_cifrado)
    if not pk or not lk:
        raise ErroTotalpass("Cadastre a chave do parceiro e a chave da unidade do TotalPass.")
    return pk, lk


def testar_conexao(cfg: TotalpassConfig, cliente: ClienteTotalpass | None = None) -> None:
    """Autentica no TotalPass com as chaves guardadas. Levanta `ErroTotalpass` (mensagem sem segredo)."""
    pk, lk = _chaves(cfg)
    c = cliente or novo_cliente()
    try:
        c.autenticar(pk, lk)
    except Exception as exc:  # noqa: BLE001 - traduzido para mensagem segura
        raise _traduzir_http(exc) from None
    finally:
        c.fechar()


# ------------------------------------------------------------------------------------------------ payload
def montar_payload_do_slot(slot: dict) -> dict:
    """Port de `_build_totalpass_payload_from_slot`: aceita o slot do `/partner/slot` ou já no formato do webhook."""
    if not isinstance(slot, dict):
        return {}
    if slot.get("event") or slot.get("user"):
        payload = dict(slot)
        payload["slot"] = slot.get("slot") or {}
        return payload
    g = slot.get
    return {
        "event": {"id": g("event_id") or g("eventId") or "", "title": g("event_title") or g("eventTitle") or g("title") or ""},
        "place": {"place": g("place_id") or g("placeId") or ""},
        "user": {
            "name": g("user_name") or g("userName") or "", "email": g("user_email") or g("userEmail") or "",
            "phone": g("phone") or g("userPhone") or "",
            "document_number": g("document_number") or g("documentNumber") or g("userDocument") or "",
            "document_type": "cpf",
        },
        "slot": {
            "id": g("slot_id") or g("id") or "", "status": g("status") or g("slot_status") or "",
            "date": g("date") or g("start_at") or g("startAt") or "",
            "start_time": g("start_time") or g("startTime") or g("time") or "",
        },
    }


def place_do_payload(payload: dict) -> str:
    place = payload.get("place") or {}
    if not isinstance(place, dict):
        return str(place)
    for chave in ("place", "id", "place_id", "uuid"):
        if place.get(chave):
            return str(place[chave])
    return ""


def _texto(v: Any, limite: int) -> str:
    return str(v or "").strip()[:limite]


def _data_e_hora(payload: dict) -> tuple[date, time]:
    slot = payload.get("slot") or {}
    data_bruta = _texto(slot.get("date") or slot.get("start_at") or slot.get("startAt"), 40)
    hora_bruta = _texto(slot.get("start_time") or slot.get("startTime") or slot.get("time"), 12)
    if not data_bruta:
        raise ErroTotalpass("Data não informada no payload.")
    try:
        if "T" in data_bruta:
            base = datetime.fromisoformat(data_bruta.replace("Z", "+00:00"))
            if base.tzinfo is not None:
                base = base.astimezone(FUSO).replace(tzinfo=None)
        else:
            base = datetime.strptime(data_bruta[:10], "%Y-%m-%d")
    except ValueError:
        raise ErroTotalpass("Data inválida no payload.") from None
    if hora_bruta:
        for formato in ("%H:%M", "%H:%M:%S"):
            try:
                h = datetime.strptime(hora_bruta, formato).time()
                break
            except ValueError:
                continue
        else:
            raise ErroTotalpass("Hora inválida no payload.")
        return base.date(), h.replace(second=0, microsecond=0)
    if base.time() == time.min:
        raise ErroTotalpass("Horário não informado no payload.")
    return base.date(), base.time().replace(second=0, microsecond=0)


# ------------------------------------------------------------------------------------------------ processamento
@dataclass
class Resultado:
    evento_id: int
    resultado: str  # processado | cancelado | descartado | erro | duplicado
    reserva_id: int | None = None
    mensagem: str | None = None

    @property
    def ok(self) -> bool:
        return self.resultado in ("processado", "cancelado", "duplicado")


def _resolver_servico(db: Session, cfg: TotalpassConfig, titulo: str) -> TipoServico:
    if titulo:
        base = select(TipoServico).where(TipoServico.ativo.is_(True))
        servico = db.scalars(base.where(func.lower(TipoServico.nome) == titulo.lower()).order_by(TipoServico.id)).first()
        if servico is None:
            like = "%" + titulo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            servico = db.scalars(base.where(TipoServico.nome.ilike(like, escape="\\")).order_by(TipoServico.id)).first()
        if servico:
            return servico
    if cfg.servico_padrao_id:
        padrao = db.get(TipoServico, cfg.servico_padrao_id)
        if padrao:
            return padrao
    raise ErroTotalpass("Tipo de serviço não encontrado. Cadastre o serviço com o mesmo nome do evento ou defina o serviço padrão.")


def _achar_aluno(db: Session, cpf: str) -> Aluno | None:
    return db.scalar(select(Aluno).where(Aluno.cpf == cpf)) if cpf else None


def _criar_aluno(db: Session, cfg: TotalpassConfig, user: dict, cpf: str) -> Aluno:
    if not cpf:
        raise ErroTotalpass("CPF não informado no payload; aluno não criado.")
    if not validar_cpf(cpf):
        raise ErroTotalpass("CPF inválido no payload; aluno não criado.")
    email = _texto(user.get("email"), 200)
    aluno = Aluno(
        nome=_texto(user.get("name"), 150) or "Aluno TotalPass", cpf=cpf, sem_cpf=False,
        email=email if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) else None,
        unidade_id=cfg.unidade_id, status=StatusAluno.ATIVO, codigo_legado=proximo_codigo(db, "aluno"),
    )
    db.add(aluno)
    db.flush()
    bruto = _texto(user.get("phone"), 30)
    canonico = normalizar_telefone_br(bruto)
    if canonico:
        db.add(AlunoTelefone(aluno_id=aluno.id, ordem=1, numero=canonico, numero_original=bruto))
    audit.registrar(db, usuario=None, acao="totalpass.aluno_criar", entidade="aluno", entidade_id=aluno.id,
                    descricao=f"Aluno {aluno.nome} criado automaticamente pelo TotalPass")
    return aluno


def _sessao_existente(db: Session, unidade_id: int, servico_id: int, dia: date, hora: time) -> AulaSessao | None:
    return db.scalars(select(AulaSessao).where(
        AulaSessao.unidade_id == unidade_id, AulaSessao.tipo_servico_id == servico_id,
        AulaSessao.profissional_id.is_(None), AulaSessao.data == dia, AulaSessao.hora_inicio == hora)).first()


def _executar(db: Session, cfg: TotalpassConfig, payload: dict, *, hoje: date, aplicar_somente_dia: bool) -> tuple[str, int | None]:
    dia, hora = _data_e_hora(payload)
    if aplicar_somente_dia and cfg.somente_dia and dia != hoje:
        raise _Descartado("Fora do dia atual.")
    unidade_id = cfg.unidade_id
    servico = _resolver_servico(db, cfg, _texto((payload.get("event") or {}).get("title"), 120))
    user = payload.get("user") or {}
    cpf = so_digitos(user.get("document_number"))[:20]
    cancelar = str((payload.get("slot") or {}).get("status") or "").lower() in STATUS_CANCELAMENTO

    if cancelar:
        aluno = _achar_aluno(db, cpf)
        sessao = _sessao_existente(db, unidade_id, servico.id, dia, hora)
        reserva = db.scalar(select(Reserva).where(Reserva.aluno_id == aluno.id, Reserva.aula_sessao_id == sessao.id)) \
            if aluno and sessao else None
        if reserva is None:
            return "cancelado", None
        agenda._trocar_status(db, reserva, StatusReserva.CANCELADA)  # libera a vaga; sem reposição (TotalPass)
        db.flush()
        audit.registrar(db, usuario=None, acao="totalpass.reserva_cancelar", entidade="reserva", entidade_id=reserva.id,
                        descricao=f"Reserva cancelada pelo TotalPass (aluno {reserva.aluno_id})")
        return "cancelado", reserva.id

    aluno = _achar_aluno(db, cpf)
    if aluno is None:
        if not cfg.criar_aluno_automatico:
            raise ErroTotalpass("Aluno não encontrado pelo CPF.")
        aluno = _criar_aluno(db, cfg, user, cpf)
    sessao, _ = agenda.obter_ou_criar_sessao(db, unidade_id=unidade_id, tipo_servico_id=servico.id, profissional_id=None,
                                             data=dia, hora_inicio=hora)
    reserva = db.scalar(select(Reserva).where(Reserva.aluno_id == aluno.id, Reserva.aula_sessao_id == sessao.id))
    if reserva is None:
        reserva = agenda.criar_reserva(db, aluno.id, sessao.id)
        acao = "totalpass.reserva_criar"
    elif StatusReserva(reserva.status) != StatusReserva.RESERVADA:
        agenda._trocar_status(db, reserva, StatusReserva.RESERVADA)  # pode falhar por lotação
        reserva.desmarcada_em = None
        reserva.reposicao_ate = None
        acao = "totalpass.reserva_reativar"
    else:
        return "processado", reserva.id
    db.flush()
    audit.registrar(db, usuario=None, acao=acao, entidade="reserva", entidade_id=reserva.id,
                    descricao=f"Reserva do aluno {aluno.id} na aula de {dia:%d/%m/%Y} {hora:%H:%M} (TotalPass)")
    return "processado", reserva.id


def processar_payload(
    db: Session, cfg: TotalpassConfig, payload: dict, *, origem: str = "webhook", hoje: date | None = None,
    aplicar_somente_dia: bool = True,
) -> Resultado:
    """Grava o evento e processa. Idempotente por (evento, slot, status, documento). Faz commit."""
    agora = agora_utc()
    hoje = hoje or hoje_de_negocio(agora)
    ev_info = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    slot_info = payload.get("slot") if isinstance(payload.get("slot"), dict) else {}
    user_info = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    payload = {**payload, "event": ev_info, "slot": slot_info, "user": user_info}
    event_id = _texto(ev_info.get("id"), 100)
    slot_id = _texto(slot_info.get("id"), 100)
    status_slot = _texto(slot_info.get("status"), 30)
    documento = so_digitos(user_info.get("document_number"))[:20]

    existente = db.scalars(select(TotalpassEvento).where(
        TotalpassEvento.event_id == event_id, TotalpassEvento.slot_id == slot_id, TotalpassEvento.status == status_slot,
        TotalpassEvento.documento_usuario == documento).order_by(TotalpassEvento.id.desc())).first()
    if existente is not None and existente.resultado in RESULTADOS_FINAIS:
        return Resultado(existente.id, "duplicado", existente.reserva_id, "Evento já processado.")
    ev = existente or TotalpassEvento(event_id=event_id, slot_id=slot_id, status=status_slot,
                                      documento_usuario=documento, recebido_em=agora)
    ev.payload, ev.origem, ev.erro, ev.resultado, ev.processado_em, ev.reserva_id = payload, origem, None, None, None, None
    db.add(ev)
    db.flush()

    resultado, reserva_id, mensagem = "erro", None, None
    try:
        with agenda.savepoint(db):
            resultado, reserva_id = _executar(db, cfg, payload, hoje=hoje, aplicar_somente_dia=aplicar_somente_dia)
    except _Descartado as exc:
        resultado, mensagem = "descartado", str(exc)
    except (ErroTotalpass, agenda.ErroAgenda) as exc:
        resultado, mensagem = "erro", str(exc.mensagem if isinstance(exc, agenda.ErroAgenda) else exc)
    except Exception:  # noqa: BLE001 - o evento fica registrado com erro genérico (sem expor detalhe interno)
        log.exception("Falha inesperada ao processar evento do TotalPass (evento %s)", ev.id)
        resultado, mensagem = "erro", "Falha inesperada ao processar o evento."
    ev.resultado, ev.erro, ev.reserva_id = resultado, mensagem, reserva_id
    if resultado in RESULTADOS_FINAIS:
        ev.processado_em = agora_utc()
    db.commit()
    return Resultado(ev.id, resultado, reserva_id, mensagem)


# ------------------------------------------------------------------------------------------------ sincronização
def sincronizar_dia(db: Session, cfg: TotalpassConfig, dia: date, cliente: ClienteTotalpass | None = None) -> dict:
    """Consulta `/partner/slot` do dia e processa cada slot como um evento. Devolve o resumo (contagens)."""
    pk, lk = _chaves(cfg)
    c = cliente or novo_cliente()
    try:
        token = c.autenticar(pk, lk)
        slots = c.listar_slots(token, dia.isoformat(), dia.isoformat(), cfg.place_id or "")
    except Exception as exc:  # noqa: BLE001
        raise _traduzir_http(exc) from None
    finally:
        c.fechar()
    resumo = {"dia": dia.isoformat(), "recebidos": len(slots), "processados": 0, "cancelados": 0, "descartados": 0,
              "duplicados": 0, "erros": 0}
    chave = {"processado": "processados", "cancelado": "cancelados", "descartado": "descartados",
             "duplicado": "duplicados", "erro": "erros"}
    for slot in slots:
        payload = montar_payload_do_slot(slot)
        if not place_do_payload(payload) and cfg.place_id:
            payload["place"] = {"place": cfg.place_id}
        r = processar_payload(db, cfg, payload, origem="sync", aplicar_somente_dia=False)
        resumo[chave[r.resultado]] += 1
    return resumo


def resumo_texto(resumo: dict) -> str:
    return (f"{resumo['dia']}: {resumo['recebidos']} recebidos, {resumo['processados']} processados, "
            f"{resumo['cancelados']} cancelados, {resumo['descartados']} descartados, {resumo['duplicados']} repetidos, "
            f"{resumo['erros']} com erro")[:300]


def registrar_sync(db: Session, cfg: TotalpassConfig, texto: str) -> None:
    cfg.sync_ultimo_em = agora_utc()
    cfg.sync_ultimo_resumo = texto[:300]
    db.commit()
