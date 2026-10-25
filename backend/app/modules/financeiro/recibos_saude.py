"""Receita Saúde (R8): configuração do profissional, análise dos pagamentos e geração do CSV (por aluno e em lote).

As regras do arquivo (16 colunas, `;`, CRLF, ≤1000 linhas, mesmo ano, tudo-ou-nada) são de
`app.domain.receita_saude`; aqui só se adaptam os objetos do banco ao formato "duck typed" do domínio e se orquestra:
marcar `recibo_saude_gerado_em` (impede duplicidade), liberar para refazer e dividir o lote em arquivos.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import agora
from app.domain import receita_saude as rs
from app.domain.documentos import so_digitos, validar_cpf
from app.modules.alunos.models import Aluno
from app.modules.financeiro.models import ContaReceber, ReceitaSaudeConfig, StatusReceber
from app.modules.financeiro.schemas import (
    LoteOut,
    ReceitaSaudeConfigIn,
    ReceitaSaudeConfigOut,
    ReciboItemOut,
    RecibosAlunoOut,
)
from app.modules.financeiro.servico import ErroDeNegocio


class ErroReceita(ErroDeNegocio):
    """Falha de validação do arquivo: `erros` traz uma mensagem por problema (o arquivo NÃO é gerado)."""

    def __init__(self, erros: list[str], status: int = 422):
        resumo = erros[0] + (f" (e mais {len(erros) - 1} problema(s))" if len(erros) > 1 else "")
        super().__init__(resumo, status)
        self.erros = erros


# ---------------------------------------------------------------------------------------------- configuração
def obter_config(db: Session) -> ReceitaSaudeConfig | None:
    return db.scalar(select(ReceitaSaudeConfig).order_by(ReceitaSaudeConfig.id.desc()))


def config_out(db: Session) -> ReceitaSaudeConfigOut:
    cfg = obter_config(db)
    return ReceitaSaudeConfigOut(
        configurado=cfg is not None,
        cpf_profissional=cfg.cpf_profissional if cfg else None,
        registro_profissional=cfg.registro_profissional if cfg else None,
        codigo_ocupacao=cfg.codigo_ocupacao if cfg else "231",
        descricao_padrao=cfg.descricao_padrao if cfg else "Aulas de Pilates",
        ocupacoes=rs.OCUPACOES,
        problemas=rs.problemas_da_configuracao(cfg),
    )


def salvar_config(db: Session, dados: ReceitaSaudeConfigIn) -> tuple[ReceitaSaudeConfig, dict | None]:
    if dados.codigo_ocupacao not in rs.OCUPACOES:
        raise ErroDeNegocio("Código de ocupação inválido.", 422)
    cfg = obter_config(db)
    antes = None
    if cfg is None:
        cfg = ReceitaSaudeConfig(cpf_profissional=dados.cpf_profissional)
        db.add(cfg)
    else:
        antes = {"cpf_profissional": cfg.cpf_profissional, "registro_profissional": cfg.registro_profissional,
                 "codigo_ocupacao": cfg.codigo_ocupacao, "descricao_padrao": cfg.descricao_padrao}
    cfg.cpf_profissional = dados.cpf_profissional
    cfg.registro_profissional = (dados.registro_profissional or "").strip() or None
    cfg.codigo_ocupacao = dados.codigo_ocupacao
    cfg.descricao_padrao = dados.descricao_padrao
    db.flush()
    return cfg, antes


# ------------------------------------------------------------------------------------------------- adaptadores
def conta_dom(c: ContaReceber) -> SimpleNamespace:
    """ContaReceber -> objeto com os nomes que o domínio (portado do Django) espera."""
    return SimpleNamespace(
        id=c.id, status=c.status.value, dtPagamento=c.pagamento, dtVencimento=c.vencimento, valor=c.valor,
        descricao=c.descricao, competencia=c.competencia, recibo_saude_gerado_em=c.recibo_saude_gerado_em,
    )


def aluno_dom(a: Aluno) -> SimpleNamespace:
    return SimpleNamespace(dsCPF=a.cpf or "", sem_cpf=bool(a.sem_cpf), cpf_pagador_recibo=a.cpf_pagador_recibo or "")


def _item(c: ContaReceber, a: Aluno) -> ReciboItemOut:
    problemas = rs.problemas_da_conta(conta_dom(c), aluno_dom(a))
    return ReciboItemOut(
        conta_id=c.id, aluno_id=a.id, aluno_nome=a.nome, pagamento=c.pagamento, vencimento=c.vencimento,
        valor=c.valor, descricao=c.descricao, competencia=c.competencia, problemas=problemas,
        gerado_em=c.recibo_saude_gerado_em, pronto=not problemas and not c.recibo_saude_gerado_em,
    )


# ------------------------------------------------------------------------------------------------- por aluno
def recibos_do_aluno(db: Session, aluno: Aluno) -> RecibosAlunoOut:
    cfg = obter_config(db)
    contas = db.scalars(
        select(ContaReceber).where(ContaReceber.aluno_id == aluno.id, ContaReceber.status == StatusReceber.PAGO)
        .order_by(ContaReceber.pagamento.desc(), ContaReceber.id.desc())
    ).all()
    problemas_cfg = rs.problemas_da_configuracao(cfg)
    return RecibosAlunoOut(
        aluno_id=aluno.id, aluno_nome=aluno.nome, aluno_cpf=aluno.cpf, sem_cpf=aluno.sem_cpf,
        cpf_pagador_recibo=aluno.cpf_pagador_recibo, config_ok=not problemas_cfg, problemas_config=problemas_cfg,
        itens=[_item(c, aluno) for c in contas],
    )


def definir_pagador(db: Session, aluno: Aluno, cpf: str | None) -> str | None:
    digitos = so_digitos(cpf)
    if digitos and not validar_cpf(digitos):
        raise ErroDeNegocio("CPF do pagador inválido.", 422)
    aluno.cpf_pagador_recibo = digitos or None
    db.flush()
    return aluno.cpf_pagador_recibo


def _contas_do_aluno(db: Session, aluno: Aluno, ids: list[int]) -> list[ContaReceber]:
    contas = db.scalars(select(ContaReceber).where(ContaReceber.id.in_(ids), ContaReceber.aluno_id == aluno.id)).all()
    if len(contas) != len(set(ids)):
        raise ErroDeNegocio("Alguma conta marcada não pertence a este aluno.", 422)
    return sorted(contas, key=rs.chave_de_ordenacao)


def gerar_arquivo_do_aluno(db: Session, aluno: Aluno, ids: list[int]) -> tuple[str, bytes, list[ContaReceber]]:
    """CSV (nome, conteúdo, contas) com os pagamentos marcados. Tudo-ou-nada; recusa os já gerados (duplicidade)."""
    contas = _contas_do_aluno(db, aluno, ids)
    ja = rs.contas_ja_geradas(contas)
    if ja:
        raise ErroDeNegocio(rs.mensagem_recibos_ja_gerados(len(ja)))
    cfg = obter_config(db)
    conteudo, erros = rs.gerar_arquivo([(conta_dom(c), aluno_dom(aluno)) for c in contas], cfg)
    if erros:
        raise ErroReceita(erros)
    agora_ = agora()
    for c in contas:
        c.recibo_saude_gerado_em = agora_
    db.flush()
    return rs.nome_do_arquivo(aluno.nome, aluno.id, agora_.astimezone(_fuso())), conteudo.encode("utf-8"), contas


def _fuso():
    from app.domain.financeiro import FUSO_NEGOCIO

    return FUSO_NEGOCIO


def liberar(db: Session, contas: list[ContaReceber]) -> int:
    n = 0
    for c in contas:
        if c.recibo_saude_gerado_em:
            c.recibo_saude_gerado_em = None
            n += 1
    db.flush()
    return n


def liberar_do_aluno(db: Session, aluno: Aluno, ids: list[int]) -> list[ContaReceber]:
    contas = _contas_do_aluno(db, aluno, ids)
    liberar(db, contas)
    return contas


# ---------------------------------------------------------------------------------------------------- em lote
def dividir_em_arquivos(itens: list[tuple[ContaReceber, Aluno]]) -> list[list[tuple[ContaReceber, Aluno]]]:
    """Agrupa por ANO do pagamento (nunca mistura anos) e quebra em blocos de até 1000 linhas, na ordem do domínio."""
    por_ano: dict[int, list[tuple[ContaReceber, Aluno]]] = {}
    for c, a in sorted(itens, key=lambda x: rs.chave_de_ordenacao(conta_dom(x[0]))):
        por_ano.setdefault(c.pagamento.year, []).append((c, a))
    blocos = []
    for ano in sorted(por_ano):
        linhas = por_ano[ano]
        for i in range(0, len(linhas), rs.MAX_LINHAS):
            blocos.append(linhas[i:i + rs.MAX_LINHAS])
    return blocos


def _pares_pagos(db: Session, de: date, ate: date) -> list[tuple[ContaReceber, Aluno]]:
    stmt = (
        select(ContaReceber, Aluno).join(Aluno, Aluno.id == ContaReceber.aluno_id)
        .where(ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento >= de, ContaReceber.pagamento <= ate)
        .order_by(ContaReceber.pagamento, ContaReceber.id)
    )
    return [(c, a) for c, a in db.execute(stmt).all()]


def analisar_lote(db: Session, de: date, ate: date) -> LoteOut:
    if ate < de:
        raise ErroDeNegocio("A data final não pode ser anterior à inicial.", 422)
    if (ate - de).days > 800:
        raise ErroDeNegocio("Escolha um período de até ~2 anos.", 422)
    cfg = obter_config(db)
    problemas_cfg = rs.problemas_da_configuracao(cfg)
    pares = _pares_pagos(db, de, ate)
    itens = [_item(c, a) for c, a in pares]
    prontos = [i for i in itens if i.pronto]
    ids_prontos = {i.conta_id for i in prontos}
    previstos = len(dividir_em_arquivos([(c, a) for c, a in pares if c.id in ids_prontos]))
    return LoteOut(
        de=de, ate=ate, config_ok=not problemas_cfg, problemas_config=problemas_cfg, total=len(itens),
        prontos=len(prontos), com_problema=sum(1 for i in itens if i.problemas),
        ja_gerados=sum(1 for i in itens if i.gerado_em), arquivos_previstos=previstos, itens=itens,
    )


@dataclass
class ArquivoGerado:
    nome: str
    conteudo: bytes
    media_type: str
    quantidade_arquivos: int
    quantidade_linhas: int
    conta_ids: list[int]


def gerar_lote(db: Session, de: date, ate: date, conta_ids: list[int] | None) -> ArquivoGerado:
    """Gera o(s) arquivo(s) do lote. Tudo-ou-nada em TODO o lote: qualquer problema numa linha selecionada impede
    todos os arquivos e nada é marcado. Vários arquivos (mais de 1000 linhas ou mais de um ano) saem num ZIP."""
    if ate < de:
        raise ErroDeNegocio("A data final não pode ser anterior à inicial.", 422)
    cfg = obter_config(db)
    pares = _pares_pagos(db, de, ate)
    if conta_ids is None:  # padrão: tudo que está pronto
        escolhidos = [(c, a) for c, a in pares if _item(c, a).pronto]
    else:
        pedidos = set(conta_ids)
        escolhidos = [(c, a) for c, a in pares if c.id in pedidos]
        if len(escolhidos) != len(pedidos):
            raise ErroDeNegocio("Alguma conta selecionada não é um pagamento do período informado.", 422)
    if not escolhidos:
        raise ErroReceita(["Nenhum pagamento pronto para gerar neste período."])
    erros = list(rs.problemas_da_configuracao(cfg))
    ja = rs.contas_ja_geradas([conta_dom(c) for c, _ in escolhidos])
    if ja:
        erros.append(rs.mensagem_recibos_ja_gerados(len(ja)))
    for c, a in escolhidos:
        for p in rs.problemas_da_conta(conta_dom(c), aluno_dom(a)):
            erros.append(f"{a.nome} - {c.vencimento:%d/%m/%Y} (R$ {rs.formatar_valor(c.valor)}): {p}")
    if erros:
        raise ErroReceita(erros)

    blocos = dividir_em_arquivos(escolhidos)
    arquivos: list[tuple[str, bytes]] = []
    for i, bloco in enumerate(blocos, start=1):
        conteudo, errs = rs.gerar_arquivo([(conta_dom(c), aluno_dom(a)) for c, a in bloco], cfg)
        if errs:  # não deve ocorrer depois da validação acima; segurança extra
            raise ErroReceita(errs)
        ano = bloco[0][0].pagamento.year
        arquivos.append((f"receita-saude-{ano}-parte-{i:02d}-de-{len(blocos):02d}.csv", conteudo.encode("utf-8")))

    agora_ = agora()
    for c, _ in escolhidos:
        c.recibo_saude_gerado_em = agora_
    db.flush()
    ids = [c.id for c, _ in escolhidos]
    if len(arquivos) == 1:
        nome, conteudo = arquivos[0]
        return ArquivoGerado(nome, conteudo, "text/csv; charset=utf-8", 1, len(escolhidos), ids)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in arquivos:
            z.writestr(nome, conteudo)
    return ArquivoGerado(f"receita-saude-lote-{de:%Y%m%d}-{ate:%Y%m%d}.zip", buf.getvalue(), "application/zip",
                         len(arquivos), len(escolhidos), ids)


def liberar_lote(db: Session, ids: list[int]) -> int:
    contas = db.scalars(select(ContaReceber).where(ContaReceber.id.in_(ids))).all()
    if len(contas) != len(set(ids)):
        raise ErroDeNegocio("Alguma conta informada não existe.", 404)
    return liberar(db, list(contas))

