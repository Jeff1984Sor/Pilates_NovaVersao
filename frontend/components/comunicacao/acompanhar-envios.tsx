"use client";

import { useQuery } from "@tanstack/react-query";
import { BellOff, BellRing } from "lucide-react";

import { Pagination, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { StatusBadge } from "@/components/mayacorp/status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useState } from "react";

import { api } from "@/lib/api";
import { dataHora } from "@/lib/format";
import { ROTULO_STATUS_MENSAGEM, type Acompanhamento } from "@/lib/tipos-comunicacao";

const TOM: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  sent: "success",
  failed: "danger",
  sessao_caida: "danger",
  credencial_recusada: "danger",
  sem_telefone: "warning",
  pendente: "warning",
};

/** Acompanhamento dos avisos automáticos (scheduler): o que foi enviado, falhou ou foi pulado. */
export function AcompanharEnvios() {
  const [status, setStatus] = useState("");
  const [pagina, setPagina] = useState(1);
  const q = useQuery({
    queryKey: ["whatsapp", "automaticos", status, pagina],
    queryFn: () => api.get<Acompanhamento>("/whatsapp/automaticos", { status, pagina, por_pagina: 25 }),
    refetchInterval: 30_000,
  });
  const d = q.data;
  return (
    <div className="space-y-4">
      <div
        className={`flex items-start gap-3 rounded-xl border p-3.5 text-sm ${d?.envio_automatico_ativo ? "border-success/30 bg-success/8 text-success-ink" : "border-warning/30 bg-warning/10 text-warning-ink"}`}
      >
        {d?.envio_automatico_ativo ? <BellRing className="mt-0.5 size-4 shrink-0" /> : <BellOff className="mt-0.5 size-4 shrink-0" />}
        <p>
          {d?.envio_automatico_ativo
            ? "O envio automático está LIGADO neste ambiente."
            : "O envio automático está DESLIGADO neste ambiente: nenhum aviso automático é enviado. O Full liga em Configurações > Integrações > WhatsApp."}
        </p>
      </div>
      {d && Object.keys(d.hoje).length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          <span className="text-muted-foreground">Últimas 24 h:</span>
          {Object.entries(d.hoje).map(([s, n]) => (
            <StatusBadge key={s} label={`${ROTULO_STATUS_MENSAGEM[s] ?? s}: ${n}`} tom={TOM[s] ?? "neutral"} />
          ))}
        </div>
      )}
      <TableCard>
        <Toolbar className="sm:justify-start">
          <NativeSelect value={status} onChange={(e) => { setStatus(e.target.value); setPagina(1); }} className="w-56" aria-label="Situação">
            <option value="">Todas as situações</option>
            <option value="sent">Enviados</option>
            <option value="failed">Com falha</option>
            <option value="sem_telefone">Sem telefone válido</option>
            <option value="sessao_caida">Sessão desconectada</option>
          </NativeSelect>
        </Toolbar>
        {q.isPending ? (
          <TableSkeleton colunas={5} />
        ) : (d?.itens.length ?? 0) === 0 ? (
          <EmptyState icone={BellOff} titulo="Nenhum aviso automático ainda" descricao="Quando o envio automático estiver ligado, cada aviso aparece aqui." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Quando</TableHead>
                  <TableHead>Aviso</TableHead>
                  <TableHead>Destinatário</TableHead>
                  <TableHead>Referência</TableHead>
                  <TableHead>Situação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d!.itens.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{dataHora(i.enviado_em)}</TableCell>
                    <TableCell className="whitespace-nowrap">{i.tipo_rotulo}</TableCell>
                    <TableCell>{i.destinatario ?? "—"}</TableCell>
                    <TableCell className="whitespace-nowrap">{i.data_referencia.split("-").reverse().join("/")}</TableCell>
                    <TableCell>
                      <StatusBadge label={ROTULO_STATUS_MENSAGEM[i.status] ?? i.status} tom={TOM[i.status] ?? "neutral"} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <Pagination pagina={pagina} porPagina={25} total={d?.total ?? 0} onChange={setPagina} />
      </TableCard>
    </div>
  );
}
