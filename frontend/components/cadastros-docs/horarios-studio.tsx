"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, History, Info, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm, type UseFormRegister } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Pagination, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { hhmm, type HorarioStudio, type OpcoesAgenda, type ResultadoGeracao } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

import { ConfirmarExclusao, Th, useLista } from "./comum";
import { DiasChips, useOpcoes } from "./seletores";

const hora = z.string().regex(/^\d{2}:\d{2}/, "Informe o horário.");
const faixa = (v: { hora_inicio: string; hora_fim: string }) => v.hora_fim.slice(0, 5) > v.hora_inicio.slice(0, 5);
const MSG_FAIXA = { message: "O horário final deve ser maior que o inicial.", path: ["hora_fim"] };
const id = (msg: string) => z.coerce.number({ message: msg }).int().positive(msg);
const capacidade = z.preprocess((v) => (v === "" || v == null ? null : Number(v)), z.number().int().min(1, "Mínimo 1.").max(200, "Máximo 200.").nullable());

const schemaStudio = z
  .object({
    unidade_id: id("Escolha a unidade."),
    tipo_servico_id: id("Escolha o serviço."),
    profissional_id: z.preprocess((v) => (v === "" || v == null ? null : Number(v)), z.number().nullable()),
    dia_semana: z.array(z.number()).length(1, "Escolha o dia da semana."),
    hora_inicio: hora,
    hora_fim: hora,
    capacidade,
  })
  .refine(faixa, MSG_FAIXA);
type DadosStudio = z.input<typeof schemaStudio>;

const schemaGerar = z
  .object({
    unidade_id: id("Escolha a unidade."),
    tipo_servico_id: id("Escolha o serviço."),
    profissional_id: z.preprocess((v) => (v === "" || v == null ? null : Number(v)), z.number().nullable()),
    dias_semana: z.array(z.number()).min(1, "Marque ao menos um dia."),
    hora_inicio: hora,
    hora_fim: hora,
    intervalo_minutos: z.coerce.number({ message: "Informe os minutos." }).int().min(5, "Mínimo de 5 minutos.").max(480, "Máximo de 480 minutos."),
    capacidade,
  })
  .refine(faixa, MSG_FAIXA);
type DadosGerar = z.input<typeof schemaGerar>;

type Comum = { unidade_id: string | number; tipo_servico_id: string | number; profissional_id: string | number | null };

