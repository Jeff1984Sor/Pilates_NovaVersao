import pytest
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core import escopo, perfis
from app.core.deps import Ctx, get_contexto
from app.core.models import PerfilAcesso
from app.core.permissoes import PERFIS_PADRAO, TODAS, normalizar, permissao_da_rota
from tests.conftest import auth, criar_usuario, entrar


def _token(client, db, perfil, email):
    criar_usuario(db, perfil, email=email)
    return entrar(client, email).json()["access_token"]


def test_catalogo_cobre_as_areas_planejadas():
    recursos = {p.split(".")[0] for p in TODAS}
    esperados = {"alunos", "agenda", "aulas", "contratos", "planos", "financeiro_receber", "financeiro_pagar", "financeiro_caixa",
                 "financeiro_dre", "financeiro_bancos", "receita_saude", "comissoes", "cadastros_unidades", "cadastros_servicos",
                 "cadastros_profissionais", "cadastros_fornecedores", "cadastros_categorias", "cadastros_horarios",
                 "cadastros_bloqueios", "cadastros_termos", "cadastros_modelos", "whatsapp", "comunicacao", "integracoes",
                 "configuracoes", "usuarios", "perfis", "auditoria"}
    assert esperados <= recursos
    assert {"aulas.operar", "aulas.evoluir"} <= TODAS


def test_perfis_padrao_existem_e_so_tem_permissoes_conhecidas():
    nomes = [p["nome"] for p in PERFIS_PADRAO]
    assert nomes == ["Administrador", "Gestão/Recepção", "Financeiro", "Professor", "Somente leitura"]
    for p in PERFIS_PADRAO:
        assert set(p["permissoes"]) <= TODAS, p["nome"]
    adm = PERFIS_PADRAO[0]
    assert adm["administrador"] and adm["sistema"]


def test_perfil_professor_so_agenda_evolucao_e_avaliacao():
    prof = next(p for p in PERFIS_PADRAO if p["nome"] == "Professor")
    assert set(prof["permissoes"]) == {"painel.ver", "agenda.ver", "aulas.ver", "aulas.evoluir", "aulas.avaliar"}
    assert prof["somente_proprias_aulas"]
    for proibida in ("financeiro_receber.ver", "contratos.ver", "alunos.editar", "configuracoes.ver", "aulas.operar"):
        assert proibida not in prof["permissoes"]


def test_somente_leitura_nao_altera_nada_nem_ve_administracao():
    p = next(p for p in PERFIS_PADRAO if p["nome"] == "Somente leitura")
    assert all(x.endswith(".ver") for x in p["permissoes"])
    assert "usuarios.ver" not in p["permissoes"] and "auditoria.ver" not in p["permissoes"]


def test_gestao_nao_administra_nem_ve_financeiro_pesado():
    p = next(p for p in PERFIS_PADRAO if p["nome"] == "Gestão/Recepção")["permissoes"]
    assert "alunos.editar" in p and "agenda.editar" in p and "aulas.operar" in p
    assert "usuarios.editar" not in p and "perfis.editar" not in p and "financeiro_dre.ver" not in p


def test_rota_nao_mapeada_e_negada_por_padrao():
    assert permissao_da_rota("GET", "/api/rota/que/ninguem/mapeou") == (False, None)


def test_mapa_por_metodo():
    assert permissao_da_rota("GET", "/api/alunos") == (True, "alunos.ver")
    assert permissao_da_rota("POST", "/api/alunos") == (True, "alunos.editar")
    assert permissao_da_rota("DELETE", "/api/alunos/3") == (True, "alunos.excluir")
    assert permissao_da_rota("POST", "/api/aulas/9/evolucao") == (True, "aulas.evoluir")
    assert permissao_da_rota("POST", "/api/aulas/9/chegou") == (True, "aulas.operar")
    assert permissao_da_rota("GET", "/api/cadastros/unidades-x") == (False, None)  # fronteira de segmento
    assert permissao_da_rota("GET", "/api/auth/me") == (True, None)


