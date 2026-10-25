"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Loader2, Save, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Field, SwitchRow } from "@/components/mayacorp/form";
import { PageHeader } from "@/components/mayacorp/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ModeloContrato, Termo, VariavelModelo } from "@/lib/tipos-cadastros-docs";

import { Carregando, ConfirmarExclusao, Guarda } from "./comum";
import { DOCUMENTOS, type TipoDocumento } from "./documentos";
import { EditorHtml } from "./editor-html";

type Documento = Termo | ModeloContrato;

function Conteudo({ tipo, id }: { tipo: TipoDocumento; id: string }) {
  const cfg = DOCUMENTOS[tipo];
  const novo = id === "novo";
  const doc = useQuery({
    queryKey: ["documento", tipo, id],
    queryFn: () => api.get<Documento>(`${cfg.api}/${id}`),
    enabled: !novo,
  });
  const variaveis = useQuery({
    queryKey: ["variaveis-documento", cfg.variaveisPath],
    queryFn: () => api.get<VariavelModelo[]>(cfg.variaveisPath, tipo === "contrato" ? { escopo: "contrato" } : undefined),
    staleTime: 10 * 60_000,
  });
  if ((!novo && doc.isPending) || variaveis.isPending) return <Carregando />;
  if (!novo && !doc.data) return <p className="text-sm text-danger-ink">Não foi possível abrir este documento.</p>;
  // o formulário nasce já com os dados carregados (sem efeitos para copiar estado)
  return <Formulario key={novo ? "novo" : String(doc.data?.id)} tipo={tipo} id={id} doc={doc.data} variaveis={variaveis.data ?? []} />;
}

