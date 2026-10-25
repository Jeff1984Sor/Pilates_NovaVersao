"use client";

import { Hammer } from "lucide-react";

import { EmptyState } from "@/components/mayacorp/empty-state";

/**
 * Abas da ficha que pertencem a outros módulos. Hoje são esqueletos "Em construção"; o coordenador troca cada
 * componente em `abas.ts` pelo definitivo (ex.: `components/agenda/aba-aluno-aulas.tsx`), todos com props `{ alunoId: number }`.
 */
export interface PropsAbaAluno {
  alunoId: number;
}

function EmConstrucao({ titulo, descricao }: { titulo: string; descricao: string }) {
  return (
    <div className="card-surface">
      <EmptyState icone={Hammer} titulo={`${titulo}: em construção`} descricao={descricao} />
    </div>
  );
}

export function AbaAulas() {
  return <EmConstrucao titulo="Aulas" descricao="Reservas, reposições e histórico de presença do aluno chegam com o módulo de Agenda." />;
}
export function AbaContratos() {
  return <EmConstrucao titulo="Contratos" descricao="Contratos, assinatura e documentos de matrícula chegam com o módulo de Contratos." />;
}
export function AbaFinanceiro() {
  return <EmConstrucao titulo="Financeiro" descricao="Cobranças, pagamentos e recibos do aluno chegam com o módulo Financeiro." />;
}
export function AbaWhatsapp() {
  return <EmConstrucao titulo="WhatsApp" descricao="O histórico de conversas e o envio de mensagens chegam com a onda de comunicação." />;
}
export function AbaEvolucao() {
  return <EmConstrucao titulo="Evolução" descricao="As evoluções registradas pelos professores em cada aula chegam com o módulo de Agenda." />;
}
export function AbaAvaliacoes() {
  return <EmConstrucao titulo="Avaliações" descricao="As fichas de avaliação do aluno chegam com o módulo de Agenda." />;
}
