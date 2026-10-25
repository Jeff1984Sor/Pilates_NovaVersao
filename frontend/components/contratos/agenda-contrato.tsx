"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarCheck, CircleCheck, Loader2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { data } from "@/lib/format";
import { DIAS_SEMANA, type AgendaOpcoes, type ResultadoAgenda, type Slot } from "@/lib/tipos-contratos";

import { useInvalidarContratos } from "./comum";

interface Escolha {
  slot: string; // valor do slot ("0|08:00|08:50")
  prof: string;
}

/** Passo "Escolher agenda": um horário por dia da semana, exatamente `aulas_por_semana`. */
export function AgendaContrato({ contratoId, novo }: { contratoId: number; novo?: boolean }) {
  const invalidar = useInvalidarContratos();
  const [escolhas, setEscolhas] = useState<Record<number, Escolha>>({});
  const [resultado, setResultado] = useState<ResultadoAgenda | null>(null);
  const opcoes = useQuery({
    queryKey: ["contratos", "agenda-opcoes", contratoId],
    queryFn: () => api.get<AgendaOpcoes>(`/contratos/${contratoId}/agenda/opcoes`),
    retry: false,
  });

  const gerar = useMutation({
    mutationFn: (o: AgendaOpcoes) =>
      api.post<ResultadoAgenda>(`/contratos/${contratoId}/agenda`, {
        selecoes: Object.entries(escolhas).map(([dia, e]) => {
          const s = o.slots.find((x) => x.valor === e.slot)!;
          return { dia_semana: Number(dia), inicio: s.inicio, fim: s.fim, profissional_id: Number(e.prof) };
        }),
      }),
    onSuccess: (r) => {
      setResultado(r);
      invalidar();
      if (r.conflitos.length === 0) toast.success(`${r.reservas_criadas} aula(s) reservada(s)`);
      else toast.warning(`${r.reservas_criadas} aula(s) reservada(s); ${r.conflitos.length} data(s) com conflito.`);
    },
  });

  if (opcoes.isPending) return <Skeleton className="h-64 w-full rounded-2xl" />;
  if (opcoes.isError || !opcoes.data) {
    return (
      <div className="card-surface p-6 text-sm">
        <p className="flex items-center gap-2 font-medium">
          <TriangleAlert className="size-4 text-warning" /> Não é possível escolher a agenda deste contrato.
        </p>
        <p className="mt-1 text-muted-foreground">{opcoes.error?.message}</p>
        <Button className="mt-4" variant="outline" render={<Link href={`/contratos/${contratoId}`} />}>
          Voltar ao contrato
        </Button>
      </div>
    );
  }
  const o = opcoes.data;
  const porDia = new Map<number, Slot[]>();
  o.slots.forEach((s) => porDia.set(s.dia_semana, [...(porDia.get(s.dia_semana) ?? []), s]));
  const escolhidos = Object.keys(escolhas).length;
  const completo = escolhidos === o.exatamente && Object.values(escolhas).every((e) => e.slot && e.prof);

  function escolherSlot(dia: number, valor: string) {
    setEscolhas((atual) => {
      const novo = { ...atual };
      if (!valor) {
        delete novo[dia];
        return novo;
      }
      const slot = o.slots.find((s) => s.valor === valor)!;
      const profAtual = atual[dia]?.prof;
      const profOk = slot.profissionais.some((p) => String(p.id) === profAtual);
      novo[dia] = { slot: valor, prof: profOk ? profAtual! : String(slot.profissionais[0]?.id ?? "") };
      return novo;
    });
  }

  if (resultado) {
    return (
      <div className="card-surface space-y-4 p-6">
        <p className="flex items-center gap-2 text-lg font-semibold">
          <CircleCheck className="size-5 text-success" /> {resultado.reservas_criadas} aula(s) reservada(s)
        </p>
        <p className="text-sm text-muted-foreground">
          {resultado.sessoes_criadas} aula(s) nova(s) criada(s) na agenda · {resultado.ja_existentes} já estava(m) reservada(s).
        </p>
        {resultado.conflitos.length > 0 && (
          <div className="rounded-xl border border-warning/40 bg-warning/10 p-4 text-sm">
            <p className="mb-1 flex items-center gap-2 font-medium">
              <TriangleAlert className="size-4 text-warning" /> {resultado.conflitos.length} data(s) não foram reservadas (o restante foi mantido)
            </p>
            <ul className="list-disc space-y-0.5 pl-5">
              {resultado.conflitos.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">Resolva cada data na agenda (remarque ou abra uma vaga) e repita este passo: ele não duplica o que já existe.</p>
          </div>
        )}
        <div className="flex gap-2">
          <Button render={<Link href={`/contratos/${contratoId}`} />}>Voltar ao contrato</Button>
          <Button variant="outline" render={<Link href="/agenda/semana" />}>
            Ver a agenda
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {novo && (
        <p className="rounded-xl border border-success/40 bg-success/10 p-3 text-sm">
          <CircleCheck className="mr-1 inline size-4 text-success" /> Contrato criado. Agora escolha os horários das aulas.
        </p>
      )}
      {o.ja_agendadas > 0 && (
        <p className="rounded-xl border bg-muted/50 p-3 text-sm">
          Este contrato já tem {o.ja_agendadas} aula(s) agendada(s) (dias: {o.dias_semana_agendados.map((d) => DIAS_SEMANA[d]).join(", ")}). Repetir a escolha não duplica as
          aulas já reservadas.
        </p>
      )}
      <div className="card-surface p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold">Horários da semana</h2>
            <p className="text-xs text-muted-foreground">
              Escolha <b>{o.exatamente}</b> horário(s), no máximo um por dia. Aulas de {data(o.inicio)} a {data(o.fim)}. Só aparecem horários com vaga em todas as
              datas e sem bloqueio.
            </p>
          </div>
          <span className={`num rounded-lg px-2.5 py-1 text-sm font-medium ${completo ? "bg-success/15 text-success-ink" : "bg-muted"}`}>
            {escolhidos} de {o.exatamente}
          </span>
        </div>
        {o.slots.length === 0 && <p className="text-sm text-muted-foreground">{o.mensagem}</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3, 4, 5, 6]
            .filter((d) => porDia.has(d))
            .map((dia) => {
              const slots = porDia.get(dia)!;
              const e = escolhas[dia];
              const slotAtual = slots.find((s) => s.valor === e?.slot);
              return (
                <div key={dia} className={`rounded-xl border p-3 ${e ? "border-brand bg-brand/5" : ""}`}>
                  <p className="mb-2 text-sm font-medium">{DIAS_SEMANA[dia]}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <NativeSelect aria-label={`Horário de ${DIAS_SEMANA[dia]}`} value={e?.slot ?? ""} onChange={(ev) => escolherSlot(dia, ev.target.value)}>
                      <option value="">Sem aula neste dia</option>
                      {slots.map((s) => (
                        <option key={s.valor} value={s.valor}>
                          {s.inicio} às {s.fim}
                        </option>
                      ))}
                    </NativeSelect>
                    <NativeSelect
                      aria-label={`Profissional de ${DIAS_SEMANA[dia]}`}
                      value={e?.prof ?? ""}
                      disabled={!e}
                      onChange={(ev) => setEscolhas((a) => ({ ...a, [dia]: { ...a[dia], prof: ev.target.value } }))}
                    >
                      {!e && <option value="">Profissional</option>}
                      {(slotAtual?.profissionais ?? []).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.nome}
                        </option>
                      ))}
                    </NativeSelect>
                  </div>
                </div>
              );
            })}
        </div>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" render={<Link href={`/contratos/${contratoId}`} />}>
          Fazer depois
        </Button>
        <Button disabled={!completo || gerar.isPending} onClick={() => gerar.mutate(o)}>
          {gerar.isPending ? <Loader2 className="animate-spin" /> : <CalendarCheck />} Reservar as aulas
        </Button>
      </div>
    </div>
  );
}
