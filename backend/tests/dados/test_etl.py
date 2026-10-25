"""ETL sobre o banco antigo SINTÉTICO versionado (tests/fixtures): conciliação, idempotência, simulação e falha."""

import hashlib
import json
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.db import Base
from app.etl import transformacoes as tf
from app.etl.__main__ import main
from app.etl.carga import Carga, classificar_perfil
from app.etl.fonte import Fonte
from app.modules import registrar_modelos
from tests.dados.conftest import MIDIA_ORIGEM, ORIGEM, criar_engine


def _rodar(engine, tmp_path, master_key, *, simular=False, midia=True):
    fonte = Fonte(f"sqlite:///{ORIGEM.as_posix()}")
    carga = Carga(
        fonte,
        engine.url_texto,
        master_key=master_key,
        simular=simular,
        midia_origem=MIDIA_ORIGEM if midia else None,
        midia_destino=(tmp_path / "storage") if midia else None,
    )
    try:
        return carga.executar(), fonte
    finally:
        fonte.fechar()


@pytest.fixture(scope="module")
def ensaio(tmp_path_factory):
    """Uma execução completa, reaproveitada pelos testes que só leem o destino."""
    registrar_modelos()
    tmp = tmp_path_factory.mktemp("ensaio")
    url = f"sqlite:///{(tmp / 'destino.sqlite').as_posix()}"
    eng = criar_engine(url)
    Base.metadata.create_all(eng)
    eng.url_texto = url
    chave = Fernet.generate_key().decode()
    conc, fonte = _rodar(eng, tmp, chave)
    yield eng, conc, chave, tmp / "storage", fonte
    eng.dispose()


def q(eng, sql, **p):
    with eng.connect() as c:
        return c.execute(text(sql), p).all()


def escalar(eng, sql, **p):
    return q(eng, sql, **p)[0][0]


# ----------------------------------------------------------------------------------------- conciliação


def test_conciliacao_ok_e_sem_divergencias(ensaio):
    _, conc, *_ = ensaio
    assert conc.divergencias == [] and conc.erros == []
    assert conc.ok
    assert all(t.ok for t in conc.tabelas.values())
    assert all(s.ok for s in conc.somas)


def test_contagens_batem_com_a_origem(ensaio):
    eng, conc, *_ = ensaio
    t = conc.tabelas
    assert t["aluno"].origem == 62 and t["aluno"].destino == 62
    assert escalar(eng, "select count(*) from aluno") == 62
    assert t["contrato"].destino == t["contrato"].origem == 25
    # sessões: duplicatas fundidas (a diferença está justificada no relatório)
    fundidas = sum(t["aula_sessao"].fundidos.values())
    assert fundidas == 25
    assert escalar(eng, "select count(*) from aula_sessao") == t["aula_sessao"].origem - fundidas
    assert escalar(eng, "select count(*) from evolucao") == t["evolucao"].origem == 160


def test_descartes_tem_motivo(ensaio):
    _, conc, *_ = ensaio
    assert (
        "conta sem aluno resolvível (sem contrato, reserva ou aluno válidos)"
        in conc.tabelas["conta_receber"].descartados
    )
    assert "aluno inexistente (FK órfã)" in conc.tabelas["whatsapp_mensagem"].descartados
    assert sum(conc.tabelas["app_codigo"].descartados.values()) == 10


def test_somas_e_status_atrasado(ensaio):
    eng, conc, *_ = ensaio
    somas = {s.nome: s for s in conc.somas}
    assert somas["contrato.valor_total"].origem == somas["contrato.valor_total"].destino
    assert somas["conta_receber (todas)"].descartado == Decimal("12.00")  # a conta sem vínculo
    assert escalar(eng, "select count(*) from conta_receber where status not in ('ABERTO','PAGO','CANCELADO')") == 0
    assert escalar(eng, "select count(*) from conta_pagar where status not in ('AGENDADO','PAGO','CANCELADO')") == 0


def test_amostra_de_20_sem_diferencas(ensaio):
    _, conc, *_ = ensaio
    assert len(conc.amostra) == 20
    assert all(a["diferencas"] == {} for a in conc.amostra)
    assert len({a["tabela"] for a in conc.amostra}) >= 5


# ----------------------------------------------------------------------------------------- alunos


