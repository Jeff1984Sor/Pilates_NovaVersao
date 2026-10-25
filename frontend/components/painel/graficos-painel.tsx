"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { AulasMes } from "@/lib/tipos-painel";

const EIXO = { tick: { fontSize: 11, fill: "var(--muted-foreground)" }, axisLine: false, tickLine: false } as const;

/** Barras de aulas (reservas não canceladas) por mês; o último mês (atual) leva a cor cheia da marca. */
export function GraficoAulasPorMes({ meses }: { meses: AulasMes[] }) {
  const ultimo = meses.length - 1;
  return (
    <div className="h-64" role="img" aria-label={`Aulas por mês: ${meses.map((m) => `${m.rotulo} ${m.total}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={meses} margin={{ top: 16, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="rotulo" {...EIXO} />
          <YAxis {...EIXO} allowDecimals={false} width={44} />
          <Tooltip
            cursor={{ fill: "var(--accent)", opacity: 0.5 }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as AulasMes | undefined;
              if (!active || !p) return null;
              return (
                <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
                  <p className="font-medium">{p.rotulo}</p>
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground num">{p.total}</span> aula{p.total === 1 ? "" : "s"}
                  </p>
                </div>
              );
            }}
          />
          <Bar
            dataKey="total"
            radius={[6, 6, 0, 0]}
            maxBarSize={36}
            label={{ position: "top", fontSize: 11, fill: "var(--muted-foreground)" }}
            shape={(props: { x?: number; y?: number; width?: number; height?: number; index?: number }) => {
              const { x = 0, y = 0, width = 0, height = 0, index = 0 } = props;
              return (
                <rect
                  x={x}
                  y={y}
                  width={width}
                  height={Math.max(height, 0)}
                  rx={6}
                  fill="var(--brand)"
                  opacity={index === ultimo ? 1 : 0.55}
                />
              );
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
