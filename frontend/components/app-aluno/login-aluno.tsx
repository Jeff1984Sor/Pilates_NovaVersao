"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ClientLogo } from "@/components/mayacorp/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useBrand } from "@/lib/brand";

import { apiAluno } from "./api-aluno";
import { maskCpf } from "./formatar";

const ESPERA_REENVIO_S = 45;

/** Entrada do aluno: 1) CPF, 2) código de 6 dígitos recebido por WhatsApp. */
export function LoginAluno() {
  const router = useRouter();
  const qc = useQueryClient();
  const { nome_exibicao } = useBrand();
  const [cpf, setCpf] = useState("");
  const [codigo, setCodigo] = useState("");
  const [etapa, setEtapa] = useState<"cpf" | "codigo">("cpf");
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [espera, setEspera] = useState(0);

  useEffect(() => {
    if (espera <= 0) return;
    const t = setTimeout(() => setEspera((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [espera]);

  const pedir = useMutation({
    meta: { silencioso: true },
    mutationFn: () => apiAluno<{ mensagem: string }>("/auth/codigo", { method: "POST", body: { cpf } }),
    onSuccess: (r) => {
      setErro(null);
      setAviso(r.mensagem);
      setCodigo("");
      setEtapa("codigo");
      setEspera(ESPERA_REENVIO_S);
    },
    onError: (e) => setErro(e.message),
  });

  const entrar = useMutation({
    meta: { silencioso: true },
    mutationFn: () => apiAluno("/auth/verificar", { method: "POST", body: { cpf, codigo } }),
    onSuccess: async () => {
      qc.clear();
      router.replace("/app");
    },
    onError: (e) => setErro(e.message),
  });

  const cpfCompleto = cpf.replace(/\D/g, "").length === 11;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-6 py-10 pt-[max(2.5rem,env(safe-area-inset-top))]">
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <ClientLogo className="size-16" compacto />
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{nome_exibicao}</h1>
          <p className="text-sm text-muted-foreground">Suas aulas, confirmações e reposições</p>
        </div>
      </div>

      {etapa === "cpf" ? (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            setErro(null);
            if (cpfCompleto) pedir.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="cpf" className="text-sm">
              Seu CPF
            </Label>
            <Input
              id="cpf"
              value={cpf}
              onChange={(e) => setCpf(maskCpf(e.target.value))}
              inputMode="numeric"
              autoComplete="off"
              placeholder="000.000.000-00"
              className="h-12 text-lg"
              autoFocus
            />
            <p className="text-xs text-muted-foreground">Enviaremos um código por WhatsApp para o telefone do seu cadastro.</p>
          </div>
          {erro && (
            <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-ink">
              {erro}
            </p>
          )}
          <Button type="submit" className="h-12 w-full text-base" disabled={!cpfCompleto || pedir.isPending}>
            {pedir.isPending && <Loader2 className="animate-spin" />}
            Receber código
          </Button>
        </form>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            setErro(null);
            if (codigo.length === 6) entrar.mutate();
          }}
        >
          <div className="flex items-start gap-3 rounded-xl bg-brand/10 p-3 text-sm">
            <MessageCircle className="mt-0.5 size-4 shrink-0 text-brand" />
            <p>{aviso}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="codigo" className="text-sm">
              Código de 6 dígitos
            </Label>
            <Input
              id="codigo"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="000000"
              maxLength={6}
              className="h-14 text-center text-2xl tracking-[0.5em]"
              autoFocus
            />
            <p className="text-xs text-muted-foreground">O código vale por 10 minutos e só funciona uma vez.</p>
          </div>
          {erro && (
            <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-ink">
              {erro}
            </p>
          )}
          <Button type="submit" className="h-12 w-full text-base" disabled={codigo.length !== 6 || entrar.isPending}>
            {entrar.isPending && <Loader2 className="animate-spin" />}
            Entrar
          </Button>
          <div className="flex items-center justify-between">
            <button
              type="button"
              className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground"
              onClick={() => {
                setEtapa("cpf");
                setErro(null);
              }}
            >
              <ArrowLeft className="size-4" /> Trocar CPF
            </button>
            <button
              type="button"
              className="min-h-11 text-sm font-medium text-brand disabled:text-muted-foreground"
              disabled={espera > 0 || pedir.isPending}
              onClick={() => pedir.mutate()}
            >
              {espera > 0 ? `Reenviar em ${espera}s` : "Reenviar código"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
