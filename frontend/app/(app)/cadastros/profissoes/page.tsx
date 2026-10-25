"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Briefcase } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ListaCadastro } from "@/components/cadastros/lista-cadastro";
import { Mono } from "@/components/mayacorp/brand";
import { Field } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ProfissaoOut } from "@/lib/tipos-cadastros";

const schema = z.object({ nome: z.string().trim().min(2, "Informe o nome (mínimo 2 letras)").max(120, "Máximo 120 caracteres") });
type Form = z.infer<typeof schema>;

function ProfissaoDialog({ profissao, open, onClose, editar }: { profissao: ProfissaoOut | null; open: boolean; onClose: () => void; editar: boolean }) {
  const qc = useQueryClient();
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { nome: "" } });
  useEffect(() => {
    if (open) f.reset({ nome: profissao?.nome ?? "" });
  }, [open, profissao, f]);
  const salvar = useMutation({
    mutationFn: (v: Form) => (profissao ? api.put(`/cadastros/profissoes/${profissao.id}`, v) : api.post("/cadastros/profissoes", v)),
    onSuccess: () => {
      toast.success(profissao ? "Profissão atualizada" : "Profissão cadastrada");
      qc.invalidateQueries({ queryKey: ["profissoes"] });
      onClose();
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      titulo={profissao ? (editar ? "Editar profissão" : "Profissão") : "Nova profissão"}
      descricao="Profissão do aluno, usada no cadastro dele e no contrato."
      rotuloSalvar={profissao ? "Salvar" : "Cadastrar"}
      salvando={salvar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        if (!editar) return onClose();
        void f.handleSubmit((v) => salvar.mutate(v))(e);
      }}
    >
      <fieldset disabled={!editar}>
        <Field label="Nome" obrigatorio erro={f.formState.errors.nome?.message}>
          <Input {...f.register("nome")} autoFocus placeholder="Ex.: Advogada" />
        </Field>
      </fieldset>
    </FormDialog>
  );
}

export default function ProfissoesPage() {
  const { pode } = useAuth();
  const editar = pode("cadastros_profissionais.editar");
  const [dialogo, setDialogo] = useState<{ p: ProfissaoOut | null } | null>(null);
  return (
    <>
      <ListaCadastro<ProfissaoOut>
        chave="profissoes"
        path="/cadastros/profissoes"
        titulo="Profissões"
        descricao="Profissões dos alunos, usadas na ficha e no contrato."
        icone={Briefcase}
        substantivo="profissão"
        generoFeminino
        comSituacao={false}
        rotuloNovo="Nova profissão"
        nomeDe={(p) => p.nome}
        buscaPlaceholder="Buscar profissão…"
        podeEditar={editar}
        podeExcluir={pode("cadastros_profissionais.excluir")}
        onNovo={() => setDialogo({ p: null })}
        onEditar={(p) => setDialogo({ p })}
        colunas={[
          { titulo: "Código", ordenar: "codigo", ate: "md", render: (p) => (p.codigo ? <Mono>{p.codigo}</Mono> : <span className="text-muted-foreground">—</span>) },
          { titulo: "Nome", ordenar: "nome", render: (p) => <span className="font-medium">{p.nome}</span> },
        ]}
      />
      <ProfissaoDialog profissao={dialogo?.p ?? null} open={!!dialogo} onClose={() => setDialogo(null)} editar={editar} />
    </>
  );
}
