"use client";

import { useQuery } from "@tanstack/react-query";
import { FileSignature, Plus } from "lucide-react";
import Link from "next/link";

import { TableCard, TableSkeleton } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ListaContratos } from "@/lib/tipos-contratos";

import { TabelaContratos } from "./tabela-contratos";

/**
 * Aba "Contratos" da ficha do aluno: contratos com situação, assinatura e ações (novo, PDF, enviar, assinar na recepção,
 * agenda, editar, renovar, encerrar, excluir). Uso: `<AbaAlunoContratos alunoId={aluno.id} />`.
 */
export function AbaAlunoContratos({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const podeVer = pode("contratos.ver");
  const lista = useQuery({
    queryKey: ["contratos", "aba-aluno", alunoId],
    queryFn: () => api.get<ListaContratos>("/contratos", { aluno_id: alunoId, chip: "todos", por_pagina: 100 }),
    enabled: podeVer,
  });
  if (!podeVer) return <SemAcesso titulo="Contratos" />;
  const itens = lista.data?.itens ?? [];
  return (
    <TableCard>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <h3 className="px-1 font-semibold">Contratos</h3>
        {pode("contratos.editar") && (
          <Button size="sm" render={<Link href={`/contratos/novo?aluno_id=${alunoId}`} />}>
            <Plus /> Novo contrato
          </Button>
        )}
      </div>
      {lista.isPending ? (
        <TableSkeleton colunas={6} />
      ) : itens.length === 0 ? (
        <EmptyState icone={FileSignature} titulo="Nenhum contrato" descricao="Crie o primeiro contrato deste aluno: valores, parcelas e PDF saem juntos." />
      ) : (
        <TabelaContratos itens={itens} mostrarAluno={false} />
      )}
    </TableCard>
  );
}
