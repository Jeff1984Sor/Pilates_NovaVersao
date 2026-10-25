"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderTree, Pencil, Plus, Trash2 } from "lucide-react";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmarExclusao, Guarda, plural, Th, useAba, useLista } from "@/components/cadastros-docs/comum";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Categoria, PaginaContagens, Subcategoria, TipoCategoria } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

type FiltroTipo = "todos" | TipoCategoria;
type Situacao = "todos" | "ativos" | "inativos";
const ABAS = ["categorias", "subcategorias"] as const;

const tomTipo = (t: TipoCategoria) => (t === "RECEITA" ? "success" : "warning");
const rotuloTipo = (t: TipoCategoria) => (t === "RECEITA" ? "Receita" : "Despesa");

function usos(c: { contas_a_pagar: number; planos: number; subcategorias?: number }) {
  const p: string[] = [];
  if (c.subcategorias) p.push(plural(c.subcategorias, "subcategoria", "subcategorias"));
  if (c.contas_a_pagar) p.push(plural(c.contas_a_pagar, "conta a pagar", "contas a pagar"));
  if (c.planos) p.push(plural(c.planos, "plano", "planos"));
  return p;
}

// ------------------------------------------------------------------------------------------------ categorias
const schemaCategoria = z.object({
  nome: z.string().trim().min(2, "Informe o nome (mínimo de 2 letras).").max(120, "Máximo de 120 caracteres."),
  tipo: z.enum(["RECEITA", "DESPESA"]),
});
type DadosCategoria = z.infer<typeof schemaCategoria>;

function CategoriaDialog({ alvo, onClose }: { alvo: Categoria | "novo" | null; onClose: () => void }) {
  const qc = useQueryClient();
  const editando = alvo && alvo !== "novo" ? alvo : null;
  const form = useForm<DadosCategoria>({ resolver: zodResolver(schemaCategoria), defaultValues: { nome: "", tipo: "DESPESA" } });
  useEffect(() => {
    if (alvo) form.reset({ nome: editando?.nome ?? "", tipo: editando?.tipo ?? "DESPESA" });
  }, [alvo, editando, form]);
  const salvar = useMutation({
    mutationFn: (d: DadosCategoria) => (editando ? api.put(`/cadastros/categorias/${editando.id}`, d) : api.post("/cadastros/categorias", d)),
    onSuccess: () => {
      toast.success(editando ? "Categoria atualizada" : "Categoria cadastrada");
      qc.invalidateQueries({ queryKey: ["categorias"] });
      qc.invalidateQueries({ queryKey: ["subcategorias"] });
      qc.invalidateQueries({ queryKey: ["categorias-opcoes"] });
      onClose();
    },
  });
  const emUso = !!editando && (editando.contas_a_pagar > 0 || editando.planos > 0);
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={editando ? "Editar categoria" : "Nova categoria"}
      descricao="Agrupa receitas e despesas do financeiro."
      rotuloSalvar={editando ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      onSubmit={form.handleSubmit((d) => salvar.mutate(d))}
    >
      <div className="grid gap-4 sm:grid-cols-[1fr_180px]">
        <Field label="Nome" obrigatorio erro={form.formState.errors.nome?.message}>
          <Input {...form.register("nome")} autoFocus maxLength={120} autoComplete="off" />
        </Field>
        <Field label="Tipo" obrigatorio dica={emUso ? "Em uso: o tipo não pode mudar." : undefined}>
          <NativeSelect {...form.register("tipo")} disabled={emUso}>
            <option value="DESPESA">Despesa</option>
            <option value="RECEITA">Receita</option>
          </NativeSelect>
        </Field>
      </div>
    </FormDialog>
  );
}

