"""Gera o "golden" da API de integração do sistema ANTIGO (api/main.py 211-380) com dados SINTÉTICOS.

Roda com o Python do ambiente ANTIGO (tem Django), a partir de ``PilatesFinal/backend`` (somente leitura: nada é
gravado no repositório antigo; o banco SQLite é temporário e fica fora dele):

    $env:PYTHONDONTWRITEBYTECODE = "1"
    <venv antigo>\\python.exe <este arquivo> --saida <repo novo>\\backend\\tests\\integracoes\\golden\\api_antiga.json

O JSON gerado traz o CENÁRIO (dados inventados), as chamadas feitas e as respostas do código antigo. Os testes
do sistema novo (``test_contrato_api_externa.py``) montam o mesmo cenário e exigem respostas idênticas.
Só o status/forma das respostas de erro de validação entram na comparação (a mensagem 422 do FastAPI é outra).
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

CENARIO = {
    "unidade": {"nome": "Studio Golden", "capacidade": 4},
    "tipo_servico": "Pilates",
    "profissional": "Paula Golden",
    "plano": {"nome": "Plano Golden 2x", "valor": "300.00", "aulas": 2},
    "tokens": [
        {"nome": "Chatbot Golden", "valor": "pilates_golden_ativo", "ativo": True},
        {"nome": "Empresa Parada", "valor": "pilates_golden_inativo", "ativo": False},
    ],
    "alunos": [
        {"cd": 101, "nome": "Ana Golden", "cpf": "529.982.247-25", "email": "ana@exemplo.invalid", "status": "ATIVO",
         "telefones": ["(15) 99776-2467", "1133334444"]},
        {"cd": 102, "nome": "Bruno Golden", "cpf": "111.444.777-35", "email": "", "status": "INATIVO", "telefones": []},
        {"cd": 103, "nome": "Carla Golden Silva", "cpf": "390.533.447-05", "email": "carla@exemplo.invalid",
         "status": "ATIVO", "telefones": ["5511988887777"]},
    ],
    "contratos": [
        {"cd": 1, "aluno": 101, "inicio": "2026-01-05", "fim": "2026-06-30", "status": "ASSINADO",
         "parcela": "300.00", "total": "1800.00"},
        {"cd": 2, "aluno": 101, "inicio": "2026-07-01", "fim": "2026-12-31", "status": "NAO_ASSINADO",
         "parcela": "320.50", "total": "1923.00"},
        {"cd": 3, "aluno": 103, "inicio": "2026-02-01", "fim": "2026-04-30", "status": "ASSINADO_DIGITALMENTE",
         "parcela": "150.00", "total": "450.00"},
    ],
    "contas": [
        {"contrato": 2, "valor": "320.50", "venc": "2026-09-10", "comp": "2026-09", "status": "PAGO", "pag": "2026-09-08"},
        {"contrato": 2, "valor": "320.50", "venc": "2026-10-10", "comp": "2026-10", "status": "ABERTO", "pag": None},
        {"contrato": 2, "valor": "320.50", "venc": "2026-08-10", "comp": "2026-08", "status": "ATRASADO", "pag": None},
        {"contrato": 2, "valor": "320.50", "venc": "2026-11-10", "comp": "2026-11", "status": "CANCELADO", "pag": None},
        {"contrato": 1, "valor": "300.00", "venc": "2099-03-10", "comp": None, "status": "ABERTO", "pag": None},
        {"contrato": 3, "valor": "150.00", "venc": "2026-03-05", "comp": "2026-03", "status": "PAGO", "pag": "2026-03-05"},
    ],
    "sessoes": [
        {"data": "2020-03-02", "ini": "09:00", "fim": "09:50", "prof": True},
        {"data": "2099-01-05", "ini": "09:00", "fim": "09:50", "prof": True},
        {"data": "2099-01-06", "ini": "10:00", "fim": "10:50", "prof": False},
        {"data": "2099-01-06", "ini": "08:00", "fim": "08:50", "prof": True},
        {"data": "2099-01-05", "ini": "10:00", "fim": "10:50", "prof": True},
    ],
    "reservas": [
        {"aluno": 101, "sessao": 0, "status": "CONCLUIDA"},
        {"aluno": 101, "sessao": 1, "status": "RESERVADA"},
        {"aluno": 101, "sessao": 2, "status": "RESERVADA"},
        {"aluno": 101, "sessao": 3, "status": "CANCELADA"},
        {"aluno": 103, "sessao": 4, "status": "RESERVADA"},
    ],
}

CH_OK = {"X-API-Key": "pilates_golden_ativo"}
CH_BEARER = {"Authorization": "Bearer pilates_golden_ativo"}
CHAMADAS = [
    # autenticação
    {"id": "sem_chave", "m": "GET", "u": "/integracao/alunos", "h": {}},
    {"id": "chave_errada", "m": "GET", "u": "/integracao/alunos", "h": {"X-API-Key": "pilates_nao_existe"}},
    {"id": "token_inativo", "m": "GET", "u": "/integracao/alunos", "h": {"X-API-Key": "pilates_golden_inativo"}},
    {"id": "bearer_vazio", "m": "GET", "u": "/integracao/alunos", "h": {"Authorization": "Bearer "}},
    {"id": "esquema_basic", "m": "GET", "u": "/integracao/alunos", "h": {"Authorization": "Basic pilates_golden_ativo"}},
    {"id": "bearer_ok", "m": "GET", "u": "/integracao/alunos", "h": CH_BEARER},
    # alunos
    {"id": "alunos", "m": "GET", "u": "/integracao/alunos", "h": CH_OK},
    {"id": "alunos_nome", "m": "GET", "u": "/integracao/alunos?nome=golden%20s", "h": CH_OK},
    {"id": "alunos_nome_minusc", "m": "GET", "u": "/integracao/alunos?nome=ANA", "h": CH_OK},
    {"id": "alunos_status", "m": "GET", "u": "/integracao/alunos?status=inativo", "h": CH_OK},
    {"id": "alunos_limit", "m": "GET", "u": "/integracao/alunos?limit=2", "h": CH_OK},
    {"id": "alunos_limit_0", "m": "GET", "u": "/integracao/alunos?limit=0", "h": CH_OK},
    {"id": "alunos_limit_201", "m": "GET", "u": "/integracao/alunos?limit=201", "h": CH_OK},
    {"id": "por_codigo", "m": "GET", "u": "/integracao/alunos/por-codigo/101", "h": CH_OK},
    {"id": "por_codigo_sem_tel", "m": "GET", "u": "/integracao/alunos/por-codigo/102", "h": CH_OK},
    {"id": "por_codigo_404", "m": "GET", "u": "/integracao/alunos/por-codigo/999", "h": CH_OK},
    {"id": "por_codigo_texto", "m": "GET", "u": "/integracao/alunos/por-codigo/abc", "h": CH_OK},
    {"id": "tel_mascara", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=(15)%2099776-2467", "h": CH_OK},
    {"id": "tel_digitos", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=15997762467", "h": CH_OK},
    {"id": "tel_ddi", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=%2B55%2015%2099776-2467", "h": CH_OK},
    {"id": "tel_sem_nono", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=(15)%209776-2467", "h": CH_OK},
    {"id": "tel_segundo", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=1133334444", "h": CH_OK},
    {"id": "tel_carla", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=11988887777", "h": CH_OK},
    {"id": "tel_carla_ddi", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=5511988887777", "h": CH_OK},
    {"id": "tel_inexistente", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=21999990000", "h": CH_OK},
    {"id": "tel_curto", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=99999999", "h": CH_OK},
    {"id": "tel_letras", "m": "GET", "u": "/integracao/alunos/por-telefone?telefone=abc", "h": CH_OK},
    {"id": "tel_ausente", "m": "GET", "u": "/integracao/alunos/por-telefone", "h": CH_OK},
    # faturas
    {"id": "faturas", "m": "GET", "u": "/integracao/faturas?cdAluno=101", "h": CH_OK},
    {"id": "faturas_aberto", "m": "GET", "u": "/integracao/faturas?cdAluno=101&status=aberto", "h": CH_OK},
    {"id": "faturas_pago", "m": "GET", "u": "/integracao/faturas?cdAluno=101&status=PAGO", "h": CH_OK},
    {"id": "faturas_atrasado", "m": "GET", "u": "/integracao/faturas?cdAluno=101&status=atrasado", "h": CH_OK},
    {"id": "faturas_status_livre", "m": "GET", "u": "/integracao/faturas?cdAluno=101&status=xyz", "h": CH_OK},
    {"id": "faturas_103", "m": "GET", "u": "/integracao/faturas?cdAluno=103", "h": CH_OK},
    {"id": "faturas_sem", "m": "GET", "u": "/integracao/faturas?cdAluno=102", "h": CH_OK},
    {"id": "faturas_sem_param", "m": "GET", "u": "/integracao/faturas", "h": CH_OK},
    # contratos
    {"id": "contratos", "m": "GET", "u": "/integracao/contratos?cdAluno=101", "h": CH_OK},
    {"id": "contratos_103", "m": "GET", "u": "/integracao/contratos?cdAluno=103", "h": CH_OK},
    {"id": "contratos_sem", "m": "GET", "u": "/integracao/contratos?cdAluno=102", "h": CH_OK},
    # aulas
    {"id": "aulas", "m": "GET", "u": "/integracao/aulas?cdAluno=101", "h": CH_OK},
    {"id": "aulas_proximas", "m": "GET", "u": "/integracao/aulas?cdAluno=101&apenas_proximas=true", "h": CH_OK},
    {"id": "aulas_limit", "m": "GET", "u": "/integracao/aulas?cdAluno=101&limit=1", "h": CH_OK},
    {"id": "aulas_103", "m": "GET", "u": "/integracao/aulas?cdAluno=103", "h": CH_OK},
    {"id": "aulas_sem", "m": "GET", "u": "/integracao/aulas?cdAluno=102", "h": CH_OK},
    # mensagens de WhatsApp (escrita)
    {"id": "msg_recebida", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": CH_OK,
     "j": {"cdAluno": 101, "direcao": "recebida", "texto": "Oi, posso remarcar?", "telefone": "5515997762467",
           "data_iso": "2026-10-20T13:30:00Z"}},
    {"id": "msg_enviada_maiuscula", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": CH_OK,
     "j": {"cdAluno": 101, "direcao": " ENVIADA ", "texto": "Claro!", "data_iso": "2026-10-20T13:31:00Z"}},
    {"id": "msg_padrao_recebida", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": CH_OK,
     "j": {"cdAluno": 103, "texto": "Bom dia", "data_iso": "2026-10-20T14:00:00Z", "contrato_id": 999999}},
    {"id": "msg_com_contrato", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": CH_OK,
     "j": {"cdAluno": 101, "texto": "Sobre o contrato", "data_iso": "2026-10-20T14:05:00Z", "contrato_id": "@contrato:2"}},
    {"id": "msg_direcao_invalida", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": CH_OK,
     "j": {"cdAluno": 101, "direcao": "ida", "texto": "x"}},
    {"id": "msg_aluno_404", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": CH_OK,
     "j": {"cdAluno": 999, "texto": "x"}},
    {"id": "msg_sem_texto", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": CH_OK, "j": {"cdAluno": 101}},
    {"id": "msg_sem_chave", "m": "POST", "u": "/integracao/whatsapp-mensagens", "h": {},
     "j": {"cdAluno": 101, "texto": "x"}},
]


def montar_cenario(m, c):
    from datetime import date, time
    from decimal import Decimal

    def d(s):
        return date.fromisoformat(s) if s else None

    perfil = m.PerfilAcesso.objects.create(cdPerfilAcesso=1, dsPerfilAcesso="Padrao")
    un = m.Unidade.objects.create(cdUnidade=1, dsUnidade=c["unidade"]["nome"], capacidade=c["unidade"]["capacidade"],
                                  duracao_aula_minutos=50)
    ts = m.TipoServico.objects.create(cdTipoServico=1, dsTipoServico=c["tipo_servico"])
    prof = m.Profissional.objects.create(cdProfissional=1, profissional=c["profissional"], cdPerfilAcesso=perfil)
    plano = m.Plano.objects.create(cdPlano=1, dsPlano=c["plano"]["nome"], cdTipoServico=ts,
                                   valor=Decimal(c["plano"]["valor"]), aulas_por_semana=c["plano"]["aulas"],
                                   duracao_meses=6)
    for t in c["tokens"]:
        m.IntegracaoToken.objects.create(nome=t["nome"], token=t["valor"], ativo=t["ativo"])
    alunos = {}
    cd_tel = 0
    for a in c["alunos"]:
        al = m.Aluno.objects.create(cdAluno=a["cd"], dsNome=a["nome"], dsCPF=a["cpf"], dsEmail=a["email"],
                                    status=a["status"], cdUnidade=un)
        alunos[a["cd"]] = al
        for tel in a["telefones"]:
            cd_tel += 1
            m.TelefoneAluno.objects.create(cdTelefone=cd_tel, cdAluno=al, dsTelefone=tel)
    contratos = {}
    for k in c["contratos"]:
        contratos[k["cd"]] = m.Contrato.objects.create(
            cdContrato=k["cd"], cdAluno=alunos[k["aluno"]], cdPlano=plano, cdUnidade=un, cdProfissional=prof,
            dtInicioContrato=d(k["inicio"]), dtFimContrato=d(k["fim"]), status=k["status"],
            valor_parcela=Decimal(k["parcela"]), valor_total=Decimal(k["total"]))
    for cr in c["contas"]:
        m.ContasReceber.objects.create(
            contrato=contratos[cr["contrato"]], valor=Decimal(cr["valor"]), dtVencimento=d(cr["venc"]),
            competencia=cr["comp"] or "", status=cr["status"], dtPagamento=d(cr["pag"]))
    sessoes = []
    for s in c["sessoes"]:
        h, mi = map(int, s["ini"].split(":"))
        h2, mi2 = map(int, s["fim"].split(":"))
        sessoes.append(m.AulaSessao.objects.create(
            unidade=un, tipoServico=ts, profissional=prof if s["prof"] else None, data=d(s["data"]),
            horaInicio=time(h, mi), horaFim=time(h2, mi2)))
    for r in c["reservas"]:
        m.Reserva.objects.create(aluno=alunos[r["aluno"]], aulaSessao=sessoes[r["sessao"]], status=r["status"])
    return contratos


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--saida", required=True)
    p.add_argument("--backend-antigo", default=os.getcwd())
    args = p.parse_args()
    backend = Path(args.backend_antigo).resolve()
    raiz = backend.parent
    tmp = Path(tempfile.mkdtemp(prefix="golden-antigo-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp / 'antigo.sqlite').as_posix()}"
    os.environ["MEDIA_ROOT"] = str(tmp / "media")
    os.environ.setdefault("DJANGO_SECRET_KEY", "golden-chave-falsa")
    for caminho in (str(raiz), str(backend)):
        if caminho not in sys.path:
            sys.path.append(caminho)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studiopilates.settings")
    import django

    django.setup()
    from django.core.management import call_command

    call_command("migrate", verbosity=0, interactive=False)
    from studiopilates.core import models as m

    contratos = montar_cenario(m, CENARIO)
    from api.main import app
    from fastapi.testclient import TestClient

    cli = TestClient(app)
    saida = []
    for ch in CHAMADAS:
        corpo = ch.get("j")
        if corpo and str(corpo.get("contrato_id", "")).startswith("@contrato:"):
            corpo = dict(corpo, contrato_id=contratos[int(corpo["contrato_id"].split(":")[1])].id)
        r = cli.request(ch["m"], ch["u"], headers=ch["h"], json=corpo)
        try:
            resp = r.json()
        except ValueError:
            resp = None
        saida.append({**ch, "j": corpo, "status": r.status_code, "resposta": resp})
    # efeito colateral: o que a API gravou (para conferir a escrita) e o uso dos tokens
    msgs = [
        {"cdAluno": x.aluno.cdAluno, "direcao": x.direcao, "telefone": x.telefone, "mensagem": x.mensagem,
         "status": x.status, "contrato_id": x.contrato_id, "tipo": x.tipo}
        for x in m.AlunoWhatsappMessage.objects.order_by("id")
    ]
    usos = {t.token: t.ultimo_uso is not None for t in m.IntegracaoToken.objects.all()}
    Path(args.saida).write_text(
        json.dumps({"cenario": CENARIO, "chamadas": saida, "mensagens_gravadas": msgs, "token_usado": usos},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )
    print(f"{len(saida)} chamadas gravadas em {args.saida}")


if __name__ == "__main__":
    main()