def test_normalizar_descarta_desconhecidas_e_inclui_ver():
    assert normalizar(["alunos.editar", "coisa.inventada"]) == ["alunos.editar", "alunos.ver"]


def test_rota_sem_mapa_responde_403_mesmo_para_admin(client, db, token_admin):
    from app.main import app

    antes = list(app.router.routes)
    r = APIRouter()

    @r.get("/rota-orfa")
    def orfa(ctx: Ctx):
        return {"ok": True}

    app.include_router(r, prefix="/api", dependencies=[Depends(get_contexto)])
    try:
        assert client.get("/api/rota-orfa", headers=auth(token_admin)).status_code == 403
    finally:
        app.router.routes[:] = antes


def test_professor_e_barrado_fora_da_agenda(client, db):
    t = _token(client, db, "Professor", "prof@exemplo.com")
    h = auth(t)
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.get("/api/config/usuarios", headers=h).status_code == 403
    assert client.get("/api/config/perfis", headers=h).status_code == 403
    assert client.get("/api/auditoria", headers=h).status_code == 403
    assert client.get("/api/config/email", headers=h).status_code == 403
    assert client.put("/api/config/identidade", headers=h, json={"nome_exibicao": "Invasor"}).status_code == 403
    # identidade (só leitura) é livre para qualquer logado
    assert client.get("/api/config/identidade", headers=h).status_code == 200


def test_admin_acessa_administracao(client, db, token_admin):
    h = auth(token_admin)
    assert client.get("/api/config/usuarios", headers=h).status_code == 200
    assert client.get("/api/config/perfis", headers=h).status_code == 200
    assert client.get("/api/auditoria", headers=h).status_code == 200


def test_perfil_customizado_vale_na_hora(client, db, token_admin):
    h = auth(token_admin)
    r = client.post("/api/config/perfis", headers=h, json={"nome": "Só auditoria", "permissoes": ["auditoria.ver"]})
    assert r.status_code == 201
    pid = r.json()["id"]
    criar_usuario(db, "Somente leitura", email="aud@exemplo.com")
    uid = criar_usuario(db, "Somente leitura", email="aud2@exemplo.com").id
    client.patch(f"/api/config/usuarios/{uid}", headers=h, json={"perfil_acesso_id": pid})
    t = entrar(client, "aud2@exemplo.com").json()["access_token"]
    assert client.get("/api/auditoria", headers=auth(t)).status_code == 200
    assert client.get("/api/config/usuarios", headers=auth(t)).status_code == 403


def test_administrador_padrao_nao_exclui_nem_perde_acesso_total(client, db, token_admin):
    h = auth(token_admin)
    perfis_ = client.get("/api/config/perfis", headers=h).json()
    adm = next(p for p in perfis_ if p["nome"] == "Administrador")
    assert client.delete(f"/api/config/perfis/{adm['id']}", headers=h).status_code == 400
    r = client.put(f"/api/config/perfis/{adm['id']}", headers=h, json={"nome": "Administrador", "administrador": False})
    assert r.status_code == 400


def test_nao_deixa_o_sistema_sem_administrador(client, db, admin, token_admin):
    h = auth(token_admin)
    assert client.delete(f"/api/config/usuarios/{admin.id}", headers=h).status_code == 400  # a si mesmo
    outro = criar_usuario(db, "Administrador", email="adm2@exemplo.com")
    assert client.delete(f"/api/config/usuarios/{outro.id}", headers=h).status_code == 200


def test_catalogo_e_perfil_sem_perfil_de_acesso_nao_tem_permissao(client, db):
    u = criar_usuario(db, "Professor", email="x@exemplo.com")
    u.perfil_acesso_id = None
    db.commit()
    assert u.permissoes == set() and not u.pode("agenda.ver")


# ---------------------------------------------------------------------------------------------- escopo "próprias aulas"
class _AulaFalsa:
    """Stub: tabela de aulas em memória com a coluna profissional_id."""

    def __init__(self, id, profissional_id):
        self.id, self.profissional_id = id, profissional_id


