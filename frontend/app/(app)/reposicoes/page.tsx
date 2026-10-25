"use client";

import { Repeat } from "lucide-react";

import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { PainelReposicoes } from "@/components/reposicoes/painel-reposicoes";
import { useAuth } from "@/lib/auth";

export default function ReposicoesPage() {
  const { pode } = useAuth();
  if (!pode("reposicoes.ver")) return <SemAcesso titulo="Reposições" />;
  return (
    <div>
      <PageHeader
        titulo="Reposições"
        descricao="Pedidos dos alunos para repor aulas desmarcadas. A decisão é da gerência: aprove escolhendo uma aula com vaga ou recuse com motivo."
        icone={Repeat}
        migalhas={[{ label: "Início", href: "/" }, { label: "Agenda" }, { label: "Reposições" }]}
      />
      <PainelReposicoes podeDecidir={pode("reposicoes.editar")} />
    </div>
  );
}
