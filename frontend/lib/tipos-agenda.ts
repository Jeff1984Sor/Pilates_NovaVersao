/** Tipos da API da agenda (backend/app/modules/agenda). Datas "YYYY-MM-DD", horas "HH:MM". */

export type StatusReserva =
  | "RESERVADA"
  | "CONCLUIDA"
  | "FALTOU_AVISOU"
  | "FALTOU_SEM_AVISAR"
  | "CANCELADA"
  | "PENDENTE";

/** Status exibido (R5), calculado no servidor pelo domínio. */
export type StatusAula = "aguardando_chegar" | "em_aula" | "finalizada" | "faltou" | "remarcada";

export const ROTULO_STATUS_AULA: Record<StatusAula, string> = {
  aguardando_chegar: "Aguardando",
  em_aula: "Em aula",
  finalizada: "Finalizada",
  faltou: "Faltou",
  remarcada: "Remarcada",
};

export const ROTULO_STATUS_RESERVA: Record<StatusReserva, string> = {
  RESERVADA: "Reservada",
  CONCLUIDA: "Concluída",
  FALTOU_AVISOU: "Faltou (avisou)",
  FALTOU_SEM_AVISAR: "Faltou",
  CANCELADA: "Desmarcada",
  PENDENTE: "Pendente",
};

export interface OpcaoUnidade {
  id: number;
  nome: string;
  capacidade: number;
  duracao_aula_minutos: number;
}
export interface OpcaoProfissional {
  id: number;
  nome: string;
  iniciais: string;
}
export interface OpcaoServico {
  id: number;
  nome: string;
}
export interface OpcaoPlanoAvulso {
  id: number;
  nome: string;
  valor: string;
  tipo_servico_id: number;
  recorrencia: "SEMANAL" | "MENSAL";
}
export interface ModeloEvolucao {
  id: number;
  titulo: string;
  texto: string;
}
export interface OpcoesAgenda {
  unidades: OpcaoUnidade[];
  profissionais: OpcaoProfissional[];
  servicos: OpcaoServico[];
  planos_avulsos: OpcaoPlanoAvulso[];
  modelos_evolucao: ModeloEvolucao[];
}

// ------------------------------------------------------------------------------------------------ grade semanal
export interface BlocoGrade {
  sessao_id: number;
  reserva_id: number | null;
  aluno_id: number | null;
  aluno: string | null;
  status: StatusReserva | null;
  cor: string;
  situacao: string;
  hora: string;
  hora_fim: string;
  servico: string;
  profissional_id: number | null;
  profissional: string | null;
  unidade: string;
  ocupacao: string | null;
  capacidade: number;
  ocupadas: number;
  inicio_min: number;
  fim_min: number;
  coluna: number;
  colunas: number;
}
export interface DiaGrade {
  data: string;
  rotulo: string;
  numero: number;
  hoje: boolean;
  blocos: BlocoGrade[];
}
export interface GradeSemanal {
  semana_inicio: string;
  semana_fim: string;
  rotulo: string;
  anterior: string;
  proxima: string;
  hoje: string;
  grade_inicio_min: number;
  grade_fim_min: number;
  legenda: { cor: string; rotulo: string }[];
  dias: DiaGrade[];
}