AULAS = [_AulaFalsa(1, 10), _AulaFalsa(2, 11), _AulaFalsa(3, 10)]


class _CtxFalso:
    """Reproduz o contrato do Contexto sem precisar de request."""

    def __init__(self, db, usuario):
        self.db, self.usuario = db, usuario

    somente_proprias_aulas = lambda self: escopo.usuario_restrito(self.usuario)  # noqa: E731
    profissional_id = lambda self: escopo.resolver_profissional_id(self.db, self.usuario)  # noqa: E731


@pytest.fixture
def resolvedor_stub():
    anterior = escopo._resolvedor
    escopo.registrar_resolvedor_profissional(lambda db, u: {"prof@exemplo.com": 10}.get(u.email))
    yield
    escopo.registrar_resolvedor_profissional(anterior)


def _visiveis(ctx):
    pid = ctx.profissional_id()
    return [a.id for a in AULAS if not ctx.somente_proprias_aulas() or (pid is not None and a.profissional_id == pid)]


def test_escopo_professor_ve_so_as_proprias_aulas(db, resolvedor_stub):
    prof = criar_usuario(db, "Professor", email="prof@exemplo.com")
    assert escopo.usuario_restrito(prof)
    ctx = _CtxFalso(db, prof)
    assert _visiveis(ctx) == [1, 3]
    assert escopo.pode_acessar_profissional(ctx, 10)
    assert not escopo.pode_acessar_profissional(ctx, 11)


def test_escopo_professor_sem_vinculo_nao_ve_nada(db, resolvedor_stub):
    outro = criar_usuario(db, "Professor", email="outro@exemplo.com")
    ctx = _CtxFalso(db, outro)
    assert _visiveis(ctx) == []
    assert not escopo.pode_acessar_profissional(ctx, None)


def test_escopo_sem_resolvedor_registrado_nega(db):
    prof = criar_usuario(db, "Professor", email="prof@exemplo.com")
    assert escopo.resolver_profissional_id(db, prof) is None


def test_escopo_nao_restringe_quem_nao_e_professor(db, resolvedor_stub):
    adm = criar_usuario(db, "Administrador", email="a@exemplo.com")
    ges = criar_usuario(db, "Gestão/Recepção", email="g@exemplo.com")
    for u in (adm, ges):
        ctx = _CtxFalso(db, u)
        assert not ctx.somente_proprias_aulas()
        assert _visiveis(ctx) == [1, 2, 3]


def test_escopo_filtrar_proprias_em_consulta_sql(db, resolvedor_stub):
    from sqlalchemy import Column, Integer, MetaData, Table, insert

    t = Table("aula_stub", MetaData(), Column("id", Integer, primary_key=True), Column("profissional_id", Integer))
    t.create(db.get_bind())
    db.execute(insert(t), [{"id": 1, "profissional_id": 10}, {"id": 2, "profissional_id": 11}, {"id": 3, "profissional_id": 10}])
    prof = criar_usuario(db, "Professor", email="prof@exemplo.com")
    outro = criar_usuario(db, "Professor", email="outro@exemplo.com")
    adm = criar_usuario(db, "Administrador", email="a@exemplo.com")

    def ids(u):
        q = escopo.filtrar_proprias(_CtxFalso(db, u), select(t.c.id), t.c.profissional_id)
        return sorted(db.scalars(q))

    assert ids(prof) == [1, 3] and ids(outro) == [] and ids(adm) == [1, 2, 3]
    t.drop(db.get_bind())


def test_contexto_real_expoe_o_escopo(client, db, token_admin):
    from app.core.deps import Contexto

    prof = criar_usuario(db, "Professor", email="prof@exemplo.com")
    ctx = Contexto(db=db, usuario=prof, ip=None)
    assert ctx.somente_proprias_aulas() is True and ctx.profissional_id() is None
    assert perfis.garantir_padrao(db)["Professor"].somente_proprias_aulas
    assert isinstance(db.scalar(select(PerfilAcesso).limit(1)), PerfilAcesso)
