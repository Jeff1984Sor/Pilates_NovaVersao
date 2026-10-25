"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CircleCheck, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { AssinaturaPad } from "@/components/alunos/assinatura-pad";
import { Field } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { dataHora } from "@/lib/format";
import type { Assinado, ContratoPublico, TermoPublico } from "@/lib/tipos-contratos";

import { mascaraCpf } from "./comum";

export function cpfValido(valor: string): boolean {
  const d = valor.replace(/\D/g, "");
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  for (const tam of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < tam; i++) soma += Number(d[i]) * (tam + 1 - i);
    if (((soma * 10) % 11) % 10 !== Number(d[tam])) return false;
  }
  return true;
}

const ESTILO_DOCUMENTO =
  "text-sm leading-relaxed text-foreground [&_h1]:mb-2 [&_h1]:text-xl [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-bold [&_h3]:mb-2 [&_h3]:font-semibold " +
  "[&_p]:mb-2 [&_ul]:mb-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-2 [&_ol]:list-decimal [&_ol]:pl-6 [&_table]:mb-2 [&_table]:w-full [&_td]:border [&_td]:p-1.5 [&_th]:border [&_th]:p-1.5 [&_a]:underline";

function Aviso({ tom, titulo, texto }: { tom: "erro" | "ok"; titulo: string; texto: string }) {
  const Icone = tom === "erro" ? ShieldAlert : CircleCheck;
  return (
    <div className="card-surface mx-auto max-w-lg space-y-2 p-8 text-center">
      <Icone className={`mx-auto size-10 ${tom === "erro" ? "text-danger" : "text-success"}`} />
      <h1 className="text-xl font-semibold">{titulo}</h1>
      <p className="text-sm text-muted-foreground">{texto}</p>
    </div>
  );
}

/**
 * Página PÚBLICA de assinatura (sem login) de contrato ou termo de imagem. O token do link é a credencial; o servidor
 * responde igual para link inválido e inexistente, e nunca devolve o texto de documento já assinado.
 */
export function PaginaAssinatura({ tipo, token }: { tipo: "contrato" | "termo"; token: string }) {
  const rotulo = tipo === "contrato" ? "contrato" : "termo de uso de imagem";
  const caminho = `/assinar/${tipo}/${encodeURIComponent(token)}`;
  const doc = useQuery({
    queryKey: ["assinar", tipo, token],
    queryFn: () => api<ContratoPublico | TermoPublico>(caminho, { auth: false }),
    retry: false,
    staleTime: Infinity,
    meta: { silencioso: true },
  });
  const [nome, setNome] = useState("");
  const [cpf, setCpf] = useState("");
  const [png, setPng] = useState<string | null>(null);
  const [concordo, setConcordo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pronto, setPronto] = useState<Assinado | null>(null);

  const enviar = useMutation({
    mutationFn: () => api.post<Assinado>(caminho, { nome, documento: cpf, assinatura: png, li_e_concordo: concordo }, { auth: false }),
    onSuccess: setPronto,
    onError: (e) => setErro(e.message),
    meta: { silencioso: true },
  });

  if (doc.isPending) return <Skeleton className="mx-auto h-96 w-full max-w-3xl rounded-2xl" />;
  if (doc.isError) {
    const e = doc.error;
    if (e instanceof ApiError && e.status === 410) return <Aviso tom="erro" titulo="Este link expirou" texto={`Peça um novo link de assinatura ao estúdio.`} />;
    if (e instanceof ApiError && e.status === 429) return <Aviso tom="erro" titulo="Muitas tentativas" texto="Aguarde um minuto e tente de novo." />;
    if (e instanceof ApiError && e.status === 409) return <Aviso tom="erro" titulo="Ainda não disponível" texto={e.message} />;
    return <Aviso tom="erro" titulo="Link inválido" texto="Confira se o endereço está completo ou peça um novo link ao estúdio." />;
  }
  const d = doc.data;
  if (pronto) return <Aviso tom="ok" titulo="Assinatura registrada" texto={`${pronto.mensagem} (${dataHora(pronto.assinado_em)})`} />;
  if (d.estado === "assinado") {
    return (
      <Aviso
        tom="ok"
        titulo={`Este ${rotulo} já foi assinado`}
        texto={`${d.assinado_em ? `Assinatura registrada em ${dataHora(d.assinado_em)}. ` : ""}Não é preciso fazer mais nada.`}
      />
    );
  }

  const cpfOk = cpfValido(cpf);
  const nomeOk = nome.trim().split(/\s+/).length >= 2 && nome.trim().length >= 5;
  const pode = nomeOk && cpfOk && !!png && concordo;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5">
      <header className="text-center">
        <p className="text-sm text-muted-foreground">{d.estudio_nome}</p>
        <h1 className="text-2xl font-semibold tracking-tight">
          {tipo === "contrato" ? `Contrato nº ${(d as ContratoPublico).numero}` : ((d as TermoPublico).termo_nome ?? "Termo de uso de imagem")}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">Olá, {d.aluno_primeiro_nome}! Leia com atenção e assine ao final.</p>
      </header>

      <section aria-label={`Texto do ${rotulo}`} className="card-surface max-h-[60dvh] overflow-y-auto p-5">
        <div className={ESTILO_DOCUMENTO} dangerouslySetInnerHTML={{ __html: d.html ?? "" }} />
      </section>

      <form
        className="card-surface space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          setErro(null);
          if (!pode) return setErro("Preencha seu nome completo, um CPF válido, desenhe a assinatura e marque a confirmação.");
          enviar.mutate();
        }}
      >
        <h2 className="flex items-center gap-2 font-semibold">
          <ShieldCheck className="size-4 text-success" /> Assinatura
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nome completo" obrigatorio erro={nome && !nomeOk ? "Informe nome e sobrenome." : undefined}>
            <Input value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="name" maxLength={150} required />
          </Field>
          <Field label="CPF" obrigatorio erro={cpf.replace(/\D/g, "").length === 11 && !cpfOk ? "CPF inválido." : undefined}>
            <Input value={cpf} onChange={(e) => setCpf(mascaraCpf(e.target.value))} inputMode="numeric" placeholder="000.000.000-00" required />
          </Field>
        </div>
        <div>
          <p className="mb-1.5 text-[13px] text-foreground/80">
            Desenhe sua assinatura <span className="text-danger">*</span>
          </p>
          <AssinaturaPad onChange={setPng} />
        </div>
        <label className="flex items-start gap-2 text-sm">
          <Checkbox checked={concordo} onCheckedChange={(v) => setConcordo(!!v)} className="mt-0.5" />
          <span>Li o {rotulo} e concordo com os termos. Sei que meu IP e a data ficam registrados.</span>
        </label>
        {erro && (
          <p role="alert" className="rounded-lg bg-danger/10 p-2.5 text-sm text-danger-ink">
            {erro}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={enviar.isPending || !pode}>
          {enviar.isPending && <Loader2 className="animate-spin" />} Assinar {rotulo}
        </Button>
      </form>
    </div>
  );
}
