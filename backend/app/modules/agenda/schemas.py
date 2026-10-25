"""Entradas (Pydantic) da API da agenda. As saídas são dicionários montados em ``consultas.py``/``servico.py``."""

from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class Entrada(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SessaoIn(Entrada):
    unidade_id: int
    tipo_servico_id: int
    profissional_id: int | None = None
    data: date
    hora_inicio: time
    hora_fim: time | None = None
    capacidade: int | None = Field(default=None, ge=0, le=500, description="Vazio = herda a capacidade da unidade")


class SessaoPatch(Entrada):
    """Só os campos enviados são alterados (``capacidade: null`` volta a herdar da unidade)."""

    unidade_id: int | None = None
    tipo_servico_id: int | None = None
    profissional_id: int | None = None
    data: date | None = None
    hora_inicio: time | None = None
    hora_fim: time | None = None
    capacidade: int | None = Field(default=None, ge=0, le=500)


class GerarSessoesIn(Entrada):
    unidade_id: int
    tipo_servico_id: int
    profissional_id: int | None = None
    data_inicio: date
    data_fim: date
    capacidade: int | None = Field(default=None, ge=0, le=500)


class ReservaIn(Entrada):
    """Reserva numa aula existente (``sessao_id``) ou no horário informado (a aula é criada se não existir)."""

    aluno_id: int
    sessao_id: int | None = None
    unidade_id: int | None = None
    tipo_servico_id: int | None = None
    profissional_id: int | None = None
    data: date | None = None
    hora_inicio: time | None = None
    hora_fim: time | None = None


class PresencaIn(Entrada):
    acao: str = Field(description="chegou | iniciar | finalizar | faltou | faltou_avisou")


class RemarcarIn(Entrada):
    data: date
    hora_inicio: time
    profissional_id: int | None = None
    ignorar_prazo_reposicao: bool = False


class EvolucaoIn(Entrada):
    texto: str | None = None
    profissional_id: int | None = None
    modelo_evolucao_id: int | None = None
    finalizar: bool = False
    status: str | None = Field(default=None, description="CONCLUIDA | FALTOU_AVISOU | FALTOU_SEM_AVISAR")


class AvaliacaoIn(Entrada):
    texto: str | None = None
    profissional_id: int | None = None


class TextoIn(Entrada):
    texto: str | None = None


class MelhorarIn(Entrada):
    texto: str = Field(min_length=1, max_length=8000)


class AvulsaIn(Entrada):
    aluno_id: int
    plano_id: int
    unidade_id: int
    profissional_id: int
    quantidade: int = Field(default=1, ge=1, le=60)
    data_inicio: date
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: time
    hora_fim: time | None = None
    valor_aula: Decimal | None = Field(default=None, ge=0, description="Vazio = valor do plano; 0 = sem cobrança")


class AvaliativaIn(Entrada):
    aluno_id: int
    unidade_id: int
    profissional_id: int
    tipo_servico_id: int
    data: date
    hora_inicio: time
    tipo: str = "AVALIATIVA"


class FichaAvaliativaIn(Entrada):
    queixa_principal: str | None = None
    objetivos: str | None = None
    historico_saude: str | None = None
    observacoes: str | None = None
    status: str | None = None
