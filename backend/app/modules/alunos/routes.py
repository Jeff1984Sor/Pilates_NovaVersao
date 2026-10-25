"""Rotas de alunos: lista, busca rápida, CEP, cadastro, ficha, foto, documentos e termo de uso de imagem."""

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core import storage
from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.core.schemas import Mensagem
from app.modules.alunos import schemas as sc
from app.modules.alunos import servico
from app.modules.alunos.models import StatusAluno

router = APIRouter(prefix="/alunos", tags=["alunos"])

# Regras específicas (as demais rotas /alunos* caem em "alunos.*": GET=ver, DELETE=excluir, demais=editar).
# Resumo e foto são LIVRES no mapa porque a checagem é "alunos.ver OU aulas.ver" (o Professor só tem a segunda), feita na rota.
adicionar_regras([
    ("GET", r"/alunos/\d+/resumo$", None),
    ("GET", r"/alunos/\d+/foto$", None),
    ("DELETE", r"/alunos/\d+/foto$", "alunos.editar"),
    ("DELETE", r"/alunos/\d+/documentos/\d+$", "alunos.editar"),
    ("POST", r"/alunos/\d+/(inativar|reativar)$", "alunos.editar"),
])


def _ver_cabecalho(ctx) -> None:
    if not (ctx.pode("alunos.ver") or ctx.pode("aulas.ver")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu perfil de acesso não permite esta ação.")


# ------------------------------------------------------------------------------------------------ lista, busca, CEP
@router.get("", response_model=sc.ListaAlunos)
def listar(
    ctx: Ctx,
    q: str = Query("", max_length=100),
    situacao: Literal["ativos", "inativos", "todos"] = "ativos",
    ordem: str = "nome",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
):
    return servico.listar(ctx, q=q, situacao=situacao, ordem=ordem, pagina=pagina, por_pagina=por_pagina)


@router.get("/busca", response_model=list[sc.AlunoBusca])
def busca_rapida(ctx: Ctx, q: str = Query("", max_length=100), limite: int = Query(8, ge=1, le=15)):
    """Barra do topo: aluno, CPF ou telefone; devolve poucos resultados."""
    return servico.busca_rapida(ctx, q, limite)


@router.get("/cep/{cep}", response_model=sc.CepOut)
def consultar_cep(cep: str, ctx: Ctx):
    return servico.buscar_cep(cep)


# ------------------------------------------------------------------------------------------------ cadastro
@router.post("", response_model=sc.AlunoOut, status_code=status.HTTP_201_CREATED)
def criar(dados: sc.AlunoIn, ctx: Ctx):
    return servico.aluno_out(ctx, servico.criar_aluno(ctx, dados))


@router.get("/{aluno_id}", response_model=sc.AlunoOut)
def ler(aluno_id: int, ctx: Ctx):
    return servico.aluno_out(ctx, servico.obter_aluno(ctx, aluno_id))


@router.get("/{aluno_id}/resumo", response_model=sc.AlunoResumo)
def resumo(aluno_id: int, ctx: Ctx):
    """Cabeçalho mínimo da ficha (sem CPF nem telefone): serve ao Professor, só para alunos de aulas dele."""
    _ver_cabecalho(ctx)
    return servico.resumo_out(ctx, servico.obter_aluno(ctx, aluno_id))


@router.put("/{aluno_id}", response_model=sc.AlunoOut)
def atualizar(aluno_id: int, dados: sc.AlunoIn, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    return servico.aluno_out(ctx, servico.atualizar_aluno(ctx, a, dados))


@router.get("/{aluno_id}/vinculos", response_model=sc.Vinculos)
def vinculos(aluno_id: int, ctx: Ctx):
    servico.obter_aluno(ctx, aluno_id)
    return servico.quantidade_vinculos(ctx.db, aluno_id)


@router.post("/{aluno_id}/inativar", response_model=sc.AlunoOut)
def inativar(aluno_id: int, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    return servico.aluno_out(ctx, servico.mudar_status(ctx, a, StatusAluno.INATIVO))


@router.post("/{aluno_id}/reativar", response_model=sc.AlunoOut)
def reativar(aluno_id: int, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    return servico.aluno_out(ctx, servico.mudar_status(ctx, a, StatusAluno.ATIVO))


@router.delete("/{aluno_id}", response_model=Mensagem)
def excluir(aluno_id: int, ctx: Ctx):
    """Exclui só aluno sem vínculos (contratos, aulas, cobranças); senão 409 orientando a inativar."""
    servico.excluir_aluno(ctx, servico.obter_aluno(ctx, aluno_id))
    return Mensagem(mensagem="Aluno excluído.")


# ------------------------------------------------------------------------------------------------ foto
@router.post("/{aluno_id}/foto", response_model=sc.AlunoOut)
async def enviar_foto(aluno_id: int, ctx: Ctx, arquivo: UploadFile = File(...)):
    a = servico.obter_aluno(ctx, aluno_id)
    await servico.salvar_foto(ctx, a, arquivo)
    return servico.aluno_out(ctx, a)


@router.delete("/{aluno_id}/foto", response_model=sc.AlunoOut)
def remover_foto(aluno_id: int, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    servico.remover_foto(ctx, a)
    return servico.aluno_out(ctx, a)


@router.get("/{aluno_id}/foto")
def foto(aluno_id: int, ctx: Ctx):
    _ver_cabecalho(ctx)
    a = servico.obter_aluno(ctx, aluno_id)
    if not storage.existe(a.foto_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sem foto.")
    return FileResponse(storage.resolver(a.foto_path), headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


# ------------------------------------------------------------------------------------------------ documentos
@router.get("/{aluno_id}/documentos", response_model=list[sc.DocumentoOut])
def listar_documentos(aluno_id: int, ctx: Ctx):
    servico.obter_aluno(ctx, aluno_id)
    return servico.listar_documentos(ctx.db, aluno_id)


@router.post("/{aluno_id}/documentos", response_model=sc.DocumentoOut, status_code=status.HTTP_201_CREATED)
async def enviar_documento(
    aluno_id: int, ctx: Ctx, titulo: str = Form(..., max_length=150), descricao: str | None = Form(None, max_length=2000),
    arquivo: UploadFile = File(...),
):
    a = servico.obter_aluno(ctx, aluno_id)
    d = await servico.enviar_documento(ctx, a, titulo, descricao, arquivo)
    return servico.documento_out(d)


@router.get("/{aluno_id}/documentos/{doc_id}/arquivo")
def baixar_documento(aluno_id: int, doc_id: int, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    d = servico.obter_documento(ctx, a, doc_id)
    if not storage.existe(d.arquivo_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O arquivo deste documento não está mais disponível.")
    ctx.auditar("aluno.documento.baixar", "aluno_documento", d.id, descricao=f"Download de \"{d.titulo}\" ({a.nome})")
    ctx.db.commit()
    nome = servico._nome_arquivo(d.arquivo_path)
    ext = nome.rsplit(".", 1)[-1] if "." in nome else ""
    seguro = "".join(c for c in d.titulo if c.isalnum() or c in " ._-")[:80].strip() or "documento"
    return FileResponse(storage.resolver(d.arquivo_path), filename=f"{seguro}.{ext}" if ext else seguro,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "sandbox"})


@router.delete("/{aluno_id}/documentos/{doc_id}", response_model=Mensagem)
def excluir_documento(aluno_id: int, doc_id: int, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    servico.excluir_documento(ctx, a, servico.obter_documento(ctx, a, doc_id))
    return Mensagem(mensagem="Documento excluído.")


# ------------------------------------------------------------------------------------------------ termo de uso de imagem
@router.get("/{aluno_id}/termo", response_model=sc.TermoEstado)
def termo(aluno_id: int, ctx: Ctx):
    return servico.estado_termo(ctx, servico.obter_aluno(ctx, aluno_id))


@router.post("/{aluno_id}/termo/registrar", response_model=sc.TermoEstado)
def registrar_termo(aluno_id: int, dados: sc.RegistrarTermoIn, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    servico.registrar_termo(ctx, a, dados.termo_id)
    return servico.estado_termo(ctx, a)


@router.post("/{aluno_id}/termo/assinatura-local", response_model=sc.TermoEstado)
def assinar_termo_local(aluno_id: int, dados: sc.AssinaturaTermoIn, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    servico.assinar_termo_local(ctx, a, dados)
    return servico.estado_termo(ctx, a)


@router.get("/{aluno_id}/termo/assinatura")
def imagem_assinatura(aluno_id: int, ctx: Ctx):
    a = servico.obter_aluno(ctx, aluno_id)
    if not storage.existe(a.termo_assinatura_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sem assinatura registrada.")
    return FileResponse(storage.resolver(a.termo_assinatura_path), headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})
