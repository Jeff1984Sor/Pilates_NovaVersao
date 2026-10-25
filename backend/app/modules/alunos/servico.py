"""Regras de aplicação do cadastro de alunos (a rota só orquestra).

Regras de negócio puras vêm de `app.domain` (CPF, telefone). Serviços estáveis para outros módulos:
`obter_aluno`, `aluno_visivel`, `telefone_principal`, `telefones_do_aluno`, `quantidade_vinculos`.
"""

from __future__ import annotations

import base64
import hashlib
import html
import re
import time
from dataclasses import dataclass
from datetime import date

import httpx
from fastapi import HTTPException, status
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import audit, escopo, storage
from app.core.db import agora
from app.core.deps import Contexto
from app.domain.documentos import formatar_cpf, so_digitos, validar_cpf
from app.domain.telefone import normalizar_telefone_br
from app.modules.agenda.models import AulaAvaliativa, AulaAvulsa, AulaSessao, Reserva, StatusReserva
from app.modules.alunos import schemas as sc
from app.modules.alunos.models import (
    Aluno,
    AlunoDocumento,
    AlunoEndereco,
    AlunoTelefone,
    AppCodigo,
    OrigemDocumento,
    StatusAluno,
    WhatsappMensagem,
)
from app.modules.cadastros.models import Profissao, TermoUso, Unidade, proximo_codigo
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber

# ------------------------------------------------------------------------------------------------ armazenamento
CAT_ALUNOS = "alunos"  # fotos (alunos/foto/...) e assinaturas do termo (alunos/termo/...)
CAT_DOCUMENTOS = "documentos"  # documentos do aluno (mesma pasta usada pelo ETL)

storage.registrar_categoria(CAT_ALUNOS, "alunos.ver", storage.IMAGENS, 4)
storage.registrar_categoria(CAT_DOCUMENTOS, "alunos.ver", storage.DOCUMENTOS, 10)


def erro(codigo: int, mensagem: str) -> HTTPException:
    return HTTPException(codigo, mensagem)


# ------------------------------------------------------------------------------------------------ formatação
def mascarar_cpf(cpf: str | None) -> str | None:
    d = so_digitos(cpf)
    if len(d) != 11:
        return None
    return f"***.***.{d[6:9]}-{d[9:]}"


def formatar_telefone(canonico: str | None) -> str:
    d = so_digitos(canonico)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return canonico or ""


def foto_url(a: Aluno) -> str | None:
    if not storage.existe(a.foto_path):
        return None
    return f"/alunos/{a.id}/foto?v={storage.versao(a.foto_path)}"


# ------------------------------------------------------------------------------------------------ escopo (Professor)
def _alunos_do_profissional(ctx: Contexto) -> Select:
    """ids de alunos com reserva em aula do profissional do usuário (sem vínculo, nenhum)."""
    q = select(Reserva.aluno_id).join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
    return escopo.filtrar_proprias(ctx, q, AulaSessao.profissional_id)


def restringir(ctx: Contexto, consulta: Select) -> Select:
    if ctx.somente_proprias_aulas():
        consulta = consulta.where(Aluno.id.in_(_alunos_do_profissional(ctx)))
    return consulta


def aluno_visivel(ctx: Contexto, aluno_id: int) -> bool:
    if not ctx.somente_proprias_aulas():
        return True
    return ctx.db.scalar(select(Aluno.id).where(Aluno.id == aluno_id, Aluno.id.in_(_alunos_do_profissional(ctx)))) is not None


def obter_aluno(ctx: Contexto, aluno_id: int) -> Aluno:
    """Aluno ou 404 (também quando o Professor não tem reserva em aula dele: não revela que existe)."""
    a = ctx.db.get(Aluno, aluno_id)
    if not a or not aluno_visivel(ctx, aluno_id):
        raise erro(status.HTTP_404_NOT_FOUND, "Aluno não encontrado.")
    return a


def exigir_escrita(ctx: Contexto) -> None:
    if ctx.somente_proprias_aulas():
        raise erro(status.HTTP_403_FORBIDDEN, "Seu perfil de acesso não permite alterar o cadastro de alunos.")


# ------------------------------------------------------------------------------------------------ telefones
def telefones_do_aluno(db: Session, aluno_id: int) -> list[AlunoTelefone]:
    return list(db.scalars(select(AlunoTelefone).where(AlunoTelefone.aluno_id == aluno_id).order_by(AlunoTelefone.ordem, AlunoTelefone.id)))


