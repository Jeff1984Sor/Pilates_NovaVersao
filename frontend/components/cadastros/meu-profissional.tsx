"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Stethoscope } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { celularParaTela, mascaraTelefone } from "@/components/cadastros/mascaras";
import { Field } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { MeuProfissional } from "@/lib/tipos-cadastros";

const hoje = () => new Date().toISOString().slice(0, 10);

const schema = z.object({
  nome: z.string().trim().min(2, "Informe o nome (mínimo 2 letras)").max(150, "Máximo 150 caracteres"),
  celular: z.string().refine((v) => v === "" || [10, 11].includes(v.replace(/\D/g, "").length), "Informe o DDD e o número"),
  data_nascimento: z.string().refine((v) => v === "" || (v >= "1900-01-01" && v <= hoje()), "Data inválida"),
  crefito: z.string().max(50, "Máximo 50 caracteres"),
});
type Form = z.infer<typeof schema>;

/** Dados de profissional do próprio usuário (equivalente ao `perfil/` do sistema antigo). Não aparece para quem não é profissional. */
export function MeuProfissionalCard() {
  const qc = useQueryClient();
  const meu = useQuery({ queryKey: ["meu-profissional"], queryFn: () => api.get<MeuProfissional | null>("/cadastros/profissionais/meu"), staleTime: 60_000 });
  const f = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { nome: "", celular: "", data_nascimento: "", crefito: "" } });
  useEffect(() => {
    if (meu.data)
      f.reset({
        nome: meu.data.nome,
        celular: celularParaTela(meu.data.celular),
        data_nascimento: meu.data.data_nascimento ?? "",
        crefito: meu.data.crefito ?? "",
      });
  }, [meu.data, f]);
  const salvar = useMutation({
    mutationFn: (v: Form) =>
      api.patch<MeuProfissional>("/cadastros/profissionais/meu", {
        nome: v.nome,
        celular: v.celular || null,
        data_nascimento: v.data_nascimento || null,
        crefito: v.crefito || null,
      }),
    onSuccess: (r) => {
      toast.success("Seus dados de profissional foram atualizados");
      qc.setQueryData(["meu-profissional"], r);
      qc.invalidateQueries({ queryKey: ["me"] });
      qc.invalidateQueries({ queryKey: ["profissionais"] });
      qc.invalidateQueries({ queryKey: ["usuarios"] });
    },
  });
  if (!meu.data) return null;
  const er = f.formState.errors;
  return (
    <form className="card-surface space-y-4 p-5" onSubmit={(e) => void f.handleSubmit((v) => salvar.mutate(v))(e)}>
      <h3 className="flex items-center gap-2 font-semibold">
        <Stethoscope className="size-4 text-info-ink" /> Meus dados de profissional
      </h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome" obrigatorio erro={er.nome?.message}>
          <Input {...f.register("nome")} />
        </Field>
        <Field label="Celular (WhatsApp)" erro={er.celular?.message} dica="Recebe o código de recuperação de senha.">
          <Input inputMode="tel" placeholder="(11) 99999-0000" {...f.register("celular", { onChange: (e) => f.setValue("celular", mascaraTelefone(e.target.value)) })} />
        </Field>
        <Field label="Data de nascimento" erro={er.data_nascimento?.message}>
          <Input type="date" max={hoje()} {...f.register("data_nascimento")} />
        </Field>
        <Field label="CREFITO" erro={er.crefito?.message}>
          <Input {...f.register("crefito")} />
        </Field>
      </div>
      <p className="text-xs text-muted-foreground">E-mail, comissão e situação são alterados por quem gerencia os profissionais.</p>
      <div className="flex justify-end">
        <Button type="submit" disabled={salvar.isPending || !f.formState.isDirty}>
          {salvar.isPending && <Loader2 className="animate-spin" />} Salvar dados
        </Button>
      </div>
    </form>
  );
}
