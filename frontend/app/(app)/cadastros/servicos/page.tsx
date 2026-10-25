"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Tags } from "lucide-react";
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
import type { ServicoOut } from "@/lib/tipos-cadastros";

const schema = z.object({
  nome: z.string().trim().min(2, "Informe o nome (mínimo 2 letras)").max(80, "Máximo 80 caracteres"),
  ativo: z.boolean(),
});
type Form = z.infer<typeof schema>;

function ServicoDialog({ servico, open, onClose, editar }: { servico: ServicoOut | null; open: boolean; onClose: () => void; editar: boolean }) {
  const qc = useQueryClient();
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { nome: "", ativo: true } });
  useEffect(() => {
    if (open) f.reset(servico ? { nome: servico.nome, ativo: servico.ativo } : { nome: "", ativo: true });
  }, [open, servico, f]);
  const salvar = useMutation({
    mutationFn: (v: Form) => (servico ? api.put(`/cadastros/servicos/${servico.id}`, v) : api.post("/cadastros/servicos", v)),
    onSuccess: () => {
      toast.success(servico ? "Tipo de serviço atualizado" : "Tipo de serviço cadastrado");
      qc.invalidateQueries({ queryKey: ["servicos"] });
      onClose();
    },
  });
  const ativo = useWatch({ control: f.control, name: "ativo" });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo={servico ? (editar ? "Editar tipo de serviço" : "Tipo de serviço") : "Novo tipo de serviço"}
      descricao="O que o estúdio oferece (ex.: Pilates, Fisioterapia). Os planos e as aulas são organizados por tipo de serviço."
      rotuloSalvar={servico ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (!editar) return onClose();
        void f.handleSubmit((v) => salvar.mutate(v))(e);
      }}
    >
      <fieldset disabled={!editar} className="space-y-4">
        <Field label="Nome" obrigatorio erro={f.formState.errors.nome?.message}>
          <Input {...f.register("nome")} autoFocus placeholder="Ex.: Pilates" />
        </Field>
        <SwitchRow titulo="Ativo" descricao="Desativado, deixa de aparecer em novos planos e aulas, mas o histórico fica preservado.">
          <Switch checked={ativo} onCheckedChange={(v) => f.setValue("ativo", v, { shouldDirty: true })} />
        </SwitchRow>
      </fieldset>
    </FormDialog>
  );
}

export default function ServicosPage() {
  const { pode } = useAuth();
  const editar = pode("cadastros_servicos.editar");
  const [dialogo, setDialogo] = useState<{ s: ServicoOut | null } | null>(null);
  return (
    <>
      <ListaCadastro<ServicoOut>
        chave="servicos"
        path="/cadastros/servicos"
        titulo="Tipos de serviço"
        descricao="O que o estúdio oferece: Pilates, Fisioterapia e outros."
        icone={Tags}
        substantivo="tipo de serviço"
        rotuloNovo="Novo tipo de serviço"
        nomeDe={(s) => s.nome}
        buscaPlaceholder="Buscar tipo de serviço…"
        podeEditar={editar}
        podeExcluir={pode("cadastros_servicos.excluir")}
        onNovo={() => setDialogo({ s: null })}
        onEditar={(s) => setDialogo({ s })}
        colunas={[
          { titulo: "Código", ordenar: "codigo", ate: "md", render: (s) => (s.codigo ? <Mono>{s.codigo}</Mono> : <span className="text-muted-foreground">—</span>) },
          { titulo: "Nome", ordenar: "nome", render: (s) => <span className="font-medium">{s.nome}</span> },
          { titulo: "Situação", render: (s) => <SeloAtivo ativo={s.ativo} /> },
        ]}
      />
      <ServicoDialog servico={dialogo?.s ?? null} open={!!dialogo} onClose={() => setDialogo(null)} editar={editar} />
    </>
  );
}