def telefone_principal(db: Session, aluno_id: int) -> str | None:
    """Número canônico do telefone principal (ordem 1), usado no envio de WhatsApp."""
    return db.scalar(select(AlunoTelefone.numero).where(AlunoTelefone.aluno_id == aluno_id).order_by(AlunoTelefone.ordem, AlunoTelefone.id).limit(1))


def telefone_out(t: AlunoTelefone, principal: bool) -> sc.TelefoneOut:
    return sc.TelefoneOut(id=t.id, ordem=t.ordem, numero=t.numero, formatado=formatar_telefone(t.numero),
                          original=t.numero_original, principal=principal, whatsapp=t.numero)


def _sincronizar_telefones(db: Session, aluno: Aluno, itens: list[sc.TelefoneIn]) -> None:
    """Atualiza por id (NÃO apaga e recria): existentes mudam no lugar, novos entram, ausentes saem.
    A ordem da lista define `ordem`; o marcado como principal vai para a ordem 1."""
    atuais = {t.id: t for t in telefones_do_aluno(db, aluno.id)}
    vistos: set[str] = set()
    normalizados: list[tuple[sc.TelefoneIn, str]] = []
    for i, it in enumerate(itens, start=1):
        canon = normalizar_telefone_br(it.numero)
        if not canon:
            raise erro(422, f"Telefone {i} inválido: informe DDD e número (ex.: (11) 99999-0000).")
        if canon in vistos:
            raise erro(422, f"O telefone {formatar_telefone(canon)} está repetido.")
        vistos.add(canon)
        if it.id is not None and it.id not in atuais:
            raise erro(422, "Telefone não pertence a este aluno.")
        normalizados.append((it, canon))
    principais = [n for n in normalizados if n[0].principal]
    ordenados = principais[:1] + [n for n in normalizados if n not in principais[:1]]

    manter = {it.id for it, _ in ordenados if it.id is not None}
    for tid, t in list(atuais.items()):
        if tid not in manter:
            db.delete(t)
    db.flush()
    # evita colisão do índice único (aluno, número) quando dois telefones trocam de número entre si
    mudando = [(atuais[it.id], canon) for it, canon in ordenados if it.id is not None and atuais[it.id].numero != canon]
    for t, _ in mudando:
        t.numero = f"tmp-{t.id}"
    if mudando:
        db.flush()
    for ordem, (it, canon) in enumerate(ordenados, start=1):
        if it.id is not None:
            t = atuais[it.id]
            t.numero = canon
            t.ordem = ordem
            t.numero_original = it.numero.strip()[:30]
        else:
            db.add(AlunoTelefone(aluno_id=aluno.id, ordem=ordem, numero=canon, numero_original=it.numero.strip()[:30]))
    db.flush()


# ------------------------------------------------------------------------------------------------ endereço
def endereco_do_aluno(db: Session, aluno_id: int) -> AlunoEndereco | None:
    return db.scalar(select(AlunoEndereco).where(AlunoEndereco.aluno_id == aluno_id))


def _sincronizar_endereco(db: Session, aluno: Aluno, e: sc.EnderecoIn) -> None:
    atual = endereco_do_aluno(db, aluno.id)
    dados = e.model_dump()
    if not any(dados.values()):
        if atual:
            db.delete(atual)
        return
    cep = so_digitos(dados["cep"])
    if cep and len(cep) != 8:
        raise erro(422, "CEP inválido: informe 8 dígitos.")
    if atual is None:
        atual = AlunoEndereco(aluno_id=aluno.id, logradouro="", numero="", cidade="", bairro="")
        db.add(atual)
    atual.cep = cep or None
    atual.logradouro = dados["logradouro"] or ""
    atual.numero = dados["numero"] or ""
    atual.bairro = dados["bairro"] or ""
    atual.cidade = dados["cidade"] or ""


# ------------------------------------------------------------------------------------------------ validações do cadastro
def _normalizar_cpf_aluno(db: Session, dados: sc.AlunoIn, atual: Aluno | None) -> tuple[str | None, bool]:
    """(cpf só dígitos ou None, sem_cpf). Valida dígitos e unicidade."""
    sem_cpf = dados.sem_cpf if dados.sem_cpf is not None else (atual.sem_cpf if atual else False)
    if sem_cpf:
        return None, True
    if "cpf" in dados.model_fields_set or atual is None:
        d = so_digitos(dados.cpf)
        if not d:
            raise erro(422, "Informe o CPF ou marque \"Aluno sem CPF\".")
        if not validar_cpf(d):
            raise erro(422, "CPF inválido.")
    else:
        d = atual.cpf if atual else None
        if not d:
            raise erro(422, "Informe o CPF ou marque \"Aluno sem CPF\".")
    outro = db.scalar(select(Aluno).where(Aluno.cpf == d, Aluno.id != (atual.id if atual else 0)))
    if outro:
        raise erro(409, f"Já existe um aluno com este CPF: {outro.nome}.")
    return d, False


