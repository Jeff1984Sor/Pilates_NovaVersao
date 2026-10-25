"use client";

import { Sparkles, UserPlus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AssistenteIA } from "@/components/alunos/assistente-ia";
import { FormAluno } from "@/components/alunos/form-aluno";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import type { DadosAssistenteIA } from "@/lib/tipos-app-aluno";
import { useAuth } from "@/lib/auth";

export default function NovoAlunoPage() {
  return (
    <Suspense>
      <NovoAluno />
    </Suspense>
  );
}

function NovoAluno() {
  const { pode } = useAuth();
  const router = useRouter();
  const abrirIA = useSearchParams().get("ia") === "1";
  const [iaAberta, setIaAberta] = useState(abrirIA); // vindo da lista com ?ia=1 já abre o assistente
  const [sugestao, setSugestao] = useState<DadosAssistenteIA | null>(null);
  if (!pode("alunos.editar")) return <SemAcesso titulo="Novo aluno" />;
  return (
    <div className="max-w-5xl">
      <PageHeader
        icone={UserPlus}
        titulo="Novo aluno"
        descricao="Cadastre os dados do aluno. Contratos e aulas são feitos depois, na ficha."
        migalhas={[{ label: "Alunos", href: "/alunos" }, { label: "Novo" }]}
        acoes={
          pode("ia.usar") ? (
            <Button variant="outline" onClick={() => setIaAberta(true)}>
              <Sparkles /> Preencher com IA
            </Button>
          ) : null
        }
      />
      <AssistenteIA open={iaAberta} onOpenChange={setIaAberta} onAplicar={(d) => setSugestao({ ...d })} />
      <div className="card-surface p-5">
        <FormAluno
          aluno={null}
          sugestao={sugestao}
          onSalvo={(a) => router.push(`/alunos/${a.id}`)}
          onCancelar={() => router.push("/alunos")}
        />
      </div>
    </div>
  );
}
