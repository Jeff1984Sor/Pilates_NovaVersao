"""Gerador dos valores de referência ("golden master") das regras de negócio.

Roda o código ANTIGO (Django em ``PilatesFinal``, SOMENTE LEITURA) contra um SQLite TEMPORÁRIO com dados
sintéticos e grava os resultados como constantes em ``backend/tests/domain/golden/*.py``. Os testes do
domínio novo comparam as funções puras com essas constantes.

Uso (a partir de qualquer pasta)::

    set PILATES_ANTIGO_DIR=C:\\Users\\...\\Projetos\\Pilates\\PilatesFinal
    <python com Django do sistema antigo> backend/tests/domain/golden_gen/gerar_golden.py [secao ...]

Nunca aponta para produção nem usa dados reais: o banco é criado do zero em um arquivo temporário fora do
repositório (``%TEMP%``) e apagado ao final. Nenhuma mensagem de WhatsApp/e-mail é enviada (clientes
substituídos por dublês).
"""
# ruff: noqa
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

DATA_GERACAO = "2026-10-25"
SAIDA = Path(__file__).resolve().parent.parent / "golden"
ANTIGO = os.environ.get("PILATES_ANTIGO_DIR", r"C:\Users\JeffersonFernandes\Projetos\Pilates\PilatesFinal")


def _boot() -> None:
    os.chdir(ANTIGO)
    sys.path.insert(0, os.path.join(ANTIGO, "backend"))
    sys.path.insert(0, ANTIGO)
    banco = os.path.join(tempfile.gettempdir(), "pilates_golden_tmp.sqlite3")
    if os.path.exists(banco):
        os.remove(banco)
    os.environ["DATABASE_URL"] = "sqlite:///" + banco.replace("\\", "/")
    os.environ["DJANGO_SETTINGS_MODULE"] = "studiopilates.settings"
    os.environ["DJANGO_SECRET_KEY"] = "chave-sintetica-de-teste-golden"
    os.environ["WHATSAPP_SCHEDULER_ENABLED"] = "False"
    os.environ["WASENDER_API_TOKEN"] = ""
    os.environ["WHATSAPP_BATCH_PAUSE_SECONDS"] = "0"
    os.environ["DEBUG"] = "True"
    os.environ["ALLOWED_HOSTS"] = "*"
    import django

    django.setup()
    from django.core.management import call_command

    call_command("migrate", verbosity=0, interactive=False)
    from django.test.utils import setup_test_environment

    setup_test_environment()


# ---------------------------------------------------------------------------
# Saída: constantes Python legíveis
# ---------------------------------------------------------------------------

def lit(valor, nivel: int = 0) -> str:
    """Representação em código Python (date, time, datetime, Decimal incluídos)."""
    pad = "    " * nivel
    if isinstance(valor, dt.datetime):
        base = f"datetime({valor.year}, {valor.month}, {valor.day}, {valor.hour}, {valor.minute}, {valor.second}"
        if valor.tzinfo is not None:
            return base + ", tzinfo=SP)"
        return base + ")"
    if isinstance(valor, dt.date):
        return f"date({valor.year}, {valor.month}, {valor.day})"
    if isinstance(valor, dt.time):
        return f"time({valor.hour}, {valor.minute})" if not valor.second else f"time({valor.hour}, {valor.minute}, {valor.second})"
    if isinstance(valor, Decimal):
        return f"Decimal({str(valor)!r})"
    if isinstance(valor, (list, tuple, set, frozenset)):
        abre, fecha = ("[", "]") if isinstance(valor, list) else ("(", ")") if isinstance(valor, tuple) else ("{", "}")
        itens = [lit(v, nivel + 1) for v in valor]
        if isinstance(valor, tuple) and len(itens) == 1:
            itens[0] += ","
        if not itens:
            return "set()" if isinstance(valor, (set, frozenset)) else abre + fecha
        linha = abre + ", ".join(itens) + fecha
        if len(linha) + len(pad) <= 100 and "\n" not in linha:
            return linha
        interno = "\n".join(f"{pad}    {i}," for i in itens)
        return f"{abre}\n{interno}\n{pad}{fecha}"
    if isinstance(valor, dict):
        itens = [f"{lit(k)}: {lit(v, nivel + 1)}" for k, v in valor.items()]
        if not itens:
            return "{}"
        linha = "{" + ", ".join(itens) + "}"
        if len(linha) + len(pad) <= 100 and "\n" not in linha:
            return linha
        interno = "\n".join(f"{pad}    {i}," for i in itens)
        return "{\n" + interno + f"\n{pad}}}"
    return repr(valor)


def escrever(nome: str, **constantes) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = [
        f'"""Valores de referência gerados pelo sistema antigo em {DATA_GERACAO} ({nome}).',
        "",
        "ARQUIVO GERADO por tests/domain/golden_gen/gerar_golden.py rodando o código Django antigo contra um",
        "SQLite temporário com dados sintéticos. Não edite à mão: regenere.",
        '"""',
        "# ruff: noqa",
        "from datetime import date, datetime, time",
        "from decimal import Decimal",
        "from zoneinfo import ZoneInfo",
        "",
        'SP = ZoneInfo("America/Sao_Paulo")',
        "",
    ]
    for chave, valor in constantes.items():
        linhas.append(f"# valor gerado pelo sistema antigo em {DATA_GERACAO}")
        linhas.append(f"{chave} = {lit(valor)}")
        linhas.append("")
    (SAIDA / f"golden_{nome}.py").write_text("\n".join(linhas), encoding="utf-8")
    print("gerado", nome)


# ---------------------------------------------------------------------------
# Construtores de cenário (dados sintéticos)
# ---------------------------------------------------------------------------

class Fabrica:
    """Cria objetos Django sintéticos com códigos sequenciais."""

    def __init__(self):
        from studiopilates.core import models

        self.m = models
        self.n = 0
        self.unidade = None
        self.tipo = None
        self.perfil = None
        self.user = None

    def prox(self) -> int:
        self.n += 1
        return self.n

    def base(self, capacidade=3, duracao=50):
        m = self.m
        self.unidade = m.Unidade.objects.create(cdUnidade=self.prox(), dsUnidade="Unidade Teste", capacidade=capacidade, duracao_aula_minutos=duracao)
        self.tipo = m.TipoServico.objects.create(cdTipoServico=self.prox(), dsTipoServico="Pilates")
        self.perfil = m.PerfilAcesso.objects.create(cdPerfilAcesso=self.prox(), dsPerfilAcesso="Administrador")
        return self

    def profissional(self, nome="Prof", celular="", perfil=None):
        return self.m.Profissional.objects.create(
            cdProfissional=self.prox(), profissional=nome, celular=celular, cdPerfilAcesso=perfil or self.perfil
        )

    def aluno(self, nome="Aluno", telefone=None, nascimento=None, status="ATIVO", unidade=None):
        k = self.prox()
        a = self.m.Aluno.objects.create(
            cdAluno=k, dsNome=nome, dsCPF=f"SEM_CPF_{k}", sem_cpf=True, cdUnidade=unidade or self.unidade,
            dtNascimento=nascimento, status=status,
        )
        if telefone:
            self.m.TelefoneAluno.objects.create(cdTelefone=self.prox(), cdAluno=a, dsTelefone=telefone)
        return a

    def plano(self, valor="300", aulas=2, meses=3, recorrencia="MENSAL", avulso=False):
        return self.m.Plano.objects.create(
            cdPlano=self.prox(), dsPlano="Plano", cdTipoServico=self.tipo, valor=Decimal(valor),
            aulas_por_semana=aulas, duracao_meses=meses, recorrencia=recorrencia, is_avulso=avulso,
        )

    def contrato(self, aluno, plano, prof, inicio, fim, status="ASSINADO", recorrencia="MENSAL", unidade=None):
        return self.m.Contrato.objects.create(
            cdContrato=self.prox(), cdAluno=aluno, cdPlano=plano, cdUnidade=unidade or self.unidade,
            cdProfissional=prof, recorrencia=recorrencia, dtInicioContrato=inicio, dtFimContrato=fim,
            valor_parcela=plano.valor, valor_total=plano.valor, status=status,
        )

    def sessao(self, data, ini, fim, prof=None, capacidade=None, tipo=None, unidade=None):
        return self.m.AulaSessao.objects.create(
            unidade=unidade or self.unidade, tipoServico=tipo or self.tipo, profissional=prof, data=data,
            horaInicio=ini, horaFim=fim, capacidade=capacidade,
        )

    def reserva(self, aluno, sessao, status="RESERVADA"):
        return self.m.Reserva.objects.create(aluno=aluno, aulaSessao=sessao, status=status)


def _cliente_logado():
    from django.contrib.auth import get_user_model
    from django.test import Client

    User = get_user_model()
    User.objects.filter(username="admin_golden").delete()
    User.objects.create_superuser(username="admin_golden", password="x")
    c = Client()
    assert c.login(username="admin_golden", password="x")
    return c


def _limpar_banco():
    from django.core.management import call_command

    call_command("flush", verbosity=0, interactive=False)


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------

def sec_precos():
    from studiopilates.core import views

    contratos = []
    for valor in ["300.00", "300", "0", "99.90", "1000", "0.01", "100.50", "250.75", "1234.56", "199.99", "333.33"]:
        for aulas in [0, 1, 2, 3, 5, None, -1]:
            for meses in [0, 1, 3, 12, None, -2]:
                plano = SimpleNamespace(valor=Decimal(valor), aulas_por_semana=aulas, duracao_meses=meses)
                rec, va, vp, vt = views._contrato_precificacao(plano)
                contratos.append((valor, aulas, meses, rec, va, vp, vt))

    avulsas = []
    for rec_plano in ["SEMANAL", "MENSAL", None, ""]:
        for valor in ["80.00", "0"]:
            for qtd in [1, 4, "3", "abc", 0, -2, None, "", 2.7, "2.5", "10"]:
                for informado in [None, "", "75.50", "abc", "0", "-5", "12,5"]:
                    plano = SimpleNamespace(valor=Decimal(valor), recorrencia=rec_plano)
                    rec, base, total, q = views._aula_avulsa_precificacao(plano, qtd, informado)
                    avulsas.append((rec_plano, valor, qtd, informado, rec, base, total, q))

    fins = []
    for inicio in [dt.date(2026, 10, 10), dt.date(2026, 1, 31), dt.date(2026, 12, 15), dt.date(2024, 2, 29)]:
        for rec in ["MENSAL", "SEMANAL"]:
            for q in [1, 2, 4, 13]:
                fim = views._add_months(inicio, q) if rec == "MENSAL" else inicio + dt.timedelta(days=7 * q)
                fins.append((inicio, rec, q, fim))
    escrever("precos", CONTRATOS=contratos, AVULSAS=avulsas, FINS_AVULSA=fins)


def sec_parcelas():
    from studiopilates.core import services, views

    parcelas = []
    inicios = [dt.date(2026, 1, 31), dt.date(2026, 1, 15), dt.date(2026, 10, 10), dt.date(2026, 11, 30), dt.date(2026, 12, 29),
               dt.date(2024, 1, 29), dt.date(2023, 3, 31), dt.date(2026, 2, 1)]
    for inicio in inicios:
        for meses in [None, 0, 1, 3, 6, 13]:
            lista = services.gerar_parcelas(Decimal("300.00"), inicio, inicio + dt.timedelta(days=90), meses, "MENSAL")
            parcelas.append((inicio, meses, [(p["vencimento"], p["competencia"]) for p in lista]))
    semanais = []
    for inicio, fim in [
        (dt.date(2026, 10, 12), dt.date(2026, 11, 9)), (dt.date(2024, 12, 30), dt.date(2025, 1, 27)),
        (dt.date(2026, 12, 28), dt.date(2027, 1, 25)), (dt.date(2026, 10, 12), dt.date(2026, 10, 12)),
        (dt.date(2026, 10, 12), dt.date(2026, 10, 11)),
    ]:
        lista = services.gerar_parcelas(Decimal("50"), inicio, fim, 1, "SEMANAL")
        semanais.append((inicio, fim, [(p["vencimento"], p["competencia"]) for p in lista]))
    add = []
    for base in [dt.date(2026, 1, 31), dt.date(2026, 1, 15), dt.date(2026, 11, 15), dt.date(2024, 2, 29), dt.date(2026, 12, 31), dt.date(2026, 3, 28)]:
        for n in [0, 1, 2, 3, 12, 13, 24, -1, -13]:
            add.append((base, n, views._add_months(base, n)))
    comps = []
    for d in [dt.date(2024, 12, 30), dt.date(2024, 12, 29), dt.date(2026, 1, 1), dt.date(2027, 1, 3), dt.date(2026, 10, 25)]:
        for rec in ["MENSAL", "SEMANAL"]:
            comps.append((d, rec, views._competencia_avulsa(d, rec)))
    escrever("parcelas", MENSAIS=parcelas, SEMANAIS=semanais, ADD_MONTHS=add, COMPETENCIAS_AVULSA=comps)