def _validar_referencias(db: Session, dados: sc.AlunoIn) -> None:
    if dados.unidade_id is not None and not db.get(Unidade, dados.unidade_id):
        raise erro(422, "Unidade não encontrada.")
    if dados.profissao_id is not None and not db.get(Profissao, dados.profissao_id):
        raise erro(422, "Profissão não encontrada.")
    if dados.termo_uso_id is not None and not db.get(TermoUso, dados.termo_uso_id):
        raise erro(422, "Termo de uso não encontrado.")


def _cpf_pagador(valor: str | None) -> str | None:
    d = so_digitos(valor)
    if not d:
        return None
    if not validar_cpf(d):
        raise erro(422, "CPF de quem paga é inválido.")
    return d


_CAMPOS_SIMPLES = ("nome", "rg", "email", "data_nascimento", "estado_civil", "profissao_id", "unidade_id", "termo_uso_id",
                   "status", "autoriza_imagem")


def _foto_da_auditoria(db: Session, a: Aluno) -> dict:
    snap = audit.snapshot(a)
    snap["telefones"] = [t.numero for t in telefones_do_aluno(db, a.id)] if a.id else []
    e = endereco_do_aluno(db, a.id) if a.id else None
    snap["endereco"] = audit.snapshot(e) if e else None
    return snap


def criar_aluno(ctx: Contexto, dados: sc.AlunoIn) -> Aluno:
    exigir_escrita(ctx)
    db = ctx.db
    if not dados.nome:
        raise erro(422, "Informe o nome do aluno.")
    if dados.unidade_id is None:
        raise erro(422, "Escolha a unidade do aluno.")
    _validar_referencias(db, dados)
    cpf, sem_cpf = _normalizar_cpf_aluno(db, dados, None)
    a = Aluno(
        nome=dados.nome, cpf=cpf, sem_cpf=sem_cpf, unidade_id=dados.unidade_id,
        status=dados.status or StatusAluno.ATIVO, autoriza_imagem=bool(dados.autoriza_imagem),
        cpf_pagador_recibo=_cpf_pagador(dados.cpf_pagador_recibo),
        codigo_legado=proximo_codigo(db, "aluno"),
    )
    for campo in ("rg", "email", "data_nascimento", "estado_civil", "profissao_id", "termo_uso_id"):
        setattr(a, campo, getattr(dados, campo))
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise erro(409, "Já existe um aluno com este CPF.") from None
    if dados.telefones:
        _sincronizar_telefones(db, a, dados.telefones)
    if dados.endereco:
        _sincronizar_endereco(db, a, dados.endereco)
    db.flush()
    ctx.auditar("aluno.criar", "aluno", a.id, descricao=f"Aluno {a.nome} cadastrado", depois=_foto_da_auditoria(db, a))
    commit_ou_conflito(db)
    return a


def atualizar_aluno(ctx: Contexto, a: Aluno, dados: sc.AlunoIn) -> Aluno:
    exigir_escrita(ctx)
    db = ctx.db
    enviados = dados.model_fields_set
    antes = _foto_da_auditoria(db, a)
    _validar_referencias(db, dados)
    if "nome" in enviados and not dados.nome:
        raise erro(422, "Informe o nome do aluno.")
    if "unidade_id" in enviados and dados.unidade_id is None:
        raise erro(422, "Escolha a unidade do aluno.")
    if "cpf" in enviados or "sem_cpf" in enviados:
        a.cpf, a.sem_cpf = _normalizar_cpf_aluno(db, dados, a)
    for campo in _CAMPOS_SIMPLES:
        if campo in enviados:
            valor = getattr(dados, campo)
            if campo in ("status", "autoriza_imagem") and valor is None:
                continue
            setattr(a, campo, valor)
    if "cpf_pagador_recibo" in enviados:
        a.cpf_pagador_recibo = _cpf_pagador(dados.cpf_pagador_recibo)
    db.flush()
    if dados.telefones is not None:
        _sincronizar_telefones(db, a, dados.telefones)
    if dados.endereco is not None:
        _sincronizar_endereco(db, a, dados.endereco)
    db.flush()
    depois = _foto_da_auditoria(db, a)
    ant, dep = audit.diff(antes, depois)
    ctx.auditar("aluno.alterar", "aluno", a.id, descricao=f"Cadastro de {a.nome} alterado", antes=ant, depois=dep)
    commit_ou_conflito(db)
    return a


