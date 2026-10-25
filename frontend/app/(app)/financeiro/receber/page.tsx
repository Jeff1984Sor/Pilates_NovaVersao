"use client";

import { ReceiptText } from "lucide-react";

import { BotoesExportar, CampoPeriodo, SituacaoChips, useOpcoesReceber } from "@/components/financeiro/comum";
import { TabelaContasReceber } from "@/components/financeiro/tabela-receber";
import { Pagination, SearchInput, TableCard, TableSkeleton, Toolbar } from "@/components/mayacorp/data-table";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Input } from "@/components/ui/input";
import { usePaginado } from "@/hooks/use-paginado";
import { useAuth } from "@/lib/auth";
import type { ContaReceber, PaginaReceber } from "@/lib/tipos-financeiro";

export default function ContasReceberPage() {
  const { pode } = useAuth();
  const podeVer = pode("financeiro_receber.ver");
  const lista = usePaginado<ContaReceber>("fin", "/financeiro/receber", {}, 25);
  const opcoes = useOpcoesReceber();
  const dados = lista.data as PaginaReceber | undefined;
  if (!podeVer) return <SemAcesso />;

  const filtros = lista.filtros;
  const query = { ...filtros, q: lista.q };
  const itens = lista.itens;

  return (
    <div>
      <PageHeader
        titulo="Contas a receber"
        descricao="Cobranças de contratos, aulas avulsas e lançamentos avulsos. Atrasado é calculado pela data de hoje (Brasília)."
        icone={ReceiptText}
        migalhas={[{ label: "Início", href: "/" }, { label: "Financeiro" }, { label: "Contas a receber" }]}
        acoes={pode("financeiro_receber.ver") && <BotoesExportar caminho="/financeiro/receber/exportar" query={query} nome="contas-a-receber" />}
      />
      <TableCard>
        <SituacaoChips chips={dados?.chips} valor={String(filtros.situacao ?? "")} onChange={(v) => lista.setFiltro("situacao", v)} />
        <Toolbar className="sm:flex-wrap sm:justify-start">
          <SearchInput value={lista.q} onChange={lista.setQ} placeholder="Aluno, descrição ou plano" />
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
          <Input
            type="month"
            aria-label="Competência"
            value={String(filtros.competencia ?? "")}
            onChange={(e) => lista.setFiltro("competencia", e.target.value)}
            className="h-9 w-40"
          />
          <CampoPeriodo
            de={String(filtros.de ?? "")}
            ate={String(filtros.ate ?? "")}
            rotuloDe="Vencimento de"
            onChange={(d, a) => {
              lista.setFiltro("de", d);
              lista.setFiltro("ate", a);
            }}
          />
        </Toolbar>
        {lista.isPending ? (
          <TableSkeleton colunas={6} />
        ) : itens.length === 0 ? (
          <EmptyState icone={ReceiptText} titulo="Nenhuma cobrança encontrada" descricao="Ajuste a situação, o período ou a busca." />
        ) : (
          <TabelaContasReceber itens={itens} />
        )}
        <Pagination pagina={lista.pagina} porPagina={lista.porPagina} total={lista.total} onChange={lista.setPagina} />
      </TableCard>
    </div>
  );
}