def sec_telefone():
    from api import main as api_main
    from studiopilates.core import views
    from studiopilates.core.whatsapp_service import WhatsappService

    entradas = [
        "(15) 99776-2467", "15997762467", "5515997762467", "+55 (15) 99776-2467", "15 9776-2467", "1597762467",
        "551597762467", "(15) 3333-4444", "1533334444", "551533334444", "015997762467", "0 15 99776-2467", "99776-2467",
        "997762467", "9776-2467", "97762467", "", None, "abc", "55", "5599", "+55", "(55) 99123-4567", "55991234567",
        "5599123456", "5555991234567", "555599123456", "11 98888-7777 ", "(11)9 8888 7777", "00551198888777", "1198888777",
        "119888877770", "123", "5511", "0011998887777", "(21) 2222-3333", "2122223333", "21 7777-6666", "11 5555-1234",
        "11 4444-1234", "(11) 1234-5678", "11912345678", "11812345678", "1112345678", "+1 415 555 2671",
    ]
    clean = [(e, WhatsappService.clean_phone(e)) for e in entradas]
    fmt = [(e, views._format_whatsapp_number([e])) for e in entradas]
    canon = [(e, api_main._telefone_canon(e)) for e in entradas]
    listas = [
        (["", None, "(15) 99776-2467", "11 98888-7777"],), (["abc"],), ([],), (["", "5599"],), (["97762467", "15997762467"],),
    ]
    fmt_listas = [(l[0], views._format_whatsapp_number(l[0])) for l in listas]
    pares = []
    amostra = ["(15) 99776-2467", "1597762467", "5515997762467", "15 3333-4444", "11 98888-7777", "11988887777", "", "123"]
    for a in amostra:
        for b in amostra:
            ca, cb = api_main._telefone_canon(a), api_main._telefone_canon(b)
            pares.append((a, b, ca is not None and ca == cb))
    escrever("telefone", ENTRADAS=entradas, CLEAN_PHONE=clean, FORMAT_WHATSAPP=fmt, FORMAT_LISTAS=fmt_listas, TELEFONE_CANON=canon, PARES_MESMO=pares)


def sec_documentos():
    from studiopilates.core import receita_saude
    from studiopilates.core.validators import validar_cpf

    entradas = ["529.982.247-25", "52998224725", "111.111.111-11", "123", "", None, "390.533.447-05", "11144477735", "000.000.000-00",
                "529.982.247-24", "5299822472", "529982247250", "abc", "529 982 247 25", "123.456.789-09", "12345678909", "98765432100"]
    antigo = [(e, bool(validar_cpf(e)), receita_saude.cpf_valido(e), receita_saude.so_digitos(e)) for e in entradas]
    escrever("documentos", CPFS=antigo)


def sec_capacidade():
    from django.core.exceptions import ValidationError

    f = Fabrica().base(capacidade=2)
    prof = f.profissional()
    s = f.sessao(dt.date(2026, 10, 12), dt.time(8, 0), dt.time(8, 50), prof)
    a1, a2, a3, a4 = (f.aluno(f"A{i}") for i in range(4))
    f.reserva(a1, s)
    f.reserva(a2, s, "RESERVADA")
    f.reserva(a3, s, "PENDENTE")  # não conta
    f.reserva(a4, s, "CONCLUIDA")  # não conta
    msg_clean = None
    from studiopilates.core import models

    extra = f.aluno("Extra")
    try:
        models.Reserva(aluno=extra, aulaSessao=s, status="RESERVADA").full_clean()
    except ValidationError as exc:
        msg_clean = exc.messages
    # nenhum erro para CANCELADA/PENDENTE mesmo lotado
    ok_status = {}
    for st in ["CANCELADA", "PENDENTE", "CONCLUIDA", "FALTOU_AVISOU"]:
        try:
            models.Reserva(aluno=extra, aulaSessao=s, status=st).full_clean()
            ok_status[st] = True
        except ValidationError:
            ok_status[st] = False
    # capacidade efetiva
    s_nula = f.sessao(dt.date(2026, 10, 13), dt.time(8, 0), dt.time(8, 50), prof)
    s_zero = f.sessao(dt.date(2026, 10, 14), dt.time(8, 0), dt.time(8, 50), prof, capacidade=0)
    s_cinco = f.sessao(dt.date(2026, 10, 15), dt.time(8, 0), dt.time(8, 50), prof, capacidade=5)
    efetivas = [(None, 2, s_nula.capacidade_efetiva()), (0, 2, s_zero.capacidade_efetiva()), (5, 2, s_cinco.capacidade_efetiva())]
    # capacidade 0: Reserva.clean recusa?
    try:
        models.Reserva(aluno=extra, aulaSessao=s_zero, status="RESERVADA").full_clean()
        zero_recusa = False
    except ValidationError as exc:
        zero_recusa = True
        msg_zero = exc.messages
    # remarcar via API (client): mensagem e capacidade 0 passa?
    c = _cliente_logado()
    import json

    movel = f.aluno("Movel")
    r_mov = f.reserva(movel, f.sessao(dt.date(2026, 10, 20), dt.time(9, 0), dt.time(9, 50), prof))
    resp = c.post(f"/agenda/aulas/reservas/{r_mov.id}/remarcar/", data=json.dumps({"data": "2026-10-12", "hora_inicio": "08:00"}), content_type="application/json")
    remarcar_cheia = (resp.status_code, resp.json())
    r_mov.refresh_from_db()
    resp0 = c.post(f"/agenda/aulas/reservas/{r_mov.id}/remarcar/", data=json.dumps({"data": "2026-10-14", "hora_inicio": "08:00"}), content_type="application/json")
    remarcar_cap_zero = (resp0.status_code, resp0.json().get("ok"))
    escrever(
        "capacidade", MSG_CLEAN=msg_clean, OK_POR_STATUS=ok_status, EFETIVAS=efetivas, ZERO_RECUSA=zero_recusa,
        MSG_ZERO=msg_zero, REMARCAR_CHEIA=remarcar_cheia, REMARCAR_CAP_ZERO=remarcar_cap_zero,
    )


def sec_reposicao():
    import json

    from api import main as api_main
    from django.utils import timezone

    f = Fabrica().base()
    prof = f.profissional()
    c = _cliente_logado()
    casos = []
    for data_aula in [dt.date(2026, 10, 10), dt.date(2026, 12, 15), dt.date(2024, 2, 1), dt.date(2026, 1, 31)]:
        al = f.aluno("A")
        r = f.reserva(al, f.sessao(data_aula, dt.time(8, 0), dt.time(8, 50), prof))
        r.confirmada_em = timezone.now()
        r.save()
        resp = c.post(f"/agenda/aulas/reservas/{r.id}/status/", data=json.dumps({"acao": "desmarcar"}), content_type="application/json")
        r.refresh_from_db()
        casos.append((data_aula, resp.status_code, resp.json(), r.status, r.confirmada_em, r.desmarcada_em is not None, r.reposicao_ate))
    # ações simples
    acoes = []
    for acao in ["chegou", "iniciar", "finalizar", "faltou", "remarcar", "desmarcar", "xyz", ""]:
        al = f.aluno("B")
        r = f.reserva(al, f.sessao(dt.date(2026, 11, 2), dt.time(8, 0), dt.time(8, 50), prof))
        resp = c.post(f"/agenda/aulas/reservas/{r.id}/status/", data=json.dumps({"acao": acao}), content_type="application/json")
        r.refresh_from_db()
        acoes.append((acao, resp.status_code, r.status))
    # professor
    perfil_prof = f.m.PerfilAcesso.objects.create(cdPerfilAcesso=f.prox(), dsPerfilAcesso="Professor")
    p2 = f.profissional("Prof Login", perfil=perfil_prof)
    p2.refresh_from_db()
    p2.user.set_password("p")
    p2.user.save()
    from django.test import Client

    cp = Client()
    assert cp.login(username=p2.user.username, password="p")
    prof_resp = []
    for acao in ["desmarcar", "remarcar", "finalizar", "faltou"]:
        al = f.aluno("C")
        r = f.reserva(al, f.sessao(dt.date(2026, 11, 3), dt.time(8, 0), dt.time(8, 50), p2))
        resp = cp.post(f"/agenda/aulas/reservas/{r.id}/status/", data=json.dumps({"acao": acao}), content_type="application/json")
        r.refresh_from_db()
        prof_resp.append((acao, resp.status_code, r.status))
    # app do aluno (função direta)
    app = []
    hoje = timezone.localdate()
    al = f.aluno("App")
    for rotulo, data_aula, status in [("futura", hoje + dt.timedelta(days=5), "RESERVADA"), ("hoje", hoje, "RESERVADA"), ("passada", hoje - dt.timedelta(days=1), "RESERVADA"), ("cancelada", hoje + dt.timedelta(days=5), "CANCELADA")]:
        r = f.reserva(al, f.sessao(data_aula, dt.time(8, 0) if rotulo != "hoje" else dt.time(8, 0), dt.time(8, 50), prof), status) if rotulo != "hoje" else f.reserva(al, f.sessao(data_aula, dt.time(9, 0), dt.time(9, 50), prof), status)
        for nome, fn in [("desmarcar", api_main.aluno_app_desmarcar), ("confirmar", api_main.aluno_app_confirmar)]:
            r.refresh_from_db()
            try:
                out = fn(r.id, al)
                resultado = ("ok", {k: v for k, v in out.items()})
            except Exception as exc:  # HTTPException
                resultado = ("erro", getattr(exc, "status_code", None), getattr(exc, "detail", str(exc)))
            app.append((rotulo, nome, (data_aula - hoje).days, resultado))
            # reabre para o próximo teste
            r.status = status
            r.save()
    escrever("reposicao", HOJE_APP=hoje, DESMARCAR_STAFF=casos, ACOES=acoes, PROFESSOR=prof_resp, APP_ALUNO=app)


def sec_status_aula():
    from unittest import mock

    from studiopilates.core import services, views

    tz = dt.timezone(dt.timedelta(hours=-3))
    sp = __import__("zoneinfo").ZoneInfo("America/Sao_Paulo")
    ini = dt.datetime(2026, 10, 26, 9, 0, tzinfo=sp)
    fim = dt.datetime(2026, 10, 26, 9, 50, tzinfo=sp)
    momentos = [
        dt.datetime(2026, 10, 26, 8, 59, 59, tzinfo=sp), ini, dt.datetime(2026, 10, 26, 9, 25, tzinfo=sp), fim,
        dt.datetime(2026, 10, 26, 9, 50, 1, tzinfo=sp),
    ]
    mapa = []
    for status in ["RESERVADA", "PENDENTE", "CONCLUIDA", "FALTOU_AVISOU", "FALTOU_SEM_AVISAR", "CANCELADA", "XYZ"]:
        for i, agora in enumerate(momentos):
            with mock.patch.object(views.timezone, "localtime", lambda value=None, a=agora: a):
                mapa.append((status, i, views._map_status(status, ini, fim)))

    # R6: concluir_aulas_passadas
    f = Fabrica().base(capacidade=9)
    prof = f.profissional()
    agora = dt.datetime(2026, 10, 26, 10, 0, tzinfo=sp)
    cenarios = []
    ids = {}
    n = 0
    for status in ["RESERVADA", "PENDENTE", "CONCLUIDA", "CANCELADA", "FALTOU_AVISOU", "FALTOU_SEM_AVISAR"]:
        for data_aula, fim_aula, rotulo in [
            (dt.date(2026, 10, 25), dt.time(23, 59), "ontem_tarde"), (dt.date(2026, 10, 26), dt.time(9, 50), "hoje_terminou"),
            (dt.date(2026, 10, 26), dt.time(10, 0), "hoje_fim_igual_agora"), (dt.date(2026, 10, 26), dt.time(10, 1), "hoje_ainda_nao"),
            (dt.date(2026, 10, 26), dt.time(15, 0), "hoje_a_tarde"), (dt.date(2026, 10, 27), dt.time(8, 50), "amanha"),
        ]:
            n += 1
            al = f.aluno(f"R{n}")
            s = f.sessao(data_aula, dt.time(0, 0), fim_aula, prof)
            r = f.reserva(al, s, status)
            ids[r.id] = (status, data_aula, fim_aula, rotulo)
    with mock.patch.object(services.timezone, "localtime", lambda value=None: agora):
        total = services.concluir_aulas_passadas()
    from studiopilates.core import models

    resultado = []
    for r in models.Reserva.objects.order_by("id"):
        st, d, hf, rot = ids[r.id]
        resultado.append((st, d, hf, rot, r.status))
    escrever("status_aula", MAPA_STATUS=mapa, AGORA_CONCLUIR=agora, CONCLUIDAS_TOTAL=total, CONCLUIR=resultado)
    _limpar_banco()


