"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { CalendarCheck, CalendarDays, CalendarPlus, ClipboardEdit, Play, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { BotoesWhatsappAula } from "@/components/comunicacao/botoes-whatsapp-aula";
import { EmptyState } from "@/components/mayacorp/empty-state";
import { NativeSelect } from "@/components/mayacorp/form";
import { SearchInput } from "@/components/mayacorp/data-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CartaoAula, GrupoProfissional, HorarioPainel, Painel, StatusAula } from "@/lib/tipos-agenda";
import { ROTULO_STATUS_AULA } from "@/lib/tipos-agenda";
import { cn } from "@/lib/utils";

import { CORES_PROFISSIONAL, PillStatusAula, hojeIso, useInvalidarAgenda, useOpcoesAgenda } from "./comum";
import { DialogoGerarSessoes, DialogoNovaAula } from "./dialogos-sessao";
import { GavetaAluno } from "./gaveta-aluno";

const PERIODOS = [
  { id: "hoje", rotulo: "Hoje" },
  { id: "amanha", rotulo: "Amanhã" },
  { id: "semana", rotulo: "Semana" },
] as const;
type Periodo = (typeof PERIODOS)[number]["id"];

function Chip({ ativo, onClick, children }: { ativo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
        ativo ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}

function Rotulo({ children }: { children: React.ReactNode }) {
  return <p className="mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{children}</p>;
}

/** Cartão do aluno: texto sempre como texto (o React escapa; nunca HTML injetado). */
function Cartao({
  c,
  podeOperar,
  onAbrir,
  onChegou,
  ocupado,
}: {
  c: CartaoAula;
  podeOperar: boolean;
  onAbrir: (aba?: "evolucao") => void;
  onChegou: () => void;
  ocupado: boolean;
}) {
  const indicadores: { rotulo: string; tom: "ok" | "aviso" | "erro" }[] = [
    c.confirmacao ? { rotulo: "Confirmado", tom: "ok" } : { rotulo: "Não confirmado", tom: "aviso" },
  ];
  if (!c.flags.tem_preliminares) indicadores.push({ rotulo: "Preliminares pendentes", tom: "aviso" });
  if (c.flags.cobranca_pendente) indicadores.push({ rotulo: "Cobrança pendente", tom: "erro" });
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onAbrir()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onAbrir())}
      className={cn(
        "card-surface cursor-pointer space-y-2 border-l-4 p-3 text-left transition-shadow hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        c.status_aula === "finalizada" && "border-l-success",
        c.status_aula === "em_aula" && "border-l-info",
        c.status_aula === "faltou" && "border-l-danger",
        c.status_aula === "remarcada" && "border-l-muted-foreground/40",
        c.status_aula === "aguardando_chegar" && "border-l-warning",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{c.aluno.nome}</p>
          <p className="truncate text-xs text-muted-foreground">{c.plano.descricao ?? "Plano não informado"}</p>
          <p className="truncate text-xs text-muted-foreground">
            {c.servicos.length > 1 ? "Serviços" : "Serviço"}: {c.servicos.join(", ") || c.servico}
          </p>
        </div>
        <PillStatusAula status={c.status_aula} />
      </div>
      <div className="flex flex-wrap gap-1">
        {indicadores.map((i) => (
          <span
            key={i.rotulo}
            className={cn(
              "rounded-md px-1.5 py-0.5 text-[11px] font-medium",
              i.tom === "ok" && "bg-success/10 text-success-ink",
              i.tom === "aviso" && "bg-warning/12 text-warning-ink",
              i.tom === "erro" && "bg-danger/10 text-danger-ink",
            )}
          >
            {i.rotulo}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
        {podeOperar && (
          <Button size="xs" variant="outline" disabled={ocupado} onClick={onChegou}>
            <Play /> Chegou
          </Button>
        )}
        <Button size="xs" variant="outline" onClick={() => onAbrir("evolucao")}>
          <ClipboardEdit /> Evolução
        </Button>
        <BotoesWhatsappAula reservaId={c.id} telefone={c.aluno.telefone} />
      </div>
    </div>
  );
}

interface AcoesPainel {
  podeOperar: boolean;
  ocupado: boolean;
  onAbrir: (c: CartaoAula, aba?: "evolucao") => void;
  onChegou: (c: CartaoAula) => void;
}

function BlocoProfissional({ g, ...resto }: { g: GrupoProfissional } & AcoesPainel) {
  const cor = CORES_PROFISSIONAL[g.cor_indice % CORES_PROFISSIONAL.length];
  return (
    <section className="min-w-0 rounded-xl border bg-card/60" style={{ borderTop: `3px solid ${cor}` }}>
      <header className="flex items-center gap-2 px-3 py-2">
        <span className="grid size-7 shrink-0 place-items-center rounded-full text-[11px] font-bold text-white" style={{ background: cor }}>
          {g.iniciais}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{g.nome}</span>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{g.total} aluno(s)</span>
      </header>
      <div className="grid gap-2 p-2 pt-0 sm:grid-cols-2 2xl:grid-cols-3">
        {g.cartoes.map((c) => (
          <Cartao
            key={c.id}
            c={c}
            podeOperar={resto.podeOperar}
            ocupado={resto.ocupado}
            onAbrir={(aba) => resto.onAbrir(c, aba)}
            onChegou={() => resto.onChegou(c)}
          />
        ))}
      </div>
    </section>
  );
}

function LinhaHorario({ h, ...resto }: { h: HorarioPainel } & AcoesPainel) {
  return (
    <div className="grid gap-3 md:grid-cols-[132px_1fr]">
      {/* quadro CLARO do horário: a hora em destaque; a data não se repete aqui */}
      <div className="flex flex-row items-center gap-3 rounded-xl border border-brand/20 bg-brand/6 px-4 py-3 md:flex-col md:items-start md:gap-0.5 md:self-start">
        <p className="num text-3xl leading-none font-bold tracking-tight text-navy dark:text-foreground">{h.hora_inicio}</p>
        <p className="text-xs text-muted-foreground">até {h.hora_fim}</p>
        <p className="text-xs font-medium text-foreground/80 md:mt-1.5">{h.total} aluno(s)</p>
      </div>
      <div className="grid min-w-0 gap-3 lg:grid-cols-[repeat(auto-fit,minmax(340px,1fr))]">
        {h.profissionais.map((g) => (
          <BlocoProfissional key={`${g.profissional_id}-${g.nome}`} g={g} {...resto} />
        ))}
      </div>
    </div>
  );
}

/**
 * Painel operacional: períodos Hoje/Amanhã/Semana, data alvo, filtros e busca; agrupado por horário > profissional >
 * alunos. Clicar num cartão abre a gaveta do aluno. Atualiza sozinho a cada minuto (o status "em aula" depende da hora).
 */
export function PainelOperacional() {
  const { pode, somenteProprias } = useAuth();
  const opcoes = useOpcoesAgenda();
  const invalidar = useInvalidarAgenda();
  const [periodo, setPeriodo] = useState<Periodo>("hoje");
  const [data, setData] = useState(hojeIso());
  const [unidade, setUnidade] = useState("");
  const [profissional, setProfissional] = useState("");
  const [status, setStatus] = useState<StatusAula | "">("");
  const [busca, setBusca] = useState("");
  const q = useDebounce(busca, 300);
  const [aberta, setAberta] = useState<{ id: number; aba: "evolucao" } | null>(null);
  const [novaAula, setNovaAula] = useState(false);
  const [gerar, setGerar] = useState(false);

  const consulta = useQuery({
    queryKey: ["agenda", "painel", periodo, data, unidade, profissional, status, q],
    queryFn: () =>
      api.get<Painel>("/aulas/painel", { periodo, data, unidade_id: unidade, profissional_id: profissional, status_aula: status, q }),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
  const chegou = useMutation({
    mutationFn: (c: CartaoAula) => api.post(`/aulas/reservas/${c.id}/presenca`, { acao: "chegou" }),
    onSuccess: () => invalidar(),
  });

  const painel = consulta.data;
  const podeOperar = pode("aulas.operar") || pode("aulas.evoluir");
  const intervalo = painel && painel.data_inicio !== painel.data_fim ? `${painel.data_inicio.slice(8)}/${painel.data_inicio.slice(5, 7)} – ${painel.data_fim.slice(8)}/${painel.data_fim.slice(5, 7)}` : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {painel ? `${painel.total} aluno(s)` : "Carregando…"}
          {intervalo ? ` · ${intervalo}` : ""}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" render={<Link href="/agenda/semana" />}>
            <CalendarDays /> Grade semanal
          </Button>
          {pode("agenda.editar") && (
            <>
              <Button variant="outline" size="sm" onClick={() => setGerar(true)}>
                <Sparkles /> Gerar aulas
              </Button>
              <Button size="sm" onClick={() => setNovaAula(true)}>
                <CalendarPlus /> Nova aula
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="card-surface grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-[auto_auto_1fr_1fr]">
        <div>
          <Rotulo>Período</Rotulo>
          <div className="flex gap-1.5">
            {PERIODOS.map((p) => (
              <Chip key={p.id} ativo={periodo === p.id} onClick={() => setPeriodo(p.id)}>
                {p.rotulo}
              </Chip>
            ))}
          </div>
        </div>
        <div>
          <Rotulo>Data alvo</Rotulo>
          <Input type="date" value={data} onChange={(e) => e.target.value && setData(e.target.value)} className="h-9 w-44" />
        </div>
        <div>
          <Rotulo>Unidade</Rotulo>
          <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value)} aria-label="Unidade">
            <option value="">Todas</option>
            {(opcoes.data?.unidades ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.nome}
              </option>
            ))}
          </NativeSelect>
        </div>
        {!somenteProprias && (
          <div>
            <Rotulo>Profissional</Rotulo>
            <NativeSelect value={profissional} onChange={(e) => setProfissional(e.target.value)} aria-label="Profissional">
              <option value="">Todos os instrutores</option>
              {(opcoes.data?.profissionais ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </NativeSelect>
          </div>
        )}
        <div className="md:col-span-2 xl:col-span-2">
          <Rotulo>Status</Rotulo>
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(ROTULO_STATUS_AULA) as StatusAula[]).map((s) => (
              <Chip key={s} ativo={status === s} onClick={() => setStatus(status === s ? "" : s)}>
                {ROTULO_STATUS_AULA[s]}
              </Chip>
            ))}
          </div>
        </div>
        <div className="md:col-span-2 xl:col-span-2">
          <Rotulo>Buscar aluno</Rotulo>
          <SearchInput value={busca} onChange={setBusca} placeholder="Nome, CPF ou telefone" className="sm:w-full" />
        </div>
      </div>

      {consulta.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
        </div>
      ) : !painel || painel.dias.length === 0 ? (
        <div className="card-surface">
          <EmptyState icone={CalendarCheck} titulo="Sem aulas para o filtro" descricao="Mude o período, a data ou os filtros para ver outras aulas." />
        </div>
      ) : (
        <div className={cn("space-y-6 transition-opacity", consulta.isPlaceholderData && "opacity-60")}>
          {painel.dias.map((d) => (
            <div key={d.data} className="space-y-3">
              {painel.periodo === "semana" && (
                <h2 className="border-b pb-1 text-sm font-semibold text-foreground/80 capitalize">
                  {d.rotulo} <span className="font-normal text-muted-foreground">· {d.total} aluno(s)</span>
                </h2>
              )}
              {d.horarios.map((h) => (
                <LinhaHorario
                  key={`${d.data}-${h.hora_inicio}`}
                  h={h}
                  podeOperar={podeOperar}
                  ocupado={chegou.isPending}
                  onAbrir={(c, aba) => setAberta({ id: c.id, aba: aba ?? "evolucao" })}
                  onChegou={(c) => chegou.mutate(c)}
                />
              ))}
            </div>
          ))}
        </div>
      )}

      <GavetaAluno key={aberta?.id ?? "fechada"} reservaId={aberta?.id ?? null} abaInicial={aberta?.aba} onFechar={() => setAberta(null)} />
      <DialogoNovaAula aberto={novaAula} onFechar={() => setNovaAula(false)} />
      <DialogoGerarSessoes aberto={gerar} onFechar={() => setGerar(false)} />
    </div>
  );
}
