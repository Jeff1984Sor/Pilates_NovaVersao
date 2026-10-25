"use client";

import { useQuery } from "@tanstack/react-query";
import { FilePlus2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { FormContrato } from "@/components/contratos/form-contrato";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AlunoResumo } from "@/lib/tipos-alunos";

function Conteudo() {
  const alunoId = Number(useSearchParams().get("aluno_id")) || null;
  const inicial = useQuery({
    queryKey: ["contratos", "aluno-inicial", alunoId],
    queryFn: () => api.get<AlunoResumo>(`/alunos/${alunoId}/resumo`),
    enabled: !!alunoId,
    retry: false,
  });
  // com ?aluno_id=, espera o nome carregar para o formulário já nascer preenchido
  if (alunoId && inicial.isPending) return null; // (se o aluno não carregar, o formulário abre sem aluno)
  return <FormContrato alunoInicial={inicial.data ? { id: inicial.data.id, nome: inicial.data.nome } : null} />;
}

export default function NovoContratoPage() {
  const { pode } = useAuth();
  if (!pode("contratos.editar")) return <SemAcesso titulo="Novo contrato" />;
  return (
    <div className="max-w-6xl">
      <PageHeader
        icone={FilePlus2}
        titulo="Novo contrato"
        descricao="Escolha o aluno e o plano: o valor da aula, a parcela e o total aparecem na hora. Depois de criar, você escolhe a agenda."
        migalhas={[{ label: "Contratos", href: "/contratos" }, { label: "Novo" }]}
      />
      <Suspense fallback={null}>
        <Conteudo />
      </Suspense>
    </div>
  );
}