def sec_agenda():
    from django.contrib.messages import get_messages
    from studiopilates.core import models, views

    # --- slots a partir das janelas
    janelas_casos = [
        [(dt.time(8, 0), dt.time(12, 0))], [(dt.time(8, 30), dt.time(12, 0))], [(dt.time(9, 0), dt.time(10, 0))],
        [(dt.time(7, 0), dt.time(9, 0)), (dt.time(14, 0), dt.time(18, 30))], [(dt.time(8, 0), dt.time(8, 40))],
        [(dt.time(23, 0), dt.time(23, 59))], [(dt.time(6, 15), dt.time(7, 0))], [(dt.time(8, 0), dt.time(8, 50))],
        [(dt.time(8, 0), dt.time(8, 49))], [],
    ]
    slots = []
    for janelas in janelas_casos:
        for dur in [50, 60, 30, 45, 20]:
            ws = [SimpleNamespace(horaInicio=a, horaFim=b) for a, b in janelas]
            slots.append((janelas, dur, views._generate_slots_for_date(dt.date(2026, 11, 2), ws, dur)))

    # --- bloqueios (_is_slot_blocked)
    defs = {
        "pontual_aberto": dict(recorrente=False, diaSemana=None, dataInicio=dt.date(2026, 11, 16), dataFim=None, horaInicio=dt.time(8, 0), horaFim=dt.time(12, 0)),
        "pontual_periodo": dict(recorrente=False, diaSemana=None, dataInicio=dt.date(2026, 11, 16), dataFim=dt.date(2026, 11, 18), horaInicio=dt.time(9, 0), horaFim=dt.time(10, 0)),
        "recorrente_seg": dict(recorrente=True, diaSemana=0, dataInicio=dt.date(2026, 11, 1), dataFim=dt.date(2026, 12, 31), horaInicio=dt.time(10, 0), horaFim=dt.time(11, 0)),
        "recorrente_sem_dia": dict(recorrente=True, diaSemana=None, dataInicio=dt.date(2026, 11, 1), dataFim=None, horaInicio=dt.time(8, 0), horaFim=dt.time(12, 0)),
        "recorrente_qua_aberto": dict(recorrente=True, diaSemana=2, dataInicio=dt.date(2026, 11, 1), dataFim=None, horaInicio=dt.time(8, 0), horaFim=dt.time(9, 0)),
    }
    datas = [dt.date(2026, 10, 30), dt.date(2026, 11, 15), dt.date(2026, 11, 16), dt.date(2026, 11, 17), dt.date(2026, 11, 18),
             dt.date(2026, 11, 19), dt.date(2026, 11, 23), dt.date(2026, 11, 25), dt.date(2026, 12, 31), dt.date(2027, 1, 4)]
    horas = [(dt.time(8, 0), dt.time(8, 50)), (dt.time(9, 0), dt.time(9, 50)), (dt.time(10, 0), dt.time(10, 50)),
             (dt.time(10, 50), dt.time(11, 40)), (dt.time(7, 10), dt.time(8, 0)), (dt.time(11, 0), dt.time(11, 50)), (dt.time(7, 0), dt.time(7, 59))]
    bloqueados = []
    for nome, d in defs.items():
        b = SimpleNamespace(**d)
        for dia in datas:
            for ini, fim in horas:
                bloqueados.append((nome, dia, ini, fim, views._is_slot_blocked([b], dia, ini, fim)))
    # lista de bloqueios juntos
    todos = [SimpleNamespace(**d) for d in defs.values()]
    juntos = [(dia, ini, fim, views._is_slot_blocked(todos, dia, ini, fim)) for dia in datas for ini, fim in horas]

    # --- datas da aula avulsa
    alinhar = []
    for base in [dt.date(2026, 10, 25), dt.date(2026, 10, 26), dt.date(2026, 10, 27), dt.date(2026, 12, 30), dt.date(2027, 1, 1)]:
        for wd in range(7):
            alinhar.append((base, wd, views._align_date_to_weekday(base, wd)))
    avancar = []
    for base in [dt.date(2026, 10, 26), dt.date(2026, 1, 31), dt.date(2026, 12, 28)]:
        for rec in ["MENSAL", "SEMANAL", "OUTRO"]:
            for idx in [0, 1, 2, 5, 13]:
                avancar.append((base, rec, idx, views._advance_recorrencia_date(base, rec, idx)))

    # --- _load_funcionamento e _load_bloqueios com banco
    f = Fabrica().base(capacidade=3)
    along = models.TipoServico.objects.create(cdTipoServico=f.prox(), dsTipoServico="Alongamento")
    P, A = f.tipo, along
    horarios_def = [
        (0, dt.time(8, 0), dt.time(12, 0), True, "", ""),
        (0, dt.time(14, 0), dt.time(18, 0), True, "P", ""),
        (1, dt.time(8, 0), dt.time(12, 0), True, "", ""),
        (2, dt.time(8, 0), dt.time(12, 0), True, "A", ""),
        (3, dt.time(8, 0), dt.time(12, 0), True, "", "PA"),
        (4, dt.time(8, 0), dt.time(12, 0), False, "", ""),
        (4, dt.time(14, 0), dt.time(18, 0), True, "", ""),
        (5, dt.time(8, 0), dt.time(10, 0), True, "A", ""),
        (5, dt.time(10, 0), dt.time(12, 0), True, "", "A"),
    ]
    mapa = {"P": P, "A": A}
    for dia, ini, fim, ativo, fk, m2m in horarios_def:
        h = models.HorarioFuncionamento.objects.create(
            unidade=f.unidade, tipoServico=mapa[fk] if fk else None, diaSemana=dia, horaInicio=ini, horaFim=fim, ativo=ativo
        )
        for letra in m2m:
            h.tipos_servico.add(mapa[letra])
    funcionamento = {}
    for rotulo, tipo in [("todos", None), ("P", P.id), ("A", A.id)]:
        resultado = views._load_funcionamento(f.unidade.id, tipo)
        funcionamento[rotulo] = {dia: [(i.horaInicio, i.horaFim) for i in itens] for dia, itens in sorted(resultado.items())}

    prof1 = f.profissional("P1")
    prof2 = f.profissional("P2")
    bloq_def = [
        # (recorrente, dia, ini, fim, hora_ini, hora_fim, ativo, tipo, prof)
        (False, None, dt.date(2026, 11, 10), None, dt.time(8, 0), dt.time(9, 0), True, "", ""),
        (False, None, dt.date(2026, 11, 10), dt.date(2026, 11, 12), dt.time(8, 0), dt.time(9, 0), True, "P", ""),
        (False, None, dt.date(2026, 11, 10), dt.date(2026, 11, 12), dt.time(8, 0), dt.time(9, 0), True, "A", ""),
        (False, None, dt.date(2026, 11, 10), dt.date(2026, 11, 12), dt.time(8, 0), dt.time(9, 0), True, "", "1"),
        (False, None, dt.date(2026, 11, 10), dt.date(2026, 11, 12), dt.time(8, 0), dt.time(9, 0), True, "", "2"),
        (False, None, dt.date(2026, 11, 10), dt.date(2026, 11, 12), dt.time(8, 0), dt.time(9, 0), False, "", ""),
        (True, 1, dt.date(2026, 9, 1), dt.date(2026, 10, 31), dt.time(8, 0), dt.time(9, 0), True, "", ""),
        (True, 1, dt.date(2026, 9, 1), None, dt.time(8, 0), dt.time(9, 0), True, "", ""),
        (False, None, dt.date(2026, 12, 20), dt.date(2026, 12, 31), dt.time(8, 0), dt.time(9, 0), True, "", ""),
    ]
    objetos = []
    pmap = {"1": prof1, "2": prof2}
    for rec, dia, ini, fim, hi, hf, ativo, tipo, prof in bloq_def:
        objetos.append(models.BloqueioAgenda.objects.create(
            unidade=f.unidade, tipoServico=mapa[tipo] if tipo else None, profissional=pmap[prof] if prof else None,
            recorrente=rec, diaSemana=dia, dataInicio=ini, dataFim=fim, horaInicio=hi, horaFim=hf, ativo=ativo,
        ))
    indice = {o.id: i for i, o in enumerate(objetos)}
    carregados = []
    for tipo_rot, tipo in [("nenhum", None), ("P", P.id), ("A", A.id)]:
        for prof_rot, prof in [("sem", None), ("1", prof1.id), ("2", prof2.id)]:
            for ini, fim in [(dt.date(2026, 11, 1), dt.date(2026, 11, 30)), (dt.date(2026, 11, 11), dt.date(2026, 11, 11)),
                             (dt.date(2026, 12, 1), dt.date(2026, 12, 19)), (dt.date(2026, 10, 1), dt.date(2026, 10, 5))]:
                ids = [indice[b.id] for b in views._load_bloqueios(f.unidade.id, tipo, prof, ini, fim)]
                carregados.append((tipo_rot, prof_rot, ini, fim, sorted(ids)))
    _limpar_banco()

    # --- contrato_agenda (view real)

    def nova_base(cap=2):
        _limpar_banco()
        fb = Fabrica().base(capacidade=cap, duracao=50)
        c = _cliente_logado()
        p1 = fb.profissional("P1")
        p2 = fb.profissional("P2")
        return fb, c, p1, p2

    def reservas_do_aluno(aluno):
        return [(r.aulaSessao.data, r.aulaSessao.horaInicio, r.aulaSessao.horaFim, r.aulaSessao.profissional_id, r.status)
                for r in models.Reserva.objects.filter(aluno=aluno).select_related("aulaSessao").order_by("aulaSessao__data", "aulaSessao__horaInicio")]

    def post(c, contrato, dados):
        resp = c.post(f"/contratos/{contrato.id}/agenda/", dados)
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        c.get(f"/contratos/{contrato.id}/agenda/")  # consome as mensagens para não acumularem
        return resp.status_code, msgs

    # Cenário A: horários configurados, bloqueio, sessão cheia
    fb, c, p1, p2 = nova_base()
    for dia, ini, fim in [(0, dt.time(8, 0), dt.time(11, 0)), (2, dt.time(9, 0), dt.time(10, 0))]:
        models.HorarioFuncionamento.objects.create(unidade=fb.unidade, diaSemana=dia, horaInicio=ini, horaFim=fim)
    aluno = fb.aluno("Aluna A")
    plano = fb.plano(aulas=2)
    contrato = fb.contrato(aluno, plano, p1, dt.date(2026, 11, 2), dt.date(2026, 11, 30))
    models.BloqueioAgenda.objects.create(unidade=fb.unidade, profissional=p1, recorrente=False, dataInicio=dt.date(2026, 11, 16),
                                         horaInicio=dt.time(8, 0), horaFim=dt.time(12, 0))
    cheia = fb.sessao(dt.date(2026, 11, 23), dt.time(8, 0), dt.time(8, 50), p2)
    fb.reserva(fb.aluno("X"), cheia)
    fb.reserva(fb.aluno("Y"), cheia)
    resp = c.get(f"/contratos/{contrato.id}/agenda/")
    opcoes_a = [(o["value"], o["allowed_profs"]) for o in resp.context["slot_options"]]
    admin_id = models.Profissional.objects.exclude(id__in=[p1.id, p2.id]).get().id
    ids_a = {"admin": admin_id, "p1": p1.id, "p2": p2.id}
    erros_a = []
    casos_erro = {
        "uma_so": {"slot_1": "0|09:00|09:50", "prof_for_1": p2.id},
        "repetido": {"slot_1": "0|09:00|09:50", "prof_for_1": p2.id, "slot_2": "0|09:00|09:50", "prof_for_2": p2.id},
        "mesmo_dia": {"slot_1": "0|09:00|09:50", "prof_for_1": p2.id, "slot_2": "0|10:00|10:50", "prof_for_2": p2.id},
        "slot_inexistente": {"slot_1": "0|08:30|09:20", "prof_for_1": p2.id, "slot_2": "2|09:00|09:50", "prof_for_2": p2.id},
        "prof_nao_permitido": {"slot_1": "0|09:00|09:50", "prof_for_1": p1.id, "slot_2": "2|09:00|09:50", "prof_for_2": p1.id},
        "sem_prof": {"slot_1": "0|09:00|09:50", "slot_2": "2|09:00|09:50", "prof_for_2": p2.id},
        "dia_nao_confere": {"slot_1": "0|09:00|09:50", "slot_day_1": "2", "prof_for_1": p2.id, "slot_2": "2|09:00|09:50", "prof_for_2": p2.id},
        "formato_ruim": {"slot_1": "lixo", "prof_for_1": p2.id, "slot_2": "2|09:00|09:50", "prof_for_2": p2.id},
        "parcial_depois_invalido": {"slot_1": "0|09:00|09:50", "prof_for_1": p2.id, "slot_2": "2|09:30|10:20", "prof_for_2": p2.id},
    }
    for nome, dados in casos_erro.items():
        status, msgs = post(c, contrato, dados)
        criadas = reservas_do_aluno(aluno)
        erros_a.append((nome, status, msgs, criadas))
        models.Reserva.objects.filter(aluno=aluno).delete()
        models.AulaSessao.objects.filter(reserva__isnull=True).exclude(id=cheia.id).delete()
    status, msgs = post(c, contrato, {"slot_1": "0|09:00|09:50", "prof_for_1": p2.id, "slot_2": "2|09:00|09:50", "prof_for_2": admin_id})
    ok_a = (status, msgs, reservas_do_aluno(aluno))

    # Cenário B: sem horários configurados (fallback pelas aulas existentes), com bloqueio e sessão cheia
    fb, c, p1, p2 = nova_base()
    aluno = fb.aluno("Aluna B")
    plano = fb.plano(aulas=1)
    contrato = fb.contrato(aluno, plano, p1, dt.date(2026, 11, 2), dt.date(2026, 11, 30))
    fb.sessao(dt.date(2026, 11, 2), dt.time(8, 0), dt.time(8, 50), p1)
    cheia = fb.sessao(dt.date(2026, 11, 23), dt.time(8, 0), dt.time(8, 50), p1)
    fb.reserva(fb.aluno("X"), cheia)
    fb.reserva(fb.aluno("Y"), cheia)
    models.BloqueioAgenda.objects.create(unidade=fb.unidade, profissional=p1, recorrente=False, dataInicio=dt.date(2026, 11, 16),
                                         dataFim=dt.date(2026, 11, 16), horaInicio=dt.time(8, 0), horaFim=dt.time(12, 0))
    resp = c.get(f"/contratos/{contrato.id}/agenda/")
    opcoes_b = [(o["value"], o["allowed_profs"]) for o in resp.context["slot_options"]]
    status, msgs = post(c, contrato, {"slot_1": "0|08:00|08:50", "prof_for_1": p1.id})
    ok_b = (status, msgs, reservas_do_aluno(aluno), {"p1": p1.id})

    # Cenário C: contrato SEMANAL (4 semanas, 1 aula) com horários configurados
    fb, c, p1, p2 = nova_base()
    models.HorarioFuncionamento.objects.create(unidade=fb.unidade, diaSemana=0, horaInicio=dt.time(9, 0), horaFim=dt.time(10, 0))
    models.HorarioFuncionamento.objects.create(unidade=fb.unidade, diaSemana=2, horaInicio=dt.time(9, 0), horaFim=dt.time(10, 0))
    aluno = fb.aluno("Aluna C")
    plano = fb.plano(aulas=3, recorrencia="SEMANAL")
    contrato = fb.contrato(aluno, plano, p1, dt.date(2026, 11, 2), dt.date(2027, 2, 2), recorrencia="SEMANAL")
    resp = c.get(f"/contratos/{contrato.id}/agenda/")
    ctx = resp.context
    semanal_info = (ctx["aulas_por_semana"], ctx["agenda_semanas"], [o["value"] for o in ctx["slot_options"]])
    status, msgs = post(c, contrato, {"slot_1": "0|09:00|09:50", "prof_for_1": p1.id})
    ok_c = (status, msgs, reservas_do_aluno(aluno))
    models.Reserva.objects.filter(aluno=aluno).delete()
    status, msgs = post(c, contrato, {"slot_1": "0|09:00|09:50", "prof_for_1": p1.id, "slot_2": "2|09:00|09:50", "prof_for_2": p1.id})
    slot_extra_c = (status, msgs, reservas_do_aluno(aluno))
    _limpar_banco()

    escrever(
        "agenda", SLOTS=slots, BLOQUEIOS_DEF=defs, BLOQUEADOS=bloqueados, BLOQUEADOS_JUNTOS=juntos, ALINHAR=alinhar,
        AVANCAR=avancar, HORARIOS_DEF=horarios_def, FUNCIONAMENTO=funcionamento, BLOQ_DB_DEF=bloq_def, BLOQ_DB_CARREGADOS=carregados,
        IDS_A=ids_a, OPCOES_A=opcoes_a, ERROS_A=erros_a, OK_A=ok_a, OPCOES_B=opcoes_b, OK_B=ok_b, SEMANAL_INFO=semanal_info,
        OK_C=ok_c, SLOT_EXTRA_C=slot_extra_c,
    )


