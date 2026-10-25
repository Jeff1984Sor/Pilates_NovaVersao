"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Pill } from "@/components/mayacorp/status-badge";
import { api } from "@/lib/api";
import type { OpcoesAgenda, StatusAula, StatusReserva } from "@/lib/tipos-agenda";
import { ROTULO_STATUS_AULA, ROTULO_STATUS_RESERVA } from "@/lib/tipos-agenda";

/** Listas de unidades, profissionais, serviços e modelos (cache de 5 min). */
export function useOpcoesAgenda() {
  return useQuery({
    queryKey: ["agenda", "opcoes"],
    queryFn: () => api.get<OpcoesAgenda>("/agenda/opcoes"),
    staleTime: 5 * 60_000,
  });
}

/** Depois de qualquer mudança numa aula, tudo que a mostra é recarregado. */
export function useInvalidarAgenda() {
  const qc = useQueryClient();
  return () => {
    for (const k of ["painel", "grade", "reserva", "aluno-aulas", "aluno-evolucoes", "aluno-avaliacoes", "aluno-avaliativas"]) {
      qc.invalidateQueries({ queryKey: ["agenda", k] });
    }
  };
}

type Tom = "success" | "warning" | "danger" | "info" | "neutral" | "brand";

export const TOM_STATUS_AULA: Record<StatusAula, Tom> = {
  aguardando_chegar: "warning",
  em_aula: "info",
  finalizada: "success",
  faltou: "danger",
  remarcada: "neutral",
};

export function PillStatusAula({ status }: { status: StatusAula }) {
  return <Pill tom={TOM_STATUS_AULA[status]}>{ROTULO_STATUS_AULA[status]}</Pill>;
}

const TOM_RESERVA: Record<StatusReserva, Tom> = {
  RESERVADA: "info",
  CONCLUIDA: "success",
  FALTOU_AVISOU: "warning",
  FALTOU_SEM_AVISAR: "danger",
  CANCELADA: "neutral",
  PENDENTE: "brand",
};

export function PillStatusReserva({ status }: { status: StatusReserva }) {
  return <Pill tom={TOM_RESERVA[status]}>{ROTULO_STATUS_RESERVA[status]}</Pill>;
}

/** Cor de cada profissional dentro do horário (a mesma ordem do servidor: índice 0 a 5). */
export const CORES_PROFISSIONAL = ["#7b2c2f", "#a8742f", "#3f6f6a", "#6b4a8a", "#b4533f", "#4d6a3a"];

export const DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

/** "2026-10-26" -> "26/10/2026" (sem passar por Date: não há risco de fuso). */
export function dataBr(iso: string | null | undefined) {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export function diaMes(iso: string) {
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}`;
}

/** Data de hoje no navegador como "YYYY-MM-DD" (local, não UTC). */
export function hojeIso() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
