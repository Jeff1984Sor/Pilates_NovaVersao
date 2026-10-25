"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, Check, Loader2, MessageSquareText, Search, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { data as dataBr, dataHora } from "@/lib/format";
import type { ListaPedidosReposicao, OpcaoReposicao, PedidoReposicaoEquipe, StatusPedidoReposicao } from "@/lib/tipos-app-aluno";
import { cn } from "@/lib/utils";

const CHIPS: { valor: StatusPedidoReposicao; rotulo: string }[] = [
  { valor: "PENDENTE", rotulo: "Pendentes" },
  { valor: "APROVADO", rotulo: "Aprovados" },
  { valor: "RECUSADO", rotulo: "Recusados" },
];
const TOM = { PENDENTE: "warning", APROVADO: "success", RECUSADO: "danger" } as const;
const NOME = { PENDENTE: "Aguardando", APROVADO: "Aprovado", RECUSADO: "Recusado" } as const;
const hora = (v: string) => v.slice(0, 5);

function AprovarDialog({ pedido, onFechar }: { pedido: PedidoReposicaoEquipe; onFechar: () => void }) {
  const qc = useQueryClient();
  const [ignorar, setIgnorar] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [aulaId, setAulaId] = useState<number | null>(null);

  const opcoes = useQuery({
    queryKey: ["reposicoes", pedido.id, "opcoes", ignorar],
    queryFn: () => api.get<OpcaoReposicao[]>(`/reposicoes/${pedido.id}/opcoes`, { ignorar_prazo: ignorar }),
  });
  const aprovar = useMutation({
    mutationFn: () => api.post(`/reposicoes/${pedido.id}/aprovar`, { aula_id: aulaId, ignorar_prazo: ignorar, motivo: ignorar ? motivo.trim() : null }),
    onSuccess: () => {
      toast.success("Reposição aprovada. O aluno foi avisado por WhatsApp.");
      qc.invalidateQueries({ queryKey: ["reposicoes"] });
      onFechar();
    },
    onError: () => opcoes.refetch(), // a vaga pode ter acabado
  });

  const escolhida = (opcoes.data ?? []).find((o) => o.aula_id === aulaId);
  const foraDoPrazo = !!escolhida && escolhida.data > pedido.reposicao_ate;
  const precisaMotivo = ignorar && (foraDoPrazo || pedido.prazo_vencido) && motivo.trim().length < 3;
  const dias = new Map<string, OpcaoReposicao[]>();
  (opcoes.data ?? []).forEach((o) => dias.set(o.data, [...(dias.get(o.data) ?? []), o]));

  return (
    <Dialog open onOpenChange={(o) => !o && !aprovar.isPending && onFechar()}>
      <DialogContent className="max-h-[92dvh] gap-0 overflow-hidden p-0 sm:max-w-xl">
        <DialogHeader className="border-b p-5">
          <DialogTitle>Aprovar reposição de {pedido.aluno?.nome}</DialogTitle>
          <DialogDescription>
            Aula desmarcada de {dataBr(pedido.aula_original.data)} às {hora(pedido.aula_original.hora_inicio)} · prazo até {dataBr(pedido.reposicao_ate)}.
            {pedido.preferencia && (
              <span className="mt-2 block rounded-lg bg-muted px-3 py-2 text-foreground">
                <strong>Preferência do aluno:</strong> {pedido.preferencia}
              </span>
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[56dvh] space-y-4 overflow-y-auto p-5">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={ignorar} onChange={(e) => { setIgnorar(e.target.checked); setAulaId(null); }} />
            <span>
              <strong>Ignorar o prazo</strong> (mostrar aulas depois de {dataBr(pedido.reposicao_ate)}). Exige um motivo, que fica na auditoria.
            </span>
          </label>
          {ignorar && (
            <Textarea value={motivo} maxLength={300} onChange={(e) => setMotivo(e.target.value)} placeholder="Motivo para ignorar o prazo" />
          )}
          {opcoes.isPending ? (
            <p className="text-sm text-muted-foreground">Buscando aulas com vaga...</p>
          ) : dias.size === 0 ? (
            <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
              Nenhuma aula com vaga do mesmo serviço e unidade {ignorar ? "nos próximos 90 dias" : "até o fim do prazo"}. Gere as aulas da agenda ou recuse com motivo.
            </p>
          ) : (
            [...dias.entries()].map(([dia, lista]) => (
              <section key={dia}>
                <h3 className="mb-1.5 text-sm font-semibold">{dataBr(dia)}</h3>
                <div className="grid gap-2 sm:grid-cols-3">
                  {lista.map((o) => (
                    <button
                      key={o.aula_id}
                      type="button"
                      onClick={() => setAulaId(o.aula_id)}
                      className={cn(
                        "rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:bg-muted",
                        aulaId === o.aula_id && "border-brand bg-brand/10 ring-1 ring-brand",
                      )}
                    >
                      <span className="block font-semibold tabular-nums">{hora(o.hora_inicio)}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {o.profissional ?? "Sem profissional"} · {o.vagas} {o.vagas === 1 ? "vaga" : "vagas"}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            ))
          )}
          {foraDoPrazo && !ignorar && <p className="text-sm text-danger-ink">Esta aula é depois do prazo: marque “Ignorar o prazo”.</p>}
        </div>
        <DialogFooter className="m-0 rounded-none p-4">
          <Button variant="outline" onClick={onFechar} disabled={aprovar.isPending}>
            Cancelar
          </Button>
          <Button disabled={!aulaId || aprovar.isPending || precisaMotivo} onClick={() => aprovar.mutate()}>
            {aprovar.isPending ? <Loader2 className="animate-spin" /> : <Check />} Aprovar e avisar o aluno
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RecusarDialog({ pedido, onFechar }: { pedido: PedidoReposicaoEquipe; onFechar: () => void }) {
  const qc = useQueryClient();
  const [motivo, setMotivo] = useState("");
  const recusar = useMutation({
    mutationFn: () => api.post(`/reposicoes/${pedido.id}/recusar`, { motivo: motivo.trim() }),
    onSuccess: () => {
      toast.success("Pedido recusado. O aluno foi avisado por WhatsApp.");
      qc.invalidateQueries({ queryKey: ["reposicoes"] });
      onFechar();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && !recusar.isPending && onFechar()}>
      <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-md">
        <DialogHeader className="border-b p-5">
          <DialogTitle>Recusar reposição de {pedido.aluno?.nome}</DialogTitle>
          <DialogDescription>O motivo aparece no app do aluno e na mensagem de WhatsApp.</DialogDescription>
        </DialogHeader>
        <div className="p-5">
          <Textarea value={motivo} maxLength={300} onChange={(e) => setMotivo(e.target.value)} placeholder="Ex.: sem horários disponíveis neste período" autoFocus />
        </div>
        <DialogFooter className="m-0 rounded-none p-4">
          <Button variant="outline" onClick={onFechar} disabled={recusar.isPending}>
            Cancelar
          </Button>
          <Button variant="destructive" disabled={motivo.trim().length < 3 || recusar.isPending} onClick={() => recusar.mutate()}>
            {recusar.isPending && <Loader2 className="animate-spin" />} Recusar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PainelReposicoes({ podeDecidir }: { podeDecidir: boolean }) {
  const [status, setStatus] = useState<StatusPedidoReposicao>("PENDENTE");
  const [busca, setBusca] = useState("");
  const [aprovando, setAprovando] = useState<PedidoReposicaoEquipe | null>(null);
  const [recusando, setRecusando] = useState<PedidoReposicaoEquipe | null>(null);

  const q = useQuery({
    queryKey: ["reposicoes", "lista", status, busca],
    queryFn: () => api.get<ListaPedidosReposicao>("/reposicoes", { status, q: busca.trim() || undefined }),
    placeholderData: (anterior) => anterior,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Situação do pedido">
          {CHIPS.map((c) => (
            <button
              key={c.valor}
              type="button"
              role="tab"
              aria-selected={status === c.valor}
              onClick={() => setStatus(c.valor)}
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded-full border px-3.5 text-sm font-medium transition-colors",
                status === c.valor ? "border-brand bg-brand/10 text-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {c.rotulo}
              <span className="rounded-full bg-muted px-1.5 text-xs tabular-nums">{q.data?.contagens[c.valor] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="relative sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar aluno" className="pl-9" />
        </div>
      </div>

      {q.isPending ? (
        <p className="text-sm text-muted-foreground">Carregando...</p>
      ) : q.data && q.data.itens.length === 0 ? (
        <div className="card-surface p-10 text-center text-sm text-muted-foreground">Nenhum pedido {CHIPS.find((c) => c.valor === status)?.rotulo.toLowerCase()}.</div>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {q.data?.itens.map((p) => (
            <li key={p.id} className="card-surface space-y-3 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{p.aluno?.nome ?? "Aluno"}</p>
                  <p className="text-sm text-muted-foreground">
                    Aula desmarcada de {dataBr(p.aula_original.data)} às {hora(p.aula_original.hora_inicio)}
                    {p.aula_original.servico ? ` · ${p.aula_original.servico}` : ""}
                  </p>
                </div>
                <Pill tom={TOM[p.status]}>{NOME[p.status]}</Pill>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <CalendarCheck className="size-4 text-muted-foreground" />
                <span>Reposição até {dataBr(p.reposicao_ate)}</span>
                {p.status === "PENDENTE" &&
                  (p.prazo_vencido ? <Pill tom="danger">Prazo vencido</Pill> : p.dias_restantes <= 7 ? <Pill tom="warning">Restam {p.dias_restantes} d</Pill> : null)}
                <span className="text-muted-foreground">· pedido em {dataHora(p.pedido_em)}</span>
              </div>
              {p.preferencia && (
                <p className="flex items-start gap-2 rounded-lg bg-muted px-3 py-2 text-sm">
                  <MessageSquareText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <span>{p.preferencia}</span>
                </p>
              )}
              {p.status === "APROVADO" && (
                <p className="text-sm text-success-ink">
                  Aprovada para {p.aprovado_data ? dataBr(p.aprovado_data) : ""} às {p.aprovado_hora ? hora(p.aprovado_hora) : ""} por {p.decidido_por ?? "gerência"}
                  {p.ignorou_prazo && <span className="text-warning-ink"> · prazo ignorado: {p.motivo_ignorar_prazo}</span>}
                </p>
              )}
              {p.status === "RECUSADO" && (
                <p className="text-sm text-danger-ink">
                  Recusada por {p.decidido_por ?? "gerência"}: {p.motivo_recusa}
                </p>
              )}
              {p.status === "PENDENTE" && podeDecidir && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => setAprovando(p)} disabled={!p.aula_desmarcada}>
                    <Check /> Aprovar
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setRecusando(p)}>
                    <X /> Recusar
                  </Button>
                  {!p.aula_desmarcada && <span className="self-center text-xs text-muted-foreground">A aula já não está desmarcada.</span>}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {aprovando && <AprovarDialog pedido={aprovando} onFechar={() => setAprovando(null)} />}
      {recusando && <RecusarDialog pedido={recusando} onFechar={() => setRecusando(null)} />}
    </div>
  );
}
