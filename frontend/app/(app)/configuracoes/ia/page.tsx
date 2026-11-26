"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field, NativeSelect, SwitchRow } from "@/components/mayacorp/form";
import { SenhaInput } from "@/components/mayacorp/senha-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import type { ConfigIAOut } from "@/lib/types";

const OUTRO = "__outro__";

const AVISO =
  "Os textos enviados à IA (melhoria de evoluções, preenchimento de cadastros) vão ao provedor escolhido. Use uma conta empresarial com retenção de dados desligada e não envie mais do que o necessário.";

function Formulario({ cfg }: { cfg: ConfigIAOut }) {
  const qc = useQueryClient();
  const [ativo, setAtivo] = useState(cfg.ativo);
  const [provedor, setProvedor] = useState(cfg.provedor);
  const [modelo, setModelo] = useState(cfg.modelo ?? "");
  const [chave, setChave] = useState("");
  const lista = useQuery({
    queryKey: ["config-ia-modelos", cfg.provedor, cfg.chave_final],
    queryFn: () => api.get<string[]>("/config/ia/modelos"),
    enabled: cfg.chave_definida && provedor === cfg.provedor,
    retry: false,
  });
  const [digitar, setDigitar] = useState(false);
  const opcoes = lista.data ?? [];
  // lista de verdade (não <datalist>: o Chrome só sugere o que combina com o texto já digitado)
  const usarLista = provedor === cfg.provedor && opcoes.length > 0 && !digitar;
  const foraDaLista = usarLista && !!modelo && !opcoes.includes(modelo);
  const salvar = useMutation({
    mutationFn: () => api.put<ConfigIAOut>("/config/ia", { ativo, provedor, modelo: modelo || null, chave: chave || null }),
    onSuccess: (novo) => {
      qc.setQueryData(["config-ia"], novo);
      setChave("");
      toast.success("Configuração de IA salva");
    },
  });
  return (
    <form
      className="card-surface max-w-2xl space-y-4 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate();
      }}
    >
      <p className="rounded-lg border border-warning/30 bg-warning/8 px-3 py-2 text-xs text-warning-ink">{AVISO}</p>
      <SwitchRow titulo="Usar Inteligência Artificial" descricao="Liga os botões de IA nas telas que oferecem esse recurso.">
        <Switch checked={ativo} onCheckedChange={setAtivo} />
      </SwitchRow>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Provedor">
          <NativeSelect
            value={provedor}
            onChange={(e) => {
              const novo = e.target.value as ConfigIAOut["provedor"];
              setProvedor(novo);
              // o modelo de um provedor não existe no outro; volta ao salvo só se voltar ao provedor salvo
              setModelo(novo === cfg.provedor ? (cfg.modelo ?? "") : "");
              setDigitar(false);
            }}
          >
            {Object.entries(cfg.provedores).map(([id, nome]) => (
              <option key={id} value={id}>
                {nome}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field
          label="Modelo"
          dica={
            provedor !== cfg.provedor || !cfg.chave_definida
              ? "Cole a chave e clique em Salvar para carregar a lista de modelos deste provedor."
              : lista.isError
                ? `${(lista.error as Error).message} Você pode digitar o nome do modelo.`
                : lista.isLoading
                  ? "Carregando os modelos do provedor…"
                  : foraDaLista
                    ? `O modelo salvo (${modelo}) não existe neste provedor. Escolha um da lista.`
                    : "Escolha na lista. Se não achar, use “Outro (digitar o nome)”."
          }
        >
          {usarLista ? (
            <NativeSelect
              value={modelo && opcoes.includes(modelo) ? modelo : ""}
              onChange={(e) => {
                if (e.target.value === OUTRO) {
                  setDigitar(true);
                  setModelo("");
                } else setModelo(e.target.value);
              }}
            >
              <option value="">Escolha o modelo…</option>
              {opcoes.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              <option value={OUTRO}>Outro (digitar o nome)</option>
            </NativeSelect>
          ) : (
            <Input
              value={modelo}
              onChange={(e) => setModelo(e.target.value)}
              placeholder={provedor === "openai" ? "ex.: gpt-4o-mini" : "ex.: gemini-2.0-flash"}
            />
          )}
        </Field>
      </div>
      <Field
        label="Chave de API"
        dica={
          cfg.chave_definida
            ? `Chave salva (termina em ${cfg.chave_final}). Preencha só para trocar. Ela fica cifrada no banco.`
            : "Cole a chave do provedor. Ela fica cifrada no banco."
        }
      >
        <SenhaInput value={chave} onChange={setChave} autoComplete="off" />
      </Field>
      <div className="flex justify-end">
        <Button type="submit" disabled={salvar.isPending}>
          {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar
        </Button>
      </div>
    </form>
  );
}

export default function IAPage() {
  const q = useQuery({ queryKey: ["config-ia"], queryFn: () => api.get<ConfigIAOut>("/config/ia") });
  return (
    <div className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="size-5 text-info-ink" /> Inteligência Artificial
        </h2>
        <p className="text-sm text-muted-foreground">Provedor e chave usados pelos recursos de IA do sistema.</p>
      </div>
      {q.data ? <Formulario cfg={q.data} /> : <Skeleton className="h-72 max-w-2xl rounded-2xl" />}
    </div>
  );
}