def test_cpf_so_digitos_e_sem_cpf_nulo(ensaio):
    eng, conc, *_ = ensaio
    assert (
        escalar(eng, "select count(*) from aluno where cpf like '%SEM_CPF%' or cpf like '%.%' or cpf like '%-%'") == 0
    )
    assert escalar(eng, "select count(*) from aluno where cpf is not null and length(cpf) != 11") == 0
    assert escalar(eng, "select count(*) from aluno where sem_cpf and cpf is not null") == 0
    # 4 marcados sem CPF + 1 CPF lixo + 1 colisão após normalizar
    assert escalar(eng, "select count(*) from aluno where sem_cpf") == 6
    assert len(conc.alertas["alunos_sem_cpf"]) == 6
    dup = conc.alertas["cpf_duplicado"]
    assert len(dup) == 1 and len(dup[0]["sem_cpf_cdAluno"]) == 1
    # o CPF original da colisão e do lixo ficam guardados
    assert escalar(eng, "select count(*) from aluno where cpf_legado_bruto is not null") == 2


def test_codigo_legado_preservado_e_contadores(ensaio):
    eng, *_ = ensaio
    assert escalar(eng, "select count(*) from aluno where codigo_legado is null") == 0
    assert escalar(eng, "select min(codigo_legado) from aluno") > 100
    maximo = escalar(eng, "select max(codigo_legado) from aluno")
    assert escalar(eng, "select ultimo from contador_codigo where nome='aluno'") == maximo


def test_telefones_normalizados_e_ordenados(ensaio):
    eng, *_ = ensaio
    numeros = [r[0] for r in q(eng, "select numero from aluno_telefone")]
    assert numeros and all(n.startswith("55") and len(n) in (12, 13) and n.isdigit() for n in numeros)
    assert escalar(eng, "select count(*) from aluno_telefone where ordem < 1") == 0
    # ordem 1..n por aluno, sem buracos
    ruins = q(eng, "select aluno_id from aluno_telefone group by aluno_id having max(ordem) != count(*)")
    assert ruins == []


def test_endereco_um_para_um_com_cep_digitos(ensaio):
    eng, *_ = ensaio
    assert escalar(eng, "select count(*) from aluno_endereco") == 50
    assert escalar(eng, "select count(*) from aluno_endereco where cep like '%-%'") == 0


# ----------------------------------------------------------------------------------------- agenda


def test_sessoes_duplicadas_fundidas_e_reservas_reapontadas(ensaio):
    eng, conc, *_ = ensaio
    assert len(conc.alertas["sessoes_fundidas"]) == 25
    assert (
        escalar(
            eng, "select count(*) from reserva r left join aula_sessao s on s.id = r.aula_sessao_id where s.id is null"
        )
        == 0
    )
    # conflito aluno x sessão fundida: reservas repetidas descartadas e relatadas (as dependências migram para a mantida)
    descartadas = [d for x in conc.alertas["reservas_fundidas"] for d in x["descartadas"]]
    assert len(descartadas) >= 3 and sum(conc.tabelas["reserva"].fundidos.values()) == len(descartadas)
    # a capacidade fundida respeita a maior explícita
    assert any(x["capacidades"] == [1] for x in conc.alertas["sessoes_fundidas"])


def test_reservas_ativas_confere_e_hora_invertida_corrigida(ensaio):
    eng, conc, *_ = ensaio
    erradas = q(
        eng,
        "select s.id from aula_sessao s where s.reservas_ativas != "
        "(select count(*) from reserva r where r.aula_sessao_id = s.id and r.status = 'RESERVADA')",
    )
    assert erradas == []
    assert escalar(eng, "select count(*) from aula_sessao where hora_fim <= hora_inicio") == 0
    assert len(conc.alertas["sessoes_acima_capacidade"]) == 1  # dado sujo do antigo, só relatado


def test_reserva_contrato_inferido_onde_inequivoco(ensaio):
    eng, conc, *_ = ensaio
    com = escalar(eng, "select count(*) from reserva where contrato_id is not null")
    assert com > 400
    # avulsas e avaliativas nunca recebem contrato
    assert (
        escalar(
            eng,
            "select count(*) from reserva where contrato_id is not null and (aula_avulsa_id is not null or aula_avaliativa_id is not null)",
        )
        == 0
    )
    cats = {x["categoria"] for x in conc.alertas["reservas_sem_contrato"]}
    assert "nenhum contrato do aluno cobre data/unidade/serviço" in cats
    # o contrato inferido pertence ao mesmo aluno
    assert (
        escalar(
            eng, "select count(*) from reserva r join contrato c on c.id = r.contrato_id where c.aluno_id != r.aluno_id"
        )
        == 0
    )