function AbaCategorias() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_categorias.editar");
  const excluir = pode("cadastros_categorias.excluir");
  const lista = useLista<Categoria>("categorias", "/cadastros/categorias", { tipo: "", situacao: "todos" }, 15, "nome");
  const [dialogo, setDialogo] = useState<Categoria | "novo" | null>(null);
  const [apagar, setApagar] = useState<Categoria | null>(null);
  const alternar = useMutation({
    mutationFn: (c: Categoria) => api.patch(`/cadastros/categorias/${c.id}/ativo?ativo=${!c.ativo}`),
    onSuccess: (_r, c) => {
      toast.success(c.ativo ? "Categoria inativada" : "Categoria reativada");
      qc.invalidateQueries({ queryKey: ["categorias"] });
      qc.invalidateQueries({ queryKey: ["subcategorias"] });
      qc.invalidateQueries({ queryKey: ["categorias-opcoes"] });
    },
  });
  const remover = useMutation({
    mutationFn: (c: Categoria) => api.del(`/cadastros/categorias/${c.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Categoria excluída");
      qc.invalidateQueries({ queryKey: ["categorias"] });
      qc.invalidateQueries({ queryKey: ["categorias-opcoes"] });
      setApagar(null);
    },
  });
  const tipo = ((lista.filtros.tipo as string) || "todos") as FiltroTipo;
  const filtrando = !!lista.q || tipo !== "todos" || lista.filtros.situacao !== "todos";
  const novo = editar && (
    <Button onClick={() => setDialogo("novo")}>
      <Plus /> Nova categoria
    </Button>
  );
  return (
    <>
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Buscar categoria" />
            <Segmented<FiltroTipo>
              value={tipo}
              onChange={(v) => lista.setFiltro("tipo", v === "todos" ? "" : v)}
              opcoes={[
                { value: "todos", label: "Todas", contagem: lista.contagens.todos },
                { value: "RECEITA", label: "Receita", contagem: lista.contagens.RECEITA, tom: "success" },
                { value: "DESPESA", label: "Despesa", contagem: lista.contagens.DESPESA, tom: "warning" },
              ]}
            />
            <Segmented<Situacao>
              value={(lista.filtros.situacao as Situacao) ?? "todos"}
              onChange={(v) => lista.setFiltro("situacao", v)}
              opcoes={[
                { value: "todos", label: "Todas", contagem: lista.contagens.todos },
                { value: "ativos", label: "Ativas", contagem: lista.contagens.ativos, tom: "success" },
                { value: "inativos", label: "Inativas", contagem: lista.contagens.inativos },
              ]}
            />
          </div>
          {novo}
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={5} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={FolderTree}
            titulo={filtrando ? "Nenhuma categoria com esses filtros" : "Nenhuma categoria cadastrada"}
            descricao={filtrando ? "Limpe a busca ou troque o filtro." : "Crie categorias de receita e despesa para organizar o financeiro."}
            acao={filtrando ? <Button variant="outline" onClick={lista.limpar}>Limpar filtros</Button> : novo}
          />
        ) : (
          <>
            <div className={cn("overflow-x-auto", lista.isPlaceholderData && "opacity-60")}>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <Th coluna="codigo" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="w-24 pl-4">Código</Th>
                    <Th coluna="nome" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Nome</Th>
                    <Th coluna="tipo" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Tipo</Th>
                    <Th className="hidden md:table-cell">Em uso</Th>
                    <Th>Ativo</Th>
                    <Th className="w-28" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((c) => (
                    <tr key={c.id} className={cn("transition-colors hover:bg-accent/40", !c.ativo && "opacity-60")}>
                      <td className="py-3 pl-4 text-xs text-muted-foreground tabular-nums">{c.codigo ?? "—"}</td>
                      <td className="px-3 py-3 font-medium">{c.nome}</td>
                      <td className="px-3 py-3"><Pill tom={tomTipo(c.tipo)}>{rotuloTipo(c.tipo)}</Pill></td>
                      <td className="hidden px-3 py-3 text-xs text-muted-foreground md:table-cell">{usos(c).join(" · ") || "—"}</td>
                      <td className="px-3 py-3">
                        <Switch size="sm" checked={c.ativo} disabled={!editar || alternar.isPending} onCheckedChange={() => alternar.mutate(c)} aria-label={c.ativo ? "Inativar" : "Reativar"} />
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex justify-end gap-1">
                          {editar && <Button variant="ghost" size="icon-sm" onClick={() => setDialogo(c)} aria-label={`Editar ${c.nome}`}><Pencil /></Button>}
                          {excluir && <Button variant="ghost" size="icon-sm" onClick={() => setApagar(c)} aria-label={`Excluir ${c.nome}`}><Trash2 /></Button>}
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
      <CategoriaDialog alvo={dialogo} onClose={() => setDialogo(null)} />
      <ConfirmarExclusao
        alvo={apagar}
        titulo={`Excluir a categoria ${apagar?.nome ?? ""}?`}
        descricao={apagar && usos(apagar).length ? `Ela tem ${usos(apagar).join(", ")}; a exclusão será recusada.` : "Esta ação não pode ser desfeita."}
        carregando={remover.isPending}
        erro={remover.error instanceof ApiError ? remover.error.message : null}
        onConfirm={() => apagar && remover.mutate(apagar)}
        onClose={() => {
          setApagar(null);
          remover.reset();
        }}
      />
    </>
  );
}

// ------------------------------------------------------------------------------------------------ subcategorias
const schemaSub = z.object({
  categoria_id: z.coerce.number({ message: "Escolha a categoria." }).int().positive("Escolha a categoria."),
  nome: z.string().trim().min(2, "Informe o nome (mínimo de 2 letras).").max(120, "Máximo de 120 caracteres."),
});
type DadosSub = z.input<typeof schemaSub>;

function SubcategoriaDialog({ alvo, onClose }: { alvo: Subcategoria | "novo" | null; onClose: () => void }) {
  const qc = useQueryClient();
  const editando = alvo && alvo !== "novo" ? alvo : null;
  const cats = useQuery({
    queryKey: ["categorias-opcoes"],
    queryFn: () => api.get<PaginaContagens<Categoria>>("/cadastros/categorias", { por_pagina: 200, ordenar: "nome", somente_ativos: true }),
    enabled: !!alvo,
  });
  const form = useForm<DadosSub>({ resolver: zodResolver(schemaSub), defaultValues: { categoria_id: "", nome: "" } });
  useEffect(() => {
    if (alvo) form.reset({ categoria_id: editando?.categoria_id ?? "", nome: editando?.nome ?? "" });
  }, [alvo, editando, form]);
  const salvar = useMutation({
    mutationFn: (d: DadosSub) => {
      const corpo = schemaSub.parse(d);
      return editando ? api.put(`/cadastros/categorias/subcategorias/${editando.id}`, corpo) : api.post("/cadastros/categorias/subcategorias", corpo);
    },
    onSuccess: () => {
      toast.success(editando ? "Subcategoria atualizada" : "Subcategoria cadastrada");
      qc.invalidateQueries({ queryKey: ["subcategorias"] });
      qc.invalidateQueries({ queryKey: ["categorias"] });
      onClose();
    },
  });
  const emUso = !!editando && (editando.contas_a_pagar > 0 || editando.planos > 0);
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={editando ? "Editar subcategoria" : "Nova subcategoria"}
      descricao="Detalha uma categoria (ex.: Despesas fixas > Aluguel)."
      rotuloSalvar={editando ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      onSubmit={form.handleSubmit((d) => salvar.mutate(d))}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Categoria" obrigatorio erro={form.formState.errors.categoria_id?.message} dica={emUso ? "Em uso: não dá para mudar de categoria." : undefined}>
          <NativeSelect {...form.register("categoria_id")} disabled={emUso}>
            <option value="">Escolha…</option>
            {(cats.data?.itens ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome} ({rotuloTipo(c.tipo).toLowerCase()})
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Nome" obrigatorio erro={form.formState.errors.nome?.message}>
          <Input {...form.register("nome")} maxLength={120} autoComplete="off" />
        </Field>
      </div>
    </FormDialog>
  );
}

function AbaSubcategorias() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_categorias.editar");
  const excluir = pode("cadastros_categorias.excluir");
  const lista = useLista<Subcategoria>("subcategorias", "/cadastros/categorias/subcategorias", { tipo: "", situacao: "todos" }, 15, "categoria");
  const [dialogo, setDialogo] = useState<Subcategoria | "novo" | null>(null);
  const [apagar, setApagar] = useState<Subcategoria | null>(null);
  const alternar = useMutation({
    mutationFn: (s: Subcategoria) => api.patch(`/cadastros/categorias/subcategorias/${s.id}/ativo?ativo=${!s.ativo}`),
    onSuccess: (_r, s) => {
      toast.success(s.ativo ? "Subcategoria inativada" : "Subcategoria reativada");
      qc.invalidateQueries({ queryKey: ["subcategorias"] });
    },
  });
  const remover = useMutation({
    mutationFn: (s: Subcategoria) => api.del(`/cadastros/categorias/subcategorias/${s.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Subcategoria excluída");
      qc.invalidateQueries({ queryKey: ["subcategorias"] });
      qc.invalidateQueries({ queryKey: ["categorias"] });
      setApagar(null);
    },
  });
  const tipo = ((lista.filtros.tipo as string) || "todos") as FiltroTipo;
  const filtrando = !!lista.q || tipo !== "todos" || lista.filtros.situacao !== "todos";
  const novo = editar && (
    <Button onClick={() => setDialogo("novo")}>
      <Plus /> Nova subcategoria
    </Button>
  );
  return (
    <>
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Buscar subcategoria ou categoria" />
            <Segmented<FiltroTipo>
              value={tipo}
              onChange={(v) => lista.setFiltro("tipo", v === "todos" ? "" : v)}
              opcoes={[
                { value: "todos", label: "Todas", contagem: lista.contagens.todos },
                { value: "RECEITA", label: "Receita", contagem: lista.contagens.RECEITA, tom: "success" },
                { value: "DESPESA", label: "Despesa", contagem: lista.contagens.DESPESA, tom: "warning" },
              ]}
            />
            <Segmented<Situacao>
              value={(lista.filtros.situacao as Situacao) ?? "todos"}
              onChange={(v) => lista.setFiltro("situacao", v)}
              opcoes={[
                { value: "todos", label: "Todas", contagem: lista.contagens.todos },
                { value: "ativos", label: "Ativas", contagem: lista.contagens.ativos, tom: "success" },
                { value: "inativos", label: "Inativas", contagem: lista.contagens.inativos },
              ]}
            />
          </div>
          {novo}
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={5} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={FolderTree}
            titulo={filtrando ? "Nenhuma subcategoria com esses filtros" : "Nenhuma subcategoria cadastrada"}
            descricao={filtrando ? "Limpe a busca ou troque o filtro." : "Crie subcategorias para detalhar suas categorias."}
            acao={filtrando ? <Button variant="outline" onClick={lista.limpar}>Limpar filtros</Button> : novo}
          />
        ) : (
          <>
            <div className={cn("overflow-x-auto", lista.isPlaceholderData && "opacity-60")}>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <Th coluna="codigo" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="w-24 pl-4">Código</Th>
                    <Th coluna="nome" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Subcategoria</Th>
                    <Th coluna="categoria" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Categoria</Th>
                    <Th className="hidden md:table-cell">Em uso</Th>
                    <Th>Ativo</Th>
                    <Th className="w-28" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((s) => (
                    <tr key={s.id} className={cn("transition-colors hover:bg-accent/40", !s.ativo && "opacity-60")}>
                      <td className="py-3 pl-4 text-xs text-muted-foreground tabular-nums">{s.codigo ?? "—"}</td>
                      <td className="px-3 py-3 font-medium">{s.nome}</td>
                      <td className="px-3 py-3">
                        <span className="mr-2">{s.categoria_nome}</span>
                        <Pill tom={tomTipo(s.categoria_tipo)}>{rotuloTipo(s.categoria_tipo)}</Pill>
                      </td>
                      <td className="hidden px-3 py-3 text-xs text-muted-foreground md:table-cell">{usos(s).join(" · ") || "—"}</td>
                      <td className="px-3 py-3">
                        <Switch size="sm" checked={s.ativo} disabled={!editar || alternar.isPending} onCheckedChange={() => alternar.mutate(s)} aria-label={s.ativo ? "Inativar" : "Reativar"} />
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex justify-end gap-1">
                          {editar && <Button variant="ghost" size="icon-sm" onClick={() => setDialogo(s)} aria-label={`Editar ${s.nome}`}><Pencil /></Button>}
                          {excluir && <Button variant="ghost" size="icon-sm" onClick={() => setApagar(s)} aria-label={`Excluir ${s.nome}`}><Trash2 /></Button>}
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
      <SubcategoriaDialog alvo={dialogo} onClose={() => setDialogo(null)} />
      <ConfirmarExclusao
        alvo={apagar}
        titulo={`Excluir a subcategoria ${apagar?.nome ?? ""}?`}
        descricao={apagar && usos(apagar).length ? `Ela está em uso por ${usos(apagar).join(" e ")}; a exclusão será recusada.` : "Esta ação não pode ser desfeita."}
        carregando={remover.isPending}
        erro={remover.error instanceof ApiError ? remover.error.message : null}
        onConfirm={() => apagar && remover.mutate(apagar)}
        onClose={() => {
          setApagar(null);
          remover.reset();
        }}
      />
    </>
  );
}

function Conteudo() {
  const [aba, setAba] = useAba<(typeof ABAS)[number]>("categorias", ABAS);
  return (
    <div>
      <PageHeader
        titulo="Categorias"
        descricao="Categorias e subcategorias de receita e despesa, usadas nos planos e nas contas a pagar."
        icone={FolderTree}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: "Categorias" }]}
        acoes={
          <Segmented
            value={aba}
            onChange={setAba}
            opcoes={[
              { value: "categorias", label: "Categorias" },
              { value: "subcategorias", label: "Subcategorias" },
            ]}
          />
        }
      />
      {aba === "categorias" ? <AbaCategorias /> : <AbaSubcategorias />}
    </div>
  );
}

export default function CategoriasPage() {
  return (
    <Guarda permissao="cadastros_categorias.ver">
      <Suspense>
        <Conteudo />
      </Suspense>
    </Guarda>
  );
}
