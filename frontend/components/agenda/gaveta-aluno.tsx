"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BadgeCheck,
  CalendarClock,
  CheckCheck,
  CircleCheck,
  ExternalLink,
  Loader2,
  MessageCircle,
  Play,
  Trash2,
  UserX,
  Undo2,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { UserAvatar } from "@/components/mayacorp/user-avatar";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { moeda } from "@/lib/format";
import type { CartaoAula, CobrancaAluno, HistoricoAula, Registro } from "@/lib/tipos-agenda";

import { PillStatusAula, PillStatusReserva, dataBr, useInvalidarAgenda } from "./comum";
import { DialogoRemarcar } from "./dialogo-remarcar";
import { EditorRegistro, ListaRegistros } from "./editor-registro";

type Aba = "evolucao" | "avaliacoes" | "cobranca";

function Cobranca({ reservaId }: { reservaId: number }) {
  const q = useQuery({
    queryKey: ["agenda", "reserva", reservaId, "cobranca"],
    queryFn: () => api.get<{ itens: CobrancaAluno[] }>(`/aulas/reservas/${reservaId}/cobranca`),
  });
  if (q.isPending) return <Skeleton className="h-24 rounded-xl" />;
  const itens = q.data?.itens ?? [];
  if (!itens.length) return <p className="py-6 text-center text-sm text-muted-foreground">Sem cobranças para este aluno.</p>;
  return (
    <ul className="space-y-2">
      {itens.map((c) => (
        <li key={c.id} className="flex items-center justify-between gap-3 rounded-xl border bg-background/60 p-3 text-sm">
          <div className="min-w-0">
            <p className="truncate font-medium">{c.descricao ?? `Competência ${c.competencia ?? "—"}`}</p>
            <p className="text-xs text-muted-foreground">
              Vence em {dataBr(c.vencimento)}
              {c.pagamento ? ` · pago em ${dataBr(c.pagamento)}` : ""}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <p className="num font-semibold">{moeda(c.valor)}</p>
            <Pill tom={c.status === "PAGO" ? "success" : c.status === "ATRASADO" ? "danger" : c.status === "CANCELADO" ? "neutral" : "warning"}>
              {c.status === "ATRASADO" ? "Atrasado" : c.status === "PAGO" ? "Pago" : c.status === "CANCELADO" ? "Cancelado" : "Em aberto"}
            </Pill>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Historico({ reservaId }: { reservaId: number }) {
  const q = useQuery({
    queryKey: ["agenda", "reserva", reservaId, "historico"],
    queryFn: () => api.get<{ itens: HistoricoAula[] }>(`/aulas/reservas/${reservaId}/historico`),
  });
  const itens = q.data?.itens ?? [];
  if (!itens.length) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">Últimas aulas</p>
      <ul className="space-y-1">
        {itens.slice(0, 6).map((h) => (
          <li key={h.id} className="flex items-center justify-between gap-2 text-xs">
            <span className="truncate">
              {dataBr(h.data)} {h.hora_inicio} · {h.servico}
            </span>
            <PillStatusReserva status={h.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Gaveta lateral do aluno numa aula: ações (chegou, finalizar, faltou, remarcar, desmarcar, excluir) e abas Evolução,
 * Avaliações e Cobrança (só com permissão financeira). O corpo rola por dentro: o cabeçalho e as abas nunca saem da tela.
 */
export function GavetaAluno({ reservaId, abaInicial = "evolucao", onFechar }: { reservaId: number | null; abaInicial?: Aba; onFechar: () => void }) {
  const { pode } = useAuth();
  const invalidar = useInvalidarAgenda();
  const [aba, setAba] = useState<Aba>(abaInicial);
  const [remarcando, setRemarcando] = useState(false);
  const [confirmar, setConfirmar] = useState<"desmarcar" | "excluir" | null>(null);

  const q = useQuery({
    queryKey: ["agenda", "reserva", reservaId],
    queryFn: () => api.get<CartaoAula>(`/aulas/reservas/${reservaId}`),
    enabled: reservaId !== null,
  });
  const c = q.data;
  const p = c?.permite;

  const evolucoes = useQuery({
    queryKey: ["agenda", "reserva", reservaId, "evolucoes"],
    queryFn: () => api.get<{ itens: Registro[] }>(`/aulas/reservas/${reservaId}/evolucao`),
    enabled: reservaId !== null && !!p?.evolucao,
  });
  const avaliacoes = useQuery({
    queryKey: ["agenda", "reserva", reservaId, "avaliacoes"],
    queryFn: () => api.get<{ itens: Registro[] }>(`/aulas/reservas/${reservaId}/avaliacao`),
    enabled: reservaId !== null && !!p?.avaliacao,
  });

  const presenca = useMutation({
    mutationFn: (acao: string) => api.post(`/aulas/reservas/${reservaId}/presenca`, { acao }),
    onSuccess: () => invalidar(),
  });
  const confirmarPresenca = useMutation({
    mutationFn: () => api.post(`/aulas/reservas/${reservaId}/confirmar`),
    onSuccess: () => {
      toast.success("Aula confirmada");
      invalidar();
    },
  });
  const desmarcar = useMutation({
    mutationFn: () => api.post<{ reposicao_ate: string | null }>(`/aulas/reservas/${reservaId}/desmarcar`),
    onSuccess: (r) => {
      toast.success(r.reposicao_ate ? `Aula desmarcada. Reposição até ${dataBr(r.reposicao_ate)}.` : "Aula desmarcada");
      setConfirmar(null);
      invalidar();
    },
    onError: () => setConfirmar(null),
  });
  const excluir = useMutation({
    mutationFn: () => api.del(`/aulas/reservas/${reservaId}`),
    onSuccess: () => {
      toast.success("Aula excluída");
      setConfirmar(null);
      invalidar();
      onFechar();
    },
    onError: () => setConfirmar(null),
  });

  const ocupado = presenca.isPending || confirmarPresenca.isPending;
  const abas: { id: Aba; rotulo: string; visivel: boolean }[] = [
    { id: "evolucao", rotulo: "Evolução", visivel: !!p?.evolucao },
    { id: "avaliacoes", rotulo: "Avaliações", visivel: !!p?.avaliacao },
    { id: "cobranca", rotulo: "Cobrança", visivel: !!p?.cobranca },
  ];
  const visiveis = abas.filter((a) => a.visivel);
  const abaAtual = visiveis.some((a) => a.id === aba) ? aba : (visiveis[0]?.id ?? "evolucao");

  return (
    <Sheet open={reservaId !== null} onOpenChange={(o) => !o && onFechar()}>
      <SheetContent side="right" className="w-full gap-0 overflow-hidden p-0 data-[side=right]:sm:max-w-xl!">
        {!c ? (
          <div className="space-y-3 p-5">
            <SheetHeader className="p-0">
              <SheetTitle>Aula</SheetTitle>
              <SheetDescription>{q.isError ? "Não foi possível abrir esta aula." : "Carregando…"}</SheetDescription>
            </SheetHeader>
            {q.isPending && <Skeleton className="h-40 rounded-xl" />}
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col">
            {/* topo: identificação e ações; se a tela for baixa, rola sozinho sem esconder as abas */}
            <div className="max-h-[48dvh] shrink-0 space-y-3 overflow-y-auto border-b p-4 pr-12">
              <SheetHeader className="p-0">
                <div className="flex items-center gap-3">
                  <UserAvatar nome={c.aluno.nome} className="size-11" />
                  <div className="min-w-0">
                    <SheetTitle className="truncate text-base">{c.aluno.nome}</SheetTitle>
                    <SheetDescription className="truncate">
                      {dataBr(c.data)} · {c.hora_inicio}–{c.hora_fim} · {c.unidade}
                      {c.profissional ? ` · ${c.profissional.nome}` : ""}
                    </SheetDescription>
                  </div>
                </div>
              </SheetHeader>
              <div className="flex flex-wrap items-center gap-1.5">
                <PillStatusAula status={c.status_aula} />
                <Pill tom={c.confirmacao ? "success" : "neutral"}>{c.confirmacao ? "Confirmado" : "Não confirmado"}</Pill>
                <Pill tom={c.flags.tem_preliminares ? "success" : "warning"}>
                  Preliminares {c.flags.tem_preliminares ? "ok" : "pendentes"}
                </Pill>
                {c.flags.cobranca_pendente && <Pill tom="danger">Cobrança pendente</Pill>}
                {c.status === "CANCELADA" && c.reposicao_ate && <Pill tom="info">Reposição até {dataBr(c.reposicao_ate)}</Pill>}
              </div>
              <p className="text-xs text-muted-foreground">
                {c.plano.descricao ?? "Plano não informado"} · {c.servicos.join(", ") || c.servico}
              </p>

              <div className="flex flex-wrap gap-1.5">
                {p?.chegou && (
                  <Button size="sm" disabled={ocupado} onClick={() => presenca.mutate("chegou")}>
                    {presenca.isPending && presenca.variables === "chegou" ? <Loader2 className="animate-spin" /> : <Play />} Chegou
                  </Button>
                )}
                {p?.finalizar && (
                  <Button size="sm" variant="outline" disabled={ocupado} onClick={() => presenca.mutate("finalizar")}>
                    <CheckCheck /> Finalizar
                  </Button>
                )}
                {p?.faltou && (
                  <>
                    <Button size="sm" variant="outline" disabled={ocupado} onClick={() => presenca.mutate("faltou")}>
                      <UserX /> Faltou
                    </Button>
                    <Button size="sm" variant="outline" disabled={ocupado} onClick={() => presenca.mutate("faltou_avisou")}>
                      <BadgeCheck /> Faltou (avisou)
                    </Button>
                  </>
                )}
                {p?.confirmar && !c.confirmacao && (
                  <Button size="sm" variant="outline" disabled={ocupado} onClick={() => confirmarPresenca.mutate()}>
                    <CircleCheck /> Confirmar
                  </Button>
                )}
                {p?.remarcar && (
                  <Button size="sm" variant="outline" onClick={() => setRemarcando(true)}>
                    <CalendarClock /> Remarcar
                  </Button>
                )}
                {p?.desmarcar && c.status !== "CANCELADA" && (
                  <Button size="sm" variant="outline" onClick={() => setConfirmar("desmarcar")}>
                    <Undo2 /> Desmarcar (reposição)
                  </Button>
                )}
                {p?.excluir && (
                  <Button size="sm" variant="destructive" onClick={() => setConfirmar("excluir")}>
                    <Trash2 /> Excluir
                  </Button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Button size="xs" variant="ghost" disabled title={c.whatsapp.motivo}>
                  <MessageCircle /> WhatsApp
                </Button>
                {pode("alunos.ver") && (
                  <Button size="xs" variant="ghost" render={<Link href={`/alunos/${c.aluno.id}`} />}>
                    <ExternalLink /> Ficha do aluno
                  </Button>
                )}
              </div>
            </div>

            {/* abas: o conteúdo rola por dentro */}
            {visiveis.length > 0 ? (
              <Tabs value={abaAtual} onValueChange={(v) => setAba(v as Aba)} className="min-h-0 flex-1 gap-0">
                <TabsList variant="line" className="w-full shrink-0 justify-start gap-3 border-b px-4">
                  {visiveis.map((a) => (
                    <TabsTrigger key={a.id} value={a.id} className="flex-none px-1">
                      {a.rotulo}
                    </TabsTrigger>
                  ))}
                </TabsList>
                <div className="min-h-0 flex-1 overflow-y-auto p-4">
                  <TabsContent value="evolucao" className="space-y-4">
                    <EditorRegistro tipo="evolucao" reservaId={c.id} />
                    <ListaRegistros tipo="evolucao" itens={evolucoes.data?.itens ?? []} podeEditar={!!p?.evolucao} vazio="Nenhuma evolução registrada." />
                    <Historico reservaId={c.id} />
                  </TabsContent>
                  <TabsContent value="avaliacoes" className="space-y-4">
                    <EditorRegistro tipo="avaliacao" reservaId={c.id} />
                    <ListaRegistros tipo="avaliacao" itens={avaliacoes.data?.itens ?? []} podeEditar={!!p?.avaliacao} vazio="Nenhuma avaliação registrada." />
                  </TabsContent>
                  <TabsContent value="cobranca">
                    <Cobranca reservaId={c.id} />
                  </TabsContent>
                </div>
              </Tabs>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <Historico reservaId={c.id} />
              </div>
            )}
          </div>
        )}
      </SheetContent>

      {c && (
        <>
          <DialogoRemarcar
            reservaId={c.id}
            status={c.status}
            reposicaoAte={c.reposicao_ate}
            profissionalId={c.profissional?.id ?? null}
            aberto={remarcando}
            onFechar={() => setRemarcando(false)}
          />
          <ConfirmDialog
            open={confirmar === "desmarcar"}
            onOpenChange={(o) => !o && setConfirmar(null)}
            titulo="Desmarcar esta aula?"
            descricao="A aula fica cancelada e o aluno ganha uma reposição por 30 dias."
            confirmar="Desmarcar"
            carregando={desmarcar.isPending}
            onConfirm={() => desmarcar.mutate()}
          />
          <ConfirmDialog
            open={confirmar === "excluir"}
            onOpenChange={(o) => !o && setConfirmar(null)}
            titulo="Excluir esta aula do aluno?"
            descricao="A vaga é liberada e, se ninguém mais estiver na aula, ela também é apagada. Aulas com evolução ou cobrança paga não podem ser excluídas."
            confirmar="Excluir"
            destrutivo
            carregando={excluir.isPending}
            onConfirm={() => excluir.mutate()}
          />
        </>
      )}
    </Sheet>
  );
}
