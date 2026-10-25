"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { MessageCircle, Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface PreviaReserva {
  aluno_id: number;
  aluno_nome: string;
  mensagem: string;
  tem_celular: boolean;
}

/** Só dígitos com DDI 55 para o link wa.me (conversa aberta no WhatsApp do próprio celular/computador). */
function linkWhatsapp(telefone: string | null | undefined): string | null {
  const d = (telefone ?? "").replace(/\D/g, "");
  if (d.length < 10) return null;
  return `https://wa.me/${d.startsWith("55") ? d : `55${d}`}`;
}

/**
 * Atalhos de WhatsApp de uma reserva no painel operacional:
 * - "WhatsApp": abre a conversa no aplicativo (link wa.me);
 * - "Enviar agora": mostra o texto do lembrete da aula e, ao confirmar, o sistema envia pela conta cadastrada.
 */
export function BotoesWhatsappAula({ reservaId, telefone }: { reservaId: number; telefone: string | null }) {
  const { pode } = useAuth();
  const [aberto, setAberto] = useState(false);
  const podeEnviar = pode("whatsapp.enviar");
  const link = linkWhatsapp(telefone);

  const previa = useQuery({
    queryKey: ["whatsapp-previa-reserva", reservaId],
    queryFn: () => api.get<PreviaReserva>(`/whatsapp/reservas/${reservaId}/previa`),
    enabled: aberto && podeEnviar,
    staleTime: 0,
  });
  const enviar = useMutation({
    mutationFn: () => api.post(`/whatsapp/reservas/${reservaId}/enviar-agora`),
    onSuccess: () => {
      toast.success("Lembrete enviado pelo WhatsApp.");
      setAberto(false);
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Não foi possível enviar."),
  });

  return (
    <>
      <Button
        size="xs"
        variant="ghost"
        disabled={!link}
        title={link ? "Abrir a conversa no WhatsApp" : "O aluno não tem celular válido"}
        render={link ? <a href={link} target="_blank" rel="noopener noreferrer" /> : undefined}
      >
        <MessageCircle /> WhatsApp
      </Button>
      {podeEnviar && (
        <Button size="xs" variant="ghost" onClick={() => setAberto(true)} title="Enviar agora o lembrete desta aula">
          <Send /> Enviar agora
        </Button>
      )}
      <ConfirmDialog
        open={aberto}
        onOpenChange={setAberto}
        titulo="Enviar lembrete agora?"
        descricao={
          previa.isLoading ? (
            "Carregando o texto…"
          ) : previa.isError ? (
            "Não foi possível montar a mensagem."
          ) : (
            <span className="block whitespace-pre-wrap rounded-md bg-muted p-3 text-sm text-foreground">{previa.data?.mensagem}</span>
          )
        }
        confirmar="Enviar"
        carregando={enviar.isPending}
        desabilitado={!previa.data?.tem_celular}
        onConfirm={() => enviar.mutate()}
      />
    </>
  );
}