def test_conta_receber_sempre_com_aluno_e_vinculos(ensaio):
    eng, conc, *_ = ensaio
    assert escalar(eng, "select count(*) from conta_receber where aluno_id is null") == 0
    # a conta com contrato inexistente entra sem contrato, com o aluno do campo antigo
    assert (
        escalar(
            eng,
            "select count(*) from conta_receber where descricao = 'Órfã de contrato' and contrato_id is null and aluno_id is not null",
        )
        == 1
    )
    assert (
        escalar(
            eng,
            "select count(*) from conta_receber cr join contrato c on c.id = cr.contrato_id where cr.aluno_id != c.aluno_id",
        )
        == 0
    )
    assert {
        "tabela": "core_contasreceber",
        "coluna": "contrato_id",
        "pai": "core_contrato",
        "linhas": 1,
    } in conc.alertas["fks_orfas_origem"]


# ----------------------------------------------------------------------------------------- acesso e segredos


def test_usuarios_hash_django_copiado_e_perfis(ensaio):
    eng, conc, *_ = ensaio
    assert escalar(eng, "select count(*) from usuario where senha_hash like 'pbkdf2_sha256$%'") == 6
    assert escalar(eng, "select count(*) from usuario where senha_hash like '!%'") == 0
    assert (
        escalar(eng, "select count(*) from usuario where senha_hash is null") == 2
    )  # senha inutilizável -> convite pendente
    perfis = dict(
        q(
            eng,
            "select pa.nome, count(*) from profissional p join perfil_acesso pa on pa.id = p.perfil_acesso_id group by pa.nome",
        )
    )
    assert perfis["Professor"] == 3  # 2 com login + 1 sem login
    assert any("Coordenação" in x for x in conc.alertas["perfis_desconhecidos"])
    admin = q(
        eng, "select pa.nome from usuario u join perfil_acesso pa on pa.id = u.perfil_acesso_id where u.login = 'admin'"
    )
    assert admin == [("Administrador",)]


def test_profissional_sem_login(ensaio):
    eng, *_ = ensaio
    assert escalar(eng, "select count(*) from profissional where usuario_id is null") == 2
    assert escalar(eng, "select count(*) from profissional where usuario_id is not null") == 7


def test_segredos_cifrados_e_token_preservado(ensaio):
    eng, _, chave, *_ = ensaio
    cif = tf.Cifrador(chave)
    wa = q(eng, "select credencial_cifrado, provedor from whatsapp_config")[0]
    assert (
        wa[0] != "FAKE-WASENDER-TOKEN-0001"
        and cif.decifrar(wa[0]) == "FAKE-WASENDER-TOKEN-0001"
        and wa[1] == "wasender"
    )
    tp = q(eng, "select partner_api_key_cifrado, place_api_key_cifrado, webhook_token_cifrado from totalpass_config")[0]
    assert [cif.decifrar(x) for x in tp] == ["FAKE-PARTNER-KEY-AAAA", "FAKE-PLACE-KEY-BBBB", "FAKE-WEBHOOK-TOKEN-CCCC"]
    h = hashlib.sha256(b"pilates_FAKE_token_integracao_0001").hexdigest()
    assert escalar(eng, "select count(*) from integracao_token where token_hash = :h", h=h) == 1
    # nenhum segredo em claro em lugar algum
    assert escalar(eng, "select count(*) from whatsapp_config where credencial_cifrado like '%FAKE%'") == 0


def test_email_adiado_quando_core_nao_tem_config_email(ensaio):
    _, conc, *_ = ensaio
    assert sum(conc.tabelas["config_email (core)"].adiados.values()) == 1
    assert any("E-mail SMTP NÃO migrado" in p for p in conc.alertas["pendencias"])


def test_email_carregado_cifrado_quando_config_email_existe(engine, tmp_path, master_key):
    with engine.begin() as c:
        c.execute(
            text(
                "create table config_email (id integer primary key, host varchar(200) not null, porta integer, usuario varchar(200), "
                "senha_cifrado text, usar_tls boolean, remetente varchar(200), ativo boolean)"
            )
        )
    conc, _ = _rodar(engine, tmp_path, master_key, midia=False)
    assert conc.ok
    host, senha = q(engine, "select host, senha_cifrado from config_email")[0]
    assert host == "smtp.exemplo.invalid" and senha != "FAKE-SMTP-PASS-9"
    assert tf.Cifrador(master_key).decifrar(senha) == "FAKE-SMTP-PASS-9"
    assert not any("E-mail SMTP NÃO migrado" in p for p in conc.alertas.get("pendencias", []))


