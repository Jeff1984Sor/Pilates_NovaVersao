"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, Loader2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PaginaContagens } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

/** Mostra a tela só a quem tem a permissão de ver; o servidor confere de novo em cada chamada. */
export function Guarda({ permissao, children }: { permissao: string; children: React.ReactNode }) {
  const { pode } = useAuth();
  return pode(permissao) ? <>{children}</> : <SemAcesso />;
}

type Filtros = Record<string, string | number | boolean | null | undefined>;

/**
 * Lista paginada dos cadastros: busca (com atraso), ordenação por coluna, paginação e filtros (chips).
 * Devolve também as `contagens` dos chips que a API calcula.
 */
export function useLista<T>(chave: string, path: string, filtrosIniciais: Filtros = {}, porPagina = 15, ordenacaoInicial?: string) {
  const [q, setQBruto] = useState("");
  const [pagina, setPagina] = useState(1);
  const [ordenar, setOrdenar] = useState(ordenacaoInicial ?? "");
  const [direcao, setDirecao] = useState<"asc" | "desc">("asc");
  const [filtros, setFiltros] = useState<Filtros>(filtrosIniciais);
  const busca = useDebounce(q, 300);

  const query = useQuery({
    queryKey: [chave, path, busca, pagina, porPagina, ordenar, direcao, filtros],
    queryFn: () => api.get<PaginaContagens<T>>(path, { q: busca, pagina, por_pagina: porPagina, ordenar, direcao, ...filtros }),
    placeholderData: keepPreviousData,
  });

  return {
    ...query,
    q,
    setQ: (v: string) => {
      setQBruto(v);
      setPagina(1);
    },
    pagina,
    setPagina,
    porPagina,
    ordenar,
    direcao,
    ordenarPor: (coluna: string) => {
      if (ordenar === coluna) setDirecao((d) => (d === "asc" ? "desc" : "asc"));
      else {
        setOrdenar(coluna);
        setDirecao("asc");
      }
      setPagina(1);
    },
    filtros,
    setFiltro: (k: string, v: Filtros[string]) => {
      setFiltros((f) => ({ ...f, [k]: v }));
      setPagina(1);
    },
    limpar: () => {
      setQBruto("");
      setFiltros(filtrosIniciais);
      setPagina(1);
    },
    itens: query.data?.itens ?? [],
    total: query.data?.total ?? 0,
    contagens: query.data?.contagens ?? {},
  };
}

/** Cabeçalho de coluna ordenável. */
export function Th({
  coluna,
  atual,
  direcao,
  onOrdenar,
  children,
  className,
}: {
  coluna?: string;
  atual?: string;
  direcao?: "asc" | "desc";
  onOrdenar?: (c: string) => void;
  children?: React.ReactNode;
  className?: string;
}) {
  if (!coluna || !onOrdenar) return <th className={cn("px-3 py-2.5 font-medium", className)}>{children}</th>;
  const ativa = atual === coluna;
  const Seta = !ativa ? ArrowUpDown : direcao === "asc" ? ArrowUp : ArrowDown;
  return (
    <th className={cn("px-3 py-2.5 font-medium", className)} aria-sort={ativa ? (direcao === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onOrdenar(coluna)} className="inline-flex items-center gap-1 hover:text-foreground">
        {children}
        <Seta className={cn("size-3", !ativa && "opacity-40")} />
      </button>
    </th>
  );
}

/**
 * Confirmação de exclusão. Se o servidor recusar (há vínculos), a explicação aparece DENTRO do diálogo,
 * que continua aberto para a pessoa ler e cancelar.
 */
export function ConfirmarExclusao({
  alvo,
  titulo,
  descricao,
  onConfirm,
  onClose,
  carregando,
  erro,
}: {
  alvo: unknown;
  titulo: string;
  descricao?: React.ReactNode;
  onConfirm: () => void;
  onClose: () => void;
  carregando?: boolean;
  erro?: string | null;
}) {
  return (
    <ConfirmDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={titulo}
      descricao={descricao}
      confirmar="Excluir"
      destrutivo
      carregando={carregando}
      onConfirm={onConfirm}
    >
      {erro && (
        <p role="alert" className="rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger-ink">
          {erro}
        </p>
      )}
    </ConfirmDialog>
  );
}

export function Carregando() {
  return (
    <div className="grid place-items-center p-10 text-muted-foreground">
      <Loader2 className="animate-spin" />
    </div>
  );
}

/** Contagem por extenso: "1 conta a pagar", "3 contas a pagar". */
export function plural(n: number, singular: string, plural_: string) {
  return `${n} ${n === 1 ? singular : plural_}`;
}

/** Data ISO (aaaa-mm-dd) para dd/mm/aaaa, sem passar por fuso. */
export function dataBr(iso: string | null | undefined) {
  if (!iso) return "";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export const DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

/** Aba da tela guardada na URL (`?aba=`), para o link/recarregar voltar à mesma aba. A página precisa estar dentro de <Suspense>. */
export function useAba<T extends string>(padrao: T, validas: readonly T[]): [T, (a: T) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const bruta = params.get("aba");
  const aba = (validas as readonly string[]).includes(bruta ?? "") ? (bruta as T) : padrao;
  return [
    aba,
    (a: T) => {
      const p = new URLSearchParams(params.toString());
      if (a === padrao) p.delete("aba");
      else p.set("aba", a);
      const qs = p.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
  ];
}
