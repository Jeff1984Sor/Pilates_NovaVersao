"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Pause, Play, Square, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { StatusBadge } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora } from "@/lib/format";
import {
  ROTULO_PUBLICO,
  ROTULO_STATUS_DESTINATARIO,
  type Comunicado,
  type DestinatarioComunicado,
} from "@/lib/tipos-comunicacao";

const STATUS: Record<string, { label: string; tom: "brand" | "warning" | "neutral" | "success"; pulse?: boolean }> = {
  enviando: { label: "Enviando", tom: "brand", pulse: true },
  pausado: { label: "Pausado", tom: "warning" },
  cancelado: { label: "Cancelado", tom: "neutral" },
  concluido: { label: "Concluído", tom: "success" },
};
const TOM_DEST: Record<string, "success" | "danger" | "warning" | "neutral" | "brand"> = {
  enviado: "success",
  falha: "danger",
  sem_telefone: "warning",
  cancelado: "neutral",
  pendente: "neutral",
  enviando: "brand",
};

/** Um comunicado com progresso ao vivo (atualiza a cada 3 s enquanto está em andamento), ações e relatório. */
export function ComunicadoCard({ inicial, destaque }: { inicial: Comunicado; destaque?: boolean }) {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const [relatorio, setRelatorio] = useState(false);
  const [cancelando, setCancelando] = useState(false);
  const q = useQuery({
    queryKey: ["comunicado", inicial.id],
    queryFn: () => api.get<Comunicado>(`/comunicacao/comunicados/${inicial.id}`),
    initialData: inicial,
    refetchInterval: (query) => (["enviando"].includes(query.state.data?.status ?? "") ? 3000 : false),
  });
  const c = q.data;
  const agir = useMutation({
    mutationFn: (acao: "pausar" | "retomar" | "cancelar") => api.post<Comunicado>(`/comunicacao/comunicados/${c.id}/${acao}`),
    onSuccess: (novo, acao) => {
      qc.setQueryData(["comunicado", c.id], novo);
      qc.invalidateQueries({ queryKey: ["comunicados"] });
      setCancelando(false);
      toast.success(acao === "pausar" ? "Envio pausado" : acao === "retomar" ? "Envio retomado" : "Envio cancelado");
    },
  });
  const s = STATUS[c.status];
  const podeAgir = pode("comunicacao.enviar");
  return (
    <div className={`card-surface space-y-3 p-4 ${destaque ? "ring-2 ring-brand/40" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            Comunicado #{c.id} <StatusBadge label={s.label} tom={s.tom} pulse={s.pulse} />
          </p>
          <p className="text-xs text-muted-foreground">
            {ROTULO_PUBLICO[c.publico]} · {dataHora(c.criado_em)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {podeAgir && c.status === "enviando" && (
            <Button size="sm" variant="outline" disabled={agir.isPending} onClick={() => agir.mutate("pausar")}>
              <Pause /> Pausar
            </Button>
          )}
          {podeAgir && c.status === "pausado" && (
            <Button size="sm" disabled={agir.isPending} onClick={() => agir.mutate("retomar")}>
              <Play /> Retomar
            </Button>
          )}
          {podeAgir && (c.status === "enviando" || c.status === "pausado") && (
            <Button size="sm" variant="outline" onClick={() => setCancelando(true)}>
              <Square /> Cancelar
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setRelatorio(true)}>
            <FileText /> Relatório
          </Button>
        </div>
      </div>
      <p className="line-clamp-2 text-sm whitespace-pre-wrap text-muted-foreground">{c.texto}</p>
      <div>
        <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={c.percentual} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${c.percentual}%` }} />
        </div>
        <p className="mt-1.5 flex flex-wrap gap-x-4 text-xs text-muted-foreground">
          <span>{c.percentual}%</span>
          <span className="text-success-ink">{c.enviados} enviado(s)</span>
          <span>{c.pendentes} na fila</span>
          {c.falhas > 0 && <span className="text-danger-ink">{c.falhas} falha(s)</span>}
          {c.sem_telefone > 0 && <span>{c.sem_telefone} sem telefone</span>}
          {c.cancelados > 0 && <span>{c.cancelados} cancelado(s)</span>}
        </p>
      </div>
      {c.aviso && c.status === "pausado" && (
        <p className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning-ink">
          <TriangleAlert className="size-3.5 shrink-0" /> {c.aviso}
        </p>
      )}
      <ConfirmDialog
        open={cancelando}
        onOpenChange={setCancelando}
        titulo="Cancelar o envio?"
        descricao="Quem ainda não recebeu não receberá. Quem já recebeu continua no relatório."
        confirmar="Cancelar envio"
        destrutivo
        carregando={agir.isPending}
        onConfirm={() => agir.mutate("cancelar")}
      />
      {relatorio && <Relatorio id={c.id} onClose={() => setRelatorio(false)} />}
    </div>
  );
}

function Relatorio({ id, onClose }: { id: number; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["comunicado", id, "destinatarios"],
    queryFn: () => api.get<DestinatarioComunicado[]>(`/comunicacao/comunicados/${id}/destinatarios`),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Relatório do comunicado #{id}</DialogTitle>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Aluno</TableHead>
                <TableHead>Telefone</TableHead>
                <TableHead>Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(q.data ?? []).map((d) => (
                <TableRow key={d.aluno_id}>
                  <TableCell className="font-medium">{d.nome}</TableCell>
                  <TableCell className="text-muted-foreground">{d.telefone ?? "—"}</TableCell>
                  <TableCell>
                    <StatusBadge label={ROTULO_STATUS_DESTINATARIO[d.status] ?? d.status} tom={TOM_DEST[d.status] ?? "neutral"} />
                    {d.erro && <p className="mt-0.5 text-xs text-muted-foreground">{d.erro}</p>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </DialogContent>
    </Dialog>
  );
}
