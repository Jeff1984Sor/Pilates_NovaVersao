"""Carga do banco antigo (Django) no esquema novo.

Regras de funcionamento
- Ordem de carga respeita as FKs; cada etapa roda numa transação própria (em `--simular`, todas as etapas rodam
  numa única transação que é desfeita no fim: nada é gravado, mas as constraints do destino são exercitadas).
- Idempotente: a chave de cada registro é `codigo_legado` (o `cdXxx` antigo; nas tabelas sem código, o `id` antigo).
  Rodar de novo só insere o que ainda não existe.
- Nada é perdido em silêncio: tudo que é descartado, fundido, adiado ou ajustado entra no relatório com o motivo.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, event, func, insert, inspect, select, update
from sqlalchemy.engine import Connection, Engine, make_url

from app.core.db import Base
from app.etl import transformacoes as tf
from app.etl.conciliacao import Conciliacao, LinhaTabela, Soma
from app.etl.fonte import Fonte
from app.etl.midia import Midia
from app.modules import registrar_modelos
from app.modules.agenda.models import StatusAvaliativa, StatusReserva, TipoAvaliativa
from app.modules.alunos.models import DirecaoMensagem, EstadoCivil, OrigemDocumento, StatusAluno
from app.modules.cadastros.models import Recorrencia, TipoCategoria
from app.modules.contratos.models import FormaPagamento, StatusAssinatura
from app.modules.financeiro.models import RecorrenciaPagar, StatusPagar, StatusReceber, TipoMovimento
from app.modules.integracoes.models import ProvedorWhatsapp

PERFIS_NOVOS = ["Administrador", "Recepção/Gestão", "Financeiro", "Professor", "Somente leitura"]
PERFIL_PADRAO_DESCONHECIDO = "Recepção/Gestão"
RANK_STATUS_RESERVA = {
    "CONCLUIDA": 5,
    "FALTOU_SEM_AVISAR": 4,
    "FALTOU_AVISOU": 4,
    "RESERVADA": 3,
    "PENDENTE": 2,
    "CANCELADA": 1,
}


class Descartar(Exception):
    """Registro que não pode ser migrado (com o motivo, que vai para o relatório)."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _sem_acento(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower().strip()


def classificar_perfil(nome: str) -> str | None:
    """Perfil antigo -> perfil do catálogo novo (por nome). None = desconhecido."""
    n = _sem_acento(nome or "")
    if "professor" in n:  # a regra antiga: "perfil contém 'professor'"
        return "Professor"
    if "admin" in n:
        return "Administrador"
    if "financ" in n:
        return "Financeiro"
    if any(p in n for p in ("recep", "gest", "padrao", "secret")):
        return "Recepção/Gestão"
    if any(p in n for p in ("leitura", "visualiz", "consulta")):
        return "Somente leitura"
    return None


