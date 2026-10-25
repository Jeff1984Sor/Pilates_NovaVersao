"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, FileSignature, FileText, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AcoesContrato } from "@/components/contratos/acoes-contrato";
import { AssinaturaPill, rotuloForma, SituacaoContratoPill } from "@/components/contratos/comum";
import { TableCard } from "@/components/mayacorp/data-table";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Pill } from "@/components/mayacorp/status-badge";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { abrirArquivo, API_URL, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { data, dataHora, moeda } from "@/lib/format";
import type { ContratoDetalhe } from "@/lib/tipos-contratos";

const TOM_PARCELA: Record<string, "brand" | "success" | "danger" | "neutral"> = { ABERTO: "brand", PAGO: "success", ATRASADO: "danger", CANCELADO: "neutral" };
const ROTULO_PARCELA: Record<string, string> = { ABERTO: "Aberta", PAGO: "Paga", ATRASADO: "Atrasada", CANCELADO: "Cancelada" };

function Info({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="mt-0.5 text-sm font-medium">{children}</dd>
    </div>
  );
}

export default function ContratoPage() {
  const { pode } = useAuth();
  const id = Number(useParams<{ id: string }>().id);
  const q = useQuery({ queryKey: ["contratos", "detalhe", id], queryFn: () => api.get<ContratoDetalhe>(`/contratos/${id}`), enabled: pode("contratos.ver") });
  if (!pode("contratos.ver")) return <SemAcesso />;
  const c = q.data;
  if (!c) return <Skeleton className="h-64 w-full rounded-2xl" />;

  return (
    <div className="max-w-5xl">
      <PageHeader
        icone={FileSignature}
        titulo={`Contrato nº ${c.numero}`}
        descricao={
          <span className="flex flex-wrap items-center gap-2">
            <Link href={`/alunos/${c.aluno.id}?aba=contratos`} className="font-medium hover:underline">
              {c.aluno.nome}
            </Link>
            <SituacaoContratoPill situacao={c.situacao} />
            <AssinaturaPill status={c.status_assinatura} />
          </span>
        }
        migalhas={[{ label: "Contratos", href: "/contratos" }, { label: `Nº ${c.numero}` }]}
        acoes={
          <>
            <Button variant="outline" onClick={() => abrirArquivo(`/contratos/${c.id}/pdf`)}>
              <FileText /> Ver PDF
            </Button>
            <AcoesContrato c={c} mostrarVer={false} />
          </>
        }
      />

      {c.avisos.map((a) => (
        <p key={a} className="mb-3 flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" /> {a}
        </p>
      ))}
      {c.precisa_agenda && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand/40 bg-brand/8 p-4">
          <p className="text-sm">
            Este contrato ainda <b>não tem aulas na agenda</b>. Escolha {c.aulas_por_semana} horário(s) por semana para reservar as aulas.
          </p>
          {pode("agenda.ver") && (
            <Button render={<Link href={`/contratos/${c.id}/agenda`} />}>
              <CalendarPlus /> Escolher agenda
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card-surface p-5">
          <h2 className="mb-3 font-semibold">Contrato</h2>
          <dl className="grid grid-cols-2 gap-4">
            <Info rotulo="Plano">{c.plano.nome}</Info>
            <Info rotulo="Aulas por semana">{c.avulso ? "Avulso" : c.aulas_por_semana}</Info>
            <Info rotulo="Vigência">
              {data(c.data_inicio)} a {data(c.data_fim)}
            </Info>
            <Info rotulo="Dias restantes">{c.situacao.dias_restantes < 0 ? "Encerrado" : c.situacao.dias_restantes}</Info>
            <Info rotulo="Unidade">{c.unidade.nome}</Info>
            <Info rotulo="Profissional">{c.profissional.nome}</Info>
            <Info rotulo="Forma de pagamento">{rotuloForma(c.forma_pagamento)}</Info>
            <Info rotulo="Aulas agendadas">{c.aulas_futuras}</Info>
            <Info rotulo="Contato do aluno">
              {c.aluno_email ?? "sem e-mail"} · {c.aluno_telefone || "sem telefone"}
            </Info>
          </dl>
        </section>
        <section className="card-surface p-5">
          <h2 className="mb-3 font-semibold">Valores</h2>
          <dl className="grid grid-cols-3 gap-3">
            <Info rotulo="Valor da aula">{c.valor_aula ? moeda(c.valor_aula) : "—"}</Info>
            <Info rotulo="Parcela mensal">{moeda(c.valor_parcela)}</Info>
            <Info rotulo="Total">{moeda(c.valor_total)}</Info>
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">
            Valor do plano hoje: {moeda(c.valor_do_plano)}/mês.{" "}
            {c.valores_divergem_do_plano ? "Os valores do contrato são diferentes dos do plano (edite para recalcular)." : "Os valores seguem o plano."}
          </p>
          <h2 className="mt-5 mb-2 font-semibold">Assinatura</h2>
          {c.status_assinatura === "NAO_ASSINADO" ? (
            <p className="text-sm text-muted-foreground">Ainda não assinado. Envie o link por e-mail/WhatsApp ou colha a assinatura na recepção (menu ⋯).</p>
          ) : (
            <div className="flex flex-wrap items-center gap-4">
              {c.assinatura.imagem_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={`${API_URL}${c.assinatura.imagem_url}`} alt="Assinatura" className="h-16 rounded-lg border bg-white p-1" />
              )}
              <div className="text-sm">
                <p className="font-medium">{c.assinatura.nome}</p>
                <p className="text-xs text-muted-foreground">
                  CPF {c.assinatura.documento} · {dataHora(c.assinatura.assinado_em)} · IP {c.assinatura.ip ?? "—"}
                </p>
              </div>
            </div>
          )}
        </section>
      </div>

      <TableCard className="mt-4">
        <div className="border-b px-4 py-3">
          <h2 className="font-semibold">Parcelas</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Vencimento</th>
                <th className="px-3 py-2.5 font-medium">Competência</th>
                <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                <th className="px-3 py-2.5 font-medium">Situação</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {c.parcelas.map((p) => (
                <tr key={p.id}>
                  <td className="num px-4 py-2.5">{data(p.vencimento)}</td>
                  <td className="num px-3 py-2.5 text-muted-foreground">{p.competencia ?? "—"}</td>
                  <td className="num px-3 py-2.5 text-right">{moeda(p.valor)}</td>
                  <td className="px-3 py-2.5">
                    <Pill tom={TOM_PARCELA[p.situacao] ?? "neutral"}>{ROTULO_PARCELA[p.situacao] ?? p.situacao}</Pill>
                  </td>
                </tr>
              ))}
              {c.parcelas.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-muted-foreground">
                    Nenhuma parcela.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </TableCard>
    </div>
  );
}
