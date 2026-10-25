"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { BadgeCheck, Calculator, Percent, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { BotoesExportar, CampoMes, hojeISO, mesAtualISO, nomeMes, Resumo, useInvalidarFinanceiro } from "@/components/financeiro/comum";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, moeda } from "@/lib/format";
import type { Comissoes } from "@/lib/tipos-financeiro";

export default function ComissoesPage() {
  const { pode } = useAuth();
  const invalidar = useInvalidarFinanceiro();
  const podeVer = pode("comissoes.ver");
  const podeEditar = pode("comissoes.editar");
  const [mes, setMes] = useState(mesAtualISO());
  const [situacao, setSituacao] = useState("");
  const [marcadas, setMarcadas] = useState<number[]>([]);
  const params = { competencia: mes, situacao: situacao || undefined };
  const q = useQuery({
    queryKey: ["fin", "comissoes", params],
    queryFn: () => api.get<Comissoes>("/comissoes", params),
    enabled: podeVer,
    placeholderData: (p) => p,
  });
  const gerar = useMutation({
    mutationFn: () => api.post<{ geradas: number; valor_total: string }>("/comissoes/gerar", { competencia: mes }),
    onSuccess: (r) => {
      toast.success(r.geradas ? `${r.geradas} comissão(ões) gerada(s): ${moeda(r.valor_total)}` : "Nenhuma comissão nova para gerar neste mês");
      invalidar();
    },
  });
  const pagar = useMutation({
    mutationFn: () => api.post("/comissoes/pagar", { comissao_ids: marcadas, data_pagamento: hojeISO() }),
    onSuccess: () => {
      toast.success("Marcadas como pagas");
      setMarcadas([]);
      invalidar();
    },
  });
  const desfazer = useMutation({
    mutationFn: (id: number) => api.post(`/comissoes/${id}/desfazer-pagamento`),
    onSuccess: () => {
      toast.success("Pagamento desfeito");
      invalidar();
    },
  });
  const excluir = useMutation({
    mutationFn: (id: number) => api.del(`/comissoes/${id}`),
    onSuccess: () => {
      toast.success("Comissão excluída");
      invalidar();
    },
  });
  if (!podeVer) return <SemAcesso />;
  const d = q.data;
  const pendentesMarcadas = (d?.itens ?? []).filter((i) => marcadas.includes(i.id) && !i.paga_em);

  return (
    <div>
      <PageHeader
        titulo="Comissões"
        descricao="Percentual do cadastro do profissional sobre as contas pagas no mês (contrato ou aula do profissional)."
        icone={Percent}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "Comissões" }]}
        acoes={<BotoesExportar caminho="/comissoes/exportar" query={params} nome={`comissoes-${mes}`} />}
      />
      <div className="card-surface mb-5 flex flex-wrap items-end gap-3 p-4">
        <CampoMes valor={mes} onChange={(v) => { setMes(v); setMarcadas([]); }} rotulo="Competência" />
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Situação
          <NativeSelect value={situacao} onChange={(e) => setSituacao(e.target.value)} className="w-40">
            <option value="">Todas</option>
            <option value="PENDENTE">Pendentes</option>
            <option value="PAGA">Pagas</option>
          </NativeSelect>
        </label>
        {podeEditar && (
          <div className="ml-auto flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => gerar.mutate()} disabled={gerar.isPending}>
              <Calculator /> Gerar comissões de {nomeMes(mes)}
            </Button>
            <Button disabled={pendentesMarcadas.length === 0 || pagar.isPending} onClick={() => pagar.mutate()}>
              <BadgeCheck /> Marcar como paga{pendentesMarcadas.length > 0 && ` (${pendentesMarcadas.length})`}
            </Button>
          </div>
        )}
      </div>

      {q.isPending || !d ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Resumo rotulo="Total de comissões" valor={moeda(d.valor_total)} />
            <Resumo rotulo="A pagar" valor={moeda(d.valor_pendente)} tom={Number(d.valor_pendente) > 0 ? "danger" : undefined} />
            {d.resumo.slice(0, 2).map((r) => (
              <Resumo key={r.profissional_id} rotulo={r.profissional_nome} valor={moeda(r.valor_total)} sub={`${r.quantidade} conta(s) · pendente ${moeda(r.valor_pendente)}`} />
            ))}
          </div>
          <section className="card-surface overflow-hidden" aria-label="Comissões">
            {d.itens.length === 0 ? (
              <EmptyState
                icone={Percent}
                titulo="Nenhuma comissão neste mês"
                descricao="Clique em “Gerar comissões” para calcular sobre as contas pagas. O percentual vem do cadastro do profissional."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="w-10 px-4 py-2.5" />
                      <th className="px-3 py-2.5 font-medium">Profissional</th>
                      <th className="px-3 py-2.5 font-medium">Aluno</th>
                      <th className="px-3 py-2.5 text-right font-medium">Base</th>
                      <th className="px-3 py-2.5 text-right font-medium">%</th>
                      <th className="px-3 py-2.5 text-right font-medium">Comissão</th>
                      <th className="px-3 py-2.5 font-medium">Situação</th>
                      <th className="w-20" />
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {d.itens.map((i) => (
                      <tr key={i.id} className="hover:bg-accent/40">
                        <td className="px-4 py-3">
                          <Checkbox
                            checked={marcadas.includes(i.id)}
                            disabled={!podeEditar || !!i.paga_em}
                            onCheckedChange={() => setMarcadas((m) => (m.includes(i.id) ? m.filter((x) => x !== i.id) : [...m, i.id]))}
                            aria-label="Selecionar comissão"
                          />
                        </td>
                        <td className="px-3 py-3 font-medium">{i.profissional_nome}</td>
                        <td className="px-3 py-3 text-muted-foreground">{i.aluno_nome}</td>
                        <td className="px-3 py-3 text-right num">{moeda(i.valor_base)}</td>
                        <td className="px-3 py-3 text-right num">{Number(i.percentual).toLocaleString("pt-BR")}%</td>
                        <td className="px-3 py-3 text-right font-semibold num">{moeda(i.valor)}</td>
                        <td className="px-3 py-3">{i.paga_em ? <Pill tom="success">Paga em {data(i.paga_em)}</Pill> : <Pill tom="warning">Pendente</Pill>}</td>
                        <td className="px-3 py-3">
                          {podeEditar && (
                            <div className="flex justify-end">
                              {i.paga_em ? (
                                <Button variant="ghost" size="icon-sm" aria-label="Desfazer pagamento" onClick={() => desfazer.mutate(i.id)}>
                                  <Undo2 />
                                </Button>
                              ) : (
                                <Button variant="ghost" size="icon-sm" aria-label="Excluir comissão" onClick={() => excluir.mutate(i.id)}>
                                  <Trash2 />
                                </Button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
