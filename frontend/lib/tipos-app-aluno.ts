// Tipos do app do aluno (backend/app/modules/app_aluno/schemas.py) e do assistente de IA do cadastro
// (backend/app/modules/ia_cadastro).

export interface AlunoMe {
  nome: string;
  primeiro_nome: string;
  unidade: string | null;
}

export type StatusAulaExibido = "aguardando_chegar" | "em_aula" | "finalizada" | "faltou" | "remarcada";

export interface AulaAluno {
  id: number; // id da reserva
  data: string; // AAAA-MM-DD
  hora_inicio: string; // HH:MM:SS
  hora_fim: string;
  servico: string | null;
  profissional: string | null;
  unidade: string | null;
  status: StatusAulaExibido;
  confirmada: boolean;
  confirmada_em: string | null;
  pode_confirmar: boolean;
  pode_desmarcar: boolean;
}

export interface DesmarcarResp {
  mensagem: string;
  reposicao_ate: string | null;
}

export interface ReposicaoAluno {
  id: number; // id da reserva desmarcada
  data: string;
  hora_inicio: string;
  servico: string | null;
  profissional: string | null;
  desmarcada_em: string | null;
  reposicao_ate: string;
  dias_restantes: number;
  dentro_do_prazo: boolean;
}

export interface OpcaoReposicao {
  aula_id: number;
  data: string;
  hora_inicio: string;
  hora_fim: string;
  profissional: string | null;
  vagas: number;
}

// ---------------------------------------------------------------------------------------- assistente de IA
/** Campos que o assistente sabe preencher no cadastro do aluno. Todos opcionais: só vêm os que foram lidos. */
export interface DadosAssistenteIA {
  nome?: string;
  /** só dígitos (11) */
  cpf?: string;
  rg?: string;
  /** AAAA-MM-DD */
  data_nascimento?: string;
  logradouro?: string;
  numero?: string;
  bairro?: string;
  cidade?: string;
  /** só dígitos (8) */
  cep?: string;
}

export type ChaveCampoIA = keyof DadosAssistenteIA;

export interface CampoRascunhoIA {
  chave: ChaveCampoIA;
  rotulo: string;
  valor: string | null;
  incerto: boolean;
  aviso: string | null;
}

export interface RascunhoIA {
  tipo: "documento" | "comprovante";
  rascunho: true;
  dados: Record<string, string | null>;
  campos: CampoRascunhoIA[];
  avisos: string[];
}

export interface StatusIA {
  disponivel: boolean;
  provedor: string | null;
  mensagem: string | null;
}
