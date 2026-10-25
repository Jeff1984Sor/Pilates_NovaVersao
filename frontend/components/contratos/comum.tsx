"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Pill } from "@/components/mayacorp/status-badge";
import { api } from "@/lib/api";
import { numero } from "@/lib/format";
import type { ChipContrato, ContagensContratos, OpcoesContrato, Situacao, StatusAssinatura } from "@/lib/tipos-contratos";
import { cn } from "@/lib/utils";

/** Invalida tudo de contratos (chaves que começam com "contratos"). */
export function useInvalidarContratos() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["contratos"] });
    qc.invalidateQueries({ queryKey: ["fin"] });
  };
}

export function useOpcoesContrato(habilitado = true) {
  return useQuery({
    queryKey: ["contratos", "opcoes"],
    queryFn: () => api.get<OpcoesContrato>("/contratos/opcoes"),
    staleTime: 60_000,
    enabled: habilitado,
  });
}

export function hojeISO(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" });
}

// ------------------------------------------------------------------------------------------------- situação
export function SituacaoContratoPill({ situacao }: { situacao: Situacao }) {
  const tom = situacao.badge === "danger" ? "danger" : situacao.badge === "warning" ? "warning" : "success";
  return <Pill tom={tom}>{situacao.rotulo}</Pill>;
}

const ASSINATURA: Record<StatusAssinatura, { rotulo: string; tom: "success" | "warning" | "info" }> = {
  NAO_ASSINADO: { rotulo: "Não assinado", tom: "warning" },
  ASSINADO: { rotulo: "Assinado na recepção", tom: "success" },
  ASSINADO_DIGITALMENTE: { rotulo: "Assinado digitalmente", tom: "success" },
};

export function AssinaturaPill({ status }: { status: StatusAssinatura }) {
  const a = ASSINATURA[status];
  return <Pill tom={a.tom}>{a.rotulo}</Pill>;
}

// ---------------------------------------------------------------------------------------------------- chips
const CHIPS: { id: ChipContrato; rotulo: string; ponto: string; chave: keyof ContagensContratos }[] = [
  { id: "ativos", rotulo: "Ativos", ponto: "bg-success", chave: "ativos" },
  { id: "vencendo", rotulo: "Vencendo em 30 dias", ponto: "bg-warning", chave: "vencendo" },
  { id: "vencidos", rotulo: "Vencidos", ponto: "bg-danger", chave: "vencidos" },
  { id: "nao_assinados", rotulo: "Não assinados", ponto: "bg-info", chave: "nao_assinados" },
  { id: "todos", rotulo: "Todos", ponto: "bg-muted-foreground/60", chave: "total" },
];

/** Chips de vigência com contagem (padrão da lista de alunos e de contas a receber). */
export function ChipsContratos({
  contagens,
  valor,
  onChange,
}: {
  contagens: ContagensContratos | undefined;
  valor: ChipContrato;
  onChange: (v: ChipContrato) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 p-3" role="tablist" aria-label="Situação dos contratos">
      {CHIPS.map((c) => {
        const ativo = valor === c.id;
        return (
          <button
            key={c.id}
            type="button"
            role="tab"
            aria-selected={ativo}
            onClick={() => onChange(c.id)}
            className={cn(
              "min-w-36 rounded-xl border bg-card px-3 py-2 text-left transition-all hover:bg-accent/40",
              ativo && "border-brand bg-brand/8 ring-1 ring-brand/30",
            )}
          >
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <span className={cn("size-1.5 rounded-full", c.ponto)} />
              {c.rotulo}
              <span className="num ml-auto rounded bg-muted px-1.5 text-[11px] text-foreground">
                {contagens ? numero(contagens[c.chave]) : "…"}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function rotuloForma(f: string | null | undefined) {
  return ({ PIX: "Pix", DINHEIRO: "Dinheiro", CREDITO: "Crédito", DEBITO: "Débito" } as Record<string, string>)[f ?? ""] ?? "—";
}

/** Só dígitos → máscara de CPF enquanto digita. */
export function mascaraCpf(v: string) {
  const d = v.replace(/\D/g, "").slice(0, 11);
  return d
    .replace(/^(\d{3})(\d)/, "$1.$2")
    .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1-$2");
}
