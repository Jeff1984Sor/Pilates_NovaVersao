"use client";

import { useQuery } from "@tanstack/react-query";
import { Mail, MessageCircle, UserX } from "lucide-react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { abasVisiveis } from "@/components/alunos/abas";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AlunoOut, AlunoResumo } from "@/lib/tipos-alunos";
import { cn } from "@/lib/utils";

function Ficha() {
  const { id } = useParams<{ id: string }>();
  const alunoId = Number(id);
  const { pode, somenteProprias } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const completo = pode("alunos.ver");
  const abas = abasVisiveis(pode, somenteProprias);
  const aba = abas.find((a) => a.id === params.get("aba")) ?? abas[0];

  // perfil sem alunos.ver (Professor) lê só o cabeçalho mínimo
  const q = useQuery({
    queryKey: ["aluno", alunoId, completo ? "completo" : "resumo"],
    queryFn: () => (completo ? api.get<AlunoOut>(`/alunos/${alunoId}`) : api.get<AlunoResumo>(`/alunos/${alunoId}/resumo`)),
    enabled: Number.isInteger(alunoId) && alunoId > 0 && (completo || pode("aulas.ver")),
    retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2,
    meta: { silencioso: true },
  });

  if (!completo && !pode("aulas.ver")) return <SemAcesso titulo="Ficha do aluno" />;

  if (q.isError) {
    return (
      <EmptyState
        icone={UserX}
        titulo="Aluno não encontrado"
        descricao="O cadastro não existe ou você não tem acesso a ele."
        acao={
          <Button variant="outline" onClick={() => router.replace("/alunos")}>
            Voltar para a lista
          </Button>
        }
        className="py-20"
      />
    );
  }
  if (q.isPending) return <Skeleton className="h-64 rounded-2xl" />;

  const a = q.data;
  const cheio = completo ? (a as AlunoOut) : null;
  const principal = cheio?.telefones.find((t) => t.principal) ?? cheio?.telefones[0];

  function irParaAba(id: string) {
    const p = new URLSearchParams(params.toString());
    p.set("aba", id);
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  const Componente = aba?.componente;
  return (
    <div>
      <PageHeader
        titulo={
          <span className="flex items-center gap-3">
            <UserAvatar nome={a.nome} fotoUrl={a.foto_url} className="size-12" textoClassName="text-base" inativo={a.status === "INATIVO"} />
            <span className="truncate">{a.nome}</span>
          </span>
        }
        migalhas={[{ label: "Alunos", href: completo ? "/alunos" : undefined }, { label: a.nome }]}
        descricao={
          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <Pill tom={a.status === "ATIVO" ? "success" : "neutral"}>{a.status === "ATIVO" ? "Ativo" : "Inativo"}</Pill>
            {cheio && (
              <>
                <span>{cheio.cpf_mascarado ?? (cheio.sem_cpf ? "Sem CPF" : "")}</span>
                {principal && (
                  <a href={`https://wa.me/${principal.whatsapp}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-foreground hover:underline">
                    <MessageCircle className="size-3.5" /> {principal.formatado}
                  </a>
                )}
                {cheio.email && (
                  <a href={`mailto:${cheio.email}`} className="inline-flex items-center gap-1 hover:text-foreground hover:underline">
                    <Mail className="size-3.5" /> {cheio.email}
                  </a>
                )}
              </>
            )}
            {a.unidade_nome && <span>{a.unidade_nome}</span>}
          </span>
        }
        acoes={abas
          .filter((x) => x.atalho)
          .map((x) => (
            <Button key={x.id} variant={aba?.id === x.id ? "default" : "outline"} size="sm" onClick={() => irParaAba(x.id)}>
              <x.icone /> {x.rotulo}
            </Button>
          ))}
      />

      <nav className="mb-4 flex gap-1 overflow-x-auto border-b" aria-label="Seções da ficha">
        {abas.map((x) => (
          <button
            key={x.id}
            type="button"
            onClick={() => irParaAba(x.id)}
            aria-current={aba?.id === x.id ? "page" : undefined}
            className={cn(
              "-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors",
              aba?.id === x.id ? "border-brand text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <x.icone className="size-4" />
            {x.rotulo}
          </button>
        ))}
      </nav>

      {Componente ? <Componente key={aba.id} alunoId={alunoId} /> : <SemAcesso titulo="Sem seções disponíveis" />}
    </div>
  );
}

export default function FichaAlunoPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 rounded-2xl" />}>
      <Ficha />
    </Suspense>
  );
}