def sec_financeiro():
    from unittest import mock

    from studiopilates.core import models, views

    m = models
    f = Fabrica().base(capacidade=5)
    prof = f.profissional("Prof")
    # categorias / planos
    cat_r = m.Categoria.objects.create(cdCategoria=f.prox(), dsCategoria="Mensalidades", tipo="RECEITA")
    sub_r1 = m.Subcategoria.objects.create(cdSubcategoria=f.prox(), cdCategoria=cat_r, dsSubcategoria="Planos 2x")
    sub_r2 = m.Subcategoria.objects.create(cdSubcategoria=f.prox(), cdCategoria=cat_r, dsSubcategoria="Planos 3x")
    cat_d = m.Categoria.objects.create(cdCategoria=f.prox(), dsCategoria="Fixas", tipo="DESPESA")
    sub_d1 = m.Subcategoria.objects.create(cdSubcategoria=f.prox(), cdCategoria=cat_d, dsSubcategoria="Imovel")
    sub_d2 = m.Subcategoria.objects.create(cdSubcategoria=f.prox(), cdCategoria=cat_d, dsSubcategoria="Servicos")
    forn_a = m.Fornecedor.objects.create(cdFornecedor=f.prox(), dsFornecedor="Imobiliaria")
    forn_b = m.Fornecedor.objects.create(cdFornecedor=f.prox(), dsFornecedor="Contador")

    plano_a = f.plano(valor="300", aulas=2, meses=3)
    plano_a.dsPlano = "Pilates 2x"
    plano_a.categoria_receita, plano_a.subcategoria_receita = cat_r, sub_r1
    plano_a.save()
    plano_b = f.plano(valor="450", aulas=3, meses=3)
    plano_b.dsPlano = "Pilates 3x"
    plano_b.categoria_receita, plano_b.subcategoria_receita = cat_r, sub_r2
    plano_b.save()
    plano_c = f.plano(valor="100", aulas=1, meses=1)
    plano_c.dsPlano = "Pilates 2x"  # mesmo nome do plano A, outra linha (a DRE agrupa por NOME)
    plano_c.save()

    ana, bia, caio = f.aluno("Ana"), f.aluno("Bia"), f.aluno("Caio")
    c_a = f.contrato(ana, plano_a, prof, dt.date(2026, 9, 1), dt.date(2026, 12, 1))
    c_b = f.contrato(bia, plano_b, prof, dt.date(2026, 9, 1), dt.date(2026, 12, 1))
    c_c = f.contrato(caio, plano_c, prof, dt.date(2026, 9, 1), dt.date(2026, 12, 1))
    sess = f.sessao(dt.date(2026, 10, 12), dt.time(9, 0), dt.time(9, 50), prof)
    res = f.reserva(caio, sess)

    def receber(**kw):
        return m.ContasReceber.objects.create(**kw)

    D = dt.date
    receber(contrato=c_a, status="PAGO", valor=Decimal("300.00"), dtVencimento=D(2026, 10, 5), dtPagamento=D(2026, 10, 6))
    receber(contrato=c_a, status="ABERTO", valor=Decimal("300.00"), dtVencimento=D(2026, 11, 5))
    receber(reserva=res, status="PAGO", valor=Decimal("80.00"), dtVencimento=D(2026, 10, 12), dtPagamento=D(2026, 10, 12))
    receber(aluno=ana, descricao="Avulso", status="ABERTO", valor=Decimal("50.00"), dtVencimento=D(2026, 10, 15))
    receber(contrato=c_a, status="CANCELADO", valor=Decimal("100.00"), dtVencimento=D(2026, 10, 10))
    receber(contrato=c_b, status="PAGO", valor=Decimal("450.00"), dtVencimento=D(2026, 10, 20), dtPagamento=D(2026, 10, 20))
    receber(contrato=c_b, status="PAGO", valor=Decimal("450.00"), dtVencimento=D(2026, 10, 2), dtPagamento=D(2026, 9, 30))
    receber(contrato=c_a, status="ABERTO", valor=Decimal("300.00"), dtVencimento=D(2026, 10, 1))
    receber(contrato=c_c, status="PAGO", valor=Decimal("100.00"), dtVencimento=D(2026, 10, 25), dtPagamento=D(2026, 10, 25))
    receber(contrato=c_a, status="PAGO", valor=Decimal("33.33"), dtVencimento=D(2026, 10, 31), dtPagamento=D(2026, 10, 31))
    receber(contrato=c_b, status="ABERTO", valor=Decimal("12.00"), dtVencimento=D(2026, 10, 25))  # vence "hoje"

    def pagar(**kw):
        k = f.prox()
        return m.ContasPagar.objects.create(cdContasPagar=k, **kw)

    pagar(cdFornecedor=forn_a, cdCategoria=cat_d, cdSubcategoria=sub_d1, dtVencimento=D(2026, 10, 10), valor=Decimal("1500.00"), status="PAGO", dtPagamento=D(2026, 10, 9))
    pagar(cdFornecedor=forn_b, cdCategoria=cat_d, cdSubcategoria=sub_d2, dtVencimento=D(2026, 10, 28), valor=Decimal("200.00"), status="AGENDADO")
    pagar(cdFornecedor=forn_b, cdCategoria=cat_d, cdSubcategoria=sub_d2, dtVencimento=D(2026, 10, 15), valor=Decimal("999.00"), status="CANCELADO")
    pagar(cdFornecedor=forn_b, cdCategoria=cat_d, cdSubcategoria=sub_d2, dtVencimento=D(2026, 10, 31), valor=Decimal("80.50"), status="PAGO", dtPagamento=D(2026, 10, 21))
    pagar(cdFornecedor=forn_a, cdCategoria=cat_d, cdSubcategoria=sub_d1, dtVencimento=D(2026, 10, 1), valor=Decimal("100.00"), status="AGENDADO")
    pagar(cdFornecedor=forn_a, cdCategoria=cat_d, cdSubcategoria=sub_d1, dtVencimento=D(2026, 9, 28), valor=Decimal("60.00"), status="PAGO", dtPagamento=D(2026, 10, 3))
    pagar(cdFornecedor=forn_b, cdCategoria=cat_d, cdSubcategoria=sub_d2, dtVencimento=D(2026, 10, 25), valor=Decimal("7.00"), status="AGENDADO")  # vence "hoje"

    conta1 = m.ContaBancaria.objects.create(cdConta=f.prox(), banco="B1", agencia="1", conta="1", saldo_inicial=Decimal("1000.00"))
    conta2 = m.ContaBancaria.objects.create(cdConta=f.prox(), banco="B2", agencia="2", conta="2", saldo_inicial=Decimal("500.00"))
    m.ContaBancaria.objects.create(cdConta=f.prox(), banco="B3", agencia="3", conta="3", saldo_inicial=Decimal("9999.00"), ativo=False)
    for conta, tipo, valor, dia in [(conta1, "ENTRADA", "200.00", D(2026, 9, 15)), (conta1, "SAIDA", "50.00", D(2026, 9, 20)),
                                    (conta1, "ENTRADA", "70.00", D(2026, 10, 5)), (conta2, "ENTRADA", "30.00", D(2026, 9, 1)),
                                    (conta2, "SAIDA", "10.25", D(2026, 9, 30))]:
        m.MovimentoConta.objects.create(conta=conta, tipo=tipo, valor=Decimal(valor), data=dia)

    # --- entradas "cruas" (para o teste reconstruir os objetos puros)
    receitas_db = []
    for r in m.ContasReceber.objects.select_related("contrato", "contrato__cdAluno", "contrato__cdPlano", "contrato__cdPlano__categoria_receita",
                                                    "contrato__cdPlano__subcategoria_receita", "reserva", "reserva__aluno", "reserva__aulaSessao",
                                                    "reserva__aulaSessao__tipoServico").order_by("id"):
        receitas_db.append({
            "id": r.id, "status": r.status, "valor": r.valor, "vencimento": r.dtVencimento, "pagamento": r.dtPagamento,
            "contrato_cd": r.contrato.cdContrato if r.contrato_id else None,
            "aluno_do_contrato": r.contrato.cdAluno.dsNome if r.contrato_id else None,
            "plano": r.contrato.cdPlano.dsPlano if r.contrato_id else None,
            "categoria": r.contrato.cdPlano.categoria_receita.dsCategoria if r.contrato_id and r.contrato.cdPlano.categoria_receita_id else None,
            "subcategoria": r.contrato.cdPlano.subcategoria_receita.dsSubcategoria if r.contrato_id and r.contrato.cdPlano.subcategoria_receita_id else None,
            "reserva_aluno": r.reserva.aluno.dsNome if r.reserva_id else None,
            "reserva_hora": r.reserva.aulaSessao.horaInicio if r.reserva_id else None,
            "reserva_servico": r.reserva.aulaSessao.tipoServico.dsTipoServico if r.reserva_id else None,
        })
    despesas_db = [
        {"id": p.id, "status": p.status, "valor": p.valor, "vencimento": p.dtVencimento, "pagamento": p.dtPagamento,
         "fornecedor": str(p.cdFornecedor), "categoria": str(p.cdCategoria), "subcategoria": str(p.cdSubcategoria)}
        for p in m.ContasPagar.objects.select_related("cdFornecedor", "cdCategoria", "cdSubcategoria").order_by("id")
    ]
    contas_banco = [(c.id, c.saldo_inicial, c.ativo) for c in m.ContaBancaria.objects.order_by("id")]
    movimentos = [(mv.conta_id, mv.tipo, mv.valor, mv.data) for mv in m.MovimentoConta.objects.order_by("id")]

    # --- fluxo de caixa (função interna por período)
    def pack(d):
        return {
            "base": d["saldo_bancario_base"], "final": d["saldo_projetado_final"], "receitas": d["total_receitas"], "despesas": d["total_despesas"],
            "lancamentos": [(x["data"], x["tipo"], x["origem"], x["descricao"], x["detalhe"], x["status"], x["valor"]) for x in d["lancamentos"]],
            "diario": [(x["data"], x["receitas"], x["despesas"], x["saldo"]) for x in d["saldo_diario"]],
            "semanal": [(x["inicio"], x["fim"], x["receitas"], x["despesas"], x["saldo"]) for x in d["saldo_semanal"]],
        }

    fluxos = []
    for inicio, fim, conta in [(D(2026, 10, 1), D(2026, 10, 31), "all"), (D(2026, 10, 10), D(2026, 10, 17), "all"),
                               (D(2026, 10, 1), D(2026, 10, 31), str(conta1.id)), (D(2026, 10, 1), D(2026, 10, 31), str(conta2.id)),
                               (D(2026, 11, 1), D(2026, 11, 30), "all"), (D(2026, 10, 25), D(2026, 10, 25), "all")]:
        d = views._build_fluxo_caixa_data_for_period(inicio, fim, conta_filtro=conta)
        fluxos.append((inicio, fim, conta == "all", conta if conta == "all" else int(conta), pack(d)))

    c = _cliente_logado()
    resp = c.get("/financeiro/fluxo-caixa/?inicio=2026-10-01&fim=2026-10-31")
    comp = resp.context["comparativo_mes_anterior"]
    comparativo = dict(comp)

    clamp = []
    for base in [D(2026, 3, 31), D(2026, 1, 31), D(2026, 10, 31), D(2024, 3, 31), D(2026, 12, 31), D(2026, 1, 15)]:
        for n in [-1, 1, -2, 2, -13]:
            clamp.append((base, n, views._shift_month_clamped(base, n)))

    # --- DRE
    dres = []
    for inicio, fim in [("2026-10-01", "2026-10-31"), ("2026-10-10", "2026-10-21"), ("2026-11-01", "2026-11-30"), ("2026-09-01", "2026-09-30")]:
        resp = c.get(f"/financeiro/dre/relatorio/?inicio={inicio}&fim={fim}")
        x = resp.context
        import json as _json
        dres.append((inicio, fim, {
            "receita_bruta": x["receita_bruta"], "despesas_operacionais": x["despesas_operacionais"], "resultado_final": x["resultado_final"],
            "resultado_label": x["resultado_label"], "saldo_anterior": x["saldo_bancario_anterior"], "saldo_final": x["saldo_bancario_final"],
            "por_plano": list(zip(_json.loads(x["chart_receitas_labels"]), _json.loads(x["chart_receitas_values"]))),
            "por_categoria": list(zip(_json.loads(x["chart_receitas_cat_labels"]), _json.loads(x["chart_receitas_cat_values"]))),
            "por_subcategoria": list(zip(_json.loads(x["chart_receitas_sub_labels"]), _json.loads(x["chart_receitas_sub_values"]))),
            "desp_categoria": list(zip(_json.loads(x["chart_despesas_labels"]), _json.loads(x["chart_despesas_values"]))),
            "desp_subcategoria": list(zip(_json.loads(x["chart_despesas_sub_labels"]), _json.loads(x["chart_despesas_sub_values"]))),
        }))
        resp2 = c.get(f"/financeiro/dre/?inicio={inicio}&fim={fim}")
        dres[-1][2]["simples"] = (resp2.context["total_receitas"], resp2.context["total_despesas"], resp2.context["resultado"], resp2.context["status_label"])

    # --- atraso (ATRASADO derivado) com "hoje" fixo; e o efeito do now().date() em UTC
    def com_agora(agora):
        return mock.patch.object(views.timezone, "now", lambda: agora)

    utc = dt.UTC
    atraso = {}
    for rotulo, agora in [("tarde_brt", dt.datetime(2026, 10, 25, 15, 0, tzinfo=utc)), ("noite_brt_ja_amanha_utc", dt.datetime(2026, 10, 26, 1, 0, tzinfo=utc))]:
        with com_agora(agora):
            resp = c.get("/financeiro/contas-pagar/?status=ATRASADO&inicio=2026-01-01&fim=2026-12-31")
            ids_pagar = sorted(o.id for o in resp.context["page"])
            disp = {o.id: o.display_status for o in resp.context["page"]}
            resp_all = c.get("/financeiro/contas-pagar/?inicio=2026-01-01&fim=2026-12-31")
            disp_all = {o.id: o.display_status for o in resp_all.context["page"]}
            dash = c.get("/")
            atraso[rotulo] = {"pagar_atrasadas_ids": ids_pagar, "pagar_display": disp_all, "receber_atrasadas_dashboard": dash.context["contas_atrasadas"]}

    # --- recorrência de contas a pagar (POST real)
    recs = []
    for rec, qtd, venc in [("SEMANAL", 4, D(2026, 10, 31)), ("MENSAL", 5, D(2026, 1, 31)), ("MENSAL", 14, D(2026, 11, 15)), ("ANUAL", 3, D(2024, 2, 29)),
                           ("ANUAL", 3, D(2026, 10, 10)), ("MENSAL", 1, D(2026, 10, 10)), ("MENSAL", 0, D(2026, 10, 10)), ("", 5, D(2026, 10, 10)),
                           ("SEMANAL", 2, D(2026, 12, 28)), ("MENSAL", 3, D(2026, 12, 29))]:
        m.ContasPagar.objects.all().delete()
        resp = c.post("/financeiro/contas-pagar/criar/", {
            "cdFornecedor": forn_a.id, "cdCategoria": cat_d.id, "cdSubcategoria": sub_d1.id, "dtVencimento": venc.isoformat(),
            "valor": "100.00", "recorrencia": rec, "recorrencia_quantidade": str(qtd),
        })
        criadas = [(p.dtVencimento, p.recorrencia, p.recorrencia_quantidade, p.status, p.valor) for p in m.ContasPagar.objects.order_by("cdContasPagar")]
        recs.append((rec, qtd, venc, resp.status_code, criadas))

    # --- cobrança de aula avulsa (R12) via view de agenda do pacote
    _limpar_banco()
    escrever(
        "financeiro", RECEITAS=receitas_db, DESPESAS=despesas_db, CONTAS_BANCO=contas_banco, MOVIMENTOS=movimentos, FLUXOS=fluxos,
        COMPARATIVO=comparativo, SHIFT_CLAMPED=clamp, DRES=dres, ATRASO=atraso, RECORRENCIAS=recs,
    )