def commit_ou_conflito(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig).lower()
        if "cpf" in msg or "unique" in msg:
            raise erro(409, "Já existe um aluno com este CPF ou telefone repetido.") from None
        raise


def mudar_status(ctx: Contexto, a: Aluno, novo: StatusAluno) -> Aluno:
    exigir_escrita(ctx)
    if a.status == novo:
        return a
    antes = a.status.value
    a.status = novo
    acao = "aluno.inativar" if novo == StatusAluno.INATIVO else "aluno.reativar"
    ctx.auditar(acao, "aluno", a.id, descricao=f"{a.nome}: {antes} -> {novo.value}", antes={"status": antes}, depois={"status": novo.value})
    ctx.db.commit()
    return a


# ------------------------------------------------------------------------------------------------ vínculos e exclusão
def quantidade_vinculos(db: Session, aluno_id: int) -> sc.Vinculos:
    def conta(modelo) -> int:
        return db.scalar(select(func.count()).select_from(modelo).where(modelo.aluno_id == aluno_id)) or 0

    v = sc.Vinculos(contratos=conta(Contrato), reservas=conta(Reserva), aulas_avulsas=conta(AulaAvulsa),
                    aulas_avaliativas=conta(AulaAvaliativa), contas_receber=conta(ContaReceber))
    v.total = v.contratos + v.reservas + v.aulas_avulsas + v.aulas_avaliativas + v.contas_receber
    v.pode_excluir = v.total == 0
    return v


def excluir_aluno(ctx: Contexto, a: Aluno) -> None:
    """Só exclui sem vínculos (contratos, aulas, cobranças). Com vínculos: 409 orientando a inativar."""
    exigir_escrita(ctx)
    db = ctx.db
    v = quantidade_vinculos(db, a.id)
    if not v.pode_excluir:
        partes = [f"{n} {rot}" for n, rot in ((v.contratos, "contrato(s)"), (v.reservas, "reserva(s) de aula"),
                                               (v.aulas_avulsas, "aula(s) avulsa(s)"), (v.aulas_avaliativas, "aula(s) avaliativa(s)"),
                                               (v.contas_receber, "cobrança(s)")) if n]
        raise erro(409, f"Este aluno tem histórico ({', '.join(partes)}) e não pode ser excluído. Inative o aluno para tirá-lo das listas.")
    arquivos = [a.foto_path, a.termo_assinatura_path]
    docs = list(db.scalars(select(AlunoDocumento).where(AlunoDocumento.aluno_id == a.id)))
    arquivos += [d.arquivo_path for d in docs]
    snap = _foto_da_auditoria(db, a)
    for modelo in (AlunoDocumento, AlunoTelefone, AlunoEndereco, WhatsappMensagem, AppCodigo):
        for obj in db.scalars(select(modelo).where(modelo.aluno_id == a.id)):
            db.delete(obj)
    db.flush()
    db.delete(a)
    ctx.auditar("aluno.excluir", "aluno", a.id, descricao=f"Aluno {a.nome} excluído", antes=snap)
    db.commit()
    for rel in arquivos:
        try:
            storage.remover(rel)
        except storage.ArquivoInvalido:
            pass


# ------------------------------------------------------------------------------------------------ saída
def _aulas_reservadas(db: Session, aluno_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Reserva).where(Reserva.aluno_id == aluno_id, Reserva.status == StatusReserva.RESERVADA)) or 0


def aluno_out(ctx: Contexto, a: Aluno) -> sc.AlunoOut:
    db = ctx.db
    tels = telefones_do_aluno(db, a.id)
    e = endereco_do_aluno(db, a.id)
    un = db.get(Unidade, a.unidade_id)
    prof = db.get(Profissao, a.profissao_id) if a.profissao_id else None
    return sc.AlunoOut(
        id=a.id, codigo=a.codigo_legado, nome=a.nome, cpf=formatar_cpf(a.cpf) if a.cpf else None, cpf_mascarado=mascarar_cpf(a.cpf),
        sem_cpf=a.sem_cpf, rg=a.rg, email=a.email, data_nascimento=a.data_nascimento, estado_civil=a.estado_civil,
        profissao_id=a.profissao_id, profissao_nome=prof.nome if prof else None, unidade_id=a.unidade_id,
        unidade_nome=un.nome if un else None, termo_uso_id=a.termo_uso_id, status=a.status, autoriza_imagem=a.autoriza_imagem,
        cpf_pagador_recibo=formatar_cpf(a.cpf_pagador_recibo) if a.cpf_pagador_recibo else None, foto_url=foto_url(a),
        telefones=[telefone_out(t, i == 0) for i, t in enumerate(tels)],
        endereco=sc.EnderecoOut(cep=e.cep, logradouro=e.logradouro, numero=e.numero, bairro=e.bairro, cidade=e.cidade) if e else None,
        termo_assinado_em=a.termo_assinado_em, criado_em=a.criado_em, atualizado_em=a.atualizado_em,
        aulas_reservadas=_aulas_reservadas(db, a.id), vinculos=quantidade_vinculos(db, a.id),
    )


