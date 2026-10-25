"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Eye, Loader2, Send, UserRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SeletorAluno } from "@/components/comunicacao/seletor-aluno";
import { Field } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AlunoBusca } from "@/lib/tipos-alunos";
import type { AvisoAlunoPrevia, EnvioResultado } from "@/lib/tipos-comunicacao";

/** Aviso a UM aluno: escolhe o aluno, escreve, vê a prévia (texto final) e envia. */
export function AvisoAluno() {
  const { pode } = useAuth();
  const [aluno, setAluno] = useState<AlunoBusca | null>(null);
  const [texto, setTexto] = useState("");
  const corpo = { aluno_id: aluno?.id, texto };

  const previa = useQuery({
    queryKey: ["comunicacao", "aviso-previa", aluno?.id, texto],
    queryFn: () => api.post<AvisoAlunoPrevia>("/comunicacao/aviso-aluno/previa", corpo),
    enabled: !!aluno && texto.trim().length > 0,
    meta: { silencioso: true },
  });
  const enviar = useMutation({
    mutationFn: () => api.post<EnvioResultado>("/comunicacao/aviso-aluno", corpo),
    onSuccess: () => {
      toast.success("Aviso enviado");
      setTexto("");
    },
  });
  const pronto = !!aluno && texto.trim().length > 0 && previa.data?.tem_celular !== false;

  return (
    <div className="card-surface max-w-3xl space-y-4 p-5">
      <p className="text-sm text-muted-foreground">
        Envia uma mensagem de WhatsApp a um aluno. Variáveis: <code className="rounded bg-muted px-1">{"{aluno}"}</code>{" "}
        <code className="rounded bg-muted px-1">{"{unidade}"}</code>.
      </p>
      <Field label="Aluno">
        <SeletorAluno valor={aluno} onChange={setAluno} />
      </Field>
      <Field label="Mensagem">
        <Textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={5} maxLength={4000} placeholder="Olá {aluno}, …" />
      </Field>
      {aluno && texto.trim() && (
        <div className="rounded-xl border bg-muted/40 p-3.5">
          <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Eye className="size-3.5" /> Prévia (como o aluno vai receber)
          </p>
          {previa.data ? (
            <>
              <p className="text-sm whitespace-pre-wrap">{previa.data.mensagem}</p>
              {!previa.data.tem_celular && (
                <p className="mt-2 flex items-center gap-1.5 text-xs text-danger-ink">
                  <UserRound className="size-3.5" /> Este aluno não tem um celular válido cadastrado.
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Carregando prévia…</p>
          )}
        </div>
      )}
      <div className="flex justify-end">
        <Button disabled={!pronto || !pode("comunicacao.enviar") || enviar.isPending} onClick={() => enviar.mutate()}>
          {enviar.isPending ? <Loader2 className="animate-spin" /> : <Send />} Enviar aviso
        </Button>
      </div>
    </div>
  );
}
