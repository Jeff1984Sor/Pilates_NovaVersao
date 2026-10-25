"""Peças comuns dos cadastros-base: paginação com contagens, situação (ativos/inativos), vínculos para exclusão."""

from collections.abc import Callable, Sequence
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import Base
from app.core.deps import Ctx
from app.core.schemas import Pagina, Schema

Situacao = Literal["ativos", "inativos", "todos"]


class PaginaCad[T](Pagina[T]):
    """Página + contagem por situação (respeita a busca e os demais filtros, não a situação escolhida)."""

    contagens: dict[str, int] = {}


class VinculoOut(Schema):
    rotulo: str
    quantidade: int


class VinculosOut(Schema):
    total: int
    itens: list[VinculoOut]
    pode_excluir: bool
    pode_desativar: bool


# Nome legível dos registros que apontam para um cadastro (tabela -> (singular, plural)).
ROTULOS: dict[str, tuple[str, str]] = {
    "aluno": ("aluno", "alunos"),
    "aula_sessao": ("aula", "aulas"),
    "aula_avulsa": ("aula avulsa", "aulas avulsas"),
    "aula_avaliativa": ("aula avaliativa", "aulas avaliativas"),
    "reserva": ("reserva", "reservas"),
    "contrato": ("contrato", "contratos"),
    "plano": ("plano", "planos"),
    "horario_funcionamento": ("horário de funcionamento", "horários de funcionamento"),
    "horario_funcionamento_tipo_servico": ("horário de funcionamento", "horários de funcionamento"),
    "horario_studio": ("horário da grade", "horários da grade"),
    "bloqueio_agenda": ("bloqueio de agenda", "bloqueios de agenda"),
    "comissao": ("comissão", "comissões"),
    "conta_receber": ("conta a receber", "contas a receber"),
    "conta_pagar": ("conta a pagar", "contas a pagar"),
    "evolucao": ("evolução", "evoluções"),
    "avaliacao": ("avaliação", "avaliações"),
    "whatsapp_config": ("configuração de WhatsApp", "configurações de WhatsApp"),
}


def vinculos(db: Session, modelo: type[Base], registro_id: int) -> list[VinculoOut]:
    """Quantos registros de OUTRAS tabelas apontam para este cadastro (FK sem exclusão em cascata).

    Percorre o metadata (assim nenhuma tabela de outro módulo fica de fora quando for criada).
    """
    from app.modules import registrar_modelos

    registrar_modelos()
    alvo = modelo.__table__
    por_tabela: dict[Any, list[ColumnElement]] = {}
    for tabela in Base.metadata.sorted_tables:
        if tabela is alvo:
            continue
        for fk in tabela.foreign_keys:
            if fk.column.table is alvo and (fk.ondelete or "").upper() != "CASCADE":
                por_tabela.setdefault(tabela, []).append(fk.parent == registro_id)
    achados: list[VinculoOut] = []
    for tabela, condicoes in por_tabela.items():
        n = db.scalar(select(func.count()).select_from(tabela).where(or_(*condicoes))) or 0
        if n:
            sing, plur = ROTULOS.get(tabela.name, (tabela.name.replace("_", " "),) * 2)
            achados.append(VinculoOut(rotulo=sing if n == 1 else plur, quantidade=n))
    # agrupa rótulos repetidos (ex.: as duas tabelas de horário)
    soma: dict[str, int] = {}
    for a in achados:
        soma[a.rotulo] = soma.get(a.rotulo, 0) + a.quantidade
    return sorted((VinculoOut(rotulo=r, quantidade=q) for r, q in soma.items()), key=lambda v: -v.quantidade)


def resumo_vinculos(lista: Sequence[VinculoOut]) -> str:
    return ", ".join(f"{v.quantidade} {v.rotulo}" for v in lista)


def vinculos_out(db: Session, modelo: type[Base], registro_id: int, *, tem_ativo: bool = True) -> VinculosOut:
    lista = vinculos(db, modelo, registro_id)
    return VinculosOut(total=sum(v.quantidade for v in lista), itens=lista, pode_excluir=not lista, pode_desativar=tem_ativo)


def bloquear_se_vinculado(db: Session, modelo: type[Base], registro_id: int, o_que: str, *, tem_ativo: bool = True) -> None:
    """409 com mensagem clara quando há vínculos; sugere desativar quando o cadastro tem a situação ativo/inativo."""
    lista = vinculos(db, modelo, registro_id)
    if lista:
        dica = " Desative-o em vez de excluir." if tem_ativo else " Remova ou troque esses vínculos antes de excluir."
        raise HTTPException(status.HTTP_409_CONFLICT, f"Não é possível excluir {o_que}: ele está em uso por {resumo_vinculos(lista)}.{dica}")


def filtro_situacao(coluna_ativo, situacao: Situacao):
    if situacao == "ativos":
        return coluna_ativo.is_(True)
    if situacao == "inativos":
        return coluna_ativo.is_(False)
    return None


def contar_situacoes(db: Session, coluna_id, coluna_ativo, filtros: Sequence, joins: Callable | None = None) -> dict[str, int]:
    """{"ativos": n, "inativos": n, "todos": n} com os filtros (busca etc.) já aplicados, exceto a situação."""
    q = select(func.count(coluna_id).filter(coluna_ativo.is_(True)), func.count(coluna_id).filter(coluna_ativo.is_(False)))
    if joins:
        q = joins(q)
    if filtros:
        q = q.where(and_(*filtros))
    ativos, inativos = db.execute(q).one()
    return {"ativos": ativos, "inativos": inativos, "todos": ativos + inativos}


def like(termo: str) -> str:
    escapado = termo.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def ordenar_por(colunas: dict[str, Any], ordenar: str | None, direcao: str, padrao: str):
    """Coluna validada (nunca texto livre vindo do cliente) + ordem estável pelo id no desempate."""
    col = colunas.get(ordenar or padrao, colunas[padrao])
    return col.desc() if direcao == "desc" else col.asc()


def duplicado(db: Session, modelo, coluna_nome, nome: str, exceto_id: int | None = None) -> bool:
    q = select(modelo.id).where(func.lower(coluna_nome) == nome.strip().lower())
    if exceto_id:
        q = q.where(modelo.id != exceto_id)
    return db.scalar(q) is not None


def registrar_ativacao(
    router: APIRouter, *, modelo, entidade: str, rotulo: str, saida: Callable, modelo_saida, descricao_de: Callable = lambda o: o.nome
) -> None:
    """Acrescenta POST /{id}/ativar e /{id}/desativar (auditados) ao router.

    A permissão é a de edição (POST). `saida(db, obj)` monta a resposta.
    """
    def _alterar(ctx, registro_id: int, ativo: bool):
        obj = ctx.db.get(modelo, registro_id)
        if not obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{rotulo.capitalize()} não encontrado(a).")
        if obj.ativo != ativo:
            antes = audit.snapshot(obj)
            obj.ativo = ativo
            ctx.db.flush()
            a, d = audit.diff(antes, audit.snapshot(obj))
            ctx.auditar(f"{entidade}.{'ativar' if ativo else 'desativar'}", entidade, obj.id, descricao=descricao_de(obj),
                        antes=a, depois=d)
            ctx.db.commit()
        return saida(ctx.db, obj)

    @router.post("/{registro_id}/ativar", response_model=modelo_saida)
    def ativar(registro_id: int, ctx: Ctx):
        return _alterar(ctx, registro_id, True)

    @router.post("/{registro_id}/desativar", response_model=modelo_saida)
    def desativar(registro_id: int, ctx: Ctx):
        return _alterar(ctx, registro_id, False)