def resumo_out(ctx: Contexto, a: Aluno) -> sc.AlunoResumo:
    un = ctx.db.get(Unidade, a.unidade_id)
    return sc.AlunoResumo(id=a.id, nome=a.nome, status=a.status, foto_url=foto_url(a), unidade_nome=un.nome if un else None)


# ------------------------------------------------------------------------------------------------ lista e busca
ORDENS = {
    "nome": Aluno.nome.asc(), "-nome": Aluno.nome.desc(), "codigo": Aluno.codigo_legado.asc(), "-codigo": Aluno.codigo_legado.desc(),
    "cadastro": Aluno.criado_em.asc(), "-cadastro": Aluno.criado_em.desc(), "status": Aluno.status.asc(),
}


def _condicao_busca(q: str):
    q = q.strip()
    d = so_digitos(q)
    conds = [Aluno.nome.ilike(f"%{q}%"), Aluno.rg.ilike(f"%{q}%")]
    if d:
        conds.append(Aluno.cpf.like(f"%{d}%"))
        conds.append(exists().where(AlunoTelefone.aluno_id == Aluno.id, AlunoTelefone.numero.like(f"%{d}%")))
        if len(d) <= 9:
            conds.append(Aluno.codigo_legado == int(d))
            conds.append(Aluno.id == int(d))
    return or_(*conds)


def contagens(ctx: Contexto) -> sc.Contagens:
    q = restringir(ctx, select(Aluno.status, func.count()).group_by(Aluno.status))
    n = {s: c for s, c in ctx.db.execute(q).all()}
    at, ina = n.get(StatusAluno.ATIVO, 0), n.get(StatusAluno.INATIVO, 0)
    return sc.Contagens(ativos=at, inativos=ina, todos=at + ina)


def listar(ctx: Contexto, *, q: str, situacao: str, ordem: str, pagina: int, por_pagina: int) -> sc.ListaAlunos:
    db = ctx.db
    base = restringir(ctx, select(Aluno))
    if situacao == "ativos":
        base = base.where(Aluno.status == StatusAluno.ATIVO)
    elif situacao == "inativos":
        base = base.where(Aluno.status == StatusAluno.INATIVO)
    if q.strip():
        base = base.where(_condicao_busca(q))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    ordenacao = ORDENS.get(ordem, ORDENS["nome"])
    linhas = list(db.scalars(base.order_by(ordenacao, Aluno.id).limit(por_pagina).offset((pagina - 1) * por_pagina)))
    ids = [a.id for a in linhas]
    reservadas = dict(db.execute(select(Reserva.aluno_id, func.count()).where(
        Reserva.aluno_id.in_(ids), Reserva.status == StatusReserva.RESERVADA).group_by(Reserva.aluno_id)).all()) if ids else {}
    principais = {}
    if ids:
        for t in db.scalars(select(AlunoTelefone).where(AlunoTelefone.aluno_id.in_(ids)).order_by(AlunoTelefone.ordem, AlunoTelefone.id)):
            principais.setdefault(t.aluno_id, t.numero)
    itens = [
        sc.AlunoLista(id=a.id, codigo=a.codigo_legado, nome=a.nome, cpf_mascarado=mascarar_cpf(a.cpf), sem_cpf=a.sem_cpf,
                      telefone=formatar_telefone(principais[a.id]) if a.id in principais else None, status=a.status,
                      aulas_reservadas=reservadas.get(a.id, 0), foto_url=foto_url(a), criado_em=a.criado_em)
        for a in linhas
    ]
    return sc.ListaAlunos(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina, contagens=contagens(ctx))


def busca_rapida(ctx: Contexto, q: str, limite: int = 8) -> list[sc.AlunoBusca]:
    """Para a barra do topo: poucos resultados, ativos primeiro."""
    q = q.strip()
    if len(q) < 2:
        return []
    db = ctx.db
    consulta = restringir(ctx, select(Aluno)).where(_condicao_busca(q)).order_by(
        (Aluno.status == StatusAluno.ATIVO).desc(), Aluno.nome, Aluno.id).limit(limite)
    alunos = list(db.scalars(consulta))
    ids = [a.id for a in alunos]
    principais: dict[int, str] = {}
    if ids:
        for t in db.scalars(select(AlunoTelefone).where(AlunoTelefone.aluno_id.in_(ids)).order_by(AlunoTelefone.ordem, AlunoTelefone.id)):
            principais.setdefault(t.aluno_id, t.numero)
    return [sc.AlunoBusca(id=a.id, nome=a.nome, cpf_mascarado=mascarar_cpf(a.cpf),
                          telefone=formatar_telefone(principais[a.id]) if a.id in principais else None,
                          status=a.status, foto_url=foto_url(a)) for a in alunos]


