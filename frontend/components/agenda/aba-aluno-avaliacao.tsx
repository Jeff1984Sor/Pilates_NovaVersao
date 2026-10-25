"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ClipboardCheck, FileDown, FileSpreadsheet, Repeat2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AulaAvaliativa, Registro } from "@/lib/tipos-agenda";

import { dataBr, useInvalidarAgenda } from "./comum";
import { DialogoFichaAvaliativa, STATUS_AVALIATIVA, TIPOS_AVALIATIVA } from "./dialogos-aluno";
import { EditorRegistro, ListaRegistros } from "./editor-registro";
import { SeletorAula, useAulasParaRegistro } from "./aba-aluno-evolucao";

function AulasAvaliativas({ alunoId }: { alunoId: number }) {
  const { pode, somenteProprias } = useAuth();
  const invalidar = useInvalidarAgenda();
  const [ficha, setFicha] = useState<AulaAvaliativa | null>(null);
  const [converter, setConverter] = useState<AulaAvaliativa | null>(null);
  const q = useQuery({
    queryKey: ["agenda", "aluno-avaliativas", alunoId],
    queryFn: () => api.get<{ itens: AulaAvaliativa[] }>(`/agenda/alunos/${alunoId}/avaliativas`),
  });
  const converte = useMutation({
    mutationFn: (id: number) => api.post<{ mensagem: string }>(`/agenda/avaliativas/${id}/converter`),
    onSuccess: (r) => {
      toast.success(r.mensagem);
      setConverter(null);
      invalidar();
    },
    onError: () => setConverter(null),
  });
  const itens = q.data?.itens ?? [];
  if (!itens.length) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">Aulas avaliativas</h3>
      <ul className="card-surface divide-y overflow-hidden">
        {itens.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
            <span className="num font-medium">
              {dataBr(a.data)} {a.hora_inicio}
            </span>
            <Pill tom="info">{TIPOS_AVALIATIVA[a.tipo]}</Pill>
            <Pill tom={a.status === "CONVERTIDA" ? "success" : a.status === "CANCELADA" ? "neutral" : "warning"}>{STATUS_AVALIATIVA[a.status]}</Pill>
            <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{a.queixa_principal}</span>
            {pode("aulas.avaliar") && (
              <Button size="xs" variant="outline" onClick={() => setFicha(a)}>
                Ficha
              </Button>
            )}
            {pode("agenda.editar") && !somenteProprias && a.status !== "CONVERTIDA" && (
              <Button size="xs" variant="outline" onClick={() => setConverter(a)}>
                <Repeat2 /> Converter
              </Button>
            )}
          </li>
        ))}
      </ul>
      <DialogoFichaAvaliativa aula={ficha} onFechar={() => setFicha(null)} />
      <ConfirmDialog
        open={!!converter}
        onOpenChange={(o) => !o && setConverter(null)}
        titulo="Marcar como convertida?"
        descricao="Isso só marca a aula avaliativa como convertida. O contrato do aluno é criado na aba Contratos."
        confirmar="Marcar como convertida"
        carregando={converte.isPending}
        onConfirm={() => converter && converte.mutate(converter.id)}
      />
    </section>
  );
}

/** Avaliações do aluno (ficha, aba "Avaliações"): nova avaliação, histórico, exportação e aulas avaliativas. */
export function AbaAlunoAvaliacao({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const podeAvaliar = pode("aulas.avaliar");
  const aulas = useAulasParaRegistro(alunoId);
  const [escolhida, setEscolhida] = useState("");
  const lista = useQuery({
    queryKey: ["agenda", "aluno-avaliacoes", alunoId],
    queryFn: () => api.get<{ itens: Registro[] }>(`/agenda/alunos/${alunoId}/avaliacoes`),
  });
  const aulasLista = aulas.data ?? [];
  const reservaId = escolhida || (aulasLista[0] ? String(aulasLista[0].id) : "");

  async function exportar(formato: "pdf" | "xlsx") {
    try {
      await baixar(`/agenda/alunos/${alunoId}/avaliacoes/exportar`, { query: { formato } }, `avaliacoes-aluno-${alunoId}.${formato}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Não foi possível exportar.");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <ClipboardCheck className="size-4 text-info-ink" /> Avaliações
        </h3>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => exportar("pdf")}>
            <FileDown /> PDF
          </Button>
          <Button size="sm" variant="outline" onClick={() => exportar("xlsx")}>
            <FileSpreadsheet /> Excel
          </Button>
        </div>
      </div>

      {podeAvaliar && (
        <div className="card-surface space-y-3 p-4">
          {aulas.isPending ? (
            <Skeleton className="h-24" />
          ) : aulasLista.length === 0 ? (
            <p className="text-sm text-muted-foreground">O aluno ainda não tem aulas para receber uma avaliação.</p>
          ) : (
            <>
              <SeletorAula aulas={aulasLista} valor={reservaId} onChange={setEscolhida} />
              <EditorRegistro key={reservaId} tipo="avaliacao" reservaId={Number(reservaId)} />
            </>
          )}
        </div>
      )}

      {lista.isPending ? (
        <Skeleton className="h-32 rounded-2xl" />
      ) : (
        <ListaRegistros tipo="avaliacao" itens={lista.data?.itens ?? []} podeEditar={podeAvaliar} vazio="Nenhuma avaliação registrada para este aluno." />
      )}

      <AulasAvaliativas alunoId={alunoId} />
    </div>
  );
}
