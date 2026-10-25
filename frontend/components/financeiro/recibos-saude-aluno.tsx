"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, HeartPulse, Unlock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/mayacorp/form";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ApiError, api, baixar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, documento, moeda } from "@/lib/format";
import type { RecibosAluno } from "@/lib/tipos-financeiro";
import { cpfValido, soDigitos } from "@/lib/validacao";

import { useInvalidarFinanceiro } from "./comum";

/** Bloco "Recibos do Receita Saúde" da ficha do aluno: marcar pagamentos, CPF do pagador, gerar e liberar. */
export function RecibosSaudeAluno({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const invalidar = useInvalidarFinanceiro();
  const podeVer = pode("receita_saude.ver");
  const podeGerar = pode("receita_saude.gerar");
  const chave = ["fin", "recibos-saude", alunoId];
  const q = useQuery({
    queryKey: chave,
    queryFn: () => api.get<RecibosAluno>(`/receita-saude/alunos/${alunoId}`),
    enabled: podeVer,
  });
  const [marcados, setMarcados] = useState<number[]>([]);
  const [pagador, setPagador] = useState<string | null>(null);
  const [erros, setErros] = useState<string[]>([]);
  const r = q.data;
  const cpfPagador = pagador ?? r?.cpf_pagador_recibo ?? "";

  const salvarPagador = useMutation({
    mutationFn: () => api.put<RecibosAluno>(`/receita-saude/alunos/${alunoId}/pagador`, { cpf: soDigitos(cpfPagador) || null }),
    onSuccess: () => {
      toast.success(soDigitos(cpfPagador) ? "CPF do pagador salvo" : "O pagador voltou a ser o próprio aluno");
      setPagador(null);
      invalidar();
    },
  });
  const gerar = useMutation({
    mutationFn: async () => {
      setErros([]);
      await baixar(`/receita-saude/alunos/${alunoId}/arquivo`, { method: "POST", body: { conta_ids: marcados }, headers: {} }, "receita-saude.csv");
    },
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Arquivo gerado. Importe no e-CAC (veja o passo a passo em Receita Saúde).");
      setMarcados([]);
      invalidar();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.body && typeof e.body === "object" && "erros" in e.body) setErros((e.body as { erros: string[] }).erros);
      else setErros([e.message]);
    },
  });
  const liberar = useMutation({
    mutationFn: () => api.post(`/receita-saude/alunos/${alunoId}/liberar`, { conta_ids: marcados }),
    onSuccess: () => {
      toast.success("Liberado para gerar o arquivo de novo");
      setMarcados([]);
      invalidar();
    },
  });

  if (!podeVer) return null;
  const itens = r?.itens ?? [];
  const selecionados = itens.filter((i) => marcados.includes(i.conta_id));
  const algumJaGerado = selecionados.some((i) => i.gerado_em);
  const alternar = (id: number) => setMarcados((m) => (m.includes(id) ? m.filter((x) => x !== id) : [...m, id]));
  const pagadorInvalido = !!soDigitos(cpfPagador) && !cpfValido(cpfPagador);

  return (
    <section className="card-surface mt-6 overflow-hidden" aria-label="Recibos do Receita Saúde">
      <header className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
        <div className="grid size-8 place-items-center rounded-lg bg-brand/10 text-navy dark:text-brand">
          <HeartPulse className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold">Recibos do Receita Saúde</h3>
          <p className="text-xs text-muted-foreground">Marque os pagamentos, gere o arquivo e importe no e-CAC (Carnê-Leão &gt; Escrituração &gt; Importar).</p>
        </div>
        {podeGerar && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={marcados.length === 0 || algumJaGerado || gerar.isPending} onClick={() => gerar.mutate()}>
              <Download /> Gerar arquivo{marcados.length > 0 && ` (${marcados.length})`}
            </Button>
            <Button size="sm" variant="outline" disabled={!algumJaGerado || liberar.isPending} onClick={() => liberar.mutate()}>
              <Unlock /> Liberar para refazer
            </Button>
          </div>
        )}
      </header>

      {r && !r.config_ok && (
        <div className="flex items-start gap-2 border-b bg-warning/10 px-4 py-3 text-sm text-warning-ink">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div>
            {r.problemas_config.map((p) => (
              <p key={p}>{p}</p>
            ))}
            <Link href="/receita-saude" className="underline">
              Configurar o profissional
            </Link>
          </div>
        </div>
      )}
      {erros.length > 0 && (
        <div className="border-b bg-danger/8 px-4 py-3 text-sm text-danger-ink" role="alert">
          <p className="font-medium">O arquivo não foi gerado (tudo ou nada):</p>
          <ul className="mt-1 list-disc pl-5">
            {erros.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-3 border-b p-4 sm:grid-cols-[1fr_auto] sm:items-end">
        <Field
          label="CPF do pagador"
          erro={pagadorInvalido ? "CPF inválido" : undefined}
          dica={
            r?.sem_cpf
              ? "Aluno sem CPF: o recibo exige o CPF do beneficiário."
              : `Em branco = o próprio aluno (${documento(r?.aluno_cpf)}). Informe só quando outra pessoa paga.`
          }
        >
          <Input
            value={cpfPagador}
            onChange={(e) => setPagador(e.target.value)}
            inputMode="numeric"
            placeholder="000.000.000-00"
            disabled={!podeGerar}
          />
        </Field>
        {podeGerar && (
          <Button variant="outline" size="sm" disabled={pagadorInvalido || salvarPagador.isPending || pagador === null} onClick={() => salvarPagador.mutate()}>
            Salvar pagador
          </Button>
        )}
      </div>

      {q.isPending ? (
        <p className="p-4 text-sm text-muted-foreground">Carregando…</p>
      ) : itens.length === 0 ? (
        <p className="p-6 text-center text-sm text-muted-foreground">Nenhum pagamento recebido ainda. Só contas pagas entram no Receita Saúde.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="w-10 px-4 py-2.5" />
                <th className="px-3 py-2.5 font-medium">Pagamento</th>
                <th className="px-3 py-2.5 font-medium">Competência</th>
                <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                <th className="px-3 py-2.5 font-medium">Situação do recibo</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {itens.map((i) => (
                <tr key={i.conta_id} className="hover:bg-accent/40">
                  <td className="px-4 py-3">
                    <Checkbox
                      checked={marcados.includes(i.conta_id)}
                      onCheckedChange={() => alternar(i.conta_id)}
                      disabled={!podeGerar || (i.problemas.length > 0 && !i.gerado_em)}
                      aria-label={`Marcar pagamento de ${data(i.pagamento)}`}
                    />
                  </td>
                  <td className="px-3 py-3 num">{data(i.pagamento)}</td>
                  <td className="px-3 py-3 text-muted-foreground num">{i.competencia ?? "—"}</td>
                  <td className="px-3 py-3 text-right font-medium num">{moeda(i.valor)}</td>
                  <td className="px-3 py-3">
                    {i.gerado_em ? (
                      <Pill tom="info">Arquivo gerado em {data(i.gerado_em)}</Pill>
                    ) : i.problemas.length > 0 ? (
                      <span className="text-xs text-danger-ink">{i.problemas.join(" · ")}</span>
                    ) : (
                      <Pill tom="success">Pronto para gerar</Pill>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
