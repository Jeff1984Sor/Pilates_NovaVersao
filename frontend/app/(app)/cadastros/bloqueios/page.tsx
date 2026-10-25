"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, CalendarX, Pencil, Plus, Trash2, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmarExclusao, dataBr, Guarda, Th, useLista } from "@/components/cadastros-docs/comum";
import { DiasChips, useOpcoes } from "@/components/cadastros-docs/seletores";
import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { type Bloqueio, hhmm, type OpcoesAgenda, type SituacaoBloqueio } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

type Situacao = "todos" | "vigentes" | "expirados" | "inativos";

const hora = z.string().regex(/^\d{2}:\d{2}/, "Informe o horário.");
const opcional = z.preprocess((v) => (v === "" || v == null ? null : Number(v)), z.number().nullable());

const schema = z
  .object({
    unidade_id: z.coerce.number({ message: "Escolha a unidade." }).int().positive("Escolha a unidade."),
    tipo_servico_id: opcional,
    profissional_id: opcional,
    recorrente: z.boolean(),
    dias_semana: z.array(z.number()),
    data_inicio: z.string().min(10, "Informe a data inicial."),
    data_fim: z.string(),
    hora_inicio: hora,
    hora_fim: hora,
    motivo: z.string().trim().max(200, "Máximo de 200 caracteres."),
    ativo: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.hora_fim.slice(0, 5) <= v.hora_inicio.slice(0, 5))
      ctx.addIssue({ code: "custom", path: ["hora_fim"], message: "O horário final deve ser maior que o inicial." });
    if (v.data_fim && v.data_inicio && v.data_fim < v.data_inicio)
      ctx.addIssue({ code: "custom", path: ["data_fim"], message: "A data final não pode ser anterior à inicial." });
    if (v.recorrente && v.dias_semana.length === 0)
      ctx.addIssue({ code: "custom", path: ["dias_semana"], message: "Marque ao menos um dia da semana." });
    if (!v.recorrente && !v.data_fim)
      ctx.addIssue({
        code: "custom",
        path: ["data_fim"],
        message: "Informe a data final (para um único dia, repita a data inicial).",
      });
  });
type Dados = z.input<typeof schema>;

const VAZIO: Dados = {
  unidade_id: "",
  tipo_servico_id: "",
  profissional_id: "",
  recorrente: false,
  dias_semana: [],
  data_inicio: "",
  data_fim: "",
  hora_inicio: "08:00",
  hora_fim: "18:00",
  motivo: "",
  ativo: true,
};

