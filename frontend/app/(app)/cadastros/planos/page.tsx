"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ListaCadastro, SeloAtivo } from "@/components/cadastros/lista-cadastro";
import { valorParaApi, valorPorAula } from "@/components/cadastros/mascaras";
import { Mono } from "@/components/mayacorp/brand";
import { Segmented } from "@/components/mayacorp/data-table";
import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { moeda } from "@/lib/format";
import type { PlanoOpcoes, PlanoOut } from "@/lib/tipos-cadastros";

const inteiro = (min: number, max: number, rotulo: string) =>
  z.number({ error: `Informe ${rotulo}` }).int("Use um número inteiro").min(min, `Mínimo ${min}`).max(max, `Máximo ${max}`);

const schema = z.object({
  nome: z.string().trim().min(2, "Informe o nome (mínimo 2 letras)").max(120, "Máximo 120 caracteres"),
  tipo_servico_id: z.string().min(1, "Escolha o tipo de serviço"),
  valor: z.string().refine((v) => valorParaApi(v) !== null, "Informe um valor válido (ex.: 300,00)"),
  aulas_por_semana: inteiro(0, 14, "as aulas por semana"),
  duracao_meses: inteiro(1, 120, "a duração em meses"),
  recorrencia: z.enum(["MENSAL", "SEMANAL"]),
  is_avulso: z.boolean(),
  categoria_receita_id: z.string(),
  subcategoria_receita_id: z.string(),
  modelo_contrato_id: z.string(),
  ativo: z.boolean(),
});
type Form = z.infer<typeof schema>;
const vazio: Form = {
  nome: "",
  tipo_servico_id: "",
  valor: "",
  aulas_por_semana: 2,
  duracao_meses: 1,
  recorrencia: "MENSAL",
  is_avulso: false,
  categoria_receita_id: "",
  subcategoria_receita_id: "",
  modelo_contrato_id: "",
  ativo: true,
};
const idOuNulo = (v: string) => (v ? Number(v) : null);

