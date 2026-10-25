"""Fixtures da comunicação: provedor FALSO (nada vai à internet), relógio/sleep neutralizados e um cenário sintético."""
from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules import registrar_modelos

registrar_modelos()

from app.core import segredos  # noqa: E402
from app.modules.agenda.models import Reserva  # noqa: E402
from app.modules.cadastros.models import Categoria, Plano, Subcategoria, TipoCategoria  # noqa: E402
from app.modules.comunicacao import models as _modelos  # noqa: E402,F401
from app.modules.comunicacao import provedores as prov  # noqa: E402
from app.modules.comunicacao import servico as svc  # noqa: E402
from app.modules.contratos.models import Contrato  # noqa: E402
from app.modules.financeiro.models import ContaReceber  # noqa: E402
from tests.agenda import fabrica  # noqa: E402
from tests.conftest import SENHA, auth, criar_usuario, entrar  # noqa: E402,F401

TOKEN = "TOKEN-SECRETO-ABCD1234"
#: 25/10/2026 19:30 em Brasília (UTC-3): o lembrete (19:00) e a agenda do professor (18:00) já estão devidos
AGORA = datetime(2026, 10, 25, 22, 30, tzinfo=UTC)


class ProvedorFalso:
    """Substitui WasenderAPI/Evolution: guarda o que seria enviado e devolve respostas roteirizadas."""

    nome = "falso"

    def __init__(self) -> None:
        self.textos: list[tuple[str, str]] = []
        self.documentos: list[tuple[str, str, str, str]] = []
        self.roteiro: list[prov.Resultado] = []  # consumido na ordem; vazio = sucesso
        self.estado = prov.StatusSessao(True, "Sessão conectada.")
        self.chamadas = 0

    def _proximo(self) -> prov.Resultado:
        self.chamadas += 1
        return self.roteiro.pop(0) if self.roteiro else prov.Resultado(True, None, 200, resumo="success=True")

    def enviar_texto(self, telefone, texto):
        r = self._proximo()
        if r.ok:
            self.textos.append((telefone, texto))
        return r

    def enviar_documento(self, telefone, url, nome, legenda=""):
        r = self._proximo()
        if r.ok:
            self.documentos.append((telefone, url, nome, legenda))
        return r

    def status_sessao(self):
        return self.estado


SESSAO_CAIDA = prov.Resultado(False, "Session is not connected", 200, sessao_caiu=True, resumo="success=False")
FALHA = prov.Resultado(False, "erro temporário", 500, resumo="status=500")


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    """Nenhum teste dorme de verdade; as pausas ficam registradas em `sem_espera.pausas`."""
    pausas: list[float] = []
    monkeypatch.setattr(svc, "dormir", pausas.append)
    return pausas


@pytest.fixture(autouse=True)
def rede_bloqueada(monkeypatch):
    """Rede de segurança: qualquer chamada HTTP real nestes testes FALHA (nunca vai à internet)."""
    import httpx

    def proibido(self, request):
        raise AssertionError(f"Chamada de rede real bloqueada nos testes: {request.method} {request.url.host}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", proibido)
    yield
    svc.definir_fabrica_provedor(None)


@pytest.fixture
def falso():
    p = ProvedorFalso()
    svc.definir_fabrica_provedor(lambda dados: p)
    yield p
    svc.definir_fabrica_provedor(None)


@pytest.fixture
def cenario(db) -> SimpleNamespace:
    """Unidade com WhatsApp configurado (avisos DESLIGADOS, chave geral desligada), 2 alunas, professora, contrato e aula amanhã."""
    un = fabrica.unidade(db, capacidade=4)
    srv = fabrica.servico(db)
    prof = fabrica.profissional(db, "Natalia Souza")
    prof.celular = "11988887777"
    maria = fabrica.aluno(db, un, "Maria Souza", "5511999990001")
    joao = fabrica.aluno(db, un, "João Lima", "5511999990002")
    sem_tel = fabrica.aluno(db, un, "Sem Telefone", None)
    fixo = fabrica.aluno(db, un, "Telefone Fixo", "551133334444")
    cat = Categoria(nome="Mensalidades", tipo=TipoCategoria.RECEITA)
    db.add(cat)
    db.flush()
    sub = Subcategoria(categoria_id=cat.id, nome="Pilates")
    db.add(sub)
    db.flush()
    plano = Plano(nome="Plano 2x", tipo_servico_id=srv.id, categoria_receita_id=cat.id, subcategoria_receita_id=sub.id,
                  valor=Decimal("300.00"), aulas_por_semana=2, duracao_meses=3)
    db.add(plano)
    db.flush()
    cfg = svc.obter_config(db, un.id, criar=True)
    cfg.credencial_cifrado = segredos.cifrar_texto(TOKEN).decode()
    cfg.acompanhar_envios = False
    db.commit()
    return SimpleNamespace(un=un, srv=srv, prof=prof, maria=maria, joao=joao, sem_tel=sem_tel, fixo=fixo, plano=plano, cfg=cfg)


def ligar_avisos(db, cenario, *tipos: str, geral: bool = True) -> None:
    """Liga os avisos pedidos (nos horários padrão) e, por padrão, a chave geral do ambiente."""
    cfg = svc.obter_config(db, cenario.un.id)
    for t in tipos:
        setattr(cfg, svc.CAMPO_ATIVO[t], True)
    if geral:
        svc.definir_parametro(db, svc.PARAM_ENVIO_AUTOMATICO, "1")
    db.commit()


def reservar(db, cenario, aluno, dia=date(2026, 10, 26), inicio=time(9, 0), prof=True) -> Reserva:
    s = fabrica.sessao(db, cenario.un, cenario.srv, cenario.prof if prof else None, dia=dia, inicio=inicio)
    r = Reserva(aluno_id=aluno.id, aula_sessao_id=s.id)
    db.add(r)
    db.commit()
    return r


def contrato(db, cenario, aluno, inicio: date, fim: date, assinado: bool = True) -> Contrato:
    c = Contrato(aluno_id=aluno.id, plano_id=cenario.plano.id, unidade_id=cenario.un.id, profissional_id=cenario.prof.id,
                 data_inicio=inicio, data_fim=fim, valor_parcela=Decimal("300.00"), valor_total=Decimal("900.00"),
                 status_assinatura="ASSINADO" if assinado else "NAO_ASSINADO")
    db.add(c)
    db.commit()
    return c


def conta(db, aluno, contrato_, vencimento: date, valor="300.00") -> ContaReceber:
    c = ContaReceber(aluno_id=aluno.id, contrato_id=contrato_.id, valor=Decimal(valor), vencimento=vencimento)
    db.add(c)
    db.commit()
    return c


def _token(client, db, perfil, email):
    criar_usuario(db, perfil, email=email)
    return entrar(client, email).json()["access_token"]


@pytest.fixture
def full(client, db):
    return auth(_token(client, db, "Full", "full@x.com"))


@pytest.fixture
def secretaria(client, db):
    return auth(_token(client, db, "Secretária", "sec@x.com"))


@pytest.fixture
def professor(client, db):
    return auth(_token(client, db, "Professor", "prof@x.com"))
