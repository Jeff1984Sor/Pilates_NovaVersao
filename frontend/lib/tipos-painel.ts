/** Resposta de GET /painel/resumo (ver backend/app/modules/painel/schemas.py). Valores em dinheiro chegam como string. */

export interface KpiNumero {
  visivel: boolean;
  valor: number | null;
  href: string | null;
}

export interface KpiAulas {
  visivel: boolean;
  hoje: number | null;
  amanha: number | null;
  href: string | null;
}

export interface KpiValor {
  visivel: boolean;
  valor: string | null;
  quantidade: number | null;
  href: string | null;
}

export interface RecebidoMes {
  visivel: boolean;
  mes: string | null;
  valor: string | null;
  mes_anterior: string | null;
  anterior_ate_mesmo_dia: string | null;
  variacao_pct: number | null;
  href: string | null;
}

export interface AulasMes {
  mes: string;
  rotulo: string;
  total: number;
}

export interface ProfessorRanking {
  profissional_id: number;
  nome: string;
  total: number;
}

export interface ProximaAula {
  reserva_id: number;
  sessao_id: number;
  hora: string;
  aluno: string | null;
  professor: string | null;
  status: string;
}

export interface Aniversariante {
  aluno_id: number;
  nome: string;
  dia: string;
  idade: number;
  hoje: boolean;
}

export type GravidadeAlerta = "critico" | "aviso" | "info";

export interface AlertaPainel {
  chave: string;
  titulo: string;
  detalhe: string | null;
  quantidade: number;
  valor: string | null;
  gravidade: GravidadeAlerta;
  href: string | null;
}

export interface PassoInicial {
  chave: string;
  titulo: string;
  descricao: string;
  feito: boolean;
  href: string;
  conta: boolean;
}

export interface ResumoPainel {
  hoje: string;
  gerado_em: string;
  restrito: boolean;
  vazio: boolean;
  kpis: {
    alunos_ativos: KpiNumero;
    aulas: KpiAulas;
    contratos_vencendo: KpiNumero;
    a_receber: KpiValor;
    atrasado: KpiValor;
  };
  recebido_mes: RecebidoMes;
  aulas_por_mes: { visivel: boolean; meses: AulasMes[]; total: number };
  ranking_professores: { visivel: boolean; mes: string | null; itens: ProfessorRanking[] };
  proximas_aulas: { visivel: boolean; itens: ProximaAula[]; restantes: number; href: string | null };
  aniversariantes: { visivel: boolean; itens: Aniversariante[] };
  alertas: { visivel: boolean; itens: AlertaPainel[] };
  primeiros_passos: { visivel: boolean; completo: boolean; passos: PassoInicial[] };
}
