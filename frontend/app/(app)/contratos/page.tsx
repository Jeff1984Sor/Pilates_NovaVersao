"use client";

import { useMutation } from "@tanstack/react-query";
import { Calculator, FileSignature, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ChipsContratos, useInvalidarContratos, useOpcoesContrato } from "@/components/contratos/comum";
import { TabelaContratos } from "@/components/contratos/tabela-contratos";
import { Pagination, SearchInput, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { usePaginado } from "@/hooks/use-paginado";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { moeda } from "@/lib/format";
import type { ChipContrato, ListaContratos, Recalculo } from "@/lib/tipos-contratos";

function RecalcularDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { pode } = useAuth();
  const invalidar = useInvalidarContratos();
  const [somenteVigentes, setSomenteVigentes] = useState(true);
  const [resultado, setResultado] = useState<Recalculo | null>(null);
  const rodar = useMutation({
    mutationFn: (simular: boolean) => api.post<Recalculo>("/contratos/recalcular", { simular, somente_vigentes: somenteVigentes }),
    onSuccess: (r) => {
      setResultado(r);
      if (!r.simulacao) {
        toast.success(`${r.alterados} contrato(s) atualizado(s)`);
        invalidar();
      }
    },
  });
  const podeAplicar = pode("contratos.excluir");
  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setResultado(null);
          onClose();
        }
      }}
      titulo="Recalcular valores dos contratos"
      descricao="Aplica a regra do plano (aula = mensal ÷ aulas por semana × 4; parcela = mensal; total = mensal × meses). Primeiro simule: nada é gravado até você aplicar. As parcelas já geradas não mudam."
      largura="xl"
      rotuloSalvar="Simular"
      salvando={rodar.isPending}
      onSubmit={(e) => {
        e.preventDefault();
        rodar.mutate(true);
      }}
      rodapeExtra={
        podeAplicar && resultado?.simulacao && resultado.alterados > 0 ? (
          <Button type="button" variant="destructive" disabled={rodar.isPending} onClick={() => rodar.mutate(false)}>
            Aplicar em {resultado.alterados} contrato(s)
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={somenteVigentes} onChange={(e) => setSomenteVigentes(e.target.checked)} className="accent-[var(--brand)]" />
          Só contratos que ainda não venceram
        </label>
        {!podeAplicar && <p className="text-xs text-muted-foreground">Você pode simular; aplicar exige a permissão de excluir contratos.</p>}
        {resultado && (
          <div>
            <p className="mb-2 text-sm font-medium">
              {resultado.simulacao ? "Simulação" : "Aplicado"}: {resultado.verificados} verificado(s), {resultado.alterados} com valores diferentes.
            </p>
            {resultado.itens.length > 0 && (
              <div className="max-h-72 overflow-auto rounded-xl border">
                <table className="w-full text-xs">
                  <thead className="bg-muted/40 text-left text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Contrato</th>
                      <th className="px-3 py-2">Aluno</th>
                      <th className="px-3 py-2 text-right">Aula</th>
                      <th className="px-3 py-2 text-right">Parcela</th>
                      <th className="px-3 py-2 text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {resultado.itens.map((i) => (
                      <tr key={i.contrato_id}>
                        <td className="num px-3 py-2">{i.numero}</td>
                        <td className="px-3 py-2">
                          {i.aluno}
                          <span className="block text-muted-foreground">{i.plano}</span>
                        </td>
                        {(["valor_aula", "valor_parcela", "valor_total"] as const).map((k) => (
                          <td key={k} className="num px-3 py-2 text-right">
                            <span className="text-muted-foreground line-through">{i.antes[k] ? moeda(i.antes[k]) : "—"}</span>
                            <br />
                            <b>{i.depois[k] ? moeda(i.depois[k]) : "—"}</b>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </FormDialog>
  );
}

export default function ContratosPage() {
  const { pode } = useAuth();
  const podeVer = pode("contratos.ver");
  const [chip, setChip] = useState<ChipContrato>("ativos");
  const [recalcular, setRecalcular] = useState(false);
  const lista = usePaginado<ListaContratos["itens"][number]>("contratos", "/contratos", { chip }, 25);
  const opcoes = useOpcoesContrato(podeVer);
  if (!podeVer) return <SemAcesso />;

  const dados = lista.data as ListaContratos | undefined;
  const filtros = lista.filtros;

  return (
    <div>
      <PageHeader
        titulo="Contratos"
        descricao="Contratos dos alunos: vigência, assinatura, parcelas e agenda. Vigência calculada pela data de hoje (Brasília)."
        icone={FileSignature}
        migalhas={[{ label: "Início", href: "/" }, { label: "Contratos" }]}
        acoes={
          <>
            {pode("contratos.editar") && (
              <Button variant="outline" onClick={() => setRecalcular(true)}>
                <Calculator /> Recalcular valores
              </Button>
            )}
            {pode("contratos.editar") && (
              <Button render={<Link href="/contratos/novo" />}>
                <Plus /> Novo contrato
              </Button>
            )}
          </>
        }
      />
      <TableCard>
        <ChipsContratos
          contagens={dados?.contagens}
          valor={chip}
          onChange={(v) => {
            setChip(v);
            lista.setFiltro("chip", v);
          }}
        />
        <Toolbar className="sm:flex-wrap sm:justify-start">
          <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Aluno, CPF ou nº do contrato" />
          <NativeSelect
            value={String(filtros.plano_id ?? "")}
            onChange={(e) => lista.setFiltro("plano_id", e.target.value)}
            className="w-48"
            aria-label="Plano"
          >
            <option value="">Todos os planos</option>
            {(opcoes.data?.planos ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
          <Field label="Vigente de" className="flex-row items-center gap-2">
            <Input type="date" value={String(filtros.de ?? "")} onChange={(e) => lista.setFiltro("de", e.target.value)} className="h-9 w-40" />
          </Field>
          <Field label="até" className="flex-row items-center gap-2">
            <Input type="date" value={String(filtros.ate ?? "")} onChange={(e) => lista.setFiltro("ate", e.target.value)} className="h-9 w-40" />
          </Field>
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={7} />
        ) : lista.itens.length === 0 ? (
          <EmptyState
            icone={FileSignature}
            titulo="Nenhum contrato aqui"
            descricao="Ajuste o filtro, o período ou a busca. Para começar, crie um novo contrato."
          />
        ) : (
          <TabelaContratos itens={lista.itens} />
        )}
        <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />
      </TableCard>
      {recalcular && <RecalcularDialog open onClose={() => setRecalcular(false)} />}
    </div>
  );
}
