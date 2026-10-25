"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CalendarSearch, Loader2, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { AulaAluno, OpcaoReposicao, ReposicaoAluno } from "@/lib/tipos-app-aluno";
import { cn } from "@/lib/utils";

import { apiAluno } from "./api-aluno";
import { Esqueleto, useReposicoes } from "./casca";
import { dataBr, diaCurto, diaSemana, hora } from "./formatar";

function Opcoes({ reposicao, aberto, onFechar }: { reposicao: ReposicaoAluno; aberto: boolean; onFechar: () => void }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [escolhida, setEscolhida] = useState<OpcaoReposicao | null>(null);

  const opcoes = useQuery({
    queryKey: ["aluno", "reposicoes", reposicao.id, "opcoes"],
    queryFn: () => apiAluno<OpcaoReposicao[]>(`/reposicoes/${reposicao.id}/opcoes`),
    enabled: aberto,
    staleTime: 0,
    meta: { silencioso: true },
  });

  const remarcar = useMutation({
    meta: { silencioso: true },
    mutationFn: (o: OpcaoReposicao) => apiAluno<AulaAluno>(`/reposicoes/${reposicao.id}/remarcar`, { method: "POST", body: { aula_id: o.aula_id } }),
    onSuccess: (a) => {
      toast.success(`Reposição marcada para ${diaCurto(a.data)} às ${hora(a.hora_inicio)}.`, { duration: 6000 });
      setEscolhida(null);
      onFechar();
      qc.invalidateQueries({ queryKey: ["aluno"] });
      router.push("/app");
    },
    onError: (e) => {
      toast.error(e.message);
      setEscolhida(null);
      opcoes.refetch(); // a vaga pode ter acabado: mostra a lista atual
    },
  });

  const dias = new Map<string, OpcaoReposicao[]>();
  (opcoes.data ?? []).forEach((o) => dias.set(o.data, [...(dias.get(o.data) ?? []), o]));

  return (
    <>
      <Dialog open={aberto} onOpenChange={(o) => !o && !remarcar.isPending && onFechar()}>
        <DialogContent className="max-h-[88dvh] gap-0 overflow-hidden p-0 sm:max-w-md">
          <DialogHeader className="border-b p-4">
            <DialogTitle>Escolha o novo horário</DialogTitle>
            <DialogDescription>
              Aula desmarcada de {diaCurto(reposicao.data)} às {hora(reposicao.hora_inicio)}. Prazo até {dataBr(reposicao.reposicao_ate)}.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[66dvh] overflow-y-auto p-4">
            {opcoes.isPending ? (
              <Esqueleto />
            ) : opcoes.isError ? (
              <p className="text-sm text-muted-foreground">{opcoes.error.message}</p>
            ) : dias.size === 0 ? (
              <div className="py-6 text-center">
                <CalendarSearch className="mx-auto size-8 text-muted-foreground" />
                <p className="mt-3 font-medium">Nenhum horário com vaga agora</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Fale com a recepção para combinar a reposição antes de {dataBr(reposicao.reposicao_ate)}.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {[...dias.entries()].map(([dia, lista]) => (
                  <section key={dia}>
                    <h3 className="mb-2 text-sm font-semibold text-muted-foreground capitalize">{diaCurto(dia)}</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {lista.map((o) => (
                        <button
                          key={o.aula_id}
                          type="button"
                          onClick={() => setEscolhida(o)}
                          className="min-h-14 rounded-xl border bg-card px-3 py-2 text-left active:bg-muted"
                        >
                          <span className="block text-lg font-semibold tabular-nums">{hora(o.hora_inicio)}</span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {o.profissional ?? "Equipe"} · {o.vagas} {o.vagas === 1 ? "vaga" : "vagas"}
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!escolhida}
        onOpenChange={(o) => !o && !remarcar.isPending && setEscolhida(null)}
        titulo="Confirmar reposição?"
        descricao={
          escolhida && (
            <span className="block capitalize">
              {diaSemana(escolhida.data)}, {dataBr(escolhida.data)} às {hora(escolhida.hora_inicio)}
              {escolhida.profissional ? ` com ${escolhida.profissional}` : ""}. Sua vaga fica garantida na hora.
            </span>
          )
        }
        confirmar="Sim, marcar"
        carregando={remarcar.isPending}
        onConfirm={() => escolhida && remarcar.mutate(escolhida)}
      />
    </>
  );
}

function CartaoReposicao({ r }: { r: ReposicaoAluno }) {
  const [aberto, setAberto] = useState(false);
  return (
    <li className={cn("rounded-2xl border bg-card p-4 shadow-xs", !r.dentro_do_prazo && "opacity-70")}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-muted-foreground">Aula desmarcada</p>
          <p className="mt-0.5 font-semibold capitalize">
            {diaSemana(r.data)}, {dataBr(r.data)} às {hora(r.hora_inicio)}
          </p>
          {r.servico && <p className="text-sm text-muted-foreground">{r.servico}</p>}
          {r.profissional && (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <UserRound className="size-3.5" /> {r.profissional}
            </p>
          )}
        </div>
      </div>
      {r.dentro_do_prazo ? (
        <>
          <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-brand/10 px-3 py-2 text-sm">
            <CalendarClock className="size-4 shrink-0 text-brand" />
            <span>
              Reponha até <strong>{dataBr(r.reposicao_ate)}</strong>
              {r.dias_restantes <= 7 && <span className="text-danger-ink"> · restam {r.dias_restantes} {r.dias_restantes === 1 ? "dia" : "dias"}</span>}
            </span>
          </p>
          <Button className="mt-3 h-12 w-full text-[15px]" onClick={() => setAberto(true)}>
            Escolher novo horário
          </Button>
          <Opcoes reposicao={r} aberto={aberto} onFechar={() => setAberto(false)} />
        </>
      ) : (
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
        <p className="text-sm text-muted-foreground">Aulas desmarcadas podem ser repostas em até 30 dias depois da data original.</p>
      </div>
      {q.data.length === 0 ? (
        <div className="rounded-2xl border border-dashed p-8 text-center">
          <CalendarClock className="mx-auto size-8 text-muted-foreground" />
          <p className="mt-3 font-medium">Nenhuma reposição pendente</p>
          <p className="mt-1 text-sm text-muted-foreground">Se você desmarcar uma aula, ela aparece aqui com o prazo para repor.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {q.data.map((r) => (
            <CartaoReposicao key={r.id} r={r} />
          ))}
        </ul>
      )}
      {q.isFetching && <Loader2 className="mx-auto size-4 animate-spin text-muted-foreground" />}
    </div>
  );
}
