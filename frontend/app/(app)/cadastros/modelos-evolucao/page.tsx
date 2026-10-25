"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NotebookPen, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmarExclusao, Guarda, Th, useLista } from "@/components/cadastros-docs/comum";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data as dataCurta } from "@/lib/format";
import type { ModeloEvolucao } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

type Situacao = "todos" | "ativos" | "inativos";

const schema = z.object({
  titulo: z.string().trim().min(2, "Informe o título (mínimo de 2 letras).").max(120, "Máximo de 120 caracteres."),
  texto: z.string().trim().min(1, "Escreva o texto-base.").max(20000, "Texto longo demais."),
  ativo: z.boolean(),
});
type Dados = z.infer<typeof schema>;

function ModeloDialog({ alvo, onClose }: { alvo: ModeloEvolucao | "novo" | null; onClose: () => void }) {
  const qc = useQueryClient();
  const editando = alvo && alvo !== "novo" ? alvo : null;
  const form = useForm<Dados>({ resolver: zodResolver(schema), defaultValues: { titulo: "", texto: "", ativo: true } });
  useEffect(() => {
    if (alvo) form.reset({ titulo: editando?.titulo ?? "", texto: editando?.texto ?? "", ativo: editando?.ativo ?? true });
  }, [alvo, editando, form]);
  const salvar = useMutation({
    mutationFn: (d: Dados) => (editando ? api.put(`/cadastros/modelos/evolucao/${editando.id}`, d) : api.post("/cadastros/modelos/evolucao", d)),
    onSuccess: () => {
      toast.success(editando ? "Modelo atualizado" : "Modelo cadastrado");
      qc.invalidateQueries({ queryKey: ["modelos-evolucao"] });
      onClose();
    },
  });
  const e = form.formState.errors;
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={editando ? "Editar modelo de evolução" : "Novo modelo de evolução"}
      descricao="Texto-base que o professor insere na gaveta de evolução da aula e depois ajusta."
      rotuloSalvar={editando ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      largura="lg"
      onSubmit={form.handleSubmit((d) => salvar.mutate(d))}
    >
      <div className="space-y-4">
        <Field label="Título" obrigatorio erro={e.titulo?.message} dica="É o nome que o professor vê na lista de modelos.">
          <Input {...form.register("titulo")} autoFocus maxLength={120} autoComplete="off" />
        </Field>
        <Field label="Texto-base" obrigatorio erro={e.texto?.message} dica="Texto simples, sem formatação.">
          <Textarea {...form.register("texto")} rows={8} />
        </Field>
        <Controller
          control={form.control}
          name="ativo"
          render={({ field }) => (
            <SwitchRow titulo="Ativo" descricao="Só os ativos aparecem para o professor na gaveta de evolução.">
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </SwitchRow>
          )}
        />
      </div>
    </FormDialog>
  );
}

function Conteudo() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_modelos.editar");
  const excluir = pode("cadastros_modelos.excluir");
  const lista = useLista<ModeloEvolucao>("modelos-evolucao", "/cadastros/modelos/evolucao", { situacao: "todos" }, 15, "titulo");
  const [dialogo, setDialogo] = useState<ModeloEvolucao | "novo" | null>(null);
  const [apagar, setApagar] = useState<ModeloEvolucao | null>(null);

  const remover = useMutation({
    mutationFn: (m: ModeloEvolucao) => api.del(`/cadastros/modelos/evolucao/${m.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Modelo excluído");
      qc.invalidateQueries({ queryKey: ["modelos-evolucao"] });
      setApagar(null);
    },
  });
  const alternar = useMutation({
    mutationFn: (m: ModeloEvolucao) => api.patch(`/cadastros/modelos/evolucao/${m.id}/ativo?ativo=${!m.ativo}`),
    onSuccess: (_r, m) => {
      toast.success(m.ativo ? "Modelo inativado" : "Modelo ativado");
      qc.invalidateQueries({ queryKey: ["modelos-evolucao"] });
    },
  });

  const situacao = (lista.filtros.situacao as Situacao) ?? "todos";
  const filtrando = !!lista.q || situacao !== "todos";
  const novo = editar && (
    <Button onClick={() => setDialogo("novo")}>
      <Plus /> Novo modelo
    </Button>
  );

  return (
    <div>
      <PageHeader
        titulo="Modelos de evolução"
        descricao="Textos-base usados pelos professores na gaveta de evolução da agenda."
        icone={NotebookPen}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: "Modelos", href: "/cadastros/modelos" }, { label: "Evolução" }]}
        acoes={novo}
      />
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Buscar por título ou texto" />
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
          <TableSkeleton colunas={4} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={NotebookPen}
            titulo={filtrando ? "Nenhum modelo com esses filtros" : "Nenhum modelo de evolução"}
            descricao={filtrando ? "Limpe a busca ou troque o filtro." : "Crie textos-base para agilizar o registro da evolução nas aulas."}
            acao={filtrando ? <Button variant="outline" onClick={lista.limpar}>Limpar filtros</Button> : novo}
          />
        ) : (
          <>
            <div className={cn("overflow-x-auto", lista.isPlaceholderData && "opacity-60")}>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <Th coluna="codigo" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="w-20 pl-4">Código</Th>
                    <Th coluna="titulo" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Título</Th>
                    <Th className="hidden md:table-cell">Texto-base</Th>
                    <Th coluna="atualizado" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="hidden lg:table-cell">Atualizado</Th>
                    <Th>Ativo</Th>
                    <Th className="w-24" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((m) => (
                    <tr key={m.id} className={cn("transition-colors hover:bg-accent/40", !m.ativo && "opacity-60")}>
                      <td className="py-3 pl-4 text-xs text-muted-foreground tabular-nums">{m.codigo ?? "—"}</td>
                      <td className="px-3 py-3 font-medium">{m.titulo}</td>
                      <td className="hidden max-w-md truncate px-3 py-3 text-muted-foreground md:table-cell">{m.texto}</td>
                      <td className="hidden px-3 py-3 text-muted-foreground lg:table-cell">{dataCurta(m.atualizado_em)}</td>
                      <td className="px-3 py-3">
                        <Switch size="sm" checked={m.ativo} disabled={!editar || alternar.isPending} onCheckedChange={() => alternar.mutate(m)} aria-label={m.ativo ? "Inativar" : "Ativar"} />
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex justify-end gap-1">
                          {editar && <Button variant="ghost" size="icon-sm" onClick={() => setDialogo(m)} aria-label={`Editar ${m.titulo}`}><Pencil /></Button>}
                          {excluir && <Button variant="ghost" size="icon-sm" onClick={() => setApagar(m)} aria-label={`Excluir ${m.titulo}`}><Trash2 /></Button>}
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
      <ModeloDialog alvo={dialogo} onClose={() => setDialogo(null)} />
      <ConfirmarExclusao
        alvo={apagar}
        titulo={`Excluir ${apagar?.titulo ?? "modelo"}?`}
        descricao="As evoluções já registradas não mudam. Para só esconder dos professores, inative."
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

export default function ModelosEvolucaoPage() {
  return (
    <Guarda permissao="cadastros_modelos.ver">
      <Conteudo />
    </Guarda>
  );
}