function PlanoDialog({ plano, open, onClose, editar }: { plano: PlanoOut | null; open: boolean; onClose: () => void; editar: boolean }) {
  const qc = useQueryClient();
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: vazio });
  const opcoes = useQuery({ queryKey: ["planos", "opcoes"], queryFn: () => api.get<PlanoOpcoes>("/planos/opcoes"), enabled: open, staleTime: 30_000 });
  useEffect(() => {
    if (!open) return;
    f.reset(
      plano
        ? {
            nome: plano.nome,
            tipo_servico_id: String(plano.tipo_servico_id),
            valor: Number(plano.valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
            aulas_por_semana: plano.aulas_por_semana,
            duracao_meses: plano.duracao_meses,
            recorrencia: plano.recorrencia,
            is_avulso: plano.is_avulso,
            categoria_receita_id: plano.categoria_receita_id ? String(plano.categoria_receita_id) : "",
            subcategoria_receita_id: plano.subcategoria_receita_id ? String(plano.subcategoria_receita_id) : "",
            modelo_contrato_id: plano.modelo_contrato_id ? String(plano.modelo_contrato_id) : "",
            ativo: plano.ativo,
          }
        : vazio,
    );
  }, [open, plano, f, opcoes.isSuccess]);

  const salvar = useMutation({
    mutationFn: (v: Form) => {
      const corpo = {
        nome: v.nome,
        tipo_servico_id: Number(v.tipo_servico_id),
        valor: valorParaApi(v.valor),
        aulas_por_semana: v.aulas_por_semana,
        duracao_meses: v.duracao_meses,
        recorrencia: v.recorrencia,
        is_avulso: v.is_avulso,
        categoria_receita_id: idOuNulo(v.categoria_receita_id),
        subcategoria_receita_id: idOuNulo(v.subcategoria_receita_id),
        modelo_contrato_id: idOuNulo(v.modelo_contrato_id),
        ativo: v.ativo,
      };
      return plano ? api.put(`/planos/${plano.id}`, corpo) : api.post("/planos", corpo);
    },
    onSuccess: () => {
      toast.success(plano ? "Plano atualizado" : "Plano cadastrado");
      qc.invalidateQueries({ queryKey: ["planos"] });
      onClose();
    },
  });

  const er = f.formState.errors;
  const [valorTxt, aulas, meses, avulso, categoria, ativo] = useWatch({ control: f.control, name: ["valor", "aulas_por_semana", "duracao_meses", "is_avulso", "categoria_receita_id", "ativo"] });
  const valorNum = Number(valorParaApi(valorTxt) ?? NaN);
  const porAula = valorPorAula(valorNum, Number(aulas));
  const total = Number.isFinite(valorNum) ? valorNum * Math.max(Number(meses) || 1, 1) : null;
  const subs = (opcoes.data?.subcategorias_receita ?? []).filter((s) => !categoria || String(s.categoria_id) === categoria);

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo={plano ? (editar ? "Editar plano" : "Plano") : "Novo plano"}
      descricao="O valor do plano é MENSAL. O valor por aula é calculado: valor mensal ÷ (aulas por semana × 4)."
      rotuloSalvar={plano ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      largura="lg"
      onSubmit={(e) => {
        e.preventDefault();
        if (!editar) return onClose();
        void f.handleSubmit((v) => salvar.mutate(v))(e);
      }}
    >
      <fieldset disabled={!editar} className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome" obrigatorio erro={er.nome?.message} className="sm:col-span-2">
          <Input {...f.register("nome")} autoFocus placeholder="Ex.: Pilates 2x por semana" />
        </Field>
        <Field label="Tipo de serviço" obrigatorio erro={er.tipo_servico_id?.message}>
          <NativeSelect {...f.register("tipo_servico_id")}>
            <option value="">Escolha…</option>
            {opcoes.data?.tipos_servico
              .filter((t) => t.ativo || String(t.id) === f.getValues("tipo_servico_id"))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nome}
                  {t.ativo ? "" : " (inativo)"}
                </option>
              ))}
          </NativeSelect>
        </Field>
        <Field label="Valor mensal (R$)" obrigatorio erro={er.valor?.message}>
          <Input {...f.register("valor")} inputMode="decimal" placeholder="300,00" className="num" />
        </Field>
        <Field label="Aulas por semana" obrigatorio erro={er.aulas_por_semana?.message}>
          <Input type="number" inputMode="numeric" min={0} max={14} {...f.register("aulas_por_semana", { valueAsNumber: true })} />
        </Field>
        <Field label="Duração (meses)" obrigatorio erro={er.duracao_meses?.message}>
          <Input type="number" inputMode="numeric" min={1} max={120} {...f.register("duracao_meses", { valueAsNumber: true })} />
        </Field>
        <div className="grid grid-cols-3 gap-3 rounded-xl border bg-muted/40 p-3 sm:col-span-2" aria-live="polite">
          <div>
            <p className="text-xs text-muted-foreground">Valor por aula</p>
            <p className="text-lg font-semibold num">{porAula === null ? "—" : moeda(porAula)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Parcela mensal</p>
            <p className="text-lg font-semibold num">{Number.isFinite(valorNum) ? moeda(valorNum) : "—"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Total do contrato</p>
            <p className="text-lg font-semibold num">{total === null ? "—" : moeda(total)}</p>
          </div>
        </div>
        <Field label="Recorrência" dica="Contratos são sempre cobrados por mês; a recorrência vale para aulas avulsas.">
          <NativeSelect {...f.register("recorrencia")}>
            <option value="MENSAL">Mensal</option>
            <option value="SEMANAL">Semanal</option>
          </NativeSelect>
        </Field>
        <Field label="Modelo de contrato" dica="Opcional. Sem modelo, o contrato usa o padrão.">
          <NativeSelect {...f.register("modelo_contrato_id")}>
            <option value="">Nenhum</option>
            {opcoes.data?.modelos_contrato
              .filter((m) => m.ativo || String(m.id) === f.getValues("modelo_contrato_id"))
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nome}
                </option>
              ))}
          </NativeSelect>
        </Field>
        <Field label="Categoria de receita">
          <NativeSelect
            {...f.register("categoria_receita_id", {
              onChange: () => f.setValue("subcategoria_receita_id", ""),
            })}
          >
            <option value="">Nenhuma</option>
            {opcoes.data?.categorias_receita.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Subcategoria de receita">
          <NativeSelect {...f.register("subcategoria_receita_id")}>
            <option value="">Nenhuma</option>
            {subs.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="space-y-3 sm:col-span-2">
          <SwitchRow titulo="Plano de aula avulsa" descricao={avulso ? "Vendido por aula/pacote, sem contrato mensal." : "Plano mensal de contrato."}>
            <Switch checked={avulso} onCheckedChange={(v) => f.setValue("is_avulso", v, { shouldDirty: true })} />
          </SwitchRow>
          <SwitchRow titulo="Plano ativo" descricao="Desativado, deixa de aparecer em novos contratos, mas os contratos existentes continuam.">
            <Switch checked={ativo} onCheckedChange={(v) => f.setValue("ativo", v, { shouldDirty: true })} />
          </SwitchRow>
        </div>
      </fieldset>
    </FormDialog>
  );
}

