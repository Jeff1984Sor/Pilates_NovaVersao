"""Comunicado geral: prévia, fila um a um com pausa, pausar/retomar/cancelar, falhas e relatório."""
from datetime import timedelta

from sqlalchemy import select

from app.modules.alunos.models import StatusAluno, WhatsappMensagem
from app.modules.comunicacao import comunicados as com
from tests.comunicacao.conftest import AGORA, FALHA, SESSAO_CAIDA

URL = "/api/comunicacao/comunicados"


def criar(client, h, **extra):
    corpo = {"texto": "Olá {aluno}, recado da {unidade}.", "publico": "ativos", "unidade_id": None} | extra
    return client.post(URL, json=corpo, headers=h)


def rodar(n=1, inicio=AGORA, passo=6):
    """n passadas do worker, `passo` segundos entre elas (maior que a pausa padrão de 5 s)."""
    return [com.processar_pendentes(inicio + timedelta(seconds=passo * i)) for i in range(n)]


def test_previa_mostra_contagem_e_primeiro_aluno(client, full, cenario):
    r = client.post(URL + "/previa", json={"texto": "Oi {aluno} ({unidade})", "publico": "ativos"}, headers=full)
    j = r.json()
    assert j["total"] == 4 and j["com_telefone"] == 2 and j["sem_telefone"] == 2
    assert j["primeiro_aluno"] == "João Lima" and j["mensagem"] == "Oi João Lima (Matriz)"  # 1º por ordem alfabética COM telefone


def test_publico_ativos_inativos_e_todos(client, full, cenario, db):
    cenario.joao.status = StatusAluno.INATIVO
    db.commit()
    p = lambda pub: client.post(URL + "/previa", json={"texto": "x", "publico": pub}, headers=full).json()["total"]  # noqa: E731
    assert (p("ativos"), p("inativos"), p("todos")) == (3, 1, 4)
    assert client.post(URL + "/previa", json={"texto": "x", "publico": "todos", "unidade_id": 9999}, headers=full).status_code == 404


def test_filtro_por_unidade(client, full, cenario, db):
    from tests.agenda import fabrica

    filial = fabrica.unidade(db, nome="Filial")
    fabrica.aluno(db, filial, "Aluno da Filial", "5511999990009")
    db.commit()
    assert client.post(URL + "/previa", json={"texto": "x", "publico": "todos", "unidade_id": filial.id}, headers=full).json()["total"] == 1


def test_envio_um_a_um_e_progresso_ate_concluir(client, full, cenario, falso, db):
    c = criar(client, full).json()
    assert c["status"] == "enviando" and c["total"] == 4 and c["sem_telefone"] == 2 and c["pendentes"] == 2
    assert falso.chamadas == 0  # a requisição não envia: quem envia é o worker
    rodar(1)
    p = client.get(f"{URL}/{c['id']}", headers=full).json()
    assert p["enviados"] == 1 and p["status"] == "enviando" and p["percentual"] == 75
    rodar(1, inicio=AGORA + timedelta(seconds=60))
    p = client.get(f"{URL}/{c['id']}", headers=full).json()
    assert p["status"] == "concluido" and p["enviados"] == 2 and p["percentual"] == 100 and p["finalizado_em"]
    assert [t for _, t in falso.textos] == ["Olá João Lima, recado da Matriz.", "Olá Maria Souza, recado da Matriz."]
    assert {m.tipo for m in db.scalars(select(WhatsappMensagem))} == {"comunicado"}


def test_respeita_a_pausa_entre_envios(client, full, cenario, falso):
    c = criar(client, full, pausa_segundos=None).json()
    com.processar_pendentes(AGORA)
    com.processar_pendentes(AGORA + timedelta(seconds=2))  # ainda dentro da pausa de 5 s
    assert falso.chamadas == 1
    com.processar_pendentes(AGORA + timedelta(seconds=5))
    assert falso.chamadas == 2 and client.get(f"{URL}/{c['id']}", headers=full).json()["status"] == "concluido"


def test_duas_passadas_no_mesmo_instante_nao_duplicam(client, full, cenario, falso):
    criar(client, full)
    com.processar_pendentes(AGORA)
    com.processar_pendentes(AGORA)
    assert falso.chamadas == 1


