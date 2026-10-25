"""Esquemas (entrada e saída) da API do financeiro."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import Pagina, Schema
from app.domain.documentos import so_digitos, validar_cpf

FormaPagamentoStr = Literal["DINHEIRO", "PIX", "CREDITO", "DEBITO"]
SituacaoReceber = Literal["ABERTO", "PAGO", "ATRASADO", "CANCELADO"]
SituacaoPagar = Literal["AGENDADO", "PAGO", "ATRASADO", "CANCELADO"]


class Entrada(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


# ------------------------------------------------------------------------------------------------ contas a receber
class ContaReceberOut(Schema):
    id: int
    aluno_id: int
    aluno_nome: str | None = None
    contrato_id: int | None = None
    contrato_numero: int | None = None
    reserva_id: int | None = None
    descricao: str | None = None
    origem: str
    plano_nome: str | None = None
    subcategoria_nome: str | None = None
    status: str  # gravado: ABERTO | PAGO | CANCELADO
    situacao: SituacaoReceber  # exibido: ATRASADO é derivado
    dias_atraso: int = 0
    valor: Decimal
    vencimento: date
    competencia: str | None = None
    pagamento: date | None = None
    forma_pagamento: str | None = None
    motivo_cancelamento: str | None = None
    recibo_saude_gerado_em: datetime | None = None


class ChipSituacao(Schema):
    situacao: str  # TODOS | ABERTO | PAGO | ATRASADO | CANCELADO
    quantidade: int
    valor: Decimal


class PaginaReceber(Pagina[ContaReceberOut]):
    chips: list[ChipSituacao]
    hoje: date


class BaixaIn(Entrada):
    data_pagamento: date | None = None
    forma_pagamento: FormaPagamentoStr | None = None
    conta_bancaria_id: int | None = None  # se informada, gera o movimento de ENTRADA na conta


class CancelarReceberIn(Entrada):
    motivo: str = Field(min_length=3, max_length=500)


class EditarReceberIn(Entrada):
    descricao: str | None = Field(default=None, max_length=200)
    valor: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    vencimento: date | None = None
    competencia: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


class AvulsoIn(Entrada):
    aluno_id: int
    descricao: str = Field(min_length=2, max_length=200)
    valor: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    vencimento: date
    competencia: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


class ResumoAlunoOut(Schema):
    aluno_id: int
    total_aberto: Decimal
    total_atrasado: Decimal
    total_pago: Decimal
    qtd_aberto: int
    qtd_atrasado: int
    qtd_pago: int
    proximo_vencimento: date | None
    em_dia: bool


class CobrancaOut(Schema):
    enviado: bool
    mensagem: str


# ------------------------------------------------------------------------------------------------- contas a pagar
class ContaPagarOut(Schema):
    id: int
    fornecedor_id: int
    fornecedor_nome: str | None = None
    categoria_id: int
    categoria_nome: str | None = None
    subcategoria_id: int
    subcategoria_nome: str | None = None
    descricao: str | None = None
    vencimento: date
    valor: Decimal
    recorrencia: str | None = None
    recorrencia_quantidade: int | None = None
    recorrencia_grupo: str | None = None
    status: str  # AGENDADO | PAGO | CANCELADO
    situacao: SituacaoPagar
    dias_atraso: int = 0
    pagamento: date | None = None
    tem_comprovante: bool = False
    motivo_cancelamento: str | None = None


class ChipPagar(Schema):
    situacao: str
    quantidade: int
    valor: Decimal


class PaginaPagar(Pagina[ContaPagarOut]):
    chips: list[ChipPagar]
    hoje: date


class ContaPagarIn(Entrada):
    fornecedor_id: int
    categoria_id: int
    subcategoria_id: int
    descricao: str | None = Field(default=None, max_length=200)
    vencimento: date
    valor: Decimal = Field(ge=0, max_digits=15, decimal_places=2)
    recorrencia: Literal["SEMANAL", "MENSAL", "ANUAL"] | None = None
    recorrencia_quantidade: int | None = Field(default=None, ge=1, le=120)


class ContaPagarEditarIn(Entrada):
    fornecedor_id: int | None = None
    categoria_id: int | None = None
    subcategoria_id: int | None = None
    descricao: str | None = Field(default=None, max_length=200)
    vencimento: date | None = None
    valor: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)


class CancelarPagarIn(Entrada):
    motivo: str = Field(min_length=3, max_length=500)


class CriarPagarOut(Schema):
    criadas: list[ContaPagarOut]


# ------------------------------------------------------------------------------------------------------- bancos
class ContaBancariaIn(Entrada):
    banco: str = Field(min_length=1, max_length=120)
    agencia: str = Field(min_length=1, max_length=20)
    conta: str = Field(min_length=1, max_length=20)
    saldo_inicial: Decimal = Field(default=Decimal("0"), max_digits=15, decimal_places=2)
    ativo: bool = True


class ContaBancariaOut(Schema):
    id: int
    banco: str
    agencia: str
    conta: str
    saldo_inicial: Decimal
    ativo: bool
    saldo_atual: Decimal  # SEMPRE calculado (saldo inicial + entradas - saídas); nunca gravado
    total_movimentos: int = 0


class MovimentoOut(Schema):
    id: int
    conta_id: int
    conta_nome: str | None = None
    tipo: str
    valor: Decimal
    data: date
    descricao: str | None = None
    tem_comprovante: bool = False
    conta_receber_id: int | None = None
    conta_pagar_id: int | None = None
    transferencia_id: str | None = None


class ExtratoOut(Schema):
    conta_id: int | None
    saldo_inicial_periodo: Decimal  # saldo no fim do dia anterior ao início do período
    total_entradas: Decimal
    total_saidas: Decimal
    saldo_final: Decimal
    movimentos: list[MovimentoOut]


class TransferenciaIn(Entrada):
    conta_origem_id: int
    conta_destino_id: int
    valor: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    data: date
    descricao: str | None = Field(default=None, max_length=200)


# -------------------------------------------------------------------------------------------------- relatórios
class LinhaFluxoOut(Schema):
    data: date
    tipo: str
    origem: str
    descricao: str
    detalhe: str
    status: str
    valor: Decimal


class DiaFluxoOut(Schema):
    data: date
    receitas: Decimal
    despesas: Decimal
    saldo: Decimal


class SemanaFluxoOut(Schema):
    inicio: date
    fim: date
    receitas: Decimal
    despesas: Decimal
    saldo: Decimal


class ComparativoOut(Schema):
    periodo: str
    receitas: Decimal
    despesas: Decimal
    saldo: Decimal
    delta_receitas: Decimal
    delta_despesas: Decimal
    delta_saldo: Decimal


class FluxoCaixaOut(Schema):
    inicio: date
    fim: date
    conta_id: int | None
    saldo_bancario_base: Decimal
    saldo_projetado_final: Decimal
    total_receitas: Decimal
    total_despesas: Decimal
    lancamentos: list[LinhaFluxoOut]
    saldo_diario: list[DiaFluxoOut]
    saldo_semanal: list[SemanaFluxoOut]
    comparativo_mes_anterior: ComparativoOut


class ItemAgrupadoOut(Schema):
    nome: str
    total: Decimal


class DreOut(Schema):
    inicio: date
    fim: date
    receita_bruta: Decimal
    deducoes: Decimal
    receita_liquida: Decimal
    custo_direto: Decimal
    lucro_bruto: Decimal
    despesas_operacionais: Decimal
    resultado_final: Decimal
    resultado_label: str
    saldo_bancario_anterior: Decimal
    saldo_bancario_final: Decimal
    receitas_por_plano: list[ItemAgrupadoOut]
    receitas_por_categoria: list[ItemAgrupadoOut]
    receitas_por_subcategoria: list[ItemAgrupadoOut]
    despesas_por_categoria: list[ItemAgrupadoOut]
    despesas_por_subcategoria: list[ItemAgrupadoOut]


# ----------------------------------------------------------------------------------------------- Receita Saúde
class ReceitaSaudeConfigIn(Entrada):
    cpf_profissional: str
    registro_profissional: str | None = Field(default=None, max_length=15)
    codigo_ocupacao: str = "231"
    descricao_padrao: str = Field(default="Aulas de Pilates", min_length=2, max_length=200)

    @field_validator("cpf_profissional")
    @classmethod
    def _cpf(cls, v: str) -> str:
        d = so_digitos(v)
        if not validar_cpf(d):
            raise ValueError("CPF do profissional inválido")
        return d


class ReceitaSaudeConfigOut(Schema):
    configurado: bool
    cpf_profissional: str | None = None
    registro_profissional: str | None = None
    codigo_ocupacao: str = "231"
    descricao_padrao: str = "Aulas de Pilates"
    ocupacoes: dict[str, str]
    problemas: list[str]


class ReciboItemOut(Schema):
    conta_id: int
    aluno_id: int
    aluno_nome: str
    pagamento: date | None
    vencimento: date
    valor: Decimal
    descricao: str | None
    competencia: str | None
    problemas: list[str]
    gerado_em: datetime | None
    pronto: bool  # sem problemas e ainda não gerado


class RecibosAlunoOut(Schema):
    aluno_id: int
    aluno_nome: str
    aluno_cpf: str | None
    sem_cpf: bool
    cpf_pagador_recibo: str | None
    config_ok: bool
    problemas_config: list[str]
    itens: list[ReciboItemOut]


class PagadorIn(Entrada):
    cpf: str | None = None


class ContasIdsIn(Entrada):
    conta_ids: list[int] = Field(min_length=1, max_length=5000)


class LoteOut(Schema):
    de: date
    ate: date
    config_ok: bool
    problemas_config: list[str]
    total: int
    prontos: int
    com_problema: int
    ja_gerados: int
    arquivos_previstos: int
    itens: list[ReciboItemOut]


class GerarLoteIn(Entrada):
    de: date
    ate: date
    conta_ids: list[int] | None = Field(default=None, max_length=20000)  # padrão: todas as prontas do período


# --------------------------------------------------------------------------------------------------- comissões
class ComissaoOut(Schema):
    id: int
    profissional_id: int
    profissional_nome: str | None = None
    conta_receber_id: int
    aluno_nome: str | None = None
    competencia: str
    valor_base: Decimal
    percentual: Decimal
    valor: Decimal
    paga_em: date | None = None


class ResumoProfissionalOut(Schema):
    profissional_id: int
    profissional_nome: str
    quantidade: int
    valor_total: Decimal
    valor_pendente: Decimal


class ComissoesOut(Schema):
    competencia: str | None
    itens: list[ComissaoOut]
    resumo: list[ResumoProfissionalOut]
    valor_total: Decimal
    valor_pendente: Decimal


class GerarComissaoIn(Entrada):
    competencia: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class GerarComissaoOut(Schema):
    competencia: str
    geradas: int
    valor_total: Decimal


class PagarComissaoIn(Entrada):
    comissao_ids: list[int] = Field(min_length=1, max_length=5000)
    data_pagamento: date | None = None


# ----------------------------------------------------------------------------------------- opções dos formulários
class OpcaoOut(Schema):
    id: int
    nome: str


class CategoriaOpcaoOut(Schema):
    id: int
    nome: str
    tipo: str
    subcategorias: list[OpcaoOut]


class OpcoesReceberOut(Schema):
    planos: list[OpcaoOut]
    contas_bancarias: list[OpcaoOut]


class OpcoesPagarOut(Schema):
    fornecedores: list[OpcaoOut]
    categorias: list[CategoriaOpcaoOut]
    contas_bancarias: list[OpcaoOut]
