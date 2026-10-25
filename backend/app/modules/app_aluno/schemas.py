from datetime import date, datetime, time

from pydantic import BaseModel, Field


class CodigoIn(BaseModel):
    cpf: str = Field(max_length=30)


class VerificarIn(BaseModel):
    cpf: str = Field(max_length=30)
    codigo: str = Field(max_length=12)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=2000)


class Mensagem(BaseModel):
    mensagem: str


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    expira_em_segundos: int
    token_type: str = "bearer"


class MeOut(BaseModel):
    nome: str
    primeiro_nome: str
    unidade: str | None = None


class AulaOut(BaseModel):
    id: int  # id da reserva (é o que o aluno usa para confirmar/desmarcar)
    data: date
    hora_inicio: time
    hora_fim: time
    servico: str | None = None
    profissional: str | None = None
    unidade: str | None = None
    status: str  # status exibido: aguardando_chegar, em_aula, finalizada, faltou, remarcada
    confirmada: bool
    confirmada_em: datetime | None = None
    pode_confirmar: bool
    pode_desmarcar: bool


class DesmarcarOut(BaseModel):
    mensagem: str
    reposicao_ate: date | None = None


class ReposicaoOut(BaseModel):
    id: int  # id da reserva desmarcada
    data: date
    hora_inicio: time
    servico: str | None = None
    profissional: str | None = None
    desmarcada_em: datetime | None = None
    reposicao_ate: date
    dias_restantes: int
    dentro_do_prazo: bool


class OpcaoReposicaoOut(BaseModel):
    aula_id: int
    data: date
    hora_inicio: time
    hora_fim: time
    profissional: str | None = None
    vagas: int


class RemarcarIn(BaseModel):
    aula_id: int
