import {
  CalendarDays,
  ClipboardList,
  FileSignature,
  FolderOpen,
  Image as ImagemIcone,
  MessageCircle,
  ReceiptText,
  TrendingUp,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import type { ComponentType } from "react";

import { AbaDados } from "./aba-dados";
import { AbaDocumentos } from "./aba-documentos";
import { AbaImagem } from "./aba-imagem";
import { AbaAlunoAulas } from "../agenda/aba-aluno-aulas";
import { AbaAlunoAvaliacao } from "../agenda/aba-aluno-avaliacao";
import { AbaAlunoEvolucao } from "../agenda/aba-aluno-evolucao";
import { AbaAlunoFinanceiro } from "../financeiro/aba-aluno-financeiro";
import { AbaContratos, AbaWhatsapp } from "./abas-esqueleto";

export interface AbaAluno {
  /** Valor de `?aba=` na URL. */
  id: string;
  rotulo: string;
  icone: LucideIcon;
  /** Todas as abas recebem só o id do aluno. */
  componente: ComponentType<{ alunoId: number }>;
  /** Permissão exigida para ver a aba ("recurso.acao"); sem ela, basta ter acesso à ficha. */
  permissao?: string;
  /** Perfil Professor ("somente as próprias aulas") só enxerga as abas marcadas aqui. */
  visivelProfessor: boolean;
  /** Aparece como atalho no cabeçalho da ficha. */
  atalho?: boolean;
}

/**
 * Registro declarativo das abas da ficha do aluno. Para ligar a entrega de outro módulo, troque o `componente`
 * da linha correspondente (os esqueletos "Em construção" estão em `abas-esqueleto.tsx`).
 */
export const ABAS_ALUNO: AbaAluno[] = [
  { id: "dados", rotulo: "Dados", icone: UserRound, componente: AbaDados, permissao: "alunos.ver", visivelProfessor: false },
  { id: "aulas", rotulo: "Aulas", icone: CalendarDays, componente: AbaAlunoAulas, permissao: "aulas.ver", visivelProfessor: false, atalho: true },
  { id: "contratos", rotulo: "Contratos", icone: FileSignature, componente: AbaContratos, permissao: "contratos.ver", visivelProfessor: false, atalho: true },
  { id: "financeiro", rotulo: "Financeiro", icone: ReceiptText, componente: AbaAlunoFinanceiro, permissao: "financeiro_receber.ver", visivelProfessor: false, atalho: true },
  { id: "whatsapp", rotulo: "WhatsApp", icone: MessageCircle, componente: AbaWhatsapp, permissao: "whatsapp.ver", visivelProfessor: false, atalho: true },
  { id: "evolucao", rotulo: "Evolução", icone: TrendingUp, componente: AbaAlunoEvolucao, permissao: "aulas.ver", visivelProfessor: true, atalho: true },
  { id: "avaliacoes", rotulo: "Avaliações", icone: ClipboardList, componente: AbaAlunoAvaliacao, permissao: "aulas.ver", visivelProfessor: true },
  { id: "documentos", rotulo: "Documentos", icone: FolderOpen, componente: AbaDocumentos, permissao: "alunos.ver", visivelProfessor: false },
  { id: "imagem", rotulo: "Uso da imagem", icone: ImagemIcone, componente: AbaImagem, permissao: "alunos.ver", visivelProfessor: false },
];

/** Abas que o usuário pode ver (permissão do perfil e, para o Professor, a lista restrita). */
export function abasVisiveis(pode: (permissao: string) => boolean, somenteProprias: boolean): AbaAluno[] {
  return ABAS_ALUNO.filter((a) => (!a.permissao || pode(a.permissao)) && (!somenteProprias || a.visivelProfessor));
}
