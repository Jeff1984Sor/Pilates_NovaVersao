"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Sparkles, UserPlus, UsersRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar, linhaClicavel } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ListaAlunos, Situacao } from "@/lib/tipos-alunos";
import { cn } from "@/lib/utils";

type Coluna = "nome" | "codigo" | "cadastro" | "status";

export default function AlunosPage() {
  const { pode } = useAuth();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [situacao, setSituacao] = useState<Situacao>("ativos");
  const [ordem, setOrdem] = useState("nome");
  const [pagina, setPagina] = useState(1);
  const [porPagina] = useState(25);
  const busca = useDebounce(q, 300);

  const lista = useQuery({
    queryKey: ["alunos", "lista", busca, situacao, ordem, pagina, porPagina],
    queryFn: () => api.get<ListaAlunos>("/alunos", { q: busca, situacao, ordem, pagina, por_pagina: porPagina }),
    placeholderData: keepPreviousData,
    enabled: pode("alunos.ver"),
  });

  if (!pode("alunos.ver")) return <SemAcesso titulo="Alunos" />;

  const d = lista.data;
  const c = d?.contagens;
  const filtrando = !!busca.trim();

  function ordenar(col: Coluna) {
    setPagina(1);
    setOrdem((o) => (o === col ? `-${col}` : col));
  }
  const seta = (col: Coluna) => (ordem === col ? <ArrowUp className="size-3" /> : ordem === `-${col}` ? <ArrowDown className="size-3" /> : null);
  const th = (col: Coluna, rotulo: string, className?: string) => (
    <th className={cn("px-3 py-2.5 font-medium", className)}>
      <button type="button" onClick={() => ordenar(col)} className="inline-flex items-center gap-1 hover:text-foreground">
        {rotulo}
        {seta(col)}
      </button>
    </th>
  );

  const novoBotao = pode("alunos.editar") && (
    <Button render={<Link href="/alunos/novo" />}>
      <UserPlus /> Novo aluno
    </Button>
  );

  return (
    <div>
      <PageHeader
        icone={UsersRound}
        titulo="Alunos"
        descricao="Cadastro, ficha e histórico de quem treina no estúdio."
        acoes={
          <>
            <Tooltip>
              <TooltipTrigger render={<span tabIndex={0} />}>
                <Button variant="outline" disabled>
                  <Sparkles /> Preencher com IA
                </Button>
              </TooltipTrigger>
              <TooltipContent>Em breve: ler documento e comprovante de endereço para preencher o cadastro.</TooltipContent>
            </Tooltip>
            {novoBotao}
          </>
        }
      />

      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput
              value={q}
              onChange={(v) => {
                setQ(v);
                setPagina(1);
              }}
              placeholder="Nome, CPF, RG, telefone ou código  ( / )"
            />
            <Segmented<Situacao>
              value={situacao}
              onChange={(v) => {
                setSituacao(v);
                setPagina(1);
              }}
              opcoes={[
                { value: "ativos", label: "Ativos", contagem: c?.ativos },
                { value: "inativos", label: "Inativos", contagem: c?.inativos },
                { value: "todos", label: "Todos", contagem: c?.todos },
              ]}
            />
          </div>
        </Toolbar>

        {lista.isPending ? (
          <TableSkeleton colunas={5} />
        ) : !d || d.itens.length === 0 ? (
          <EmptyState
            icone={UsersRound}
            titulo={filtrando ? "Nenhum aluno encontrado" : situacao === "inativos" ? "Nenhum aluno inativo" : "Nenhum aluno cadastrado"}
            descricao={
              filtrando
                ? "Confira a grafia ou busque pelo CPF, telefone ou código."
                : situacao === "inativos"
                  ? "Quando você inativar um aluno, ele aparece aqui."
                  : "Cadastre o primeiro aluno para começar."
            }
            acao={
              filtrando ? (
                <Button variant="outline" onClick={() => setQ("")}>
                  Limpar busca
                </Button>
              ) : situacao === "ativos" ? (
                novoBotao
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    {th("nome", "Aluno", "px-4")}
                    {th("codigo", "Código", "hidden md:table-cell")}
                    <th className="hidden px-3 py-2.5 font-medium lg:table-cell">CPF</th>
                    <th className="hidden px-3 py-2.5 font-medium md:table-cell">Telefone</th>
                    <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Aulas reservadas</th>
                    {th("status", "Status")}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {d.itens.map((a) => (
                    <tr
                      key={a.id}
                      tabIndex={0}
                      onClick={() => router.push(`/alunos/${a.id}`)}
                      onKeyDown={(e) => e.key === "Enter" && router.push(`/alunos/${a.id}`)}
                      className={cn(linhaClicavel, "focus-visible:bg-accent/40 focus-visible:outline-none", a.status === "INATIVO" && "opacity-60")}
                    >
                      <td className="px-4 py-3">
                        <Link href={`/alunos/${a.id}`} className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
                          <UserAvatar nome={a.nome} fotoUrl={a.foto_url} className="size-9" textoClassName="text-xs" inativo={a.status === "INATIVO"} />
                          <span className="min-w-0 truncate font-medium">{a.nome}</span>
                        </Link>
                      </td>
                      <td className="hidden px-3 py-3 text-muted-foreground tabular-nums md:table-cell">{a.codigo ?? "—"}</td>
                      <td className="hidden px-3 py-3 font-mono text-xs text-muted-foreground lg:table-cell">
                        {a.cpf_mascarado ?? (a.sem_cpf ? <Pill tom="warning">Sem CPF</Pill> : "—")}
                      </td>
                      <td className="hidden px-3 py-3 text-muted-foreground md:table-cell">{a.telefone ?? "—"}</td>
                      <td className="hidden px-3 py-3 tabular-nums sm:table-cell">{a.aulas_reservadas}</td>
                      <td className="px-3 py-3">
                        <Pill tom={a.status === "ATIVO" ? "success" : "neutral"}>{a.status === "ATIVO" ? "Ativo" : "Inativo"}</Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination pagina={d.pagina} porPagina={d.por_pagina} total={d.total} onChange={setPagina} />
          </>
        )}
      </TableCard>
    </div>
  );
}
