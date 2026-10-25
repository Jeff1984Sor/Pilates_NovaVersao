"use client";

import { CalendarPlus } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AgendaContrato } from "@/components/contratos/agenda-contrato";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useAuth } from "@/lib/auth";

function Conteudo({ id }: { id: number }) {
  const novo = useSearchParams().get("novo") === "1";
  return <AgendaContrato contratoId={id} novo={novo} />;
}

export default function AgendaDoContratoPage() {
  const { pode } = useAuth();
  const id = Number(useParams<{ id: string }>().id);
  if (!pode("contratos.editar") || !pode("agenda.ver")) return <SemAcesso titulo="Agenda do contrato" />;
  return (
    <div className="max-w-4xl">
      <PageHeader
        icone={CalendarPlus}
        titulo="Agenda do contrato"
        descricao="Um horário por dia da semana. As aulas são reservadas já ligadas a este contrato."
        migalhas={[{ label: "Contratos", href: "/contratos" }, { label: "Contrato", href: `/contratos/${id}` }, { label: "Agenda" }]}
      />
      <Suspense fallback={null}>
        <Conteudo id={id} />
      </Suspense>
    </div>
  );
}
