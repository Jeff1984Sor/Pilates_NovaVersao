"use client";

import { Sparkles, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";

import { FormAluno } from "@/components/alunos/form-aluno";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";

export default function NovoAlunoPage() {
  const { pode } = useAuth();
  const router = useRouter();
  if (!pode("alunos.editar")) return <SemAcesso titulo="Novo aluno" />;
  return (
    <div className="max-w-5xl">
      <PageHeader
        icone={UserPlus}
        titulo="Novo aluno"
        descricao="Cadastre os dados do aluno. Contratos e aulas são feitos depois, na ficha."
        migalhas={[{ label: "Alunos", href: "/alunos" }, { label: "Novo" }]}
        acoes={
          <Tooltip>
            <TooltipTrigger render={<span tabIndex={0} />}>
              <Button variant="outline" disabled>
                <Sparkles /> Preencher com IA
              </Button>
            </TooltipTrigger>
            <TooltipContent>Em breve: ler documento e comprovante de endereço para preencher o cadastro.</TooltipContent>
          </Tooltip>
        }
      />
      <div className="card-surface p-5">
        <FormAluno aluno={null} onSalvo={(a) => router.push(`/alunos/${a.id}`)} onCancelar={() => router.push("/alunos")} />
      </div>
    </div>
  );
}
