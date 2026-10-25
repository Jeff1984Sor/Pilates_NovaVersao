"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { useState } from "react";

import { BotoesExportar, CampoPeriodo, mesAtual, Resumo } from "@/components/financeiro/comum";
import { BarrasAgrupadas, COR_ENTRADA, COR_SAIDA } from "@/components/financeiro/graficos";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { moeda, toNum } from "@/lib/format";
import type { Dre } from "@/lib/tipos-financeiro";
import { cn } from "@/lib/utils";

function Linha({ rotulo, valor, forte, tom }: { rotulo: string; valor: string; forte?: boolean; tom?: "success" | "danger" }) {
  return (
    <tr className={cn(forte && "bg-muted/40 font-semibold")}>
      <td className="px-4 py-2.5">{rotulo}</td>
      <td className={cn("px-4 py-2.5 text-right num", tom === "success" && "text-success-ink", tom === "danger" && "text-danger-ink")}>{moeda(valor)}</td>
    </tr>
  );
}

function Bloco({ titulo, itens, cor }: { titulo: string; itens: { nome: string; total: string }[]; cor: string }) {
  return (
    <section className="card-surface p-4" aria-label={titulo}>
      <h3 className="mb-2 text-sm font-semibold">{titulo}</h3>
      <BarrasAgrupadas itens={itens} cor={cor} />
      {itens.length > 0 && (
        <ul className="mt-2 divide-y text-sm">
          {itens.map((i) => (
            <li key={i.nome} className="flex justify-between py-1.5">
              <span>{i.nome}</span>
              <span className="font-medium num">{moeda(i.total)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function DrePage() {
  const { pode } = useAuth();
  const [periodo, setPeriodo] = useState(mesAtual);
  const podeVer = pode("financeiro_dre.ver");
  const q = useQuery({
    queryKey: ["fin", "dre", periodo],
    queryFn: () => api.get<Dre>("/financeiro/dre", periodo),
    enabled: podeVer,
    placeholderData: (p) => p,
  });
  if (!podeVer) return <SemAcesso />;
  const d = q.data;

  return (
    <div>
      <PageHeader
        titulo="DRE"
        descricao="Demonstração do resultado por data de pagamento. Lançamentos avulsos e aulas avulsas aparecem em “Sem plano”."
        icone={BarChart3}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "DRE" }]}
        acoes={<BotoesExportar caminho="/financeiro/dre/exportar" query={periodo} nome="dre" />}
      />
      <div className="card-surface mb-5 flex flex-wrap items-end gap-3 p-4">
        <CampoPeriodo de={periodo.de} ate={periodo.ate} onChange={(de, ate) => setPeriodo({ de, ate })} />
      </div>
      {q.isPending || !d ? (
        <Skeleton className="h-96 rounded-2xl" />
      ) : (
        <div className={cn("space-y-5 transition-opacity", q.isFetching && "opacity-70")}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Resumo rotulo="Receita bruta" valor={moeda(d.receita_bruta)} tom="success" />
            <Resumo rotulo="Despesas operacionais" valor={moeda(d.despesas_operacionais)} tom="danger" />
            <Resumo
              rotulo={d.resultado_label === "Lucro" ? "Lucro do período" : "Prejuízo do período"}
              valor={moeda(d.resultado_final)}
              tom={toNum(d.resultado_final) >= 0 ? "success" : "danger"}
            />
            <Resumo rotulo="Saldo bancário final" valor={moeda(d.saldo_bancario_final)} sub={`Anterior: ${moeda(d.saldo_bancario_anterior)}`} />
          </div>

          <section className="card-surface overflow-hidden" aria-label="Demonstração">
            <table className="w-full text-sm">
              <tbody className="divide-y">
                <Linha rotulo="Receita bruta" valor={d.receita_bruta} forte />
                <Linha rotulo="(−) Deduções" valor={d.deducoes} />
                <Linha rotulo="Receita líquida" valor={d.receita_liquida} forte />
                <Linha rotulo="(−) Custo direto" valor={d.custo_direto} />
                <Linha rotulo="Lucro bruto" valor={d.lucro_bruto} forte />
                <Linha rotulo="(−) Despesas operacionais" valor={d.despesas_operacionais} />
                <Linha rotulo={`Resultado final (${d.resultado_label === "Lucro" ? "lucro" : "prejuízo"})`} valor={d.resultado_final} forte tom={toNum(d.resultado_final) >= 0 ? "success" : "danger"} />
              </tbody>
            </table>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <Bloco titulo="Receitas por plano" itens={d.receitas_por_plano} cor={COR_ENTRADA} />
            <Bloco titulo="Receitas por categoria" itens={d.receitas_por_categoria} cor={COR_ENTRADA} />
            <Bloco titulo="Receitas por subcategoria" itens={d.receitas_por_subcategoria} cor={COR_ENTRADA} />
            <Bloco titulo="Despesas por categoria" itens={d.despesas_por_categoria} cor={COR_SAIDA} />
            <Bloco titulo="Despesas por subcategoria" itens={d.despesas_por_subcategoria} cor={COR_SAIDA} />
          </div>
        </div>
      )}
    </div>
  );
}