export default function PlanosPage() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const editar = pode("planos.editar");
  const [dialogo, setDialogo] = useState<{ p: PlanoOut | null } | null>(null);
  const opcoes = useQuery({ queryKey: ["planos", "opcoes"], queryFn: () => api.get<PlanoOpcoes>("/planos/opcoes"), staleTime: 30_000 });
  const duplicar = useMutation({
    mutationFn: (p: PlanoOut) => api.post<PlanoOut>(`/planos/${p.id}/duplicar`),
    onSuccess: (novo) => {
      toast.success(`Cópia criada: ${novo.nome}`, { description: "Ajuste o que for preciso." });
      qc.invalidateQueries({ queryKey: ["planos"] });
      setDialogo({ p: novo });
    },
  });
  return (
    <>
      <ListaCadastro<PlanoOut>
        chave="planos"
        path="/planos"
        titulo="Planos"
        descricao="Planos mensais e de aula avulsa, com o valor por aula calculado."
        icone={ClipboardList}
        substantivo="plano"
        rotuloNovo="Novo plano"
        nomeDe={(p) => p.nome}
        buscaPlaceholder="Buscar plano…"
        podeEditar={editar}
        podeExcluir={pode("planos.excluir")}
        onNovo={() => setDialogo({ p: null })}
        onEditar={(p) => setDialogo({ p })}
        filtros={(lista) => (
          <>
            <Segmented<string>
              value={String(lista.filtros.tipo ?? "todos")}
              onChange={(v) => lista.setFiltro("tipo", v === "todos" ? undefined : v)}
              opcoes={[
                { value: "todos", label: "Todos os tipos" },
                { value: "mensal", label: "Mensais" },
                { value: "avulso", label: "Avulsos" },
              ]}
            />
            <div className="w-full sm:w-48">
              <NativeSelect
                aria-label="Filtrar por tipo de serviço"
                value={String(lista.filtros.tipo_servico_id ?? "")}
                onChange={(e) => lista.setFiltro("tipo_servico_id", e.target.value ? Number(e.target.value) : undefined)}
              >
                <option value="">Todos os serviços</option>
                {opcoes.data?.tipos_servico.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.nome}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </>
        )}
        acoesExtras={(p) => (
          <DropdownMenuItem onClick={() => duplicar.mutate(p)}>
            <Copy /> Duplicar
          </DropdownMenuItem>
        )}
        colunas={[
          { titulo: "Código", ordenar: "codigo", ate: "lg", render: (p) => (p.codigo ? <Mono>{p.codigo}</Mono> : <span className="text-muted-foreground">—</span>) },
          {
            titulo: "Nome",
            ordenar: "nome",
            render: (p) => (
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{p.nome}</span>
                {p.is_avulso && <Pill tom="info">Avulso</Pill>}
              </div>
            ),
          },
          { titulo: "Serviço", ate: "md", render: (p) => <span className="text-muted-foreground">{p.tipo_servico_nome ?? "—"}</span> },
          { titulo: "Valor mensal", ordenar: "valor", render: (p) => <span className="num">{moeda(p.valor)}</span> },
          { titulo: "Aulas/semana", ordenar: "aulas", ate: "md", render: (p) => <span className="num">{p.aulas_por_semana}</span> },
          { titulo: "Valor por aula", ate: "md", render: (p) => <span className="num">{p.valor_aula === null ? "—" : moeda(p.valor_aula)}</span> },
          { titulo: "Duração", ordenar: "duracao", ate: "lg", render: (p) => <span className="num">{p.duracao_meses} {p.duracao_meses === 1 ? "mês" : "meses"}</span> },
          { titulo: "Situação", render: (p) => <SeloAtivo ativo={p.ativo} /> },
        ]}
      />
      <PlanoDialog plano={dialogo?.p ?? null} open={!!dialogo} onClose={() => setDialogo(null)} editar={editar} />
    </>
  );
}
