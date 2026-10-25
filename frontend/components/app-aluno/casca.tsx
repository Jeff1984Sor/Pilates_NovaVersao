"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, LogOut, Repeat, WifiOff } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ClientLogo } from "@/components/mayacorp/brand";
import { Skeleton } from "@/components/ui/skeleton";
import { useBrand } from "@/lib/brand";
import type { AlunoMe, ReposicaoAluno } from "@/lib/tipos-app-aluno";
import { cn } from "@/lib/utils";

import { apiAluno, semSessao } from "./api-aluno";
import { InstalarApp } from "./instalar-app";

/** Hook: o aluno logado. 401 = sem sessão (o BFF já limpou os cookies) e quem usa manda para a tela de entrada. */
export function useAlunoMe() {
  return useQuery({
    queryKey: ["aluno", "me"],
    queryFn: () => apiAluno<AlunoMe>("/me"),
    staleTime: 5 * 60_000,
    retry: false,
    meta: { silencioso: true },
  });
}

export function useReposicoes() {
  return useQuery({
    queryKey: ["aluno", "reposicoes"],
    queryFn: () => apiAluno<ReposicaoAluno[]>("/reposicoes"),
    staleTime: 30_000,
    meta: { silencioso: true },
  });
}

function useOnline() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const atualizar = () => setOnline(navigator.onLine);
    atualizar();
    window.addEventListener("online", atualizar);
    window.addEventListener("offline", atualizar);
    return () => {
      window.removeEventListener("online", atualizar);
      window.removeEventListener("offline", atualizar);
    };
  }, []);
  return online;
}

const ABAS = [
  { href: "/app", rotulo: "Minhas aulas", icone: CalendarCheck },
  { href: "/app/reposicoes", rotulo: "Reposições", icone: Repeat },
] as const;

/** Estrutura das telas do aluno (com sessão): cabeçalho com a marca do estúdio, conteúdo e barra de abas embaixo. */
export function Casca({ children }: { children: React.ReactNode }) {
  const me = useAlunoMe();
  const reposicoes = useReposicoes();
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  const { nome_exibicao } = useBrand();
  const online = useOnline();
  const [saindo, setSaindo] = useState(false);

  useEffect(() => {
    if (me.isError && semSessao(me.error)) router.replace("/app/entrar");
  }, [me.isError, me.error, router]);

  async function sair() {
    setSaindo(true);
    try {
      await apiAluno("/auth/sair", { method: "POST" });
    } catch {
      /* o cookie some mesmo assim na próxima chamada recusada */
    }
    qc.clear();
    router.replace("/app/entrar");
  }

  const pendentes = (reposicoes.data ?? []).filter((r) => r.dentro_do_prazo).length;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/95 pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="flex items-center gap-3 px-4 py-3">
          <ClientLogo className="size-10" compacto />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] leading-tight font-semibold">{nome_exibicao}</p>
            {me.data ? (
              <p className="truncate text-xs text-muted-foreground">Olá, {me.data.primeiro_nome}</p>
            ) : (
              <Skeleton className="mt-1 h-3 w-24" />
            )}
          </div>
          <button
            type="button"
            onClick={sair}
            disabled={saindo}
            className="inline-flex h-11 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted-foreground hover:bg-muted active:bg-muted disabled:opacity-50"
          >
            <LogOut className="size-4" /> Sair
          </button>
        </div>
        {!online && (
          <div role="status" className="flex items-center gap-2 bg-warning/15 px-4 py-2 text-xs text-warning-ink">
            <WifiOff className="size-3.5" /> Você está sem internet. Os horários podem estar desatualizados.
          </div>
        )}
      </header>

      <main className="flex-1 px-4 pt-4 pb-28">
        <InstalarApp />
        {me.isPending ? <Esqueleto /> : me.isError && semSessao(me.error) ? <Esqueleto /> : children}
      </main>

      <nav
        aria-label="Navegação do app"
        className="fixed inset-x-0 bottom-0 z-20 mx-auto grid max-w-md grid-cols-2 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      >
        {ABAS.map((a) => {
          const ativa = a.href === "/app" ? pathname === "/app" : pathname.startsWith(a.href);
          return (
            <Link
              key={a.href}
              href={a.href}
              aria-current={ativa ? "page" : undefined}
              className={cn(
                "relative flex min-h-16 flex-col items-center justify-center gap-1 text-xs font-medium",
                ativa ? "text-brand" : "text-muted-foreground",
              )}
            >
              <a.icone className="size-5" />
              {a.rotulo}
              {a.href === "/app/reposicoes" && pendentes > 0 && (
                <span className="absolute top-2 left-1/2 ml-3 grid min-w-4 place-items-center rounded-full bg-brand px-1 text-[10px] leading-4 font-bold text-brand-foreground">
                  {pendentes}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function Esqueleto() {
  return (
    <div className="space-y-3" aria-hidden>
      <Skeleton className="h-5 w-28" />
      <Skeleton className="h-32 w-full rounded-2xl" />
      <Skeleton className="h-32 w-full rounded-2xl" />
    </div>
  );
}