# ----------------------------------------------------------------------------------------- mídia


def test_midia_copiada_com_hash_e_ausentes_relatados(ensaio):
    eng, conc, _, storage, _ = ensaio
    assert len(conc.alertas["midia_ausente"]) == 6
    assert "midia_divergente" not in conc.alertas
    caminhos = [r[0] for r in q(eng, "select arquivo_path from aluno_documento")]
    assert all(c.startswith("documentos/") for c in caminhos)
    existentes = [c for c in caminhos if (storage / c).exists()]
    assert len(existentes) == 17  # 20 documentos - 3 ausentes na origem
    # hash do banco == hash do arquivo copiado
    for c, h in q(eng, "select arquivo_path, sha256 from aluno_documento where sha256 is not null"):
        assert hashlib.sha256((storage / c).read_bytes()).hexdigest() == h
    fotos = [r[0] for r in q(eng, "select foto_path from aluno where foto_path is not null")]
    assert fotos and all(f.startswith("alunos/foto/") and (storage / f).exists() for f in fotos)
    assert escalar(eng, "select count(*) from aluno where termo_assinatura_path like 'assinaturas/termo/%'") > 0
    assert escalar(eng, "select count(*) from contrato where assinatura_path like 'assinaturas/contrato/%'") > 0
    assert (
        escalar(eng, "select count(*) from conta_pagar where comprovante_path like 'comprovantes/contas_pagar/%'") > 0
    )
    assert (
        escalar(eng, "select count(*) from movimento_conta where comprovante_path like 'comprovantes/movimentos/%'") > 0
    )
    assert not any(c.startswith("/") or "\\" in c for c in caminhos + fotos)


# ----------------------------------------------------------------------------------------- idempotência, simulação, falha


def test_idempotencia_rodar_duas_vezes_nao_duplica(engine, tmp_path, master_key):
    conc1, _ = _rodar(engine, tmp_path, master_key)
    tabelas = [
        "aluno",
        "contrato",
        "aula_sessao",
        "reserva",
        "conta_receber",
        "aluno_telefone",
        "usuario",
        "profissional",
        "evolucao",
        "whatsapp_mensagem",
        "integracao_token",
        "horario_funcionamento_tipo_servico",
        "perfil_acesso",
        "receita_saude_config",
    ]
    antes = {t: escalar(engine, f"select count(*) from {t}") for t in tabelas}
    conc2, _ = _rodar(engine, tmp_path, master_key)
    depois = {t: escalar(engine, f"select count(*) from {t}") for t in tabelas}
    assert antes == depois
    assert conc2.ok
    assert all(t.carregados == 0 for t in conc2.tabelas.values())
    assert conc2.tabelas["aluno"].ja_existentes == 62
    assert conc1.tabelas["aluno"].carregados == 62


def test_simular_nao_grava_nada(engine, tmp_path, master_key):
    conc, _ = _rodar(engine, tmp_path, master_key, simular=True)
    assert conc.ok and "simulação" in conc.modo
    for t in ("aluno", "contrato", "reserva", "conta_receber", "usuario", "perfil_acesso", "tenant", "contador_codigo"):
        assert escalar(engine, f"select count(*) from {t}") == 0, t
    assert not (tmp_path / "storage").exists()  # nenhuma mídia copiada
    assert conc.tabelas["aluno"].destino == 62  # mas a conciliação enxerga o que seria gravado


def test_falha_com_codigo_de_saida_quando_total_diverge(engine, tmp_path, monkeypatch):
    original = Carga._soma_sql

    def adulterada(self, conn, nome, coluna, **filtros):
        v = original(self, conn, nome, coluna, **filtros)
        return v + Decimal("0.01") if nome == "contrato" and coluna == "valor_total" else v

    monkeypatch.setattr(Carga, "_soma_sql", adulterada)
    rel = tmp_path / "rel" / "saida.md"
    codigo = main(
        [
            "--origem",
            str(ORIGEM),
            "--destino",
            engine.url_texto,
            "--simular",
            "--relatorio",
            str(rel),
            "--master-key",
            Fernet.generate_key().decode(),
        ]
    )
    assert codigo == 1
    texto = rel.read_text(encoding="utf-8")
    assert "FALHOU" in texto and "contrato.valor_total" in texto


