"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Clock, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Pagination, SearchInput, Segmented, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { hhmm, type HorarioFuncionamento, type OpcoesAgenda, type ResultadoGeracao } from "@/lib/tipos-cadastros-docs";
import { cn } from "@/lib/utils";

import { ConfirmarExclusao, Th, useLista } from "./comum";
import { DiasChips, ServicosCheck, useOpcoes } from "./seletores";

type Situacao = "todos" | "ativos" | "inativos";

const hora = z.string().regex(/^\d{2}:\d{2}/, "Informe o horário.");
const faixa = (v: { hora_inicio: string; hora_fim: string }) => v.hora_fim.slice(0, 5) > v.hora_inicio.slice(0, 5);
const MSG_FAIXA = { message: "O horário final deve ser maior que o inicial.", path: ["hora_fim"] };

const schemaHorario = z
  .object({
    unidade_id: z.coerce.number({ message: "Escolha a unidade." }).int().positive("Escolha a unidade."),
    dia_semana: z.array(z.number()).length(1, "Escolha o dia da semana."),
    hora_inicio: hora,
    hora_fim: hora,
    tipos_servico_ids: z.array(z.number()),
    ativo: z.boolean(),
  })
  .refine(faixa, MSG_FAIXA);
type DadosHorario = z.input<typeof schemaHorario>;

const schemaGerar = z
  .object({
    unidade_id: z.coerce.number({ message: "Escolha a unidade." }).int().positive("Escolha a unidade."),
    dias_semana: z.array(z.number()).min(1, "Marque ao menos um dia."),
    hora_inicio: hora,
    hora_fim: hora,
    tipos_servico_ids: z.array(z.number()),
    ativo: z.boolean(),
  })
  .refine(faixa, MSG_FAIXA);
type DadosGerar = z.input<typeof schemaGerar>;

