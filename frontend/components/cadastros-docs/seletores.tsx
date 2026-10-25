"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { OpcoesAgenda } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

import { DIAS_CURTOS } from "./comum";

/** Unidades, serviços e profissionais para os formulários (vem da API de horários, sob a permissão de ver horários). */
export function useOpcoes(ativo = true, caminho = "/cadastros/horarios/opcoes") {
  return useQuery({
    queryKey: ["opcoes-agenda", caminho],
    queryFn: () => api.get<OpcoesAgenda>(caminho),
    enabled: ativo,
    staleTime: 60_000,
  });
}

/** Dias da semana como botões de alternar (0 = segunda ... 6 = domingo). */
export function DiasChips({
  valor,
  onChange,
  unico,
}: {
  valor: number[];
  onChange: (v: number[]) => void;
  /** só um dia pode ficar marcado (edição de um registro) */
  unico?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Dias da semana">
      {DIAS_CURTOS.map((nome, i) => {
        const on = valor.includes(i);
        return (
          <button
            key={i}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(unico ? [i] : on ? valor.filter((d) => d !== i) : [...valor, i].sort())}
            className={cn(
              "h-8 min-w-12 rounded-lg border px-3 text-sm font-medium transition-colors",
              on ? "border-brand bg-brand/15 text-foreground" : "text-muted-foreground hover:bg-muted",
            )}
          >
            {nome}
          </button>
        );
      })}
    </div>
  );
}

/** Lista de serviços com caixas de marcar. Nenhum marcado = vale para todos os serviços. */
export function ServicosCheck({
  servicos,
  valor,
  onChange,
}: {
  servicos: { id: number; nome: string; ativo: boolean }[];
  valor: number[];
  onChange: (v: number[]) => void;
}) {
  return (
    <div>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {servicos.map((s) => (
          <label key={s.id} className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-[var(--brand)]"
              checked={valor.includes(s.id)}
              onChange={(e) => onChange(e.target.checked ? [...valor, s.id] : valor.filter((x) => x !== s.id))}
            />
            <span className={cn(!s.ativo && "text-muted-foreground line-through")}>{s.nome}</span>
          </label>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">
        {valor.length === 0 ? "Nenhum serviço marcado: vale para todos os serviços." : "Vale só para os serviços marcados."}
      </p>
    </div>
  );
}
