"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

import { hojeIso, useInvalidarAgenda, useOpcoesAgenda } from "./comum";

function SelecoesBasicas({
  unidade,
  setUnidade,
  servico,
  setServico,
  profissional,
  setProfissional,
}: {
  unidade: string;
  setUnidade: (v: string) => void;
  servico: string;
  setServico: (v: string) => void;
  profissional: string;
  setProfissional: (v: string) => void;
}) {
  const opcoes = useOpcoesAgenda();
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Unidade" obrigatorio>
          <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value)} required>
            <option value="">Selecione</option>
            {(opcoes.data?.unidades ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Tipo de serviço" obrigatorio>
          <NativeSelect value={servico} onChange={(e) => setServico(e.target.value)} required>
            <option value="">Selecione</option>
            {(opcoes.data?.servicos ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      <Field label="Profissional" dica="Aulas sem profissional (ex.: TotalPass) são permitidas.">
        <NativeSelect value={profissional} onChange={(e) => setProfissional(e.target.value)}>
          <option value="">Sem profissional</option>
          {(opcoes.data?.profissionais ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </NativeSelect>
      </Field>
    </>
  );
}

/** Nova aula (sessão): serviço, profissional opcional, data, horário e capacidade (vazia = a da unidade). */
export function DialogoNovaAula({ aberto, onFechar }: { aberto: boolean; onFechar: () => void }) {
  const invalidar = useInvalidarAgenda();
  const [unidade, setUnidade] = useState("");
  const [servico, setServico] = useState("");
  const [profissional, setProfissional] = useState("");
  const [data, setData] = useState(hojeIso());
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [capacidade, setCapacidade] = useState("");

  const criar = useMutation({
    mutationFn: () =>
      api.post("/agenda/sessoes", {
        unidade_id: Number(unidade),
        tipo_servico_id: Number(servico),
        profissional_id: profissional ? Number(profissional) : null,
        data,
        hora_inicio: inicio,
        hora_fim: fim || null,
        capacidade: capacidade === "" ? null : Number(capacidade),
      }),
    onSuccess: () => {
      toast.success("Aula criada");
      invalidar();
      onFechar();
    },
  });

  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo="Nova aula"
      descricao="Se a hora final ficar vazia, vale a duração da unidade."
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate();
      }}
      salvando={criar.isPending}
      largura="lg"
    >
      <div className="grid gap-4">
        <SelecoesBasicas {...{ unidade, setUnidade, servico, setServico, profissional, setProfissional }} />
        <div className="grid gap-4 sm:grid-cols-4">
          <Field label="Data" obrigatorio className="sm:col-span-2">
            <Input type="date" value={data} onChange={(e) => setData(e.target.value)} required />
          </Field>
          <Field label="Início" obrigatorio>
            <Input type="time" value={inicio} onChange={(e) => setInicio(e.target.value)} required />
          </Field>
          <Field label="Fim">
            <Input type="time" value={fim} onChange={(e) => setFim(e.target.value)} />
          </Field>
        </div>
        <Field label="Capacidade" dica="Vazio = a capacidade da unidade.">
          <Input type="number" min={0} max={500} value={capacidade} onChange={(e) => setCapacidade(e.target.value)} className="w-32" />
        </Field>
      </div>
    </FormDialog>
  );
}

/** Gerar as aulas vazias de um período pelos horários de funcionamento. Só roda quando o usuário pede. */
export function DialogoGerarSessoes({ aberto, onFechar }: { aberto: boolean; onFechar: () => void }) {
  const invalidar = useInvalidarAgenda();
  const [unidade, setUnidade] = useState("");
  const [servico, setServico] = useState("");
  const [profissional, setProfissional] = useState("");
  const [de, setDe] = useState(hojeIso());
  const [ate, setAte] = useState(hojeIso());

  const gerar = useMutation({
    mutationFn: () =>
      api.post<{ criadas: number; ja_existiam: number; bloqueadas: number }>("/agenda/sessoes/gerar", {
        unidade_id: Number(unidade),
        tipo_servico_id: Number(servico),
        profissional_id: profissional ? Number(profissional) : null,
        data_inicio: de,
        data_fim: ate,
      }),
    onSuccess: (r) => {
      toast.success(`${r.criadas} aula(s) criada(s) · ${r.ja_existiam} já existiam · ${r.bloqueadas} bloqueada(s)`);
      invalidar();
      onFechar();
    },
  });

  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo="Gerar aulas do período"
      descricao="Cria as aulas vazias pelos horários de funcionamento da unidade, pulando bloqueios e o que já existe. Até 92 dias."
      rotuloSalvar="Gerar"
      onSubmit={(e) => {
        e.preventDefault();
        gerar.mutate();
      }}
      salvando={gerar.isPending}
      largura="lg"
    >
      <div className="grid gap-4">
        <SelecoesBasicas {...{ unidade, setUnidade, servico, setServico, profissional, setProfissional }} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="De" obrigatorio>
            <Input type="date" value={de} onChange={(e) => setDe(e.target.value)} required />
          </Field>
          <Field label="Até" obrigatorio>
            <Input type="date" value={ate} onChange={(e) => setAte(e.target.value)} required />
          </Field>
        </div>
      </div>
    </FormDialog>
  );
}
