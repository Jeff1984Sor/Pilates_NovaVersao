// Tipos da API de contratos (espelham backend/app/modules/contratos/schemas.py). Valores em dinheiro chegam como string decimal.

export type ChipContrato = "ativos" | "vencendo" | "vencidos" | "nao_assinados" | "todos";
export type StatusAssinatura = "NAO_ASSINADO" | "ASSINADO" | "ASSINADO_DIGITALMENTE";
export type FormaPagamento = "DINHEIRO" | "PIX" | "CREDITO" | "DEBITO";

export const FORMAS_PAGAMENTO_CONTRATO: { value: FormaPagamento; label: string }[] = [
  { value: "PIX", label: "Pix" },
  { value: "DINHEIRO", label: "Dinheiro" },
  { value: "CREDITO", label: "Cartão de crédito" },
  { value: "DEBITO", label: "Cartão de débito" },
];

export const DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

export interface PessoaRef {
  id: number;
  nome: string;
}

export interface Situacao {
  rotulo: string;
  badge: "danger" | "warning" | "success";
  dias_restantes: number;
}

export interface ContratoResumo {
  id: number;
  numero: number;
  aluno: PessoaRef;
  plano: PessoaRef;
  unidade: PessoaRef;
  profissional: PessoaRef;
  data_inicio: string;
  data_fim: string;
  valor_aula: string | null;
  valor_parcela: string;
  valor_total: string;
  forma_pagamento: FormaPagamento | null;
  status_assinatura: StatusAssinatura;
  situacao: Situacao;
  parcelas_abertas: number;
  aulas_futuras: number;
  pdf_documento_id: number | null;
}

export interface ContagensContratos {
  ativos: number;
  vencendo: number;
  vencidos: number;
  nao_assinados: number;
  total: number;
}

export interface ListaContratos {
  itens: ContratoResumo[];
  total: number;
  pagina: number;
  por_pagina: number;
  chip: ChipContrato;
  contagens: ContagensContratos;
}

export interface ParcelaContrato {
  id: number;
  vencimento: string;
  competencia: string | null;
  valor: string;
  situacao: string;
}

export interface AssinaturaContrato {
  nome: string | null;
  documento: string | null;
  ip: string | null;
  assinado_em: string | null;
  imagem_url: string | null;
}

export interface ContratoDetalhe extends ContratoResumo {
  tipo_servico_id: number;
  aulas_por_semana: number;
  duracao_meses: number;
  avulso: boolean;
  recorrencia: string;
  valor_do_plano: string;
  valores_divergem_do_plano: boolean;
  parcelas: ParcelaContrato[];
  assinatura: AssinaturaContrato;
  precisa_agenda: boolean;
  aluno_email: string | null;
  aluno_telefone: string | null;
  avisos: string[];
}

export interface ContratoCriado {
  contrato: ContratoDetalhe;
  parcelas_criadas: number;
  pdf_documento_id: number;
  proximo_passo: "agenda" | "nenhum";
}

export interface ParcelaPrevista {
  numero: number;
  vencimento: string;
  competencia: string;
  valor: string;
}

export interface Precificacao {
  plano_id: number;
  plano_nome: string;
  avulso: boolean;
  aulas_por_semana: number;
  duracao_meses: number;
  valor_mensal: string;
  valor_aula: string | null;
  valor_parcela: string;
  valor_total: string;
  data_inicio: string;
  data_fim: string;
  data_fim_sugerida: string;
  parcelas: ParcelaPrevista[];
}

export interface PlanoOpcao {
  id: number;
  nome: string;
  valor: string;
  aulas_por_semana: number;
  duracao_meses: number;
  avulso: boolean;
  tipo_servico_id: number;
}

export interface OpcoesContrato {
  planos: PlanoOpcao[];
  unidades: PessoaRef[];
  profissionais: PessoaRef[];
  formas_pagamento: string[];
  whatsapp_disponivel: boolean;
}

export interface ContaExclusao {
  id: number;
  vencimento: string;
  valor: string;
  situacao: string;
}

export interface PlanoExclusao {
  pode_excluir: boolean;
  motivos_bloqueio: string[];
  alternativa: string | null;
  contas_a_excluir: ContaExclusao[];
  contas_pagas: ContaExclusao[];
  comissoes: number;
  reservas_a_excluir: { id: number; data: string; inicio: string; status: string }[];
  reservas_mantidas: number;
  sessoes_que_ficam_vazias: number;
  documento_pdf_sera_excluido: boolean;
  resumo: string;
}

export interface Encerramento {
  contrato: ContratoDetalhe;
  parcelas_canceladas: number;
  reservas_removidas: number;
  reservas_mantidas: number;
}

export interface Recalculo {
  simulacao: boolean;
  verificados: number;
  alterados: number;
  itens: {
    contrato_id: number;
    numero: number;
    aluno: string;
    plano: string;
    antes: Record<string, string | null>;
    depois: Record<string, string | null>;
  }[];
}

export interface Slot {
  dia_semana: number;
  inicio: string;
  fim: string;
  valor: string;
  profissionais: PessoaRef[];
}

export interface AgendaOpcoes {
  contrato_id: number;
  aulas_por_semana: number;
  exatamente: number;
  inicio: string;
  fim: string;
  slots: Slot[];
  ja_agendadas: number;
  dias_semana_agendados: number[];
  mensagem: string | null;
}

export interface ResultadoAgenda {
  reservas_criadas: number;
  sessoes_criadas: number;
  ja_existentes: number;
  conflitos: string[];
  mensagem_conflitos: string | null;
}

export interface LinkAssinatura {
  url: string;
  expira_em: string;
  pdf_url: string;
}

export interface Envio {
  canal: "email" | "whatsapp";
  destino: string;
  mensagem: string;
}

// ------------------------------------------------------------------------------------------- páginas públicas
export interface ContratoPublico {
  estado: "pendente" | "assinado";
  estudio_nome: string;
  numero: number;
  aluno_primeiro_nome: string;
  assinado_em: string | null;
  html: string | null;
}

export interface TermoPublico {
  estado: "pendente" | "assinado";
  estudio_nome: string;
  aluno_primeiro_nome: string;
  termo_nome: string | null;
  assinado_em: string | null;
  html: string | null;
}

export interface Assinado {
  mensagem: string;
  assinado_em: string;
}
