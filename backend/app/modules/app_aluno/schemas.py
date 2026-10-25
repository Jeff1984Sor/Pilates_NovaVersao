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
    desmarcar_ate: str | None = None  # regra das 6 horas: "26/10 às 03:00"


class DesmarcarOut(BaseModel):
    mensagem: str
    reposicao_ate: date | None = None


class PedidoAlunoOut(BaseModel):
    status: str  # PENDENTE | APROVADO | RECUSADO
    preferencia: str | None = None
    pedido_em: datetime
    aprovado_data: date | None = None
    aprovado_hora: time | None = None
    motivo_recusa: str | None = None


class ReposicaoOut(BaseModel):
    id: int  # id da reserva desmarcada (é o que se usa para pedir)
    data: date
    hora_inicio: time
    servico: str | None = None
    profissional: str | None = None
    desmarcada_em: datetime | None = None
    reposicao_ate: date
    dias_restantes: int
    dentro_do_prazo: bool
    pode_pedir: bool
    pedido: PedidoAlunoOut | None = None


class OpcaoReposicaoOut(BaseModel):
    aula_id: int
    data: date
    hora_inicio: time
    hora_fim: time
    profissional: str | None = None
    vagas: int


class PedirIn(BaseModel):
    preferencia: str | None = Field(default=None, max_length=300)  # dias/horários que o aluno prefere, texto livre


class AprovarIn(BaseModel):
    aula_id: int
    ignorar_prazo: bool = False
    motivo: str | None = Field(default=None, max_length=300)


class RecusarIn(BaseModel):
    motivo: str = Field(max_length=300)
