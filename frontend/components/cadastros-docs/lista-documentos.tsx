"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data as dataCurta } from "@/lib/format";
import type { ModeloContratoLista, TermoLista } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

import { ConfirmarExclusao, Guarda, plural, Th, useLista } from "./comum";
import { DOCUMENTOS, type TipoDocumento } from "./documentos";

type Item = (TermoLista | ModeloContratoLista) & { ativo?: boolean };
type Situacao = "todos" | "ativos" | "inativos";

function Conteudo({ tipo }: { tipo: TipoDocumento }) {
  const cfg = DOCUMENTOS[tipo];
  const qc = useQueryClient();
  const router = useRouter();
  const { pode } = useAuth();
  const editar = pode(`${cfg.permissao}.editar`);
  const excluir = pode(`${cfg.permissao}.excluir`);
  const lista = useLista<Item>(cfg.chave, cfg.api, cfg.temAtivo ? { situacao: "todos" } : {}, 15, "nome");
  const [apagar, setApagar] = useState<Item | null>(null);

  const remover = useMutation({
    mutationFn: (i: Item) => api.del(`${cfg.api}/${i.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Documento excluído");
      qc.invalidateQueries({ queryKey: [cfg.chave] });
      setApagar(null);
    },
  });
  const duplicar = useMutation({
    mutationFn: (i: Item) => api.post<{ id: number; nome: string }>(`${cfg.api}/${i.id}/duplicar`),
    onSuccess: (c) => {
      toast.success("Cópia criada", { description: c.nome });
      qc.invalidateQueries({ queryKey: [cfg.chave] });
      router.push(`${cfg.rota}/${c.id}`);
    },
  });
  const alternar = useMutation({
    mutationFn: (i: Item) => api.patch(`${cfg.api}/${i.id}/ativo?ativo=${!i.ativo}`),
    onSuccess: (_r, i) => {
      toast.success(i.ativo ? "Inativado" : "Reativado");
      qc.invalidateQueries({ queryKey: [cfg.chave] });
    },
  });

  const situacao = (lista.filtros.situacao as Situacao) ?? "todos";
  const filtrando = !!lista.q || (cfg.temAtivo && situacao !== "todos");
  const vinculoDe = (i: Item) => (i as unknown as Record<string, number>)[cfg.vinculo.campo] ?? 0;
  const novo = editar && (
    <Button render={<Link href={`${cfg.rota}/novo`} />}>
      <Plus /> {cfg.tituloNovo}
    </Button>
  );

  return (
    <div>
      <PageHeader
        titulo={cfg.titulo}
        descricao={cfg.descricao}
        icone={cfg.icone}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: cfg.titulo }]}
        acoes={novo}
      />
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Buscar por nome" />
            {cfg.temAtivo && (
              <Segmented<Situacao>
                value={situacao}
                onChange={(v) => lista.setFiltro("situacao", v)}
                opcoes={[
                  { value: "todos", label: "Todos", contagem: lista.contagens.todos },
                  { value: "ativos", label: "Ativos", contagem: lista.contagens.ativos, tom: "success" },
                  { value: "inativos", label: "Inativos", contagem: lista.contagens.inativos },
                ]}
              />
            )}
          </div>
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={5} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={cfg.icone}
            titulo={filtrando ? "Nada encontrado com esses filtros" : `Nenhum ${cfg.singular} cadastrado`}
            descricao={filtrando ? "Limpe a busca ou troque o filtro." : "Crie o primeiro texto e use as variáveis para preencher os dados do aluno sozinho."}
            acao={filtrando ? <Button variant="outline" onClick={lista.limpar}>Limpar filtros</Button> : novo}
          />
        ) : (
          <>
            <div className={cn("overflow-x-auto", lista.isPlaceholderData && "opacity-60")}>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <Th coluna="codigo" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="w-20 pl-4">Código</Th>
                    <Th coluna="nome" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Nome</Th>
                    <Th className="hidden lg:table-cell">Início do texto</Th>
                    <Th coluna={tipo === "termo" ? "alunos" : "planos"} atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>{cfg.vinculo.rotulo}</Th>
                    <Th coluna="atualizado" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="hidden md:table-cell">Atualizado</Th>
                    {cfg.temAtivo && <Th>Ativo</Th>}
                    <Th className="w-32" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((i) => (
                    <tr
                      key={i.id}
                      className={cn("cursor-pointer transition-colors hover:bg-accent/40", cfg.temAtivo && i.ativo === false && "opacity-60")}
                      onClick={() => router.push(`${cfg.rota}/${i.id}`)}
                    >
                      <td className="py-3 pl-4 text-xs text-muted-foreground tabular-nums">{i.codigo ?? "—"}</td>
                      <td className="px-3 py-3 font-medium">{i.nome}</td>
                      <td className="hidden max-w-sm truncate px-3 py-3 text-muted-foreground lg:table-cell">{i.previa || "—"}</td>
                      <td className="px-3 py-3">
                        {vinculoDe(i) ? <Pill tom="info">{plural(vinculoDe(i), cfg.vinculo.singular.split(" ")[0], cfg.vinculo.plural.split(" ")[0])}</Pill> : <span className="text-xs text-muted-foreground">—</span>}
                      </td>
                      <td className="hidden px-3 py-3 text-muted-foreground md:table-cell">{dataCurta(i.atualizado_em)}</td>
                      {cfg.temAtivo && (
                        <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                          <Switch size="sm" checked={!!i.ativo} disabled={!editar || alternar.isPending} onCheckedChange={() => alternar.mutate(i)} aria-label={i.ativo ? "Inativar" : "Ativar"} />
                        </td>
                      )}
                      <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="icon-sm" render={<Link href={`${cfg.rota}/${i.id}`} />} aria-label={`${editar ? "Editar" : "Abrir"} ${i.nome}`}>
                            <Pencil />
                          </Button>
                          {editar && (
                            <Button variant="ghost" size="icon-sm" onClick={() => duplicar.mutate(i)} disabled={duplicar.isPending} aria-label={`Duplicar ${i.nome}`}>
                              <Copy />
                            </Button>
                          )}
                          {excluir && (
                            <Button variant="ghost" size="icon-sm" onClick={() => setApagar(i)} aria-label={`Excluir ${i.nome}`}>
                              <Trash2 />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />
          </>
        )}
      </TableCard>
      <ConfirmarExclusao
        alvo={apagar}
        titulo={`Excluir ${apagar?.nome ?? cfg.singular}?`}
        descricao={
          apagar && vinculoDe(apagar) > 0
            ? `Há ${vinculoDe(apagar)} ${vinculoDe(apagar) === 1 ? cfg.vinculo.singular : cfg.vinculo.plural}; a exclusão será recusada.`
            : "Esta ação não pode ser desfeita."
        }
        carregando={remover.isPending}
        erro={remover.error instanceof ApiError ? remover.error.message : null}
        onConfirm={() => apagar && remover.mutate(apagar)}
        onClose={() => {
          setApagar(null);
          remover.reset();
        }}
      />
    </div>
  );
}

export function ListaDocumentos({ tipo }: { tipo: TipoDocumento }) {
  return (
    <Guarda permissao={`${DOCUMENTOS[tipo].permissao}.ver`}>
      <Conteudo tipo={tipo} />
    </Guarda>
  );
}
