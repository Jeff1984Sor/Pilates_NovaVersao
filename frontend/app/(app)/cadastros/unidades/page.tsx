"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ListaCadastro, SeloAtivo } from "@/components/cadastros/lista-cadastro";
import { Mono } from "@/components/mayacorp/brand";
import { Field, SwitchRow } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UnidadeOut } from "@/lib/tipos-cadastros";

const numero = (min: number, max: number, rotulo: string) =>
  z
    .number({ error: `Informe ${rotulo}` })
    .int("Use um número inteiro")
    .min(min, `Mínimo ${min}`)
    .max(max, `Máximo ${max}`);

const schema = z.object({
  nome: z.string().trim().min(2, "Informe o nome (mínimo 2 letras)").max(120, "Máximo 120 caracteres"),
  capacidade: numero(0, 500, "as vagas por aula"),
  duracao_aula_minutos: numero(10, 240, "a duração em minutos"),
  ativo: z.boolean(),
});
type Form = z.infer<typeof schema>;
const vazio: Form = { nome: "", capacidade: 6, duracao_aula_minutos: 50, ativo: true };

function UnidadeDialog({ unidade, open, onClose, editar }: { unidade: UnidadeOut | null; open: boolean; onClose: () => void; editar: boolean }) {
  const qc = useQueryClient();
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: vazio });
  useEffect(() => {
    if (open) f.reset(unidade ? { nome: unidade.nome, capacidade: unidade.capacidade, duracao_aula_minutos: unidade.duracao_aula_minutos, ativo: unidade.ativo } : vazio);
  }, [open, unidade, f]);
  const salvar = useMutation({
    mutationFn: (v: Form) => (unidade ? api.put(`/cadastros/unidades/${unidade.id}`, v) : api.post("/cadastros/unidades", v)),
    onSuccess: () => {
      toast.success(unidade ? "Unidade atualizada" : "Unidade cadastrada");
      qc.invalidateQueries({ queryKey: ["unidades"] });
      onClose();
    },
  });
  const er = f.formState.errors;
  const ativo = useWatch({ control: f.control, name: "ativo" });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo={unidade ? (editar ? "Editar unidade" : "Unidade") : "Nova unidade"}
      descricao="Local onde as aulas acontecem. A capacidade vale para toda aula que não define a sua própria."
      rotuloSalvar={unidade ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (!editar) return onClose();
        void f.handleSubmit((v) => salvar.mutate(v))(e);
      }}
    >
      <fieldset disabled={!editar} className="space-y-4">
        <Field label="Nome" obrigatorio erro={er.nome?.message}>
          <Input {...f.register("nome")} autoFocus placeholder="Ex.: Matriz" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Vagas por aula" obrigatorio erro={er.capacidade?.message} dica="Aulas sem capacidade própria herdam este número. 0 = sem vagas.">
            <Input type="number" inputMode="numeric" min={0} max={500} {...f.register("capacidade", { valueAsNumber: true })} />
          </Field>
          <Field label="Duração da aula (min)" obrigatorio erro={er.duracao_aula_minutos?.message} dica="Usada para sugerir o horário final das aulas.">
            <Input type="number" inputMode="numeric" min={10} max={240} {...f.register("duracao_aula_minutos", { valueAsNumber: true })} />
          </Field>
        </div>
        <SwitchRow titulo="Unidade ativa" descricao="Desativada, deixa de aparecer em novos cadastros, mas o histórico fica preservado.">
          <Switch checked={ativo} onCheckedChange={(v) => f.setValue("ativo", v, { shouldDirty: true })} />
        </SwitchRow>
      </fieldset>
    </FormDialog>
  );
}

export default function UnidadesPage() {
  const { pode } = useAuth();
  const editar = pode("cadastros_unidades.editar");
  const [dialogo, setDialogo] = useState<{ u: UnidadeOut | null } | null>(null);
  return (
    <>
      <ListaCadastro<UnidadeOut>
        chave="unidades"
        path="/cadastros/unidades"
        titulo="Unidades"
        descricao="Locais onde o estúdio atende, com a capacidade e a duração padrão das aulas."
        icone={Building2}
        substantivo="unidade"
        generoFeminino
        rotuloNovo="Nova unidade"
        nomeDe={(u) => u.nome}
        buscaPlaceholder="Buscar unidade…"
        podeEditar={editar}
        podeExcluir={pode("cadastros_unidades.excluir")}
        onNovo={() => setDialogo({ u: null })}
        onEditar={(u) => setDialogo({ u })}
        colunas={[
          { titulo: "Código", ordenar: "codigo", ate: "md", render: (u) => (u.codigo ? <Mono>{u.codigo}</Mono> : <span className="text-muted-foreground">—</span>) },
          { titulo: "Nome", ordenar: "nome", render: (u) => <span className="font-medium">{u.nome}</span> },
          { titulo: "Vagas por aula", ordenar: "capacidade", render: (u) => <span className="num">{u.capacidade}</span> },
          { titulo: "Duração da aula", ordenar: "duracao", ate: "md", render: (u) => <span className="num">{u.duracao_aula_minutos} min</span> },
          { titulo: "Situação", render: (u) => <SeloAtivo ativo={u.ativo} /> },
        ]}
      />
      <UnidadeDialog unidade={dialogo?.u ?? null} open={!!dialogo} onClose={() => setDialogo(null)} editar={editar} />
    </>
  );
}
