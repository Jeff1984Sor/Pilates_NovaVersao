// Tipos da API de comunicação (espelham backend/app/modules/comunicacao/schemas.py).
// Nenhum tipo carrega o valor da credencial do WhatsApp: ela é somente escrita.

export type ProvedorWhatsapp = "wasender" | "evolution";
export type PublicoComunicado = "ativos" | "inativos" | "todos";

export interface AvisoConfig {
  tipo: string;
  rotulo: string;
  ativo: boolean;
  /** "HH:MM:SS" */
  horario: string;
  campo_texto: string;
}

export interface ConfigWhatsapp {
  unidade_id: number;
  unidade_nome: string;
  existe: boolean;
  provedor: ProvedorWhatsapp;
  url_api: string | null;
  instancia: string | null;
  credencial_definida: boolean;
  /** só os 4 últimos caracteres */
  credencial_final: string | null;
  acompanhar_envios: boolean;
  numero_acompanhamento: string | null;
  pausa_segundos: number;
  pix_tipo: string | null;
  pix_chave: string | null;
  enviar_link_contrato: boolean;
  avisar_fim_contrato: boolean;
  avisos: AvisoConfig[];
  textos: Record<string, string>;
  envio_automatico_ativo: boolean;
}

export interface ConfigWhatsappEntrada {
  provedor: ProvedorWhatsapp;
  url_api: string | null;
  instancia: string | null;
  credencial: string | null;
  limpar_credencial: boolean;
  acompanhar_envios: boolean;
  numero_acompanhamento: string | null;
  pausa_segundos: number;
  pix_tipo: string | null;
  pix_chave: string | null;
  enviar_link_contrato: boolean;
  avisar_fim_contrato: boolean;
  avisos: Record<string, { ativo: boolean; horario: string }>;
  textos: Record<string, string | null>;
}

export interface ResumoUnidadeWhatsapp {
  unidade_id: number;
  unidade_nome: string;
  configurado: boolean;
  provedor: ProvedorWhatsapp | null;
  avisos_ligados: number;
}

export interface TesteConexao {
  conectada: boolean | null;
  detalhe: string;
}

export interface CampoTextoPadrao {
  campo: string;
  rotulo: string;
  padrao: string;
  variaveis: string[];
}

export interface TextosPadrao {
  campos: CampoTextoPadrao[];
  variaveis_estudio: string[];
}

export interface MensagemWhatsapp {
  id: number;
  aluno_id: number;
  aluno_nome: string | null;
  tipo: string;
  tipo_rotulo: string;
  direcao: "enviada" | "recebida";
  telefone: string | null;
  mensagem: string;
  status: string;
  detalhe: string | null;
  enviado_em: string;
}

export interface EnvioResultado {
  enviado: boolean;
  mensagem: string;
}

export interface PreviaComunicado {
  total: number;
  com_telefone: number;
  sem_telefone: number;
  primeiro_aluno: string | null;
  mensagem: string;
}

export type StatusComunicado = "enviando" | "pausado" | "cancelado" | "concluido";

export interface Comunicado {
  id: number;
  status: StatusComunicado;
  texto: string;
  publico: PublicoComunicado;
  unidade_id: number | null;
  pausa_segundos: number;
  aviso: string | null;
  total: number;
  enviados: number;
  falhas: number;
  sem_telefone: number;
  pendentes: number;
  cancelados: number;
  percentual: number;
  criado_em: string;
  finalizado_em: string | null;
}

export interface DestinatarioComunicado {
  aluno_id: number;
  nome: string;
  telefone: string | null;
  status: "pendente" | "enviando" | "enviado" | "falha" | "sem_telefone" | "cancelado";
  erro: string | null;
  enviado_em: string | null;
}

export interface AvisoAlunoPrevia {
  aluno_nome: string;
  mensagem: string;
  tem_celular: boolean;
}

export interface EnvioAutomatico {
  id: number;
  tipo: string;
  tipo_rotulo: string;
  unidade_id: number | null;
  data_referencia: string;
  destinatario: string | null;
  status: string;
  mensagem: string;
  enviado_em: string;
}

export interface Acompanhamento {
  envio_automatico_ativo: boolean;
  /** contagem por status nas últimas 24 h */
  hoje: Record<string, number>;
  itens: EnvioAutomatico[];
  total: number;
}

export interface StatusWhatsapp {
  unidades_configuradas: number;
  envio_automatico_ativo: boolean;
}

export const ROTULO_STATUS_MENSAGEM: Record<string, string> = {
  sent: "Enviada",
  failed: "Falhou",
  sem_telefone: "Sem telefone",
  sessao_caida: "Sessão desconectada",
  credencial_recusada: "Credencial recusada",
  pendente: "Em andamento",
  resumo: "Resumo",
};

export const ROTULO_STATUS_DESTINATARIO: Record<string, string> = {
  pendente: "Na fila",
  enviando: "Enviando",
  enviado: "Enviado",
  falha: "Falhou",
  sem_telefone: "Sem telefone",
  cancelado: "Cancelado",
};

export const ROTULO_PUBLICO: Record<PublicoComunicado, string> = {
  ativos: "Alunos ativos",
  inativos: "Alunos inativos",
  todos: "Todos os alunos",
};
