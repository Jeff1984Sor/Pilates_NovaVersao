"""Receita Saúde (R8): configuração, por aluno e em lote. Gerar/liberar são POST (nunca GET)."""

from __future__ import annotations

from datetime import date

from fastapi.responses import Response

from app.core.deps import Ctx
from app.core.schemas import Mensagem
from app.modules.alunos.models import Aluno
from app.modules.financeiro import recibos_saude as srv
from app.modules.financeiro.rotas_base import anexo, novo_router
from app.modules.financeiro.schemas import (
    ContasIdsIn,
    GerarLoteIn,
    LoteOut,
    PagadorIn,
    ReceitaSaudeConfigIn,
    ReceitaSaudeConfigOut,
    RecibosAlunoOut,
)
from app.modules.financeiro.servico import ErroDeNegocio

router = novo_router(prefix="/receita-saude", tags=["financeiro: receita saúde"])


def _aluno(db, aluno_id: int) -> Aluno:
    a = db.get(Aluno, aluno_id)
    if not a:
        raise ErroDeNegocio("Aluno não encontrado.", 404)
    return a


# ------------------------------------------------------------------------------------------------ configuração
@router.get("/config", response_model=ReceitaSaudeConfigOut)
def ver_config(ctx: Ctx):
    return srv.config_out(ctx.db)


@router.put("/config", response_model=ReceitaSaudeConfigOut)
def salvar_config(dados: ReceitaSaudeConfigIn, ctx: Ctx):
    cfg, antes = srv.salvar_config(ctx.db, dados)
    depois = {"cpf_profissional": cfg.cpf_profissional, "registro_profissional": cfg.registro_profissional,
              "codigo_ocupacao": cfg.codigo_ocupacao, "descricao_padrao": cfg.descricao_padrao}
    ctx.auditar("configurar", "receita_saude_config", cfg.id, "Salvou os dados do profissional do Receita Saúde",
                antes=antes, depois=depois)
    ctx.db.commit()
    return srv.config_out(ctx.db)


# --------------------------------------------------------------------------------------------------- por aluno
@router.get("/alunos/{aluno_id:int}", response_model=RecibosAlunoOut)
def recibos_do_aluno(aluno_id: int, ctx: Ctx):
    return srv.recibos_do_aluno(ctx.db, _aluno(ctx.db, aluno_id))


@router.put("/alunos/{aluno_id:int}/pagador", response_model=RecibosAlunoOut)
def definir_pagador(aluno_id: int, dados: PagadorIn, ctx: Ctx):
    """CPF de quem paga (quando não é o aluno). Vazio volta a ser o próprio aluno."""
    aluno = _aluno(ctx.db, aluno_id)
    antes = aluno.cpf_pagador_recibo
    novo = srv.definir_pagador(ctx.db, aluno, dados.cpf)
    ctx.auditar("definir_pagador", "aluno", aluno.id, "Alterou o CPF do pagador do recibo",
                antes={"cpf_pagador_recibo": antes}, depois={"cpf_pagador_recibo": novo})
    ctx.db.commit()
    return srv.recibos_do_aluno(ctx.db, aluno)


@router.post("/alunos/{aluno_id:int}/arquivo")
def gerar_do_aluno(aluno_id: int, dados: ContasIdsIn, ctx: Ctx) -> Response:
    """CSV do Receita Saúde com os pagamentos marcados. Tudo-ou-nada; marca `recibo_saude_gerado_em`."""
    aluno = _aluno(ctx.db, aluno_id)
    nome, conteudo, contas = srv.gerar_arquivo_do_aluno(ctx.db, aluno, dados.conta_ids)
    ctx.auditar("gerar_arquivo", "receita_saude", aluno.id,
                f"Gerou arquivo do Receita Saúde ({len(contas)} pagamento(s)) do aluno {aluno.nome}",
                depois={"conta_ids": [c.id for c in contas]})
    ctx.db.commit()
    return anexo(conteudo, nome, "text/csv; charset=utf-8")


@router.post("/alunos/{aluno_id:int}/liberar", response_model=Mensagem)
def liberar_do_aluno(aluno_id: int, dados: ContasIdsIn, ctx: Ctx):
    aluno = _aluno(ctx.db, aluno_id)
    contas = srv.liberar_do_aluno(ctx.db, aluno, dados.conta_ids)
    ctx.auditar("liberar", "receita_saude", aluno.id, f"Liberou {len(contas)} pagamento(s) para gerar o arquivo de novo",
                depois={"conta_ids": [c.id for c in contas]})
    ctx.db.commit()
    return Mensagem(mensagem=f"{len(contas)} pagamento(s) liberado(s) para gerar o arquivo de novo.")


# ------------------------------------------------------------------------------------------------------ em lote
@router.get("/lote", response_model=LoteOut)
def analisar_lote(ctx: Ctx, de: date, ate: date):
    """Pagamentos do período (por data de pagamento) de TODOS os alunos, com os problemas de cada linha."""
    return srv.analisar_lote(ctx.db, de, ate)


@router.post("/lote/arquivo")
def gerar_lote(dados: GerarLoteIn, ctx: Ctx) -> Response:
    """Gera o lote: um CSV (até 1000 linhas, um ano) ou um ZIP com vários. Tudo-ou-nada em todo o lote."""
    r = srv.gerar_lote(ctx.db, dados.de, dados.ate, dados.conta_ids)
    ctx.auditar("gerar_arquivo_lote", "receita_saude", None,
                f"Gerou {r.quantidade_arquivos} arquivo(s) do Receita Saúde com {r.quantidade_linhas} pagamento(s) "
                f"({dados.de:%d/%m/%Y} a {dados.ate:%d/%m/%Y})",
                depois={"conta_ids": r.conta_ids})
    ctx.db.commit()
    resp = anexo(r.conteudo, r.nome, r.media_type)
    resp.headers["X-Arquivos"] = str(r.quantidade_arquivos)
    resp.headers["X-Linhas"] = str(r.quantidade_linhas)
    return resp


@router.post("/lote/liberar", response_model=Mensagem)
def liberar_lote(dados: ContasIdsIn, ctx: Ctx):
    n = srv.liberar_lote(ctx.db, dados.conta_ids)
    ctx.auditar("liberar", "receita_saude", None, f"Liberou {n} pagamento(s) do lote para gerar o arquivo de novo",
                depois={"conta_ids": dados.conta_ids})
    ctx.db.commit()
    return Mensagem(mensagem=f"{n} pagamento(s) liberado(s) para gerar o arquivo de novo.")
