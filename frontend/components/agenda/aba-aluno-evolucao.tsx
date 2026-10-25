"use client";

import { useQuery } from "@tanstack/react-query";
import { FileDown, FileSpreadsheet, HeartPulse } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AulaDoAluno, Registro } from "@/lib/tipos-agenda";

import { dataBr } from "./comum";
import { EditorRegistro, ListaRegistros } from "./editor-registro";

/** Seletor da aula (reserva) a que o novo registro pertence: as mais recentes que não foram desmarcadas. */
export function useAulasParaRegistro(alunoId: number) {
  return useQuery({
    queryKey: ["agenda", "aluno-aulas", alunoId, "para-registro"],
    queryFn: () => api.get<{ itens: AulaDoAluno[] }>(`/agenda/alunos/${alunoId}/reservas`, { limite: 60 }),
    select: (d) => d.itens.filter((a) => a.status !== "CANCELADA"),
  });
}

export function SeletorAula({ aulas, valor, onChange }: { aulas: AulaDoAluno[]; valor: string; onChange: (v: string) => void }) {
  return (
    <Field label="Aula" dica="A evolução fica registrada na aula escolhida.">
      <NativeSelect value={valor} onChange={(e) => onChange(e.target.value)}>
        {aulas.map((a) => (
          <option key={a.id} value={a.id}>
            {dataBr(a.data)} {a.hora_inicio} · {a.servico} · {a.rotulo_status}
          </option>
        ))}
      </NativeSelect>
    </Field>
  );
}

/** Evolução do aluno (ficha, aba "Evolução"): nova evolução, histórico e exportação em PDF/Excel. */
export function AbaAlunoEvolucao({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const podeEvoluir = pode("aulas.evoluir");
  const aulas = useAulasParaRegistro(alunoId);
  const [escolhida, setEscolhida] = useState("");
  const lista = useQuery({
    queryKey: ["agenda", "aluno-evolucoes", alunoId],
    queryFn: () => api.get<{ itens: Registro[] }>(`/agenda/alunos/${alunoId}/evolucoes`),
  });
  const aulasLista = aulas.data ?? [];
  const reservaId = escolhida || (aulasLista[0] ? String(aulasLista[0].id) : "");

  async function exportar(formato: "pdf" | "xlsx") {
    try {
      await baixar(`/agenda/alunos/${alunoId}/evolucoes/exportar`, { query: { formato } }, `evolucoes-aluno-${alunoId}.${formato}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Não foi possível exportar.");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <HeartPulse className="size-4 text-info-ink" /> Evolução
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

      {podeEvoluir && (
        <div className="card-surface space-y-3 p-4">
          {aulas.isPending ? (
            <Skeleton className="h-24" />
          ) : aulasLista.length === 0 ? (
            <p className="text-sm text-muted-foreground">O aluno ainda não tem aulas para receber uma evolução.</p>
          ) : (
            <>
              <SeletorAula aulas={aulasLista} valor={reservaId} onChange={setEscolhida} />
              <EditorRegistro key={reservaId} tipo="evolucao" reservaId={Number(reservaId)} />
            </>
          )}
        </div>
      )}

      {lista.isPending ? (
        <Skeleton className="h-32 rounded-2xl" />
      ) : (
        <ListaRegistros tipo="evolucao" itens={lista.data?.itens ?? []} podeEditar={podeEvoluir} vazio="Nenhuma evolução registrada para este aluno." />
      )}
    </div>
  );
}
