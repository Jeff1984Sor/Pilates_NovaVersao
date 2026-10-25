"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Loader2, Megaphone, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ComunicadoCard } from "@/components/comunicacao/comunicado-card";
import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Field, NativeSelect } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { OpcoesAluno } from "@/lib/tipos-alunos";
import { ROTULO_PUBLICO, type Comunicado, type PreviaComunicado, type PublicoComunicado } from "@/lib/tipos-comunicacao";

export default function ComunicadosPage() {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const [texto, setTexto] = useState("");
  const [publico, setPublico] = useState<PublicoComunicado>("ativos");
  const [unidade, setUnidade] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const [novoId, setNovoId] = useState<number | null>(null);
  const corpo = { texto, publico, unidade_id: unidade ? Number(unidade) : null };

  const unidades = useQuery({
    queryKey: ["alunos", "opcoes"],
    queryFn: () => api.get<OpcoesAluno>("/alunos/opcoes"),
    enabled: pode("alunos.ver"),
    meta: { silencioso: true },
  });
  const previa = useQuery({
    queryKey: ["comunicado", "previa", texto, publico, unidade],
    queryFn: () => api.post<PreviaComunicado>("/comunicacao/comunicados/previa", corpo),
    enabled: texto.trim().length > 0,
    meta: { silencioso: true },
  });
  const lista = useQuery({
    queryKey: ["comunicados"],
    queryFn: () => api.get<Comunicado[]>("/comunicacao/comunicados"),
    enabled: pode("comunicacao.ver"),
  });
  const criar = useMutation({
    mutationFn: () => api.post<Comunicado>("/comunicacao/comunicados", corpo),
    onSuccess: (c) => {
      setConfirmar(false);
      setTexto("");
      setNovoId(c.id);
      qc.invalidateQueries({ queryKey: ["comunicados"] });
      toast.success("Comunicado na fila: os alunos recebem um a um, com pausa entre os envios");
    },
  });

  if (!pode("comunicacao.ver")) return <SemAcesso titulo="Comunicados" />;
  const p = previa.data;
  const podeEnviar = pode("comunicacao.enviar");

  return (
    <div>
      <PageHeader
        titulo="Comunicados"
        descricao="Mensagem de WhatsApp para vários alunos, enviada um a um com pausa entre os envios (evita bloqueio do número)."
        icone={Megaphone}
        migalhas={[{ label: "Início", href: "/" }, { label: "Comunicação" }, { label: "Comunicados" }]}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {podeEnviar && (
          <section className="card-surface space-y-4 self-start p-5">
            <h2 className="font-semibold">Novo comunicado</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Destinatários">
                <NativeSelect value={publico} onChange={(e) => setPublico(e.target.value as PublicoComunicado)}>
                  {(Object.keys(ROTULO_PUBLICO) as PublicoComunicado[]).map((k) => (
                    <option key={k} value={k}>
                      {ROTULO_PUBLICO[k]}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Unidade">
                <NativeSelect value={unidade} onChange={(e) => setUnidade(e.target.value)}>
                  <option value="">Todas as unidades</option>
                  {(unidades.data?.unidades ?? []).map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.nome}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            </div>
            <Field label="Mensagem" dica="Variáveis: {aluno} e {unidade}.">
              <Textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={6} maxLength={4000} placeholder="Olá {aluno}, …" />
            </Field>
            {texto.trim() && p && (
              <div className="space-y-2 rounded-xl border bg-muted/40 p-3.5 text-sm">
                <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <Eye className="size-3.5" /> Prévia{p.primeiro_aluno ? ` (para ${p.primeiro_aluno})` : ""}
                </p>
                <p className="whitespace-pre-wrap">{p.mensagem || "—"}</p>
                <p className="border-t pt-2 text-xs text-muted-foreground">
                  <strong className="text-foreground">{p.total}</strong> aluno(s): <strong className="text-success-ink">{p.com_telefone}</strong> receberão ·{" "}
                  {p.sem_telefone} sem celular válido (serão pulados).
                </p>
              </div>
            )}
            <div className="flex justify-end">
              <Button disabled={!texto.trim() || !p || p.com_telefone === 0} onClick={() => setConfirmar(true)}>
                <Send /> Enviar comunicado
              </Button>
            </div>
          </section>
        )}
        <section className="space-y-3">
          <h2 className="font-semibold">Envios recentes</h2>
          {lista.isPending ? (
            <Loader2 className="animate-spin text-muted-foreground" />
          ) : (lista.data?.length ?? 0) === 0 ? (
            <p className="card-surface p-5 text-sm text-muted-foreground">Nenhum comunicado enviado ainda.</p>
          ) : (
            lista.data!.map((c) => <ComunicadoCard key={c.id} inicial={c} destaque={c.id === novoId} />)
          )}
        </section>
      </div>
      <ConfirmDialog
        open={confirmar}
        onOpenChange={setConfirmar}
        titulo="Enviar o comunicado?"
        descricao={`Serão enviadas ${p?.com_telefone ?? 0} mensagens de WhatsApp, uma a uma. Você pode pausar ou cancelar a qualquer momento.`}
        confirmar="Enviar"
        carregando={criar.isPending}
        onConfirm={() => criar.mutate()}
      />
    </div>
  );
}