function HorarioDialog({ alvo, opcoes, onClose }: { alvo: HorarioFuncionamento | "novo" | null; opcoes?: OpcoesAgenda; onClose: () => void }) {
  const qc = useQueryClient();
  const editando = alvo && alvo !== "novo" ? alvo : null;
  const form = useForm<DadosHorario>({
    resolver: zodResolver(schemaHorario),
    defaultValues: { unidade_id: "", dia_semana: [0], hora_inicio: "08:00", hora_fim: "12:00", tipos_servico_ids: [], ativo: true },
  });
  useEffect(() => {
    if (!alvo) return;
    form.reset(
      editando
        ? {
            unidade_id: editando.unidade_id,
            dia_semana: [editando.dia_semana],
            hora_inicio: hhmm(editando.hora_inicio),
            hora_fim: hhmm(editando.hora_fim),
            tipos_servico_ids: editando.tipos_servico_ids,
            ativo: editando.ativo,
          }
        : { unidade_id: opcoes?.unidades.length === 1 ? opcoes.unidades[0].id : "", dia_semana: [0], hora_inicio: "08:00", hora_fim: "12:00", tipos_servico_ids: [], ativo: true },
    );
  }, [alvo, editando, form, opcoes]);
  const salvar = useMutation({
    mutationFn: (d: DadosHorario) => {
      const v = schemaHorario.parse(d);
      const corpo = { ...v, dia_semana: v.dia_semana[0] };
      return editando ? api.put(`/cadastros/horarios/${editando.id}`, corpo) : api.post("/cadastros/horarios", corpo);
    },
    onSuccess: () => {
      toast.success(editando ? "Horário atualizado" : "Horário cadastrado");
      qc.invalidateQueries({ queryKey: ["horarios"] });
      onClose();
    },
  });
  const e = form.formState.errors;
  return (
    <FormDialog
      open={!!alvo}
      onOpenChange={(o) => !o && onClose()}
      titulo={editando ? "Editar horário de funcionamento" : "Novo horário de funcionamento"}
      descricao="Janela em que a unidade atende num dia da semana. A agenda cria as aulas dentro dela."
      rotuloSalvar={editando ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      largura="lg"
      onSubmit={form.handleSubmit((d) => salvar.mutate(d))}
    >
      <div className="space-y-4">
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
        <Field label="Dia da semana" obrigatorio erro={e.dia_semana?.message}>
          <Controller control={form.control} name="dia_semana" render={({ field }) => <DiasChips unico valor={field.value} onChange={field.onChange} />} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Início" obrigatorio erro={e.hora_inicio?.message}>
            <Input type="time" {...form.register("hora_inicio")} />
          </Field>
          <Field label="Fim" obrigatorio erro={e.hora_fim?.message}>
            <Input type="time" {...form.register("hora_fim")} />
          </Field>
        </div>
        <Field label="Serviços atendidos">
          <Controller
            control={form.control}
            name="tipos_servico_ids"
            render={({ field }) => <ServicosCheck servicos={opcoes?.servicos ?? []} valor={field.value} onChange={field.onChange} />}
          />
        </Field>
        <Controller
          control={form.control}
          name="ativo"
          render={({ field }) => (
            <SwitchRow titulo="Ativo" descricao="Desligado = a janela fica guardada, mas a agenda não a usa.">
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </SwitchRow>
          )}
        />
      </div>
    </FormDialog>
  );
}

function GerarDialog({ aberto, opcoes, onClose }: { aberto: boolean; opcoes?: OpcoesAgenda; onClose: () => void }) {
  const qc = useQueryClient();
  const form = useForm<DadosGerar>({
    resolver: zodResolver(schemaGerar),
    defaultValues: { unidade_id: "", dias_semana: [0, 1, 2, 3, 4], hora_inicio: "07:00", hora_fim: "20:00", tipos_servico_ids: [], ativo: true },
  });
  useEffect(() => {
    if (aberto) form.reset({ unidade_id: opcoes?.unidades.length === 1 ? opcoes.unidades[0].id : "", dias_semana: [0, 1, 2, 3, 4], hora_inicio: "07:00", hora_fim: "20:00", tipos_servico_ids: [], ativo: true });
  }, [aberto, form, opcoes]);
  const gerar = useMutation({
    mutationFn: (d: DadosGerar) => api.post<ResultadoGeracao>("/cadastros/horarios/gerar", schemaGerar.parse(d)),
    onSuccess: (r) => {
      toast.success(r.mensagem);
      qc.invalidateQueries({ queryKey: ["horarios"] });
      onClose();
    },
  });
  const e = form.formState.errors;
  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onClose()}
      titulo="Gerar horários"
      descricao="Cria a mesma janela em vários dias de uma vez. O que já existe é ignorado."
      rotuloSalvar="Gerar"
      salvando={gerar.isPending}
      largura="lg"
      onSubmit={form.handleSubmit((d) => gerar.mutate(d))}
    >
      <div className="space-y-4">
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
        </div>
        <Field label="Serviços atendidos">
          <Controller
            control={form.control}
            name="tipos_servico_ids"
            render={({ field }) => <ServicosCheck servicos={opcoes?.servicos ?? []} valor={field.value} onChange={field.onChange} />}
          />
        </Field>
        <Controller
          control={form.control}
          name="ativo"
          render={({ field }) => (
            <SwitchRow titulo="Criar como ativos">
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </SwitchRow>
          )}
        />
      </div>
    </FormDialog>
  );
}

