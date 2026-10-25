"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageCircle, Send, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/mayacorp/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora } from "@/lib/format";
import type { EnvioResultado, MensagemWhatsapp } from "@/lib/tipos-comunicacao";
import { cn } from "@/lib/utils";

/**
 * Aba "WhatsApp" da ficha do aluno: conversa (histórico das mensagens enviadas) e envio de uma mensagem.
 * Uso: `<AbaAlunoWhatsapp alunoId={aluno.id} />` (o coordenador liga em `components/alunos/abas.ts`).
 * Permissões: ver o histórico = `whatsapp.ver`; enviar = `whatsapp.enviar`.
 */
export function AbaAlunoWhatsapp({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const podeVer = pode("whatsapp.ver");
  const podeEnviar = pode("whatsapp.enviar");
  const [texto, setTexto] = useState("");
  const fim = useRef<HTMLDivElement>(null);

  const conversa = useQuery({
    queryKey: ["whatsapp", "conversa", alunoId],
    queryFn: () => api.get<MensagemWhatsapp[]>(`/whatsapp/alunos/${alunoId}/mensagens`),
    enabled: podeVer,
  });

  const enviar = useMutation({
    mutationFn: () => api.post<EnvioResultado>(`/whatsapp/alunos/${alunoId}/enviar`, { texto }),
    onSuccess: () => {
      setTexto("");
      toast.success("Mensagem enviada");
    },
    // falhou ou não: o histórico registra a tentativa
    onSettled: () => qc.invalidateQueries({ queryKey: ["whatsapp", "conversa", alunoId] }),
  });

  const itens = conversa.data ?? [];
  useEffect(() => {
    fim.current?.scrollIntoView({ block: "end" });
  }, [itens.length]);

  if (!podeVer) return <EmptyState icone={MessageCircle} titulo="Sem acesso ao WhatsApp" descricao="Seu perfil não permite ver as mensagens." />;

  return (
    <div className="card-surface flex flex-col overflow-hidden">
      <div className="max-h-[28rem] min-h-48 flex-1 space-y-3 overflow-y-auto bg-muted/30 p-4">
        {conversa.isPending ? (
          <Skeleton className="h-24 rounded-xl" />
        ) : itens.length === 0 ? (
          <EmptyState icone={MessageCircle} titulo="Nenhuma mensagem ainda" descricao="Os avisos, cobranças e mensagens enviados a este aluno aparecem aqui." className="py-8" />
        ) : (
          itens.map((m) => (
            <div key={m.id} className={cn("flex", m.direcao === "enviada" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm shadow-sm ring-1 ring-inset",
                  m.status === "failed" ? "bg-danger/10 ring-danger/25" : m.direcao === "enviada" ? "bg-brand/12 ring-brand/25" : "bg-card ring-border",
                )}
              >
                <p className="whitespace-pre-wrap break-words">{m.mensagem}</p>
                <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                  <span>{m.tipo_rotulo}</span>
                  <span>{dataHora(m.enviado_em)}</span>
                  {m.status === "failed" && (
                    <span className="inline-flex items-center gap-1 text-danger-ink">
                      <TriangleAlert className="size-3" /> não enviada
                    </span>
                  )}
                </p>
              </div>
            </div>
          ))
        )}
        <div ref={fim} />
      </div>
      {podeEnviar && (
        <form
          className="flex items-end gap-2 border-t p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (texto.trim()) enviar.mutate();
          }}
        >
          <Textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={2}
            maxLength={4000}
            placeholder="Escreva a mensagem… (use {aluno} e {unidade} se quiser)"
            aria-label="Mensagem"
            className="min-h-10 flex-1"
          />
          <Button type="submit" disabled={!texto.trim() || enviar.isPending}>
            {enviar.isPending ? <Loader2 className="animate-spin" /> : <Send />} Enviar
          </Button>
        </form>
      )}
    </div>
  );
}
