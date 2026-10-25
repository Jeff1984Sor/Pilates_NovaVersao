"use client";

import { CalendarDays } from "lucide-react";
import { useState } from "react";

import { GavetaAluno } from "@/components/agenda/gaveta-aluno";
import { GradeSemanal } from "@/components/agenda/grade-semanal";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

export default function GradeSemanalPage() {
  const { pode } = useAuth();
  const [aberta, setAberta] = useState<number | null>(null);
  if (!pode("agenda.ver")) return <SemAcesso />;
  return (
    <div>
      <PageHeader
        titulo="Grade semanal"
        descricao="Aulas da semana por horário, com a ocupação (alunos/vagas) e a cor de cada situação."
        icone={CalendarDays}
        migalhas={[{ label: "Início", href: "/" }, { label: "Agenda" }, { label: "Grade semanal" }]}
      />
      <GradeSemanal onAbrirReserva={pode("aulas.ver") ? setAberta : undefined} />
      <GavetaAluno key={aberta ?? "fechada"} reservaId={aberta} onFechar={() => setAberta(null)} />
    </div>
  );
}
