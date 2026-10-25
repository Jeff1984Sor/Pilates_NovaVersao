// Tipos da API de alunos (espelham backend/app/modules/alunos/schemas.py).

export type StatusAluno = "ATIVO" | "INATIVO";

export interface TelefoneAluno {
  id: number;
  ordem: number;
  numero: string; // canônico: 55 + DDD + número
  formatado: string;
  original: string | null;
  principal: boolean;
  whatsapp: string;
}

export interface EnderecoAluno {
  cep: string | null;
  logradouro: string;
  numero: string;
  bairro: string;
  cidade: string;
}

export interface Vinculos {
  contratos: number;
  reservas: number;
  aulas_avulsas: number;
  aulas_avaliativas: number;
  contas_receber: number;
  total: number;
  pode_excluir: boolean;
}

export interface AlunoOut {
  id: number;
  codigo: number | null;
  nome: string;
  cpf: string | null;
  cpf_mascarado: string | null;
  sem_cpf: boolean;
  rg: string | null;
  email: string | null;
  data_nascimento: string | null;
  estado_civil: string | null;
  profissao_id: number | null;
  profissao_nome: string | null;
  unidade_id: number;
  unidade_nome: string | null;
  termo_uso_id: number | null;
  status: StatusAluno;
  autoriza_imagem: boolean;
  cpf_pagador_recibo: string | null;
  foto_url: string | null;
  telefones: TelefoneAluno[];
  endereco: EnderecoAluno | null;
  termo_assinado_em: string | null;
  criado_em: string;
  atualizado_em: string;
  aulas_reservadas: number;
  vinculos: Vinculos;
}

/** Cabeçalho mínimo (perfil Professor): sem CPF nem telefone. */
export interface AlunoResumo {
  id: number;
  nome: string;
  status: StatusAluno;
  foto_url: string | null;
  unidade_nome: string | null;
}

export interface AlunoLista {
  id: number;
  codigo: number | null;
  nome: string;
  cpf_mascarado: string | null;
  sem_cpf: boolean;
  telefone: string | null;
  status: StatusAluno;
  aulas_reservadas: number;
  foto_url: string | null;
  criado_em: string;
}

export interface ListaAlunos {
  itens: AlunoLista[];
  total: number;
  pagina: number;
  por_pagina: number;
  contagens: { ativos: number; inativos: number; todos: number };
}

export interface AlunoBusca {
  id: number;
  nome: string;
  cpf_mascarado: string | null;
  telefone: string | null;
  status: StatusAluno;
  foto_url: string | null;
}

export interface DocumentoAluno {
  id: number;
  titulo: string;
  descricao: string | null;
  origem: "UPLOAD" | "CONTRATO_PDF";
  contrato_id: number | null;
  nome_arquivo: string;
  tamanho: number | null;
  criado_em: string;
  pode_excluir: boolean;
}

export interface TermoOpcao {
  id: number;
  nome: string;
}

export interface TermoEstado {
  autoriza_imagem: boolean;
  assinado: boolean;
  termo: TermoOpcao | null;
  termos_disponiveis: TermoOpcao[];
  aceite_em: string | null;
  assinado_em: string | null;
  assinatura_nome: string | null;
  assinatura_documento: string | null;
  assinatura_ip: string | null;
  assinatura_url: string | null;
  texto_html: string | null;
  link_assinatura_disponivel: boolean;
}

export interface CepOut {
  cep: string;
  logradouro: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
}

export interface OpcoesAluno {
  unidades: { id: number; nome: string; ativo: boolean }[];
  profissoes: { id: number; nome: string }[];
  termos: { id: number; nome: string }[];
  estados_civis: { id: string; nome: string }[];
}

/** Corpo de POST /alunos e PUT /alunos/{id}. */
export interface AlunoEntrada {
  nome: string;
  cpf: string | null;
  sem_cpf: boolean;
  rg: string | null;
  email: string | null;
  data_nascimento: string | null;
  estado_civil: string | null;
  profissao_id: number | null;
  unidade_id: number | null;
  termo_uso_id: number | null;
  status: StatusAluno;
  autoriza_imagem: boolean;
  cpf_pagador_recibo: string | null;
  telefones: { id?: number; numero: string; principal: boolean }[];
  endereco: { cep: string | null; logradouro: string | null; numero: string | null; bairro: string | null; cidade: string | null };
}

export type Situacao = "ativos" | "inativos" | "todos";