export function HorariosFuncionamento() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("cadastros_horarios.editar");
  const excluir = pode("cadastros_horarios.excluir");
  const opcoes = useOpcoes();
  const lista = useLista<HorarioFuncionamento>("horarios", "/cadastros/horarios", { situacao: "todos", unidade_id: "", dia_semana: "", tipo_servico_id: "" }, 15, "dia");
  const [dialogo, setDialogo] = useState<HorarioFuncionamento | "novo" | null>(null);
  const [gerar, setGerar] = useState(false);
  const [apagar, setApagar] = useState<HorarioFuncionamento | null>(null);

  const remover = useMutation({
    mutationFn: (h: HorarioFuncionamento) => api.del(`/cadastros/horarios/${h.id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Horário excluído");
      qc.invalidateQueries({ queryKey: ["horarios"] });
      setApagar(null);
    },
  });
  const alternar = useMutation({
    mutationFn: (h: HorarioFuncionamento) => api.patch(`/cadastros/horarios/${h.id}/ativo?ativo=${!h.ativo}`),
    onSuccess: (_r, h) => {
      toast.success(h.ativo ? "Horário inativado" : "Horário ativado");
      qc.invalidateQueries({ queryKey: ["horarios"] });
    },
  });

  const situacao = (lista.filtros.situacao as Situacao) ?? "todos";
  const filtrando = !!lista.q || situacao !== "todos" || !!lista.filtros.unidade_id || lista.filtros.dia_semana !== "" || !!lista.filtros.tipo_servico_id;
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
      <TableCard>
        <Toolbar>
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Buscar por unidade" className="sm:w-56" />
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
            {(opcoes.data?.unidades.length ?? 0) > 1 && (
              <NativeSelect className="sm:w-44" value={String(lista.filtros.unidade_id ?? "")} onChange={(e) => lista.setFiltro("unidade_id", e.target.value)} aria-label="Unidade">
                <option value="">Todas as unidades</option>
                {opcoes.data?.unidades.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nome}
                  </option>
                ))}
              </NativeSelect>
            )}
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
          {acoes}
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={Clock}
            titulo={filtrando ? "Nenhum horário com esses filtros" : "Nenhum horário de funcionamento"}
            descricao={filtrando ? "Limpe a busca ou troque os filtros." : "Cadastre os dias e horários em que a unidade atende. Use “Gerar horários” para criar vários de uma vez."}
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
                    <Th coluna="unidade" atual={lista.ordenar} direcao={lista.direcao} onOrdenar={lista.ordenarPor} className="hidden md:table-cell">Unidade</Th>
                    <Th>Serviços</Th>
                    <Th className="hidden lg:table-cell">Aulas/dia</Th>
                    <Th>Ativo</Th>
                    <Th className="w-24" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {lista.itens.map((h) => (
                    <tr key={h.id} className={cn("transition-colors hover:bg-accent/40", !h.ativo && "opacity-60")}>
                      <td className="py-3 pl-4 font-medium">{h.dia_nome}</td>
                      <td className="px-3 py-3 tabular-nums">
                        {hhmm(h.hora_inicio)} – {hhmm(h.hora_fim)}
                      </td>
                      <td className="hidden px-3 py-3 text-muted-foreground md:table-cell">{h.unidade_nome}</td>
                      <td className="px-3 py-3">
                        {h.tipos_servico_ids.length ? h.servicos : <Pill tom="neutral">Todos os serviços</Pill>}
                      </td>
                      <td className="hidden px-3 py-3 text-muted-foreground tabular-nums lg:table-cell">{h.aulas_por_dia}</td>
                      <td className="px-3 py-3">
                        <Switch size="sm" checked={h.ativo} disabled={!editar || alternar.isPending} onCheckedChange={() => alternar.mutate(h)} aria-label={h.ativo ? "Inativar" : "Ativar"} />
                      </td>
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
      <HorarioDialog alvo={dialogo} opcoes={opcoes.data} onClose={() => setDialogo(null)} />
      <GerarDialog aberto={gerar} opcoes={opcoes.data} onClose={() => setGerar(false)} />
      <ConfirmarExclusao
        alvo={apagar}
        titulo={apagar ? `Excluir ${apagar.dia_nome.toLowerCase()} ${hhmm(apagar.hora_inicio)}–${hhmm(apagar.hora_fim)}?` : "Excluir horário?"}
        descricao="As aulas já criadas não mudam; a agenda só deixa de gerar novas aulas nesta janela. Para pausar sem apagar, inative."
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
