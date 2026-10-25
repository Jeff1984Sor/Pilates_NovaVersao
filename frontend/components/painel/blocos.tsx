"use client";

import { AlertTriangle, ArrowDownRight, ArrowUpRight, Check, Circle, Info, Minus } from "lucide-react";
import Link from "next/link";

import { Skeleton } from "@/components/ui/skeleton";
import { data, moeda, percentual } from "@/lib/format";
import type { AlertaPainel, Aniversariante, PassoInicial } from "@/lib/tipos-painel";
import { cn } from "@/lib/utils";

type Icone = React.ComponentType<{ className?: string }>;

/** KPI clicável: o cartão inteiro leva à tela filtrada. */
export function KpiPainel({
  titulo,
  valor,
  rodape,
  icone: Icone,
  href,
  tom = "neutro",
  carregando,
}: {
  titulo: string;
  valor: React.ReactNode;
  rodape?: React.ReactNode;
  icone: Icone;
  href?: string | null;
  tom?: "neutro" | "perigo";
  carregando?: boolean;
}) {
  const corpo = (
    <div
      className={cn(
        "group card-surface relative h-full overflow-hidden p-4 transition-shadow",
        href && "hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      <div className="pointer-events-none absolute -top-10 -right-10 size-28 rounded-full bg-brand/10 blur-2xl md:opacity-60" />
      <div className="relative flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-muted-foreground">{titulo}</p>
        <div
          className={cn(
            "grid size-8 place-items-center rounded-lg",
            tom === "perigo" ? "bg-danger/10 text-danger-ink" : "bg-brand/10 text-navy dark:text-brand",
          )}
        >
          <Icone className="size-4" />
        </div>
      </div>
      {carregando ? (
        <>
          <Skeleton className="mt-3 h-8 w-24" />
          <Skeleton className="mt-3 h-4 w-32" />
        </>
      ) : (
        <>
          <p className={cn("relative mt-2 truncate text-[22px] leading-tight font-semibold tracking-tight num sm:text-[26px]", tom === "perigo" && "text-danger-ink")}>
            {valor}
          </p>
          {rodape && <p className="relative mt-2 text-xs text-muted-foreground">{rodape}</p>}
        </>
      )}
    </div>
  );
  return href && !carregando ? (
    <Link href={href} className="block rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {corpo}
    </Link>
  ) : (
    corpo
  );
}

/** Cartão de seção com título e (opcional) ação à direita. */
export function Secao({
  titulo,
  descricao,
  acao,
  children,
  className,
}: {
  titulo: string;
  descricao?: string;
  acao?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("card-surface p-5", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{titulo}</h2>
          {descricao && <p className="mt-0.5 text-xs text-muted-foreground">{descricao}</p>}
        </div>
        {acao}
      </div>
      {children}
    </section>
  );
}

export function Vazio({ icone: Icone, texto, dica }: { icone: Icone; texto: string; dica?: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-4 py-8 text-center">
      <div className="grid size-10 place-items-center rounded-xl bg-muted text-muted-foreground">
        <Icone className="size-5" />
      </div>
      <p className="text-sm font-medium">{texto}</p>
      {dica && <p className="max-w-xs text-xs text-muted-foreground">{dica}</p>}
    </div>
  );
}

export function LinhasEsqueleto({ n = 4 }: { n?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: n }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

const ROTULO_STATUS: Record<string, { rotulo: string; classe: string }> = {
  RESERVADA: { rotulo: "Reservada", classe: "bg-brand/10 text-navy dark:text-brand" },
  PENDENTE: { rotulo: "Pendente", classe: "bg-warning/15 text-warning-ink" },
};

export function SeloStatusAula({ status }: { status: string }) {
  const s = ROTULO_STATUS[status] ?? { rotulo: status, classe: "bg-muted text-muted-foreground" };
  return <span className={cn("rounded-md px-1.5 py-0.5 text-[11px] font-medium", s.classe)}>{s.rotulo}</span>;
}

export function VariacaoRecebido({ pct, base }: { pct: number | null; base: string | null }) {
  if (pct == null) return <span>sem base de comparação no mês anterior</span>;
  const Seta = pct === 0 ? Minus : pct > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span
        className={cn(
          "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-medium",
          pct === 0 && "bg-muted text-muted-foreground",
          pct > 0 && "bg-success/10 text-success-ink",
          pct < 0 && "bg-danger/10 text-danger-ink",
        )}
      >
        <Seta className="size-3" />
        {percentual(pct)}
      </span>
      <span>vs. mesmo período do mês anterior ({moeda(base)})</span>
    </span>
  );
}

const ESTILO_ALERTA = {
  critico: { Icone: AlertTriangle, classe: "bg-danger/10 text-danger-ink" },
  aviso: { Icone: AlertTriangle, classe: "bg-warning/15 text-warning-ink" },
  info: { Icone: Info, classe: "bg-muted text-muted-foreground" },
} as const;

export function ItemAlerta({ a }: { a: AlertaPainel }) {
  const { Icone, classe } = ESTILO_ALERTA[a.gravidade] ?? ESTILO_ALERTA.info;
  const conteudo = (
    <div className="flex items-start gap-3 rounded-xl border p-3 transition-colors hover:bg-accent/40">
      <div className={cn("grid size-8 shrink-0 place-items-center rounded-lg", classe)}>
        <Icone className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {a.titulo}
          {a.chave !== "whatsapp_automatico_desligado" && (
            <span className="ml-1.5 rounded-md bg-muted px-1.5 py-0.5 text-xs num">
              {a.quantidade}
              {a.valor ? ` · ${moeda(a.valor)}` : ""}
            </span>
          )}
        </p>
        {a.detalhe && <p className="mt-0.5 text-xs text-muted-foreground">{a.detalhe}</p>}
      </div>
    </div>
  );
  return a.href ? (
    <Link href={a.href} className="block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {conteudo}
    </Link>
  ) : (
    conteudo
  );
}

export function LinhaAniversariante({ a }: { a: Aniversariante }) {
  const dia = data(a.dia).slice(0, 5);
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <Link href={`/alunos/${a.aluno_id}`} className="min-w-0 truncate text-sm font-medium hover:underline">
        {a.nome}
      </Link>
      <span className="shrink-0 text-xs text-muted-foreground">
        {a.hoje ? <strong className="text-navy dark:text-brand">Hoje</strong> : dia} · {a.idade} anos
      </span>
    </li>
  );
}

export function ListaPassos({ passos }: { passos: PassoInicial[] }) {
  return (
    <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {passos.map((p, i) => (
        <li key={p.chave}>
          <Link
            href={p.href}
            className={cn(
              "flex h-full items-start gap-3 rounded-xl border p-3 transition-colors hover:bg-accent/40",
              p.feito && "opacity-70",
            )}
          >
            <span
              className={cn(
                "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold",
                p.feito ? "bg-success/15 text-success-ink" : "bg-brand/10 text-navy dark:text-brand",
              )}
              aria-label={p.feito ? "feito" : "pendente"}
            >
              {p.feito ? <Check className="size-3.5" /> : p.conta ? i + 1 : <Circle className="size-3" />}
            </span>
            <span className="min-w-0">
              <span className={cn("block text-sm font-medium", p.feito && "line-through")}>{p.titulo}</span>
              <span className="block text-xs text-muted-foreground">{p.descricao}</span>
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