def sec_avulsa():
    from django.contrib.messages import get_messages
    from studiopilates.core import models

    m = models
    D = dt.date
    resultados = []

    def cenario(rotulo, recorrencia_plano, valor_plano, quantidade, valor_informado, inicio, slot, dois_servicos=False):
        _limpar_banco()
        f = Fabrica().base(capacidade=3)
        c = _cliente_logado()
        prof = f.profissional("Prof")
        extra = m.TipoServico.objects.create(cdTipoServico=f.prox(), dsTipoServico="Alongamento")
        for dia in (0, 1, 2, 5):
            h = m.HorarioFuncionamento.objects.create(unidade=f.unidade, diaSemana=dia, horaInicio=dt.time(9, 0), horaFim=dt.time(10, 0))
            if dois_servicos:
                h.tipos_servico.add(f.tipo, extra)
        plano = f.plano(valor=valor_plano, aulas=1, meses=1, recorrencia=recorrencia_plano, avulso=True)
        aluno = f.aluno("Aluno Avulso")
        dados = {"plano": plano.id, "unidade": f.unidade.id, "profissional": prof.id, "quantidade": quantidade,
                 "valor_aula": valor_informado, "dtInicio": inicio.isoformat()}
        resp = c.post(f"/cadastros/alunos/{aluno.id}/aulas-avulsas/criar/", dados)
        pacote = m.AulaAvulsa.objects.get()
        info = {"recorrencia": pacote.recorrencia, "quantidade": pacote.quantidade, "valor_aula": pacote.valor_aula,
                "valor_total": pacote.valor_total, "inicio": pacote.dtInicio, "fim": pacote.dtFim}
        url = f"/cadastros/alunos/{aluno.id}/aulas-avulsas/{pacote.id}/agenda/"
        resp = c.post(url, {"slot_1": slot, "prof_for_1": prof.id})
        msgs = [x.message for x in get_messages(resp.wsgi_request)]
        contas = [(x.dtVencimento, x.competencia, x.valor, x.status, x.contrato_id, x.reserva_id is not None)
                  for x in m.ContasReceber.objects.order_by("dtVencimento", "id")]
        reservas = [(r.aulaSessao.data, r.aulaSessao.tipoServico.dsTipoServico) for r in
                    m.Reserva.objects.select_related("aulaSessao", "aulaSessao__tipoServico").order_by("aulaSessao__data", "aulaSessao__tipoServico__dsTipoServico")]
        resultados.append({
            "rotulo": rotulo, "plano": (recorrencia_plano, valor_plano), "entrada": (quantidade, valor_informado, inicio, slot),
            "pacote": info, "mensagens": msgs, "contas": contas, "reservas": reservas,
        })

    cenario("semanal_valor_do_plano", "SEMANAL", "80", 3, "", D(2026, 11, 2), "0|09:00|09:50")
    cenario("mensal_valor_informado", "MENSAL", "80", 3, "75.50", D(2026, 11, 2), "0|09:00|09:50")
    cenario("cortesia_valor_zero", "SEMANAL", "80", 2, "0", D(2026, 11, 2), "0|09:00|09:50")
    cenario("comeca_na_terca_slot_segunda_fora_do_periodo", "SEMANAL", "80", 4, "", D(2026, 11, 3), "0|09:00|09:50")
    cenario("mensal_dia_31", "MENSAL", "60", 3, "", D(2026, 1, 31), "5|09:00|09:50")
    cenario("dois_servicos_no_horario", "SEMANAL", "80", 2, "", D(2026, 11, 2), "0|09:00|09:50", dois_servicos=True)
    _limpar_banco()
    escrever("avulsa", CENARIOS=resultados)