function Selecoes({
  opcoes,
  register,
  erros,
}: {
  opcoes?: OpcoesAgenda;
  register: UseFormRegister<Comum>;
  erros: Partial<Record<keyof Comum, { message?: string }>>;
}) {
  const e = erros;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Unidade" obrigatorio erro={e.unidade_id?.message}>
          <NativeSelect {...register("unidade_id")}>
            <option value="">Escolha…</option>
            {opcoes?.unidades.map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Serviço" obrigatorio erro={e.tipo_servico_id?.message}>
          <NativeSelect {...register("tipo_servico_id")}>
            <option value="">Escolha…</option>
            {opcoes?.servicos.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      <Field label="Profissional" dica="Opcional.">
        <NativeSelect {...register("profissional_id")}>
          <option value="">Sem profissional definido</option>
          {opcoes?.profissionais.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </NativeSelect>
      </Field>
    </>
  );
}

function StudioDialog({ alvo, opcoes, onClose }: { alvo: HorarioStudio | "novo" | null; opcoes?: OpcoesAgenda; onClose: () => void }) {
  const qc = useQueryClient();
  const editando = alvo && alvo !== "novo" ? alvo : null;
  const form = useForm<DadosStudio>({
    resolver: zodResolver(schemaStudio),
    defaultValues: { unidade_id: "", tipo_servico_id: "", profissional_id: "", dia_semana: [0], hora_inicio: "08:00", hora_fim: "08:50", capacidade: "" },
  });
  useEffect(() => {
    if (!alvo) return;
    form.reset(
      editando
        ? {
            unidade_id: editando.unidade_id,
            tipo_servico_id: editando.tipo_servico_id,
            profissional_id: editando.profissional_id ?? "",
            dia_semana: [editando.dia_semana],
            hora_inicio: hhmm(editando.hora_inicio),
            hora_fim: hhmm(editando.hora_fim),
            capacidade: editando.capacidade ?? "",
          }
        : { unidade_id: opcoes?.unidades.length === 1 ? opcoes.unidades[0].id : "", tipo_servico_id: "", profissional_id: "", dia_semana: [0], hora_inicio: "08:00", hora_fim: "08:50", capacidade: "" },
    );
  }, [alvo, editando, form, opcoes]);
  const salvar = useMutation({
    mutationFn: (d: DadosStudio) => {
      const v = schemaStudio.parse(d);
      const corpo = { ...v, dia_semana: v.dia_semana[0] };
      return editando ? api.put(`/cadastros/horarios/studio/${editando.id}`, corpo) : api.post("/cadastros/horarios/studio", corpo);
    },
    onSuccess: () => {
      toast.success(editando ? "Horário atualizado" : "Horário cadastrado");
      qc.invalidateQueries({ queryKey: ["horarios-studio"] });
      onClose();
    },
  });
  const e = form.formState.errors;
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={editando ? "Editar horário do studio" : "Novo horário do studio"}
      descricao="Grade legada por dia, com serviço, profissional e capacidade."
      rotuloSalvar={editando ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      largura="lg"
      onSubmit={form.handleSubmit((d) => salvar.mutate(d))}
    >
      <div className="space-y-4">
        <Selecoes opcoes={opcoes} register={form.register as unknown as UseFormRegister<Comum>} erros={form.formState.errors} />
        <Field label="Dia da semana" obrigatorio erro={e.dia_semana?.message}>
          <Controller control={form.control} name="dia_semana" render={({ field }) => <DiasChips unico valor={field.value} onChange={field.onChange} />} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Início" obrigatorio erro={e.hora_inicio?.message}>
            <Input type="time" {...form.register("hora_inicio")} />
          </Field>
          <Field label="Fim" obrigatorio erro={e.hora_fim?.message}>
            <Input type="time" {...form.register("hora_fim")} />
          </Field>
          <Field label="Capacidade" erro={e.capacidade?.message} dica="Vazio = a da unidade.">
            <Input type="number" min={1} max={200} {...form.register("capacidade")} />
          </Field>
        </div>
      </div>
    </FormDialog>
  );
}

function GerarStudioDialog({ aberto, opcoes, onClose }: { aberto: boolean; opcoes?: OpcoesAgenda; onClose: () => void }) {
  const qc = useQueryClient();
  const padrao = { unidade_id: "", tipo_servico_id: "", profissional_id: "", dias_semana: [0, 1, 2, 3, 4], hora_inicio: "07:00", hora_fim: "12:00", intervalo_minutos: 60, capacidade: "" };
  const form = useForm<DadosGerar>({ resolver: zodResolver(schemaGerar), defaultValues: padrao });
  useEffect(() => {
    if (aberto) form.reset({ ...padrao, unidade_id: opcoes?.unidades.length === 1 ? opcoes.unidades[0].id : "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, form, opcoes]);
  const gerar = useMutation({
    mutationFn: (d: DadosGerar) => api.post<ResultadoGeracao>("/cadastros/horarios/studio/gerar", schemaGerar.parse(d)),
    onSuccess: (r) => {
      toast.success(r.mensagem);
      qc.invalidateQueries({ queryKey: ["horarios-studio"] });
      onClose();
    },
  });
  const e = form.formState.errors;
  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onClose()}
      titulo="Gerar horários do studio"
      descricao="Divide o período em horários consecutivos do tamanho informado, em cada dia marcado. O que já existe é ignorado."
      rotuloSalvar="Gerar"
      salvando={gerar.isPending}
      largura="lg"
      onSubmit={form.handleSubmit((d) => gerar.mutate(d))}
    >
      <div className="space-y-4">
        <Selecoes opcoes={opcoes} register={form.register as unknown as UseFormRegister<Comum>} erros={form.formState.errors} />
        <Field label="Dias da semana" obrigatorio erro={e.dias_semana?.message}>
          <Controller control={form.control} name="dias_semana" render={({ field }) => <DiasChips valor={field.value} onChange={field.onChange} />} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Início" obrigatorio erro={e.hora_inicio?.message}>
            <Input type="time" {...form.register("hora_inicio")} />
          </Field>
          <Field label="Fim" obrigatorio erro={e.hora_fim?.message}>
            <Input type="time" {...form.register("hora_fim")} />
          </Field>
          <Field label="Duração de cada horário (min)" obrigatorio erro={e.intervalo_minutos?.message}>
            <Input type="number" min={5} max={480} {...form.register("intervalo_minutos")} />
          </Field>
          <Field label="Capacidade" erro={e.capacidade?.message} dica="Vazio = a da unidade.">
            <Input type="number" min={1} max={200} {...form.register("capacidade")} />
          </Field>
        </div>
      </div>
    </FormDialog>
  );
}

export function HorariosStudio() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_horarios.editar");
  const excluir = pode("cadastros_horarios.excluir");
  const opcoes = useOpcoes();
  const lista = useLista<HorarioStudio>("horarios-studio", "/cadastros/horarios/studio", { unidade_id: "", tipo_servico_id: "", profissional_id: "", dia_semana: "" }, 15, "dia");
  const [dialogo, setDialogo] = useState<HorarioStudio | "novo" | null>(null);
  const [gerar, setGerar] = useState(false);
  const [apagar, setApagar] = useState<HorarioStudio | null>(null);
  const remover = useMutation({
    mutationFn: (h: HorarioStudio) => api.del(`/cadastros/horarios/studio/${h.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Horário do studio excluído");
      qc.invalidateQueries({ queryKey: ["horarios-studio"] });
      setApagar(null);
    },
  });
  const filtrando = !!lista.q || Object.values(lista.filtros).some((v) => v !== "" && v != null);
  const acoes = editar && (
    <div className="flex gap-2">
      <Button variant="outline" onClick={() => setGerar(true)}>
        <CalendarPlus /> Gerar horários
      </Button>
      <Button onClick={() => setDialogo("novo")}>
        <Plus /> Novo horário
      </Button>
    </div>
  );
  return (
    <>
      <div className="mb-4 flex items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 p-3.5 text-sm text-warning-ink">
        <Info className="mt-0.5 size-4 shrink-0" />
        <p>
          <strong className="font-semibold">Grade legada.</strong> Estes horários vêm do sistema antigo e são mantidos por compatibilidade. A agenda usa os{" "}
          <strong className="font-semibold">horários de funcionamento</strong> (aba ao lado) e os bloqueios.
        </p>
      </div>
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <NativeSelect className="sm:w-44" value={String(lista.filtros.dia_semana ?? "")} onChange={(e) => lista.setFiltro("dia_semana", e.target.value)} aria-label="Dia da semana">
              <option value="">Todos os dias</option>
              {opcoes.data?.dias.map((d) => (
                <option key={d.valor} value={d.valor}>
                  {d.nome}
                </option>
              ))}
            </NativeSelect>
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
            <span className="text-xs text-muted-foreground">{lista.total} horário(s)</span>
          </div>
          {acoes}
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={History}
            titulo={filtrando ? "Nenhum horário com esses filtros" : "Nenhum horário do studio"}
            descricao={filtrando ? "Troque os filtros." : "A grade legada está vazia. Cadastre só se ainda precisar dela."}
            acao={filtrando ? <Button variant="outline" onClick={lista.limpar}>Limpar filtros</Button> : acoes}
          />
        ) : (
          <>
            <div className={cn("overflow-x-auto", lista.isPlaceholderData && "opacity-60")}>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <Th coluna="dia" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="pl-4">Dia</Th>
                    <Th coluna="inicio" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Horário</Th>
                    <Th coluna="servico" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor}>Serviço</Th>
                    <Th className="hidden md:table-cell">Profissional</Th>
                    <Th className="hidden lg:table-cell">Capacidade</Th>
                    <Th className="w-24" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((h) => (
                    <tr key={h.id} className="transition-colors hover:bg-accent/40">
                      <td className="py-3 pl-4 font-medium">
                        {h.dia_nome} <Pill tom="warning" className="ml-1">Legado</Pill>
                      </td>
                      <td className="px-3 py-3 tabular-nums">
                        {hhmm(h.hora_inicio)} – {hhmm(h.hora_fim)}
                      </td>
                      <td className="px-3 py-3">{h.tipo_servico_nome}</td>
                      <td className="hidden px-3 py-3 text-muted-foreground md:table-cell">{h.profissional_nome ?? "—"}</td>
                      <td className="hidden px-3 py-3 text-muted-foreground tabular-nums lg:table-cell">{h.capacidade ?? "da unidade"}</td>
                      <td className="px-3 py-3">
                        <div className="flex justify-end gap-1">
                          {editar && <Button variant="ghost" size="icon-sm" onClick={() => setDialogo(h)} aria-label="Editar horário"><Pencil /></Button>}
                          {excluir && <Button variant="ghost" size="icon-sm" onClick={() => setApagar(h)} aria-label="Excluir horário"><Trash2 /></Button>}
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
      <StudioDialog alvo={dialogo} opcoes={opcoes.data} onClose={() => setDialogo(null)} />
      <GerarStudioDialog aberto={gerar} opcoes={opcoes.data} onClose={() => setGerar(false)} />
      <ConfirmarExclusao
        alvo={apagar}
        titulo={apagar ? `Excluir ${apagar.dia_nome.toLowerCase()} ${hhmm(apagar.hora_inicio)}–${hhmm(apagar.hora_fim)}?` : "Excluir horário?"}
        descricao="Esta ação não pode ser desfeita."
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
