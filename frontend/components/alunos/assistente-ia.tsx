"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileText, Home, Loader2, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { ChaveCampoIA, DadosAssistenteIA, RascunhoIA, StatusIA } from "@/lib/tipos-app-aluno";
import { cn } from "@/lib/utils";

/**
 * Modal "Preencher com IA" do cadastro do aluno.
 *
 * Fluxo: o usuário envia a foto/PDF do documento de identidade e/ou do comprovante de endereço; a IA devolve um RASCUNHO
 * (nada é gravado no servidor). O usuário confere e corrige cada campo (os incertos vêm destacados) e só então clica em
 * "Aplicar ao cadastro", que chama `onAplicar(dados)`. Quem usa o componente decide como preencher o formulário.
 *
 * Formatos de `dados`: `cpf` e `cep` só dígitos, `data_nascimento` em AAAA-MM-DD, demais textos já limpos. Só vão os campos
 * preenchidos (o que ficou em branco não apaga nada do formulário).
 *
 * Uso (coordenador): <AssistenteIA open={aberto} onOpenChange={setAberto} onAplicar={(d) => preencherFormulario(d)} />
 * Requer a permissão `ia.usar`; sem ela a API responde 403 e o usuário vê a mensagem.
 */
export function AssistenteIA({
  open,
  onOpenChange,
  onAplicar,
}: {
  open: boolean;
  onOpenChange: (aberto: boolean) => void;
  onAplicar: (dados: DadosAssistenteIA) => void;
}) {
  const status = useQuery({
    queryKey: ["ia-cadastro", "status"],
    queryFn: () => api.get<StatusIA>("/ia/cadastro/status"),
    enabled: open,
    staleTime: 60_000,
    meta: { silencioso: true },
  });
  const [valores, setValores] = useState<Partial<Record<ChaveCampoIA, string>>>({});
  const [incertos, setIncertos] = useState<Partial<Record<ChaveCampoIA, string | null>>>({});
  const [lido, setLido] = useState<{ documento?: boolean; comprovante?: boolean }>({});

  const ler = useMutation({
    mutationFn: async ({ tipo, arquivo }: { tipo: "documento" | "comprovante"; arquivo: File }) => {
      const form = new FormData();
      form.append("arquivo", arquivo);
      return api.post<RascunhoIA>(`/ia/cadastro/${tipo}`, form);
    },
    onSuccess: (r) => {
      setValores((v) => {
        const novo = { ...v };
        r.campos.forEach((c) => {
          if (c.valor) novo[c.chave] = c.valor;
        });
        return novo;
      });
      setIncertos((v) => {
        const novo = { ...v };
        r.campos.forEach((c) => {
          novo[c.chave] = c.incerto ? (c.aviso ?? "Confira este campo.") : null;
        });
        return novo;
      });
      setLido((l) => ({ ...l, [r.tipo]: true }));
    },
  });

  function fechar(aberto: boolean) {
    if (!aberto) {
      setValores({});
      setIncertos({});
      setLido({});
      ler.reset();
    }
    onOpenChange(aberto);
  }

  function aplicar() {
    const dados: DadosAssistenteIA = {};
    (Object.keys(valores) as ChaveCampoIA[]).forEach((k) => {
      const v = (valores[k] ?? "").trim();
      if (v) dados[k] = v;
    });
    onAplicar(dados);
    fechar(false);
  }

  const indisponivel = status.data && !status.data.disponivel;
  const temAlgo = Object.values(valores).some((v) => (v ?? "").trim());
  const pendentes = Object.values(incertos).filter(Boolean).length;

  return (
    <Dialog open={open} onOpenChange={fechar}>
      <DialogContent className="max-h-[92dvh] gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="border-b p-5">
          <DialogTitle className="flex items-center gap-2 text-lg">
            <Sparkles className="size-5 text-brand" /> Preencher com IA
          </DialogTitle>
          <DialogDescription>
            Envie o documento de identidade e o comprovante de endereço. A IA lê e sugere os dados; <strong>nada é salvo</strong> até você conferir e
            aplicar ao cadastro.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[64dvh] space-y-5 overflow-y-auto p-5">
          {indisponivel && (
            <div role="alert" className="flex items-start gap-3 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-ink" />
              <div>
                <p className="font-medium">A IA ainda não está configurada.</p>
                <p className="text-muted-foreground">
                  Informe a chave e escolha o modelo em{" "}
                  <Link href="/configuracoes/ia" className="font-medium text-brand underline underline-offset-2" onClick={() => fechar(false)}>
                    Configurações › Inteligência Artificial
                  </Link>
                  .
                </p>
              </div>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Envio
              icone={FileText}
              titulo="Documento de identidade"
              dica="RG ou CNH: nome, CPF, RG e nascimento"
              lido={!!lido.documento}
              carregando={ler.isPending && ler.variables?.tipo === "documento"}
              desabilitado={!!indisponivel || ler.isPending}
              onArquivo={(arquivo) => ler.mutate({ tipo: "documento", arquivo })}
            />
            <Envio
              icone={Home}
              titulo="Comprovante de endereço"
              dica="Conta de luz, água ou telefone: rua, número, bairro, cidade e CEP"
              lido={!!lido.comprovante}
              carregando={ler.isPending && ler.variables?.tipo === "comprovante"}
              desabilitado={!!indisponivel || ler.isPending}
              onArquivo={(arquivo) => ler.mutate({ tipo: "comprovante", arquivo })}
            />
          </div>

          {ler.isError && (
            <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-ink">
              {ler.error.message}
            </p>
          )}

          {(lido.documento || lido.comprovante) && (
            <div className="space-y-4">
              {pendentes > 0 && (
                <p className="flex items-center gap-2 text-sm text-warning-ink">
                  <AlertTriangle className="size-4" /> {pendentes} {pendentes === 1 ? "campo precisa" : "campos precisam"} de conferência (em destaque).
                </p>
              )}
              {lido.documento && (
                <Bloco titulo="Documento de identidade">
                  <Campo chave="nome" rotulo="Nome" valores={valores} incertos={incertos} onChange={setValores} className="sm:col-span-2" />
                  <Campo chave="cpf" rotulo="CPF" valores={valores} incertos={incertos} onChange={setValores} mascara={mascaraCpf} />
                  <Campo chave="rg" rotulo="RG" valores={valores} incertos={incertos} onChange={setValores} />
                  <Campo chave="data_nascimento" rotulo="Data de nascimento" valores={valores} incertos={incertos} onChange={setValores} tipo="date" />
                </Bloco>
              )}
              {lido.comprovante && (
                <Bloco titulo="Endereço">
                  <Campo chave="cep" rotulo="CEP" valores={valores} incertos={incertos} onChange={setValores} mascara={mascaraCep} />
                  <Campo chave="logradouro" rotulo="Logradouro" valores={valores} incertos={incertos} onChange={setValores} />
                  <Campo chave="numero" rotulo="Número" valores={valores} incertos={incertos} onChange={setValores} />
                  <Campo chave="bairro" rotulo="Bairro" valores={valores} incertos={incertos} onChange={setValores} />
                  <Campo chave="cidade" rotulo="Cidade" valores={valores} incertos={incertos} onChange={setValores} />
                </Bloco>
              )}
              <p className="text-xs text-muted-foreground">
                Confira com o documento original. A IA pode errar, principalmente em fotos escuras ou tortas.
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="m-0 rounded-none p-4">
          <Button type="button" variant="outline" onClick={() => fechar(false)}>
            Cancelar
          </Button>
          <Button type="button" disabled={!temAlgo || ler.isPending} onClick={aplicar} className="px-4">
            <CheckCircle2 /> Aplicar ao cadastro
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const mascaraCpf = (v: string) => {
  const d = v.replace(/\D/g, "").slice(0, 11);
  return d
    .replace(/^(\d{3})(\d)/, "$1.$2")
    .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1-$2");
};
const mascaraCep = (v: string) => {
  const d = v.replace(/\D/g, "").slice(0, 8);
  return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
};

function Envio({
  icone: Icone,
  titulo,
  dica,
  lido,
  carregando,
  desabilitado,
  onArquivo,
}: {
  icone: React.ComponentType<{ className?: string }>;
  titulo: string;
  dica: string;
  lido: boolean;
  carregando: boolean;
  desabilitado: boolean;
  onArquivo: (f: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className={cn("flex flex-col gap-2 rounded-xl border border-dashed p-4", lido && "border-success/50 bg-success/5")}>
      <div className="flex items-center gap-2">
        <Icone className="size-4 text-muted-foreground" />
        <p className="text-sm font-medium">{titulo}</p>
        {lido && <CheckCircle2 className="ml-auto size-4 text-success" />}
      </div>
      <p className="text-xs text-muted-foreground">{dica}</p>
      <input
        ref={ref}
        type="file"
        accept="image/png,image/jpeg,image/webp,application/pdf,.png,.jpg,.jpeg,.webp,.pdf"
        className="sr-only"
        aria-label={`Enviar ${titulo}`}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onArquivo(f);
          e.target.value = ""; // permite reenviar o mesmo arquivo
        }}
      />
      <Button type="button" variant="outline" disabled={desabilitado} onClick={() => ref.current?.click()}>
        {carregando ? <Loader2 className="animate-spin" /> : <Upload />}
        {carregando ? "Lendo..." : lido ? "Enviar outro" : "Enviar foto ou PDF"}
      </Button>
    </div>
  );
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">{titulo}</h3>
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function Campo({
  chave,
  rotulo,
  valores,
  incertos,
  onChange,
  mascara,
  tipo,
  className,
}: {
  chave: ChaveCampoIA;
  rotulo: string;
  valores: Partial<Record<ChaveCampoIA, string>>;
  incertos: Partial<Record<ChaveCampoIA, string | null>>;
  onChange: React.Dispatch<React.SetStateAction<Partial<Record<ChaveCampoIA, string>>>>;
  mascara?: (v: string) => string;
  tipo?: "date";
  className?: string;
}) {
  const aviso = incertos[chave];
  const bruto = valores[chave] ?? "";
  // CPF e CEP ficam guardados só com dígitos; a máscara é só de exibição
  const mostrado = mascara ? mascara(bruto) : bruto;
  const id = `ia-${chave}`;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id} className="text-[13px]">
        {rotulo}
      </Label>
      <Input
        id={id}
        type={tipo ?? "text"}
        value={mostrado}
        aria-invalid={!!aviso}
        aria-describedby={aviso ? `${id}-aviso` : undefined}
        className={cn(aviso && "border-warning bg-warning/10 ring-1 ring-warning/40")}
        onChange={(e) => {
          const v = mascara ? e.target.value.replace(/\D/g, "") : e.target.value;
          onChange((atual) => ({ ...atual, [chave]: v }));
        }}
      />
      {aviso && (
        <p id={`${id}-aviso`} className="flex items-start gap-1 text-xs text-warning-ink">
          <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {aviso}
        </p>
      )}
    </div>
  );
}
