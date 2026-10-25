"""Contrato "golden" da API de integração externa: o mesmo cenário sintético e as mesmas chamadas, com as respostas do
código ANTIGO (gravadas em ``golden/api_antiga.json`` por ``golden/gerar_golden_antigo.py``), exigem respostas idênticas
do sistema novo. As diferenças deliberadas estão listadas em ``DIVERGENCIAS`` (cada uma com o motivo).
"""

from __future__ import annotations

import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.domain.telefone import normalizar_telefone_br
from app.modules.agenda.models import AulaSessao, Reserva
from app.modules.alunos.models import Aluno, AlunoTelefone, WhatsappMensagem
from app.modules.cadastros.models import IntegracaoToken, Plano, Profissional, TipoServico, Unidade
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber
from app.modules.integracoes import tokens

GOLDEN = json.loads((Path(__file__).parent / "golden" / "api_antiga.json").read_text(encoding="utf-8"))
CENARIO = GOLDEN["cenario"]

#: id da chamada -> motivo da divergência (o novo responde diferente do antigo DE PROPÓSITO)
DIVERGENCIAS = {
    # o antigo buscava `dsTelefone__contains=<8 dígitos>` num campo guardado COM máscara e nunca achava; o novo compara o
    # número normalizado e acha o aluno (o comportamento pretendido do antigo).
    "tel_mascara": "antigo=404 por bug da máscara",
    "tel_digitos": "antigo=404 por bug da máscara",
    "tel_ddi": "antigo=404 por bug da máscara",
    "tel_sem_nono": "antigo=404 por bug da máscara",
}
TEL_ANA = "(15) 99776-2467"


def _d(s):
    return date.fromisoformat(s) if s else None


def montar_cenario_novo(db):
    """O mesmo cenário do golden, no banco novo (ids na mesma ordem de criação => mesmos ids)."""
    c = CENARIO
    un = Unidade(nome=c["unidade"]["nome"], capacidade=c["unidade"]["capacidade"])
    srv = TipoServico(nome=c["tipo_servico"])
    prof = Profissional(nome=c["profissional"])
    db.add_all([un, srv, prof])
    db.flush()
    plano = Plano(nome=c["plano"]["nome"], tipo_servico_id=srv.id, valor=Decimal(c["plano"]["valor"]),
                  aulas_por_semana=c["plano"]["aulas"], duracao_meses=6)
    db.add(plano)
    for t in c["tokens"]:
        db.add(IntegracaoToken(nome=t["nome"], token_hash=tokens.hash_token(t["valor"]), token_final=t["valor"][-4:],
                               ativo=t["ativo"]))
    alunos = {}
    for a in c["alunos"]:
        al = Aluno(nome=a["nome"], cpf="".join(ch for ch in a["cpf"] if ch.isdigit()), email=a["email"] or None,
                   status=a["status"], unidade_id=un.id, codigo_legado=a["cd"])
        db.add(al)
        db.flush()
        alunos[a["cd"]] = al
        for i, tel in enumerate(a["telefones"], start=1):
            digitos = "".join(ch for ch in tel if ch.isdigit())
            db.add(AlunoTelefone(aluno_id=al.id, ordem=i, numero=normalizar_telefone_br(digitos), numero_original=tel))
    db.flush()
    contratos = {}
    for k in c["contratos"]:
        ct = Contrato(aluno_id=alunos[k["aluno"]].id, plano_id=plano.id, unidade_id=un.id, profissional_id=prof.id,
                      data_inicio=_d(k["inicio"]), data_fim=_d(k["fim"]), status_assinatura=k["status"],
                      valor_parcela=Decimal(k["parcela"]), valor_total=Decimal(k["total"]), codigo_legado=k["cd"])
        db.add(ct)
        db.flush()
        contratos[k["cd"]] = ct
    for cr in c["contas"]:
        ct = contratos[cr["contrato"]]
        # ATRASADO não é gravado no novo: é uma conta ABERTA vencida
        status = "ABERTO" if cr["status"] == "ATRASADO" else cr["status"]
        db.add(ContaReceber(aluno_id=ct.aluno_id, contrato_id=ct.id, valor=Decimal(cr["valor"]), vencimento=_d(cr["venc"]),
                            competencia=cr["comp"], status=status, pagamento=_d(cr["pag"])))
    db.flush()
    sessoes = []
    for s in c["sessoes"]:
        h, m = map(int, s["ini"].split(":"))
        h2, m2 = map(int, s["fim"].split(":"))
        ss = AulaSessao(unidade_id=un.id, tipo_servico_id=srv.id, profissional_id=prof.id if s["prof"] else None,
                        data=_d(s["data"]), hora_inicio=time(h, m), hora_fim=time(h2, m2))
        db.add(ss)
        db.flush()
        sessoes.append(ss)
    for r in c["reservas"]:
        db.add(Reserva(aluno_id=alunos[r["aluno"]].id, aula_sessao_id=sessoes[r["sessao"]].id, status=r["status"]))
    db.commit()


@pytest.fixture
def cenario_golden(db, hoje_fixo):
    montar_cenario_novo(db)


def _chamar(client, ch):
    url = "/api" + ch["u"]
    return client.request(ch["m"], url, headers=ch["h"], json=ch.get("j"))


@pytest.mark.parametrize("ch", GOLDEN["chamadas"], ids=[c["id"] for c in GOLDEN["chamadas"]])
def test_resposta_igual_a_do_antigo(client, cenario_golden, ch):
    r = _chamar(client, ch)
    if ch["id"] in DIVERGENCIAS:
        assert ch["status"] == 404 and r.status_code == 200
        corpo = r.json()
        assert corpo["cdAluno"] == 101 and corpo["dsTelefone"] == TEL_ANA
        return
    assert r.status_code == ch["status"], r.text
    if ch["status"] == 422:  # só o código: o texto da validação mudou de formato (ver progresso)
        return
    corpo, esperado = r.json(), ch["resposta"]
    if ch["m"] == "POST" and "id" in corpo:  # o id da mensagem depende de quantas já existiam (cada teste começa do zero)
        assert isinstance(corpo.pop("id"), int)
        esperado = {k: v for k, v in esperado.items() if k != "id"}
    assert corpo == esperado


def test_mensagens_gravadas_iguais_as_do_antigo(client, db, cenario_golden):
    for ch in GOLDEN["chamadas"]:
        if ch["m"] == "POST":
            _chamar(client, ch)
    gravadas = [
        {"cdAluno": db.get(Aluno, m.aluno_id).codigo_legado, "direcao": m.direcao.value, "telefone": m.telefone or "",
         "mensagem": m.mensagem, "status": m.status, "contrato_id": m.contrato_id, "tipo": m.tipo}
        for m in db.scalars(select(WhatsappMensagem).order_by(WhatsappMensagem.id))
    ]
    assert gravadas == GOLDEN["mensagens_gravadas"]


def test_ultimo_uso_so_do_token_que_autenticou(client, db, cenario_golden):
    for ch in GOLDEN["chamadas"]:
        _chamar(client, ch)
    usos = {t.nome: t.ultimo_uso is not None for t in db.scalars(select(IntegracaoToken))}
    esperado = {t["nome"]: GOLDEN["token_usado"][t["valor"]] for t in CENARIO["tokens"]}
    assert usos == esperado
