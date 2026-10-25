"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";

import { SearchInput } from "@/components/mayacorp/data-table";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import type { AlunoBusca } from "@/lib/tipos-alunos";

/** Busca um aluno pelo nome/CPF/telefone e devolve o escolhido. */
export function SeletorAluno({
  valor,
  onChange,
}: {
  valor: AlunoBusca | null;
  onChange: (a: AlunoBusca | null) => void;
}) {
  const [q, setQ] = useState("");
  const termo = useDebounce(q, 300);
  const busca = useQuery({
    queryKey: ["comunicacao", "busca-aluno", termo],
    queryFn: () => api.get<AlunoBusca[]>("/alunos/busca", { q: termo }),
    enabled: termo.trim().length >= 2 && !valor,
  });

  if (valor) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-lg border bg-background px-3 py-2 text-sm">
        <span className="min-w-0 truncate">
          <strong className="font-medium">{valor.nome}</strong>
          {valor.telefone && <span className="ml-2 text-muted-foreground">{valor.telefone}</span>}
        </span>
        <button type="button" onClick={() => onChange(null)} className="grid size-6 place-items-center rounded text-muted-foreground hover:bg-muted" aria-label="Trocar aluno">
          <X className="size-3.5" />
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <SearchInput value={q} onChange={setQ} placeholder="Buscar aluno por nome, CPF ou telefone…" className="sm:w-full" />
      {termo.trim().length >= 2 && (
        <ul className="max-h-56 divide-y overflow-y-auto rounded-lg border bg-card text-sm">
          {busca.isPending && <li className="px-3 py-2 text-muted-foreground">Buscando…</li>}
          {busca.data?.length === 0 && <li className="px-3 py-2 text-muted-foreground">Nenhum aluno encontrado.</li>}
          {busca.data?.map((a) => (
            <li key={a.id}>
              <button type="button" onClick={() => onChange(a)} className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-accent/50">
                <span className="truncate">{a.nome}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{a.telefone ?? "sem telefone"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
