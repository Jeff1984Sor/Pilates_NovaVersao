"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, CalendarPlus, ClipboardList, Ticket } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AulaDoAluno } from "@/lib/tipos-agenda";
import { cn } from "@/lib/utils";

import { PillStatusAula, dataBr } from "./comum";
import { DialogoAgendarAula, DialogoAulaAvaliativa, DialogoAulaAvulsa } from "./dialogos-aluno";
import { GavetaAluno } from "./gaveta-aluno";

type Filtro = "todas" | "futuras" | "passadas";
const TIPO: Record<AulaDoAluno["tipo"], string> = { regular: "Aula", contrato: "Contrato", avulsa: "Avulsa", avaliativa: "Avaliativa" };

/** Aulas do aluno (ficha, aba "Aulas"): futuras e passadas com status, e atalhos para agendar, avulsa e avaliativa. */
export function AbaAlunoAulas({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [aberta, setAberta] = useState<number | null>(null);
  const [dialogo, setDialogo] = useState<"agendar" | "avulsa" | "avaliativa" | null>(null);

  const q = useQuery({
    queryKey: ["agenda", "aluno-aulas", alunoId, filtro],
    queryFn: () =>
      api.get<{ itens: AulaDoAluno[] }>(`/agenda/alunos/${alunoId}/reservas`, {
        futuras: filtro === "todas" ? undefined : filtro === "futuras",
      }),
  });
  const itens = q.data?.itens ?? [];
  const podeAgendar = pode("agenda.editar");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1.5">
          {(["todas", "futuras", "passadas"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFiltro(f)}
              aria-pressed={filtro === f}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors",
                filtro === f ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-accent",
              )}
            >
              {f}
            </button>
          ))}
        </div>
        {podeAgendar && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setDialogo("agendar")}>
              <CalendarPlus /> Agendar aula
            </Button>
            <Button size="sm" variant="outline" onClick={() => setDialogo("avulsa")}>
              <Ticket /> Aula avulsa
            </Button>
            <Button size="sm" variant="outline" onClick={() => setDialogo("avaliativa")}>
              <ClipboardList /> Aula avaliativa
            </Button>
          </div>
        )}
      </div>

      {q.isPending ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : itens.length === 0 ? (
        <div className="card-surface">
          <EmptyState icone={CalendarCheck} titulo="Nenhuma aula" descricao="As aulas agendadas para este aluno aparecem aqui." />
        </div>
      ) : (
        <ul className="card-surface divide-y overflow-hidden">
          {itens.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => setAberta(a.id)}
                className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-accent/40"
              >
                <span className="num w-24 shrink-0 text-sm font-medium">{dataBr(a.data)}</span>
                <span className="num w-24 shrink-0 text-sm text-muted-foreground">
                  {a.hora_inicio}–{a.hora_fim}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">
                  {a.servico}
                  {a.profissional ? ` · ${a.profissional.nome}` : ""}
                </span>
                <Pill tom={a.tipo === "avulsa" ? "warning" : a.tipo === "avaliativa" ? "info" : "neutral"}>{TIPO[a.tipo]}</Pill>
                {a.status === "CANCELADA" && a.reposicao_ate && <Pill tom="info">Repor até {dataBr(a.reposicao_ate)}</Pill>}
                <PillStatusAula status={a.status_aula} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <GavetaAluno key={aberta ?? "fechada"} reservaId={aberta} onFechar={() => setAberta(null)} />
      {podeAgendar && (
        <>
          <DialogoAgendarAula alunoId={alunoId} aberto={dialogo === "agendar"} onFechar={() => setDialogo(null)} />
          <DialogoAulaAvulsa alunoId={alunoId} aberto={dialogo === "avulsa"} onFechar={() => setDialogo(null)} />
          <DialogoAulaAvaliativa alunoId={alunoId} aberto={dialogo === "avaliativa"} onFechar={() => setDialogo(null)} />
        </>
      )}
    </div>
  );
}