def sec_receita():
    from django.utils.text import slugify
    from studiopilates.core import receita_saude as rs

    D = dt.date
    CPF_PROF, CPF_ALUNO, CPF_PAI = "52998224725", "11144477735", "39053344705"

    def cfg(**kw):
        base = dict(cpf_profissional=CPF_PROF, registro_profissional="79013-F", codigo_ocupacao="231", descricao_padrao="Aulas de Pilates")
        base.update(kw)
        return SimpleNamespace(**base)

    def aluno(cpf=CPF_ALUNO, pagador="", sem_cpf=False):
        return SimpleNamespace(dsCPF=cpf, sem_cpf=sem_cpf, cpf_pagador_recibo=pagador)

    def conta(valor="150.00", pago=D(2026, 10, 5), status="PAGO", descricao="", competencia="2026-10", venc=D(2026, 10, 5)):
        return SimpleNamespace(status=status, dtPagamento=pago, valor=Decimal(valor), descricao=descricao, competencia=competencia, dtVencimento=venc)

    # cada caso: rotulo, parametros (dicts simples para o teste reconstruir), saida do antigo
    casos = []

    def caso(rotulo, itens_def, config_def):
        itens = [(conta(**c), aluno(**a)) for c, a in itens_def]
        config = None if config_def is None else cfg(**config_def)
        conteudo, erros = rs.gerar_arquivo(itens, config)
        casos.append({"rotulo": rotulo, "itens": itens_def, "config": config_def, "conteudo": conteudo, "erros": erros})

    um = [({}, {})]
    caso("simples", um, {})
    caso("valor_1234_50", [({"valor": "1234.5"}, {})], {})
    caso("pagador_diferente", [({}, {"pagador": "390.533.447-05"})], {})
    caso("descricao_acentos_e_ponto_virgula", [({"descricao": "Sessão; fisioterapia\ncom acentuação " + "x" * 400, "competencia": ""}, {})], {})
    caso("competencia_ja_na_descricao", [({"descricao": "Mensalidade 2026-10"}, {})], {})
    caso("sem_descricao_usa_padrao", [({"descricao": "", "competencia": ""}, {})], {})
    caso("varias_linhas_ordem_dada", [({"pago": D(2026, 10, 20), "valor": "200"}, {}), ({"pago": D(2026, 10, 5)}, {})], {})
    caso("config_none", um, None)
    caso("cpf_profissional_invalido", um, {"cpf_profissional": "123"})
    caso("ocupacao_invalida", um, {"codigo_ocupacao": "999"})
    caso("registro_longo_e_com_espacos", um, {"registro_profissional": "  1234567890123456789  "})
    caso("registro_vazio", um, {"registro_profissional": ""})
    caso("sem_itens", [], {})
    caso("nao_paga", [({"status": "ABERTO"}, {})], {})
    caso("sem_data_pagamento", [({"pago": None}, {})], {})
    caso("valor_zero", [({"valor": "0"}, {})], {})
    caso("aluno_sem_cpf_campo_vazio", [({}, {"cpf": ""})], {})
    caso("aluno_sem_cpf_flag", [({}, {"sem_cpf": True})], {})
    caso("cpf_aluno_invalido", [({}, {"cpf": "12345678900"})], {})
    caso("cpf_pagador_invalido", [({}, {"pagador": "11111111111"})], {})
    caso("anos_misturados", [({"pago": D(2025, 12, 30)}, {}), ({"pago": D(2026, 1, 2)}, {})], {})
    caso("mil_linhas", [({}, {})] * 1000, {})
    caso("mil_e_uma_linhas", [({}, {})] * 1001, {})
    caso("varios_erros_juntos", [({"status": "ABERTO", "valor": "0", "pago": None}, {"cpf": "1"})], {"cpf_profissional": "1", "codigo_ocupacao": "1"})
    # resumo curto para os casos grandes (mil linhas): guarda só o tamanho
    for c in casos:
        if c["rotulo"] in ("mil_linhas",):
            c["conteudo"] = ("QTD_LINHAS", c["conteudo"].count("\r\n"), c["conteudo"].split("\r\n")[0])
            c["itens"] = ("REPETIR", 1000)
        if c["rotulo"] == "mil_e_uma_linhas":
            c["itens"] = ("REPETIR", 1001)

    nomes = [(n, i, slugify(n) or i) for n, i in [("Ana Souza", 1), ("José da Conceição", 2), ("", 3), ("  Maria--Lúcia  ", 4), ("O'Neil & Co.", 5), ("123", 6)]]
    escrever("receita_saude", CASOS=casos, SLUGS=nomes, MAX_LINHAS=rs.MAX_LINHAS, OCUPACOES=rs.OCUPACOES)


def sec_tokens():
    from unittest import mock

    from django.core import signing
    from django.test import override_settings
    from studiopilates.core import services

    chave = os.environ["DJANGO_SECRET_KEY"]
    t0 = 1_761_400_000

    def com_tempo(agora):
        return mock.patch("django.core.signing.time.time", lambda: float(agora))

    emitidos = []
    for pk in [1, 123, 99999999, 7]:
        for ts in [t0, 1_700_000_000, 1_000_000_000, 4_000_000_000]:
            with com_tempo(ts):
                tc = services.gerar_token_contrato(SimpleNamespace(pk=pk))
                tt = services.gerar_token_termo(SimpleNamespace(pk=pk))
            emitidos.append((pk, ts, tc, tt))

    def tentar(fn, token):
        try:
            return ("ok", fn(token))
        except signing.SignatureExpired:
            return ("erro", "SignatureExpired")
        except signing.BadSignature:
            return ("erro", "BadSignature")
        except Exception as exc:  # noqa: BLE001
            return ("erro", type(exc).__name__)

    with com_tempo(t0):
        token_contrato = services.gerar_token_contrato(SimpleNamespace(pk=123))
        token_termo = services.gerar_token_termo(SimpleNamespace(pk=4567))
    dia = 86400
    validacoes = []
    for rotulo, agora in [("na_hora", t0), ("seis_dias", t0 + 6 * dia), ("sete_dias_exatos", t0 + 7 * dia), ("sete_dias_mais_1s", t0 + 7 * dia + 1),
                          ("trinta_dias_exatos", t0 + 30 * dia), ("trinta_dias_mais_1s", t0 + 30 * dia + 1), ("futuro_100s", t0 - 100), ("um_ano", t0 + 365 * dia)]:
        with com_tempo(agora):
            validacoes.append((rotulo, agora, tentar(services.validar_token_contrato, token_contrato), tentar(services.validar_token_termo, token_termo),
                               tentar(services.validar_token_termo, token_contrato), tentar(services.validar_token_contrato, token_termo)))
    adulterados = []
    with com_tempo(t0 + 10):
        variacoes = {
            "ultimo_char": token_contrato[:-1] + ("A" if token_contrato[-1] != "A" else "B"),
            "valor_trocado": "124" + token_contrato[3:],
            "timestamp_trocado": token_contrato.split(":")[0] + ":" + "zzzzzz" + ":" + token_contrato.split(":")[2],
            "sem_assinatura": token_contrato.rsplit(":", 1)[0],
            "vazio": "",
            "lixo": "lixo",
            "so_valor": "123",
            "assinatura_truncada": token_contrato[:-5],
            "dois_pontos_extra": token_contrato + ":x",
        }
        for nome, tok in variacoes.items():
            adulterados.append((nome, tok, tentar(services.validar_token_contrato, tok)))
    chave_errada = []
    with override_settings(SECRET_KEY="outra-chave-qualquer"), com_tempo(t0 + 10):
        chave_errada.append(tentar(services.validar_token_contrato, token_contrato))
    escrever(
        "tokens", CHAVE=chave, T0=t0, EMITIDOS=emitidos, TOKEN_CONTRATO=token_contrato, TOKEN_TERMO=token_termo, VALIDACOES=validacoes,
        ADULTERADOS=adulterados, CHAVE_ERRADA=chave_errada,
    )


