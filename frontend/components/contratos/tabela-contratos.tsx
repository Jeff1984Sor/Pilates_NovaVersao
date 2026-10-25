"use client";

import Link from "next/link";

import { data, moeda } from "@/lib/format";
import type { ContratoResumo } from "@/lib/tipos-contratos";

import { AcoesContrato } from "./acoes-contrato";
import { AssinaturaPill, SituacaoContratoPill } from "./comum";

export function TabelaContratos({ itens, mostrarAluno = true }: { itens: ContratoResumo[]; mostrarAluno?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-sm">
        <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-4 py-2.5 font-medium">Nº</th>
            {mostrarAluno && <th className="px-3 py-2.5 font-medium">Aluno</th>}
            <th className="px-3 py-2.5 font-medium">Plano</th>
            <th className="px-3 py-2.5 font-medium">Vigência</th>
            <th className="px-3 py-2.5 text-right font-medium">Parcela</th>
            <th className="px-3 py-2.5 text-right font-medium">Total</th>
            <th className="px-3 py-2.5 font-medium">Assinatura</th>
            <th className="px-3 py-2.5 font-medium">Situação</th>
            <th className="w-10 px-2 py-2.5" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {itens.map((c) => (
            <tr key={c.id} className="hover:bg-accent/40">
              <td className="num px-4 py-3 font-medium">
                <Link href={`/contratos/${c.id}`} className="hover:underline">
                  {c.numero}
                </Link>
              </td>
              {mostrarAluno && (
                <td className="px-3 py-3">
                  <Link href={`/alunos/${c.aluno.id}?aba=contratos`} className="font-medium hover:underline">
                    {c.aluno.nome}
                  </Link>
                </td>
              )}
              <td className="px-3 py-3">
                {c.plano.nome}
                <span className="block text-xs text-muted-foreground">
                  {c.unidade.nome} · {c.profissional.nome}
                </span>
              </td>
              <td className="num px-3 py-3 whitespace-nowrap">
                {data(c.data_inicio)} a {data(c.data_fim)}
                <span className="block text-xs text-muted-foreground">
                  {c.aulas_futuras > 0 ? `${c.aulas_futuras} aula(s) agendada(s)` : "sem aulas agendadas"} · {c.parcelas_abertas} parcela(s) em aberto
                </span>
              </td>
              <td className="num px-3 py-3 text-right">{moeda(c.valor_parcela)}</td>
              <td className="num px-3 py-3 text-right">{moeda(c.valor_total)}</td>
              <td className="px-3 py-3">
                <AssinaturaPill status={c.status_assinatura} />
              </td>
              <td className="px-3 py-3">
                <SituacaoContratoPill situacao={c.situacao} />
              </td>
              <td className="px-2 py-3 text-right">
                <AcoesContrato c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
