"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, CircleCheck, CirclePlus, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { TableCard, TableSkeleton } from "@/components/mayacorp/data-table";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda } from "@/lib/format";
import type { PaginaReceber, ResumoAluno } from "@/lib/tipos-financeiro";

import { BotoesExportar, Resumo, SituacaoChips } from "./comum";
import { RecibosSaudeAluno } from "./recibos-saude-aluno";
import { AvulsoDialog, TabelaContasReceber } from "./tabela-receber";

/**
 * Aba "Financeiro" da ficha do aluno: faturas (com chips de situação, baixa, recibo, avulso, exportação) e o bloco
 * "Recibos do Receita Saúde". Uso: `<AbaAlunoFinanceiro alunoId={aluno.id} />`.
 */
export function AbaAlunoFinanceiro({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const [situacao, setSituacao] = useState("");
  const [avulso, setAvulso] = useState(false);
  const podeVer = pode("financeiro_receber.ver");

  const lista = useQuery({
    queryKey: ["fin", "aba-aluno", alunoId, situacao],
    queryFn: () => api.get<PaginaReceber>("/financeiro/receber", { aluno_id: alunoId, situacao, por_pagina: 200 }),
    enabled: podeVer,
    placeholderData: (p) => p,
  });
  const resumo = useQuery({
    queryKey: ["fin", "resumo-aluno", alunoId],
    queryFn: () => api.get<ResumoAluno>(`/financeiro/receber/aluno/${alunoId}/resumo`),
    enabled: podeVer,
  });

  if (!podeVer) return pode("receita_saude.ver") ? <RecibosSaudeAluno alunoId={alunoId} /> : null;
  const r = resumo.data;
  const itens = lista.data?.itens ?? [];

  return (
    <div>
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Resumo rotulo="Em atraso" valor={moeda(r?.total_atrasado)} tom={r && r.qtd_atrasado > 0 ? "danger" : undefined} sub={`${r?.qtd_atrasado ?? 0} fatura(s)`} />
        <Resumo rotulo="A vencer" valor={moeda(r?.total_aberto)} sub={r?.proximo_vencimento ? `Próximo: ${data(r.proximo_vencimento)}` : "Nada a vencer"} />
        <Resumo rotulo="Pago" valor={moeda(r?.total_pago)} tom="success" sub={`${r?.qtd_pago ?? 0} fatura(s)`} />
        <div className="card-surface flex items-center gap-3 p-4">
          {r?.em_dia ? <CircleCheck className="size-8 text-success" /> : <TriangleAlert className="size-8 text-danger" />}
          <div>
            <p className="text-sm font-semibold">{r ? (r.em_dia ? "Em dia" : "Com pendência") : "—"}</p>
            <p className="text-xs text-muted-foreground">
              <CalendarClock className="mr-1 inline size-3" />
              situação financeira
            </p>
          </div>
        </div>
      </div>

      <TableCard>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
          <h3 className="px-1 font-semibold">Faturas</h3>
          <div className="flex flex-wrap items-center gap-2">
            <BotoesExportar caminho="/financeiro/receber/exportar" query={{ aluno_id: alunoId, situacao }} nome={`faturas-aluno-${alunoId}`} />
            {pode("financeiro_receber.editar") && (
              <Button size="sm" onClick={() => setAvulso(true)}>
                <CirclePlus /> Lançar valor avulso
              </Button>
            )}
          </div>
        </div>
        <SituacaoChips chips={lista.data?.chips} valor={situacao} onChange={setSituacao} />
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : itens.length === 0 ? (
          <EmptyState icone={CalendarClock} titulo="Nenhuma fatura" descricao="As parcelas do contrato e os lançamentos avulsos aparecem aqui." />
        ) : (
          <TabelaContasReceber itens={itens} mostrarAluno={false} />
        )}
      </TableCard>

      <RecibosSaudeAluno alunoId={alunoId} />
      <AvulsoDialog alunoId={alunoId} open={avulso} onClose={() => setAvulso(false)} />
    </div>
  );
}
