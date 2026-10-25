"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, Ban, CheckCircle2, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { PageHeader } from "@/components/mayacorp/page-header";
import { StatusBadge } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { usePaginado } from "@/hooks/use-paginado";
import { api } from "@/lib/api";
import type { Mensagem } from "@/lib/types";
import type { PaginaCad, Situacao, VinculosOut } from "@/lib/tipos-cadastros";
import { cn } from "@/lib/utils";

export interface Coluna<T> {
  titulo: string;
  render: (item: T) => React.ReactNode;
  /** Campo aceito pela API em `ordenar`; sem ele a coluna não é clicável. */
  ordenar?: string;
  /** Esconde a coluna em telas menores. */
  ate?: "md" | "lg";
  className?: string;
}

type Lista<T> = ReturnType<typeof usePaginado<T>>;

interface Props<T extends { id: number }> {
  /** Chave do cache do TanStack Query (também invalidada após salvar). */
  chave: string;
  path: string;
  titulo: string;
  descricao: string;
  icone: React.ComponentType<{ className?: string }>;
  colunas: Coluna<T>[];
  nomeDe: (item: T) => string;
  rotuloNovo: string;
  /** Substantivo para as mensagens: "unidade", "plano"... */
  substantivo: string;
  generoFeminino?: boolean;
  podeEditar: boolean;
  podeExcluir: boolean;
  onNovo: () => void;
  onEditar: (item: T) => void;
  /** Cadastros com ativo/inativo mostram os chips Ativos/Inativos/Todos e a ação de desativar. */
  comSituacao?: boolean;
  ordenarPadrao?: string;
  buscaPlaceholder?: string;
  filtrosIniciais?: Record<string, string | number | boolean | null | undefined>;
  /** Filtros extras ao lado da busca (usam o estado da lista). */
  filtros?: (lista: Lista<T>) => React.ReactNode;
  /** Itens extras no menu de ações da linha. */
  acoesExtras?: (item: T) => React.ReactNode;
  /** Caminho de ativar/desativar (padrão: `${path}/${id}/ativar|desativar`). */
  ativoDe?: (item: T) => boolean;
  /** Chamado quando o item é ativado/desativado/excluído (ex.: invalidar outras listas). */
  aoMudar?: () => void;
  vazio?: { titulo: string; descricao: string };
}

