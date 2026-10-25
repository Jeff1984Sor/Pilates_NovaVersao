"use client";

import { CalendarCheck } from "lucide-react";

import { PainelOperacional } from "@/components/agenda/painel-operacional";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

export default function AulasPage() {
  const { pode } = useAuth();
  if (!pode("aulas.ver")) return <SemAcesso />;
  return (
    <div>
      <PageHeader
        titulo="Painel operacional"
        descricao="Chegada, evolução e cobrança dos alunos, agrupados por horário e profissional."
        icone={CalendarCheck}
        migalhas={[{ label: "Início", href: "/" }, { label: "Agenda" }, { label: "Aulas" }]}
      />
      <PainelOperacional />
    </div>
  );
}
