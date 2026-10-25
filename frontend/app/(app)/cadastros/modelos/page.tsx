"use client";

import { ChevronRight, FileText, NotebookPen } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/mayacorp/page-header";
import { useAuth } from "@/lib/auth";

const MODELOS = [
  {
    href: "/cadastros/modelos-contrato",
    titulo: "Modelos de contrato",
    descricao: "Texto do contrato com variáveis do aluno, do plano e do contrato. Cada plano usa um modelo.",
    icone: FileText,
  },
  {
    href: "/cadastros/modelos-evolucao",
    titulo: "Modelos de evolução",
    descricao: "Textos-base que o professor aplica na gaveta de evolução da aula.",
    icone: NotebookPen,
  },
];

export default function ModelosPage() {
  const { pode } = useAuth();
  return (
    <div>
      <PageHeader
        titulo="Modelos"
        descricao="Textos prontos usados em contratos e nas evoluções das aulas."
        icone={FileText}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: "Modelos" }]}
      />
      {pode("cadastros_modelos.ver") && (
        <div className="grid gap-4 sm:grid-cols-2">
          {MODELOS.map(({ href, titulo, descricao, icone: Icone }) => (
            <Link key={href} href={href} className="card-surface group flex items-start gap-4 p-5 transition-colors hover:bg-accent/40">
              <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand/12 text-navy ring-1 ring-brand/25 dark:text-brand">
                <Icone className="size-5" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="font-semibold">{titulo}</h2>
                <p className="mt-0.5 text-sm text-muted-foreground">{descricao}</p>
              </div>
              <ChevronRight className="mt-1 size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