# ------------------------------------------------------------------------------------------------ foto
async def salvar_foto(ctx: Contexto, a: Aluno, arquivo) -> None:
    exigir_escrita(ctx)
    conteudo = await arquivo.read(4 * 1024 * 1024 + 1)
    try:
        anterior = a.foto_path
        a.foto_path = storage.salvar(CAT_ALUNOS, arquivo.filename or "", conteudo, subpasta="foto", nome_base=f"aluno_{a.id}", substituir=True)
        if anterior and anterior != a.foto_path:
            storage.remover(anterior)
    except storage.ArquivoInvalido as e:
        raise erro(400, str(e)) from e
    ctx.auditar("aluno.foto", "aluno", a.id, descricao=f"Nova foto de {a.nome}")
    ctx.db.commit()


def remover_foto(ctx: Contexto, a: Aluno) -> None:
    exigir_escrita(ctx)
    storage.remover(a.foto_path)
    a.foto_path = None
    ctx.auditar("aluno.foto", "aluno", a.id, descricao=f"Foto de {a.nome} removida")
    ctx.db.commit()


# ------------------------------------------------------------------------------------------------ documentos
def _nome_arquivo(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def documento_out(d: AlunoDocumento) -> sc.DocumentoOut:
    tam = None
    try:
        p = storage.resolver(d.arquivo_path)
        tam = p.stat().st_size if p.is_file() else None
    except storage.ArquivoInvalido:
        pass
    return sc.DocumentoOut(id=d.id, titulo=d.titulo, descricao=d.descricao, origem=d.origem, contrato_id=d.contrato_id,
                           nome_arquivo=_nome_arquivo(d.arquivo_path), tamanho=tam, criado_em=d.criado_em,
                           pode_excluir=d.origem == OrigemDocumento.UPLOAD)


def listar_documentos(db: Session, aluno_id: int) -> list[sc.DocumentoOut]:
    docs = db.scalars(select(AlunoDocumento).where(AlunoDocumento.aluno_id == aluno_id).order_by(AlunoDocumento.criado_em.desc(), AlunoDocumento.id.desc()))
    return [documento_out(d) for d in docs]


async def enviar_documento(ctx: Contexto, a: Aluno, titulo: str, descricao: str | None, arquivo) -> AlunoDocumento:
    exigir_escrita(ctx)
    titulo = (titulo or "").strip()
    if not titulo:
        raise erro(422, "Informe o título do documento.")
    conteudo = await arquivo.read(10 * 1024 * 1024 + 1)
    try:
        rel = storage.salvar(CAT_DOCUMENTOS, arquivo.filename or "", conteudo, subpasta=str(a.id))
    except storage.ArquivoInvalido as e:
        raise erro(400, str(e)) from e
    d = AlunoDocumento(aluno_id=a.id, titulo=titulo[:150], descricao=(descricao or "").strip() or None, arquivo_path=rel,
                       sha256=hashlib.sha256(conteudo).hexdigest(), origem=OrigemDocumento.UPLOAD)
    ctx.db.add(d)
    ctx.db.flush()
    ctx.auditar("aluno.documento.enviar", "aluno_documento", d.id, descricao=f"Documento \"{d.titulo}\" de {a.nome}",
                depois={"aluno_id": a.id, "arquivo": _nome_arquivo(rel), "sha256": d.sha256})
    ctx.db.commit()
    return d


def obter_documento(ctx: Contexto, a: Aluno, doc_id: int) -> AlunoDocumento:
    d = ctx.db.get(AlunoDocumento, doc_id)
    if not d or d.aluno_id != a.id:
        raise erro(404, "Documento não encontrado.")
    return d


def excluir_documento(ctx: Contexto, a: Aluno, d: AlunoDocumento) -> None:
    exigir_escrita(ctx)
    if d.origem != OrigemDocumento.UPLOAD:
        raise erro(409, "Este documento foi gerado pelo contrato e não pode ser excluído por aqui.")
    rel = d.arquivo_path
    ctx.auditar("aluno.documento.excluir", "aluno_documento", d.id, descricao=f"Documento \"{d.titulo}\" de {a.nome} excluído",
                antes={"aluno_id": a.id, "arquivo": _nome_arquivo(rel)})
    ctx.db.delete(d)
    ctx.db.commit()
    storage.remover(rel)


# ------------------------------------------------------------------------------------------------ termo de uso de imagem
def _termo_do_aluno(db: Session, a: Aluno) -> TermoUso | None:
    if a.termo_uso_id:
        t = db.get(TermoUso, a.termo_uso_id)
        if t:
            return t
    return db.scalar(select(TermoUso).order_by(TermoUso.id).limit(1))


def renderizar_termo_html(db: Session, termo: TermoUso, a: Aluno) -> str:
    """Troca as variáveis `{ALUNO_*}`/`{ENDERECO_*}` pelos dados do aluno (valores escapados: o HTML do termo é do admin,
    os dados do aluno nunca viram marcação)."""
    e = endereco_do_aluno(db, a.id)
    prof = db.get(Profissao, a.profissao_id) if a.profissao_id else None
    tels = ", ".join(formatar_telefone(t.numero) for t in telefones_do_aluno(db, a.id))
    end_txt = f"{e.logradouro}, {e.numero} - {e.bairro} - {e.cidade} ({e.cep or ''})" if e else ""
    sub = {
        "{ALUNO_NOME}": a.nome, "{ALUNO_CPF}": formatar_cpf(a.cpf) if a.cpf else "", "{ALUNO_RG}": a.rg or "",
        "{ALUNO_NASCIMENTO}": a.data_nascimento.strftime("%d/%m/%Y") if a.data_nascimento else "",
        "{ALUNO_ESTADO_CIVIL}": a.estado_civil.value.replace("_", " ").title() if a.estado_civil else "",
        "{ALUNO_PROFISSAO}": prof.nome if prof else "", "{ALUNO_EMAIL}": a.email or "", "{ALUNO_TELEFONE}": tels,
        "{ALUNO_ENDERECO}": end_txt, "{ENDERECO_LOGRADOURO}": e.logradouro if e else "", "{ENDERECO_NUMERO}": e.numero if e else "",
        "{ENDERECO_BAIRRO}": e.bairro if e else "", "{ENDERECO_CIDADE}": e.cidade if e else "", "{ENDERECO_CEP}": (e.cep or "") if e else "",
        "{DATA_HOJE}": date.today().strftime("%d/%m/%Y"),
    }
    texto = termo.conteudo_html or ""
    for chave, valor in sub.items():
        texto = texto.replace(chave, html.escape(valor or ""))
    return texto


def estado_termo(ctx: Contexto, a: Aluno) -> sc.TermoEstado:
    db = ctx.db
    termo = _termo_do_aluno(db, a)
    disponiveis = [sc.TermoOpcao(id=t.id, nome=t.nome) for t in db.scalars(select(TermoUso).order_by(TermoUso.nome))]
    assinatura_url = f"/alunos/{a.id}/termo/assinatura?v={storage.versao(a.termo_assinatura_path)}" if storage.existe(a.termo_assinatura_path) else None
    return sc.TermoEstado(
        autoriza_imagem=a.autoriza_imagem, assinado=a.termo_assinado_em is not None,
        termo=sc.TermoOpcao(id=termo.id, nome=termo.nome) if termo else None, termos_disponiveis=disponiveis,
        aceite_em=a.termo_aceite_em, assinado_em=a.termo_assinado_em, assinatura_nome=a.termo_assinatura_nome,
        assinatura_documento=a.termo_assinatura_documento, assinatura_ip=a.termo_assinatura_ip, assinatura_url=assinatura_url,
        texto_html=renderizar_termo_html(db, termo, a) if termo else None,
    )


def registrar_termo(ctx: Contexto, a: Aluno, termo_id: int) -> None:
    """Registra o aceite do termo sem imagem de assinatura (como o "registrar" do sistema antigo)."""
    exigir_escrita(ctx)
    termo = ctx.db.get(TermoUso, termo_id)
    if not termo:
        raise erro(422, "Selecione um termo válido.")
    a.termo_uso_id = termo.id
    a.termo_aceite_em = agora()
    a.autoriza_imagem = True
    ctx.auditar("aluno.termo.registrar", "aluno", a.id, descricao=f"Termo \"{termo.nome}\" registrado para {a.nome}",
                depois={"termo_uso_id": termo.id, "autoriza_imagem": True})
    ctx.db.commit()


_DATA_URL = re.compile(r"^data:image/png;base64,(?P<b64>[A-Za-z0-9+/=\s]+)$")


def decodificar_assinatura(data_url: str) -> bytes:
    m = _DATA_URL.match((data_url or "").strip())
    if not m:
        raise erro(422, "A assinatura deve ser uma imagem PNG.")
    try:
        png = base64.b64decode(m.group("b64"), validate=False)
    except Exception:
        raise erro(422, "Assinatura inválida.") from None
    if len(png) > 1024 * 1024:
        raise erro(422, "A imagem da assinatura é grande demais.")
    return png


def assinar_termo_local(ctx: Contexto, a: Aluno, dados: sc.AssinaturaTermoIn) -> None:
    """Assinatura feita na tela do estúdio (canvas). Grava imagem, nome, documento e IP; autoriza o uso da imagem."""
    exigir_escrita(ctx)
    db = ctx.db
    termo = db.get(TermoUso, dados.termo_id) if dados.termo_id else _termo_do_aluno(db, a)
    if not termo:
        raise erro(409, "Nenhum termo cadastrado para assinar. Cadastre em Cadastros > Termos.")
    png = decodificar_assinatura(dados.assinatura)
    try:
        rel = storage.salvar(CAT_ALUNOS, "assinatura.png", png, subpasta="termo", nome_base=f"termo_{a.id}", substituir=True)
    except storage.ArquivoInvalido as e:
        raise erro(422, str(e)) from e
    antiga = a.termo_assinatura_path
    if antiga and antiga != rel:
        storage.remover(antiga)
    agora_ = agora()
    a.termo_uso_id = termo.id
    a.termo_assinatura_nome = dados.nome.strip()
    a.termo_assinatura_documento = (dados.documento or "").strip() or None
    a.termo_assinatura_ip = ctx.ip
    a.termo_assinatura_path = rel
    a.autoriza_imagem = True
    a.termo_aceite_em = agora_
    a.termo_assinado_em = agora_
    ctx.auditar("aluno.termo.assinar", "aluno", a.id, descricao=f"Termo \"{termo.nome}\" assinado no estúdio por {a.termo_assinatura_nome}",
                depois={"termo_uso_id": termo.id, "assinatura_nome": a.termo_assinatura_nome, "ip": ctx.ip})
    db.commit()


def gerar_link_assinatura_termo(a: Aluno) -> str:  # pragma: no cover - ponto de extensão
    """PONTO DE EXTENSÃO (onda de comunicação): gerar o link assinado com prazo (`core.links`) e enviá-lo por WhatsApp.
    Ainda não implementado: a página pública de assinatura e o envio pertencem ao módulo de comunicação."""
    raise NotImplementedError("Link de assinatura do termo ainda não disponível.")


# ------------------------------------------------------------------------------------------------ CEP (ViaCEP)
_CACHE_CEP: dict[str, tuple[float, sc.CepOut | None]] = {}
TTL_CEP_S = 600
TTL_CEP_NAO_ACHADO_S = 60


@dataclass
class CepIndisponivel(Exception):
    pass


def consultar_viacep(cep: str) -> dict | None:
    """Chamada real ao ViaCEP (os testes substituem esta função: nunca vão à internet). None = CEP inexistente."""
    try:
        r = httpx.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=4.0)
        r.raise_for_status()
        dados = r.json()
    except (httpx.HTTPError, ValueError):
        raise CepIndisponivel() from None
    if not isinstance(dados, dict) or dados.get("erro"):
        return None
    return dados