def sec_contratos():
    from unittest import mock

    from studiopilates.core import models, views

    m = models
    D = dt.date
    f = Fabrica().base(capacidade=5)
    c = _cliente_logado()
    prof = f.profissional("Prof")
    outra_unidade = m.Unidade.objects.create(cdUnidade=f.prox(), dsUnidade="Outra", capacidade=5, duracao_aula_minutos=50)
    outro_tipo = m.TipoServico.objects.create(cdTipoServico=f.prox(), dsTipoServico="Alongamento")
    plano = f.plano(valor="300", aulas=2, meses=1)
    ana, bia = f.aluno("Ana"), f.aluno("Bia")
    c1 = f.contrato(ana, plano, prof, D(2026, 11, 2), D(2026, 11, 30))
    c2 = f.contrato(ana, plano, prof, D(2026, 11, 20), D(2026, 12, 20))   # sobrepoe c1 (mesmo aluno/unidade/servico)
    c3 = f.contrato(bia, plano, prof, D(2026, 11, 2), D(2026, 11, 30))

    rotulos = {}

    def reserva(rotulo, aluno, data, ini=dt.time(9, 0), unidade=None, tipo=None, status="RESERVADA", avulsa=False, sessao=None, evolucao=False):
        s = sessao or f.sessao(data, ini, dt.time(ini.hour, 50), prof, unidade=unidade, tipo=tipo)
        r = m.Reserva.objects.create(aluno=aluno, aulaSessao=s, status=status)
        if avulsa:
            pacote = m.AulaAvulsa.objects.create(
                cdAulaAvulsa=f.prox(), aluno=aluno, plano=plano, unidade=f.unidade, profissional=prof, quantidade=1,
                valor_aula=Decimal("80"), valor_total=Decimal("80"), dtInicio=data, dtFim=data,
            )
            r.pacote_avulso = pacote
            r.save()
        if evolucao:
            m.EvolucaoAluno.objects.create(reserva=r, profissional=prof, texto="evolucao")
        rotulos[r.id] = rotulo
        return r, s

    compartilhada = f.sessao(D(2026, 11, 3), dt.time(8, 0), dt.time(8, 50), prof)
    reserva("r1_compartilhada_com_bia", ana, D(2026, 11, 3), sessao=compartilhada)
    reserva("r1b_bia_na_compartilhada", bia, D(2026, 11, 3), sessao=compartilhada)
    reserva("r2_sozinha", ana, D(2026, 11, 10))
    reserva("r3_outro_servico", ana, D(2026, 11, 12), tipo=outro_tipo)
    reserva("r4_outra_unidade", ana, D(2026, 11, 14), unidade=outra_unidade)
    reserva("r5_depois_do_fim", ana, D(2026, 12, 1))
    reserva("r6_no_primeiro_dia", ana, D(2026, 11, 2))
    reserva("r7_no_ultimo_dia", ana, D(2026, 11, 30), ini=dt.time(10, 0))
    reserva("r8_aula_avulsa_no_periodo", ana, D(2026, 11, 5), avulsa=True)
    reserva("r9_concluida", ana, D(2026, 11, 6), status="CONCLUIDA", evolucao=True)
    reserva("r10_cancelada", ana, D(2026, 11, 9), status="CANCELADA")
    reserva("r11_so_do_contrato_2", ana, D(2026, 12, 10))
    reserva("r12_na_sobreposicao", ana, D(2026, 11, 25))
    reserva("r13_antes_do_inicio", ana, D(2026, 11, 1))
    reserva("r14_da_bia", bia, D(2026, 11, 11))

    def conta(rotulo, **kw):
        k = m.ContasReceber.objects.create(**kw)
        rotulos[("c", k.id)] = rotulo
        return k

    conta("c1_pago", contrato=c1, status="PAGO", valor=Decimal("300"), dtVencimento=D(2026, 11, 5), dtPagamento=D(2026, 11, 5))
    conta("c1_aberto", contrato=c1, status="ABERTO", valor=Decimal("300"), dtVencimento=D(2026, 12, 5))
    conta("c1_cancelado", contrato=c1, status="CANCELADO", valor=Decimal("300"), dtVencimento=D(2026, 12, 6))
    conta("c2_aberto", contrato=c2, status="ABERTO", valor=Decimal("300"), dtVencimento=D(2026, 12, 5))
    conta("avulsa_da_ana", aluno=ana, status="ABERTO", valor=Decimal("50"), dtVencimento=D(2026, 11, 15))
    conta("c3_da_bia", contrato=c3, status="ABERTO", valor=Decimal("300"), dtVencimento=D(2026, 11, 5))

    # entradas "cruas" do cenario (para o teste reconstruir)
    contratos_def = [(x.id, x.cdAluno_id, x.cdUnidade_id, x.cdPlano.cdTipoServico_id, x.dtInicioContrato, x.dtFimContrato) for x in m.Contrato.objects.order_by("id")]
    reservas_def = [(r.id, rotulos[r.id], r.aluno_id, r.aulaSessao_id, r.aulaSessao.data, r.aulaSessao.unidade_id, r.aulaSessao.tipoServico_id,
                     r.status, r.pacote_avulso_id, m.EvolucaoAluno.objects.filter(reserva=r).exists())
                    for r in m.Reserva.objects.select_related("aulaSessao").order_by("id")]
    contas_def = [(k.id, rotulos[("c", k.id)], k.contrato_id, k.status) for k in m.ContasReceber.objects.order_by("id")]

    resumos = {}
    resp = c.get(f"/contratos/{c1.id}/excluir/")
    resumos["c1"] = dict(resp.context["delete_summary"])
    resp = c.get(f"/contratos/{c3.id}/excluir/")
    resumos["c3"] = dict(resp.context["delete_summary"])

    # sem confirmacao: nada acontece
    resp = c.post(f"/contratos/{c1.id}/excluir/", {})
    sem_confirmar = (resp.status_code, m.Contrato.objects.filter(id=c1.id).exists(), m.Reserva.objects.count(), m.ContasReceber.objects.count())

    sessoes_antes = set(m.AulaSessao.objects.values_list("id", flat=True))
    resp = c.post(f"/contratos/{c1.id}/excluir/", {"confirm_delete": "1"})
    apos_reservas = sorted(rotulos[i] for i in m.Reserva.objects.values_list("id", flat=True))
    apos_contas = sorted(rotulos[("c", i)] for i in m.ContasReceber.objects.values_list("id", flat=True))
    sessoes_apagadas = sorted(sessoes_antes - set(m.AulaSessao.objects.values_list("id", flat=True)))
    evolucoes_restantes = m.EvolucaoAluno.objects.count()
    todas_labels = sorted(rotulos[r[0]] for r in reservas_def)
    apagadas = sorted(set(todas_labels) - set(apos_reservas))
    contas_apagadas = sorted(set(v for k, v in rotulos.items() if isinstance(k, tuple)) - set(apos_contas))

    # --- gestao de contratos (data fixa)
    _limpar_banco()
    f = Fabrica().base(capacidade=5)
    c = _cliente_logado()
    prof = f.profissional("Prof")
    plano = f.plano()
    hoje = D(2026, 10, 25)
    fins = [("venceu_ontem", D(2026, 10, 24), D(2026, 9, 1)), ("vence_hoje", D(2026, 10, 25), D(2026, 9, 1)), ("vence_em_3", D(2026, 10, 28), D(2026, 9, 1)),
            ("vence_em_7", D(2026, 11, 1), D(2026, 9, 1)), ("vence_em_8", D(2026, 11, 2), D(2026, 9, 1)), ("vence_em_30", D(2026, 11, 24), D(2026, 9, 1)),
            ("vence_em_31", D(2026, 11, 25), D(2026, 9, 1)), ("comeca_amanha_vence_em_20", D(2026, 11, 14), D(2026, 10, 26)), ("comeca_amanha_vence_em_90", D(2027, 1, 23), D(2026, 10, 26)),
            ("termina_hoje_comecou_hoje", D(2026, 10, 25), D(2026, 10, 25)), ("vencido_ha_um_ano", D(2025, 10, 25), D(2025, 1, 1))]
    ids = {}
    for rotulo, fim, ini in fins:
        al = f.aluno(rotulo)
        ct = f.contrato(al, plano, prof, ini, fim)
        ids[ct.id] = rotulo
    agora = dt.datetime(2026, 10, 25, 15, 0, tzinfo=dt.UTC)
    gestao = {}
    with mock.patch.object(views.timezone, "now", lambda: agora):
        for filtro in ["ativos", "vencendo", "vencidos", "todos", "xyz", ""]:
            resp = c.get(f"/contratos/gestao/?filtro={filtro}")
            gestao[filtro] = {
                "filtro_efetivo": resp.context["filtro"],
                "contratos": [(ids[x["obj"].id], x["dias_restantes"], x["situacao"], x["badge"]) for x in resp.context["contratos"]],
                "resumo": dict(resp.context["resumo"]),
            }
        painel = c.get("/")
        contratos_vencendo_painel = painel.context["contratos_vencendo"]
        alertas = list(painel.context["alertas"])
    _limpar_banco()
    escrever(
        "contratos", CONTRATOS=contratos_def, RESERVAS=reservas_def, CONTAS=contas_def, RESUMOS_CONFIRMACAO=resumos, SEM_CONFIRMAR=sem_confirmar,
        RESERVAS_APAGADAS=apagadas, CONTAS_APAGADAS=contas_apagadas, SESSOES_APAGADAS_QTD=len(sessoes_apagadas), EVOLUCOES_RESTANTES=evolucoes_restantes,
        HOJE=hoje, GESTAO=gestao, FINS=[(r, fim, ini) for r, fim, ini in fins], CONTRATOS_VENCENDO_PAINEL=contratos_vencendo_painel, ALERTAS=alertas,
    )


