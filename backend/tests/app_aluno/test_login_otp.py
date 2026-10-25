"""Login do aluno: código por WhatsApp (R15) com os limites que o sistema antigo não tinha."""

from datetime import timedelta

from sqlalchemy import select

from app.modules.alunos.models import AlunoTelefone, AppCodigo, StatusAluno
from tests.agenda import fabrica
from tests.app_aluno.conftest import AGORA_FIXO, codigo_do_zap, cpf_mascarado

URL = "/api/aluno-app/auth"


def pedir(client, cpf):
    return client.post(f"{URL}/codigo", json={"cpf": cpf})


def verificar(client, cpf, codigo):
    return client.post(f"{URL}/verificar", json={"cpf": cpf, "codigo": codigo})


def test_pedido_envia_codigo_de_6_digitos_e_guarda_so_o_hash(client, db, zap, cenario):
    r = pedir(client, cenario.ana.cpf)
    assert r.status_code == 200
    assert len(zap.enviadas) == 1
    telefone, texto = zap.enviadas[0]
    assert telefone == "5511999990001"  # telefone do cadastro normalizado
    codigo = codigo_do_zap(zap)
    assert len(codigo) == 6 and "10 minutos" in texto
    linha = db.scalars(select(AppCodigo)).one()
    assert codigo not in linha.codigo_hash and linha.usado is False
    assert linha.expira_em - linha.criado_em == timedelta(minutes=10)


def test_cpf_com_mascara_funciona(client, zap, cenario):
    assert pedir(client, cpf_mascarado(cenario.ana.cpf)).status_code == 200
    r = verificar(client, cpf_mascarado(cenario.ana.cpf), codigo_do_zap(zap))
    assert r.status_code == 200
    assert {"access_token", "refresh_token", "expira_em_segundos"} <= set(r.json())
    assert r.json()["expira_em_segundos"] == 12 * 3600


def test_resposta_igual_exista_ou_nao_o_cpf(client, db, zap, cenario):
    """Sem enumeração: CPF inexistente, aluno inativo e aluno sem telefone respondem exatamente como o aluno válido."""
    inativo = cenario.bruna
    inativo.status = StatusAluno.INATIVO
    sem_tel = fabrica.aluno(db, cenario.un, "Sem Telefone", telefone=None)
    tel_ruim = fabrica.aluno(db, cenario.un, "Telefone Ruim", telefone="123")
    db.commit()
    respostas = [
        pedir(client, c) for c in (cenario.ana.cpf, "99988877766", inativo.cpf, sem_tel.cpf, tel_ruim.cpf, "abc", "")
    ]
    assert {r.status_code for r in respostas} == {200}
    assert len({r.text for r in respostas}) == 1
    assert len(zap.enviadas) == 1  # só a aluna válida recebeu
    assert len(db.scalars(select(AppCodigo)).all()) == 1


def test_falha_no_envio_nao_muda_a_resposta(client, zap, cenario, monkeypatch):
    def cai(*_):
        raise RuntimeError("caiu")

    monkeypatch.setattr(zap, "enviar_texto", cai)
    assert pedir(client, cenario.ana.cpf).status_code == 200


def test_verificar_com_cpf_inexistente_e_codigo_errado_tem_a_mesma_resposta(client, zap, cenario):
    pedir(client, cenario.ana.cpf)
    certo = codigo_do_zap(zap)
    a = verificar(client, "99988877766", "123456")
    b = verificar(client, cenario.ana.cpf, "000000" if certo != "000000" else "111111")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_codigo_e_de_uso_unico(client, zap, cenario):
    pedir(client, cenario.ana.cpf)
    c = codigo_do_zap(zap)
    assert verificar(client, cenario.ana.cpf, c).status_code == 200
    assert verificar(client, cenario.ana.cpf, c).status_code == 401


def test_novo_pedido_invalida_o_codigo_anterior(client, zap, cenario):
    pedir(client, cenario.ana.cpf)
    antigo = codigo_do_zap(zap)
    pedir(client, cenario.ana.cpf)
    novo = codigo_do_zap(zap)
    if antigo != novo:  # 1 chance em 1 milhão de colidir
        assert verificar(client, cenario.ana.cpf, antigo).status_code == 401
    assert verificar(client, cenario.ana.cpf, novo).status_code == 200


def test_codigo_expira_em_10_minutos(client, zap, cenario, monkeypatch):
    from app.modules.app_aluno import routes

    pedir(client, cenario.ana.cpf)
    c = codigo_do_zap(zap)
    monkeypatch.setattr(routes, "_agora", lambda: AGORA_FIXO + timedelta(minutes=10, seconds=1))
    assert verificar(client, cenario.ana.cpf, c).status_code == 401


def test_vale_ate_o_ultimo_minuto(client, zap, cenario, monkeypatch):
    from app.modules.app_aluno import routes

    pedir(client, cenario.ana.cpf)
    c = codigo_do_zap(zap)
    monkeypatch.setattr(routes, "_agora", lambda: AGORA_FIXO + timedelta(minutes=9, seconds=59))
    assert verificar(client, cenario.ana.cpf, c).status_code == 200


def test_cinco_erros_queimam_o_codigo_mesmo_com_o_certo_depois(client, zap, cenario):
    pedir(client, cenario.ana.cpf)
    certo = codigo_do_zap(zap)
    errado = "000000" if certo != "000000" else "111111"
    for _ in range(5):
        assert verificar(client, cenario.ana.cpf, errado).status_code == 401
    assert verificar(client, cenario.ana.cpf, certo).status_code == 401
    # pedir outro código volta a funcionar
    pedir(client, cenario.ana.cpf)
    assert verificar(client, cenario.ana.cpf, codigo_do_zap(zap)).status_code == 200


def test_limite_de_pedidos_por_cpf(client, zap, cenario):
    assert [pedir(client, cenario.ana.cpf).status_code for _ in range(3)] == [200, 200, 200]
    r = pedir(client, cenario.ana.cpf)
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert len(zap.enviadas) == 3
    # a máscara não burla o limite
    assert pedir(client, cpf_mascarado(cenario.ana.cpf)).status_code == 429
    # CPF inexistente também é limitado do mesmo jeito (não dá para distinguir)
    for _ in range(3):
        assert pedir(client, "99988877766").status_code == 200
    assert pedir(client, "99988877766").status_code == 429


def test_limite_de_pedidos_por_ip(client, zap, cenario):
    codigos = [pedir(client, f"{i:011d}").status_code for i in range(11)]
    assert codigos[:10] == [200] * 10 and codigos[10] == 429


def test_limite_de_tentativas_por_ip_na_verificacao(client, zap, cenario):
    resultados = [verificar(client, f"{i:011d}", "123456").status_code for i in range(21)]
    assert resultados[:20] == [401] * 20 and resultados[20] == 429


def test_telefone_invalido_na_frente_cai_para_o_proximo_valido(client, db, zap, cenario):
    db.add(AlunoTelefone(aluno_id=cenario.ana.id, ordem=0, numero="12"))
    db.commit()
    pedir(client, cenario.ana.cpf)
    assert zap.enviadas[0][0] == "5511999990001"


def test_corpo_invalido_vira_422(client):
    assert client.post(f"{URL}/codigo", json={}).status_code == 422