class Carga:
    def __init__(
        self,
        fonte: Fonte,
        destino_url: str,
        *,
        master_key: str,
        simular: bool = False,
        midia_origem: Path | None = None,
        midia_destino: Path | None = None,
        semente_amostra: int = 20261025,
        tamanho_amostra: int = 20,
        criar_esquema: bool = False,
    ):
        registrar_modelos()
        self.fonte = fonte
        self.simular = simular
        self.cif = tf.Cifrador(master_key)
        self.midia = Midia(midia_origem, midia_destino, simular)
        self.conc = Conciliacao(
            modo="simulação (nada gravado)" if simular else "gravação",
            origem=self._mascarar(fonte.rotulo),
            destino=self._mascarar(destino_url),
        )
        self.semente_amostra = semente_amostra
        self.tamanho_amostra = tamanho_amostra
        self.engine = self._criar_engine(destino_url)
        if criar_esquema:
            Base.metadata.create_all(self.engine)
        self.mapas: dict[str, dict[int, int]] = defaultdict(dict)
        self.ok_src: dict[str, list[dict]] = {}
        self.amostras: list[tuple[str, str, Any, dict, Callable]] = []
        self._silencioso = False
        self._linha: LinhaTabela | None = None
        self._conn: Connection | None = None
        self._conn_unica: Connection | None = None
        self._core: dict[str, Table | None] = {}
        self._tenant: int | None = None
        self._agora = datetime.now(UTC)
        for nome in (
            "tenant",
            "usuario",
            "perfil_acesso",
            "config_email",
        ):  # tabelas do core: lidas do banco de destino
            self._core[nome] = self._refletir(nome)

    # ================================================================================== infraestrutura
    @staticmethod
    def _mascarar(url: str) -> str:
        u = make_url(url)
        return u.render_as_string(hide_password=True)

    @staticmethod
    def _criar_engine(url: str) -> Engine:
        eng = create_engine(url)
        if eng.dialect.name == "sqlite":

            @event.listens_for(eng, "connect")
            def _pragmas(conn, _):  # noqa: ANN001
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        return eng

    def _refletir(self, nome: str) -> Table | None:
        if not inspect(self.engine).has_table(nome):
            return None
        return Table(nome, MetaData(), autoload_with=self.engine)

    @staticmethod
    def T(nome: str) -> Table:
        return Base.metadata.tables[nome]

    @contextmanager
    def _etapa(self, nome: str):
        self.conc.etapas.append(nome)
        if self.simular:
            self._conn = self._conn_unica
            yield self._conn
        else:
            with self.engine.begin() as conn:
                self._conn = conn
                yield conn

    def _nota(self, tipo: str, motivo: str, ref: Any = None) -> None:
        if self._silencioso or self._linha is None:
            return
        getattr(self._linha, tipo)(motivo, ref)

    def _ts(self, r: dict, campo: str | None = "dtCadastro") -> dict:
        x = tf.como_instante(r.get(campo)) if campo else None
        x = x or self._agora
        return {"criado_em": x, "atualizado_em": x}

    def _fk(self, tabela_origem: str, old_id: Any, *, obrigatorio: bool, motivo: str = "") -> int | None:
        if old_id is None:
            if obrigatorio:
                raise Descartar(motivo or f"{tabela_origem}: vínculo obrigatório ausente")
            return None
        novo = self.mapas[tabela_origem].get(old_id)
        if novo is None:
            if obrigatorio:
                raise Descartar(motivo or f"{tabela_origem} #{old_id} inexistente ou não migrado (FK órfã)")
            self._nota("corrigir", f"FK órfã para {tabela_origem} zerada (vínculo opcional)", old_id)
        return novo

    def _existentes(self, conn: Connection, tabela: Table) -> dict[int, int]:
        rows = conn.execute(select(tabela.c.codigo_legado, tabela.c.id).where(tabela.c.codigo_legado.is_not(None)))
        return {c: i for c, i in rows}

    def _contar_migrados(self, conn: Connection, tabela: Table) -> int:
        return conn.execute(
            select(func.count()).select_from(tabela).where(tabela.c.codigo_legado.is_not(None))
        ).scalar_one()

    def _inserir_em_lotes(self, conn: Connection, tabela: Table, linhas: list[dict], tamanho: int = 500) -> None:
        for i in range(0, len(linhas), tamanho):
            conn.execute(insert(tabela), linhas[i : i + tamanho])

    # ----------------------------------------------------------------------------------- carga genérica
    def _carregar(
        self,
        rotulo: str,
        origem: str,
        destino: str,
        *,
        chave: Callable[[dict], int],
        mapper: Callable[[dict], dict],
        ignorar: dict[int, str] | None = None,
        alias: dict[int, int] | None = None,
        amostrar: bool = True,
        antes: Callable[[dict], None] | None = None,
    ) -> LinhaTabela:
        """Carrega uma tabela inteira. `ignorar`: id antigo -> motivo (registros fundidos em outro). `alias`: id antigo -> id
        antigo sobrevivente (o mapa de ids dos fundidos aponta para o sobrevivente)."""
        conn = self._conn
        tabela = self.T(destino)
        rows = self.fonte.linhas(origem)
        linha = self.conc.tabela(rotulo, origem=len(rows))
        self._linha = linha
        existentes = self._existentes(conn, tabela)
        novos: list[dict] = []
        chaves: dict[int, int] = {}
        migrados: list[dict] = []
        for r in rows:
            if ignorar and r["id"] in ignorar:
                linha.fundir(ignorar[r["id"]], r["id"])
                continue
            try:
                k = chave(r)
                valores = mapper(r)
            except Descartar as d:
                linha.descartar(d.motivo, r["id"])
                continue
            chaves[r["id"]] = k
            migrados.append(r)
            if k in existentes:
                linha.ja_existentes += 1
                continue
            valores["codigo_legado"] = k
            novos.append(valores)
            if amostrar:
                self.amostras.append((rotulo, destino, k, r, mapper))
        self._inserir_em_lotes(conn, tabela, novos)
        linha.carregados = len(novos)
        existentes = self._existentes(conn, tabela)
        self.mapas[origem] = {oid: existentes[k] for oid, k in chaves.items()}
        for velho, sobrevivente in (alias or {}).items():
            if sobrevivente in self.mapas[origem]:
                self.mapas[origem][velho] = self.mapas[origem][sobrevivente]
        self.ok_src[rotulo] = migrados
        linha.destino = self._contar_migrados(conn, tabela)
        self._linha = None
        return linha

    # ================================================================================== núcleo (core) genérico
    def _tenant_id(self, conn: Connection) -> int | None:
        t = self._core.get("tenant")
        if t is None:
            return None
        if self._tenant is None:
            existente = conn.execute(select(t.c.id).order_by(t.c.id).limit(1)).scalar()
            if existente is None:
                existente = self._inserir_core(
                    conn, "tenant", {"slug": "estudio", "nome": "Studio Mayris Pilates", "status": "ativo"}
                )
            self._tenant = existente
        return self._tenant

    def _inserir_core(self, conn: Connection, nome: str, valores: dict) -> int:
        """Insere numa tabela do core preenchendo só o que existe; colunas NOT NULL desconhecidas recebem um padrão (e vão ao relatório)."""
        t = self._core[nome]
        assert t is not None
        dados = {k: v for k, v in valores.items() if k in t.c}
        for col in t.c:
            if col.name in dados or col.primary_key:
                continue
            if col.name == "tenant_id":
                dados["tenant_id"] = self._tenant_id(conn)
                continue
            if col.nullable or col.server_default is not None:
                continue
            tipo = str(col.type).upper()
            if col.name in ("criado_em", "atualizado_em"):
                dados[col.name] = self._agora
            elif "BOOL" in tipo:
                dados[col.name] = "ativo" in col.name
            elif "INT" in tipo:
                dados[col.name] = 0
            elif "JSON" in tipo:
                dados[col.name] = []
            elif "DATE" in tipo or "TIME" in tipo:
                dados[col.name] = self._agora
            else:
                dados[col.name] = ""
            self.conc.alerta(
                "preenchimento_core", f"{nome}.{col.name} preenchida automaticamente (NOT NULL sem padrão no destino)"
            )
        return conn.execute(insert(t).values(**dados)).inserted_primary_key[0]

    # ================================================================================== etapas
    def executar(self) -> Conciliacao:
        c = self.conc
        try:
            if self.simular:
                self._conn_unica = self.engine.connect()
                self._conn_unica.begin()
            self._ler_orfas_origem()
            with self._etapa("perfis e usuários"):
                self._perfis()
                self._usuarios()
            with self._etapa("cadastros básicos"):
                self._cadastros_basicos()
            with self._etapa("profissionais"):
                self._profissionais()
            with self._etapa("agenda base, bloqueios e tokens"):
                self._horarios_bloqueios_tokens()
            with self._etapa("alunos, endereços e telefones"):
                self._alunos()
                self._enderecos()
                self._telefones()
            with self._etapa("contratos e documentos"):
                self._contratos()
                self._documentos()
            with self._etapa("sessões, reservas, evoluções e avaliações"):
                self._sessoes()
                self._avulsas_avaliativas()
                self._reservas()
                self._evolucoes_avaliacoes()
            with self._etapa("financeiro"):
                self._financeiro()
            with self._etapa("integrações e comunicação"):
                self._integracoes()
                self._comunicacao()
            with self._etapa("contadores de código"):
                self._contadores()
            self._verificar()
        except Exception as e:  # noqa: BLE001
            c.erros.append(f"{type(e).__name__}: {e}")
            raise
        finally:
            if self._conn_unica is not None:
                self._conn_unica.rollback()
                self._conn_unica.close()
            c.fim = datetime.now()
            self._finalizar_midia()
            c.avaliar()
        return c

    # ----------------------------------------------------------------------------------- origem
    def _ler_orfas_origem(self) -> None:
        for o in self.fonte.fks_orfas():
            self.conc.alerta("fks_orfas_origem", o)

    # ----------------------------------------------------------------------------------- perfis e usuários
    def _perfis(self) -> None:
        conn = self._conn
        t = self._core["perfil_acesso"]
        linha = self.conc.tabela("perfil_acesso (mapeamento)", origem=len(self.fonte.linhas("core_perfilacesso")))
        if t is None:
            raise RuntimeError("A tabela perfil_acesso não existe no destino (esquema do core ausente).")
        existentes = {_sem_acento(n): i for i, n in conn.execute(select(t.c.id, t.c.nome))}
        self._perfil_novo: dict[str, int] = {}
        for nome in PERFIS_NOVOS:
            i = existentes.get(_sem_acento(nome))
            if i is None:
                i = self._inserir_core(
                    conn,
                    "perfil_acesso",
                    {
                        "nome": nome,
                        "descricao": "Criado pelo ETL (permissões a definir pelo core)",
                        "administrador": nome == "Administrador",
                        "sistema": True,
                        "permissoes": [],
                    },
                )
                self.conc.alerta(
                    "pendencias",
                    f"Perfil '{nome}' não existia no destino: criado pelo ETL sem permissões. O core deve semear o catálogo.",
                )
            self._perfil_novo[nome] = i
        self.mapas["core_perfilacesso"] = {}
        for p in self.fonte.linhas("core_perfilacesso"):
            alvo = classificar_perfil(p["dsPerfilAcesso"])
            if alvo is None:
                alvo = PERFIL_PADRAO_DESCONHECIDO
                self.conc.alerta(
                    "perfis_desconhecidos",
                    f"Perfil antigo '{p['dsPerfilAcesso']}' (cd {p['cdPerfilAcesso']}) sem equivalente: usado '{alvo}'. Revisar.",
                )
            self.conc.alerta("perfis", f"'{p['dsPerfilAcesso']}' (cd {p['cdPerfilAcesso']}) → {alvo}")
            self.mapas["core_perfilacesso"][p["id"]] = self._perfil_novo[alvo]
        linha.destino = len(self.mapas["core_perfilacesso"])
        linha.informativo = True

    def _usuarios(self) -> None:
        conn = self._conn
        t = self._core["usuario"]
        if t is None:
            raise RuntimeError("A tabela usuario não existe no destino (esquema do core ausente).")
        users = self.fonte.linhas("auth_user")
        linha = self.conc.tabela("usuario", origem=len(users))
        profs = {p["user_id"]: p for p in self.fonte.linhas("core_profissional") if p["user_id"] is not None}
        existentes = {str(e).lower(): i for i, e in conn.execute(select(t.c.id, t.c.email))}
        usados = set(existentes)
        self.mapas["auth_user"] = {}
        algoritmos: Counter = Counter()
        for u in users:
            username = (u["username"] or "").strip()
            email = (u["email"] or "").strip().lower()
            if not email:
                email = username.lower() if "@" in username else f"{username.lower()}@legado.invalid"
                linha.corrigir("usuário sem e-mail: gerado a partir do login (precisa de e-mail real)", u["id"])
            prof = profs.get(u["id"])
            senha = u["password"] or ""
            usavel = bool(senha) and not senha.startswith("!")
            if usavel:
                algoritmos[senha.split("$", 1)[0]] += 1
            if prof is not None:
                perfil_id = self.mapas["core_perfilacesso"].get(prof["cdPerfilAcesso_id"])
            else:
                perfil_id = None
            if tf.booleano(u["is_superuser"]):
                perfil_id = self._perfil_novo["Administrador"]
            elif perfil_id is None:
                perfil_id = self._perfil_novo[PERFIL_PADRAO_DESCONHECIDO]
                self.conc.alerta(
                    "usuarios_revisar",
                    f"Usuário '{username}' sem profissional/perfil: recebeu '{PERFIL_PADRAO_DESCONHECIDO}'. Revisar.",
                )
            mapeados = set(self.mapas["auth_user"].values())
            if email in existentes and existentes[email] not in mapeados:  # já migrado numa execução anterior
                self.mapas["auth_user"][u["id"]] = existentes[email]
                linha.ja_existentes += 1
                continue
            if email in usados:  # e-mail repetido entre usuários da origem
                email = email.replace("@", f"+{u['id']}@", 1)
                linha.corrigir("e-mail duplicado entre usuários: acrescentado +id", u["id"])
                if email in existentes and existentes[email] not in mapeados:
                    self.mapas["auth_user"][u["id"]] = existentes[email]
                    linha.ja_existentes += 1
                    continue
            nome = (
                " ".join(x for x in ((u["first_name"] or "").strip(), (u["last_name"] or "").strip()) if x)
            ) or username
            ativo = tf.booleano(u["is_active"], True)
            ts = tf.como_instante(u["date_joined"]) or self._agora
            novo = self._inserir_core(
                conn,
                "usuario",
                {
                    "nome": nome,
                    "email": email,
                    "login": username or None,
                    "senha_hash": senha if usavel else None,
                    "ativo": ativo,
                    "acesso_sistema": ativo and usavel,
                    "convite_pendente": not usavel,
                    "perfil_acesso_id": perfil_id,
                    "perfil": "admin" if tf.booleano(u["is_superuser"]) else "operador",
                    "ultimo_acesso": tf.como_instante(u["last_login"]),
                    "criado_em": ts,
                    "atualizado_em": ts,
                },
            )
            usados.add(email)
            existentes[email] = novo
            self.mapas["auth_user"][u["id"]] = novo
            linha.carregados += 1
            if not usavel:
                self.conc.alerta(
                    "usuarios_revisar",
                    f"Usuário '{username}' sem senha utilizável no antigo: precisa definir senha (convite pendente).",
                )
        for alg, n in sorted(algoritmos.items()):
            self.conc.alerta("senhas", f"{n} usuário(s) com hash '{alg}' copiado como está")
        ids = list(self.mapas["auth_user"].values())
        linha.destino = self._contar_ids(conn, t, ids)

    def _contar_ids(self, conn: Connection, tabela: Table, ids: list[int], coluna: str = "id") -> int:
        total = 0
        ids = list(set(ids))
        for i in range(0, len(ids), 500):
            total += conn.execute(
                select(func.count()).select_from(tabela).where(tabela.c[coluna].in_(ids[i : i + 500]))
            ).scalar_one()
        return total

    # ----------------------------------------------------------------------------------- cadastros básicos
    def _cadastros_basicos(self) -> None:
        def enum_ou_nota(valor: Any, cls: type, padrao: Any, campo: str, ref: Any) -> Any:
            m, ok = tf.como_enum(valor, cls, padrao)
            if not ok:
                self._nota(
                    "corrigir",
                    f"{campo}: valor '{valor}' fora do domínio, usado '{padrao.value if padrao else None}'",
                    ref,
                )
            return m

        self._enum_ou_nota = enum_ou_nota
        self._carregar(
            "unidade",
            "core_unidade",
            "unidade",
            chave=lambda r: r["cdUnidade"],
            mapper=lambda r: {
                "nome": r["dsUnidade"],
                "capacidade": max(r["capacidade"] or 0, 0),
                "duracao_aula_minutos": r["duracao_aula_minutos"] or 50,
                "ativo": True,
                **self._ts(r, None),
            },
        )
        self._carregar(
            "tipo_servico",
            "core_tiposervico",
            "tipo_servico",
            chave=lambda r: r["cdTipoServico"],
            mapper=lambda r: {"nome": r["dsTipoServico"], "ativo": True, **self._ts(r, None)},
        )
        self._carregar(
            "profissao",
            "core_profissao",
            "profissao",
            chave=lambda r: r["cdProfissao"],
            mapper=lambda r: {"nome": r["dsProfissao"], **self._ts(r, None)},
        )
        self._carregar(
            "categoria",
            "core_categoria",
            "categoria",
            chave=lambda r: r["cdCategoria"],
            mapper=lambda r: {
                "nome": r["dsCategoria"],
                "tipo": enum_ou_nota(r["tipo"], TipoCategoria, TipoCategoria.DESPESA, "categoria.tipo", r["id"]),
                **self._ts(r, None),
            },
        )
        self._carregar(
            "subcategoria",
            "core_subcategoria",
            "subcategoria",
            chave=lambda r: r["cdSubcategoria"],
            mapper=lambda r: {
                "categoria_id": self._fk("core_categoria", r["cdCategoria_id"], obrigatorio=True),
                "nome": r["dsSubcategoria"],
                **self._ts(r, None),
            },
        )
        self._carregar(
            "fornecedor",
            "core_fornecedor",
            "fornecedor",
            chave=lambda r: r["cdFornecedor"],
            mapper=lambda r: {"nome": r["dsFornecedor"], **self._ts(r, None)},
        )
        self._carregar(
            "modelo_contrato",
            "core_modelocontrato",
            "modelo_contrato",
            chave=lambda r: r["cdModeloContrato"],
            mapper=lambda r: {
                "nome": r["dsNome"],
                "conteudo_html": r["conteudo_html"] or "",
                "ativo": tf.booleano(r["ativo"], True),
                **self._ts(r),
            },
        )
        self._carregar(
            "modelo_evolucao",
            "core_modeloevolucao",
            "modelo_evolucao",
            chave=lambda r: r["cdModeloEvolucao"],
            mapper=lambda r: {
                "titulo": r["titulo"],
                "texto": r["texto"] or "",
                "ativo": tf.booleano(r["ativo"], True),
                **self._ts(r),
            },
        )
        self._carregar(
            "termo_uso",
            "core_termouso",
            "termo_uso",
            chave=lambda r: r["cdTermoUso"],
            mapper=lambda r: {"nome": r["nome"], "conteudo_html": r["dsTermoUso"] or "", **self._ts(r, None)},
        )
        self._carregar(
            "plano",
            "core_plano",
            "plano",
            chave=lambda r: r["cdPlano"],
            mapper=lambda r: {
                "nome": r["dsPlano"],
                "tipo_servico_id": self._fk("core_tiposervico", r["cdTipoServico_id"], obrigatorio=True),
                "categoria_receita_id": self._fk("core_categoria", r["categoria_receita_id"], obrigatorio=False),
                "subcategoria_receita_id": self._fk(
                    "core_subcategoria", r["subcategoria_receita_id"], obrigatorio=False
                ),
                "modelo_contrato_id": self._fk("core_modelocontrato", r["modeloContrato_id"], obrigatorio=False),
                "valor": tf.dinheiro(r["valor"]) or Decimal("0.00"),
                "aulas_por_semana": r["aulas_por_semana"] or 0,
                "duracao_meses": r["duracao_meses"] or 1,
                "recorrencia": enum_ou_nota(
                    r["recorrencia"], Recorrencia, Recorrencia.MENSAL, "plano.recorrencia", r["id"]
                ),
                "avulso": tf.booleano(r["is_avulso"]),
                "ativo": True,
                **self._ts(r, None),
            },
        )

    # ----------------------------------------------------------------------------------- profissionais
    def _profissionais(self) -> None:
        def mapper(r: dict) -> dict:
            return {
                "nome": r["profissional"],
                "email": (tf.texto(r["email"]) or "").lower() or None,
                "celular": tf.texto(r["celular"]),
                "crefito": tf.texto(r["crefito"]),
                "data_nascimento": tf.como_data(r["dtNascimento"]),
                "usuario_id": self._fk("auth_user", r["user_id"], obrigatorio=False),
                "perfil_acesso_id": self.mapas["core_perfilacesso"].get(r["cdPerfilAcesso_id"]),
                "comissao_percentual": Decimal("0.00"),
                "ativo": True,
                **self._ts(r),
            }

        self._carregar(
            "profissional", "core_profissional", "profissional", chave=lambda r: r["cdProfissional"], mapper=mapper
        )
        sem_login = sum(1 for p in self.fonte.linhas("core_profissional") if p["user_id"] is None)
        if sem_login:
            self.conc.alerta(
                "info", f"{sem_login} profissional(is) sem login (usuario_id nulo): permitido no novo modelo."
            )
        self.conc.alerta(
            "info",
            "Comissão: profissional.comissao_percentual entra com 0 (a comissão não existia no sistema Django em produção).",
        )

    # ----------------------------------------------------------------------------------- horários, bloqueios, tokens
    def _horarios_bloqueios_tokens(self) -> None:
        hf_rows = self.fonte.linhas("core_horariofuncionamento")
        m2m = defaultdict(set)
        for x in self.fonte.linhas("core_horariofuncionamento_tipos_servico"):
            m2m[x["horariofuncionamento_id"]].add(x["tiposervico_id"])
        for r in hf_rows:  # o campo legado tipoServico entra no M2M atual
            if r["tipoServico_id"] is not None:
                m2m[r["id"]].add(r["tipoServico_id"])

        def mapper_hf(r: dict) -> dict:
            ini, fim = tf.como_hora(r["horaInicio"]), tf.como_hora(r["horaFim"])
            if not (0 <= r["diaSemana"] <= 6) or fim <= ini:
                raise Descartar("horário de funcionamento inválido (dia fora de 0-6 ou fim <= início)")
            return {
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "dia_semana": r["diaSemana"],
                "hora_inicio": ini,
                "hora_fim": fim,
                "ativo": tf.booleano(r["ativo"], True),
                **self._ts(r, None),
            }

        self._carregar(
            "horario_funcionamento",
            "core_horariofuncionamento",
            "horario_funcionamento",
            chave=lambda r: r["id"],
            mapper=mapper_hf,
        )
        # M2M (idempotente por par)
        conn = self._conn
        t = self.T("horario_funcionamento_tipo_servico")
        ja = {(a, b) for a, b in conn.execute(select(t.c.horario_funcionamento_id, t.c.tipo_servico_id))}
        novos = []
        for velho, tipos in m2m.items():
            hid = self.mapas["core_horariofuncionamento"].get(velho)
            if hid is None:
                continue
            for tp in tipos:
                tid = self.mapas["core_tiposervico"].get(tp)
                if tid is not None and (hid, tid) not in ja:
                    novos.append({"horario_funcionamento_id": hid, "tipo_servico_id": tid})
        self._inserir_em_lotes(conn, t, novos)
        esperado = sum(
            1
            for velho, tipos in m2m.items()
            if velho in self.mapas["core_horariofuncionamento"]
            for tp in tipos
            if tp in self.mapas["core_tiposervico"]
        )
        linha = self.conc.tabela("horario_funcionamento_tipo_servico (M2M)", origem=sum(len(v) for v in m2m.values()))
        perdidos = linha.origem - esperado
        if perdidos:
            linha.descartados["par ligado a horário descartado ou serviço inexistente"] = perdidos
        linha.carregados = len(novos)
        linha.destino = conn.execute(select(func.count()).select_from(t)).scalar_one()
        linha.informativo = True

        def mapper_hs(r: dict) -> dict:
            if not (0 <= r["diaSemana"] <= 6):
                raise Descartar("dia da semana fora de 0-6")
            return {
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "tipo_servico_id": self._fk("core_tiposervico", r["tipoServico_id"], obrigatorio=True),
                "profissional_id": self._fk("core_profissional", r["profissional_id"], obrigatorio=False),
                "dia_semana": r["diaSemana"],
                "hora_inicio": tf.como_hora(r["horaInicio"]),
                "hora_fim": tf.como_hora(r["horaFim"]),
                "capacidade": r["capacidade"],
                **self._ts(r, None),
            }

        self._carregar(
            "horario_studio", "core_horariostudio", "horario_studio", chave=lambda r: r["cdHorario"], mapper=mapper_hs
        )

        def mapper_bl(r: dict) -> dict:
            ini, fim = tf.como_hora(r["horaInicio"]), tf.como_hora(r["horaFim"])
            rec = tf.booleano(r["recorrente"])
            if fim <= ini:
                raise Descartar("bloqueio com hora final <= inicial")
            if rec and r["diaSemana"] is None:
                raise Descartar("bloqueio recorrente sem dia da semana")
            return {
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "tipo_servico_id": self._fk("core_tiposervico", r["tipoServico_id"], obrigatorio=False),
                "profissional_id": self._fk("core_profissional", r["profissional_id"], obrigatorio=False),
                "recorrente": rec,
                "dia_semana": r["diaSemana"],
                "data_inicio": tf.como_data(r["dataInicio"]),
                "data_fim": tf.como_data(r["dataFim"]),
                "hora_inicio": ini,
                "hora_fim": fim,
                "motivo": tf.texto(r["motivo"]),
                "ativo": tf.booleano(r["ativo"], True),
                **self._ts(r, None),
            }

        self._carregar(
            "bloqueio_agenda", "core_bloqueioagenda", "bloqueio_agenda", chave=lambda r: r["id"], mapper=mapper_bl
        )

        def mapper_tk(r: dict) -> dict:
            tok = r["token"] or ""
            if not tok:
                raise Descartar("token vazio")
            return {
                "nome": r["nome"],
                "token_hash": tf.hash_token(tok),
                "token_final": tok[-4:],
                "ativo": tf.booleano(r["ativo"], True),
                "ultimo_uso": tf.como_instante(r["ultimo_uso"]),
                **self._ts(r),
            }

        self._carregar(
            "integracao_token", "core_integracaotoken", "integracao_token", chave=lambda r: r["id"], mapper=mapper_tk
        )
        self.conc.alerta(
            "info",
            "Tokens de integração: o valor original NÃO é guardado; entra o SHA-256 (token_hash). Os integradores continuam enviando o mesmo valor.",
        )

    # ----------------------------------------------------------------------------------- alunos
    def _planejar_cpfs(self) -> dict[int, dict]:
        rows = self.fonte.linhas("core_aluno")
        n_contratos = Counter(c["cdAluno_id"] for c in self.fonte.linhas("core_contrato"))
        plano: dict[int, dict] = {}
        por_cpf: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            bruto = tf.texto(r["dsCPF"])
            sem = tf.booleano(r["sem_cpf"]) or (bruto or "").upper().startswith("SEM_CPF")
            if sem:
                plano[r["id"]] = {"cpf": None, "sem_cpf": True, "bruto": None}
                self.conc.alerta(
                    "alunos_sem_cpf", {"cdAluno": r["cdAluno"], "motivo": "marcado sem CPF no sistema antigo"}
                )
                continue
            d = tf.normalizar_cpf_digitos(bruto)
            if len(d) == 11:
                por_cpf[d].append(r)
                plano[r["id"]] = {"cpf": d, "sem_cpf": False, "bruto": None}
                if not tf.validar_cpf(d):
                    self.conc.alerta(
                        "cpf_invalido", {"cdAluno": r["cdAluno"], "motivo": "dígito verificador inválido (mantido)"}
                    )
            elif not d:
                plano[r["id"]] = {"cpf": None, "sem_cpf": True, "bruto": None}
                self.conc.alerta(
                    "alunos_sem_cpf",
                    {"cdAluno": r["cdAluno"], "motivo": "CPF vazio sem a marca sem_cpf: marcado sem_cpf"},
                )
            else:
                plano[r["id"]] = {"cpf": None, "sem_cpf": True, "bruto": bruto[:32]}
                self.conc.alerta(
                    "cpf_invalido",
                    {
                        "cdAluno": r["cdAluno"],
                        "motivo": f"CPF com {len(d)} dígitos: guardado em cpf_legado_bruto, aluno marcado sem_cpf",
                    },
                )
                self.conc.alerta("alunos_sem_cpf", {"cdAluno": r["cdAluno"], "motivo": "CPF irreconhecível"})
        for d, grupo in por_cpf.items():
            if len(grupo) < 2:
                continue
            mantido = max(grupo, key=lambda r: (n_contratos[r["id"]], -r["id"]))
            outros = [r for r in grupo if r is not mantido]
            for r in outros:
                plano[r["id"]] = {"cpf": None, "sem_cpf": True, "bruto": tf.texto(r["dsCPF"])[:32]}
                self.conc.alerta(
                    "alunos_sem_cpf",
                    {"cdAluno": r["cdAluno"], "motivo": "CPF repetido: ficou sem CPF (ver cpf_duplicado)"},
                )
            self.conc.alerta(
                "cpf_duplicado",
                {
                    "final_cpf": d[-2:],
                    "mantido_cdAluno": mantido["cdAluno"],
                    "sem_cpf_cdAluno": [r["cdAluno"] for r in outros],
                    "acao": "o aluno com mais contratos (depois o mais antigo) mantém o CPF; os outros ficam sem CPF, com o original em cpf_legado_bruto. Revisar e unificar manualmente.",
                },
            )
        return plano

    def _alunos(self) -> None:
        plano_cpf = self._planejar_cpfs()
        enum_ou_nota = self._enum_ou_nota

        def mapper(r: dict) -> dict:
            p = plano_cpf[r["id"]]
            ec, ok = tf.como_enum(r["estado_civil"], EstadoCivil, None)
            if not ok:
                ec = EstadoCivil.OUTRO
                self._nota("corrigir", "estado civil fora do domínio: OUTRO", r["id"])
            pag = tf.normalizar_cpf_digitos(r["cpf_pagador_recibo"])
            if pag and len(pag) != 11:
                self._nota("corrigir", "cpf_pagador_recibo com tamanho inválido: descartado o campo", r["id"])
                pag = ""
            foto = tf.caminho_midia("foto", r["foto"])
            assin = tf.caminho_midia("termo", r["termo_assinatura_imagem"])
            self.midia.registrar(
                tf.texto(r["foto"]), foto, f"aluno {r['cdAluno']} foto"
            ) if not self._silencioso else None
            self.midia.registrar(
                tf.texto(r["termo_assinatura_imagem"]), assin, f"aluno {r['cdAluno']} assinatura do termo"
            ) if not self._silencioso else None
            return {
                "nome": r["dsNome"],
                "cpf": p["cpf"],
                "sem_cpf": p["sem_cpf"],
                "cpf_legado_bruto": p["bruto"],
                "rg": tf.texto(r["dsRg"]),
                "email": (tf.texto(r["dsEmail"]) or "").lower() or None,
                "foto_path": foto,
                "autoriza_imagem": tf.booleano(r["autoriza_imagem"]),
                "status": enum_ou_nota(r["status"], StatusAluno, StatusAluno.ATIVO, "aluno.status", r["id"]),
                "data_nascimento": tf.como_data(r["dtNascimento"]),
                "estado_civil": ec,
                "profissao_id": self._fk("core_profissao", r["cdProfissao_id"], obrigatorio=False),
                "unidade_id": self._fk("core_unidade", r["cdUnidade_id"], obrigatorio=True),
                "cpf_pagador_recibo": pag or None,
                "termo_uso_id": self._fk("core_termouso", r["cdTermoUso_id"], obrigatorio=False),
                "termo_aceite_em": tf.como_instante(r["termo_aceite_em"]),
                "termo_assinatura_nome": tf.texto(r["termo_assinatura_nome"]),
                "termo_assinatura_documento": tf.texto(r["termo_assinatura_documento"]),
                "termo_assinatura_ip": tf.texto(r["termo_assinatura_ip"]),
                "termo_assinatura_path": assin,
                "termo_assinado_em": tf.como_instante(r["termo_assinado_em"]),
                **self._ts(r),
            }

        self._carregar("aluno", "core_aluno", "aluno", chave=lambda r: r["cdAluno"], mapper=mapper)

    def _enderecos(self) -> None:
        def mapper(r: dict) -> dict:
            cep = tf.so_digitos(r["dsCEP"])
            if cep and len(cep) != 8:
                self._nota("corrigir", "CEP sem 8 dígitos (mantidos os dígitos existentes)", r["id"])
            return {
                "aluno_id": self._fk("core_aluno", r["cdAluno_id"], obrigatorio=True),
                "logradouro": r["dsLogradouro"] or "",
                "numero": r["dsNumero"] or "",
                "cep": cep or None,
                "cidade": r["dsCidade"] or "",
                "bairro": r["dsBairro"] or "",
                **self._ts(r),
            }

        self._carregar(
            "aluno_endereco", "core_enderecoaluno", "aluno_endereco", chave=lambda r: r["cdEndereco"], mapper=mapper
        )
        # aluno.cdEndereco apontava para um endereço; no novo o vínculo é 1:1 por aluno_id. Conferir consistência da origem.
        for a in self.fonte.linhas("core_aluno"):
            e = a.get("cdEndereco_id")
            if e is not None:
                end = next((x for x in self.fonte.linhas("core_enderecoaluno") if x["id"] == e), None)
                if end is not None and end["cdAluno_id"] != a["id"]:
                    self.conc.alerta(
                        "info",
                        f"Aluno cd {a['cdAluno']}: cdEndereco apontava para endereço de outro aluno (ignorado; vale cdAluno do endereço).",
                    )

    def _telefones(self) -> None:
        conn = self._conn
        t = self.T("aluno_telefone")
        rows = self.fonte.linhas("core_telefonealuno")
        linha = self.conc.tabela("aluno_telefone", origem=len(rows))
        self._linha = linha
        por_aluno: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            por_aluno[r["cdAluno_id"]].append(r)
        existentes = {(a, n) for a, n in conn.execute(select(t.c.aluno_id, t.c.numero))}
        novos: list[dict] = []
        esperado: set[tuple[int, str]] = set()
        for aluno_antigo, lista in por_aluno.items():
            aid = self.mapas["core_aluno"].get(aluno_antigo)
            if aid is None:
                for r in lista:
                    linha.descartar("aluno do telefone inexistente/não migrado", r["id"])
                continue
            ordem = 0
            vistos: set[str] = set()
            # cdTelefone é instável (o antigo apagava e recriava a cada salvamento); a ordem relativa dentro do aluno vale
            for r in sorted(lista, key=lambda x: (x["cdTelefone"], x["id"])):
                num = tf.normalizar_telefone_br(r["dsTelefone"])
                if num is None:
                    linha.descartar("telefone vazio ou com menos de 8 dígitos", r["id"])
                    continue
                if num in vistos:
                    linha.descartar("telefone repetido no mesmo aluno (após normalizar)", r["id"])
                    continue
                vistos.add(num)
                ordem += 1
                esperado.add((aid, num))
                if num != tf.so_digitos(r["dsTelefone"]):
                    linha.corrigir("telefone normalizado (DDI 55 / nono dígito)")
                if (aid, num) in existentes:
                    linha.ja_existentes += 1
                    continue
                novos.append(
                    {
                        "aluno_id": aid,
                        "ordem": ordem,
                        "numero": num,
                        "numero_original": tf.texto(r["dsTelefone"]),
                        **self._ts(r),
                    }
                )
        self._inserir_em_lotes(conn, t, novos)
        linha.carregados = len(novos)
        linha.destino = self._contar_ids(conn, t, [a for a, _ in esperado], "aluno_id")
        self._linha = None
        self.conc.alerta(
            "info", "Telefones: cdTelefone antigo NÃO preservado (era instável); ordem reconstruída por aluno."
        )

    # ----------------------------------------------------------------------------------- contratos e documentos
    def _contratos(self) -> None:
        def mapper(r: dict) -> dict:
            st, ok = tf.como_enum(r["status"], StatusAssinatura, StatusAssinatura.NAO_ASSINADO)
            if not ok:
                self._nota("corrigir", "status de assinatura desconhecido: NAO_ASSINADO", r["id"])
            fp = tf.texto(r["modo_pagamento"])
            forma, ok2 = tf.como_enum(fp, FormaPagamento, None)
            if not ok2:
                self._nota("corrigir", f"forma de pagamento '{fp}' desconhecida: nula", r["id"])
            rec, _ = tf.como_enum(r["recorrencia"], Recorrencia, Recorrencia.MENSAL)
            assin = tf.caminho_midia("assinatura_contrato", r["assinatura_imagem"])
            if not self._silencioso:
                self.midia.registrar(tf.texto(r["assinatura_imagem"]), assin, f"contrato {r['cdContrato']} assinatura")
            ini, fim = tf.como_data(r["dtInicioContrato"]), tf.como_data(r["dtFimContrato"])
            if fim < ini:
                self.conc.alerta(
                    "info", f"Contrato cd {r['cdContrato']}: data fim anterior ao início (migrado como está)."
                )
            return {
                "aluno_id": self._fk("core_aluno", r["cdAluno_id"], obrigatorio=True),
                "plano_id": self._fk("core_plano", r["cdPlano_id"], obrigatorio=True),
                "unidade_id": self._fk("core_unidade", r["cdUnidade_id"], obrigatorio=True),
                "profissional_id": self._fk("core_profissional", r["cdProfissional_id"], obrigatorio=True),
                "recorrencia": rec,
                "forma_pagamento": forma,
                "valor_aula": tf.dinheiro(r["valor_aula"]),
                "valor_parcela": tf.dinheiro(r["valor_parcela"]) or Decimal("0.00"),
                "valor_total": tf.dinheiro(r["valor_total"]) or Decimal("0.00"),
                "data_inicio": ini,
                "data_fim": fim,
                "status_assinatura": st,
                "assinado_em": tf.como_instante(r["assinado_em"]),
                "assinatura_nome": tf.texto(r["assinatura_nome"]),
                "assinatura_documento": tf.texto(r["assinatura_documento"]),
                "assinatura_ip": tf.texto(r["assinatura_ip"]),
                "assinatura_path": assin,
                **self._ts(r),
            }

        self._carregar("contrato", "core_contrato", "contrato", chave=lambda r: r["cdContrato"], mapper=mapper)

    def _documentos(self) -> None:
        def mapper(r: dict) -> dict:
            novo = tf.caminho_midia("documento", r["arquivo"])
            h = (
                None
                if self._silencioso
                else self.midia.registrar(tf.texto(r["arquivo"]), novo, f"documento {r['cdDocumento']}")
            )
            if self._silencioso:
                h = self.midia.hashes.get(novo)
            org, ok = tf.como_enum(r["origem"], OrigemDocumento, OrigemDocumento.UPLOAD)
            if not ok:
                self._nota("corrigir", "origem de documento desconhecida: UPLOAD", r["id"])
            return {
                "aluno_id": self._fk("core_aluno", r["aluno_id"], obrigatorio=True),
                "contrato_id": self._fk("core_contrato", r["contrato_id"], obrigatorio=False),
                "titulo": r["titulo"],
                "arquivo_path": novo or "",
                "sha256": h,
                "descricao": tf.texto(r["descricao"]),
                "origem": org,
                **self._ts(r),
            }

        self._carregar(
            "aluno_documento", "core_alunodocumento", "aluno_documento", chave=lambda r: r["cdDocumento"], mapper=mapper
        )

    # ----------------------------------------------------------------------------------- sessões
    def _sessoes(self) -> None:
        sess = self.fonte.linhas("core_aulasessao")
        unidades = {u["id"]: u for u in self.fonte.linhas("core_unidade")}
        grupos: dict[tuple, list[dict]] = defaultdict(list)
        for s in sess:
            grupos[
                (
                    s["unidade_id"],
                    s["tipoServico_id"],
                    s["profissional_id"] or 0,
                    tf.como_data(s["data"]),
                    tf.como_hora(s["horaInicio"]),
                )
            ].append(s)
        reservas_por_sessao = Counter(r["aulaSessao_id"] for r in self.fonte.linhas("core_reserva"))
        self._alias_sessao: dict[int, int] = {}
        ignorar: dict[int, str] = {}
        self._capacidade_fundida: dict[int, int | None] = {}
        for chave, grupo in grupos.items():
            sobrevivente = grupo[0]
            if len(grupo) == 1:
                continue
            caps = {g["capacidade"] for g in grupo if g["capacidade"] is not None}
            self._capacidade_fundida[sobrevivente["id"]] = max(caps) if caps else None
            for dup in grupo[1:]:
                ignorar[dup["id"]] = (
                    "sessão duplicada (mesma unidade/serviço/profissional/data/início) fundida na de menor id"
                )
                self._alias_sessao[dup["id"]] = sobrevivente["id"]
            self.conc.alerta(
                "sessoes_fundidas",
                {
                    "data": str(chave[3]),
                    "hora": str(chave[4]),
                    "sobrevivente_id": sobrevivente["id"],
                    "fundidas_ids": [g["id"] for g in grupo[1:]],
                    "reservas_movidas": sum(reservas_por_sessao[g["id"]] for g in grupo[1:]),
                    "capacidades": sorted(caps) if caps else None,
                },
            )

        def mapper(r: dict) -> dict:
            ini, fim = tf.como_hora(r["horaInicio"]), tf.como_hora(r["horaFim"])
            if fim <= ini:
                dur = unidades.get(r["unidade_id"], {}).get("duracao_aula_minutos") or 50
                fim = (datetime.combine(tf.como_data(r["data"]), ini) + timedelta(minutes=dur)).time()
                self._nota(
                    "corrigir", "sessão com hora final <= inicial: fim recalculado pela duração da unidade", r["id"]
                )
            cap = self._capacidade_fundida.get(r["id"], r["capacidade"])
            return {
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "tipo_servico_id": self._fk("core_tiposervico", r["tipoServico_id"], obrigatorio=True),
                "profissional_id": self._fk("core_profissional", r["profissional_id"], obrigatorio=False),
                "data": tf.como_data(r["data"]),
                "hora_inicio": ini,
                "hora_fim": fim,
                "capacidade": cap,
                "reservas_ativas": 0,
                **self._ts(r),
            }

        self._carregar(
            "aula_sessao",
            "core_aulasessao",
            "aula_sessao",
            chave=lambda r: r["id"],
            mapper=mapper,
            ignorar=ignorar,
            alias=self._alias_sessao,
            amostrar=True,
        )

    def _avulsas_avaliativas(self) -> None:
        def mapper_av(r: dict) -> dict:
            rec, _ = tf.como_enum(r["recorrencia"], Recorrencia, Recorrencia.SEMANAL)
            return {
                "aluno_id": self._fk("core_aluno", r["aluno_id"], obrigatorio=True),
                "plano_id": self._fk("core_plano", r["plano_id"], obrigatorio=True),
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "profissional_id": self._fk("core_profissional", r["profissional_id"], obrigatorio=True),
                "recorrencia": rec,
                "quantidade": r["quantidade"] or 1,
                "valor_aula": tf.dinheiro(r["valor_aula"]),
                "valor_total": tf.dinheiro(r["valor_total"]) or Decimal("0.00"),
                "data_inicio": tf.como_data(r["dtInicio"]),
                "data_fim": tf.como_data(r["dtFim"]),
                **self._ts(r),
            }

        self._carregar(
            "aula_avulsa", "core_aulaavulsa", "aula_avulsa", chave=lambda r: r["cdAulaAvulsa"], mapper=mapper_av
        )

        def mapper_aa(r: dict) -> dict:
            tipo, _ = tf.como_enum(r["tipo"], TipoAvaliativa, TipoAvaliativa.AVALIATIVA)
            st, ok = tf.como_enum(r["status"], StatusAvaliativa, StatusAvaliativa.AGENDADA)
            if not ok:
                self._nota("corrigir", "status de aula avaliativa desconhecido: AGENDADA", r["id"])
            return {
                "tipo": tipo,
                "aluno_id": self._fk("core_aluno", r["aluno_id"], obrigatorio=True),
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "profissional_id": self._fk("core_profissional", r["profissional_id"], obrigatorio=True),
                "tipo_servico_id": self._fk("core_tiposervico", r["tipoServico_id"], obrigatorio=False),
                "data": tf.como_data(r["data"]),
                "hora_inicio": tf.como_hora(r["horaInicio"]),
                "hora_fim": tf.como_hora(r["horaFim"]),
                "status": st,
                "queixa_principal": tf.texto(r["queixa_principal"]),
                "objetivos": tf.texto(r["objetivos"]),
                "historico_saude": tf.texto(r["historico_saude"]),
                "observacoes": tf.texto(r["observacoes"]),
                "contrato_id": self._fk("core_contrato", r["contrato_id"], obrigatorio=False),
                **self._ts(r),
            }

        self._carregar(
            "aula_avaliativa",
            "core_aulaavaliativa",
            "aula_avaliativa",
            chave=lambda r: r["cdAulaAvaliativa"],
            mapper=mapper_aa,
        )

    # ----------------------------------------------------------------------------------- reservas
    def _planejar_contratos_das_reservas(self, sessoes_por_id: dict[int, dict]) -> dict[int, int | None]:
        """Para cada reserva do antigo, o contrato inferido (id antigo) ou None, e o relato do que não foi inequívoco."""
        planos = {p["id"]: p for p in self.fonte.linhas("core_plano")}
        por_aluno: dict[int, list[dict]] = defaultdict(list)
        for c in self.fonte.linhas("core_contrato"):
            por_aluno[c["cdAluno_id"]].append(c)
        resultado: dict[int, int | None] = {}
        cont = Counter()
        exemplos: dict[str, list] = defaultdict(list)
        for r in self.fonte.linhas("core_reserva"):
            s = sessoes_por_id.get(self._alias_sessao.get(r["aulaSessao_id"], r["aulaSessao_id"]))
            if r["pacote_avulso_id"] is not None:
                cont["avulsa"] += 1
                resultado[r["id"]] = None
                continue
            if r["aula_avaliativa_id"] is not None:
                cont["avaliativa"] += 1
                resultado[r["id"]] = None
                continue
            if s is None:
                resultado[r["id"]] = None
                continue
            d = tf.como_data(s["data"])
            cand = []
            for c in por_aluno.get(r["aluno_id"], []):
                pl = planos.get(c["cdPlano_id"])
                if (
                    c["cdUnidade_id"] == s["unidade_id"]
                    and pl is not None
                    and pl["cdTipoServico_id"] == s["tipoServico_id"]
                    and tf.como_data(c["dtInicioContrato"]) <= d <= tf.como_data(c["dtFimContrato"])
                ):
                    cand.append(c["id"])
            if len(cand) == 1:
                resultado[r["id"]] = cand[0]
                cont["inferido"] += 1
            else:
                resultado[r["id"]] = None
                if s["profissional_id"] is None and not cand:
                    cat = "sem profissional (aula TotalPass/externa)"
                elif len(cand) > 1:
                    cat = "ambígua: mais de um contrato cobre a aula"
                else:
                    cat = "nenhum contrato do aluno cobre data/unidade/serviço"
                cont[cat] += 1
                if len(exemplos[cat]) < 8:
                    exemplos[cat].append(
                        {"reserva_id": r["id"], "aluno_id": r["aluno_id"], "data": str(d), "contratos": cand}
                    )
        self.conc.alerta(
            "info",
            f"Contrato inferido sem ambiguidade em {cont['inferido']} reserva(s); avulsas (esperado sem contrato): {cont['avulsa']}; avaliativas: {cont['avaliativa']}.",
        )
        for cat in (
            "sem profissional (aula TotalPass/externa)",
            "ambígua: mais de um contrato cobre a aula",
            "nenhum contrato do aluno cobre data/unidade/serviço",
        ):
            if cont[cat]:
                self.conc.alerta(
                    "reservas_sem_contrato", {"categoria": cat, "quantidade": cont[cat], "exemplos": exemplos[cat]}
                )
        return resultado

    def _reservas(self) -> None:
        sessoes_por_id = {s["id"]: s for s in self.fonte.linhas("core_aulasessao")}
        reservas = self.fonte.linhas("core_reserva")
        deps = Counter()
        for tabela, col in (
            ("core_evolucaoaluno", "reserva_id"),
            ("core_avaliacaoaluno", "reserva_id"),
            ("core_contasreceber", "reserva_id"),
        ):
            for x in self.fonte.linhas(tabela):
                if x[col] is not None:
                    deps[x[col]] += 1
        grupos: dict[tuple, list[dict]] = defaultdict(list)
        for r in reservas:
            grupos[(r["aluno_id"], self._alias_sessao.get(r["aulaSessao_id"], r["aulaSessao_id"]))].append(r)
        ignorar: dict[int, str] = {}
        self._alias_reserva: dict[int, int] = {}
        for (aluno, sobrev), grupo in grupos.items():
            if len(grupo) < 2:
                continue
            mantida = max(grupo, key=lambda r: (deps[r["id"]], RANK_STATUS_RESERVA.get(r["status"], 0), -r["id"]))
            for r in grupo:
                if r is mantida:
                    continue
                ignorar[r["id"]] = (
                    "reserva repetida (mesmo aluno) após fundir sessões duplicadas; ficou a de maior uso/status"
                )
                self._alias_reserva[r["id"]] = mantida["id"]
            self.conc.alerta(
                "reservas_fundidas",
                {
                    "aluno_id": aluno,
                    "sessao_sobrevivente": sobrev,
                    "reserva_mantida": mantida["id"],
                    "descartadas": [r["id"] for r in grupo if r is not mantida],
                    "status": {r["id"]: r["status"] for r in grupo},
                },
            )
        inferidos = self._planejar_contratos_das_reservas(sessoes_por_id)

        def mapper(r: dict) -> dict:
            st, ok = tf.como_enum(r["status"], StatusReserva, StatusReserva.RESERVADA)
            if not ok:
                self._nota("corrigir", "status de reserva desconhecido: RESERVADA", r["id"])
            sess_old = self._alias_sessao.get(r["aulaSessao_id"], r["aulaSessao_id"])
            contrato_antigo = inferidos.get(r["id"])
            return {
                "aluno_id": self._fk("core_aluno", r["aluno_id"], obrigatorio=True),
                "aula_sessao_id": self._fk(
                    "core_aulasessao", sess_old, obrigatorio=True, motivo="sessão inexistente (FK órfã)"
                ),
                "contrato_id": self.mapas["core_contrato"].get(contrato_antigo) if contrato_antigo else None,
                "aula_avulsa_id": self._fk("core_aulaavulsa", r["pacote_avulso_id"], obrigatorio=False),
                "aula_avaliativa_id": self._fk("core_aulaavaliativa", r["aula_avaliativa_id"], obrigatorio=False),
                "status": st,
                "confirmada_em": tf.como_instante(r["confirmada_em"]),
                "desmarcada_em": tf.como_instante(r["desmarcada_em"]),
                "reposicao_ate": tf.como_data(r["reposicao_ate"]),
                **self._ts(r),
            }

        self._carregar(
            "reserva",
            "core_reserva",
            "reserva",
            chave=lambda r: r["id"],
            mapper=mapper,
            ignorar=ignorar,
            alias=self._alias_reserva,
        )
        # contador de vagas = reservas em RESERVADA por sessão (idempotente: recalcula para as sessões migradas)
        conn = self._conn
        s, rs = self.T("aula_sessao"), self.T("reserva")
        conta = (
            select(func.count())
            .select_from(rs)
            .where(rs.c.aula_sessao_id == s.c.id, rs.c.status == StatusReserva.RESERVADA)
            .scalar_subquery()
        )
        conn.execute(
            update(s)
            .where(s.c.codigo_legado.is_not(None))
            .values(reservas_ativas=conta, atualizado_em=s.c.atualizado_em)
        )
        # sessões acima da capacidade (dado sujo do antigo, só relatado)
        un = self.T("unidade")
        cap_efetiva = func.coalesce(
            s.c.capacidade, select(un.c.capacidade).where(un.c.id == s.c.unidade_id).scalar_subquery()
        )
        for sid, data, ativas, cap in conn.execute(
            select(s.c.codigo_legado, s.c.data, s.c.reservas_ativas, cap_efetiva).where(
                s.c.reservas_ativas > cap_efetiva
            )
        ):
            self.conc.alerta(
                "sessoes_acima_capacidade",
                {"sessao_id_legado": sid, "data": str(data), "reservas_ativas": ativas, "capacidade": cap},
            )

    def _evolucoes_avaliacoes(self) -> None:
        def make(origem_tabela: str):
            def mapper(r: dict) -> dict:
                rid = self._alias_reserva.get(r["reserva_id"], r["reserva_id"])
                return {
                    "reserva_id": self._fk(
                        "core_reserva", rid, obrigatorio=True, motivo="reserva inexistente (FK órfã)"
                    ),
                    "profissional_id": self._fk("core_profissional", r["profissional_id"], obrigatorio=True),
                    "texto": r["texto"] or "",
                    **self._ts(r, "dtEvolucao" if "dtEvolucao" in r else "dtAvaliacao"),
                }

            return mapper

        self._carregar(
            "evolucao", "core_evolucaoaluno", "evolucao", chave=lambda r: r["id"], mapper=make("core_evolucaoaluno")
        )
        self._carregar(
            "avaliacao", "core_avaliacaoaluno", "avaliacao", chave=lambda r: r["id"], mapper=make("core_avaliacaoaluno")
        )

    # ----------------------------------------------------------------------------------- financeiro
    def _financeiro(self) -> None:
        contratos = {c["id"]: c for c in self.fonte.linhas("core_contrato")}
        reservas = {r["id"]: r for r in self.fonte.linhas("core_reserva")}

        def mapper_cr(r: dict) -> dict:
            st_raw = (tf.texto(r["status"]) or "ABERTO").upper()
            if st_raw == "ATRASADO":
                st = StatusReceber.ABERTO
                self._nota("corrigir", "status ATRASADO gravado no antigo -> ABERTO (atraso agora é derivado)", r["id"])
            else:
                st, ok = tf.como_enum(st_raw, StatusReceber, StatusReceber.ABERTO)
                if not ok:
                    self._nota("corrigir", f"status '{st_raw}' desconhecido -> ABERTO", r["id"])
            contrato_old = r["contrato_id"] if r["contrato_id"] in contratos else None
            if r["contrato_id"] is not None and contrato_old is None:
                self._nota("corrigir", "contrato inexistente (FK órfã): vínculo zerado", r["id"])
            reserva_old = r["reserva_id"] if r["reserva_id"] in reservas else None
            if r["reserva_id"] is not None and reserva_old is None:
                self._nota("corrigir", "reserva inexistente (FK órfã): vínculo zerado", r["id"])
            reserva_old = self._alias_reserva.get(reserva_old, reserva_old) if reserva_old else None
            aluno_old = None  # contrato -> reserva -> aluno (regra do antigo)
            if contrato_old is not None:
                aluno_old = contratos[contrato_old]["cdAluno_id"]
            elif reserva_old is not None:
                aluno_old = reservas[reserva_old]["aluno_id"]
            else:
                aluno_old = r["aluno_id"]
            aluno_novo = self.mapas["core_aluno"].get(aluno_old) if aluno_old is not None else None
            if aluno_novo is None:
                raise Descartar("conta sem aluno resolvível (sem contrato, reserva ou aluno válidos)")
            pag = tf.como_data(r["dtPagamento"])
            if st == StatusReceber.PAGO and pag is None:
                self._nota("corrigir", "conta PAGO sem data de pagamento (mantida)", r["id"])
            return {
                "aluno_id": aluno_novo,
                "contrato_id": self.mapas["core_contrato"].get(contrato_old) if contrato_old else None,
                "reserva_id": self.mapas["core_reserva"].get(reserva_old) if reserva_old else None,
                "descricao": tf.texto(r["descricao"]),
                "status": st,
                "valor": tf.dinheiro(r["valor"]),
                "vencimento": tf.como_data(r["dtVencimento"]),
                "competencia": tf.texto(r["competencia"]),
                "pagamento": pag,
                "recibo_saude_gerado_em": tf.como_instante(r["recibo_saude_gerado_em"]),
                **self._ts(r),
            }

        self._carregar(
            "conta_receber", "core_contasreceber", "conta_receber", chave=lambda r: r["id"], mapper=mapper_cr
        )

        def mapper_cp(r: dict) -> dict:
            st_raw = (tf.texto(r["status"]) or "AGENDADO").upper()
            if st_raw == "ATRASADO":
                st = StatusPagar.AGENDADO
                self._nota("corrigir", "status ATRASADO gravado no antigo -> AGENDADO (atraso derivado)", r["id"])
            else:
                st, ok = tf.como_enum(st_raw, StatusPagar, StatusPagar.AGENDADO)
                if not ok:
                    self._nota("corrigir", f"status '{st_raw}' desconhecido -> AGENDADO", r["id"])
            rec, ok2 = tf.como_enum(r["recorrencia"], RecorrenciaPagar, None)
            if not ok2:
                self._nota("corrigir", "recorrência desconhecida: nula", r["id"])
            comp = tf.caminho_midia("comprovante_pagar", r["comprovante"])
            if not self._silencioso:
                self.midia.registrar(
                    tf.texto(r["comprovante"]), comp, f"conta a pagar {r['cdContasPagar']} comprovante"
                )
            return {
                "fornecedor_id": self._fk("core_fornecedor", r["cdFornecedor_id"], obrigatorio=True),
                "categoria_id": self._fk("core_categoria", r["cdCategoria_id"], obrigatorio=True),
                "subcategoria_id": self._fk("core_subcategoria", r["cdSubcategoria_id"], obrigatorio=True),
                "vencimento": tf.como_data(r["dtVencimento"]),
                "valor": tf.dinheiro(r["valor"]),
                "recorrencia": rec,
                "recorrencia_quantidade": r["recorrencia_quantidade"],
                "status": st,
                "pagamento": tf.como_data(r["dtPagamento"]),
                "comprovante_path": comp,
                "motivo_cancelamento": tf.texto(r["motivo_cancelamento"]),
                **self._ts(r),
            }

        self._carregar(
            "conta_pagar", "core_contaspagar", "conta_pagar", chave=lambda r: r["cdContasPagar"], mapper=mapper_cp
        )
        self._carregar(
            "conta_bancaria",
            "core_contabancaria",
            "conta_bancaria",
            chave=lambda r: r["cdConta"],
            mapper=lambda r: {
                "banco": r["banco"],
                "agencia": r["agencia"],
                "conta": r["conta"],
                "saldo_inicial": tf.dinheiro(r["saldo_inicial"]) or Decimal("0.00"),
                "ativo": tf.booleano(r["ativo"], True),
                **self._ts(r),
            },
        )

        def mapper_mv(r: dict) -> dict:
            tp, ok = tf.como_enum(r["tipo"], TipoMovimento, None)
            if not ok or tp is None:
                raise Descartar("tipo de movimento desconhecido")
            comp = tf.caminho_midia("comprovante_movimento", r["comprovante"])
            if not self._silencioso:
                self.midia.registrar(tf.texto(r["comprovante"]), comp, f"movimento {r['id']} comprovante")
            return {
                "conta_id": self._fk("core_contabancaria", r["conta_id"], obrigatorio=True),
                "tipo": tp,
                "valor": tf.dinheiro(r["valor"]),
                "data": tf.como_data(r["data"]),
                "descricao": tf.texto(r["descricao"]),
                "comprovante_path": comp,
                **self._ts(r),
            }

        self._carregar(
            "movimento_conta", "core_movimentoconta", "movimento_conta", chave=lambda r: r["id"], mapper=mapper_mv
        )
        self._receita_saude()

    def _receita_saude(self) -> None:
        conn = self._conn
        t = self.T("receita_saude_config")
        rows = self.fonte.linhas("core_receitasaudeconfig")
        linha = self.conc.tabela("receita_saude_config", origem=len(rows))
        if rows:
            ultimo = rows[-1]  # registro único: vale o mais recente (order_by -id no antigo)
            for r in rows[:-1]:
                linha.descartar("registro único: mantido o mais recente", r["id"])
            if conn.execute(select(func.count()).select_from(t)).scalar_one() == 0:
                cpf = tf.so_digitos(ultimo["cpf_profissional"])
                conn.execute(
                    insert(t).values(
                        cpf_profissional=cpf,
                        registro_profissional=tf.texto(ultimo["registro_profissional"]),
                        codigo_ocupacao=ultimo["codigo_ocupacao"] or "231",
                        descricao_padrao=ultimo["descricao_padrao"] or "Aulas de Pilates",
                        **self._ts(ultimo, "dtAtualizacao"),
                    )
                )
                linha.carregados = 1
            else:
                linha.ja_existentes = 1
        linha.destino = conn.execute(select(func.count()).select_from(t)).scalar_one()

    # ----------------------------------------------------------------------------------- integrações e comunicação
    def _integracoes(self) -> None:
        cif = self.cif

        def mapper_wa(r: dict) -> dict:
            inst = tf.texto(r["evolution_instance"])
            blank = lambda v: tf.texto(v)  # noqa: E731
            return {
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "provedor": ProvedorWhatsapp.evolution if inst else ProvedorWhatsapp.wasender,
                "url_api": tf.texto(r["evolution_url"]),
                "usuario_api": tf.texto(r["evolution_usuario"]),
                "credencial_cifrado": cif.cifrar(r["evolution_senha"]),
                "instancia": inst,
                "acompanhar_envios": tf.booleano(r["acompanhar_envios"]),
                "numero_acompanhamento": tf.texto(r["numero_acompanhamento"]),
                "avisar_aluno": tf.booleano(r["avisar_aluno"], True),
                "horario_aviso_aluno": tf.como_hora(r["horario_aviso_aluno"]),
                "template_aviso_aluno": blank(r["template_aviso_aluno"]),
                "avisar_professor": tf.booleano(r["avisar_professor"], True),
                "horario_aviso_professor": tf.como_hora(r["horario_aviso_professor"]),
                "template_aviso_professor": blank(r["template_aviso_professor"]),
                "enviar_link_contrato": tf.booleano(r["enviar_link_contrato"], True),
                "template_link_contrato": blank(r["template_link_contrato"]),
                "avisar_renovacao": tf.booleano(r["avisar_renovacao"], True),
                "horario_aviso_renovacao": tf.como_hora(r["horario_aviso_renovacao"]),
                "template_aviso_renovacao": blank(r["template_aviso_renovacao"]),
                "avisar_aniversario": tf.booleano(r["avisar_aniversario"]),
                "horario_aviso_aniversario": tf.como_hora(r["horario_aviso_aniversario"]),
                "template_aniversario": blank(r["template_aniversario"]),
                "avisar_vencimento": tf.booleano(r["avisar_vencimento"]),
                "horario_aviso_vencimento": tf.como_hora(r["horario_aviso_vencimento"]),
                "template_vencimento_proximo": blank(r["template_vencimento_proximo"]),
                "avisar_atraso": tf.booleano(r["avisar_atraso"]),
                "horario_aviso_atraso": tf.como_hora(r["horario_aviso_atraso"]),
                "template_mensalidade_atraso": blank(r["template_mensalidade_atraso"]),
                "avisar_tres_meses": tf.booleano(r["avisar_tres_meses"]),
                "horario_aviso_tres_meses": tf.como_hora(r["horario_aviso_tres_meses"]),
                "template_tres_meses": blank(r["template_tres_meses"]),
                "avisar_fim_contrato": tf.booleano(r["avisar_fim_contrato"], True),
                "template_fim_contrato": blank(r["template_fim_contrato"]),
                "variaveis_template": tf.como_json(r["variaveis_template"]),
                **self._ts(r),
            }

        self._carregar(
            "whatsapp_config",
            "core_whatsappconfiguracao",
            "whatsapp_config",
            chave=lambda r: r["id"],
            mapper=mapper_wa,
            amostrar=False,
        )

        def mapper_tp(r: dict) -> dict:
            return {
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=True),
                "ativo": tf.booleano(r["ativo"], True),
                "partner_api_key_cifrado": cif.cifrar(r["partner_api_key"]),
                "place_api_key_cifrado": cif.cifrar(r["place_api_key"]),
                "webhook_token_cifrado": cif.cifrar(r["webhook_token"]),
                "place_id": tf.texto(r["place_id"]),
                "criar_aluno_automatico": tf.booleano(r["criar_aluno_automatico"], True),
                "somente_dia": tf.booleano(r["somente_dia"], True),
                **self._ts(r),
            }

        self._carregar(
            "totalpass_config",
            "core_totalpassconfiguracao",
            "totalpass_config",
            chave=lambda r: r["id"],
            mapper=mapper_tp,
            amostrar=False,
        )

        def mapper_ev(r: dict) -> dict:
            return {
                "event_id": tf.texto(r["event_id"]),
                "slot_id": tf.texto(r["slot_id"]),
                "documento_usuario": tf.texto(r["user_document"]),
                "status": tf.texto(r["status"]),
                "payload": tf.como_json(r["payload"]) or {},
                "recebido_em": tf.como_instante(r["received_at"]) or self._agora,
                "processado_em": tf.como_instante(r["processed_at"]),
                "erro": tf.texto(r["error"]),
            }

        self._carregar(
            "totalpass_evento",
            "core_totalpasswebhookevent",
            "totalpass_evento",
            chave=lambda r: r["id"],
            mapper=mapper_ev,
        )
        self._email()

    def _email(self) -> None:
        conn = self._conn
        rows = self.fonte.linhas("core_emailconfiguracao")
        linha = self.conc.tabela("config_email (core)", origem=len(rows))
        t = self._core.get("config_email")
        if not rows:
            linha.destino = 0
            return
        if t is None:
            for r in rows:
                linha.adiar(
                    "tabela config_email ainda não existe no destino (core em reescrita): reexecutar o ETL depois da migração do core",
                    r["cdEmail"],
                )
            self.conc.alerta(
                "pendencias",
                "E-mail SMTP NÃO migrado: a tabela config_email do core não existe no destino. Reexecutar o ETL (idempotente) após a migração do core.",
            )
            linha.destino = 0
            return

        def col(*nomes: str):
            return next((n for n in nomes if n in t.c), None)

        mapa = {
            "host": col("host", "smtp_host"),
            "porta": col("porta", "smtp_porta"),
            "usuario": col("usuario", "smtp_usuario"),
            "senha": col("senha_cifrado", "smtp_senha_cifrado", "senha_cifrada", "smtp_senha_cifrada"),
            "tls": col("usar_tls", "use_tls", "tls"),
            "remetente": col("remetente", "remetente_email", "de_email"),
            "ativo": col("ativo"),
        }
        faltam = [k for k in ("host", "senha") if mapa[k] is None]
        if faltam:
            for r in rows:
                linha.adiar(
                    f"config_email do destino sem coluna esperada ({', '.join(faltam)}): carga adiada", r["cdEmail"]
                )
            self.conc.alerta("pendencias", f"E-mail SMTP NÃO migrado: colunas ausentes em config_email ({faltam}).")
            linha.destino = 0
            return
        # idempotência: sem coluna de código legado, só carrega se o destino estiver vazio
        if conn.execute(select(func.count()).select_from(t)).scalar_one() > 0:
            linha.ja_existentes = len(rows)
            linha.destino = len(rows)
            linha.informativo = True
            return
        for r in rows:
            senha = self.cif.cifrar(r["senha"])
            ct = t.c[mapa["senha"]]
            valor_senha = senha.encode() if senha and "BLOB" in str(ct.type).upper() else senha
            valores = {mapa["host"]: r["host"], mapa["senha"]: valor_senha}
            for k, v in (
                ("porta", r["porta"]),
                ("usuario", r["usuario"]),
                ("tls", tf.booleano(r["use_tls"], True)),
                ("remetente", r["remetente"]),
                ("ativo", tf.booleano(r["ativo"], True)),
            ):
                if mapa[k]:
                    valores[mapa[k]] = v
            self._inserir_core(conn, "config_email", valores)
            linha.carregados += 1
        linha.destino = conn.execute(select(func.count()).select_from(t)).scalar_one()
        linha.informativo = True

    def _comunicacao(self) -> None:
        def mapper_msg(r: dict) -> dict:
            d, ok = tf.como_enum(r["direcao"], DirecaoMensagem, DirecaoMensagem.enviada)
            if not ok:
                self._nota("corrigir", "direção desconhecida: enviada", r["id"])
            return {
                "aluno_id": self._fk(
                    "core_aluno", r["aluno_id"], obrigatorio=True, motivo="aluno inexistente (FK órfã)"
                ),
                "contrato_id": self._fk("core_contrato", r["contrato_id"], obrigatorio=False),
                "tipo": r["tipo"] or "manual",
                "direcao": d,
                "telefone": tf.texto(r["telefone"]),
                "mensagem": r["mensagem"] or "",
                "status": r["status"] or "sent",
                "resposta_payload": tf.texto(r["response_payload"]),
                "enviado_em": tf.como_instante(r["enviado_em"]) or self._agora,
            }

        self._carregar(
            "whatsapp_mensagem",
            "core_alunowhatsappmessage",
            "whatsapp_mensagem",
            chave=lambda r: r["id"],
            mapper=mapper_msg,
        )

        def mapper_log(r: dict) -> dict:
            return {
                "tipo": r["tipo"],
                "dedupe_key": r["dedupe_key"],
                "unidade_id": self._fk("core_unidade", r["unidade_id"], obrigatorio=False),
                "aluno_id": self._fk("core_aluno", r["aluno_id"], obrigatorio=False),
                "profissional_id": self._fk("core_profissional", r["profissional_id"], obrigatorio=False),
                "contrato_id": self._fk("core_contrato", r["contrato_id"], obrigatorio=False),
                "data_referencia": tf.como_data(r["data_referencia"]),
                "telefone": tf.texto(r["telefone"]),
                "mensagem": r["mensagem"] or "",
                "status": r["status"] or "sent",
                "resposta_payload": tf.texto(r["response_payload"]),
                "enviado_em": tf.como_instante(r["enviado_em"]) or self._agora,
            }

        self._carregar(
            "whatsapp_agendamento_log",
            "core_whatsappagendamentolog",
            "whatsapp_agendamento_log",
            chave=lambda r: r["id"],
            mapper=mapper_log,
        )
        otp = self.fonte.linhas("core_alunoappcodigo")
        linha = self.conc.tabela("app_codigo", origem=len(otp))
        for r in otp:
            linha.descartar("código OTP efêmero (expira em minutos; o app emite códigos novos)", r["id"])
        linha.destino = self.conn_count("app_codigo")

    def conn_count(self, nome: str) -> int:
        return self._conn.execute(select(func.count()).select_from(self.T(nome))).scalar_one()

    # ----------------------------------------------------------------------------------- contadores
    def _contadores(self) -> None:
        conn = self._conn
        ct = self.T("contador_codigo")
        for nome in (
            "aluno",
            "contrato",
            "plano",
            "profissional",
            "unidade",
            "tipo_servico",
            "profissao",
            "fornecedor",
            "categoria",
            "subcategoria",
            "conta_bancaria",
            "conta_pagar",
            "modelo_contrato",
            "modelo_evolucao",
            "termo_uso",
            "aula_avulsa",
            "aula_avaliativa",
            "aluno_documento",
            "horario_studio",
            "aluno_endereco",
        ):
            t = self.T(nome)
            maximo = conn.execute(select(func.max(t.c.codigo_legado))).scalar() or 0
            atual = conn.execute(select(ct.c.ultimo).where(ct.c.nome == nome)).scalar()
            if atual is None:
                conn.execute(insert(ct).values(nome=nome, ultimo=maximo))
                self.conc.alerta("contadores", f"{nome}: próximo código = {maximo + 1}")
            elif atual < maximo:
                conn.execute(update(ct).where(ct.c.nome == nome).values(ultimo=maximo))
                self.conc.alerta("contadores", f"{nome}: ajustado, próximo código = {maximo + 1}")

    # ----------------------------------------------------------------------------------- verificação final
    def _soma_sql(self, conn: Connection, nome: str, coluna: str, **filtros: Any) -> Decimal:
        t = self.T(nome)
        q = select(func.coalesce(func.sum(t.c[coluna]), 0)).where(t.c.codigo_legado.is_not(None))
        for k, v in filtros.items():
            q = q.where(t.c[k] == v)
        return Decimal(str(round(float(conn.execute(q).scalar()), 2))).quantize(Decimal("0.01"))

    @staticmethod
    def _soma_py(rows: list[dict], campo: str, filtro: Callable[[dict], bool] | None = None) -> Decimal:
        return sum(
            (tf.dinheiro(r[campo]) or Decimal("0") for r in rows if filtro is None or filtro(r)), Decimal("0.00")
        )

    def _verificar(self) -> None:
        conn = self._conn_unica if self.simular else self.engine.connect()
        try:
            self._verificar_com(conn)
        finally:
            if not self.simular:
                conn.close()

    def _verificar_com(self, conn: Connection) -> None:
        c = self.conc
        F = self.fonte

        def soma(
            nome: str,
            tabela_origem: str,
            rotulo: str,
            destino: str,
            campo_origem: str,
            coluna: str,
            bucket: Callable[[dict], bool] | None = None,
            **filtro_dest: Any,
        ) -> None:
            total = self._soma_py(F.linhas(tabela_origem), campo_origem, bucket)
            migradas = self._soma_py(self.ok_src.get(rotulo, []), campo_origem, bucket)
            c.somas.append(Soma(nome, total, total - migradas, self._soma_sql(conn, destino, coluna, **filtro_dest)))

        soma("plano.valor", "core_plano", "plano", "plano", "valor", "valor")
        soma("contrato.valor_total", "core_contrato", "contrato", "contrato", "valor_total", "valor_total")
        soma("contrato.valor_parcela", "core_contrato", "contrato", "contrato", "valor_parcela", "valor_parcela")
        soma("aula_avulsa.valor_total", "core_aulaavulsa", "aula_avulsa", "aula_avulsa", "valor_total", "valor_total")
        soma("conta_receber (todas)", "core_contasreceber", "conta_receber", "conta_receber", "valor", "valor")
        for novo, antigos in (
            (StatusReceber.ABERTO, ("ABERTO", "ATRASADO")),
            (StatusReceber.PAGO, ("PAGO",)),
            (StatusReceber.CANCELADO, ("CANCELADO",)),
        ):
            soma(
                f"conta_receber {novo.value}" + (" (inclui ATRASADO gravado)" if novo == StatusReceber.ABERTO else ""),
                "core_contasreceber",
                "conta_receber",
                "conta_receber",
                "valor",
                "valor",
                bucket=lambda r, a=antigos: (r["status"] or "ABERTO").upper() in a,
                status=novo,
            )
        soma("conta_pagar (todas)", "core_contaspagar", "conta_pagar", "conta_pagar", "valor", "valor")
        for novo, antigos in (
            (StatusPagar.AGENDADO, ("AGENDADO", "ATRASADO")),
            (StatusPagar.PAGO, ("PAGO",)),
            (StatusPagar.CANCELADO, ("CANCELADO",)),
        ):
            soma(
                f"conta_pagar {novo.value}" + (" (inclui ATRASADO gravado)" if novo == StatusPagar.AGENDADO else ""),
                "core_contaspagar",
                "conta_pagar",
                "conta_pagar",
                "valor",
                "valor",
                bucket=lambda r, a=antigos: (r["status"] or "AGENDADO").upper() in a,
                status=novo,
            )
        for tp in TipoMovimento:
            soma(
                f"movimento_conta {tp.value}",
                "core_movimentoconta",
                "movimento_conta",
                "movimento_conta",
                "valor",
                "valor",
                bucket=lambda r, v=tp.value: (r["tipo"] or "").upper() == v,
                tipo=tp,
            )
        soma(
            "conta_bancaria.saldo_inicial",
            "core_contabancaria",
            "conta_bancaria",
            "conta_bancaria",
            "saldo_inicial",
            "saldo_inicial",
        )

        # contador de vagas confere com as reservas RESERVADA
        s, rs = self.T("aula_sessao"), self.T("reserva")
        ativas = (
            select(func.count())
            .select_from(rs)
            .where(rs.c.aula_sessao_id == s.c.id, rs.c.status == StatusReserva.RESERVADA)
            .scalar_subquery()
        )
        erradas = conn.execute(select(func.count()).select_from(s).where(s.c.reservas_ativas != ativas)).scalar_one()
        if erradas:
            c.alerta(
                "divergencia", f"{erradas} sessão(ões) com reservas_ativas diferente da contagem de reservas RESERVADA."
            )

        # FKs órfãs no destino
        for t in Base.metadata.sorted_tables:
            for fk in t.foreign_key_constraints:
                pai = list(fk.elements)[0].column
                if pai.table.name not in {x.name for x in Base.metadata.sorted_tables} or not inspect(conn).has_table(
                    pai.table.name
                ):
                    continue
                col = t.c[fk.columns[0].name]
                n = conn.execute(
                    select(func.count())
                    .select_from(t.outerjoin(pai.table, col == pai))
                    .where(col.is_not(None), pai.is_(None))
                ).scalar_one()
                if n:
                    c.alerta(
                        "divergencia", f"FK órfã no destino: {t.name}.{col.name} -> {pai.table.name} ({n} linha(s))."
                    )

        self._amostrar(conn)

    def _amostrar(self, conn: Connection) -> None:
        rng = random.Random(self.semente_amostra)
        pool = [
            a
            for a in self.amostras
            if a[0]
            in {
                "aluno",
                "contrato",
                "conta_receber",
                "conta_pagar",
                "reserva",
                "aula_sessao",
                "plano",
                "aluno_documento",
                "movimento_conta",
                "evolucao",
                "whatsapp_mensagem",
                "profissional",
            }
        ]
        por_tabela: dict[str, list] = defaultdict(list)
        for a in pool:
            por_tabela[a[0]].append(a)
        for lista in por_tabela.values():
            rng.shuffle(lista)
        escolhidas = []  # distribui a amostra entre as tabelas (rodízio), em vez de deixar o acaso concentrar numa só
        nomes = sorted(por_tabela)
        while len(escolhidas) < min(self.tamanho_amostra, len(pool)):
            for nome in nomes:
                if por_tabela[nome] and len(escolhidas) < self.tamanho_amostra:
                    escolhidas.append(por_tabela[nome].pop())
        self._silencioso = True
        try:
            for rotulo, destino, chave, linha_src, mapper in escolhidas:
                t = self.T(destino)
                real = conn.execute(select(t).where(t.c.codigo_legado == chave)).mappings().first()
                esperado = mapper(linha_src)
                dif: dict[str, str] = {}
                if real is None:
                    dif["_linha"] = "não encontrada no destino"
                else:
                    for campo, v in esperado.items():
                        if campo == "reservas_ativas":  # derivado: conferido à parte contra as reservas
                            continue
                        r = real[campo]
                        if isinstance(v, Decimal) or isinstance(r, Decimal) or isinstance(r, float):
                            iguais = (
                                r is not None
                                and v is not None
                                and Decimal(str(r)).quantize(Decimal("0.01"))
                                == Decimal(str(v)).quantize(Decimal("0.01"))
                            )
                            iguais = iguais or (r is None and v is None)
                        else:
                            iguais = r == v
                        if not iguais:
                            dif[campo] = f"esperado {v!r}, destino {r!r}"
                self.conc.amostra.append({"tabela": rotulo, "chave": chave, "campos": len(esperado), "diferencas": dif})
        finally:
            self._silencioso = False

    def _finalizar_midia(self) -> None:
        m, c = self.midia, self.conc
        if not m.ativa:
            c.alerta(
                "pendencias",
                f"Mídia NÃO verificada/copiada (informe --midia-origem e --midia-destino). {len(m.itens)} arquivo(s) referenciado(s) no banco.",
            )
            return
        c.alerta(
            "info",
            f"Mídia: {len(m.itens)} arquivo(s) referenciados; copiados {m.copiados}; já idênticos no destino {m.ja_iguais}; ausentes na origem {len(m.ausentes)}"
            + ("; SIMULAÇÃO: nada copiado." if self.simular else "."),
        )
        for a in m.ausentes:
            c.alerta("midia_ausente", a)
        for a in m.divergentes:
            c.alerta("midia_divergente", a)
            c.alerta("divergencia", f"Mídia divergente: {a['arquivo']} ({a['motivo']})")