def test_pausar_e_retomar(client, full, cenario, falso):
    c = criar(client, full).json()
    rodar(1)
    assert client.post(f"{URL}/{c['id']}/pausar", headers=full).json()["status"] == "pausado"
    rodar(3, inicio=AGORA + timedelta(seconds=60))
    assert falso.chamadas == 1  # pausado: nada sai
    assert client.post(f"{URL}/{c['id']}/pausar", headers=full).status_code == 409
    assert client.post(f"{URL}/{c['id']}/retomar", headers=full).json()["status"] == "enviando"
    rodar(1, inicio=AGORA + timedelta(seconds=120))
    assert falso.chamadas == 2
    assert client.post(f"{URL}/{c['id']}/retomar", headers=full).status_code == 409


def test_cancelar_para_o_envio_e_marca_pendentes(client, full, cenario, falso):
    c = criar(client, full).json()
    rodar(1)
    r = client.post(f"{URL}/{c['id']}/cancelar", headers=full).json()
    assert r["status"] == "cancelado" and r["cancelados"] == 1 and r["enviados"] == 1
    rodar(3, inicio=AGORA + timedelta(seconds=60))
    assert falso.chamadas == 1
    assert client.post(f"{URL}/{c['id']}/cancelar", headers=full).status_code == 409


def test_falhas_sao_contadas_e_listadas_no_relatorio(client, full, cenario, falso, sem_espera):
    c = criar(client, full).json()
    falso.roteiro = [FALHA, FALHA, FALHA]  # os 3 retries do 1º destinatário
    rodar(3)
    p = client.get(f"{URL}/{c['id']}", headers=full).json()
    assert p["status"] == "concluido" and p["falhas"] == 1 and p["enviados"] == 1 and p["sem_telefone"] == 2
    rel = client.get(f"{URL}/{c['id']}/destinatarios", headers=full).json()
    assert {d["status"] for d in rel} == {"falha", "enviado", "sem_telefone"}
    falha = next(d for d in rel if d["status"] == "falha")
    assert falha["erro"] == "erro temporário"
    only = client.get(f"{URL}/{c['id']}/destinatarios?status=sem_telefone", headers=full).json()
    assert {d["nome"] for d in only} == {"Sem Telefone", "Telefone Fixo"}


def test_sessao_caida_pausa_o_comunicado_sem_perder_ninguem(client, full, cenario, falso):
    c = criar(client, full).json()
    falso.roteiro = [SESSAO_CAIDA]
    rodar(1)
    p = client.get(f"{URL}/{c['id']}", headers=full).json()
    assert p["status"] == "pausado" and "desconectada" in p["aviso"] and p["pendentes"] == 2 and p["falhas"] == 0
    client.post(f"{URL}/{c['id']}/retomar", headers=full)
    rodar(2, inicio=AGORA + timedelta(minutes=5))
    assert client.get(f"{URL}/{c['id']}", headers=full).json()["status"] == "concluido"
    assert falso.chamadas == 3  # 1 que falhou por sessão + 2 envios


def test_comunicado_sem_aluno_ou_texto_vazio(client, full, cenario, db):
    assert criar(client, full, texto="   ").status_code in (422,)
    cenario.maria.status = cenario.joao.status = cenario.sem_tel.status = cenario.fixo.status = StatusAluno.INATIVO
    db.commit()
    assert criar(client, full, publico="ativos").status_code == 422


def test_unidade_sem_whatsapp_configurado_vira_falha_do_destinatario(client, full, cenario, falso, db):
    from app.modules.comunicacao import servico as svc

    svc.obter_config(db, cenario.un.id).credencial_cifrado = None
    db.commit()
    c = criar(client, full).json()
    rodar(3)
    p = client.get(f"{URL}/{c['id']}", headers=full).json()
    assert p["falhas"] == 2 and p["status"] == "concluido" and falso.chamadas == 0


def test_listar_e_auditoria(client, full, cenario, db):
    from app.core.models import Auditoria

    c = criar(client, full).json()
    client.post(f"{URL}/{c['id']}/cancelar", headers=full)
    lista = client.get(URL, headers=full).json()
    assert lista[0]["id"] == c["id"]
    acoes = {a.acao for a in db.scalars(select(Auditoria))}
    assert {"comunicacao.comunicado.criar", "comunicacao.comunicado.cancelar"} <= acoes
    assert client.get(f"{URL}/9999", headers=full).status_code == 404


def test_secretaria_pode_enviar_comunicado(client, secretaria, cenario):
    assert criar(client, secretaria).status_code == 201
