// Tipos da API dos cadastros de agenda e documentos (espelham backend/app/modules/cadastros/*.py).
// Os campos de hora chegam como "HH:MM:SS"; use `hhmm()` para exibir.

export interface PaginaContagens<T> {
  itens: T[];
  total: number;
  pagina: number;
  por_pagina: number;
  contagens: Record<string, number>;
}

export type TipoCategoria = "RECEITA" | "DESPESA";

export interface Fornecedor {
  id: number;
  codigo: number | null;
  nome: string;
  ativo: boolean;
  contas_a_pagar: number;
  criado_em: string | null;
}

export interface Categoria {
  id: number;
  codigo: number | null;
  nome: string;
  tipo: TipoCategoria;
  ativo: boolean;
  subcategorias: number;
  contas_a_pagar: number;
  planos: number;
}

export interface Subcategoria {
  id: number;
  codigo: number | null;
  categoria_id: number;
  categoria_nome: string;
  categoria_tipo: TipoCategoria;
  nome: string;
  ativo: boolean;
  contas_a_pagar: number;
  planos: number;
}

export interface Opcao {
  id: number;
  nome: string;
  ativo: boolean;
}

export interface OpcoesAgenda {
  unidades: Opcao[];
  servicos: Opcao[];
  profissionais: Opcao[];
  dias: { valor: number; nome: string }[];
}

export interface HorarioFuncionamento {
  id: number;
  unidade_id: number;
  unidade_nome: string;
  dia_semana: number;
  dia_nome: string;
  hora_inicio: string;
  hora_fim: string;
  ativo: boolean;
  tipos_servico_ids: number[];
  servicos: string;
  aulas_por_dia: number;
}

export interface HorarioStudio {
  id: number;
  codigo: number | null;
  unidade_id: number;
  unidade_nome: string;
  tipo_servico_id: number;
  tipo_servico_nome: string;
  profissional_id: number | null;
  profissional_nome: string | null;
  dia_semana: number;
  dia_nome: string;
  hora_inicio: string;
  hora_fim: string;
  capacidade: number | null;
  legado: boolean;
}

export interface ResultadoGeracao {
  criados: number;
  ignorados: number;
  mensagem: string;
}

export type SituacaoBloqueio = "vigente" | "agendado" | "expirado" | "inativo";

export interface Bloqueio {
  id: number;
  unidade_id: number;
  unidade_nome: string;
  tipo_servico_id: number | null;
  tipo_servico_nome: string;
  profissional_id: number | null;
  profissional_nome: string;
  recorrente: boolean;
  dia_semana: number | null;
  dia_nome: string | null;
  data_inicio: string;
  data_fim: string | null;
  hora_inicio: string;
  hora_fim: string;
  motivo: string | null;
  ativo: boolean;
  situacao: SituacaoBloqueio;
  vale_ate: string;
  aviso: string | null;
}

export interface VariavelModelo {
  chave: string;
  marcador: string;
  descricao: string;
  exemplo: string;
}

export interface PreviaDocumento {
  html: string;
  usadas: string[];
  desconhecidas: string[];
}

export interface ModeloContratoLista {
  id: number;
  codigo: number | null;
  nome: string;
  ativo: boolean;
  previa: string;
  planos: number;
  atualizado_em: string | null;
}

export interface ModeloContrato extends ModeloContratoLista {
  conteudo_html: string;
  variaveis_usadas: string[];
  variaveis_desconhecidas: string[];
}

export interface TermoLista {
  id: number;
  codigo: number | null;
  nome: string;
  ativo: boolean;
  previa: string;
  alunos_com_aceite: number;
  atualizado_em: string | null;
}

export interface Termo extends TermoLista {
  conteudo_html: string;
  variaveis_usadas: string[];
  variaveis_desconhecidas: string[];
}

export interface ModeloEvolucao {
  id: number;
  codigo: number | null;
  titulo: string;
  texto: string;
  ativo: boolean;
  atualizado_em: string | null;
}

export const hhmm = (h: string | null | undefined) => (h ? h.slice(0, 5) : "");
