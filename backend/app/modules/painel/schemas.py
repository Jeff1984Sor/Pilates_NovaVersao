"""Contrato da resposta de ``GET /api/painel/resumo``.

Todo bloco traz ``visivel``: sem a permissão do assunto o bloco nem é calculado (``visivel=False`` e dados vazios).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class KpiNumero(BaseModel):
    visivel: bool = False
    valor: int | None = None
    href: str | None = None


class KpiAulas(BaseModel):
    visivel: bool = False
    hoje: int | None = None
    amanha: int | None = None
    href: str | None = None


class KpiValor(BaseModel):
    visivel: bool = False
    valor: Decimal | None = None
    quantidade: int | None = None
    href: str | None = None


class Kpis(BaseModel):
    alunos_ativos: KpiNumero = Field(default_factory=KpiNumero)
    aulas: KpiAulas = Field(default_factory=KpiAulas)
    contratos_vencendo: KpiNumero = Field(default_factory=KpiNumero)  # fim do contrato nos próximos 30 dias
    a_receber: KpiValor = Field(default_factory=KpiValor)  # em aberto e ainda não vencido
    atrasado: KpiValor = Field(default_factory=KpiValor)  # em aberto e vencido antes de hoje


class RecebidoMes(BaseModel):
    visivel: bool = False
    mes: str | None = None  # AAAA-MM
    valor: Decimal | None = None  # recebido de 1º do mês até hoje
    mes_anterior: Decimal | None = None  # total do mês anterior inteiro
    anterior_ate_mesmo_dia: Decimal | None = None  # mês anterior até o mesmo dia (comparação justa)
    variacao_pct: float | None = None  # valor vs anterior_ate_mesmo_dia; None quando não há base
    href: str | None = None


class AulasMes(BaseModel):
    mes: str  # AAAA-MM
    rotulo: str  # "out/26"
    total: int


class AulasPorMes(BaseModel):
    visivel: bool = False
    meses: list[AulasMes] = []
    total: int = 0


class ProfessorRanking(BaseModel):
    profissional_id: int
    nome: str
    total: int


class RankingProfessores(BaseModel):
    visivel: bool = False
    mes: str | None = None
    itens: list[ProfessorRanking] = []


class ProximaAula(BaseModel):
    reserva_id: int
    sessao_id: int
    hora: str  # HH:MM
    aluno: str | None  # None quando o perfil não pode ver alunos (Professor)
    professor: str | None
    status: str


class ProximasAulas(BaseModel):
    visivel: bool = False
    itens: list[ProximaAula] = []
    restantes: int = 0  # quantas além das listadas
    href: str | None = None


class Aniversariante(BaseModel):
    aluno_id: int
    nome: str
    dia: date  # próxima ocorrência do aniversário
    idade: int  # idade que completa
    hoje: bool


class Aniversariantes(BaseModel):
    visivel: bool = False
    itens: list[Aniversariante] = []


class Alerta(BaseModel):
    chave: str
    titulo: str
    detalhe: str | None = None
    quantidade: int = 0
    valor: Decimal | None = None
    gravidade: str = "aviso"  # "critico" | "aviso" | "info"
    href: str | None = None


class Alertas(BaseModel):
    visivel: bool = False
    itens: list[Alerta] = []


class PassoInicial(BaseModel):
    chave: str
    titulo: str
    descricao: str
    feito: bool
    href: str
    conta: bool = True  # False = sugestão que não segura o "Primeiros passos" na tela


class PrimeirosPassos(BaseModel):
    visivel: bool = False
    completo: bool = True
    passos: list[PassoInicial] = []


class ResumoPainel(BaseModel):
    hoje: date
    gerado_em: datetime
    restrito: bool = False  # perfil Professor: só as próprias aulas
    vazio: bool = False  # instalação nova, sem aluno cadastrado
    kpis: Kpis
    recebido_mes: RecebidoMes
    aulas_por_mes: AulasPorMes
    ranking_professores: RankingProfessores
    proximas_aulas: ProximasAulas
    aniversariantes: Aniversariantes
    alertas: Alertas
    primeiros_passos: PrimeirosPassos