function BloqueioDialog({ alvo, opcoes, onClose }: { alvo: Bloqueio | "novo" | null; opcoes?: OpcoesAgenda; onClose: () => void }) {
  const qc = useQueryClient();
  const editando = alvo && alvo !== "novo" ? alvo : null;
  const form = useForm<Dados>({ resolver: zodResolver(schema), defaultValues: VAZIO });
  useEffect(() => {
    if (!alvo) return;
    form.reset(
      editando
        ? {
            unidade_id: editando.unidade_id,
            tipo_servico_id: editando.tipo_servico_id ?? "",
            profissional_id: editando.profissional_id ?? "",
            recorrente: editando.recorrente,
            dias_semana: editando.dia_semana != null ? [editando.dia_semana] : [],
            data_inicio: editando.data_inicio,
            data_fim: editando.data_fim ?? "",
            hora_inicio: hhmm(editando.hora_inicio),
            hora_fim: hhmm(editando.hora_fim),
            motivo: editando.motivo ?? "",
            ativo: editando.ativo,
          }
        : { ...VAZIO, unidade_id: opcoes?.unidades.length === 1 ? opcoes.unidades[0].id : "" },
    );
  }, [alvo, editando, form, opcoes]);

  const salvar = useMutation({
    mutationFn: (d: Dados) => {
      const v = schema.parse(d);
      const corpo = { ...v, data_fim: v.data_fim || null, motivo: v.motivo || null, dias_semana: v.recorrente ? v.dias_semana : [] };
      return editando ? api.put(`/cadastros/bloqueios/${editando.id}`, corpo) : api.post("/cadastros/bloqueios", corpo);
    },
    onSuccess: () => {
      toast.success(editando ? "Bloqueio atualizado" : "Bloqueio cadastrado");
      qc.invalidateQueries({ queryKey: ["bloqueios"] });
      onClose();
    },
  });

  const e = form.formState.errors;
  const recorrente = useWatch({ control: form.control, name: "recorrente" });
  const dataFim = useWatch({ control: form.control, name: "data_fim" });
  const dataIni = useWatch({ control: form.control, name: "data_inicio" });
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={editando ? "Editar bloqueio" : "Novo bloqueio"}
      descricao="Impede aulas num período ou toda semana num dia, para a unidade, um serviço ou um profissional."
      rotuloSalvar={editando ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      largura="lg"
      onSubmit={form.handleSubmit((d) => salvar.mutate(d))}
    >
      <div className="space-y-4">
        {editando?.aviso && !editando.data_fim && !editando.recorrente && (
          <p className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning-ink">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            Este bloqueio está valendo para sempre porque foi criado sem data final. Informe até quando ele vale.
          </p>
        )}
        <Controller
          control={form.control}
          name="recorrente"
          render={({ field }) => (
            <Segmented<"pontual" | "recorrente">
              value={field.value ? "recorrente" : "pontual"}
              onChange={(v) => !editando && field.onChange(v === "recorrente")}
              opcoes={[
                { value: "pontual", label: "Pontual (período)" },
                { value: "recorrente", label: "Toda semana" },
              ]}
            />
          )}
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Unidade" obrigatorio erro={e.unidade_id?.message}>
            <NativeSelect {...form.register("unidade_id")}>
              <option value="">Escolha…</option>
              {opcoes?.unidades.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Serviço">
            <NativeSelect {...form.register("tipo_servico_id")}>
              <option value="">Todos os serviços</option>
              {opcoes?.servicos.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Profissional">
            <NativeSelect {...form.register("profissional_id")}>
              <option value="">Todos os profissionais</option>
              {opcoes?.profissionais.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </NativeSelect>
          </Field>
        </div>
        {recorrente && (
          <Field label="Dias da semana" obrigatorio erro={e.dias_semana?.message} dica={editando ? "Ao editar, escolha um único dia. Para outros dias, crie um novo bloqueio." : "Um bloqueio é criado para cada dia marcado."}>
            <Controller control={form.control} name="dias_semana" render={({ field }) => <DiasChips unico={!!editando} valor={field.value} onChange={field.onChange} />} />
          </Field>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={recorrente ? "A partir de" : "Data inicial"} obrigatorio erro={e.data_inicio?.message}>
            <Input type="date" {...form.register("data_inicio")} />
          </Field>
          <Field
            label={recorrente ? "Até (opcional)" : "Data final"}
            obrigatorio={!recorrente}
            erro={e.data_fim?.message}
            dica={!recorrente ? "Para bloquear um único dia, use a mesma data nos dois campos." : undefined}
          >
            <Input type="date" {...form.register("data_fim")} />
          </Field>
          <Field label="Hora inicial" obrigatorio erro={e.hora_inicio?.message}>
            <Input type="time" {...form.register("hora_inicio")} />
          </Field>
          <Field label="Hora final" obrigatorio erro={e.hora_fim?.message}>
            <Input type="time" {...form.register("hora_fim")} />
          </Field>
        </div>
        {recorrente && !dataFim && (
          <p className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning-ink">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            Sem data final, este bloqueio vale para sempre, toda semana, até alguém inativá-lo.
          </p>
        )}
        {dataIni && dataFim && !recorrente && (
          <p className="text-xs text-muted-foreground">
            Vale de {dataBr(dataIni)} até {dataBr(dataFim)}.
          </p>
        )}
        <Field label="Motivo" erro={e.motivo?.message}>
          <Input {...form.register("motivo")} maxLength={200} placeholder="Ex.: Recesso de fim de ano" autoComplete="off" />
        </Field>
        <Controller
          control={form.control}
          name="ativo"
          render={({ field }) => (
            <SwitchRow titulo="Ativo" descricao="Desligado = o bloqueio fica guardado, mas a agenda o ignora.">
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </SwitchRow>
          )}
        />
      </div>
    </FormDialog>
  );
}

const TOM: Record<SituacaoBloqueio, { rotulo: string; tom: "success" | "info" | "neutral" | "warning" }> = {
  vigente: { rotulo: "Vigente", tom: "success" },
  agendado: { rotulo: "Começa depois", tom: "info" },
  expirado: { rotulo: "Expirado", tom: "neutral" },
  inativo: { rotulo: "Inativo", tom: "warning" },
};

function Conteudo() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_bloqueios.editar");
  const excluir = pode("cadastros_bloqueios.excluir");
  const opcoes = useOpcoes(true, "/cadastros/bloqueios/opcoes");
  const lista = useLista<Bloqueio>("bloqueios", "/cadastros/bloqueios", { situacao: "todos", unidade_id: "", tipo_servico_id: "", profissional_id: "" }, 15);
  const [dialogo, setDialogo] = useState<Bloqueio | "novo" | null>(null);
  const [apagar, setApagar] = useState<Bloqueio | null>(null);

  const remover = useMutation({
    mutationFn: (b: Bloqueio) => api.del(`/cadastros/bloqueios/${b.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Bloqueio excluído");
      qc.invalidateQueries({ queryKey: ["bloqueios"] });
      setApagar(null);
    },
  });
  const alternar = useMutation({
    mutationFn: (b: Bloqueio) => api.patch(`/cadastros/bloqueios/${b.id}/ativo?ativo=${!b.ativo}`),
    onSuccess: (_r, b) => {
      toast.success(b.ativo ? "Bloqueio inativado" : "Bloqueio ativado");
      qc.invalidateQueries({ queryKey: ["bloqueios"] });
    },
  });

  const situacao = (lista.filtros.situacao as Situacao) ?? "todos";
  const filtrando = !!lista.q || situacao !== "todos" || !!lista.filtros.unidade_id || !!lista.filtros.tipo_servico_id || !!lista.filtros.profissional_id;
  const novo = editar && (
    <Button onClick={() => setDialogo("novo")}>
      <Plus /> Novo bloqueio
    </Button>
  );

  return (
    <div>
      <PageHeader
        titulo="Bloqueios de agenda"
        descricao="Períodos e horários em que não há aula: feriados, recessos, reuniões, ausências."
        icone={Ban}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: "Bloqueios" }]}
        acoes={novo}
      />
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Motivo, unidade, serviço…" className="sm:w-64" />
            <NativeSelect className="sm:w-44" value={String(lista.filtros.tipo_servico_id ?? "")} onChange={(e) => lista.setFiltro("tipo_servico_id", e.target.value)} aria-label="Serviço">
              <option value="">Todos os serviços</option>
              {opcoes.data?.servicos.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect className="sm:w-48" value={String(lista.filtros.profissional_id ?? "")} onChange={(e) => lista.setFiltro("profissional_id", e.target.value)} aria-label="Profissional">
              <option value="">Todos os profissionais</option>
              {opcoes.data?.profissionais.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </NativeSelect>
            <Segmented<Situacao>
              value={situacao}
              onChange={(v) => lista.setFiltro("situacao", v)}
              opcoes={[
                { value: "todos", label: "Todos", contagem: lista.contagens.todos },
                { value: "vigentes", label: "Vigentes", contagem: lista.contagens.vigentes, tom: "success" },
                { value: "expirados", label: "Expirados", contagem: lista.contagens.expirados },
                { value: "inativos", label: "Inativos", contagem: lista.contagens.inativos, tom: "warning" },
              ]}
            />
          </div>
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={CalendarX}
            titulo={filtrando ? "Nenhum bloqueio com esses filtros" : "Nenhum bloqueio cadastrado"}
            descricao={filtrando ? "Limpe a busca ou troque os filtros." : "Cadastre feriados, recessos e horários em que a agenda deve ficar fechada."}
            acao={filtrando ? <Button variant="outline" onClick={lista.limpar}>Limpar filtros</Button> : novo}
          />
        ) : (
          <>
            <div className={cn("overflow-x-auto", lista.isPlaceholderData && "opacity-60")}>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <Th coluna="data" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="pl-4">Quando</Th>
                    <Th coluna="inicio" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Horário</Th>
                    <Th>Escopo</Th>
                    <Th className="hidden md:table-cell">Motivo</Th>
                    <Th>Vale até</Th>
                    <Th>Ativo</Th>
                    <Th className="w-24" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((b) => {
                    const s = TOM[b.situacao];
                    return (
                      <tr key={b.id} className={cn("align-top transition-colors hover:bg-accent/40", !b.ativo && "opacity-60")}>
                        <td className="py-3 pl-4">
                          {b.recorrente ? (
                            <>
                              <p className="font-medium">Toda {b.dia_nome?.toLowerCase()}</p>
                              <p className="text-xs text-muted-foreground">desde {dataBr(b.data_inicio)}</p>
                            </>
                          ) : (
                            <p className="font-medium">
                              {dataBr(b.data_inicio)}
                              {b.data_fim && b.data_fim !== b.data_inicio ? ` a ${dataBr(b.data_fim)}` : ""}
                            </p>
                          )}
                        </td>
                        <td className="px-3 py-3 tabular-nums">
                          {hhmm(b.hora_inicio)} – {hhmm(b.hora_fim)}
                        </td>
                        <td className="px-3 py-3">
                          <p>{b.tipo_servico_nome}</p>
                          <p className="text-xs text-muted-foreground">{b.profissional_nome}</p>
                        </td>
                        <td className="hidden max-w-60 px-3 py-3 text-muted-foreground md:table-cell">{b.motivo || "—"}</td>
                        <td className="px-3 py-3">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Pill tom={s.tom}>{s.rotulo}</Pill>
                            <span className="text-xs text-muted-foreground">{b.vale_ate}</span>
                          </div>
                          {b.aviso && (
                            <p className="mt-1 flex max-w-72 items-start gap-1 text-xs text-warning-ink">
                              <TriangleAlert className="mt-0.5 size-3 shrink-0" />
                              {b.aviso}
                            </p>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <Switch size="sm" checked={b.ativo} disabled={!editar || alternar.isPending} onCheckedChange={() => alternar.mutate(b)} aria-label={b.ativo ? "Inativar" : "Ativar"} />
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex justify-end gap-1">
                            {editar && <Button variant="ghost" size="icon-sm" onClick={() => setDialogo(b)} aria-label="Editar bloqueio"><Pencil /></Button>}
                            {excluir && <Button variant="ghost" size="icon-sm" onClick={() => setApagar(b)} aria-label="Excluir bloqueio"><Trash2 /></Button>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />
          </>
        )}
      </TableCard>
      <BloqueioDialog alvo={dialogo} opcoes={opcoes.data} onClose={() => setDialogo(null)} />
      <ConfirmarExclusao
        alvo={apagar}
        titulo="Excluir este bloqueio?"
        descricao="Os horários bloqueados voltam a ficar livres na agenda na hora. Para só pausar, inative."
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

export default function BloqueiosPage() {
  return (
    <Guarda permissao="cadastros_bloqueios.ver">
      <Conteudo />
    </Guarda>
  );
}
