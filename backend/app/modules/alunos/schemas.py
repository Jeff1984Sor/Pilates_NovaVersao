"""Esquemas (entrada e saída) do módulo de alunos."""

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.schemas import Schema
from app.modules.alunos.models import EstadoCivil, OrigemDocumento, StatusAluno


def _vazio_para_none(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


# ------------------------------------------------------------------------------------------------ entrada
class TelefoneIn(BaseModel):
    """`id` presente = atualiza o registro existente (não recria); ausente = telefone novo."""

    id: int | None = None
    numero: str = Field(min_length=1, max_length=30)
    principal: bool = False


class EnderecoIn(BaseModel):
    cep: str | None = Field(default=None, max_length=12)
    logradouro: str | None = Field(default=None, max_length=150)
    numero: str | None = Field(default=None, max_length=20)
    bairro: str | None = Field(default=None, max_length=80)
    cidade: str | None = Field(default=None, max_length=80)

    @field_validator("*", mode="before")
    @classmethod
    def _limpa(cls, v):
        return _vazio_para_none(v)


class AlunoIn(BaseModel):
    """Criação (POST) e edição (PUT). Na edição só os campos enviados mudam (`telefones` e `endereco` ausentes = intactos;
    `telefones: []` remove todos; `endereco` com tudo vazio remove o endereço)."""

    nome: str | None = Field(default=None, min_length=2, max_length=150)
    cpf: str | None = Field(default=None, max_length=20)
    sem_cpf: bool | None = None
    rg: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    data_nascimento: date | None = None
    estado_civil: EstadoCivil | None = None
    profissao_id: int | None = None
    unidade_id: int | None = None
    termo_uso_id: int | None = None
    status: StatusAluno | None = None
    autoriza_imagem: bool | None = None
    cpf_pagador_recibo: str | None = Field(default=None, max_length=20)
    telefones: list[TelefoneIn] | None = Field(default=None, max_length=8)
    endereco: EnderecoIn | None = None

    @field_validator("nome", "cpf", "rg", "email", "cpf_pagador_recibo", mode="before")
    @classmethod
    def _limpa(cls, v):
        return _vazio_para_none(v)

    @field_validator("data_nascimento")
    @classmethod
    def _nascimento(cls, v):
        if v and (v > date.today() or v.year < 1900):
            raise ValueError("data de nascimento inválida")
        return v


class AssinaturaTermoIn(BaseModel):
    termo_id: int | None = None
    nome: str = Field(min_length=2, max_length=150)
    documento: str | None = Field(default=None, max_length=30)
    assinatura: str = Field(min_length=20, description="Imagem PNG da assinatura em data URL (base64)")


class RegistrarTermoIn(BaseModel):
    termo_id: int


# ------------------------------------------------------------------------------------------------ saída
class TelefoneOut(Schema):
    id: int
    ordem: int
    numero: str  # canônico (55 + DDD + número)
    formatado: str
    original: str | None = None
    principal: bool
    whatsapp: str  # link/número para o WhatsApp (somente dígitos)


class EnderecoOut(Schema):
    cep: str | None = None
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""


class AlunoLista(Schema):
    id: int
    codigo: int | None
    nome: str
    cpf_mascarado: str | None
    sem_cpf: bool
    telefone: str | None = None  # principal, formatado
    status: StatusAluno
    aulas_reservadas: int = 0
    foto_url: str | None = None
    criado_em: datetime


class Contagens(Schema):
    ativos: int
    inativos: int
    todos: int


class ListaAlunos(Schema):
    itens: list[AlunoLista]
    total: int
    pagina: int
    por_pagina: int
    contagens: Contagens


class AlunoBusca(Schema):
    id: int
    nome: str
    cpf_mascarado: str | None = None
    telefone: str | None = None
    status: StatusAluno
    foto_url: str | None = None


class AlunoResumo(Schema):
    """Cabeçalho mínimo (perfil Professor): sem CPF nem telefone."""

    id: int
    nome: str
    status: StatusAluno
    foto_url: str | None = None
    unidade_nome: str | None = None


class Vinculos(Schema):
    contratos: int = 0
    reservas: int = 0
    aulas_avulsas: int = 0
    aulas_avaliativas: int = 0
    contas_receber: int = 0
    total: int = 0
    pode_excluir: bool = True


class AlunoOut(Schema):
    id: int
    codigo: int | None
    nome: str
    cpf: str | None  # formatado
    cpf_mascarado: str | None
    sem_cpf: bool
    rg: str | None
    email: str | None
    data_nascimento: date | None
    estado_civil: EstadoCivil | None
    profissao_id: int | None
    profissao_nome: str | None = None
    unidade_id: int
    unidade_nome: str | None = None
    termo_uso_id: int | None
    status: StatusAluno
    autoriza_imagem: bool
    cpf_pagador_recibo: str | None  # formatado
    foto_url: str | None = None
    telefones: list[TelefoneOut] = []
    endereco: EnderecoOut | None = None
    termo_assinado_em: datetime | None = None
    criado_em: datetime
    atualizado_em: datetime
    aulas_reservadas: int = 0
    vinculos: Vinculos


class DocumentoOut(Schema):
    id: int
    titulo: str
    descricao: str | None
    origem: OrigemDocumento
    contrato_id: int | None
    nome_arquivo: str
    tamanho: int | None = None
    criado_em: datetime
    pode_excluir: bool


class TermoOpcao(Schema):
    id: int
    nome: str


class TermoEstado(Schema):
    autoriza_imagem: bool
    assinado: bool
    termo: TermoOpcao | None
    termos_disponiveis: list[TermoOpcao]
    aceite_em: datetime | None
    assinado_em: datetime | None
    assinatura_nome: str | None
    assinatura_documento: str | None
    assinatura_ip: str | None
    assinatura_url: str | None
    texto_html: str | None  # termo já com as variáveis do aluno (exibir em iframe isolado)
    link_assinatura_disponivel: bool = False  # ponto de extensão: onda de comunicação


class CepOut(Schema):
    cep: str
    logradouro: str
    complemento: str = ""
    bairro: str
    cidade: str
    uf: str


class OpcaoUnidade(Schema):
    id: int
    nome: str
    ativo: bool


class OpcaoSimples(Schema):
    id: int
    nome: str


class OpcaoTexto(Schema):
    id: str
    nome: str


class Opcoes(Schema):
    """Listas para os selects do cadastro (evita depender das rotas de Cadastros e de permissões diferentes)."""

    unidades: list[OpcaoUnidade]
    profissoes: list[OpcaoSimples]
    termos: list[OpcaoSimples]
    estados_civis: list[OpcaoTexto]
