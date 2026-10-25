// Tipos da API de integrações (espelham backend/app/modules/integracoes/schemas.py).
// Segredos NUNCA chegam do servidor: só `definido` + `final` (últimos caracteres).

export interface TokenApi {
  id: number;
  nome: string;
  token_final: string | null;
  ativo: boolean;
  /** veio do sistema antigo sem o valor: gerar um novo e repassar ao integrador */
  precisa_regenerar: boolean;
  ultimo_uso: string | null;
  criado_em: string;
}

/** Resposta de criar/regenerar: o `valor` aparece UMA ÚNICA VEZ. */
export interface TokenApiComValor extends TokenApi {
  valor: string;
}

export interface Segredo {
  definido: boolean;
  final: string | null;
}

export interface TotalpassConfig {
  unidade_id: number;
  unidade_nome: string;
  configurada: boolean;
  ativo: boolean;
  place_id: string | null;
  criar_aluno_automatico: boolean;
  somente_dia: boolean;
  servico_padrao_id: number | null;
  sync_ativo: boolean;
  sync_ultimo_em: string | null;
  sync_ultimo_resumo: string | null;
  partner_api_key: Segredo;
  place_api_key: Segredo;
  webhook_token: Segredo;
}

export interface TotalpassTela {
  webhook_caminho: string;
  configuracoes: TotalpassConfig[];
  servicos: { id: number; nome: string }[];
}

export type SegredoNome = "partner_api_key" | "place_api_key" | "webhook_token";

export interface TotalpassConfigIn {
  ativo: boolean;
  place_id: string | null;
  criar_aluno_automatico: boolean;
  somente_dia: boolean;
  servico_padrao_id: number | null;
  sync_ativo: boolean;
  partner_api_key?: string | null;
  place_api_key?: string | null;
  webhook_token?: string | null;
  limpar: SegredoNome[];
}

export interface ResumoSync {
  resumo: string;
  dia: string;
  recebidos: number;
  processados: number;
  cancelados: number;
  descartados: number;
  duplicados: number;
  erros: number;
}

export type ResultadoEvento = "processado" | "cancelado" | "descartado" | "erro" | "pendente";

export interface EventoTotalpass {
  id: number;
  recebido_em: string;
  processado_em: string | null;
  origem: "webhook" | "sync" | null;
  event_id: string | null;
  slot_id: string | null;
  documento_mascarado: string | null;
  status: string | null;
  titulo: string | null;
  aula_em: string | null;
  resultado: ResultadoEvento;
  erro: string | null;
  reserva_id: number | null;
}

export interface ListaEventos {
  total: number;
  pagina: number;
  por_pagina: number;
  itens: EventoTotalpass[];
}

/** Resposta de "gerar token do webhook": o `valor` aparece UMA ÚNICA VEZ. */
export interface WebhookTokenOut {
  valor: string;
  final: string;
}