def sec_whatsapp():
    from unittest import mock

    from studiopilates.core import models, views
    from studiopilates.core import whatsapp_scheduler as ws
    from studiopilates.core.whatsapp_service import WhatsappService

    m = models
    D = dt.date
    T = dt.time

    # ---- templates padrão do modelo e renderização (as duas funções antigas)
    campos = ["template_aviso_aluno", "template_aviso_professor", "template_link_contrato", "template_aviso_renovacao", "template_aniversario",
              "template_fim_contrato", "template_vencimento_proximo", "template_mensalidade_atraso", "template_tres_meses"]
    padroes = {c: m.WhatsappConfiguracao._meta.get_field(c).default for c in campos}
    horarios_padrao = {c: m.WhatsappConfiguracao._meta.get_field(c).default for c in
                       ["horario_aviso_aluno", "horario_aviso_professor", "horario_aviso_renovacao", "horario_aviso_aniversario", "horario_aviso_vencimento",
                        "horario_aviso_atraso", "horario_aviso_tres_meses"]}
    ligados_padrao = {c: m.WhatsappConfiguracao._meta.get_field(c).default for c in
                      ["avisar_aluno", "avisar_professor", "avisar_renovacao", "avisar_aniversario", "avisar_vencimento", "avisar_atraso", "avisar_tres_meses",
                       "avisar_fim_contrato", "enviar_link_contrato"]}

    modelos = [
        "Ola {aluno}", "  Ola {aluno}  ", "", "   ", None, "Oi {aluno}, {faltando} e {aluno}", "R$ {valor} em {data}", "{{literal}} {aluno}",
        "{aluno", "aluno}", "{0}", "{aluno.nome}", "{valor:.2f}", "{aluno!r}", "Sem variaveis", "Multi\nlinha {aluno}\n{aluno}", "{aluno} {aluno}",
        "{ALUNO}", "Chave {PIX_CHAVE}", "100% {aluno}", "{}", "{ aluno }", "{aluno:>10}|", "{n:03d}",
    ]
    contexto = dict(aluno="Ana", valor="300,00", data="27/10/2026", horario="08:00", n=5, vazio=None)
    render_views = [(t, views._render_whatsapp_template(t, **contexto)) for t in modelos]
    render_sched = [(t, ws._render_template(t, **contexto)) for t in modelos]

    # ---- cenario para os avisos automaticos
    f = Fabrica().base(capacidade=9)
    outra_unidade = m.Unidade.objects.create(cdUnidade=f.prox(), dsUnidade="Outra", capacidade=5)
    prof1 = f.profissional("Natalia", celular="(15) 98111-2222")
    prof2 = f.profissional("Sem Celular", celular="")
    tipo_alt = m.TipoServico.objects.create(cdTipoServico=f.prox(), dsTipoServico="Alongamento")
    hoje = D(2026, 10, 26)       # segunda-feira
    amanha = D(2026, 10, 27)
    plano = f.plano(valor="300", aulas=2, meses=3)

    ana = f.aluno("Ana", telefone="(15) 99776-2467", nascimento=D(1990, 10, 26))
    bia = f.aluno("Bia", telefone="11 98888-7777", nascimento=D(1985, 10, 26), status="INATIVO")
    caio = f.aluno("Caio", telefone=None, nascimento=D(2000, 2, 29))
    duda = f.aluno("Duda", telefone="21 97777-6666", nascimento=D(1995, 10, 27))
    edu = f.aluno("Edu", telefone="31 96666-5555")
    fabi = f.aluno("Fabi", telefone="41 95555-4444", unidade=outra_unidade)
    dani = f.aluno("Dani", telefone="51 94444-3333", nascimento=D(1992, 1, 1))
    gabi = f.aluno("Gabi", telefone="(15) 3333-4444")        # so fixo
    hugo = f.aluno("Hugo", telefone="123")                    # telefone invalido

    def res(aluno, ini, status="RESERVADA", prof=prof1, tipo=None, unidade=None, dia=amanha):
        s = f.sessao(dia, ini, T(ini.hour, 50), prof, tipo=tipo, unidade=unidade)
        return f.reserva(aluno, s, status)

    res(ana, T(8, 0))
    res(ana, T(9, 0), status="PENDENTE", prof=prof2)
    res(bia, T(10, 0), status="CONCLUIDA")
    res(bia, T(11, 0), tipo=tipo_alt)
    res(caio, T(8, 0))
    res(duda, T(8, 0), status="CANCELADA")
    res(edu, T(9, 0), status="FALTOU_AVISOU")
    res(edu, T(10, 0), status="FALTOU_SEM_AVISAR")
    res(fabi, T(8, 0), unidade=outra_unidade)
    res(gabi, T(14, 0), prof=None)
    res(hugo, T(15, 0))
    res(dani, T(7, 0), status="PENDENTE")

    def ctr(aluno, ini, fim, status="ASSINADO", unidade=None):
        return f.contrato(aluno, plano, prof1, ini, fim, status=status, unidade=unidade)

    k1 = ctr(ana, D(2026, 8, 3), hoje + dt.timedelta(days=7))
    k2 = ctr(bia, D(2026, 8, 3), hoje + dt.timedelta(days=7), status="NAO_ASSINADO")
    k3 = ctr(caio, D(2026, 8, 3), hoje + dt.timedelta(days=7), status="ASSINADO_DIGITALMENTE")
    k4 = ctr(duda, D(2026, 8, 3), hoje + dt.timedelta(days=6))
    k5 = ctr(dani, hoje - dt.timedelta(days=90), hoje + dt.timedelta(days=100))
    k6 = ctr(edu, hoje - dt.timedelta(days=89), hoje + dt.timedelta(days=100))
    k7 = ctr(gabi, hoje - dt.timedelta(days=90), hoje + dt.timedelta(days=100), status="NAO_ASSINADO")
    k8 = ctr(fabi, hoje + dt.timedelta(days=0), hoje + dt.timedelta(days=7), unidade=outra_unidade)

    def conta(contrato, status, venc, valor="300.00", **kw):
        return m.ContasReceber.objects.create(contrato=contrato, status=status, valor=Decimal(valor), dtVencimento=venc, **kw)

    cv1 = conta(k1, "ABERTO", amanha, "300.00")
    cv2 = conta(k2, "ABERTO", amanha, "150.5")
    conta(k1, "PAGO", amanha)
    conta(k3, "ATRASADO", amanha)
    conta(k1, "ABERTO", amanha + dt.timedelta(days=1))
    m.ContasReceber.objects.create(aluno=ana, status="ABERTO", valor=Decimal("50"), dtVencimento=amanha)
    conta(k8, "ABERTO", amanha)   # outra unidade
    ca1 = conta(k1, "ABERTO", D(2026, 10, 1), "300.00")
    ca2 = conta(k1, "ABERTO", D(2026, 10, 10), "300.00")
    ca3 = conta(k2, "ATRASADO", D(2026, 10, 20), "80.00")
    conta(k1, "PAGO", D(2026, 10, 1))
    conta(k1, "CANCELADO", D(2026, 10, 1))
    conta(k1, "ABERTO", hoje)

    cfg = m.WhatsappConfiguracao.objects.create(unidade=f.unidade)
    cfg_outra = m.WhatsappConfiguracao.objects.create(unidade=outra_unidade)

    chamadas = []

    def falso_send(self, aluno_obj, telefone, mensagem, tipo, contrato=None):
        chamadas.append(("aluno", aluno_obj.dsNome, telefone, mensagem, str(tipo), contrato.cdContrato if contrato else None))
        return {"ok": True}

    class ClienteFalso:
        def send_message(self, telefone, mensagem):
            chamadas.append(("professor", None, telefone, mensagem, None, None))
            return {"ok": True}

    def rodar(nome, fn, *args, **kw):
        antes = len(chamadas)
        retorno = fn(*args, **kw)
        logs = [(x.dedupe_key, x.tipo, x.telefone, x.data_referencia) for x in m.WhatsappAgendamentoLog.objects.order_by("id")]
        return {"funcao": nome, "retorno": retorno, "chamadas": chamadas[antes:], "logs_total": len(logs)}

    sleeps = mock.patch.object(ws.time, "sleep", lambda s: None)
    with sleeps, mock.patch.object(WhatsappService, "send", falso_send), \
            mock.patch.object(WhatsappService, "_get_client_for_unidade", lambda self, u: ClienteFalso()):
        servico = WhatsappService()
        execucoes = []
        for rodada in (1, 2):   # a 2a rodada prova o dedupe
            resultado = {}
            for nome, fn, args in [
                ("lembrete_aluno", ws._send_class_reminders, (servico, cfg, amanha)),
                ("agenda_professor", ws._send_professor_schedule, (servico, cfg, amanha)),
                ("renovacao", ws._send_contract_renewals, (servico, cfg, hoje + dt.timedelta(days=7))),
                ("aniversario", ws._send_birthdays, (servico, cfg, hoje)),
                ("vencimento", ws._send_payment_due, (servico, cfg, hoje)),
                ("atraso", ws._send_payment_overdue, (servico, cfg, hoje)),
                ("tres_meses", ws._send_three_months, (servico, cfg, hoje)),
            ]:
                r = rodar(nome, fn, *args)
                if isinstance(r["retorno"], dict):
                    r["entradas"] = [(e["aluno"], e["status"], e["telefone"], e["mensagem"]) for e in r["retorno"]["entries"]]
                    r["retorno"] = {k: v for k, v in r["retorno"].items() if k != "entries"}
                resultado[nome] = r
            execucoes.append(resultado)
        # resumo detalhado do lembrete (entries) a partir de um novo cálculo forçado
        forcado = ws._send_class_reminders  # noqa: F841 (documentacao)
        chaves_log = sorted(x.dedupe_key for x in m.WhatsappAgendamentoLog.objects.all())

        # templates em branco + force=True: usa os fallbacks do codigo (ou nao envia)
        m.WhatsappAgendamentoLog.objects.all().delete()
        cfg.template_aviso_aluno = ""
        cfg.template_aviso_professor = ""
        cfg.template_aviso_renovacao = ""
        cfg.template_aniversario = ""
        cfg.template_vencimento_proximo = ""
        cfg.template_mensalidade_atraso = ""
        cfg.template_tres_meses = ""
        cfg.save()
        branco = {}
        for nome, fn, args in [
            ("lembrete_aluno", ws._send_class_reminders, (servico, cfg, amanha)),
            ("agenda_professor", ws._send_professor_schedule, (servico, cfg, amanha)),
            ("renovacao", ws._send_contract_renewals, (servico, cfg, hoje + dt.timedelta(days=7))),
            ("aniversario", ws._send_birthdays, (servico, cfg, hoje)),
            ("vencimento", ws._send_payment_due, (servico, cfg, hoje)),
            ("atraso", ws._send_payment_overdue, (servico, cfg, hoje)),
            ("tres_meses", ws._send_three_months, (servico, cfg, hoje)),
        ]:
            r = rodar(nome, fn, *args, force=True)
            if isinstance(r["retorno"], dict):
                r["entradas"] = [(e["aluno"], e["status"], e["telefone"], e["mensagem"]) for e in r["retorno"]["entries"]]
                r["retorno"] = {k: v for k, v in r["retorno"].items() if k != "entries"}
            branco[nome] = r

        # montar_mensagem_lembrete direto (UI ao vivo)
        cfg.template_aviso_aluno = "Aluno {aluno} {aulas} | {horarios} | {unidade} {data} {tipo_servico} {horario}"
        reservas_ana = ws.reservas_lembrete_por_aluno(cfg, amanha)
        grupo_ana = next(v for k, v in reservas_ana.items() if v[0].aluno.dsNome == "Ana")
        mensagem_ui = ws.montar_mensagem_lembrete(cfg, grupo_ana, amanha)

    # ---- _run_jobs: quais avisos disparam em cada horario (sem PG: o advisory lock e simulado)
    m.WhatsappAgendamentoLog.objects.all().delete()
    m.WhatsappConfiguracao.objects.filter(pk=cfg.pk).update(
        template_aviso_aluno="L {aluno}", template_aviso_professor="P {horario}", template_aviso_renovacao="R {aluno}",
        template_aniversario="A {aluno}", template_vencimento_proximo="V {aluno}", template_mensalidade_atraso="T {aluno}",
        template_tres_meses="M {aluno}", avisar_aniversario=True, avisar_vencimento=True, avisar_atraso=True, avisar_tres_meses=True,
    )
    m.WhatsappConfiguracao.objects.filter(pk=cfg_outra.pk).update(avisar_aluno=False, avisar_professor=False, avisar_renovacao=False)
    quando = {}
    for hhmm in [(0, 0), (8, 59), (9, 0), (9, 5), (10, 0), (17, 59), (18, 0), (18, 5), (19, 0), (23, 55)]:
        m.WhatsappAgendamentoLog.objects.all().delete()
        agora = dt.datetime(2026, 10, 26, hhmm[0], hhmm[1], tzinfo=__import__("zoneinfo").ZoneInfo("America/Sao_Paulo"))
        antes = len(chamadas)
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
        with sleeps, mock.patch.object(WhatsappService, "send", falso_send), \
                mock.patch.object(WhatsappService, "_get_client_for_unidade", lambda self, u: ClienteFalso()), \
                mock.patch.object(ws, "connection", fake_conn), \
                mock.patch.object(ws.timezone, "now", lambda a=agora: a), mock.patch.object(ws.timezone, "localtime", lambda value=None, a=agora: a), \
                mock.patch.object(ws.timezone, "localdate", lambda value=None, a=agora: a.date()):
            ws._run_jobs()
        tipos = sorted(set(l.dedupe_key.split(":")[0] for l in m.WhatsappAgendamentoLog.objects.all()))
        quando[f"{hhmm[0]:02d}:{hhmm[1]:02d}"] = tipos

    respostas = [
        {"error": "Session not connected"}, {"error": "x", "response": {"message": "WhatsApp session is not connected"}}, {"error": "timeout"},
        {"ok": True}, None, "texto", {"error": None, "response": {"message": "Session disconnected: please connect"}},
        {"error": "Rate", "retry_after": 12}, {"error": "x", "response": {"retry_after": "30"}}, {"retry_after": "abc", "error": "y"},
        {"error": "x", "retry_after": 2}, {"error": "x", "retry_after": 0}, {"status": "sent"}, {"error": "SESSION CONNECT lost"}, {"response": "ok"},
    ]
    sessao_caiu = [(r, ws._is_session_down(r)) for r in respostas]
    retry = []
    for r in respostas:
        pausas = []
        with mock.patch.object(ws.time, "sleep", lambda sec: pausas.append(sec)):
            final = ws._send_with_retry(lambda r=r: r, attempts=3, pause_seconds=5.0)
        retry.append((r, pausas, final))

    definicoes = {
        "alunos": [(a.id, a.dsNome, a.cdUnidade_id, a.status, a.dtNascimento, [t.dsTelefone for t in a.telefones.all()]) for a in m.Aluno.objects.order_by("id")],
        "reservas": [(r.id, r.aluno_id, r.status, r.aulaSessao.data, r.aulaSessao.horaInicio, r.aulaSessao.tipoServico.dsTipoServico, r.aulaSessao.unidade_id,
                      r.aulaSessao.unidade.dsUnidade, r.aulaSessao.profissional_id) for r in m.Reserva.objects.select_related("aulaSessao", "aulaSessao__tipoServico", "aulaSessao__unidade").order_by("id")],
        "profissionais": [(p.id, p.profissional, p.celular) for p in m.Profissional.objects.exclude(profissional__startswith="admin").order_by("id")],
        "contratos": [(k.id, k.cdContrato, k.cdAluno_id, k.cdUnidade_id, k.dtInicioContrato, k.dtFimContrato, k.status) for k in m.Contrato.objects.order_by("id")],
        "contas": [(c.id, c.contrato_id, c.status, c.valor, c.dtVencimento) for c in m.ContasReceber.objects.order_by("id")],
        "unidades": {f.unidade.id: f.unidade.dsUnidade, outra_unidade.id: outra_unidade.dsUnidade},
        "principal": f.unidade.id,
    }
    escrever(
        "whatsapp", PADROES=padroes, HORARIOS_PADRAO=horarios_padrao, LIGADOS_PADRAO=ligados_padrao, MODELOS=modelos, CONTEXTO=contexto,
        RENDER_VIEWS=render_views, RENDER_SCHEDULER=render_sched, HOJE=hoje, AMANHA=amanha, DEFINICOES=definicoes, EXECUCOES=execucoes,
        CHAVES_LOG=chaves_log, EM_BRANCO=branco, MENSAGEM_UI=mensagem_ui, QUANDO=quando, SESSAO_CAIU=sessao_caiu, RETRY=retry,
    )


SECOES = {
    "precos": sec_precos,
    "parcelas": sec_parcelas,
    "telefone": sec_telefone,
    "documentos": sec_documentos,
    "capacidade": sec_capacidade,
    "reposicao": sec_reposicao,
    "status_aula": sec_status_aula,
    "agenda": sec_agenda,
    "financeiro": sec_financeiro,
    "avulsa": sec_avulsa,
    "receita": sec_receita,
    "tokens": sec_tokens,
    "contratos": sec_contratos,
    "whatsapp": sec_whatsapp,
}


def main(argv: list[str]) -> None:
    _boot()
    escolhidas = argv or list(SECOES)
    for nome in escolhidas:
        SECOES[nome]()
        _limpar_banco()


if __name__ == "__main__":
    main(sys.argv[1:])
