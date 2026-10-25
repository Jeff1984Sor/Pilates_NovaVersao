"""Esquemas (entrada e saída) da API de contratos."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.contratos.models import FormaPagamento, StatusAssinatura

Chip = Literal["ativos", "vencendo", "vencidos", "nao_assinados", "todos"]


# ------------------------------------------------------------------------------------------------ precificação
class PrecificarIn(BaseModel):
    plano_id: int
    data_inicio: date
    data_fim: date | None = None


class ParcelaPrevista(BaseModel):
    numero: int
    vencimento: date
    competencia: str
    valor: Decimal


class PrecificacaoOut(BaseModel):
    """O que a tela mostra em tempo real (R1 e R2). Nada é gravado."""

    plano_id: int
    plano_nome: str
    avulso: bool
    aulas_por_semana: int
    duracao_meses: int
    valor_mensal: Decimal
    valor_aula: Decimal | None
    valor_parcela: Decimal
    valor_total: Decimal
    data_inicio: date
    data_fim: date
    data_fim_sugerida: date
    parcelas: list[ParcelaPrevista]


# ----------------------------------------------------------------------------------------------------- criação
class ContratoIn(BaseModel):
    aluno_id: int
    plano_id: int
    unidade_id: int
    profissional_id: int
    data_inicio: date
    data_fim: date | None = None  # vazio = início + duração do plano
    forma_pagamento: FormaPagamento | None = None

    @model_validator(mode="after")
    def _datas(self):
        if self.data_fim is not None and self.data_fim < self.data_inicio:
            raise ValueError("A data final não pode ser anterior à inicial.")
        return self


class RenovarIn(BaseModel):
    data_inicio: date | None = None  # vazio = dia seguinte ao fim do contrato original
    data_fim: date | None = None
    plano_id: int | None = None
    forma_pagamento: FormaPagamento | None = None


class EditarIn(BaseModel):
    unidade_id: int | None = None
    profissional_id: int | None = None
    forma_pagamento: FormaPagamento | None = None
    limpar_forma_pagamento: bool = False
    plano_id: int | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    #: só recalcula valor da aula, parcela e total (R1) se o usuário CONFIRMAR; senão os valores atuais ficam como estão
    recalcular_valores: bool = False
    #: valores digitados à mão (não combinam com `recalcular_valores`)
    valor_aula: Decimal | None = Field(None, ge=0)
    valor_parcela: Decimal | None = Field(None, ge=0)
    valor_total: Decimal | None = Field(None, ge=0)
    #: contrato já assinado: alterar plano, datas ou valores exige confirmar que o documento assinado deixa de valer igual
    confirmar_alterar_assinado: bool = False


class EncerrarIn(BaseModel):
    cancelar_parcelas_futuras: bool = True
    remover_aulas_futuras: bool = True
    motivo: str | None = Field(None, max_length=200)


class RecalcularIn(BaseModel):
    simular: bool = True
    contrato_ids: list[int] | None = None
    somente_vigentes: bool = False


# ------------------------------------------------------------------------------------------------------ saída
class PessoaRef(BaseModel):
    id: int
    nome: str


class Situacao(BaseModel):
    rotulo: str
    badge: str  # danger | warning | success
    dias_restantes: int


class ContratoResumo(BaseModel):
    id: int
    numero: int
    aluno: PessoaRef
    plano: PessoaRef
    unidade: PessoaRef
    profissional: PessoaRef
    data_inicio: date
    data_fim: date
    valor_aula: Decimal | None
    valor_parcela: Decimal
    valor_total: Decimal
    forma_pagamento: FormaPagamento | None
    status_assinatura: StatusAssinatura
    situacao: Situacao
    parcelas_abertas: int
    aulas_futuras: int
    pdf_documento_id: int | None = None


class Contagens(BaseModel):
    ativos: int
    vencendo: int
    vencidos: int
    nao_assinados: int
    total: int


class ListaContratos(BaseModel):
    itens: list[ContratoResumo]
    total: int
    pagina: int
    por_pagina: int
    chip: Chip
    contagens: Contagens


class ParcelaOut(BaseModel):
    id: int
    vencimento: date
    competencia: str | None
    valor: Decimal
    situacao: str


class AssinaturaOut(BaseModel):
    nome: str | None
    documento: str | None
    ip: str | None
    assinado_em: datetime | None
    imagem_url: str | None


class ContratoDetalhe(ContratoResumo):
    tipo_servico_id: int
    aulas_por_semana: int
    duracao_meses: int
    avulso: bool
    recorrencia: str
    valor_do_plano: Decimal
    valores_divergem_do_plano: bool
    parcelas: list[ParcelaOut]
    assinatura: AssinaturaOut
    precisa_agenda: bool
    aluno_email: str | None
    aluno_telefone: str | None
    avisos: list[str] = []


class ContratoCriado(BaseModel):
    contrato: ContratoDetalhe
    parcelas_criadas: int
    pdf_documento_id: int
    proximo_passo: Literal["agenda", "nenhum"]


class RecalculoItem(BaseModel):
    contrato_id: int
    numero: int
    aluno: str
    plano: str
    antes: dict[str, Decimal | None]
    depois: dict[str, Decimal | None]


class RecalculoOut(BaseModel):
    simulacao: bool
    verificados: int
    alterados: int
    itens: list[RecalculoItem]


# ----------------------------------------------------------------------------------------------------- exclusão
class ContaExclusao(BaseModel):
    id: int
    vencimento: date
    valor: Decimal
    situacao: str


class ReservaExclusao(BaseModel):
    id: int
    data: date
    inicio: str
    status: str


class PlanoExclusaoOut(BaseModel):
    pode_excluir: bool
    motivos_bloqueio: list[str]
    alternativa: str | None
    contas_a_excluir: list[ContaExclusao]
    contas_pagas: list[ContaExclusao]
    comissoes: int
    reservas_a_excluir: list[ReservaExclusao]
    reservas_mantidas: int
    sessoes_que_ficam_vazias: int
    documento_pdf_sera_excluido: bool
    resumo: str


class ExclusaoOut(BaseModel):
    contas_excluidas: int
    reservas_excluidas: int
    reservas_mantidas: int
    sessoes_excluidas: int


class EncerramentoOut(BaseModel):
    contrato: ContratoDetalhe
    parcelas_canceladas: int
    reservas_removidas: int
    reservas_mantidas: int


# -------------------------------------------------------------------------------------------------------- agenda
class SlotOut(BaseModel):
    dia_semana: int
    inicio: str
    fim: str
    valor: str  # "0|08:00|08:50" (formato do domínio)
    profissionais: list[PessoaRef]


class AgendaOpcoes(BaseModel):
    contrato_id: int
    aulas_por_semana: int
    exatamente: int
    inicio: date
    fim: date
    slots: list[SlotOut]
    ja_agendadas: int
    dias_semana_agendados: list[int]
    mensagem: str | None = None


class SelecaoIn(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    inicio: str = Field(pattern=r"^\d{2}:\d{2}$")
    fim: str = Field(pattern=r"^\d{2}:\d{2}$")
    profissional_id: int


class AgendaIn(BaseModel):
    selecoes: list[SelecaoIn] = Field(min_length=1, max_length=7)
    a_partir_de: date | None = None  # padrão: o maior entre o início do contrato e hoje


class AgendaOut(BaseModel):
    reservas_criadas: int
    sessoes_criadas: int
    ja_existentes: int
    conflitos: list[str]
    mensagem_conflitos: str | None


# --------------------------------------------------------------------------------------------- assinatura e envio
class AssinaturaLocalIn(BaseModel):
    nome: str = Field(min_length=3, max_length=150)
    documento: str = Field(min_length=11, max_length=18)
    assinatura: str = Field(min_length=20, max_length=2_000_000)  # data URL PNG do canvas

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        return " ".join(v.split())


class LinkOut(BaseModel):
    url: str
    expira_em: datetime
    pdf_url: str


class EnvioOut(BaseModel):
    canal: Literal["email", "whatsapp"]
    destino: str
    mensagem: str


class WhatsappDisponivelOut(BaseModel):
    disponivel: bool


class OpcoesOut(BaseModel):
    planos: list[dict]
    unidades: list[PessoaRef]
    profissionais: list[PessoaRef]
    formas_pagamento: list[str]
    whatsapp_disponivel: bool


# --------------------------------------------------------------------------------------------- páginas públicas
class ContratoPublico(BaseModel):
    """O mínimo para o aluno conferir e assinar. Contrato já assinado NÃO devolve o texto."""

    estado: Literal["pendente", "assinado"]
    estudio_nome: str
    numero: int
    aluno_primeiro_nome: str
    assinado_em: datetime | None = None
    html: str | None = None


class AssinarPublicoIn(BaseModel):
    nome: str = Field(min_length=3, max_length=150)
    documento: str = Field(min_length=11, max_length=18)
    assinatura: str = Field(min_length=20, max_length=2_000_000)
    li_e_concordo: bool

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        return " ".join(v.split())


class AssinadoOut(BaseModel):
    mensagem: str
    assinado_em: datetime


class TermoPublico(BaseModel):
    estado: Literal["pendente", "assinado"]
    estudio_nome: str
    aluno_primeiro_nome: str
    termo_nome: str | None = None
    assinado_em: datetime | None = None
    html: str | None = None
