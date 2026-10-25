"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarClock, Loader2, Search, UserRound, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { data, moeda } from "@/lib/format";
import type { AlunoBusca } from "@/lib/tipos-alunos";
import { FORMAS_PAGAMENTO_CONTRATO, type ContratoCriado, type Precificacao } from "@/lib/tipos-contratos";

import { hojeISO, useInvalidarContratos, useOpcoesContrato } from "./comum";

function SeletorAluno({ valor, onChange }: { valor: { id: number; nome: string } | null; onChange: (a: { id: number; nome: string } | null) => void }) {
  const [q, setQ] = useState("");
  const busca = useDebounce(q, 250);
  const resultados = useQuery({
    queryKey: ["contratos", "busca-aluno", busca],
    queryFn: () => api.get<AlunoBusca[]>("/alunos/busca", { q: busca, limite: 8 }),
    enabled: busca.trim().length >= 2 && !valor,
  });
  if (valor) {
    return (
      <div className="flex items-center justify-between rounded-lg border bg-muted/40 px-3 py-2 text-sm">
        <span className="flex items-center gap-2 font-medium">
          <UserRound className="size-4 text-muted-foreground" /> {valor.nome}
        </span>
        <Button type="button" variant="ghost" size="icon-sm" onClick={() => onChange(null)} aria-label="Trocar aluno">
          <X />
        </Button>
      </div>
    );
  }
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Digite nome, CPF ou telefone do aluno" className="pl-9" autoComplete="off" />
      {busca.trim().length >= 2 && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border bg-popover p-1 shadow-lg" role="listbox">
          {resultados.isFetching && <li className="px-3 py-2 text-sm text-muted-foreground">Buscando…</li>}
          {!resultados.isFetching && (resultados.data ?? []).length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">Nenhum aluno encontrado.</li>}
          {(resultados.data ?? []).map((a) => (
            <li key={a.id}>
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent"
                onClick={() => onChange({ id: a.id, nome: a.nome })}
              >
                <span>
                  {a.nome}
                  {a.status === "INATIVO" && <span className="ml-2 text-xs text-danger">inativo</span>}
                </span>
                <span className="text-xs text-muted-foreground">{a.cpf_mascarado ?? "sem CPF"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Formulário de novo contrato, com os valores (R1) e as parcelas (R2) calculados em tempo real pela API. */
export function FormContrato({ alunoInicial }: { alunoInicial?: { id: number; nome: string } | null }) {
  const router = useRouter();
  const invalidar = useInvalidarContratos();
  const opcoes = useOpcoesContrato();
  const [aluno, setAluno] = useState<{ id: number; nome: string } | null>(alunoInicial ?? null);
  const [plano, setPlano] = useState("");
  const [unidade, setUnidade] = useState("");
  const [prof, setProf] = useState("");
  const [forma, setForma] = useState("PIX");
  const [inicio, setInicio] = useState(hojeISO());
  const [fim, setFim] = useState("");
  const [fimManual, setFimManual] = useState(false);

  const dadosOpc = opcoes.data;
  // com uma única unidade/profissional cadastrado, já vem escolhido (derivado, sem efeito)
  const unidadeSel = unidade || (dadosOpc?.unidades.length === 1 ? String(dadosOpc.unidades[0].id) : "");
  const profSel = prof || (dadosOpc?.profissionais.length === 1 ? String(dadosOpc.profissionais[0].id) : "");

  const debInicio = useDebounce(inicio, 250);
  const debFim = useDebounce(fim, 250);
  const preco = useQuery({
    queryKey: ["contratos", "precificar", plano, debInicio, fimManual ? debFim : ""],
    queryFn: () =>
      api.post<Precificacao>("/contratos/precificar", { plano_id: Number(plano), data_inicio: debInicio, data_fim: fimManual && debFim ? debFim : null }),
    enabled: !!plano && !!debInicio,
    placeholderData: (p) => p,
  });
  // enquanto o usuário não digitou uma data final, vale a sugerida (início + duração do plano)
  const fimSel = fimManual ? fim : (preco.data?.data_fim_sugerida ?? "");

  const criar = useMutation({
    mutationFn: () =>
      api.post<ContratoCriado>("/contratos", {
        aluno_id: aluno!.id,
        plano_id: Number(plano),
        unidade_id: Number(unidadeSel),
        profissional_id: Number(profSel),
        data_inicio: inicio,
        data_fim: fimSel || null,
        forma_pagamento: forma || null,
      }),
    onSuccess: (r) => {
      toast.success(`Contrato nº ${r.contrato.numero} criado com ${r.parcelas_criadas} parcela(s) e PDF gerado.`);
      r.contrato.avisos.forEach((a) => toast.info(a, { duration: 9000 }));
      invalidar();
      router.push(r.proximo_passo === "agenda" ? `/contratos/${r.contrato.id}/agenda?novo=1` : `/contratos/${r.contrato.id}`);
    },
  });

  const p = preco.data;
  return (
    <form
      className="grid gap-6 lg:grid-cols-[1fr_380px]"
      onSubmit={(e) => {
        e.preventDefault();
        if (!aluno) return toast.error("Escolha o aluno.");
        criar.mutate();
      }}
    >
      <div className="card-surface grid gap-4 p-5 sm:grid-cols-2">
        <Field label="Aluno" obrigatorio className="sm:col-span-2">
          <SeletorAluno valor={aluno} onChange={setAluno} />
        </Field>
        <Field label="Plano" obrigatorio className="sm:col-span-2">
          <NativeSelect value={plano} onChange={(e) => setPlano(e.target.value)} required>
            <option value="">Selecione o plano…</option>
            {(dadosOpc?.planos ?? []).map((pl) => (
              <option key={pl.id} value={pl.id}>
                {pl.nome} — {moeda(pl.valor)}/mês · {pl.aulas_por_semana}x/semana · {pl.duracao_meses} mês(es){pl.avulso ? " · avulso" : ""}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Unidade" obrigatorio>
          <NativeSelect value={unidadeSel} onChange={(e) => setUnidade(e.target.value)} required>
            <option value="">Selecione…</option>
            {(dadosOpc?.unidades ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Profissional responsável" obrigatorio>
          <NativeSelect value={profSel} onChange={(e) => setProf(e.target.value)} required>
            <option value="">Selecione…</option>
            {(dadosOpc?.profissionais ?? []).map((pr) => (
              <option key={pr.id} value={pr.id}>
                {pr.nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Início" obrigatorio>
          <Input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} required />
        </Field>
        <Field label="Fim" obrigatorio dica={fimManual ? "Data final escolhida por você." : "Sugerida pela duração do plano; você pode mudar."}>
          <Input
            type="date"
            value={fimSel}
            min={inicio}
            onChange={(e) => {
              setFim(e.target.value);
              setFimManual(true);
            }}
            required
          />
        </Field>
        <Field label="Forma de pagamento">
          <NativeSelect value={forma} onChange={(e) => setForma(e.target.value)}>
            <option value="">Não informar</option>
            {FORMAS_PAGAMENTO_CONTRATO.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="flex items-end justify-end gap-2 sm:col-span-2">
          <Button type="button" variant="outline" onClick={() => router.push("/contratos")}>
            Cancelar
          </Button>
          <Button type="submit" disabled={criar.isPending || !plano || !aluno}>
            {criar.isPending && <Loader2 className="animate-spin" />}
            Criar contrato
          </Button>
        </div>
      </div>

      <aside className="card-surface h-fit space-y-4 p-5" aria-live="polite">
        <h2 className="flex items-center gap-2 font-semibold">
          <CalendarClock className="size-4 text-muted-foreground" /> Valores e parcelas
          {preco.isFetching && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
        </h2>
        {!p ? (
          <p className="text-sm text-muted-foreground">Escolha o plano para ver o valor da aula, da parcela e o total.</p>
        ) : (
          <>
            <dl className="grid grid-cols-3 gap-2 text-center">
              {[
                ["Valor da aula", p.valor_aula ? moeda(p.valor_aula) : "—"],
                ["Parcela mensal", moeda(p.valor_parcela)],
                ["Total", moeda(p.valor_total)],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-muted/50 p-2">
                  <dt className="text-[11px] text-muted-foreground">{k}</dt>
                  <dd className="num text-sm font-semibold">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="text-xs text-muted-foreground">
              {p.aulas_por_semana}x por semana · {p.duracao_meses} mês(es). Aula = mensal ÷ ({p.aulas_por_semana} × 4). Vigência {data(p.data_inicio)} a{" "}
              {data(p.data_fim)}.
            </p>
            <div className="max-h-64 overflow-auto rounded-xl border">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-1.5 font-medium">#</th>
                    <th className="px-3 py-1.5 font-medium">Vencimento</th>
                    <th className="px-3 py-1.5 font-medium">Competência</th>
                    <th className="px-3 py-1.5 text-right font-medium">Valor</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {p.parcelas.map((x) => (
                    <tr key={x.numero}>
                      <td className="num px-3 py-1.5">{x.numero}</td>
                      <td className="num px-3 py-1.5">{data(x.vencimento)}</td>
                      <td className="num px-3 py-1.5 text-muted-foreground">{x.competencia}</td>
                      <td className="num px-3 py-1.5 text-right">{moeda(x.valor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">
              Ao criar: as parcelas entram em Contas a receber e o PDF do contrato fica nos documentos do aluno.
              {!p.avulso && " Em seguida você escolhe os horários das aulas."}
            </p>
          </>
        )}
      </aside>
    </form>
  );
}