function Formulario({ tipo, id, doc, variaveis }: { tipo: TipoDocumento; id: string; doc?: Documento; variaveis: VariavelModelo[] }) {
  const cfg = DOCUMENTOS[tipo];
  const novo = id === "novo";
  const router = useRouter();
  const qc = useQueryClient();
  const { pode } = useAuth();
  const podeEditar = pode(`${cfg.permissao}.editar`);
  const podeExcluir = pode(`${cfg.permissao}.excluir`);

  const schema = useMemo(
    () =>
      z.object({
        nome: z.string().trim().min(2, "Informe o nome (mínimo de 2 letras).").max(cfg.nomeMax, `Máximo de ${cfg.nomeMax} caracteres.`),
        ativo: z.boolean(),
      }),
    [cfg.nomeMax],
  );
  type Dados = z.infer<typeof schema>;
  const ativoInicial = doc && "ativo" in doc ? doc.ativo : true;
  const form = useForm<Dados>({ resolver: zodResolver(schema), defaultValues: { nome: doc?.nome ?? "", ativo: ativoInicial } });
  const [html, setHtml] = useState(doc?.conteudo_html ?? "");
  const [inicial, setInicial] = useState({ nome: doc?.nome ?? "", html: doc?.conteudo_html ?? "", ativo: ativoInicial });
  const [apagar, setApagar] = useState(false);

  const nome = useWatch({ control: form.control, name: "nome" });
  const ativo = useWatch({ control: form.control, name: "ativo" });
  const sujo = html !== inicial.html || nome !== inicial.nome || ativo !== inicial.ativo;
  useEffect(() => {
    if (!sujo) return;
    const avisar = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", avisar);
    return () => window.removeEventListener("beforeunload", avisar);
  }, [sujo]);

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: [cfg.chave] });
    qc.invalidateQueries({ queryKey: ["documento", tipo] });
  };

  const salvar = useMutation({
    mutationFn: (d: Dados) => {
      const corpo = { nome: d.nome, conteudo_html: html, ...(cfg.temAtivo ? { ativo: d.ativo } : {}) };
      return novo ? api.post<Documento>(cfg.api, corpo) : api.put<Documento>(`${cfg.api}/${id}`, corpo);
    },
    onSuccess: (salvo) => {
      toast.success(novo ? "Documento criado" : "Alterações salvas");
      invalidar();
      setInicial({ nome: salvo.nome, html: salvo.conteudo_html, ativo: "ativo" in salvo ? salvo.ativo : true });
      if (salvo.variaveis_desconhecidas.length)
        toast.warning("Há variáveis não reconhecidas no texto", { description: salvo.variaveis_desconhecidas.map((c) => `{${c}}`).join(", ") });
      if (novo) router.replace(`${cfg.rota}/${salvo.id}`);
    },
  });

  const duplicar = useMutation({
    mutationFn: () => api.post<Documento>(`${cfg.api}/${id}/duplicar`),
    onSuccess: (copia) => {
      toast.success("Cópia criada", { description: copia.nome });
      invalidar();
      router.push(`${cfg.rota}/${copia.id}`);
    },
  });

  const remover = useMutation({
    mutationFn: () => api.del(`${cfg.api}/${id}`),
    meta: { silencioso: true },
    onSuccess: () => {
      toast.success("Documento excluído");
      invalidar();
      router.replace(cfg.rota);
    },
  });

  const vinculo = !novo && doc ? (doc as unknown as Record<string, number>)[cfg.vinculo.campo] : 0;
  const titulo = novo ? cfg.tituloNovo : (doc?.nome ?? cfg.titulo);

  return (
    <div>
      <PageHeader
        titulo={titulo}
        descricao={cfg.descricao}
        icone={cfg.icone}
        migalhas={[{ label: "Início", href: "/" }, { label: "Cadastros" }, { label: cfg.titulo, href: cfg.rota }, { label: novo ? "Novo" : "Editar" }]}
        acoes={
          <>
            {!novo && podeEditar && (
              <Button variant="outline" onClick={() => duplicar.mutate()} disabled={duplicar.isPending}>
                {duplicar.isPending ? <Loader2 className="animate-spin" /> : <Copy />} Duplicar
              </Button>
            )}
            {!novo && podeExcluir && (
              <Button variant="outline" onClick={() => setApagar(true)}>
                <Trash2 /> Excluir
              </Button>
            )}
            {podeEditar && (
              <Button onClick={form.handleSubmit((d) => salvar.mutate(d))} disabled={salvar.isPending || (!novo && !sujo)}>
                {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar
              </Button>
            )}
          </>
        }
      />
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field label="Nome" obrigatorio erro={form.formState.errors.nome?.message}>
            <Input {...form.register("nome")} maxLength={cfg.nomeMax} autoComplete="off" disabled={!podeEditar} />
          </Field>
          {cfg.temAtivo && (
            <Controller
              control={form.control}
              name="ativo"
              render={({ field }) => (
                <SwitchRow titulo="Ativo" descricao={cfg.descAtivo}>
                  <Switch checked={field.value} onCheckedChange={field.onChange} disabled={!podeEditar} />
                </SwitchRow>
              )}
            />
          )}
        </div>
        {vinculo > 0 && (
          <p className="rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground">
            {vinculo} {vinculo === 1 ? cfg.vinculo.singular : cfg.vinculo.plural} {tipo === "termo" ? "este termo" : "usam este modelo"}. Mudar o texto vale
            para os próximos documentos gerados.
          </p>
        )}
        <EditorHtml
          chave={novo ? "novo" : String(doc?.id)}
          valorInicial={doc?.conteudo_html ?? ""}
          onChange={setHtml}
          variaveis={variaveis}
          previaPath={cfg.previaPath}
          somenteLeitura={!podeEditar}
        />
      </div>
      <ConfirmarExclusao
        alvo={apagar}
        titulo={`Excluir ${doc?.nome ?? "documento"}?`}
        descricao={vinculo > 0 ? `Há ${vinculo} ${vinculo === 1 ? cfg.vinculo.singular : cfg.vinculo.plural}; a exclusão será recusada.` : "Esta ação não pode ser desfeita."}
        carregando={remover.isPending}
        erro={remover.error instanceof ApiError ? remover.error.message : null}
        onConfirm={() => remover.mutate()}
        onClose={() => {
          setApagar(false);
          remover.reset();
        }}
      />
    </div>
  );
}

export function PaginaDocumento({ tipo, id }: { tipo: TipoDocumento; id: string }) {
  const cfg = DOCUMENTOS[tipo];
  return (
    <Guarda permissao={`${cfg.permissao}.ver`}>
      <Conteudo tipo={tipo} id={id} />
    </Guarda>
  );
}
