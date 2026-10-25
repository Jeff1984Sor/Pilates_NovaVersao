"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ImageOff, Link2, PenLine, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect } from "@/components/mayacorp/form";
import { FormDialog } from "@/components/mayacorp/form-dialog";
import { Pill } from "@/components/mayacorp/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useFoto } from "@/hooks/use-foto";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dataHora } from "@/lib/format";
import type { TermoEstado } from "@/lib/tipos-alunos";

import { AssinaturaPad } from "./assinatura-pad";
import { useAluno } from "./aba-dados";
import { mascaraCpf } from "./mascaras";

function Assinatura({ url }: { url: string }) {
  const src = useFoto(url);
  if (!src) return <Skeleton className="h-28 w-64" />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt="Assinatura do aluno" className="h-28 rounded-lg border bg-white object-contain p-2" />;
}

/** Aba "Uso da imagem": estado do termo, aceite registrado e assinatura feita na tela do estúdio. */
export function AbaImagem({ alunoId }: { alunoId: number }) {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const podeEditar = pode("alunos.editar");
  const aluno = useAluno(alunoId);
  const termo = useQuery({ queryKey: ["aluno", alunoId, "termo"], queryFn: () => api.get<TermoEstado>(`/alunos/${alunoId}/termo`) });
  const [assinando, setAssinando] = useState(false);
  const [termoId, setTermoId] = useState("");
  const [nome, setNome] = useState("");
  const [documento, setDocumento] = useState("");
  const [png, setPng] = useState<string | null>(null);

  const atualizar = (t: TermoEstado) => {
    qc.setQueryData(["aluno", alunoId, "termo"], t);
    qc.invalidateQueries({ queryKey: ["aluno", alunoId] });
    qc.invalidateQueries({ queryKey: ["alunos"] });
  };

  const registrar = useMutation({
    mutationFn: (id: number) => api.post<TermoEstado>(`/alunos/${alunoId}/termo/registrar`, { termo_id: id }),
    onSuccess: (t) => {
      toast.success("Aceite do termo registrado");
      atualizar(t);
    },
  });
  const assinar = useMutation({
    mutationFn: () =>
      api.post<TermoEstado>(`/alunos/${alunoId}/termo/assinatura-local`, {
        termo_id: termoId ? Number(termoId) : null,
        nome: nome.trim(),
        documento: documento.trim() || null,
        assinatura: png,
      }),
    onSuccess: (t) => {
      toast.success("Termo assinado e uso de imagem autorizado");
      atualizar(t);
      setAssinando(false);
    },
  });

  if (termo.isPending) return <Skeleton className="h-96 rounded-2xl" />;
  if (termo.isError || !termo.data) return null;
  const t = termo.data;
  const termoAtual = termoId || (t.termo ? String(t.termo.id) : "");

  function abrirAssinatura() {
    setNome(aluno.data?.nome ?? "");
    setDocumento(aluno.data?.cpf ?? "");
    setTermoId(t.termo ? String(t.termo.id) : "");
    setPng(null);
    setAssinando(true);
  }

  return (
    <div className="space-y-4">
      <section className="card-surface p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className={`grid size-11 shrink-0 place-items-center rounded-xl ${t.autoriza_imagem ? "bg-success/12 text-success-ink" : "bg-muted text-muted-foreground"}`}>
              {t.autoriza_imagem ? <ShieldCheck className="size-5" /> : <ImageOff className="size-5" />}
            </div>
            <div>
              <h3 className="text-sm font-semibold">{t.autoriza_imagem ? "Uso de imagem autorizado" : "Uso de imagem não autorizado"}</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {t.assinado
                  ? `Termo assinado em ${dataHora(t.assinado_em)}${t.assinatura_nome ? ` por ${t.assinatura_nome}` : ""}.`
                  : t.aceite_em
                    ? `Aceite registrado em ${dataHora(t.aceite_em)}, sem imagem de assinatura.`
                    : "O aluno ainda não assinou nem aceitou o termo."}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {t.termo && <Pill tom="info">{t.termo.nome}</Pill>}
                {t.assinado && (
                  <Pill tom="success">
                    <CheckCircle2 className="size-3" /> Assinado
                  </Pill>
                )}
              </div>
            </div>
          </div>
          {podeEditar && (
            <div className="flex flex-wrap gap-2">
              <Button onClick={abrirAssinatura} disabled={!t.termo}>
                <PenLine /> {t.assinado ? "Assinar novamente" : "Assinar agora"}
              </Button>
              <Button variant="outline" disabled={!t.termo || registrar.isPending} onClick={() => t.termo && registrar.mutate(t.termo.id)}>
                Registrar aceite sem assinatura
              </Button>
              {/* Ponto de extensão: o envio do link de assinatura por WhatsApp entra na onda de comunicação. */}
              <Tooltip>
                <TooltipTrigger render={<span tabIndex={0} />}>
                  <Button variant="outline" disabled>
                    <Link2 /> Enviar link de assinatura
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Disponível quando o módulo de comunicação (WhatsApp) for ligado.</TooltipContent>
              </Tooltip>
            </div>
          )}
        </div>
        {!t.termo && (
          <p className="mt-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning-ink">
            Nenhum termo de uso de imagem cadastrado. Cadastre o texto em Cadastros &gt; Termos para poder colher a assinatura.
          </p>
        )}
      </section>

      {t.assinado && (
        <section className="card-surface p-5">
          <h3 className="mb-3 text-sm font-semibold">Assinatura registrada</h3>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            {t.assinatura_url && <Assinatura url={t.assinatura_url} />}
            <dl className="grid gap-2 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">Nome</dt>
                <dd>{t.assinatura_nome ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Documento</dt>
                <dd>{t.assinatura_documento ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Origem (IP)</dt>
                <dd>{t.assinatura_ip ?? "—"}</dd>
              </div>
            </dl>
          </div>
        </section>
      )}

      {t.texto_html && (
        <section className="card-surface p-5">
          <h3 className="mb-3 text-sm font-semibold">Texto do termo</h3>
          {/* iframe isolado (sandbox sem permissões): o HTML do termo nunca executa script na página */}
          <iframe title="Texto do termo de uso de imagem" sandbox="" srcDoc={`<base target="_blank"><body style="font-family:system-ui,sans-serif;font-size:14px;line-height:1.5;padding:12px;color:#222">${t.texto_html}</body>`} className="h-80 w-full rounded-lg border bg-white" />
        </section>
      )}

      <FormDialog
        open={assinando}
        onOpenChange={setAssinando}
        titulo="Assinar termo de uso de imagem"
        descricao="Peça ao aluno para assinar na tela (dedo, caneta ou mouse). Ao confirmar, o uso de imagem fica autorizado."
        rotuloSalvar="Confirmar assinatura"
        salvando={assinar.isPending}
        largura="lg"
        onSubmit={(e) => {
          e.preventDefault();
          if (nome.trim().length < 2) return void toast.error("Informe o nome de quem assina.");
          if (!png) return void toast.error("A assinatura está em branco.");
          assinar.mutate();
        }}
      >
        <div className="space-y-4">
          {t.termos_disponiveis.length > 1 && (
            <Field label="Termo">
              <NativeSelect value={termoAtual} onChange={(e) => setTermoId(e.target.value)}>
                {t.termos_disponiveis.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.nome}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nome de quem assina" obrigatorio>
              <Input value={nome} onChange={(e) => setNome(e.target.value)} maxLength={150} />
            </Field>
            <Field label="CPF / documento">
              <Input value={documento} onChange={(e) => setDocumento(mascaraCpf(e.target.value))} maxLength={30} />
            </Field>
          </div>
          <AssinaturaPad onChange={setPng} />
        </div>
      </FormDialog>
    </div>
  );
}