def buscar_cep(cep: str) -> sc.CepOut:
    d = so_digitos(cep)
    if len(d) != 8:
        raise erro(422, "CEP inválido: informe 8 dígitos.")
    agora_s = time.monotonic()
    em_cache = _CACHE_CEP.get(d)
    if em_cache and em_cache[0] > agora_s:
        if em_cache[1] is None:
            raise erro(404, "CEP não encontrado. Preencha o endereço manualmente.")
        return em_cache[1]
    try:
        dados = consultar_viacep(d)
    except CepIndisponivel:
        raise erro(502, "Não foi possível consultar o CEP agora. Preencha o endereço manualmente.") from None
    if dados is None:
        _CACHE_CEP[d] = (agora_s + TTL_CEP_NAO_ACHADO_S, None)
        raise erro(404, "CEP não encontrado. Preencha o endereço manualmente.")
    out = sc.CepOut(cep=d, logradouro=dados.get("logradouro", "") or "", complemento=dados.get("complemento", "") or "",
                    bairro=dados.get("bairro", "") or "", cidade=dados.get("localidade", "") or "", uf=dados.get("uf", "") or "")
    if len(_CACHE_CEP) > 500:
        _CACHE_CEP.clear()
    _CACHE_CEP[d] = (agora_s + TTL_CEP_S, out)
    return out


def limpar_cache_cep() -> None:
    _CACHE_CEP.clear()

