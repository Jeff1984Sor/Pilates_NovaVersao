"use client";

import { Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { data, moeda, moedaCompacta, toNum } from "@/lib/format";

const EIXO = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, axisLine: false, tickLine: false } as const;
const GRADE = { stroke: "var(--border)", strokeDasharray: "3 3" } as const;
const COR_ENTRADA = "var(--success)";
const COR_SAIDA = "var(--danger)";
const COR_SALDO = "var(--brand)";

function Dica({ titulo, linhas }: { titulo: string; linhas: { cor: string; rotulo: string; valor: string }[] }) {
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium">{titulo}</p>
      {linhas.map((l) => (
        <p key={l.rotulo} className="flex items-center gap-2">
          <span className="size-2 rounded-full" style={{ background: l.cor }} />
          <span className="text-muted-foreground">{l.rotulo}</span>
          <span className="ml-auto font-medium num">{l.valor}</span>
        </p>
      ))}
    </div>
  );
}

export function Legenda({ itens }: { itens: { cor: string; rotulo: string }[] }) {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
      {itens.map((i) => (
        <span key={i.rotulo} className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: i.cor }} />
          {i.rotulo}
        </span>
      ))}
    </div>
  );
}

export interface PontoFluxo {
  rotulo: string;
  receitas: number;
  despesas: number;
  saldo: number;
}

/** Barras de receitas/despesas previstas e linha do saldo acumulado (Recharts). */
export function GraficoFluxo({ pontos }: { pontos: PontoFluxo[] }) {
  return (
    <div className="h-72" role="img" aria-label="Receitas, despesas e saldo projetado no período">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={pontos} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid vertical={false} {...GRADE} />
          <XAxis dataKey="rotulo" {...EIXO} minTickGap={14} />
          <YAxis yAxisId="v" {...EIXO} width={60} tickFormatter={(v) => moedaCompacta(v)} />
          <YAxis yAxisId="s" orientation="right" {...EIXO} width={60} tickFormatter={(v) => moedaCompacta(v)} />
          <Tooltip
            cursor={{ fill: "var(--accent)", opacity: 0.5 }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as PontoFluxo | undefined;
              if (!active || !p) return null;
              return (
                <Dica
                  titulo={p.rotulo}
                  linhas={[
                    { cor: COR_ENTRADA, rotulo: "Receitas", valor: moeda(p.receitas) },
                    { cor: COR_SAIDA, rotulo: "Despesas", valor: moeda(p.despesas) },
                    { cor: COR_SALDO, rotulo: "Saldo", valor: moeda(p.saldo) },
                  ]}
                />
              );
            }}
          />
          <Bar yAxisId="v" dataKey="receitas" fill={COR_ENTRADA} maxBarSize={22} radius={[4, 4, 0, 0]} />
          <Bar yAxisId="v" dataKey="despesas" fill={COR_SAIDA} maxBarSize={22} radius={[4, 4, 0, 0]} />
          <Line yAxisId="s" type="monotone" dataKey="saldo" stroke={COR_SALDO} strokeWidth={2.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function pontosDiarios(dias: { data: string; receitas: string; despesas: string; saldo: string }[]): PontoFluxo[] {
  return dias.map((d) => ({ rotulo: data(d.data).slice(0, 5), receitas: toNum(d.receitas), despesas: toNum(d.despesas), saldo: toNum(d.saldo) }));
}

export function pontosSemanais(semanas: { inicio: string; fim: string; receitas: string; despesas: string; saldo: string }[]): PontoFluxo[] {
  return semanas.map((s) => ({
    rotulo: `${data(s.inicio).slice(0, 5)}–${data(s.fim).slice(0, 5)}`,
    receitas: toNum(s.receitas),
    despesas: toNum(s.despesas),
    saldo: toNum(s.saldo),
  }));
}

/** Barras horizontais de um agrupamento da DRE (plano, categoria...). */
export function BarrasAgrupadas({ itens, cor }: { itens: { nome: string; total: string }[]; cor: string }) {
  const dados = itens.slice(0, 10).map((i) => ({ nome: i.nome, total: toNum(i.total) }));
  if (dados.length === 0) return <p className="py-8 text-center text-sm text-muted-foreground">Nada no período</p>;
  return (
    <div style={{ height: Math.max(120, dados.length * 38 + 20) }} role="img" aria-label="Valores por grupo">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={dados} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} {...GRADE} />
          <XAxis type="number" {...EIXO} tickFormatter={(v) => moedaCompacta(v)} />
          <YAxis type="category" dataKey="nome" {...EIXO} width={130} />
          <Tooltip
            cursor={{ fill: "var(--accent)", opacity: 0.5 }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as { nome: string; total: number } | undefined;
              if (!active || !p) return null;
              return <Dica titulo={p.nome} linhas={[{ cor, rotulo: "Total", valor: moeda(p.total) }]} />;
            }}
          />
          <Bar dataKey="total" fill={cor} radius={[0, 4, 4, 0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export { COR_ENTRADA, COR_SAIDA, COR_SALDO };
