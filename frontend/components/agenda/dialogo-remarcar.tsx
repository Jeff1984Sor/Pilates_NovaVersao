"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import type { HorarioRemarcacao, ReservaResumo, StatusReserva } from "@/lib/tipos-agenda";

import { dataBr, useInvalidarAgenda, useOpcoesAgenda } from "./comum";

/**
 * Remarcar a aula de um aluno. As opções sugeridas vêm do servidor SEM criar nada; a aula só nasce ao confirmar.
 * Aula desmarcada (reposição) tem prazo: o servidor recusa depois de `reposicao_ate`, a menos que a equipe ignore.
 */
export function DialogoRemarcar({
  reservaId,
  status,
  reposicaoAte,
  profissionalId,
  aberto,
  onFechar,
  onRemarcada,
}: {
  reservaId: number;
  status: StatusReserva;
  reposicaoAte: string | null;
  profissionalId: number | null;
  aberto: boolean;
  onFechar: () => void;
  onRemarcada?: (r: ReservaResumo) => void;
}) {
  const opcoes = useOpcoesAgenda();
  const invalidar = useInvalidarAgenda();
  const [data, setData] = useState("");
  const [hora, setHora] = useState("");
  const [prof, setProf] = useState("");
  const [ignorar, setIgnorar] = useState(false);

  const sugestoes = useQuery({
    queryKey: ["agenda", "reserva", reservaId, "horarios"],
    queryFn: () => api.get<{ itens: HorarioRemarcacao[] }>(`/agenda/reservas/${reservaId}/horarios`),
    enabled: aberto,
    staleTime: 30_000,
  });

  const remarcar = useMutation({
    mutationFn: () =>
      api.post<ReservaResumo>(`/aulas/reservas/${reservaId}/remarcar`, {
        data,
        hora_inicio: hora,
        profissional_id: prof ? Number(prof) : null,
        ignorar_prazo_reposicao: ignorar,
      }),
    onSuccess: (r) => {
      toast.success(`Aula remarcada para ${dataBr(r.data)} às ${r.hora_inicio}`);
      invalidar();
      onRemarcada?.(r);
      onFechar();
    },
  });

  const emReposicao = status === "CANCELADA" && !!reposicaoAte;
  return (
    <FormDialog
      open={aberto}
      onOpenChange={(o) => !o && onFechar()}
      titulo="Remarcar aula"
      descricao="A duração segue a aula atual. A vaga é conferida na hora de salvar."
      onSubmit={(e) => {
        e.preventDefault();
        remarcar.mutate();
      }}
      salvando={remarcar.isPending}
    >
      <div className="grid gap-4">
        {emReposicao && (
          <p className="rounded-lg border border-info/30 bg-info/8 px-3 py-2 text-xs text-info-ink">
            Reposição disponível até <strong>{dataBr(reposicaoAte)}</strong>.
          </p>
        )}
        <Field label="Horários com vaga" dica="Opcional: escolher um preenche data, horário e profissional.">
          <NativeSelect
            value=""
            onChange={(e) => {
              const s = sugestoes.data?.itens[Number(e.target.value)];
              if (!s) return;
              setData(s.data);
              setHora(s.hora_inicio);
              setProf(s.profissional_id ? String(s.profissional_id) : "");
            }}
          >
            <option value="">{sugestoes.isPending ? "Carregando…" : "Escolher um horário sugerido"}</option>
            {(sugestoes.data?.itens ?? []).slice(0, 200).map((s, i) => (
              <option key={`${s.data}-${s.hora_inicio}-${s.profissional_id}-${i}`} value={i}>
                {dataBr(s.data)} · {s.rotulo}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Data" obrigatorio>
            <Input type="date" value={data} onChange={(e) => setData(e.target.value)} required />
          </Field>
          <Field label="Hora de início" obrigatorio>
            <Input type="time" value={hora} onChange={(e) => setHora(e.target.value)} required />
          </Field>
        </div>
        <Field label="Profissional">
          <NativeSelect value={prof} onChange={(e) => setProf(e.target.value)}>
            <option value="">{profissionalId ? "Manter profissional atual" : "Sem profissional"}</option>
            {(opcoes.data?.profissionais ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {emReposicao && (
          <label className="flex items-center justify-between gap-4 rounded-xl border bg-background/50 p-3 text-sm">
            <span>Ignorar o prazo da reposição</span>
            <Switch checked={ignorar} onCheckedChange={setIgnorar} />
          </label>
        )}
      </div>
    </FormDialog>
  );
}
