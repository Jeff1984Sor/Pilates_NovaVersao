"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarX2, Check, CheckCircle2, Clock, Loader2, UserRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Button } from "@/components/ui/button";
import type { AulaAluno, DesmarcarResp } from "@/lib/tipos-app-aluno";
import { cn } from "@/lib/utils";

import { apiAluno } from "./api-aluno";
import { Esqueleto } from "./casca";
import { dataBr, diaSemana, hora, rotuloDia, somarDias } from "./formatar";

const STATUS: Record<string, { texto: string; classe: string }> = {
  aguardando_chegar: { texto: "Agendada", classe: "bg-muted text-muted-foreground" },
  em_aula: { texto: "Em andamento", classe: "bg-brand/15 text-brand" },
  finalizada: { texto: "Concluída", classe: "bg-success/10 text-success-ink" },
  faltou: { texto: "Falta", classe: "bg-danger/10 text-danger-ink" },
  remarcada: { texto: "Desmarcada", classe: "bg-muted text-muted-foreground" },
};

function CartaoAula({ aula, onConfirmar, onDesmarcar, ocupado }: { aula: AulaAluno; onConfirmar: () => void; onDesmarcar: () => void; ocupado: boolean }) {
  const st = STATUS[aula.status] ?? STATUS.aguardando_chegar;
  return (
    <li className="rounded-2xl border bg-card p-4 shadow-xs">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-2xl leading-none font-semibold tabular-nums">{hora(aula.hora_inicio)}</p>
          <p className="mt-1.5 text-sm text-muted-foreground capitalize">{diaSemana(aula.data)}</p>
        </div>
        <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", st.classe)}>{st.texto}</span>
      </div>
      <div className="mt-3 space-y-1 text-sm">
        {aula.servico && <p className="font-medium">{aula.servico}</p>}
        {aula.profissional && (
          <p className="flex items-center gap-1.5 text-muted-foreground">
            <UserRound className="size-3.5" /> {aula.profissional}
          </p>
        )}
        <p className="flex items-center gap-1.5 text-muted-foreground">
          <Clock className="size-3.5" /> {hora(aula.hora_inicio)} às {hora(aula.hora_fim)}
          {aula.unidade ? ` · ${aula.unidade}` : ""}
        </p>
      </div>

      {aula.confirmada && (
        <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-success/10 px-3 py-2 text-sm font-medium text-success-ink">
          <CheckCircle2 className="size-4" /> Presença confirmada
        </p>
      )}

      {(aula.pode_confirmar || aula.pode_desmarcar) && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {aula.pode_confirmar ? (
            <Button className="h-12 text-[15px]" onClick={onConfirmar} disabled={ocupado}>
              {ocupado ? <Loader2 className="animate-spin" /> : <Check />} Confirmar
            </Button>
          ) : (
            <span />
          )}
          {aula.pode_desmarcar && (
            <Button variant="outline" className="h-12 text-[15px]" onClick={onDesmarcar} disabled={ocupado}>
              <CalendarX2 /> Desmarcar
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

/** Lista das próximas aulas do aluno, com confirmar (um toque) e desmarcar (com aviso de reposição). */
export function ListaAulas() {
  const qc = useQueryClient();
  const aulas = useQuery({
    queryKey: ["aluno", "aulas"],
    queryFn: () => apiAluno<AulaAluno[]>("/aulas"),
    staleTime: 15_000,
    meta: { silencioso: true },
  });
  const [alvo, setAlvo] = useState<AulaAluno | null>(null);
  const [emAcao, setEmAcao] = useState<number | null>(null);

  const atualizar = () => {
    qc.invalidateQueries({ queryKey: ["aluno", "aulas"] });
    qc.invalidateQueries({ queryKey: ["aluno", "reposicoes"] });
  };

  const confirmar = useMutation({
    meta: { silencioso: true },
    mutationFn: (a: AulaAluno) => apiAluno<AulaAluno>(`/aulas/${a.id}/confirmar`, { method: "POST" }),
    onMutate: (a) => setEmAcao(a.id),
    onSuccess: (_r, a) => toast.success(`Presença confirmada: ${rotuloDia(a.data).toLowerCase()} às ${hora(a.hora_inicio)}.`),
    onError: (e) => toast.error(e.message),
    onSettled: () => {
      setEmAcao(null);
      atualizar();
    },
  });

  const desmarcar = useMutation({
    meta: { silencioso: true },
    mutationFn: (a: AulaAluno) => apiAluno<DesmarcarResp>(`/aulas/${a.id}/desmarcar`, { method: "POST" }),
    onSuccess: (r) => {
      toast.success(r.mensagem, { duration: 8000 });
      setAlvo(null);
    },
    onError: (e) => {
      toast.error(e.message);
      setAlvo(null);
    },
    onSettled: atualizar,
  });

  if (aulas.isPending) return <Esqueleto />;
  if (aulas.isError) {
    return (
      <div className="rounded-2xl border bg-card p-6 text-center">
        <p className="text-sm text-muted-foreground">{aulas.error.message}</p>
        <Button variant="outline" className="mt-3 h-11" onClick={() => aulas.refetch()}>
          Tentar de novo
        </Button>
      </div>
    );
  }

  if (aulas.data.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed p-8 text-center">
        <CalendarX2 className="mx-auto size-8 text-muted-foreground" />
        <p className="mt-3 font-medium">Nenhuma aula marcada</p>
        <p className="mt-1 text-sm text-muted-foreground">Quando houver novas aulas, elas aparecem aqui. Veja também suas reposições.</p>
      </div>
    );
  }

  // agrupa por dia
  const dias = new Map<string, AulaAluno[]>();
  aulas.data.forEach((a) => dias.set(a.data, [...(dias.get(a.data) ?? []), a]));

  const prazo = alvo ? dataBr(somarDias(alvo.data, 30)) : "";

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-semibold">Próximas aulas</h1>
      {[...dias.entries()].map(([dia, lista]) => (
        <section key={dia} aria-label={rotuloDia(dia)}>
          <h2 className="mb-2 text-sm font-semibold text-muted-foreground capitalize">{rotuloDia(dia)}</h2>
          <ul className="space-y-3">
            {lista.map((a) => (
              <CartaoAula key={a.id} aula={a} ocupado={emAcao === a.id} onConfirmar={() => confirmar.mutate(a)} onDesmarcar={() => setAlvo(a)} />
            ))}
          </ul>
        </section>
      ))}

      <ConfirmDialog
        open={!!alvo}
        onOpenChange={(o) => !o && !desmarcar.isPending && setAlvo(null)}
        titulo="Desmarcar esta aula?"
        descricao={
          alvo && (
            <span className="block space-y-2">
              <span className="block font-medium text-foreground capitalize">
                {diaSemana(alvo.data)}, {dataBr(alvo.data)} às {hora(alvo.hora_inicio)}
              </span>
              <span className="block">
                Sua vaga será liberada para outros alunos. Você poderá <strong>repor esta aula até {prazo}</strong> (30 dias após a data da aula) na aba
                Reposições.
              </span>
            </span>
          )
        }
        confirmar="Sim, desmarcar"
        destrutivo
        carregando={desmarcar.isPending}
        onConfirm={() => alvo && desmarcar.mutate(alvo)}
      />
    </div>
  );
}
