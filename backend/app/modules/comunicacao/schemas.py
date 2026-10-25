"""Esquemas da API de comunicação. NENHUM esquema de saída tem campo para o valor da credencial."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.domain import whatsapp_avisos as dom
from app.modules.comunicacao import servico as svc

Publico = Literal["ativos", "inativos", "todos"]


class GeralIn(BaseModel):
    envio_automatico_ativo: bool


class GeralOut(BaseModel):
    envio_automatico_ativo: bool


class AvisoCfg(BaseModel):
    ativo: bool
    horario: time


class ConfigIn(BaseModel):
    provedor: Literal["wasender", "evolution"]
    url_api: str | None = Field(None, max_length=300)
    instancia: str | None = Field(None, max_length=150)
    #: somente escrita: vazio/ausente = mantém a atual
    credencial: str | None = Field(None, max_length=500)
    limpar_credencial: bool = False
    acompanhar_envios: bool = False
    numero_acompanhamento: str | None = Field(None, max_length=20)
    pausa_segundos: int = Field(dom.INTERVALO_ENTRE_ENVIOS_SEGUNDOS, ge=0, le=svc.PAUSA_MAX_S)
    pix_tipo: str | None = Field(None, max_length=40)
    pix_chave: str | None = Field(None, max_length=140)
    enviar_link_contrato: bool = False
    avisar_fim_contrato: bool = False
    avisos: dict[str, AvisoCfg] = {}
    textos: dict[str, str | None] = {}

    @field_validator("url_api")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if not v:
            return None
        if urlparse(v).scheme not in ("http", "https") or not urlparse(v).netloc:
            raise ValueError("endereço inválido: use http:// ou https://")
        return v

    @field_validator("avisos")
    @classmethod
    def _avisos(cls, v: dict[str, AvisoCfg]) -> dict[str, AvisoCfg]:
        extra = set(v) - set(dom.TIPOS)
        if extra:
            raise ValueError(f"aviso desconhecido: {', '.join(sorted(extra))}")
        return v

    @field_validator("textos")
    @classmethod
    def _textos(cls, v: dict[str, str | None]) -> dict[str, str | None]:
        extra = set(v) - set(svc.CAMPOS_TEXTO)
        if extra:
            raise ValueError(f"texto desconhecido: {', '.join(sorted(extra))}")
        for k, t in v.items():
            if t is not None and len(t) > 4000:
                raise ValueError(f"{k}: texto muito longo (máx. 4000)")
        return v


class AvisoOut(BaseModel):
    tipo: str
    rotulo: str
    ativo: bool
    horario: time
    campo_texto: str


class ConfigOut(BaseModel):
    unidade_id: int
    unidade_nome: str
    existe: bool
    provedor: str
    url_api: str | None
    instancia: str | None
    credencial_definida: bool
    credencial_final: str | None  # só os 4 últimos caracteres
    acompanhar_envios: bool
    numero_acompanhamento: str | None
    pausa_segundos: int
    pix_tipo: str | None
    pix_chave: str | None
    enviar_link_contrato: bool
    avisar_fim_contrato: bool
    avisos: list[AvisoOut]
    textos: dict[str, str]  # já com o texto padrão quando a unidade não personalizou
    envio_automatico_ativo: bool  # chave geral do ambiente (somente leitura aqui)


class ResumoUnidadeOut(BaseModel):
    unidade_id: int
    unidade_nome: str
    configurado: bool
    provedor: str | None
    avisos_ligados: int


class TesteOut(BaseModel):
    conectada: bool | None
    detalhe: str


class CampoTextoOut(BaseModel):
    campo: str
    rotulo: str
    padrao: str
    variaveis: list[str]


class TextosPadraoOut(BaseModel):
    campos: list[CampoTextoOut]
    variaveis_estudio: list[str]


class MensagemOut(BaseModel):
    id: int
    aluno_id: int
    aluno_nome: str | None
    tipo: str
    tipo_rotulo: str
    direcao: str
    telefone: str | None
    mensagem: str
    status: str
    detalhe: str | None  # só nas falhas
    enviado_em: datetime


class EnviarIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


class EnvioOut(BaseModel):
    enviado: bool
    mensagem: str


class PreviaReservaOut(BaseModel):
    aluno_id: int
    aluno_nome: str
    mensagem: str
    tem_celular: bool


class ComunicadoIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)
    publico: Publico
    unidade_id: int | None = None


class PreviaIn(ComunicadoIn):
    pass


class PreviaOut(BaseModel):
    total: int
    com_telefone: int
    sem_telefone: int
    primeiro_aluno: str | None
    mensagem: str


class ComunicadoOut(BaseModel):
    id: int
    status: str
    texto: str
    publico: str
    unidade_id: int | None
    pausa_segundos: int
    aviso: str | None
    total: int
    enviados: int
    falhas: int
    sem_telefone: int
    pendentes: int
    cancelados: int
    percentual: int
    criado_em: datetime
    finalizado_em: datetime | None


class DestinatarioOut(BaseModel):
    aluno_id: int
    nome: str
    telefone: str | None
    status: str
    erro: str | None
    enviado_em: datetime | None


class AvisoAlunoIn(BaseModel):
    aluno_id: int
    texto: str = Field(min_length=1, max_length=4000)


class AvisoAlunoPreviaOut(BaseModel):
    aluno_nome: str
    mensagem: str
    tem_celular: bool


class AutomaticoOut(BaseModel):
    id: int
    tipo: str
    tipo_rotulo: str
    unidade_id: int | None
    data_referencia: date
    destinatario: str | None
    status: str
    mensagem: str
    enviado_em: datetime


class AcompanhamentoOut(BaseModel):
    envio_automatico_ativo: bool
    hoje: dict[str, int]  # contagem por status
    itens: list[AutomaticoOut]
    total: int


class StatusOut(BaseModel):
    unidades_configuradas: int
    envio_automatico_ativo: bool
