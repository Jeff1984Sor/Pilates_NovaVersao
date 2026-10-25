"""Peças comuns às telas de cadastro de fornecedores, categorias, horários, bloqueios, termos e modelos."""

from __future__ import annotations

from datetime import time
from typing import Annotated, Any

from fastapi import HTTPException, Query
from pydantic import AfterValidator
from pydantic_core import PydanticCustomError
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.schemas import Pagina, Schema

DIAS_SEMANA = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")  # 0 = segunda (weekday())


def regra(mensagem: str) -> PydanticCustomError:
    """Erro de validação de regra de negócio, com a mensagem limpa (sem o prefixo 'Value error, ')."""
    return PydanticCustomError("regra_negocio", mensagem)


def _aparar(v: str) -> str:
    return " ".join(v.split())


#: texto de uma linha: espaços repetidos/pontas removidos
Texto = Annotated[str, AfterValidator(_aparar)]


class PaginaContagens[T](Pagina[T]):
    """Página com as contagens dos chips de situação (calculadas SEM o filtro de situação, só com a busca)."""

    contagens: dict[str, int] = {}


class Pedido(Schema):
    """Parâmetros comuns de lista."""

    q: str = ""
    pagina: int = 1
    por_pagina: int = 20
    ordenar: str = ""
    direcao: str = "asc"


def parametros_lista(
    q: Annotated[str, Query(max_length=120)] = "",
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=200)] = 20,
    ordenar: Annotated[str, Query(max_length=30)] = "",
    direcao: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> Pedido:
    return Pedido(q=q.strip(), pagina=pagina, por_pagina=por_pagina, ordenar=ordenar, direcao=direcao)


def contem(coluna: Any, termo: str):
    """Filtro de busca (sem diferenciar maiúsculas); `%` e `_` digitados são tratados como texto."""
    t = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.lower(coluna).like(f"%{t.lower()}%", escape="\\")


def ordem(pedido: Pedido, colunas: dict[str, Any], padrao: str):
    """ORDER BY seguro: só colunas conhecidas; `id` desempata para a paginação ser estável."""
    col = colunas.get(pedido.ordenar) if pedido.ordenar else colunas[padrao]
    if col is None:
        raise HTTPException(422, f"Ordenação inválida: {pedido.ordenar}.")
    cabeca = col.desc() if pedido.direcao == "desc" else col.asc()
    return cabeca


def contar(db: Session, stmt: Select) -> int:
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0


def pagina_de(db: Session, stmt: Select, pedido: Pedido) -> tuple[list[Any], int]:
    total = contar(db, stmt)
    linhas = db.execute(stmt.limit(pedido.por_pagina).offset((pedido.pagina - 1) * pedido.por_pagina)).all()
    return list(linhas), total


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{n} {singular if n == 1 else plural_}"


def foto(obj: Any, excluir: tuple[str, ...] = ()) -> dict[str, Any]:
    """Foto de auditoria; campos de texto longo (HTML) entram só com o tamanho."""
    s = audit.snapshot(obj)
    for k, v in s.items():  # a auditoria do core não serializa `time`
        if isinstance(v, time):
            s[k] = v.strftime("%H:%M")
    for campo in excluir:
        if campo in s:
            s[f"{campo}_tamanho"] = len(s.pop(campo) or "")
    return s


def nao_encontrado(rotulo: str) -> HTTPException:
    return HTTPException(404, f"{rotulo} não encontrado(a).")
