"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, FileText } from "lucide-react";

import { NativeSelect } from "@/components/mayacorp/form";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, baixar, type RequestOpts } from "@/lib/api";
import { moeda, numero } from "@/lib/format";
import type { Chip } from "@/lib/tipos-financeiro";
import { cn } from "@/lib/utils";

/** Data de hoje no fuso do negócio (America/Sao_Paulo), "AAAA-MM-DD". */
export function hojeISO(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" });
}

export function mesAtualISO(): string {
  return hojeISO().slice(0, 7);
}

/** "2026-10" -> primeiro e último dia do mês. */
export function limitesDoMes(ym: string): { de: string; ate: string } {
  const [a, m] = ym.split("-").map(Number);
  const ultimo = new Date(a, m, 0).getDate();
  return { de: `${ym}-01`, ate: `${ym}-${String(ultimo).padStart(2, "0")}` };
}

export function mesAtual() {
  return limitesDoMes(mesAtualISO());
}

export const nomeMes = (ym: string) => {
  const [a, m] = ym.split("-").map(Number);
  return new Date(a, m - 1, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
};

/** Invalida todas as consultas do financeiro (chaves que começam com "fin"). */
export function useInvalidarFinanceiro() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["fin"] });
}

// ------------------------------------------------------------------------------------------------ situação
const TOM: Record<string, "brand" | "info" | "success" | "danger" | "neutral" | "warning"> = {
  TODOS: "neutral",
  ABERTO: "brand",
  AGENDADO: "info",
  PAGO: "success",
  ATRASADO: "danger",
  CANCELADO: "neutral",
};

const ROTULO: Record<string, string> = {
  TODOS: "Todos",
  ABERTO: "Aberto",
  AGENDADO: "Agendado",
  PAGO: "Pago",
  ATRASADO: "Atrasado",
  CANCELADO: "Cancelado",
};

export function SituacaoPill({ situacao, className }: { situacao: string; className?: string }) {
  return (
    <Pill tom={TOM[situacao] ?? "neutral"} className={className}>
      {ROTULO[situacao] ?? situacao}
    </Pill>
  );
}

const PONTO: Record<string, string> = {
  TODOS: "bg-muted-foreground/60",
  ABERTO: "bg-brand",
  AGENDADO: "bg-info",
  PAGO: "bg-success",
  ATRASADO: "bg-danger",
  CANCELADO: "bg-muted-foreground/40",
};

/** Chips de situação com contagem e valor somado (padrão da lista do sistema antigo). */
export function SituacaoChips({ chips, valor, onChange }: { chips: Chip[] | undefined; valor: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 p-3" role="tablist" aria-label="Situação">
      {(chips ?? []).map((c) => {
        const ativo = (valor || "TODOS") === c.situacao;
        return (
          <button
            key={c.situacao}
            type="button"
            role="tab"
            aria-selected={ativo}
            onClick={() => onChange(c.situacao === "TODOS" ? "" : c.situacao)}
            className={cn(
              "min-w-32 rounded-xl border bg-card px-3 py-2 text-left transition-all hover:bg-accent/40",
              ativo && "border-brand bg-brand/8 ring-1 ring-brand/30",
            )}
          >
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <span className={cn("size-1.5 rounded-full", PONTO[c.situacao])} />
              {ROTULO[c.situacao] ?? c.situacao}
              <span className="ml-auto rounded bg-muted px-1.5 text-[11px] text-foreground num">{numero(c.quantidade)}</span>
            </span>
            <span className="mt-0.5 block text-sm font-semibold num">{moeda(c.valor)}</span>
          </button>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ filtros
export function CampoPeriodo({
  de,
  ate,
  onChange,
  rotuloDe = "De",
  rotuloAte = "Até",
}: {
  de: string;
  ate: string;
  onChange: (de: string, ate: string) => void;
  rotuloDe?: string;
  rotuloAte?: string;
}) {
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        {rotuloDe}
        <Input type="date" value={de} onChange={(e) => onChange(e.target.value, ate)} className="h-9 w-40" />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        {rotuloAte}
        <Input type="date" value={ate} onChange={(e) => onChange(de, e.target.value)} className="h-9 w-40" />
      </label>
    </div>
  );
}

export function CampoMes({ valor, onChange, rotulo = "Mês" }: { valor: string; onChange: (v: string) => void; rotulo?: string }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {rotulo}
      <Input type="month" value={valor} onChange={(e) => e.target.value && onChange(e.target.value)} className="h-9 w-44" />
    </label>
  );
}

// ------------------------------------------------------------------------------------------------ opções
export interface Opcao {
  id: number;
  nome: string;
}

export function useOpcoesReceber() {
  return useQuery({
    queryKey: ["fin", "opcoes-receber"],
    queryFn: () => api.get<{ planos: Opcao[]; contas_bancarias: Opcao[] }>("/financeiro/receber/opcoes"),
    staleTime: 60_000,
    meta: { silencioso: true },
  });
}

export interface CategoriaOpcao extends Opcao {
  tipo: string;
  subcategorias: Opcao[];
}

export function useOpcoesPagar() {
  return useQuery({
    queryKey: ["fin", "opcoes-pagar"],
    queryFn: () => api.get<{ fornecedores: Opcao[]; categorias: CategoriaOpcao[]; contas_bancarias: Opcao[] }>("/financeiro/pagar/opcoes"),
    staleTime: 60_000,
    meta: { silencioso: true },
  });
}

export function SelectContaBancaria({
  valor,
  onChange,
  contas,
  vazio = "Não lançar no banco",
  id,
}: {
  valor: string;
  onChange: (v: string) => void;
  contas: Opcao[] | undefined;
  vazio?: string;
  id?: string;
}) {
  return (
    <NativeSelect id={id} value={valor} onChange={(e) => onChange(e.target.value)}>
      <option value="">{vazio}</option>
      {(contas ?? []).map((c) => (
        <option key={c.id} value={c.id}>
          {c.nome}
        </option>
      ))}
    </NativeSelect>
  );
}

// ------------------------------------------------------------------------------------------------ exportar
export function BotoesExportar({
  caminho,
  query,
  nome,
  className,
}: {
  caminho: string;
  query?: RequestOpts["query"];
  nome: string;
  className?: string;
}) {
  const baixarFormato = (formato: "xlsx" | "pdf") => baixar(caminho, { query: { ...query, formato } }, `${nome}.${formato}`);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Button variant="outline" size="sm" onClick={() => baixarFormato("xlsx")}>
        <FileSpreadsheet /> Excel
      </Button>
      <Button variant="outline" size="sm" onClick={() => baixarFormato("pdf")}>
        <FileText /> PDF
      </Button>
    </div>
  );
}

/** Caixa de resumo (KPI simples) usada nos relatórios. */
export function Resumo({ rotulo, valor, tom, sub }: { rotulo: string; valor: string; tom?: "success" | "danger" | "neutral"; sub?: string }) {
  return (
    <div className="card-surface p-4">
      <p className="text-[13px] font-medium text-muted-foreground">{rotulo}</p>
      <p className={cn("mt-1.5 text-2xl font-semibold tracking-tight num", tom === "success" && "text-success-ink", tom === "danger" && "text-danger-ink")}>
        {valor}
      </p>
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}
