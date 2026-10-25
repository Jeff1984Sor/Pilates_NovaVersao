"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BellRing,
  Cake,
  CalendarCheck,
  CalendarClock,
  CalendarDays,
  CircleCheckBig,
  FileClock,
  Hourglass,
  LayoutDashboard,
  Medal,
  RefreshCw,
  Rocket,
  UsersRound,
  Wallet,
  WalletCards,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useBrand } from "@/lib/brand";
import { moeda, numero } from "@/lib/format";
import type { ResumoPainel } from "@/lib/tipos-painel";

import { GraficoAulasPorMes } from "./graficos-painel";
import {
  ItemAlerta,
  KpiPainel,
  LinhaAniversariante,
  LinhasEsqueleto,
  ListaPassos,
  Secao,
  SeloStatusAula,
  Vazio,
  VariacaoRecebido,
} from "./blocos";

const ATUALIZA_A_CADA_MS = 60_000;

function saudacao(hora: number) {
  return hora < 12 ? "Bom dia" : hora < 18 ? "Boa tarde" : "Boa noite";
}

function dataPorExtenso(iso: string | undefined) {
  const d = iso ? new Date(`${iso}T00:00:00`) : new Date();
  const t = d.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function PainelResumo() {
  const { usuario, pode, somenteProprias, carregando: carregandoAuth } = useAuth();
  const { nome_exibicao } = useBrand();
  const router = useRouter();

  // Professor não usa o painel: vai direto para as aulas dele (como no sistema antigo)
  useEffect(() => {
    if (somenteProprias) router.replace("/agenda/aulas");
  }, [somenteProprias, router]);

  const liberado = pode("painel.ver") && !somenteProprias;
  const q = useQuery({
    queryKey: ["painel", "resumo"],
    queryFn: () => api.get<ResumoPainel>("/painel/resumo"),
    enabled: liberado,
    refetchInterval: ATUALIZA_A_CADA_MS,
    refetchOnWindowFocus: true,
    placeholderData: (anterior) => anterior,
  });

  if (carregandoAuth || somenteProprias) return <Skeleton className="h-40 w-full" />;
  if (!pode("painel.ver")) return <SemAcesso />;

  const r = q.data;
  const carregando = q.isPending;
  const primeiroNome = usuario?.nome.split(" ")[0] ?? "";
  const hora = new Date().getHours();
  const atualizadoEm = q.dataUpdatedAt
    ? new Date(q.dataUpdatedAt).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div>
      <PageHeader
        titulo={`${saudacao(hora)}, ${primeiroNome}`}
        descricao={`${dataPorExtenso(r?.hoje)} · ${nome_exibicao}`}
        icone={LayoutDashboard}
        migalhas={[{ label: "Início", href: "/" }, { label: "Painel" }]}
        acoes={
          <>
            {atualizadoEm && <span className="text-xs text-muted-foreground">Atualizado às {atualizadoEm}</span>}
            <Button variant="outline" size="sm" onClick={() => q.refetch()} disabled={q.isFetching}>
              <RefreshCw className={q.isFetching ? "animate-spin" : ""} />
              Atualizar
            </Button>
          </>
        }
      />

      {q.isError && !r && (
        <div className="card-surface mb-6 flex flex-wrap items-center justify-between gap-3 p-5">
          <p className="text-sm">Não foi possível carregar o painel agora.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}

      {r?.primeiros_passos.visivel && !r.primeiros_passos.completo && (
        <Secao
          titulo="Primeiros passos"
          descricao="Deixe o estúdio pronto para o primeiro aluno. Esta lista some quando o básico estiver cadastrado."
          acao={<Rocket className="size-5 text-brand" />}
          className="mb-6"
        >
          <ListaPassos passos={r.primeiros_passos.passos} />
        </Secao>
      )}

      <Kpis r={r} carregando={carregando} />

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        {(carregando || r?.aulas_por_mes.visivel) && (
          <Secao
            titulo="Aulas por mês"
            descricao="Últimos 6 meses, sem as aulas canceladas"
            className="xl:col-span-2"
            acao={r && <span className="text-xs text-muted-foreground num">{numero(r.aulas_por_mes.total)} no período</span>}
          >
            {carregando || !r ? (
              <Skeleton className="h-64 w-full" />
            ) : r.aulas_por_mes.total === 0 ? (
              <Vazio icone={CalendarDays} texto="Ainda não há aulas no período" dica="Quando as aulas forem agendadas, o gráfico aparece aqui." />
            ) : (
              <GraficoAulasPorMes meses={r.aulas_por_mes.meses} />
            )}
          </Secao>
        )}
        {(carregando || r?.alertas.visivel) && (
          <Secao titulo="Alertas" descricao="O que precisa da sua atenção" acao={<BellRing className="size-4 text-muted-foreground" />}>
            {carregando || !r ? (
              <LinhasEsqueleto n={3} />
            ) : r.alertas.itens.length === 0 ? (
              <Vazio icone={CircleCheckBig} texto="Tudo em dia" dica="Nenhuma pendência no momento." />
            ) : (
              <div className="space-y-2">
                {r.alertas.itens.map((a) => (
                  <ItemAlerta key={a.chave} a={a} />
                ))}
              </div>
            )}
          </Secao>
        )}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {(carregando || r?.proximas_aulas.visivel) && (
          <Secao
            titulo="Próximas aulas de hoje"
            acao={
              r?.proximas_aulas.href && (
                <Link href={r.proximas_aulas.href} className="text-xs font-medium text-navy hover:underline dark:text-brand">
                  Ver todas
                </Link>
              )
            }
          >
            {carregando || !r ? (
              <LinhasEsqueleto />
            ) : r.proximas_aulas.itens.length === 0 ? (
              <Vazio icone={CalendarClock} texto="Sem mais aulas hoje" dica="As aulas que ainda vão acontecer hoje aparecem aqui." />
            ) : (
              <ul className="divide-y">
                {r.proximas_aulas.itens.map((a) => (
                  <li key={a.reserva_id} className="flex items-center gap-3 py-2">
                    <span className="w-12 shrink-0 text-sm font-semibold num">{a.hora}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{a.aluno ?? "Aluno reservado"}</span>
                      <span className="block truncate text-xs text-muted-foreground">{a.professor ?? "Sem profissional"}</span>
                    </span>
                    <SeloStatusAula status={a.status} />
                  </li>
                ))}
                {r.proximas_aulas.restantes > 0 && (
                  <li className="pt-2 text-xs text-muted-foreground">+ {r.proximas_aulas.restantes} aulas depois destas</li>
                )}
              </ul>
            )}
          </Secao>
        )}
        {(carregando || r?.ranking_professores.visivel) && (
          <Secao titulo="Professores no mês" descricao="Aulas do mês por profissional">
            {carregando || !r ? (
              <LinhasEsqueleto />
            ) : r.ranking_professores.itens.length === 0 ? (
              <Vazio icone={Medal} texto="Sem aulas neste mês" dica="O ranking aparece quando houver aulas no mês." />
            ) : (
              <RankingProfessores itens={r.ranking_professores.itens} />
            )}
          </Secao>
        )}
        {(carregando || r?.aniversariantes.visivel) && (
          <Secao titulo="Aniversariantes" descricao="Hoje e nos próximos 7 dias" acao={<Cake className="size-4 text-muted-foreground" />}>
            {carregando || !r ? (
              <LinhasEsqueleto />
            ) : r.aniversariantes.itens.length === 0 ? (
              <Vazio icone={Cake} texto="Nenhum aniversário por perto" dica="Os próximos aniversários dos alunos ativos aparecem aqui." />
            ) : (
              <ul className="divide-y">
                {r.aniversariantes.itens.map((a) => (
                  <LinhaAniversariante key={a.aluno_id} a={a} />
                ))}
              </ul>
            )}
          </Secao>
        )}
      </div>
    </div>
  );
}

function RankingProfessores({ itens }: { itens: { profissional_id: number; nome: string; total: number }[] }) {
  const maximo = Math.max(...itens.map((i) => i.total), 1);
  return (
    <ol className="space-y-3">
      {itens.map((p, i) => (
        <li key={p.profissional_id}>
          <div className="mb-1 flex items-center justify-between gap-2 text-sm">
            <span className="min-w-0 truncate">
              <span className="mr-2 text-xs text-muted-foreground num">{i + 1}º</span>
              <span className="font-medium">{p.nome}</span>
            </span>
            <span className="shrink-0 text-xs text-muted-foreground num">{numero(p.total)} aulas</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted" role="presentation">
            <div className="h-full rounded-full bg-brand" style={{ width: `${Math.round((p.total / maximo) * 100)}%` }} />
          </div>
        </li>
      ))}
    </ol>
  );
}

function Kpis({ r, carregando }: { r: ResumoPainel | undefined; carregando: boolean }) {
  const k = r?.kpis;
  const rm = r?.recebido_mes;
  // enquanto carrega ainda não sabemos o que o perfil enxerga: mostra os esqueletos de sempre
  const mostrar = (visivel: boolean | undefined) => carregando || !!visivel;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {mostrar(k?.alunos_ativos.visivel) && (
        <KpiPainel
          titulo="Alunos ativos"
          valor={numero(k?.alunos_ativos.valor)}
          rodape={k?.alunos_ativos.valor === 0 ? "Cadastre o primeiro aluno para começar" : "Ver alunos ativos"}
          icone={UsersRound}
          href={k?.alunos_ativos.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.aulas.visivel) && (
        <KpiPainel
          titulo="Aulas hoje"
          valor={numero(k?.aulas.hoje)}
          rodape={`${numero(k?.aulas.amanha)} amanhã`}
          icone={CalendarCheck}
          href={k?.aulas.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.contratos_vencendo.visivel) && (
        <KpiPainel
          titulo="Contratos vencendo"
          valor={numero(k?.contratos_vencendo.valor)}
          rodape="nos próximos 30 dias"
          icone={FileClock}
          href={k?.contratos_vencendo.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.a_receber.visivel) && (
        <KpiPainel
          titulo="A receber (em aberto)"
          valor={moeda(k?.a_receber.valor)}
          rodape={`${numero(k?.a_receber.quantidade)} cobranças a vencer`}
          icone={Wallet}
          href={k?.a_receber.href}
          carregando={carregando}
        />
      )}
      {mostrar(k?.atrasado.visivel) && (
        <KpiPainel
          titulo="Atrasado"
          valor={moeda(k?.atrasado.valor)}
          rodape={`${numero(k?.atrasado.quantidade)} cobranças vencidas`}
          icone={Hourglass}
          tom={(k?.atrasado.quantidade ?? 0) > 0 ? "perigo" : "neutro"}
          href={k?.atrasado.href}
          carregando={carregando}
        />
      )}
      {mostrar(rm?.visivel) && (
        <KpiPainel
          titulo="Recebido no mês"
          valor={moeda(rm?.valor)}
          rodape={rm && <VariacaoRecebido pct={rm.variacao_pct} base={rm.anterior_ate_mesmo_dia} />}
          icone={WalletCards}
          href={rm?.href}
          carregando={carregando}
        />
      )}
    </div>
  );
}
