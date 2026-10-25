"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CalendarCheck, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { NativeSelect } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { BlocoGrade, GradeSemanal } from "@/lib/tipos-agenda";
import { cn } from "@/lib/utils";

import { useOpcoesAgenda } from "./comum";

const PX_POR_MIN = 0.8;

function Bloco({ b, inicioGrade, onAbrir }: { b: BlocoGrade; inicioGrade: number; onAbrir?: (reservaId: number) => void }) {
  const largura = 100 / b.colunas;
  const clicavel = !!onAbrir && b.reserva_id !== null;
  const dica = [b.hora, b.servico, b.aluno ?? "Sem alunos", b.situacao, b.profissional].filter(Boolean).join(" · ");
  return (
    <button
      type="button"
      title={dica}
      disabled={!clicavel}
      onClick={() => b.reserva_id !== null && onAbrir?.(b.reserva_id)}
      className={cn(
        "absolute overflow-hidden rounded-md px-1.5 py-1 text-left text-[11px] leading-tight text-white shadow-sm ring-1 ring-black/10 transition-[filter]",
        clicavel ? "cursor-pointer hover:brightness-110" : "cursor-default",
      )}
      style={{
        top: (b.inicio_min - inicioGrade) * PX_POR_MIN,
        height: Math.max((b.fim_min - b.inicio_min) * PX_POR_MIN, 22),
        left: `${b.coluna * largura}%`,
        width: `calc(${largura}% - 2px)`,
        background: b.cor,
      }}
    >
      <span className="block truncate font-bold">
        {b.ocupacao && <span className="mr-1 rounded bg-black/20 px-1 py-px text-[10px]">{b.ocupacao}</span>}
        {b.hora}
      </span>
      {b.aluno && <span className="block truncate opacity-95">{b.aluno}</span>}
      <span className="block truncate text-[10px] opacity-80">{b.servico}</span>
    </button>
  );
}

/**
 * Grade semanal (seg a sáb): bloco por aluno colorido pelo status, ocupação n/m, filtro por profissional e navegação
 * semana anterior / hoje / próxima. Sem semana escolhida, sábado e domingo mostram a próxima semana (o servidor decide).
 * `onAbrirReserva` (opcional) abre a gaveta do aluno ao clicar num bloco.
 */
export function GradeSemanal({ onAbrirReserva }: { onAbrirReserva?: (reservaId: number) => void }) {
  const { somenteProprias } = useAuth();
  const opcoes = useOpcoesAgenda();
  const [semana, setSemana] = useState<string | null>(null);
  const [profissional, setProfissional] = useState("");

  const q = useQuery({
    queryKey: ["agenda", "grade", semana, profissional],
    queryFn: () => api.get<GradeSemanal>("/agenda/grade", { semana, profissional_id: profissional }),
    placeholderData: keepPreviousData,
  });
  const g = q.data;
  const horas = g ? Array.from({ length: (g.grade_fim_min - g.grade_inicio_min) / 60 + 1 }, (_, i) => g.grade_inicio_min + i * 60) : [];
  const altura = g ? (g.grade_fim_min - g.grade_inicio_min) * PX_POR_MIN : 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-semibold capitalize">{g?.rotulo ?? "…"}</h2>
        <div className="ml-1 flex items-center gap-1">
          <Button variant="outline" size="icon" aria-label="Semana anterior" disabled={!g} onClick={() => g && setSemana(g.anterior)}>
            <ChevronLeft />
          </Button>
          <Button variant="outline" disabled={!g} onClick={() => g && setSemana(g.hoje)}>
            Hoje
          </Button>
          <Button variant="outline" size="icon" aria-label="Próxima semana" disabled={!g} onClick={() => g && setSemana(g.proxima)}>
            <ChevronRight />
          </Button>
        </div>
        {!somenteProprias && (
          <NativeSelect value={profissional} onChange={(e) => setProfissional(e.target.value)} className="min-w-52" aria-label="Profissional">
            <option value="">Todos os profissionais</option>
            {(opcoes.data?.profissionais ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
        )}
        <Button variant="outline" className="ml-auto" render={<Link href="/agenda/aulas" />}>
          <CalendarCheck /> Painel operacional
        </Button>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {(g?.legenda ?? []).map((l) => (
          <span key={l.rotulo} className="inline-flex items-center gap-1.5">
            <i className="inline-block size-2.5 rounded-sm" style={{ background: l.cor }} /> {l.rotulo}
          </span>
        ))}
      </div>

      {!g ? (
        <Skeleton className="h-96 rounded-2xl" />
      ) : (
        <div className="card-surface overflow-x-auto">
          <div className="grid min-w-[760px]" style={{ gridTemplateColumns: "56px repeat(6, minmax(0, 1fr))" }}>
            <div className="sticky top-0 z-10 border-b bg-muted/60" />
            {g.dias.map((d) => (
              <div
                key={d.data}
                className={cn(
                  "sticky top-0 z-10 border-b border-l px-2 py-2 text-center text-[13px] font-medium",
                  d.hoje ? "bg-primary text-primary-foreground" : "bg-muted/60",
                )}
              >
                {d.rotulo} {d.numero}
              </div>
            ))}
            <div className="relative" style={{ height: altura }}>
              {horas.map((h) => (
                <span
                  key={h}
                  className="absolute right-1.5 -translate-y-1.5 text-[11px] text-muted-foreground"
                  style={{ top: (h - g.grade_inicio_min) * PX_POR_MIN }}
                >
                  {String(h / 60).padStart(2, "0")}:00
                </span>
              ))}
            </div>
            {g.dias.map((d) => (
              <div key={d.data} className={cn("relative border-l", d.hoje && "bg-brand/5")} style={{ height: altura }}>
                {horas.map((h) => (
                  <div key={h} className="absolute inset-x-0 border-t border-dashed border-border/70" style={{ top: (h - g.grade_inicio_min) * PX_POR_MIN }} />
                ))}
                {d.blocos.map((b, i) => (
                  <Bloco key={`${b.sessao_id}-${b.reserva_id ?? "v"}-${i}`} b={b} inicioGrade={g.grade_inicio_min} onAbrir={onAbrirReserva} />
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
