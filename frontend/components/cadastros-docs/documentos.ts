import { FileText, ScrollText, type LucideIcon } from "lucide-react";

/** Os dois tipos de documento com editor HTML e variáveis: termo de imagem e modelo de contrato. */
export type TipoDocumento = "termo" | "contrato";

export interface ConfigDocumento {
  tipo: TipoDocumento;
  /** nome no singular, minúsculo, para frases ("Excluir o termo X?") */
  singular: string;
  titulo: string;
  tituloNovo: string;
  descricao: string;
  icone: LucideIcon;
  api: string;
  variaveisPath: string;
  previaPath: string;
  /** endereço da lista na interface */
  rota: string;
  permissao: string;
  nomeMax: number;
  temAtivo: boolean;
  /** texto do interruptor "Ativo" no editor */
  descAtivo: string;
  /** chave do cache (TanStack Query) da lista */
  chave: string;
  vinculo: { campo: "alunos_com_aceite" | "planos"; singular: string; plural: string; rotulo: string };
}

export const DOCUMENTOS: Record<TipoDocumento, ConfigDocumento> = {
  termo: {
    tipo: "termo",
    singular: "termo",
    titulo: "Termos de uso",
    tituloNovo: "Novo termo de uso",
    descricao: "Termo de uso de imagem e outros termos que o aluno aceita ou assina. O texto aceita variáveis do aluno.",
    icone: ScrollText,
    api: "/cadastros/termos",
    variaveisPath: "/cadastros/termos/variaveis",
    previaPath: "/cadastros/termos/previa",
    rota: "/cadastros/termos",
    permissao: "cadastros_termos",
    nomeMax: 80,
    temAtivo: true,
    descAtivo: "Inativo não é oferecido para novos aceites; os aceites já feitos continuam valendo.",
    chave: "termos",
    vinculo: { campo: "alunos_com_aceite", singular: "aluno aceitou", plural: "alunos aceitaram", rotulo: "Aceites" },
  },
  contrato: {
    tipo: "contrato",
    singular: "modelo de contrato",
    titulo: "Modelos de contrato",
    tituloNovo: "Novo modelo de contrato",
    descricao: "Texto do contrato com variáveis do aluno, do plano e do contrato. Cada plano usa um modelo.",
    icone: FileText,
    api: "/cadastros/modelos/contrato",
    variaveisPath: "/cadastros/modelos/variaveis",
    previaPath: "/cadastros/modelos/contrato/previa",
    rota: "/cadastros/modelos-contrato",
    permissao: "cadastros_modelos",
    nomeMax: 120,
    temAtivo: true,
    descAtivo: "Inativo não é oferecido em novos planos.",
    chave: "modelos-contrato",
    vinculo: { campo: "planos", singular: "plano", plural: "planos", rotulo: "Planos" },
  },
};
