"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight } from "lucide-react";
import { useState } from "react";

import { BotoesExportar, CampoPeriodo, mesAtual, Resumo, SituacaoPill } from "@/components/financeiro/comum";
import { GraficoFluxo, Legenda, pontosDiarios, pontosSemanais } from "@/components/financeiro/graficos";
import { Segmented } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda, toNum } from "@/lib/format";
import type { ContaBancaria, FluxoCaixa } from "@/lib/tipos-financeiro";
import { cn } from "@/lib/utils";

type Visao = "semana" | "dia";

export default function FluxoCaixaPage() {
  const { pode } = useAuth();
  const [periodo, setPeriodo] = useState(mesAtual);
  const [conta, setConta] = useState("");
  const [visao, setVisao] = useState<Visao>("semana");
  const podeVer = pode("financeiro_caixa.ver");
  const params = { de: periodo.de, ate: periodo.ate, conta_id: conta || undefined };
  const q = useQuery({
    queryKey: ["fin", "caixa", params],
    queryFn: () => api.get<FluxoCaixa>("/financeiro/caixa", params),
    enabled: podeVer,
    placeholderData: (p) => p,
  });
  const contas = useQuery({
    queryKey: ["fin", "contas-bancarias-caixa"],
    queryFn: () => api.get<ContaBancaria[]>("/financeiro/bancos/contas", { somente_ativas: true }),
    enabled: podeVer && pode("financeiro_bancos.ver"),
    meta: { silencioso: true },
  });
  if (!podeVer) return <SemAcesso />;
  const f = q.data;
  const pontos = f ? (visao === "dia" ? pontosDiarios(f.saldo_diario) : pontosSemanais(f.saldo_semanal)) : [];
  const comp = f?.comparativo_mes_anterior;

  return (
    <div>
      <PageHeader
        titulo="Fluxo de caixa"
        descricao="Previsão por data de vencimento (cancelados ficam de fora). O saldo inicial vem das contas bancárias ativas."
        icone={ArrowLeftRight}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "Fluxo de caixa" }]}
        acoes={<BotoesExportar caminho="/financeiro/caixa/exportar" query={params} nome="fluxo-de-caixa" />}
      />
      <div className="card-surface mb-5 flex flex-wrap items-end gap-3 p-4">
        <CampoPeriodo de={periodo.de} ate={periodo.ate} onChange={(de, ate) => setPeriodo({ de, ate })} />
        {(contas.data?.length ?? 0) > 0 && (
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Saldo inicial da conta
            <NativeSelect value={conta} onChange={(e) => setConta(e.target.value)} className="w-56">
              <option value="">Todas as contas ativas</option>
              {contas.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.banco} · {c.conta}
                </option>
              ))}
            </NativeSelect>
          </label>
        )}
      </div>

      {q.isPending || !f ? (
        <Skeleton className="h-96 rounded-2xl" />
      ) : (
        <div className={cn("space-y-5 transition-opacity", q.isFetching && "opacity-70")}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Resumo rotulo="Saldo bancário no início" valor={moeda(f.saldo_bancario_base)} tom={toNum(f.saldo_bancario_base) < 0 ? "danger" : undefined} />
            <Resumo rotulo="Receitas previstas" valor={moeda(f.total_receitas)} tom="success" />
            <Resumo rotulo="Despesas previstas" valor={moeda(f.total_despesas)} tom="danger" />
            <Resumo
              rotulo="Saldo projetado no fim"
              valor={moeda(f.saldo_projetado_final)}
              tom={toNum(f.saldo_projetado_final) < 0 ? "danger" : "success"}
              sub={comp ? `Mês anterior: ${moeda(comp.saldo)} (${toNum(comp.delta_saldo) >= 0 ? "+" : ""}${moeda(comp.delta_saldo)})` : undefined}
            />
          </div>

          <section className="card-surface p-4" aria-label="Gráfico do fluxo de caixa">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">Receitas, despesas e saldo</h2>
              <Segmented<Visao>
                value={visao}
                onChange={setVisao}
                opcoes={[
                  { value: "semana", label: "Por semana" },
                  { value: "dia", label: "Por dia" },
                ]}
              />
            </div>
            <Legenda
              itens={[
                { cor: "var(--success)", rotulo: "Receitas" },
                { cor: "var(--danger)", rotulo: "Despesas" },
                { cor: "var(--brand)", rotulo: "Saldo acumulado" },
              ]}
            />
            <div className="mt-3">
              <GraficoFluxo pontos={pontos} />
            </div>
          </section>

          {comp && (
            <section className="card-surface p-4 text-sm" aria-label="Comparativo com o mês anterior">
              <h2 className="mb-2 font-semibold">Comparativo com o período anterior ({comp.periodo})</h2>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  ["Receitas", comp.receitas, comp.delta_receitas],
                  ["Despesas", comp.despesas, comp.delta_despesas],
                  ["Saldo projetado", comp.saldo, comp.delta_saldo],
                ].map(([rotulo, valor, delta]) => (
                  <div key={rotulo}>
                    <p className="text-xs text-muted-foreground">{rotulo}</p>
                    <p className="font-semibold num">{moeda(valor)}</p>
                    <p className={cn("text-xs num", toNum(delta) >= 0 ? "text-success-ink" : "text-danger-ink")}>
                      {toNum(delta) >= 0 ? "+" : ""}
                      {moeda(delta)} no período atual
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="card-surface overflow-hidden" aria-label="Lançamentos previstos">
            <header className="flex items-center justify-between border-b px-4 py-3">
              <h2 className="font-semibold">Lançamentos previstos</h2>
              <span className="text-xs text-muted-foreground">{f.lancamentos.length} lançamento(s)</span>
            </header>
            {f.lancamentos.length === 0 ? (
              <EmptyState icone={ArrowLeftRight} titulo="Nada previsto no período" descricao="Troque o período para ver receitas e despesas." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Data</th>
                      <th className="px-3 py-2.5 font-medium">Tipo</th>
                      <th className="px-3 py-2.5 font-medium">Descrição</th>
                      <th className="px-3 py-2.5 font-medium">Detalhe</th>
                      <th className="px-3 py-2.5 font-medium">Situação</th>
                      <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {f.lancamentos.map((l, i) => (
                      <tr key={i} className="hover:bg-accent/40">
                        <td className="px-4 py-2.5 whitespace-nowrap num">{data(l.data)}</td>
                        <td className="px-3 py-2.5">
                          <span className={l.tipo === "Receita" ? "text-success-ink" : "text-danger-ink"}>{l.tipo}</span>
                        </td>
                        <td className="px-3 py-2.5">{l.descricao}</td>
                        <td className="px-3 py-2.5 text-muted-foreground">{l.detalhe}</td>
                        <td className="px-3 py-2.5">
                          <SituacaoPill situacao={l.status} />
                        </td>
                        <td className={cn("px-3 py-2.5 text-right font-medium num", l.tipo === "Despesa" && "text-danger-ink")}>
                          {l.tipo === "Despesa" ? "−" : ""}
                          {moeda(l.valor)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