export function ListaCadastro<T extends { id: number }>(p: Props<T>) {
  const qc = useQueryClient();
  const comSituacao = p.comSituacao ?? true;
  const lista = usePaginado<T>(p.chave, p.path, {
    ...(comSituacao ? { situacao: "ativos" as Situacao } : {}),
    ordenar: p.ordenarPadrao ?? "nome",
    direcao: "asc",
    ...p.filtrosIniciais,
  });
  const dados = lista.data as PaginaCad<T> | undefined;
  const [excluir, setExcluir] = useState<T | null>(null);

  const ordenar = String(lista.filtros.ordenar ?? "");
  const direcao = String(lista.filtros.direcao ?? "asc");
  const alternarOrdem = (campo: string) => {
    if (ordenar === campo) lista.setFiltro("direcao", direcao === "asc" ? "desc" : "asc");
    else {
      lista.setFiltro("ordenar", campo);
      lista.setFiltro("direcao", "asc");
    }
  };

  const recarregar = () => {
    qc.invalidateQueries({ queryKey: [p.chave] });
    p.aoMudar?.();
  };
  const artigo = p.generoFeminino ? "a" : "o";

  const alternarAtivo = useMutation({
    mutationFn: ({ item, ativar }: { item: T; ativar: boolean }) => api.post(`${p.path}/${item.id}/${ativar ? "ativar" : "desativar"}`),
    onSuccess: (_r, { item, ativar }) => {
      toast.success(`${p.nomeDe(item)} ${ativar ? (p.generoFeminino ? "reativada" : "reativado") : p.generoFeminino ? "desativada" : "desativado"}`);
      setExcluir(null);
      recarregar();
    },
  });

  const vinculos = useQuery({
    queryKey: [p.chave, "vinculos", excluir?.id],
    queryFn: () => api.get<VinculosOut>(`${p.path}/${excluir!.id}/vinculos`),
    enabled: !!excluir,
    staleTime: 0,
  });
  const remover = useMutation({
    mutationFn: (item: T) => api.del<Mensagem>(`${p.path}/${item.id}`),
    onSuccess: (r) => {
      toast.success(r.mensagem);
      setExcluir(null);
      recarregar();
    },
    onError: () => {
      // 409 por vínculo criado entre a consulta e o clique: reabre a explicação atualizada
      qc.invalidateQueries({ queryKey: [p.chave, "vinculos"] });
    },
  });

  const filtrando = !!(lista.q || lista.filtros.tipo || lista.filtros.acesso || lista.filtros.tipo_servico_id);
  const semCadastroNenhum = !filtrando && (!comSituacao ? lista.total === 0 : (dados?.contagens?.todos ?? 0) === 0);
  const situacao = String(lista.filtros.situacao ?? "todos") as Situacao;
  const contagens = dados?.contagens;
  const colunas = p.colunas;
  const classeAte = (ate?: "md" | "lg") => (ate === "md" ? "hidden md:table-cell" : ate === "lg" ? "hidden lg:table-cell" : "");

  const bloqueado = !!excluir && !!vinculos.data && !vinculos.data.pode_excluir;
  const ativoDe = p.ativoDe ?? ((item: T) => (item as unknown as { ativo?: boolean }).ativo !== false);

  return (
    <div>
      <PageHeader
        titulo={p.titulo}
        descricao={p.descricao}
        icone={p.icone}
        acoes={
          p.podeEditar && (
            <Button onClick={p.onNovo}>
              <Plus /> {p.rotuloNovo}
            </Button>
          )
        }
      />
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder={p.buscaPlaceholder ?? "Buscar pelo nome…"} />
            {comSituacao && (
              <Segmented<Situacao>
                value={situacao}
                onChange={(v) => lista.setFiltro("situacao", v)}
                opcoes={[
                  { value: "ativos", label: "Ativos", contagem: contagens?.ativos },
                  { value: "inativos", label: "Inativos", contagem: contagens?.inativos },
                  { value: "todos", label: "Todos", contagem: contagens?.todos },
                ]}
              />
            )}
            {p.filtros?.(lista)}
          </div>
        </Toolbar>

        {lista.isPending ? (
          <TableSkeleton colunas={colunas.length} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={p.icone}
            titulo={!semCadastroNenhum ? `Nenhum registro com esses filtros` : (p.vazio?.titulo ?? `Nenhum${p.generoFeminino ? "a" : ""} ${p.substantivo} cadastrad${artigo}`)}
            descricao={
              !semCadastroNenhum
                ? "Limpe a busca ou troque a situação para ver mais resultados."
                : (p.vazio?.descricao ?? `Cadastre ${p.generoFeminino ? "a primeira" : "o primeiro"} ${p.substantivo} para começar.`)
            }
            acao={
              !semCadastroNenhum ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    lista.setQ("");
                    lista.setFiltro("tipo", undefined);
                    lista.setFiltro("acesso", undefined);
                    lista.setFiltro("tipo_servico_id", undefined);
                    if (comSituacao) lista.setFiltro("situacao", "todos");
                  }}
                >
                  Limpar filtros
                </Button>
              ) : (
                p.podeEditar && (
                  <Button onClick={p.onNovo}>
                    <Plus /> {p.rotuloNovo}
                  </Button>
                )
              )
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  {colunas.map((c) => (
                    <th key={c.titulo} className={cn("px-4 py-2.5 font-medium", classeAte(c.ate), c.className)}>
                      {c.ordenar ? (
                        <button type="button" onClick={() => alternarOrdem(c.ordenar!)} className="inline-flex items-center gap-1 hover:text-foreground" aria-label={`Ordenar por ${c.titulo}`}>
                          {c.titulo}
                          {ordenar === c.ordenar ? direcao === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" /> : <ArrowUpDown className="size-3 opacity-40" />}
                        </button>
                      ) : (
                        c.titulo
                      )}
                    </th>
                  ))}
                  <th className="w-12 px-3 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {lista.itens.map((item) => (
                  <tr
                    key={item.id}
                    tabIndex={0}
                    onClick={() => p.onEditar(item)}
                    onKeyDown={(e) => e.key === "Enter" && p.onEditar(item)}
                    className={cn("cursor-pointer transition-colors hover:bg-accent/40 focus-visible:bg-accent/40 focus-visible:outline-none", comSituacao && !ativoDe(item) && "opacity-60")}
                  >
                    {colunas.map((c) => (
                      <td key={c.titulo} className={cn("px-4 py-3", classeAte(c.ate), c.className)}>
                        {c.render(item)}
                      </td>
                    ))}
                    <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Ações de ${p.nomeDe(item)}`} />}>
                          <MoreHorizontal />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56">
                          <DropdownMenuItem onClick={() => p.onEditar(item)}>
                            <Pencil /> {p.podeEditar ? "Editar" : "Ver detalhes"}
                          </DropdownMenuItem>
                          {p.podeEditar && p.acoesExtras?.(item)}
                          {p.podeEditar && comSituacao && (
                            <DropdownMenuItem onClick={() => alternarAtivo.mutate({ item, ativar: !ativoDe(item) })}>
                              {ativoDe(item) ? (
                                <>
                                  <Ban /> Desativar
                                </>
                              ) : (
                                <>
                                  <CheckCircle2 /> Reativar
                                </>
                              )}
                            </DropdownMenuItem>
                          )}
                          {p.podeExcluir && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem variant="destructive" onClick={() => setExcluir(item)}>
                                <Trash2 /> Excluir
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {lista.total > 0 && <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />}
      </TableCard>

      <ConfirmDialog
        open={!!excluir}
        onOpenChange={(o) => !o && setExcluir(null)}
        titulo={bloqueado ? `Não é possível excluir ${artigo} ${p.substantivo}` : `Excluir ${excluir ? p.nomeDe(excluir) : p.substantivo}?`}
        descricao={
          vinculos.isPending ? (
            "Verificando se está em uso…"
          ) : bloqueado ? (
            <>
              {excluir && p.nomeDe(excluir)} está em uso por{" "}
              <strong className="font-medium text-foreground">{vinculos.data!.itens.map((v) => `${v.quantidade} ${v.rotulo}`).join(", ")}</strong>.{" "}
              {comSituacao && vinculos.data!.pode_desativar
                ? `Desative-${p.generoFeminino ? "a" : "o"}: ${p.generoFeminino ? "ela" : "ele"} deixa de aparecer para novos cadastros, mas o histórico fica preservado.`
                : "Remova ou troque esses vínculos antes de excluir."}
            </>
          ) : (
            <>
              {vinculos.data && vinculos.data.total_junto > 0 && (
                <>
                  Serão removidos junto:{" "}
                  <strong className="font-medium text-foreground">{vinculos.data.junto.map((v) => `${v.quantidade} ${v.rotulo}`).join(", ")}</strong>.{" "}
                </>
              )}
              Esta ação não pode ser desfeita.
            </>
          )
        }
        confirmar={bloqueado ? (comSituacao && vinculos.data?.pode_desativar && excluir && ativoDe(excluir) ? "Desativar" : "Entendi") : "Excluir"}
        destrutivo={!bloqueado}
        carregando={remover.isPending || alternarAtivo.isPending}
        desabilitado={vinculos.isPending}
        onConfirm={() => {
          if (!excluir) return;
          if (!bloqueado) remover.mutate(excluir);
          else if (comSituacao && vinculos.data?.pode_desativar && ativoDe(excluir)) alternarAtivo.mutate({ item: excluir, ativar: false });
          else setExcluir(null);
        }}
      />
    </div>
  );
}

/** Selo padrão de situação (Ativo/Inativo) para as listas. */
export function SeloAtivo({ ativo }: { ativo: boolean }) {
  return ativo ? <StatusBadge status="ativo" label="Ativo" /> : <StatusBadge status="descartado" label="Inativo" />;
}
