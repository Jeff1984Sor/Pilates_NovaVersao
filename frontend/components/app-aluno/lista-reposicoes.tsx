"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CalendarClock, Hourglass, Loader2, UserRound, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import type { ReposicaoAluno } from "@/lib/tipos-app-aluno";
import { cn } from "@/lib/utils";

import { apiAluno } from "./api-aluno";
import { Esqueleto, useReposicoes } from "./casca";
import { dataBr, diaSemana, hora } from "./formatar";

const MAX = 300;

function PedirDialog({ r, aberto, onFechar }: { r: ReposicaoAluno; aberto: boolean; onFechar: () => void }) {
  const qc = useQueryClient();
  const [texto, setTexto] = useState(r.pedido?.preferencia ?? "");
  const atualizando = r.pedido?.status === "PENDENTE";

  const pedir = useMutation({
    meta: { silencioso: true },
    mutationFn: () => apiAluno<ReposicaoAluno>(`/reposicoes/${r.id}/pedir`, { method: "POST", body: { preferencia: texto.trim() || null } }),
    onSuccess: () => {
      toast.success(atualizando ? "Preferência atualizada." : "Pedido enviado! A gerência vai escolher o horário e avisar você.", { duration: 6000 });
      qc.invalidateQueries({ queryKey: ["aluno", "reposicoes"] });
      onFechar();
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Dialog open={aberto} onOpenChange={(o) => !o && !pedir.isPending && onFechar()}>
      <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-md">
        <DialogHeader className="border-b p-4">
          <DialogTitle>{atualizando ? "Atualizar preferência" : "Pedir reposição"}</DialogTitle>
          <DialogDescription>
            Aula desmarcada de <span className="capitalize">{diaSemana(r.data)}</span>, {dataBr(r.data)} às {hora(r.hora_inicio)}. Prazo até{" "}
            {dataBr(r.reposicao_ate)}.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 p-4">
          <label htmlFor="preferencia" className="text-sm font-medium">
            Quais dias e horários ficam melhores para você? <span className="font-normal text-muted-foreground">(opcional)</span>
          </label>
          <Textarea
            id="preferencia"
            value={texto}
            maxLength={MAX}
            rows={4}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Ex.: terças e quintas de manhã, depois das 8h"
            className="text-base"
          />
          <p className="text-right text-xs text-muted-foreground">
            {texto.length}/{MAX}
          </p>
          <p className="text-xs text-muted-foreground">É um pedido: a gerência confere as vagas, escolhe o horário e avisa você por WhatsApp.</p>
        </div>
        <DialogFooter className="m-0 rounded-none p-4">
          <Button variant="outline" className="h-11" onClick={onFechar} disabled={pedir.isPending}>
            Cancelar
          </Button>
          <Button className="h-11" onClick={() => pedir.mutate()} disabled={pedir.isPending}>
            {pedir.isPending && <Loader2 className="animate-spin" />}
            {atualizando ? "Salvar" : "Enviar pedido"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Situacao({ r }: { r: ReposicaoAluno }) {
  const p = r.pedido;
  if (!p) return null;
  if (p.status === "PENDENTE") {
    return (
      <div className="mt-3 rounded-lg bg-warning/12 px-3 py-2 text-sm text-warning-ink">
        <p className="flex items-center gap-1.5 font-medium">
          <Hourglass className="size-4" /> Aguardando a gerência
        </p>
        {p.preferencia && <p className="mt-1 text-xs opacity-90">Sua preferência: {p.preferencia}</p>}
      </div>
    );
  }
  if (p.status === "APROVADO") {
    return (
      <p className="mt-3 flex items-start gap-1.5 rounded-lg bg-success/10 px-3 py-2 text-sm font-medium text-success-ink">
        <CalendarCheck className="mt-0.5 size-4 shrink-0" />
        <span>
          Aprovada para {p.aprovado_data ? dataBr(p.aprovado_data) : ""} {p.aprovado_hora ? `às ${hora(p.aprovado_hora)}` : ""}
        </span>
      </p>
    );
  }
  return (
    <p className="mt-3 flex items-start gap-1.5 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-ink">
      <XCircle className="mt-0.5 size-4 shrink-0" />
      <span>
        <strong>Recusada:</strong> {p.motivo_recusa}
      </span>
    </p>
  );
}

function CartaoReposicao({ r }: { r: ReposicaoAluno }) {
  const [aberto, setAberto] = useState(false);
  const encerrado = !r.dentro_do_prazo && !r.pedido;
  return (
    <li className={cn("rounded-2xl border bg-card p-4 shadow-xs", encerrado && "opacity-70")}>
      <p className="text-xs text-muted-foreground">Aula desmarcada</p>
      <p className="mt-0.5 font-semibold">
        <span className="capitalize">{diaSemana(r.data)}</span>, {dataBr(r.data)} às {hora(r.hora_inicio)}
      </p>
      {r.servico && <p className="text-sm text-muted-foreground">{r.servico}</p>}
      {r.profissional && (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <UserRound className="size-3.5" /> {r.profissional}
        </p>
      )}

      {r.dentro_do_prazo && (!r.pedido || r.pedido.status === "PENDENTE") && (
        <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-brand/10 px-3 py-2 text-sm">
          <CalendarClock className="size-4 shrink-0 text-brand" />
          <span>
            Peça até <strong>{dataBr(r.reposicao_ate)}</strong>
            {r.dias_restantes <= 7 && (
              <span className="text-danger-ink">
                {" "}
                · restam {r.dias_restantes} {r.dias_restantes === 1 ? "dia" : "dias"}
              </span>
            )}
          </span>
        </p>
      )}

      <Situacao r={r} />

      {r.pode_pedir && (
        <>
          <Button className="mt-3 h-12 w-full text-[15px]" variant={r.pedido ? "outline" : "default"} onClick={() => setAberto(true)}>
            {r.pedido ? "Alterar preferência" : "Pedir reposição"}
          </Button>
          {aberto && <PedirDialog r={r} aberto={aberto} onFechar={() => setAberto(false)} />}
        </>
      )}
      {!r.dentro_do_prazo && !r.pedido && (
        <p className="mt-3 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
          O prazo terminou em {dataBr(r.reposicao_ate)}. Fale com a recepção se precisar de ajuda.
        </p>
      )}
    </li>
  );
}

export function ListaReposicoes() {
  const q = useReposicoes();
  if (q.isPending) return <Esqueleto />;
  if (q.isError) {
    return (
      <div className="rounded-2xl border bg-card p-6 text-center">
        <p className="text-sm text-muted-foreground">{q.error.message}</p>
        <Button variant="outline" className="mt-3 h-11" onClick={() => q.refetch()}>
          Tentar de novo
        </Button>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Reposições</h1>
        <p className="text-sm text-muted-foreground">
          Aulas desmarcadas podem ser repostas em até 30 dias depois da data original. Você faz o pedido e a gerência escolhe o horário.
        </p>
      </div>
      {q.data.length === 0 ? (
        <div className="rounded-2xl border border-dashed p-8 text-center">
          <CalendarClock className="mx-auto size-8 text-muted-foreground" />
          <p className="mt-3 font-medium">Nenhuma reposição pendente</p>
          <p className="mt-1 text-sm text-muted-foreground">Se você desmarcar uma aula, ela aparece aqui para você pedir a reposição.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {q.data.map((r) => (
            <CartaoReposicao key={r.id} r={r} />
          ))}
        </ul>
      )}
    </div>
  );
}
