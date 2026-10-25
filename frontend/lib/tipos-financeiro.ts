// Tipos da API do financeiro (espelham backend/app/modules/financeiro/schemas.py). Valores monetários chegam como string decimal.

import type { Pagina } from "@/lib/types";

export type SituacaoReceber = "ABERTO" | "PAGO" | "ATRASADO" | "CANCELADO";
export type SituacaoPagar = "AGENDADO" | "PAGO" | "ATRASADO" | "CANCELADO";
export type FormaPagamento = "DINHEIRO" | "PIX" | "CREDITO" | "DEBITO";

export const FORMAS_PAGAMENTO: { value: FormaPagamento; label: string }[] = [
  { value: "PIX", label: "Pix" },
  { value: "DINHEIRO", label: "Dinheiro" },
  { value: "CREDITO", label: "Cartão de crédito" },
  { value: "DEBITO", label: "Cartão de débito" },
];

export interface Chip {
  situacao: "TODOS" | SituacaoReceber | SituacaoPagar;
  quantidade: number;
  valor: string;
}

export interface ContaReceber {
  id: number;
  aluno_id: number;
  aluno_nome: string | null;
  contrato_id: number | null;
  contrato_numero: number | null;
  reserva_id: number | null;
  descricao: string | null;
  origem: string;
  plano_nome: string | null;
  subcategoria_nome: string | null;
  status: "ABERTO" | "PAGO" | "CANCELADO";
  situacao: SituacaoReceber;
  dias_atraso: number;
  valor: string;
  vencimento: string;
  competencia: string | null;
  pagamento: string | null;
  forma_pagamento: string | null;
  motivo_cancelamento: string | null;
  recibo_saude_gerado_em: string | null;
}

export interface PaginaReceber extends Pagina<ContaReceber> {
  chips: Chip[];
  hoje: string;
}

export interface ResumoAluno {
  aluno_id: number;
  total_aberto: string;
  total_atrasado: string;
  total_pago: string;
  qtd_aberto: number;
  qtd_atrasado: number;
  qtd_pago: number;
  proximo_vencimento: string | null;
  em_dia: boolean;
}

export interface ContaPagar {
  id: number;
  fornecedor_id: number;
  fornecedor_nome: string | null;
  categoria_id: number;
  categoria_nome: string | null;
  subcategoria_id: number;
  subcategoria_nome: string | null;
  descricao: string | null;
  vencimento: string;
  valor: string;
  recorrencia: "SEMANAL" | "MENSAL" | "ANUAL" | null;
  recorrencia_quantidade: number | null;
  recorrencia_grupo: string | null;
  status: "AGENDADO" | "PAGO" | "CANCELADO";
  situacao: SituacaoPagar;
  dias_atraso: number;
  pagamento: string | null;
  tem_comprovante: boolean;
  motivo_cancelamento: string | null;
}

export interface PaginaPagar extends Pagina<ContaPagar> {
  chips: Chip[];
  hoje: string;
}

export interface ContaBancaria {
  id: number;
  banco: string;
  agencia: string;
  conta: string;
  saldo_inicial: string;
  ativo: boolean;
  saldo_atual: string;
  total_movimentos: number;
}

export interface Movimento {
  id: number;
  conta_id: number;
  conta_nome: string | null;
  tipo: "ENTRADA" | "SAIDA";
  valor: string;
  data: string;
  descricao: string | null;
  tem_comprovante: boolean;
  conta_receber_id: number | null;
  conta_pagar_id: number | null;
  transferencia_id: string | null;
}

export interface Extrato {
  conta_id: number | null;
  saldo_inicial_periodo: string;
  total_entradas: string;
  total_saidas: string;
  saldo_final: string;
  movimentos: Movimento[];
}

export interface FluxoCaixa {
  inicio: string;
  fim: string;
  conta_id: number | null;
  saldo_bancario_base: string;
  saldo_projetado_final: string;
  total_receitas: string;
  total_despesas: string;
  lancamentos: { data: string; tipo: "Receita" | "Despesa"; origem: string; descricao: string; detalhe: string; status: string; valor: string }[];
  saldo_diario: { data: string; receitas: string; despesas: string; saldo: string }[];
  saldo_semanal: { inicio: string; fim: string; receitas: string; despesas: string; saldo: string }[];
  comparativo_mes_anterior: {
    periodo: string;
    receitas: string;
    despesas: string;
    saldo: string;
    delta_receitas: string;
    delta_despesas: string;
    delta_saldo: string;
  };
}

export interface ItemAgrupado {
  nome: string;
  total: string;
}

export interface Dre {
  inicio: string;
  fim: string;
  receita_bruta: string;
  deducoes: string;
  receita_liquida: string;
  custo_direto: string;
  lucro_bruto: string;
  despesas_operacionais: string;
  resultado_final: string;
  resultado_label: "Lucro" | "Prejuizo";
  saldo_bancario_anterior: string;
  saldo_bancario_final: string;
  receitas_por_plano: ItemAgrupado[];
  receitas_por_categoria: ItemAgrupado[];
  receitas_por_subcategoria: ItemAgrupado[];
  despesas_por_categoria: ItemAgrupado[];
  despesas_por_subcategoria: ItemAgrupado[];
}

export interface ReceitaSaudeConfig {
  configurado: boolean;
  cpf_profissional: string | null;
  registro_profissional: string | null;
  codigo_ocupacao: string;
  descricao_padrao: string;
  ocupacoes: Record<string, string>;
  problemas: string[];
}

export interface ReciboItem {
  conta_id: number;
  aluno_id: number;
  aluno_nome: string;
  pagamento: string | null;
  vencimento: string;
  valor: string;
  descricao: string | null;
  competencia: string | null;
  problemas: string[];
  gerado_em: string | null;
  pronto: boolean;
}

export interface RecibosAluno {
  aluno_id: number;
  aluno_nome: string;
  aluno_cpf: string | null;
  sem_cpf: boolean;
  cpf_pagador_recibo: string | null;
  config_ok: boolean;
  problemas_config: string[];
  itens: ReciboItem[];
}

export interface LoteReceitaSaude {
  de: string;
  ate: string;
  config_ok: boolean;
  problemas_config: string[];
  total: number;
  prontos: number;
  com_problema: number;
  ja_gerados: number;
  arquivos_previstos: number;
  itens: ReciboItem[];
}

export interface Comissao {
  id: number;
  profissional_id: number;
  profissional_nome: string | null;
  conta_receber_id: number;
  aluno_nome: string | null;
  competencia: string;
  valor_base: string;
  percentual: string;
  valor: string;
  paga_em: string | null;
}

export interface Comissoes {
  competencia: string | null;
  itens: Comissao[];
  resumo: { profissional_id: number; profissional_nome: string; quantidade: number; valor_total: string; valor_pendente: string }[];
  valor_total: string;
  valor_pendente: string;
}

/** Cadastros usados nos filtros e formulários (rotas dos módulos de cadastros). */
export interface OpcaoCadastro {
  id: number;
  nome: string;
}
