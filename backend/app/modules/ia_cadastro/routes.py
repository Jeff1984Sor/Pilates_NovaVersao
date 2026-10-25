"""API da IA de cadastro (assistente "Preencher com IA" da ficha do aluno).

- ``GET  /api/ia/cadastro/status``       a IA está configurada? (para habilitar o botão)
- ``POST /api/ia/cadastro/documento``    foto/PDF do documento de identidade -> rascunho (nome, CPF, RG, nascimento)
- ``POST /api/ia/cadastro/comprovante``  foto/PDF do comprovante de endereço -> rascunho (logradouro, número, bairro, cidade, CEP)

Permissão ``ia.usar`` (regra ``/ia`` do core). Devolve só um RASCUNHO: nada é gravado; o usuário confere e aplica no
formulário do aluno. A chave da IA vem de Configurações (cifrada, somente escrita). Rate limit por usuário (cada leitura
custa dinheiro). A auditoria registra quem leu e de que tipo, nunca o conteúdo.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.core import ia
from app.core.deps import Ctx
from app.core.ratelimit import verificar
from app.modules.ia_cadastro import servico as srv
from app.modules.ia_cadastro.cliente import get_cliente

router = APIRouter(prefix="/ia/cadastro", tags=["ia-cadastro"])

LIMITE_POR_HORA = 30


def _ler(arquivo: UploadFile) -> bytes:
    try:
        return arquivo.file.read(srv.MAX_BYTES + 1)  # lê no máximo o limite + 1 byte: arquivo gigante não vai à memória
    finally:
        arquivo.file.close()  # apaga o temporário do upload


@router.get("/status")
def status(ctx: Ctx) -> dict:
    return srv.disponibilidade(ctx.db)


def _processar(request: Request, ctx: Ctx, arquivo: UploadFile, tipo: str) -> dict:
    verificar(request, "ia-cadastro", LIMITE_POR_HORA, 3600, chave=f"u{ctx.usuario.id}", db=ctx.db)
    conteudo = _ler(arquivo)
    try:
        mime = srv.validar_arquivo(arquivo.filename, conteudo)
    except srv.ErroArquivo as e:
        raise HTTPException(e.status, e.mensagem) from None
    pronta = srv.disponibilidade(ctx.db)
    if not pronta["disponivel"]:
        raise HTTPException(409, pronta["mensagem"])
    extrair = srv.extrair_documento if tipo == "documento" else srv.extrair_comprovante
    try:
        r = extrair(ctx.db, get_cliente(), arquivo.filename, conteudo)
    except srv.ErroArquivo as e:
        raise HTTPException(e.status, e.mensagem) from None
    except ia.IAIndisponivel as e:
        # provedor recusou a chave (401/403), cota, timeout ou resposta fora do formato
        ctx.auditar("ia_cadastro.falha", "aluno_rascunho", descricao=f"{tipo}: {mime}, falha do provedor de IA")
        ctx.db.commit()
        raise HTTPException(502, str(e)) from None
    incertos = sum(1 for c in r["campos"] if c["incerto"])
    ctx.auditar(
        "ia_cadastro.extrair", "aluno_rascunho",
        descricao=f"{tipo}: {mime}, {len(conteudo) // 1024} KB, {len(r['campos'])} campos, {incertos} incertos",
    )
    ctx.db.commit()
    return r


@router.post("/documento")
def documento(request: Request, ctx: Ctx, arquivo: UploadFile = File(...)) -> dict:
    return _processar(request, ctx, arquivo, "documento")


@router.post("/comprovante")
def comprovante(request: Request, ctx: Ctx, arquivo: UploadFile = File(...)) -> dict:
    return _processar(request, ctx, arquivo, "comprovante")
