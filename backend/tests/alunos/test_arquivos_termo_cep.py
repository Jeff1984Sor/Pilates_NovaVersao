import pytest
from sqlalchemy import select

from app.core import storage
from app.core.models import Auditoria
from app.modules.alunos import servico
from app.modules.alunos.models import Aluno, AlunoDocumento, OrigemDocumento
from tests.alunos.conftest import PDF, data_url_png, png_bytes


def acoes(db):
    return [a.acao for a in db.scalars(select(Auditoria).order_by(Auditoria.id))]


# ----------------------------------------------------------------------------------------------------- foto
def test_foto_upload_download_troca_e_remocao(client, h, criar, db):
    a = criar()
    assert a["foto_url"] is None
    r = client.post(f"/api/alunos/{a['id']}/foto", headers=h, files={"arquivo": ("eu.png", png_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["foto_url"]
    assert url.startswith(f"/alunos/{a['id']}/foto?v=")
    rel = db.get(Aluno, a["id"]).foto_path
    assert rel.startswith("alunos/foto/") and not rel.startswith("/")  # caminho relativo no banco
    g = client.get(f"/api/alunos/{a['id']}/foto", headers=h)
    assert g.status_code == 200 and g.content == png_bytes()
    # trocar por JPG remove o arquivo anterior
    client.post(f"/api/alunos/{a['id']}/foto", headers=h, files={"arquivo": ("eu.jpg", b"\xff\xd8\xff\xe0" + b"0" * 50, "image/jpeg")})
    db.expire_all()
    assert not storage.existe(rel) and storage.existe(db.get(Aluno, a["id"]).foto_path)
    assert client.delete(f"/api/alunos/{a['id']}/foto", headers=h).json()["foto_url"] is None
    assert client.get(f"/api/alunos/{a['id']}/foto", headers=h).status_code == 404
    assert acoes(db).count("aluno.foto") == 3


def test_foto_recusa_conteudo_falso_e_extensao(client, h, criar):
    a = criar()
    assert client.post(f"/api/alunos/{a['id']}/foto", headers=h, files={"arquivo": ("x.png", b"nao sou imagem", "image/png")}).status_code == 400
    assert client.post(f"/api/alunos/{a['id']}/foto", headers=h, files={"arquivo": ("x.svg", b"<svg/>", "image/svg+xml")}).status_code == 400
    assert client.post(f"/api/alunos/{a['id']}/foto", headers=h, files={"arquivo": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024), "image/png")}).status_code == 400


def test_foto_exige_login(client, criar):
    a = criar()
    assert client.get(f"/api/alunos/{a['id']}/foto").status_code == 401


# ------------------------------------------------------------------------------------------- documentos
def enviar(client, h, aluno_id, titulo="Atestado", nome="atestado.pdf", conteudo=PDF, descricao="obs"):
    return client.post(f"/api/alunos/{aluno_id}/documentos", headers=h, data={"titulo": titulo, "descricao": descricao},
                       files={"arquivo": (nome, conteudo, "application/pdf")})


def test_documento_upload_lista_baixa_e_exclui(client, h, criar, db):
    a = criar()
    r = enviar(client, h, a["id"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["titulo"] == "Atestado" and d["origem"] == "UPLOAD" and d["pode_excluir"] and d["tamanho"] == len(PDF)
    reg = db.get(AlunoDocumento, d["id"])
    assert reg.arquivo_path.startswith(f"documentos/{a['id']}/") and len(reg.sha256) == 64
    assert [x["id"] for x in client.get(f"/api/alunos/{a['id']}/documentos", headers=h).json()] == [d["id"]]
    dl = client.get(f"/api/alunos/{a['id']}/documentos/{d['id']}/arquivo", headers=h)
    assert dl.status_code == 200 and dl.content == PDF and "Atestado.pdf" in dl.headers["content-disposition"]
    arquivo = reg.arquivo_path
    assert client.delete(f"/api/alunos/{a['id']}/documentos/{d['id']}", headers=h).status_code == 200
    assert not storage.existe(arquivo) and client.get(f"/api/alunos/{a['id']}/documentos", headers=h).json() == []
    assert {"aluno.documento.enviar", "aluno.documento.baixar", "aluno.documento.excluir"} <= set(acoes(db))


def test_documento_validacoes(client, h, criar):
    a = criar()
    assert enviar(client, h, a["id"], titulo="  ").status_code == 422
    assert enviar(client, h, a["id"], nome="virus.exe", conteudo=b"MZ").status_code == 400
    assert enviar(client, h, a["id"], nome="falso.pdf", conteudo=b"texto").status_code == 400
    assert enviar(client, h, a["id"], conteudo=b"").status_code == 400
    assert enviar(client, h, a["id"], conteudo=PDF + b"0" * (11 * 1024 * 1024)).status_code == 400


def test_documento_nao_vaza_entre_alunos(client, h, criar):
    a = criar()
    b = criar(nome="Joana", cpf="111.444.777-35")
    d = enviar(client, h, a["id"]).json()
    assert client.get(f"/api/alunos/{b['id']}/documentos/{d['id']}/arquivo", headers=h).status_code == 404
    assert client.delete(f"/api/alunos/{b['id']}/documentos/{d['id']}", headers=h).status_code == 404


def test_documento_de_contrato_nao_pode_ser_excluido(client, h, criar, db):
    a = criar()
    rel = storage.salvar("documentos", "contrato.pdf", PDF, subpasta=str(a["id"]))
    doc = AlunoDocumento(aluno_id=a["id"], titulo="Contrato", arquivo_path=rel, origem=OrigemDocumento.CONTRATO_PDF)
    db.add(doc)
    db.commit()
    lista = client.get(f"/api/alunos/{a['id']}/documentos", headers=h).json()
    assert lista[0]["origem"] == "CONTRATO_PDF" and not lista[0]["pode_excluir"]
    assert client.delete(f"/api/alunos/{a['id']}/documentos/{doc.id}", headers=h).status_code == 409


def test_arquivo_do_documento_ausente_no_disco(client, h, criar, db):
    a = criar()
    d = enviar(client, h, a["id"]).json()
    storage.remover(db.get(AlunoDocumento, d["id"]).arquivo_path)
    assert client.get(f"/api/alunos/{a['id']}/documentos/{d['id']}/arquivo", headers=h).status_code == 404


def test_excluir_aluno_remove_arquivos(client, h, criar, db):
    a = criar()
    client.post(f"/api/alunos/{a['id']}/foto", headers=h, files={"arquivo": ("eu.png", png_bytes(), "image/png")})
    d = enviar(client, h, a["id"]).json()
    arquivos = [db.get(Aluno, a["id"]).foto_path, db.get(AlunoDocumento, d["id"]).arquivo_path]
    assert client.delete(f"/api/alunos/{a['id']}", headers=h).status_code == 200
    assert not any(storage.existe(x) for x in arquivos)


def test_autorizacao_de_documentos_e_foto_por_perfil(client, db, h, criar, base):
    from tests.conftest import auth, criar_usuario, entrar

    a = criar()
    d = enviar(client, h, a["id"]).json()
    criar_usuario(db, "Secretária", email="sec@exemplo.com")
    hs = auth(entrar(client, "sec@exemplo.com").json()["access_token"])
    assert client.get(f"/api/alunos/{a['id']}/documentos", headers=hs).status_code == 200  # ver
    assert enviar(client, hs, a["id"], titulo="Outro").status_code == 201  # editar
    assert client.delete(f"/api/alunos/{a['id']}/documentos/{d['id']}", headers=hs).status_code == 200  # excluir doc = editar
    assert client.delete(f"/api/alunos/{a['id']}", headers=hs).status_code == 403  # excluir aluno exige alunos.excluir
    # Professor padrão não tem nenhum acesso aos documentos
    criar_usuario(db, "Professor", email="prof@exemplo.com")
    hp = auth(entrar(client, "prof@exemplo.com").json()["access_token"])
    assert client.get(f"/api/alunos/{a['id']}/documentos", headers=hp).status_code == 403
    assert enviar(client, hp, a["id"]).status_code == 403
    assert client.get(f"/api/alunos/{a['id']}/documentos/{d['id']}/arquivo", headers=hp).status_code == 403
    # a rota genérica do storage também respeita a permissão da categoria
    rel = db.query(AlunoDocumento).first().arquivo_path
    assert client.get(f"/api/arquivos/{rel}", headers=hp).status_code == 403
    assert client.get(f"/api/arquivos/{rel}", headers=hs).status_code == 200
    assert client.get(f"/api/alunos/{a['id']}/documentos").status_code == 401


# ------------------------------------------------------------------------------------------------ termo
def test_estado_inicial_do_termo(client, h, criar, base):
    a = criar(nome="Maria Teste", telefones=[{"numero": "11988887777"}])
    t = client.get(f"/api/alunos/{a['id']}/termo", headers=h).json()
    assert not t["assinado"] and not t["autoriza_imagem"] and t["termo"]["nome"] == "Termo de imagem"
    assert [x["id"] for x in t["termos_disponiveis"]] == [base["termo_id"]]
    assert "Maria Teste" in t["texto_html"] and "529.982.247-25" in t["texto_html"]
    assert t["link_assinatura_disponivel"] is False


def test_termo_escapa_dados_do_aluno(client, h, criar):
    a = criar(nome="<img src=x onerror=alert(1)>")
    assert "<img" not in client.get(f"/api/alunos/{a['id']}/termo", headers=h).json()["texto_html"]


def test_registrar_termo_sem_assinatura(client, h, criar, base, db):
    a = criar()
    t = client.post(f"/api/alunos/{a['id']}/termo/registrar", headers=h, json={"termo_id": base["termo_id"]}).json()
    assert t["autoriza_imagem"] and t["aceite_em"] and not t["assinado"]
    assert client.post(f"/api/alunos/{a['id']}/termo/registrar", headers=h, json={"termo_id": 999}).status_code == 422
    assert "aluno.termo.registrar" in acoes(db)


def test_assinatura_local_grava_imagem_nome_documento_e_ip(client, h, criar, base, db):
    a = criar()
    r = client.post(f"/api/alunos/{a['id']}/termo/assinatura-local", headers=h,
                    json={"nome": "Maria Teste", "documento": "529.982.247-25", "assinatura": data_url_png()})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["assinado"] and t["autoriza_imagem"] and t["assinatura_nome"] == "Maria Teste" and t["assinatura_ip"]
    assert t["assinatura_url"].startswith(f"/alunos/{a['id']}/termo/assinatura")
    img = client.get(f"/api/alunos/{a['id']}/termo/assinatura", headers=h)
    assert img.status_code == 200 and img.content == png_bytes()
    reg = db.get(Aluno, a["id"])
    assert reg.termo_assinatura_path.startswith("alunos/termo/") and reg.termo_uso_id == base["termo_id"] and reg.autoriza_imagem
    assert "aluno.termo.assinar" in acoes(db)
    # assinar de novo substitui a imagem
    assert client.post(f"/api/alunos/{a['id']}/termo/assinatura-local", headers=h,
                       json={"nome": "Maria T.", "assinatura": data_url_png()}).json()["assinatura_nome"] == "Maria T."


@pytest.mark.parametrize("assinatura", ["data:image/jpeg;base64,AAAA", "nada", "data:image/png;base64,bm90IHBuZyBhdCBhbGwgbm90IHBuZyBhdCBhbGw="])
def test_assinatura_invalida(client, h, criar, assinatura):
    a = criar()
    r = client.post(f"/api/alunos/{a['id']}/termo/assinatura-local", headers=h, json={"nome": "Maria", "assinatura": assinatura})
    assert r.status_code == 422, r.text


def test_assinatura_sem_termo_cadastrado(client, h, criar, db):
    from app.modules.cadastros.models import TermoUso

    a = criar()
    db.query(TermoUso).delete()
    db.commit()
    assert client.post(f"/api/alunos/{a['id']}/termo/assinatura-local", headers=h,
                       json={"nome": "Maria", "assinatura": data_url_png()}).status_code == 409


# ------------------------------------------------------------------------------------------------- CEP
@pytest.fixture(autouse=True)
def _cep_limpo():
    servico.limpar_cache_cep()
    yield
    servico.limpar_cache_cep()


@pytest.fixture
def viacep(monkeypatch):
    """ViaCEP simulado: os testes nunca vão à internet."""
    chamadas = []
    respostas = {"01310100": {"cep": "01310-100", "logradouro": "Avenida Paulista", "complemento": "de 612 a 1510 - lado par",
                              "bairro": "Bela Vista", "localidade": "São Paulo", "uf": "SP"}}

    def falso(cep):
        chamadas.append(cep)
        if cep == "99999999":
            raise servico.CepIndisponivel()
        return respostas.get(cep)

    monkeypatch.setattr(servico, "consultar_viacep", falso)
    return chamadas


def test_cep_encontrado_com_cache(client, h, viacep):
    r = client.get("/api/alunos/cep/01310-100", headers=h)
    assert r.status_code == 200
    assert r.json() == {"cep": "01310100", "logradouro": "Avenida Paulista", "complemento": "de 612 a 1510 - lado par",
                        "bairro": "Bela Vista", "cidade": "São Paulo", "uf": "SP"}
    client.get("/api/alunos/cep/01310100", headers=h)
    assert viacep == ["01310100"]  # a segunda consulta saiu do cache


def test_cep_inexistente_invalido_e_servico_fora(client, h, viacep):
    r = client.get("/api/alunos/cep/12345678", headers=h)
    assert r.status_code == 404 and "manualmente" in r.json()["detail"]
    client.get("/api/alunos/cep/12345678", headers=h)
    assert viacep.count("12345678") == 1  # "não achado" também fica em cache curto
    assert client.get("/api/alunos/cep/123", headers=h).status_code == 422
    r = client.get("/api/alunos/cep/99999999", headers=h)
    assert r.status_code == 502 and "Preencha o endereço manualmente" in r.json()["detail"]


def test_cep_exige_login_e_permissao(client, db, viacep):
    from tests.conftest import auth, criar_usuario, entrar

    assert client.get("/api/alunos/cep/01310100").status_code == 401
    criar_usuario(db, "Professor", email="prof@exemplo.com")
    hp = auth(entrar(client, "prof@exemplo.com").json()["access_token"])
    assert client.get("/api/alunos/cep/01310100", headers=hp).status_code == 403


def test_viacep_real_trata_falha_de_rede(monkeypatch):
    import httpx

    def quebra(*a, **k):
        raise httpx.ConnectTimeout("sem rede")

    monkeypatch.setattr(httpx, "get", quebra)
    with pytest.raises(servico.CepIndisponivel):
        servico.consultar_viacep("01310100")
