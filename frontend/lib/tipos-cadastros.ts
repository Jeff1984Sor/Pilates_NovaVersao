// Tipos da API dos cadastros-base (espelham backend/app/modules/cadastros/*.py). Dinheiro e percentuais chegam como texto.
import type { Pagina } from "./types";

export type Situacao = "ativos" | "inativos" | "todos";

export interface PaginaCad<T> extends Pagina<T> {
  contagens: Record<Situacao, number>;
}

export interface VinculosOut {
  total: number;
  itens: { rotulo: string; quantidade: number }[];
  pode_excluir: boolean;
  pode_desativar: boolean;
  /** Itens que serão removidos junto com o cadastro (ex.: horários e bloqueios da unidade). */
  junto: { rotulo: string; quantidade: number }[];
  total_junto: number;
}

export interface UnidadeOut {
  id: number;
  codigo: number | null;
  nome: string;
  capacidade: number;
  duracao_aula_minutos: number;
  ativo: boolean;
}

export interface ServicoOut {
  id: number;
  codigo: number | null;
  nome: string;
  ativo: boolean;
}

export interface ProfissaoOut {
  id: number;
  codigo: number | null;
  nome: string;
}

export type Recorrencia = "MENSAL" | "SEMANAL";

export interface PlanoOut {
  id: number;
  codigo: number | null;
  nome: string;
  tipo_servico_id: number;
  tipo_servico_nome: string | null;
  valor: string;
  aulas_por_semana: number;
  duracao_meses: number;
  recorrencia: Recorrencia;
  is_avulso: boolean;
  categoria_receita_id: number | null;
  categoria_receita_nome: string | null;
  subcategoria_receita_id: number | null;
  subcategoria_receita_nome: string | null;
  modelo_contrato_id: number | null;
  modelo_contrato_nome: string | null;
  ativo: boolean;
  /** Regra R1: valor mensal / (aulas por semana x 4); null sem aulas por semana. */
  valor_aula: string | null;
  valor_total: string;
}

export interface PlanoOpcoes {
  tipos_servico: { id: number; nome: string; ativo: boolean }[];
  categorias_receita: { id: number; nome: string }[];
  subcategorias_receita: { id: number; nome: string; categoria_id: number }[];
  modelos_contrato: { id: number; nome: string; ativo: boolean }[];
}

export interface ProfissionalOut {
  id: number;
  codigo: number | null;
  nome: string;
  email: string | null;
  celular: string | null;
  data_nascimento: string | null;
  crefito: string | null;
  comissao_percentual: string;
  ativo: boolean;
  usuario_id: number | null;
  login: string | null;
  acesso_sistema: boolean;
  convite_pendente: boolean;
  perfil_acesso_id: number | null;
  perfil_acesso_nome: string | null;
  perfil_acesso_cor: string | null;
  /** Só na criação / ao dar acesso: false = o e-mail de convite não saiu. */
  convite_enviado: boolean | null;
}

export interface PerfilAcessoOpcao {
  id: number;
  nome: string;
  cor: string | null;
  administrador: boolean;
  somente_proprias_aulas: boolean;
}

export interface MeuProfissional {
  id: number;
  codigo: number | null;
  nome: string;
  email: string | null;
  celular: string | null;
  data_nascimento: string | null;
  crefito: string | null;
}