// ------------------------------------------------------------------------------------------ painel operacional
export interface CartaoAula {
  id: number;
  aula_sessao_id: number;
  data: string;
  hora_inicio: string;
  hora_fim: string;
  dt_inicio: string;
  dt_fim: string;
  unidade_id: number;
  unidade: string;
  profissional: { id: number; nome: string } | null;
  aluno: { id: number; nome: string; iniciais: string; telefone: string | null };
  plano: { id: number | null; descricao: string | null };
  servico: string;
  servicos: string[];
  status: StatusReserva;
  status_aula: StatusAula;
  rotulo_status: string;
  confirmacao: boolean;
  confirmada_em: string | null;
  reposicao_ate: string | null;
  flags: { tem_preliminares: boolean; cobranca_pendente: boolean | null };
  ultima_evolucao: { texto: string | null; criado_em: string | null };
  whatsapp: { disponivel: boolean; motivo: string };
  permite?: PermissoesAula;
}
export interface PermissoesAula {
  chegou: boolean;
  finalizar: boolean;
  faltou: boolean;
  remarcar: boolean;
  desmarcar: boolean;
  excluir: boolean;
  confirmar: boolean;
  evolucao: boolean;
  avaliacao: boolean;
  cobranca: boolean;
}
export interface GrupoProfissional {
  profissional_id: number | null;
  nome: string;
  iniciais: string;
  cor_indice: number;
  total: number;
  cartoes: CartaoAula[];
}
export interface HorarioPainel {
  hora_inicio: string;
  hora_fim: string;
  total: number;
  profissionais: GrupoProfissional[];
}
export interface DiaPainel {
  data: string;
  rotulo: string;
  total: number;
  horarios: HorarioPainel[];
}
export interface Painel {
  data_inicio: string;
  data_fim: string;
  periodo: "hoje" | "amanha" | "semana";
  total: number;
  pode_ver_cobranca: boolean;
  dias: DiaPainel[];
}

// ------------------------------------------------------------------------------------ gaveta e ficha do aluno
export interface ReservaResumo {
  id: number;
  aluno_id: number;
  sessao_id: number;
  data: string;
  hora_inicio: string;
  hora_fim: string;
  profissional_id: number | null;
  status: StatusReserva;
  confirmada_em: string | null;
  desmarcada_em: string | null;
  reposicao_ate: string | null;
  contrato_id: number | null;
  ocupacao: string;
}
export interface HistoricoAula {
  id: number;
  data: string;
  hora_inicio: string;
  hora_fim: string;
  unidade: string;
  profissional: string | null;
  servico: string;
  status: StatusReserva;
  status_aula: StatusAula;
  rotulo_status: string;
}
export interface CobrancaAluno {
  id: number;
  descricao: string | null;
  competencia: string | null;
  vencimento: string;
  pagamento: string | null;
  status: "ABERTO" | "PAGO" | "CANCELADO" | "ATRASADO";
  valor: string;
  contrato_id: number | null;
  reserva_id: number | null;
}
export interface AulaDoAluno extends Omit<CartaoAula, "whatsapp" | "permite"> {
  tipo: "regular" | "contrato" | "avulsa" | "avaliativa";
  contrato_id: number | null;
  aula_avulsa_id: number | null;
  aula_avaliativa_id: number | null;
  evolucoes: number;
  avaliacoes: number;
}
export interface Registro {
  id: number;
  reserva_id: number;
  aluno_id: number;
  texto: string;
  criado_em: string;
  atualizado_em: string | null;
  profissional_id: number;
  profissional: string | null;
  data_aula: string;
  hora_inicio: string;
  status_reserva?: StatusReserva;
}
export interface MelhoriaTexto {
  texto: string;
  melhorado: boolean;
  aviso: string | null;
}
export interface HorarioRemarcacao {
  sessao_id: number | null;
  data: string;
  hora_inicio: string;
  hora_fim: string;
  profissional_id: number | null;
  profissional: string | null;
  vagas: number;
  rotulo: string;
}

export type TipoAvaliativa = "AVALIATIVA" | "TOTALPASS" | "WELLHUB";
export type StatusAvaliativa = "AGENDADA" | "REALIZADA" | "CANCELADA" | "CONVERTIDA";
export interface AulaAvaliativa {
  id: number;
  tipo: TipoAvaliativa;
  aluno_id: number;
  unidade_id: number;
  profissional_id: number;
  tipo_servico_id: number | null;
  data: string;
  hora_inicio: string;
  hora_fim: string;
  status: StatusAvaliativa;
  queixa_principal: string | null;
  objetivos: string | null;
  historico_saude: string | null;
  observacoes: string | null;
  contrato_id: number | null;
}
export interface SlotAvulsa {
  dia_semana: number;
  inicio: string;
  fim: string;
  valor: string;
  profissionais: { id: number; nome: string }[];
}
export interface ResultadoAvulsa {
  id: number;
  quantidade: number;
  valor_aula: string;
  valor_total: string;
  reservas: number[];
  contas: { id: number; reserva_id: number; valor: string; vencimento: string }[];
  conflitos: string[];
  aviso: string | null;
}
