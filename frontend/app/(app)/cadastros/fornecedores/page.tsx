"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmarExclusao, Guarda, plural, Th, useLista } from "@/components/cadastros-docs/comum";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Fornecedor } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

type Situacao = "todos" | "ativos" | "inativos";

const schema = z.object({
  nome: z.string().trim().min(2, "Informe o nome (mínimo de 2 letras).").max(120, "Máximo de 120 caracteres."),
});
type Dados = z.infer<typeof schema>;

function FornecedorDialog({ alvo, onClose }: { alvo: Fornecedor | "novo" | null; onClose: () => void }) {
  const qc = useQueryClient();
  const editando = alvo && alvo !== "novo" ? alvo : null;
  const form = useForm<Dados>({ resolver: zodResolver(schema), defaultValues: { nome: "" } });
  useEffect(() => {
    if (alvo) form.reset({ nome: editando?.nome ?? "" });
  }, [alvo, editando, form]);

  const salvar = useMutation({
    mutationFn: (d: Dados) => (editando ? api.put(`/cadastros/fornecedores/${editando.id}`, d) : api.post("/cadastros/fornecedores", d)),
    onSuccess: () => {
      toast.success(editando ? "Fornecedor atualizado" : "Fornecedor cadastrado");
      qc.invalidateQueries({ queryKey: ["fornecedores"] });
      onClose();
    },
  });

  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={editando ? "Editar fornecedor" : "Novo fornecedor"}
      descricao="Quem recebe os pagamentos do estúdio (contas a pagar)."
      rotuloSalvar={editando ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      onSubmit={form.handleSubmit((d) => salvar.mutate(d))}
    >
      <Field label="Nome" obrigatorio erro={form.formState.errors.nome?.message}>
        <Input {...form.register("nome")} autoFocus maxLength={120} autoComplete="off" />
      </Field>
    </FormDialog>
  );
}

function Conteudo() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_fornecedores.editar");
  const excluir = pode("cadastros_fornecedores.excluir");
  const lista = useLista<Fornecedor>("fornecedores", "/cadastros/fornecedores", { situacao: "todos" }, 15, "nome");
  const [dialogo, setDialogo] = useState<Fornecedor | "novo" | null>(null);
  const [apagar, setApagar] = useState<Fornecedor | null>(null);

  const alternar = useMutation({
    mutationFn: (f: Fornecedor) => api.patch(`/cadastros/fornecedores/${f.id}/ativo?ativo=${!f.ativo}`),
    onSuccess: (_r, f) => {
      toast.success(f.ativo ? "Fornecedor inativado" : "Fornecedor reativado");
      qc.invalidateQueries({ queryKey: ["fornecedores"] });
    },
  });

  const remover = useMutation({
    mutationFn: (f: Fornecedor) => api.del(`/cadastros/fornecedores/${f.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Fornecedor excluído");
      qc.invalidateQueries({ queryKey: ["fornecedores"] });
      setApagar(null);
    },
  });

  const situacao = (lista.filtros.situacao as Situacao) ?? "todos";
  const filtrando = !!lista.q || situacao !== "todos";
  const novo = editar && (
    <Button onClick={() => setDialogo("novo")}>
      <Plus /> Novo fornecedor
    </Button>
  );

  return (
    <div>
      <PageHeader
        titulo="Fornecedores"
        descricao="Cadastro de quem o estúdio paga. Usado nas contas a pagar."
        icone={Truck}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: "Fornecedores" }]}
        acoes={novo}
      />
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Buscar por nome" />
            <Segmented<Situacao>
              value={situacao}
              onChange={(v) => lista.setFiltro("situacao", v)}
              opcoes={[
                { value: "todos", label: "Todos", contagem: lista.contagens.todos },
                { value: "ativos", label: "Ativos", contagem: lista.contagens.ativos, tom: "success" },
                { value: "inativos", label: "Inativos", contagem: lista.contagens.inativos },
              ]}
            />
          </div>
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={5} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={Truck}
            titulo={filtrando ? "Nenhum fornecedor com esses filtros" : "Nenhum fornecedor cadastrado"}
            descricao={filtrando ? "Limpe a busca ou troque o filtro." : "Cadastre os fornecedores para lançar contas a pagar."}
            acao={
              filtrando ? (
                <Button variant="outline" onClick={lista.limpar}>
                  Limpar filtros
                </Button>
              ) : (
                novo
              )
            }
          />
        ) : (
          <>
            <div className={cn("overflow-x-auto", lista.isPlaceholderData && "opacity-60")}>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <Th coluna="codigo" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="w-24 pl-4">
                      Código
                    </Th>
                    <Th coluna="nome" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>
                      Nome
                    </Th>
                    <Th coluna="contas" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>
                      Contas a pagar
                    </Th>
                    <Th>Ativo</Th>
                    <Th className="w-28" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((f) => (
                    <tr key={f.id} className={cn("transition-colors hover:bg-accent/40", !f.ativo && "opacity-60")}>
                      <td className="py-3 pl-4 text-xs text-muted-foreground tabular-nums">{f.codigo ?? "—"}</td>
                      <td className="px-3 py-3 font-medium">{f.nome}</td>
                      <td className="px-3 py-3">
                        {f.contas_a_pagar ? <Pill tom="info">{plural(f.contas_a_pagar, "conta", "contas")}</Pill> : <span className="text-xs text-muted-foreground">—</span>}
                      </td>
                      <td className="px-3 py-3">
                        <Switch size="sm" checked={f.ativo} disabled={!editar || alternar.isPending} onCheckedChange={() => alternar.mutate(f)} aria-label={f.ativo ? "Inativar" : "Reativar"} />
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex justify-end gap-1">
                          {editar && (
                            <Button variant="ghost" size="icon-sm" onClick={() => setDialogo(f)} aria-label={`Editar ${f.nome}`}>
                              <Pencil />
                            </Button>
                          )}
                          {excluir && (
                            <Button variant="ghost" size="icon-sm" onClick={() => setApagar(f)} aria-label={`Excluir ${f.nome}`}>
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

      <FornecedorDialog alvo={dialogo} onClose={() => setDialogo(null)} />
      <ConfirmarExclusao
        alvo={apagar}
        titulo={`Excluir ${apagar?.nome ?? "fornecedor"}?`}
        descricao={
          apagar?.contas_a_pagar
            ? `Este fornecedor tem ${plural(apagar.contas_a_pagar, "conta a pagar", "contas a pagar")}; a exclusão será recusada. Inative-o para não usá-lo mais.`
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

export default function FornecedoresPage() {
  return (
    <Guarda permissao="cadastros_fornecedores.ver">
      <Conteudo />
    </Guarda>
  );
}
