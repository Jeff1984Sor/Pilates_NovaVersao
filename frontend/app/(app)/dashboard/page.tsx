"use client";

import { CalendarDays, FileSignature, LayoutDashboard, ReceiptText, UsersRound } from "lucide-react";

import { PageHeader } from "@/components/mayacorp/page-header";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";

const EM_BREVE = [
  { i: UsersRound, t: "Alunos ativos", d: "Total de alunos com contrato vigente." },
  { i: CalendarDays, t: "Aulas de hoje", d: "Ocupação por horário e professor." },
  { i: FileSignature, t: "Contratos a vencer", d: "Renovações nos próximos 30 dias." },
  { i: ReceiptText, t: "Recebimentos do mês", d: "Previsto, recebido e em atraso." },
];

/** Placeholder: o painel real é construído junto com os módulos de agenda, contratos e financeiro. */
export default function DashboardPage() {
  const { usuario } = useAuth();
  const { nome_exibicao } = useBrand();
  return (
    <div>
      <PageHeader
        titulo={`Olá, ${usuario?.nome.split(" ")[0] ?? ""}`}
        descricao={`Painel do ${nome_exibicao}`}
        icone={LayoutDashboard}
        migalhas={[{ label: "Início", href: "/" }, { label: "Painel" }]}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {EM_BREVE.map((c) => (
          <div key={c.t} className="card-surface p-5">
            <c.i className="mb-3 size-5 text-muted-foreground" />
            <p className="font-medium">{c.t}</p>
            <p className="mt-1 text-sm text-muted-foreground">{c.d}</p>
            <p className="mt-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Em breve</p>
          </div>
        ))}
      </div>
    </div>
  );
}
