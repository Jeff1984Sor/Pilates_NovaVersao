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
    from django.apps import apps

    for model in reversed(list(apps.get_app_config("core").get_models())):
        model.objects.all().delete()


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
    from studiopilates.core.validators import validar_cpf
    from studiopilates.core import receita_saude

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

    from django.utils import timezone
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
    from django.test import Client

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


SECOES = {
    "precos": sec_precos,
    "parcelas": sec_parcelas,
    "telefone": sec_telefone,
    "documentos": sec_documentos,
    "capacidade": sec_capacidade,
    "reposicao": sec_reposicao,
    "status_aula": sec_status_aula,
    "agenda": sec_agenda,
}


def main(argv: list[str]) -> None:
    _boot()
    escolhidas = argv or list(SECOES)
    for nome in escolhidas:
        SECOES[nome]()
        _limpar_banco()


if __name__ == "__main__":
    main(sys.argv[1:])