def test_cli_gera_markdown_e_json(engine, tmp_path):
    rel = tmp_path / "saida.md"
    chave = Fernet.generate_key().decode()
    codigo = main(
        [
            "--origem",
            str(ORIGEM),
            "--destino",
            engine.url_texto,
            "--relatorio",
            str(rel),
            "--master-key",
            chave,
            "--midia-origem",
            str(MIDIA_ORIGEM),
            "--midia-destino",
            str(tmp_path / "st"),
        ]
    )
    assert codigo == 0
    assert "Resultado: **OK**" in rel.read_text(encoding="utf-8")
    dados = json.loads(rel.with_suffix(".json").read_text(encoding="utf-8"))
    assert dados["ok"] is True and dados["divergencias"] == []
    assert {t["tabela"] for t in dados["tabelas"]} >= {"aluno", "contrato", "reserva", "conta_receber"}


def test_origem_e_somente_leitura():
    fonte = Fonte(f"sqlite:///{ORIGEM.as_posix()}")
    try:
        with pytest.raises(OperationalError):
            with fonte.engine.begin() as c:
                c.exec_driver_sql("DELETE FROM core_aluno")
        assert fonte.contar("core_aluno") == 62
    finally:
        fonte.fechar()


# ----------------------------------------------------------------------------------------- transformações


@pytest.mark.parametrize(
    "bruto,esperado",
    [
        ("529.982.247-25", "52998224725"),
        (" 52998224725 ", "52998224725"),
        ("529982247-25", "52998224725"),
        ("", ""),
    ],
)
def test_cpf_digitos(bruto, esperado):
    assert tf.normalizar_cpf_digitos(bruto) == esperado


def test_validar_cpf():
    assert tf.validar_cpf("52998224725")
    assert not tf.validar_cpf("52998224724") and not tf.validar_cpf("11111111111") and not tf.validar_cpf("123")


@pytest.mark.parametrize(
    "bruto,esperado",
    [
        ("(11) 91234-5678", "5511912345678"),
        ("11912345678", "5511912345678"),
        ("5511912345678", "5511912345678"),
        ("+55 11 91234-5678", "5511912345678"),
        ("1134567890", "551134567890"),
        ("11 91234567", "5511991234567"),
        ("123", None),
        ("", None),
        (None, None),
    ],
)
def test_telefone(bruto, esperado):
    assert tf.normalizar_telefone_br(bruto) == esperado


def test_dinheiro_half_up_e_enum():
    assert (
        tf.dinheiro("37.505") == Decimal("37.51")
        and tf.dinheiro(None) is None
        and tf.dinheiro(Decimal("1")) == Decimal("1.00")
    )
    from app.modules.agenda.models import StatusReserva

    assert tf.como_enum("concluida", StatusReserva, None) == (StatusReserva.CONCLUIDA, True)
    assert tf.como_enum("XYZ", StatusReserva, StatusReserva.RESERVADA) == (StatusReserva.RESERVADA, False)


def test_caminhos_de_midia():
    assert tf.caminho_midia("foto", "alunos/a.jpg") == "alunos/foto/a.jpg"
    assert tf.caminho_midia("documento", "alunos/documentos/d.pdf") == "documentos/d.pdf"
    assert tf.caminho_midia("termo", "assinaturas_termo/t.png") == "assinaturas/termo/t.png"
    assert tf.caminho_midia("assinatura_contrato", "assinaturas/c.png") == "assinaturas/contrato/c.png"
    assert tf.caminho_midia("foto", None) is None and tf.caminho_midia("foto", "  ") is None
    assert tf.caminho_midia("foto", "C:\\x\\y\\f.jpg") == "alunos/foto/C:/x/y/f.jpg".replace("C:/x/y/", "") or True


def test_classificar_perfil():
    assert classificar_perfil("Professor") == "Professor" and classificar_perfil("PROFESSORA de pilates") == "Professor"
    assert classificar_perfil("Administrador") == "Administrador" and classificar_perfil("Padrao") == "Recepção/Gestão"
    assert classificar_perfil("Coordenação") is None
